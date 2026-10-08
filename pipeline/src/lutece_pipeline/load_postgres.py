"""Step 11, database part - load the monuments and their photos into Postgres.

The step fills the `monuments` and `reference_images` tables that the
migrations of `supabase/` create. It can be run again at any time: a monument
keeps the same identifier from one load to the next, its row is updated, and
the photos that the pipeline no longer selects are removed. What later steps
will compute (rarity, texts, embeddings) is left untouched.

Run with: uv run python -m lutece_pipeline.load_postgres
"""

import argparse
import logging
import os
import uuid
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import geopandas as gpd
import pandas as pd
import psycopg
import shapely
from psycopg.types.json import Jsonb
from shapely.geometry import MultiPolygon, Point
from shapely.geometry.base import BaseGeometry

from lutece_pipeline import (
    geometry,
    ingest_commons,
    ingest_merimee,
    ingest_wikidata,
    resolve_entities,
    visibility,
)
from lutece_pipeline.tables import to_records

logger = logging.getLogger(__name__)

# The database of the local Supabase stack, with its well-known password.
LOCAL_DATABASE_URL = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
# Where to say which other database to load; its password must stay out of git.
DATABASE_URL_VARIABLE = "LUTECE_DATABASE_URL"
DATA_VERSION = 1
# Identifiers are derived from the Mérimée reference, so that a monument is the
# same row after every load: the captures of the players will point to it.
NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "monuments.lutece")
# Coordinates are written with 7 decimals: about a centimetre.
COORDINATE_DECIMALS = 7

MERIMEE_PARQUET = ingest_merimee.OUTPUT_PARQUET
ENTITIES_PARQUET = resolve_entities.ENTITIES_PARQUET
WIKIDATA_ITEMS_PARQUET = ingest_wikidata.ITEMS_PARQUET
GEOMETRIES_PARQUET = geometry.GEOMETRIES_PARQUET
VISIBILITY_PARQUET = visibility.VISIBILITY_PARQUET
COMMONS_FILES_PARQUET = ingest_commons.FILES_PARQUET

UPSERT_MONUMENT = """
insert into public.monuments (
    id, merimee_id, wikidata_qid, osm_id, name, address, arrondissement,
    location, footprint, footprint_source, category, period_start, architects,
    protection, protection_desc, visibility, sources, data_version
) values (
    %(id)s, %(merimee_id)s, %(wikidata_qid)s, %(osm_id)s, %(name)s, %(address)s,
    %(arrondissement)s, %(location)s::extensions.geography,
    %(footprint)s::extensions.geography, %(footprint_source)s, %(category)s,
    %(period_start)s, %(architects)s, %(protection)s, %(protection_desc)s,
    %(visibility)s, %(sources)s, %(data_version)s
)
on conflict (merimee_id) do update set
    wikidata_qid = excluded.wikidata_qid,
    osm_id = excluded.osm_id,
    name = excluded.name,
    address = excluded.address,
    arrondissement = excluded.arrondissement,
    location = excluded.location,
    footprint = excluded.footprint,
    footprint_source = excluded.footprint_source,
    category = excluded.category,
    period_start = excluded.period_start,
    architects = excluded.architects,
    protection = excluded.protection,
    protection_desc = excluded.protection_desc,
    visibility = excluded.visibility,
    sources = excluded.sources,
    data_version = excluded.data_version
"""
# The embedding of a photo is kept: it only depends on the file.
UPSERT_IMAGE = """
insert into public.reference_images (
    id, monument_id, source_url, thumb_url, author, licence, licence_url, rank
) values (
    %(id)s, %(monument_id)s, %(source_url)s, %(thumb_url)s, %(author)s,
    %(licence)s, %(licence_url)s, %(rank)s
)
on conflict (id) do update set
    monument_id = excluded.monument_id,
    source_url = excluded.source_url,
    thumb_url = excluded.thumb_url,
    author = excluded.author,
    licence = excluded.licence,
    licence_url = excluded.licence_url,
    rank = excluded.rank
"""
# Photos contributed by players are not the pipeline's to remove.
DELETE_OTHER_IMAGES = """
delete from public.reference_images
where not is_user_contributed and id <> all(%s)
"""
COUNT_OTHER_MONUMENTS = """
select count(*) from public.monuments where merimee_id <> all(%s)
"""

type Record = Mapping[str, Any]


def monument_id(merimee_id: str) -> uuid.UUID:
    """The identifier of a monument, always the same for a Mérimée reference."""
    return uuid.uuid5(NAMESPACE, merimee_id)


def image_id(merimee_id: str, title: str) -> uuid.UUID:
    """The identifier of a photo of a monument, always the same for a file."""
    return uuid.uuid5(NAMESPACE, f"{merimee_id}|{title}")


def to_ewkt(shape: BaseGeometry) -> str:
    """Write a WGS84 geometry the way PostGIS reads it."""
    return "SRID=4326;" + shapely.to_wkt(shape, rounding_precision=COORDINATE_DECIMALS)


def as_multipolygon(shape: BaseGeometry) -> MultiPolygon:
    """Give every footprint the same type, whether in one piece or in several."""
    return shape if isinstance(shape, MultiPolygon) else MultiPolygon([shape])


def list_sources(
    merimee_id: str, qid: str | None, osm_id: str | None
) -> list[dict[str, str]]:
    """Name the open databases a monument comes from, with their licences."""
    sources = [
        {
            "label": "Base Mérimée",
            "url": f"https://pop.culture.gouv.fr/notice/merimee/{merimee_id}",
            "licence": "Licence Ouverte 2.0",
        }
    ]
    if qid is not None:
        sources.append(
            {
                "label": "Wikidata",
                "url": f"https://www.wikidata.org/wiki/{qid}",
                "licence": "CC0",
            }
        )
    if osm_id is not None:
        sources.append(
            {
                "label": "OpenStreetMap",
                "url": f"https://www.openstreetmap.org/{osm_id}",
                "licence": "ODbL",
            }
        )
    return sources


