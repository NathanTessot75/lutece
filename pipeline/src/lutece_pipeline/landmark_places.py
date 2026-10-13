"""Build the places that are not protected monuments and that a review has kept.

The landmarks step lists the well-known places of Paris that the Mérimée base
does not hold; `review/landmarks.csv` says which ones enter the app, under
which name, and from how far they may be captured. This step gives each of
them what a monument has: an outline and an arrondissement from OpenStreetMap,
a century and architects from Wikidata, and photos from Wikimedia Commons.

Run with: uv run python -m lutece_pipeline.landmark_places
"""

import argparse
import csv
import json
import logging
import re
import time
from collections.abc import Iterable, Mapping, Sequence
from contextlib import nullcontext
from dataclasses import dataclass
from itertools import groupby
from pathlib import Path
from typing import Any

import geopandas as gpd
import httpx
import pandas as pd
import pyarrow as pa
from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from lutece_pipeline import (
    geometry,
    ingest_commons,
    ingest_merimee,
    ingest_osm,
    ingest_wikidata,
    landmarks,
    selection,
)
from lutece_pipeline.geo import LAMBERT_93, WGS84
from lutece_pipeline.paths import INTERIM_DIR, RAW_DIR, REVIEW_DIR
from lutece_pipeline.tables import from_rows, to_records, write_parquet
from lutece_pipeline.web import Pause

logger = logging.getLogger(__name__)

KEEP, DROP = "keep", "drop"

REVIEW_CSV = REVIEW_DIR / "landmarks.csv"
ITEMS_SNAPSHOT = landmarks.ITEMS_SNAPSHOT
VIEWS_SNAPSHOT = landmarks.VIEWS_SNAPSHOT
OUTLINES_SNAPSHOT = RAW_DIR / "osm" / "landmarks.json"
COMMONS_FOLDER = ingest_commons.RAW_FOLDER
PLACES_PARQUET = INTERIM_DIR / "landmarks.parquet"
FILES_PARQUET = INTERIM_DIR / "landmark_files.parquet"

# The objects of Paris that OpenStreetMap ties to one of the given items, those
# that the review names, and the arrondissements.
OUTLINES_QUERY = (
    ingest_osm.QUERY_HEADER
    + ingest_osm.PARIS_AREA
    + '(nwr["wikidata"~"^(%s)$"](area.paris);%s'
    + 'rel["boundary"="administrative"]["admin_level"="9"](area.paris););out geom;'
)
OSM_OBJECT = re.compile(r"(node|way|relation)/(\d+)")
# Words that a file name may share with the name of a place without being
# about it.
COMMON_WORDS = frozenset({"paris", "des", "les", "the", "and"})
# What rules a file out whoever chose it.
UNUSABLE = frozenset({"format", "licence"})

PLACE_COLUMNS = [
    "qid",
    "title",
    "kind",
    "group",
    "arrondissement",
    "ref_lat",
    "ref_lon",
    "footprint_source",
    "century",
    "architects",
    "article",
    "views",
    "languages",
    "commons_category",
    "reach_m",
]
PLACES_SCHEMA = pa.schema(
    [
        ("qid", pa.string()),
        ("title", pa.string()),
        ("kind", pa.string()),
        ("group", pa.string()),
        ("arrondissement", pa.int16()),
        ("ref_lat", pa.float64()),
        ("ref_lon", pa.float64()),
        ("footprint_source", pa.string()),
        ("century", pa.int16()),
        ("architects", pa.list_(pa.string())),
        ("article", pa.string()),
        ("views", pa.int64()),
        ("languages", pa.int32()),
        ("commons_category", pa.string()),
        ("reach_m", pa.int32()),
    ]
)

type Record = Mapping[str, Any]
type Element = dict[str, Any]
type ObjectKey = tuple[str, int]
type District = tuple[int, BaseGeometry]


