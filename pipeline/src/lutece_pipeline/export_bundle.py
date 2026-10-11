"""Step 11, app part - write the SQLite file that the app carries with it.

The app works offline: everything it shows about the monuments comes from one
file, built here and shipped among its assets. The file holds the monuments
with their reference point, their footprint, whether they can be captured and
from how far, and a few photos with their credits. It is small enough to be
versioned, so the app builds without running the pipeline.

Run with: uv run python -m lutece_pipeline.export_bundle
"""

import argparse
import csv
import hashlib
import json
import logging
import math
import sqlite3
from collections.abc import Mapping, Sequence
from itertools import pairwise
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
from lutece_pipeline.geo import LAMBERT_93, WGS84
from lutece_pipeline.paths import PIPELINE_ROOT, REVIEW_DIR
from lutece_pipeline.tables import to_records

logger = logging.getLogger(__name__)

# The photos of a monument page; image recognition will use embeddings instead.
PHOTOS_PER_MONUMENT = 3
# Coordinates are written with 6 decimals: about ten centimetres.
COORDINATE_DECIMALS = 6
COORDINATE_GRID = 10**-COORDINATE_DECIMALS
# Several addresses of one notice are separated this way; the first one is shown.
ADDRESS_SEPARATOR = ";"
# A monument can be captured from as far as twice its length, whatever the
# accuracy of the GPS: a large one is photographed from a distance.
REACH_PER_LENGTH = 2
MAX_REACH_M = 300

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
# Tall monuments seen from much further than their footprint tells, set by hand.
REACHES_CSV = REVIEW_DIR / "capture_reach.csv"

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
    min_lat real not null,
    max_lat real not null,
    min_lon real not null,
    max_lon real not null,
    footprint text not null,
    footprint_source text not null,
    category text,
    century integer,
    architects text not null,
    wikidata_qid text,
    protection text not null,
    visibility text not null,
    readiness text not null,
    capture_reach_m integer not null,
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
    "min_lat",
    "max_lat",
    "min_lon",
    "max_lon",
    "footprint",
    "footprint_source",
    "category",
    "century",
    "architects",
    "wikidata_qid",
    "protection",
    "visibility",
    "readiness",
    "capture_reach_m",
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


def read_reaches(path: Path) -> dict[str, int]:
    """Read the distances, in metres, set by hand for a few tall monuments."""
    if not path.exists():
        return {}
    reaches: dict[str, int] = {}
    with path.open(newline="", encoding="utf-8") as file:
        for line_number, row in enumerate(csv.DictReader(file), start=2):
            where = f"{path.name} line {line_number}"
            if row["merimee_id"] in reaches:
                raise ValueError(f"{where}: {row['merimee_id']} appears twice")
            if not row["reach_m"].isdecimal() or int(row["reach_m"]) == 0:
                raise ValueError(f"{where}: {row['reach_m']!r} is not a distance")
            reaches[row["merimee_id"]] = int(row["reach_m"])
    return reaches


def longest_sides(geometries: Sequence[Record]) -> dict[str, float]:
    """The length in metres of each footprint: the long side of its tightest box."""
    shapes = gpd.GeoSeries([row["geometry"] for row in geometries], crs=WGS84)
    boxes = shapes.to_crs(LAMBERT_93).minimum_rotated_rectangle()
    lengths = {}
    for row, box in zip(geometries, boxes, strict=True):
        corners = shapely.get_coordinates(box).tolist()
        sides = [math.dist(start, end) for start, end in pairwise(corners)]
        lengths[row["merimee_id"]] = max(sides, default=0.0)
    return lengths


def capture_reaches(
    geometries: Sequence[Record], by_hand: Mapping[str, int]
) -> dict[str, int]:
    """How far each monument may be captured from, in metres.

    The app adds what the accuracy of the GPS allows; the larger of the two
    distances applies.
    """
    reaches = {}
    for merimee_id, length in longest_sides(geometries).items():
        by_size = min(round(REACH_PER_LENGTH * length), MAX_REACH_M)
        reaches[merimee_id] = max(by_size, by_hand.get(merimee_id, 0))
    return reaches


def build_monuments(
    notices: Sequence[Record],
    entities: Sequence[Record],
    items: Sequence[Record],
    geometries: Sequence[Record],
    visibilities: Sequence[Record],
    photo_counts: Mapping[str, int],
    reaches: Mapping[str, int],
) -> list[dict[str, Any]]:
    """One row of the bundle per protected notice that has a location."""
    item_of = {entity["merimee_id"]: entity["wikidata_qid"] for entity in entities}
    items_by_id = {item["qid"]: item for item in items}
    places = {row["merimee_id"]: row for row in geometries}
    seen = {row["merimee_id"]: row for row in visibilities}
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
        view = seen.get(merimee_id, {})
        visible = view.get("visibility", visibility.UNKNOWN)
        west, south, east, north = shapely.bounds(place["geometry"]).tolist()
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
                # The box of the footprint lets the app find what is around.
                "min_lat": round(south, COORDINATE_DECIMALS),
                "max_lat": round(north, COORDINATE_DECIMALS),
                "min_lon": round(west, COORDINATE_DECIMALS),
                "max_lon": round(east, COORDINATE_DECIMALS),
                "footprint": to_geojson(place["geometry"]),
                "footprint_source": place["footprint_source"],
                "category": kinds[0] if kinds else None,
                "century": notice["construction_century"],
                "architects": json.dumps(architects, ensure_ascii=False),
                "wikidata_qid": qid,
                "protection": notice["protection"],
                "visibility": visible,
                "readiness": quality_report.readiness(
                    visible, view.get("reason"), place["footprint_source"]
                ),
                "capture_reach_m": reaches[merimee_id],
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
    geometries = to_records(pd.DataFrame(gpd.read_parquet(GEOMETRIES_PARQUET)))
    by_hand = read_reaches(REACHES_CSV)
    stale = sorted(set(by_hand) - {row["merimee_id"] for row in geometries})
    if stale:
        logger.warning("%d distances match no monument: %s", len(stale), stale)
    monuments = build_monuments(
        to_records(pd.read_parquet(MERIMEE_PARQUET)),
        to_records(pd.read_parquet(ENTITIES_PARQUET)),
        to_records(pd.read_parquet(WIKIDATA_ITEMS_PARQUET)),
        geometries,
        to_records(pd.read_parquet(VISIBILITY_PARQUET)),
        counts,
        capture_reaches(geometries, by_hand),
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
