"""Step 3 - fetch the OpenStreetMap objects linked to our Mérimée notices.

An OSM object is linked to a notice either directly, through its "ref:mhs" tag
(the Mérimée identifier), or through its "wikidata" tag when that item is one of
those matched by ingest_wikidata. The objects are read from the Overpass API with
their geometry. OSM data is published under the ODbL by OpenStreetMap contributors.

Run with: uv run python -m lutece_pipeline.ingest_osm
"""

import argparse
import json
import logging
import time
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from itertools import batched, groupby
from pathlib import Path
from typing import Any

import geopandas as gpd
import httpx
import pandas as pd
import pyarrow as pa
from shapely import make_valid
from shapely.geometry import LineString, MultiPoint, Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import polygonize, unary_union

from lutece_pipeline import ingest_merimee, ingest_wikidata, web
from lutece_pipeline.ingest_merimee import split_values
from lutece_pipeline.paths import INTERIM_DIR, RAW_DIR
from lutece_pipeline.tables import from_rows, write_parquet
from lutece_pipeline.web import Pause

logger = logging.getLogger(__name__)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
QUERY_HEADER = "[out:json][timeout:180];"
PARIS_AREA = 'area["ref:INSEE"="75056"]["boundary"="administrative"]->.paris;'
REF_MHS_QUERY = QUERY_HEADER + PARIS_AREA + 'nwr["ref:mhs"](area.paris);out geom;'
# Tags only: most of these objects are unrelated to our notices, so their geometry
# is requested afterwards, by identifier, for the few that are.
WIKIDATA_TAGGED_QUERY = (
    QUERY_HEADER + PARIS_AREA + 'nwr["wikidata"](area.paris);out tags;'
)
GEOMETRY_BATCH_SIZE = 1500
# Pause between two queries, to stay a polite client of the public endpoint.
BATCH_PAUSE_SECONDS = 5.0
# The public Overpass server throttles and times out for minutes at a time when
# busy: with five attempts, this waits 15, 30, 60 then 120 seconds.
RETRY_BASE_DELAY_SECONDS = 15.0

MERIMEE_PARQUET = ingest_merimee.OUTPUT_PARQUET
WIKIDATA_LINKS_PARQUET = ingest_wikidata.LINKS_PARQUET
RAW_SNAPSHOT = RAW_DIR / "osm" / "snapshot.json"
OBJECTS_PARQUET = INTERIM_DIR / "osm_objects.parquet"
LINKS_PARQUET = INTERIM_DIR / "osm_merimee_links.parquet"

OBJECT_COLUMNS = [
    "osm_type",
    "osm_id",
    "relation_type",
    "name",
    "ref_mhs",
    "wikidata",
    "building",
    "tags",
]
# Relations whose member ways are the rings of a single area.
AREA_RELATION_TYPES = {"multipolygon", "boundary"}
# Relations mapped as the monument itself; the other types (street with its
# houses, transport hub) only describe its surroundings.
FOOTPRINT_RELATION_TYPES = {"multipolygon", "site"}

LINKS_SCHEMA = pa.schema(
    [
        ("merimee_id", pa.string()),
        ("osm_type", pa.string()),
        ("osm_id", pa.int64()),
        ("via_ref_mhs", pa.bool_()),
        ("via_wikidata", pa.bool_()),
    ]
)

type Element = dict[str, Any]


def make_client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    """Create the HTTP client used to talk to the Overpass API."""
    return web.make_client(timeout=300.0, transport=transport)


def run_overpass(
    client: httpx.Client, query: str, *, pause: Pause = time.sleep
) -> list[Element]:
    """Run an Overpass query and return its elements."""
    response = web.post_form(
        client,
        OVERPASS_URL,
        {"data": query},
        pause=pause,
        base_delay=RETRY_BASE_DELAY_SECONDS,
    )
    payload = response.json()
    # Overpass reports runtime failures, such as a timeout, inside a successful answer.
    if "remark" in payload:
        raise RuntimeError(f"Overpass query failed: {payload['remark']}")
    return payload["elements"]


def element_key(element: Mapping[str, Any]) -> tuple[str, int]:
    """Identify an element: identifiers are only unique within a type."""
    return element["type"], element["id"]


def geometry_query(keys: Sequence[tuple[str, int]]) -> str:
    """Build the query returning the given elements with their geometry."""
    selectors = [
        f"{kind}(id:{','.join(str(osm_id) for _, osm_id in group)});"
        for kind, group in groupby(sorted(keys), key=lambda key: key[0])
    ]
    return f"{QUERY_HEADER}({''.join(selectors)});out geom;"