@dataclass(frozen=True)
class Decision:
    """What a review says of a place: whether to keep it, and how to show it."""

    qid: str
    title: str
    kind: str
    group: str
    reach_m: int
    # The objects of OpenStreetMap that draw the place, when the map does not
    # tie it to the item or only as a point: a café is the building it is in.
    objects: tuple[ObjectKey, ...] = ()
    # The files of Commons to show first, when the usual order starts badly.
    photos: tuple[str, ...] = ()


def read_objects(text: str, where: str) -> tuple[ObjectKey, ...]:
    """Read objects written as `way/123 relation/45`."""
    objects = []
    for name in text.split():
        found = OSM_OBJECT.fullmatch(name)
        if found is None:
            raise ValueError(f"{where}: {name!r} is not an object of OpenStreetMap")
        objects.append((found.group(1), int(found.group(2))))
    return tuple(objects)


def read_review(path: Path) -> list[Decision]:
    """Read the places that the review keeps, in the order of the file."""
    kept: list[Decision] = []
    seen: set[str] = set()
    with path.open(newline="", encoding="utf-8") as file:
        for line_number, row in enumerate(csv.DictReader(file), start=2):
            where = f"{path.name} line {line_number}"
            if row["decision"] not in (KEEP, DROP):
                raise ValueError(f"{where}: unknown decision {row['decision']!r}")
            if row["qid"] in seen:
                raise ValueError(f"{where}: {row['qid']} appears twice")
            seen.add(row["qid"])
            if not row["reach_m"].isdecimal():
                raise ValueError(f"{where}: {row['reach_m']!r} is not a distance")
            objects = read_objects(row["osm"], where)
            if row["decision"] == KEEP:
                if not row["title"] or not row["kind"]:
                    raise ValueError(f"{where}: a place kept needs a title and a kind")
                kept.append(
                    Decision(
                        row["qid"],
                        row["title"],
                        row["kind"],
                        row["group"],
                        int(row["reach_m"]),
                        objects,
                        read_photos(row["photos"]),
                    )
                )
    return kept


def read_photos(text: str) -> tuple[str, ...]:
    """Read files written as `First.jpg | Second.jpg`: no title holds a bar."""
    names = (name.strip().removeprefix("File:") for name in text.split("|"))
    return tuple(name for name in names if name)


def named_objects(decisions: Sequence[Decision]) -> dict[ObjectKey, str]:
    """Index the objects that the review names: for each, the place it draws."""
    return {key: decision.qid for decision in decisions for key in decision.objects}


def fetch_outlines(
    client: httpx.Client, decisions: Sequence[Decision], *, pause: Pause = time.sleep
) -> list[Element]:
    """Return, with their geometry, the objects of the places and the arrondissements."""
    tagged = "|".join(decision.qid for decision in decisions)
    named = sorted(named_objects(decisions))
    selectors = "".join(
        f"{kind}(id:{','.join(str(osm_id) for _, osm_id in group)});"
        for kind, group in groupby(named, key=lambda key: key[0])
    )
    return ingest_osm.run_overpass(
        client, OUTLINES_QUERY % (tagged, selectors), pause=pause
    )


def district_number(element: Mapping[str, Any]) -> int | None:
    """Return the number of the arrondissement that an object is, if it is one."""
    tags = element.get("tags", {})
    if tags.get("admin_level") != "9":
        return None
    return ingest_merimee.parse_arrondissement(tags.get("ref:INSEE"))


def to_metres(elements: Sequence[Element]) -> list[tuple[Element, BaseGeometry]]:
    """Give the objects that have a geometry, with it in metres."""
    shapes = [ingest_osm.element_geometry(element) for element in elements]
    kept = [
        (element, shape)
        for element, shape in zip(elements, shapes, strict=True)
        if shape is not None and not shape.is_empty
    ]
    if not kept:
        return []
    metric = gpd.GeoSeries([shape for _, shape in kept], crs=WGS84).to_crs(LAMBERT_93)
    return [(element, shape) for (element, _), shape in zip(kept, metric, strict=True)]


