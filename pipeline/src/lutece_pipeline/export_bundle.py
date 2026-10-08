"""Step 11, app part - write the SQLite file that the app carries with it.

The app works offline: everything it shows about the monuments comes from one
file, built here and shipped among its assets. The file holds the monuments
with their reference point, their footprint and whether they can be captured,
and a few photos with their credits. It is small enough to be versioned, so
the app builds without running the pipeline.

Run with: uv run python -m lutece_pipeline.export_bundle
"""

import argparse
import hashlib
import json
import logging
import sqlite3
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import shapely

from lutece_pipeline import (
    geometry,
    ingest_commons,
    ingest_merimee,
    ingest_wikidata,
    load_postgres,
    quality_report,
    resolve_entities,
    visibility,
)
from lutece_pipeline.paths import PIPELINE_ROOT
from lutece_pipeline.tables import to_records

logger = logging.getLogger(__name__)

# The photos of a monument page; image recognition will use embeddings instead.
PHOTOS_PER_MONUMENT = 3
# Coordinates are written with 6 decimals: about ten centimetres.
COORDINATE_GRID = 1e-6
# Several addresses of one notice are separated this way; the first one is shown.
ADDRESS_SEPARATOR = ";"

MERIMEE_PARQUET = ingest_merimee.OUTPUT_PARQUET
ENTITIES_PARQUET = resolve_entities.ENTITIES_PARQUET
WIKIDATA_ITEMS_PARQUET = ingest_wikidata.ITEMS_PARQUET
GEOMETRIES_PARQUET = geometry.GEOMETRIES_PARQUET
VISIBILITY_PARQUET = visibility.VISIBILITY_PARQUET
COMMONS_FILES_PARQUET = ingest_commons.FILES_PARQUET
ASSETS_FOLDER = PIPELINE_ROOT.parent / "apps" / "mobile" / "assets" / "data"
BUNDLE_DB = ASSETS_FOLDER / "lutece.db"
# What the app must know before it opens the file: which version it carries.
BUNDLE_JSON = ASSETS_FOLDER / "bundle.json"

SCHEMA = """
create table meta (
    key text primary key,
    value text not null
) strict;

create table monuments (
    id text primary key,
    merimee_id text not null unique,
    title text not null,
    name text not null,
    address text,
    arrondissement integer,
    lat real not null,
    lon real not null,
    footprint text not null,
    footprint_source text not null,
    category text,
    century integer,
    architects text not null,
    wikidata_qid text,
    protection text not null,
    visibility text not null,
    readiness text not null,
    photo_count integer not null
) strict;

create index monuments_arrondissement on monuments (arrondissement);

create table photos (
    monument_id text not null references monuments (id),
    rank integer not null,
    thumb_url text not null,
    page_url text not null,
    author text,
    licence text,
    licence_url text,
    primary key (monument_id, rank)
) strict;
"""
MONUMENT_COLUMNS = [
    "id",
    "merimee_id",
    "title",
    "name",
    "address",
    "arrondissement",
    "lat",
    "lon",
    "footprint",
    "footprint_source",
    "category",
    "century",
    "architects",
    "wikidata_qid",
    "protection",
    "visibility",
    "readiness",
    "photo_count",
]
PHOTO_COLUMNS = [
    "monument_id",
    "rank",
    "thumb_url",
    "page_url",
    "author",
    "licence",
    "licence_url",
]

type Record = Mapping[str, Any]


def display_title(
    name: str, address: str | None, denominations: Sequence[str] | None
) -> str:
    """Name a monument for the app: its own name, or its kind and its address.

    Hundreds of notices are only called "Immeuble" or "Maison": the address is
    what tells them apart.
    """
    if address is None or quality_report.has_own_name(name, denominations):
        return name
    return f"{name}, {first_address(address)}"


def first_address(address: str) -> str:
    """Keep the first of the addresses that a notice lists."""
    return address.split(ADDRESS_SEPARATOR)[0].strip()


def tell_apart(rows: Sequence[dict[str, Any]]) -> None:
    """Add its address to the title of a monument that shares it with another.

    Thirty buildings are all called "Immeuble en bordure du Palais-Royal".
    """
    shared = pd.Series([row["title"] for row in rows]).value_counts()
    for row in rows:
        address = row["address"]
        if shared[row["title"]] > 1 and address is not None:
            street = first_address(address)
            if street not in row["title"]:
                row["title"] = f"{row['title']}, {street}"


def to_geojson(shape: shapely.Geometry) -> str:
    """Write a footprint as a GeoJSON multipolygon, in WGS84."""
    whole = load_postgres.as_multipolygon(shape)
    return shapely.to_geojson(shapely.set_precision(whole, COORDINATE_GRID))