def fetch_elements(
    client: httpx.Client, qids: set[str], *, pause: Pause = time.sleep
) -> list[Element]:
    """Return, with their geometry, the Paris objects tagged with a Mérimée
    reference or with one of the given Wikidata items."""
    elements = run_overpass(client, REF_MHS_QUERY, pause=pause)
    known = {element_key(element) for element in elements}

    pause(BATCH_PAUSE_SECONDS)
    tagged = run_overpass(client, WIKIDATA_TAGGED_QUERY, pause=pause)
    wanted = sorted(
        element_key(element)
        for element in tagged
        if element_key(element) not in known
        and qids.intersection(split_values(element["tags"].get("wikidata")))
    )
    for batch in batched(wanted, GEOMETRY_BATCH_SIZE):
        pause(BATCH_PAUSE_SECONDS)
        elements += run_overpass(client, geometry_query(batch), pause=pause)
    return elements


def is_linear_feature(tags: Mapping[str, str]) -> bool:
    """Tell whether a closed way is a loop (road, wall) rather than an area."""
    return tags.get("area") != "yes" and ("highway" in tags or "barrier" in tags)


def to_line(points: Sequence[Mapping[str, float] | None]) -> LineString | None:
    """Build a line from Overpass points, or None when fewer than two are known."""
    coordinates = [(point["lon"], point["lat"]) for point in points if point]
    return LineString(coordinates) if len(coordinates) >= 2 else None


def way_geometry(element: Mapping[str, Any]) -> BaseGeometry | None:
    """Return a polygon for a closed way describing an area, a line otherwise."""
    line = to_line(element.get("geometry", []))
    if line is None:
        return None
    is_closed = line.is_closed and len(line.coords) >= 4
    if is_closed and not is_linear_feature(element.get("tags", {})):
        return Polygon(line.coords)
    return line


def merge_areas(polygons: Iterable[BaseGeometry]) -> BaseGeometry:
    """Merge polygons into one area, repairing the invalid ones first."""
    return unary_union([make_valid(polygon) for polygon in polygons])


def relation_geometry(element: Mapping[str, Any]) -> BaseGeometry | None:
    """Return the area covered by a relation, or its lines or nodes failing that.

    A multipolygon lists the rings of one area: its member ways are stitched into
    outer rings and holes whatever their order. Any other relation (site, street
    with its houses, transport hub) groups separate features, so each closed
    member way counts as an area of its own.
    """
    outers: list[LineString] = []
    inners: list[LineString] = []
    points: list[Point] = []
    for member in element.get("members", []):
        if member["type"] == "way":
            line = to_line(member.get("geometry", []))
            if line is not None:
                (inners if member.get("role") == "inner" else outers).append(line)
        elif member["type"] == "node" and "lat" in member:
            points.append(Point(member["lon"], member["lat"]))

    if element.get("tags", {}).get("type") in AREA_RELATION_TYPES:
        holes = merge_areas(polygonize(inners))
        area = merge_areas(polygonize(outers)).difference(holes)
    else:
        lines = outers + inners
        closed = [line for line in lines if line.is_closed and len(line.coords) >= 4]
        area = merge_areas(Polygon(line.coords) for line in closed)
    if not area.is_empty:
        return area
    if outers:
        return unary_union(outers)
    return MultiPoint(points) if points else None


def element_geometry(element: Mapping[str, Any]) -> BaseGeometry | None:
    """Return the WGS84 geometry of an Overpass element, repaired when invalid."""
    match element["type"]:
        case "node":
            geometry: BaseGeometry | None = Point(element["lon"], element["lat"])
        case "way":
            geometry = way_geometry(element)
        case "relation":
            geometry = relation_geometry(element)
        case _:
            geometry = None
    if geometry is not None and not geometry.is_valid:
        geometry = make_valid(geometry)
    return geometry


def notices_by_item(wikidata_links: pd.DataFrame) -> dict[str, set[str]]:
    """Index the Wikidata links: for each item, the notices it stands for."""
    notices: dict[str, set[str]] = {}
    pairs = zip(wikidata_links["qid"], wikidata_links["merimee_id"], strict=True)
    for qid, merimee_id in pairs:
        notices.setdefault(qid, set()).add(merimee_id)
    return notices


def build_links(
    elements: Sequence[Mapping[str, Any]],
    merimee_ids: set[str],
    notices_by_qid: Mapping[str, set[str]],
) -> pd.DataFrame:
    """Pair each element with the notices it designates, recording by which tag."""
    rows = []
    for element in elements:
        tags = element.get("tags", {})
        by_ref = merimee_ids.intersection(split_values(tags.get("ref:mhs")))
        by_wikidata: set[str] = set()
        for qid in split_values(tags.get("wikidata")):
            by_wikidata |= notices_by_qid.get(qid, set())
        rows += [
            {
                "merimee_id": merimee_id,
                "osm_type": element["type"],
                "osm_id": element["id"],
                "via_ref_mhs": merimee_id in by_ref,
                "via_wikidata": merimee_id in by_wikidata,
            }
            for merimee_id in by_ref | by_wikidata
        ]
    rows.sort(key=lambda row: (row["merimee_id"], row["osm_type"], row["osm_id"]))
    return from_rows(rows, LINKS_SCHEMA)