def read_districts(elements: Sequence[Element]) -> list[District]:
    """Keep the arrondissements among the objects: their number and their area."""
    districts: list[District] = []
    for element, shape in to_metres(elements):
        number = district_number(element)
        if number is not None:
            districts.append((number, shape))
    return sorted(districts, key=lambda district: district[0])


def district_of(point: BaseGeometry, districts: Sequence[District]) -> int | None:
    """Return the arrondissement a point lies in, None outside all of them."""
    return next((number for number, area in districts if area.covers(point)), None)


def group_outlines(
    elements: Sequence[Element], named: Mapping[ObjectKey, str] | None = None
) -> dict[str, list[BaseGeometry]]:
    """Gather, by item, the geometries of its objects, in metres.

    An object draws the items it is tagged with, and the place that the
    review names it for. An object named that the map no longer has is an
    error: the place would silently fall back to a circle.
    """
    named = named or {}
    objects = [e for e in elements if district_number(e) is None]
    outlines: dict[str, list[BaseGeometry]] = {}
    drawn: set[ObjectKey] = set()
    for element, shape in to_metres(objects):
        key = ingest_osm.element_key(element)
        drawn.add(key)
        tagged = element.get("tags", {}).get("wikidata", "").split(";")
        qids = {qid.strip() for qid in tagged if qid.strip()}
        if key in named:
            qids.add(named[key])
        for qid in sorted(qids):
            outlines.setdefault(qid, []).append(shape)
    missing = sorted(f"{kind}/{osm_id}" for kind, osm_id in set(named) - drawn)
    if missing:
        raise ValueError(f"Objects named by the review that are not found: {missing}")
    return outlines


def outline(
    shapes: Sequence[BaseGeometry], point: BaseGeometry
) -> tuple[BaseGeometry, BaseGeometry, str]:
    """Draw a place from its objects: its outline, a point in it, and the source.

    Areas make the outline; failing that, lines are widened into a strip;
    failing that, a circle stands around the point of the map, or around the
    one that Wikidata gives.
    """
    areas = [shape for shape in shapes if shape.area > 0]
    if areas:
        footprint = geometry.simplify(unary_union(areas))
        return footprint, footprint.representative_point(), "osm_footprint"
    lines = [shape for shape in shapes if shape.length > 0]
    if lines:
        strip = unary_union(lines).buffer(geometry.LINE_HALF_WIDTH_METERS)
        footprint = geometry.simplify(strip)
        return footprint, footprint.representative_point(), "osm_line"
    nodes = [shape for shape in shapes if shape.geom_type == "Point"]
    centre = min(nodes, key=point.distance) if nodes else point
    return centre.buffer(geometry.BUFFER_RADIUS_METERS), centre, "buffer"


def century_of(year: int | None) -> int | None:
    """1889 → 19, 1900 → 19, 1901 → 20."""
    return None if year is None or year <= 0 else (year - 1) // 100 + 1