def build_monuments(
    notices: Sequence[Record],
    entities: Sequence[Record],
    items: Sequence[Record],
    geometries: Sequence[Record],
    visibilities: Sequence[Record],
    photo_counts: Mapping[str, int],
) -> list[dict[str, Any]]:
    """One row of the bundle per protected notice that has a location."""
    item_of = {entity["merimee_id"]: entity["wikidata_qid"] for entity in entities}
    items_by_id = {item["qid"]: item for item in items}
    places = {row["merimee_id"]: row for row in geometries}
    seen = {row["merimee_id"]: row["visibility"] for row in visibilities}
    rows = []
    for notice in sorted(notices, key=lambda notice: notice["merimee_id"]):
        merimee_id = notice["merimee_id"]
        place = places.get(merimee_id)
        if notice["protection"] is None or place is None:
            continue
        qid = item_of.get(merimee_id)
        kinds = load_postgres.names(notice["denominations"])
        architects = load_postgres.names(notice["architects"]) or load_postgres.names(
            items_by_id.get(qid, {}).get("architects")
        )
        visible = seen.get(merimee_id, visibility.UNKNOWN)
        rows.append(
            {
                "id": str(load_postgres.monument_id(merimee_id)),
                "merimee_id": merimee_id,
                "title": display_title(notice["name"], notice["address"], kinds),
                "name": notice["name"],
                "address": notice["address"],
                "arrondissement": notice["arrondissement"],
                "lat": place["ref_lat"],
                "lon": place["ref_lon"],
                "footprint": to_geojson(place["geometry"]),
                "footprint_source": place["footprint_source"],
                "category": kinds[0] if kinds else None,
                "century": notice["construction_century"],
                "architects": json.dumps(architects, ensure_ascii=False),
                "wikidata_qid": qid,
                "protection": notice["protection"],
                "visibility": visible,
                "readiness": quality_report.readiness(
                    visible, place["footprint_source"]
                ),
                "photo_count": photo_counts.get(merimee_id, 0),
            }
        )
    tell_apart(rows)
    return rows


def build_photos(
    files: Sequence[Record], monuments: Sequence[Record]
) -> list[dict[str, Any]]:
    """The first photos selected for each monument of the bundle, with credits."""
    ids = {row["merimee_id"]: row["id"] for row in monuments}
    rows = [
        {
            "monument_id": ids[file["merimee_id"]],
            "rank": file["rank"],
            "thumb_url": file["thumb_url"],
            "page_url": file["page_url"],
            "author": file["author"],
            "licence": file["licence"],
            "licence_url": file["licence_url"],
        }
        for file in files
        if file["selected"]
        and file["rank"] <= PHOTOS_PER_MONUMENT
        and file["merimee_id"] in ids
    ]
    return sorted(rows, key=lambda row: (row["monument_id"], row["rank"]))


def content_version(monuments: Sequence[Record], photos: Sequence[Record]) -> str:
    """A short fingerprint of the content: it changes when any value does.

    The app names its copy of the file after it, so a new bundle replaces the
    old one without any number to remember to increase.
    """
    content = json.dumps(
        [SCHEMA, list(monuments), list(photos)], ensure_ascii=False, sort_keys=True
    )
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]


def write_bundle(
    path: Path, monuments: Sequence[Record], photos: Sequence[Record], version: str
) -> None:
    """Write the SQLite file from scratch."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    meta = {
        "version": version,
        "monuments": str(len(monuments)),
        "photos": str(len(photos)),
    }
    database = sqlite3.connect(path)
    try:
        database.executescript(SCHEMA)
        database.executemany("insert into meta values (?, ?)", sorted(meta.items()))
        database.executemany(
            f"insert into monuments values ({', '.join('?' * len(MONUMENT_COLUMNS))})",
            [[row[column] for column in MONUMENT_COLUMNS] for row in monuments],
        )
        database.executemany(
            f"insert into photos values ({', '.join('?' * len(PHOTO_COLUMNS))})",
            [[row[column] for column in PHOTO_COLUMNS] for row in photos],
        )
        database.commit()
        database.execute("vacuum")
    finally:
        database.close()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Write the SQLite file that the app carries with it."
    )
    parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    files = to_records(pd.read_parquet(COMMONS_FILES_PARQUET))
    counts: dict[str, int] = {}
    for file in files:
        if file["selected"]:
            counts[file["merimee_id"]] = counts.get(file["merimee_id"], 0) + 1
    monuments = build_monuments(
        to_records(pd.read_parquet(MERIMEE_PARQUET)),
        to_records(pd.read_parquet(ENTITIES_PARQUET)),
        to_records(pd.read_parquet(WIKIDATA_ITEMS_PARQUET)),
        to_records(pd.DataFrame(gpd.read_parquet(GEOMETRIES_PARQUET))),
        to_records(pd.read_parquet(VISIBILITY_PARQUET)),
        counts,
    )
    photos = build_photos(files, monuments)
    version = content_version(monuments, photos)
    write_bundle(BUNDLE_DB, monuments, photos, version)
    summary = {"version": version, "monuments": len(monuments), "photos": len(photos)}
    BUNDLE_JSON.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    logger.info("Wrote %s (%d bytes)", BUNDLE_DB, BUNDLE_DB.stat().st_size)
    for label, value in summary.items():
        logger.info("  %-10s %s", label, value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