def build_objects(elements: Sequence[Mapping[str, Any]]) -> gpd.GeoDataFrame:
    """Turn the elements into one row per OSM object, with its geometry."""
    rows = []
    for element in sorted(elements, key=element_key):
        tags = element.get("tags", {})
        rows.append(
            {
                "osm_type": element["type"],
                "osm_id": element["id"],
                "relation_type": tags.get("type")
                if element["type"] == "relation"
                else None,
                "name": tags.get("name"),
                "ref_mhs": tags.get("ref:mhs"),
                "wikidata": tags.get("wikidata"),
                "building": tags.get("building"),
                "tags": json.dumps(tags, ensure_ascii=False, sort_keys=True),
                "geometry": element_geometry(element),
            }
        )
    frame = pd.DataFrame(rows, columns=[*OBJECT_COLUMNS, "geometry"])
    objects = gpd.GeoDataFrame(frame, geometry="geometry", crs="EPSG:4326")
    duplicated = objects.loc[
        objects.duplicated(["osm_type", "osm_id"]), "osm_id"
    ].tolist()
    if duplicated:
        raise ValueError(f"Several rows for the same OSM object: {duplicated}")
    return objects


def save_snapshot(path: Path, elements: Sequence[Element]) -> None:
    """Keep the raw elements, so that the step can be replayed offline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    snapshot = {
        "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "elements": elements,
    }
    path.write_text(json.dumps(snapshot, ensure_ascii=False) + "\n")


def summarize(
    merimee_ids: set[str], links: pd.DataFrame, objects: gpd.GeoDataFrame
) -> dict[str, int]:
    """Count the matches and the coverage gaps that the quality report will track."""
    # Areas are measured in Lambert-93, the metric projection used in France.
    areas = objects.geometry.to_crs("EPSG:2154").area
    is_footprint = (areas > 0) & (
        (objects["osm_type"] == "way")
        | objects["relation_type"].isin(FOOTPRINT_RELATION_TYPES)
    )
    footprints = objects.loc[is_footprint, ["osm_type", "osm_id"]]
    footprint_links = links.merge(footprints, on=["osm_type", "osm_id"])
    by_ref = set(links.loc[links["via_ref_mhs"], "merimee_id"])
    by_wikidata = set(links.loc[links["via_wikidata"], "merimee_id"])
    return {
        "notices": len(merimee_ids),
        "notices_without_object": len(merimee_ids - set(links["merimee_id"])),
        "notices_via_ref_mhs": len(by_ref),
        "notices_via_wikidata": len(by_wikidata),
        "notices_via_both": len(by_ref & by_wikidata),
        "notices_with_footprint": footprint_links["merimee_id"].nunique(),
        "objects": len(objects),
        "nodes": int((objects["osm_type"] == "node").sum()),
        "ways": int((objects["osm_type"] == "way").sum()),
        "relations": int((objects["osm_type"] == "relation").sum()),
        "objects_without_geometry": int(objects.geometry.isna().sum()),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch the OpenStreetMap objects linked to our Mérimée notices."
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="reuse the last saved Overpass answers instead of querying the service",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    merimee_ids = set(
        pd.read_parquet(MERIMEE_PARQUET, columns=["merimee_id"])["merimee_id"]
    )
    wikidata_links = pd.read_parquet(WIKIDATA_LINKS_PARQUET)
    notices_by_qid = notices_by_item(wikidata_links)

    if args.offline:
        elements = json.loads(RAW_SNAPSHOT.read_text())["elements"]
    else:
        with make_client() as client:
            elements = fetch_elements(client, set(notices_by_qid))
        save_snapshot(RAW_SNAPSHOT, elements)

    links = build_links(elements, merimee_ids, notices_by_qid)
    linked = set(zip(links["osm_type"], links["osm_id"], strict=True))
    unlinked = [element for element in elements if element_key(element) not in linked]
    if unlinked:
        references = sorted(
            {element["tags"].get("ref:mhs", "?") for element in unlinked}
        )
        logger.info(
            "Ignored %d objects whose reference is not ours: %s",
            len(unlinked),
            references,
        )
    objects = build_objects(
        [element for element in elements if element_key(element) in linked]
    )

    write_parquet(links, LINKS_SCHEMA, LINKS_PARQUET)
    OBJECTS_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    objects.to_parquet(OBJECTS_PARQUET, index=False)

    logger.info("Wrote %d links to %s", len(links), LINKS_PARQUET)
    logger.info("Wrote %d objects to %s", len(objects), OBJECTS_PARQUET)
    for label, count in summarize(merimee_ids, links, objects).items():
        logger.info("  %-26s %5d", label, count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