def build_places(
    decisions: Sequence[Decision],
    items: Sequence[Record],
    views: Mapping[str, int],
    outlines: Mapping[str, Sequence[BaseGeometry]],
    districts: Sequence[District],
) -> gpd.GeoDataFrame:
    """One line per place kept, with its outline in WGS84."""
    items_by_id = {item["qid"]: item for item in items}
    unknown = [d.qid for d in decisions if d.qid not in items_by_id]
    if unknown:
        raise ValueError(f"Places kept that the landmarks step did not find: {unknown}")
    located = [items_by_id[decision.qid] for decision in decisions]
    lost = [item["qid"] for item in located if item["lat"] is None]
    if lost:
        raise ValueError(f"Places kept without a point in Paris: {lost}")
    points = gpd.GeoSeries(
        [Point(item["lon"], item["lat"]) for item in located], crs=WGS84
    ).to_crs(LAMBERT_93)

    rows, footprints, centres = [], [], []
    for decision, item, point in zip(decisions, located, points, strict=True):
        footprint, centre, source = outline(outlines.get(decision.qid, ()), point)
        footprints.append(footprint)
        centres.append(centre)
        rows.append(
            {
                "qid": decision.qid,
                "title": decision.title,
                "kind": decision.kind,
                "group": decision.group,
                "arrondissement": district_of(centre, districts),
                "footprint_source": source,
                "century": century_of(item["inception_year"]),
                "architects": list(item["architects"]),
                "article": item["frwiki_title"],
                "views": views.get(item["frwiki_title"], 0),
                "languages": item["sitelinks"],
                "commons_category": item["commons_category"],
                "reach_m": decision.reach_m,
            }
        )
    centres_wgs84 = gpd.GeoSeries(centres, crs=LAMBERT_93).to_crs(WGS84)
    frame = pd.DataFrame(rows)
    frame["ref_lat"] = [centre.y for centre in centres_wgs84]
    frame["ref_lon"] = [centre.x for centre in centres_wgs84]
    places = gpd.GeoDataFrame(
        frame[PLACE_COLUMNS], geometry=footprints, crs=LAMBERT_93
    ).to_crs(WGS84)
    return places.sort_values("qid", key=lambda qids: qids.str[1:].astype(int))


def commons_subjects(
    decisions: Sequence[Decision], items: Sequence[Record]
) -> list[ingest_commons.Monument]:
    """Describe the places the way the Commons step knows a monument."""
    items_by_id = {item["qid"]: item for item in items}
    subjects = []
    for decision in decisions:
        item = items_by_id[decision.qid]
        names = [decision.title, decision.kind, item["label_fr"]]
        names.append(item["commons_category"])
        kinds = ingest_commons.EXEMPT_KINDS
        subjects.append(
            ingest_commons.Monument(
                merimee_id=decision.qid,
                category=item["commons_category"],
                main_image=item["image_file"],
                names=tuple(dict.fromkeys(name for name in names if name)),
                exempt=frozenset(kinds[name] for name in names if name in kinds),
                entrance_only=False,
            )
        )
    return subjects


def name_words(name: str) -> frozenset[str]:
    """The words of a name that tell it apart, without accents or case."""
    words = re.findall(r"[a-z0-9]+", ingest_commons.fold(name))
    return frozenset(w for w in words if len(w) > 2 and w not in COMMON_WORDS)


def is_named_after(title: str, names: Iterable[str]) -> bool:
    """Tell whether the name of a file holds every word of a name of the place."""
    said = name_words(title)
    return any(words and words <= said for words in map(name_words, names))


def place_names(
    decisions: Sequence[Decision], items: Sequence[Record]
) -> dict[str, tuple[str, ...]]:
    """The names a place goes by: on the page, in Wikidata, in Wikipedia, on Commons."""
    items_by_id = {item["qid"]: item for item in items}
    names = {}
    for decision in decisions:
        item = items_by_id[decision.qid]
        known = [item["label_fr"], item["frwiki_title"], item["commons_category"]]
        names[decision.qid] = tuple(
            dict.fromkeys(name for name in [decision.title, *known] if name)
        )
    return names


def order_photos(
    photos: Sequence[dict[str, Any]], chosen: Sequence[str], names: Sequence[str]
) -> list[dict[str, Any]]:
    """Order the photos of a place: chosen, of Wikidata, named after it, others."""

    def level(row: Mapping[str, Any]) -> tuple[int, int]:
        if row["title"] in chosen:
            return 0, chosen.index(row["title"])
        if row["source"] == "main_image":
            return 1, 0
        return (2 if is_named_after(row["title"], names) else 3), 0

    return sorted(photos, key=lambda row: (level(row), row["rank"]))