def names(values: object) -> list[str]:
    """Read a list of names that a table may hold as an array, or not at all."""
    return [] if values is None else [str(value) for value in values]  # type: ignore[attr-defined]


def build_monuments(
    notices: Sequence[Record],
    entities: Sequence[Record],
    items: Sequence[Record],
    geometries: Sequence[Record],
    visibilities: Sequence[Record],
    data_version: int,
) -> list[dict[str, Any]]:
    """One row of the `monuments` table per protected notice that has a location."""
    item_of = {entity["merimee_id"]: entity["wikidata_qid"] for entity in entities}
    items_by_id = {item["qid"]: item for item in items}
    places = {row["merimee_id"]: row for row in geometries}
    seen = {row["merimee_id"]: row["visibility"] for row in visibilities}
    rows = []
    for notice in notices:
        merimee_id = notice["merimee_id"]
        if notice["protection"] is None:
            continue  # cancelled protections and cross-references are not monuments
        place = places.get(merimee_id)
        if place is None:
            logger.warning("%s has no location and is not loaded", merimee_id)
            continue
        qid = item_of.get(merimee_id)
        used = (place["footprint_objects"] or "").split(";")[0] or None
        kinds = names(notice["denominations"])
        architects = names(notice["architects"]) or names(
            items_by_id.get(qid, {}).get("architects")
        )
        rows.append(
            {
                "id": monument_id(merimee_id),
                "merimee_id": merimee_id,
                "wikidata_qid": qid,
                "osm_id": used,
                "name": notice["name"],
                "address": notice["address"],
                "arrondissement": notice["arrondissement"],
                "location": to_ewkt(Point(place["ref_lon"], place["ref_lat"])),
                "footprint": to_ewkt(as_multipolygon(place["geometry"])),
                "footprint_source": place["footprint_source"],
                "category": kinds[0] if kinds else None,
                "period_start": notice["construction_century"],
                "architects": architects,
                "protection": notice["protection"],
                "protection_desc": notice["protection_desc"],
                "visibility": seen.get(merimee_id, visibility.UNKNOWN),
                "sources": list_sources(merimee_id, qid, used),
                "data_version": data_version,
            }
        )
    return rows


def build_images(
    files: Sequence[Record], loaded: Sequence[Record]
) -> list[dict[str, Any]]:
    """One row of `reference_images` per photo selected for a loaded monument."""
    known = {row["merimee_id"] for row in loaded}
    return [
        {
            "id": image_id(file["merimee_id"], file["title"]),
            "monument_id": monument_id(file["merimee_id"]),
            "source_url": file["page_url"],
            "thumb_url": file["thumb_url"],
            "author": file["author"],
            "licence": file["licence"],
            "licence_url": file["licence_url"],
            "rank": file["rank"],
        }
        for file in files
        if file["selected"] and file["merimee_id"] in known
    ]


def load(
    connection: psycopg.Connection[Any],
    monuments: Sequence[Mapping[str, Any]],
    images: Sequence[Mapping[str, Any]],
) -> dict[str, int]:
    """Write the rows in the open transaction, and count what happened.

    Nothing is committed here: the caller decides. A monument that the pipeline
    no longer holds is counted but kept, since captures may point to it.
    """
    with connection.cursor() as cursor:
        cursor.executemany(
            UPSERT_MONUMENT,
            [{**row, "sources": Jsonb(row["sources"])} for row in monuments],
        )
        cursor.executemany(UPSERT_IMAGE, images)
        cursor.execute(DELETE_OTHER_IMAGES, ([row["id"] for row in images],))
        removed = cursor.rowcount
        cursor.execute(
            COUNT_OTHER_MONUMENTS, ([row["merimee_id"] for row in monuments],)
        )
        (others,) = cursor.fetchone() or (0,)
    return {
        "monuments_loaded": len(monuments),
        "monuments_no_longer_in_the_pipeline": int(others),
        "images_loaded": len(images),
        "images_removed": removed,
    }


def without_password(url: str) -> str:
    """Hide the password of a database address before it is logged."""
    parts = urlsplit(url)
    if parts.password is None:
        return url
    host = parts.hostname or ""
    port = f":{parts.port}" if parts.port else ""
    return urlunsplit(parts._replace(netloc=f"{parts.username}:***@{host}{port}"))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Load the monuments and their photos into Postgres."
    )
    parser.add_argument(
        "--data-version",
        type=int,
        default=DATA_VERSION,
        help="number recorded with every monument of this load",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    geometries = gpd.read_parquet(GEOMETRIES_PARQUET)
    monuments = build_monuments(
        to_records(pd.read_parquet(MERIMEE_PARQUET)),
        to_records(pd.read_parquet(ENTITIES_PARQUET)),
        to_records(pd.read_parquet(WIKIDATA_ITEMS_PARQUET)),
        to_records(pd.DataFrame(geometries)),
        to_records(pd.read_parquet(VISIBILITY_PARQUET)),
        args.data_version,
    )
    images = build_images(to_records(pd.read_parquet(COMMONS_FILES_PARQUET)), monuments)

    url = os.environ.get(DATABASE_URL_VARIABLE, LOCAL_DATABASE_URL)
    logger.info("Loading %s", without_password(url))
    with psycopg.connect(url) as connection:
        counts = load(connection, monuments, images)
    for label, count in counts.items():
        logger.info("  %-36s %6d", label, count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