def rank_for_places(
    files: pd.DataFrame,
    names: Mapping[str, Sequence[str]],
    first: Mapping[str, Sequence[str]],
) -> pd.DataFrame:
    """Order again the photos kept for each place.

    The category of a monument holds pictures of a building. That of a stadium,
    a concert hall or a tower also holds matches, guests and views from the
    top. So the photos that the review names come first, then the image of
    Wikidata, then the files named after the place, then the others; within
    each group the order of the Commons step stands.

    A photo that the review names was looked at: what the Commons step held
    against its subject, such as being a view from afar, no longer counts.
    Its format and its licence still do.
    """
    rows = to_records(files)
    by_place: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_place.setdefault(row["merimee_id"], []).append(row)
    for qid, photos in first.items():
        found = {row["title"]: row for row in by_place.get(qid, ())}
        for photo in photos:
            row = found.get(f"File:{photo}")
            if row is None:
                raise ValueError(f"{qid}: {photo!r}, named by the review, is not found")
            if row["reject_reason"] in UNUSABLE:
                raise ValueError(f"{qid}: {photo!r} cannot be shown, whoever names it")
            if row["rank"] is None:
                row["reject_reason"] = None
                row["rank"] = 0
    for qid, found in by_place.items():
        chosen = [f"File:{photo}" for photo in first.get(qid, ())]
        kept = [row for row in found if row["rank"] is not None]
        for position, row in enumerate(order_photos(kept, chosen, names[qid]), 1):
            row["rank"] = position
            row["selected"] = position <= ingest_commons.MAX_SELECTED
    return from_rows(rows, ingest_commons.FILES_SCHEMA)


def summarize(places: gpd.GeoDataFrame, files: pd.DataFrame) -> dict[str, int]:
    """Count the places by the source of their outline, and their photos."""
    counts = {"places": len(places)}
    for source, count in places["footprint_source"].value_counts().items():
        counts[f"outline={source}"] = int(count)
    counts["without_arrondissement"] = int(places["arrondissement"].isna().sum())
    selected = files[files["selected"]]
    counts["places_with_a_photo"] = int(selected["merimee_id"].nunique())
    counts["photos_selected"] = len(selected)
    return counts


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the places that are not monuments and that a review kept."
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="reuse the last saved answers instead of querying the services",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    decisions = read_review(REVIEW_CSV)
    qids = {decision.qid for decision in decisions}
    item_rows = json.loads(ITEMS_SNAPSHOT.read_text())["items"]
    items = [
        item
        for item in map(ingest_wikidata.build_item, item_rows)
        if item["qid"] in qids
    ]
    views = json.loads(VIEWS_SNAPSHOT.read_text())["views"]
    if args.offline:
        elements = json.loads(OUTLINES_SNAPSHOT.read_text())["elements"]
    else:
        with ingest_osm.make_client() as client:
            elements = fetch_outlines(client, decisions)
        selection.save_snapshot(OUTLINES_SNAPSHOT, "elements", elements)

    places = build_places(
        decisions,
        items,
        views,
        group_outlines(elements, named_objects(decisions)),
        read_districts(elements),
    )
    subjects = commons_subjects(decisions, items)
    with nullcontext() if args.offline else ingest_commons.make_client() as client:
        source = ingest_commons.Source.open(COMMONS_FOLDER, client)
        answers = ingest_commons.collect(source, subjects)
    first = {decision.qid: decision.photos for decision in decisions}
    files = rank_for_places(
        ingest_commons.build_files(subjects, answers),
        place_names(decisions, items),
        first,
    )

    PLACES_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    places.to_parquet(PLACES_PARQUET, index=False)
    write_parquet(files, ingest_commons.FILES_SCHEMA, FILES_PARQUET)

    logger.info("Wrote %d places to %s", len(places), PLACES_PARQUET)
    for label, count in summarize(places, files).items():
        logger.info("  %-28s %5d", label, count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
