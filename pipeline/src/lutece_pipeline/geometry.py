"""Step 5 - give each notice a reference point and a footprint.

The footprint is, in order of preference: the OSM footprints confirmed by
resolve_entities merged together; else the confirmed OSM lines (covered passages,
ramparts, canal) widened into a strip; else a circle around the reference point.

The reference point lies on the OSM geometry when there is one. Otherwise it is
the OSM node tagged with the Mérimée reference, else the Mérimée point, else the
Wikidata point. A point corrected by hand in review/geometry_overrides.csv always
comes first.

Run with: uv run python -m lutece_pipeline.geometry
"""

import argparse
import csv
import logging
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import shapely
from shapely import make_valid
from shapely.geometry.base import BaseGeometry
from shapely.ops import nearest_points, unary_union

from lutece_pipeline import (
    ingest_merimee,
    ingest_osm,
    ingest_wikidata,
    resolve_entities,
)
from lutece_pipeline.geo import LAMBERT_93, WGS84, project_points
from lutece_pipeline.paths import INTERIM_DIR, REVIEW_DIR
from lutece_pipeline.tables import to_records

logger = logging.getLogger(__name__)

# Radius of the circle that stands for a monument without any OSM geometry.
BUFFER_RADIUS_METERS = 10.0
# Half-width of the strip drawn around a monument mapped as a line.
LINE_HALF_WIDTH_METERS = 3.0
# Phone GPS is accurate to 5 m at best, so finer outlines only add weight.
SIMPLIFY_TOLERANCE_METERS = 1.0
# Beyond this gap between the Mérimée and Wikidata points, one of them is wrong.
POINT_DISAGREEMENT_METERS = 100.0
# Relations that describe the surroundings of a monument rather than the monument.
POINT_CHOICES = frozenset({"merimee", "wikidata", "manual"})
SURROUNDINGS_RELATION_TYPES = frozenset(
    {"associatedStreet", "street", "public_transport"}
)

MERIMEE_PARQUET = ingest_merimee.OUTPUT_PARQUET
WIKIDATA_ITEMS_PARQUET = ingest_wikidata.ITEMS_PARQUET
OSM_OBJECTS_PARQUET = ingest_osm.OBJECTS_PARQUET
ENTITIES_PARQUET = resolve_entities.ENTITIES_PARQUET
ENTITY_LINKS_PARQUET = resolve_entities.LINKS_PARQUET
OVERRIDES_CSV = REVIEW_DIR / "geometry_overrides.csv"
GEOMETRIES_PARQUET = INTERIM_DIR / "geometries.parquet"
REVIEW_CSV = INTERIM_DIR / "geometries_to_review.csv"

COLUMNS = [
    "merimee_id",
    "ref_lat",
    "ref_lon",
    "point_source",
    "footprint_source",
    "footprint_objects",
    "footprint_area_m2",
    "point_gap_m",
    "point_doubtful",
    "point_reviewed",
    "geometry",
]

REVIEW_COLUMNS = [
    "merimee_id",
    "name",
    "address",
    "arrondissement",
    "point_gap_m",
    "merimee_point_url",
    "wikidata_qid",
    "wikidata_point_url",
    "merimee_url",
]

type Record = Mapping[str, Any]


@dataclass(frozen=True)
class OsmObject:
    """A confirmed OSM object of a notice, with its geometry in Lambert-93."""

    entity_id: str
    geometry: BaseGeometry
    relation_type: str | None
    is_footprint: bool
    is_primary: bool
    via_ref_mhs: bool


@dataclass(frozen=True)
class Location:
    """Where a notice stands: all geometries are in Lambert-93."""

    point: BaseGeometry
    point_source: str
    footprint: BaseGeometry
    footprint_source: str
    objects: tuple[str, ...] = ()


@dataclass(frozen=True)
class Override:
    """A reviewer's choice of reference point for a notice."""

    use: str
    lat: float | None = None
    lon: float | None = None


def read_overrides(path: Path) -> dict[str, Override]:
    """Read the reviewed point choices, keyed by notice."""
    if not path.exists():
        return {}
    overrides: dict[str, Override] = {}
    with path.open(newline="", encoding="utf-8") as file:
        for line_number, row in enumerate(csv.DictReader(file), start=2):
            where = f"{path.name} line {line_number}"
            if row["use"] not in POINT_CHOICES:
                raise ValueError(f"{where}: unknown choice {row['use']!r}")
            if row["merimee_id"] in overrides:
                raise ValueError(f"{where}: {row['merimee_id']} is decided twice")
            if row["use"] != "manual":
                overrides[row["merimee_id"]] = Override(row["use"])
            elif row["lat"] and row["lon"]:
                overrides[row["merimee_id"]] = Override(
                    "manual", float(row["lat"]), float(row["lon"])
                )
            else:
                raise ValueError(f"{where}: a manual point needs lat and lon")
    return overrides


def confirmed_objects(
    links: Sequence[Record], objects: gpd.GeoDataFrame
) -> dict[str, list[OsmObject]]:
    """Group by notice the OSM objects whose link was confirmed, with their geometry."""
    projected = objects.to_crs(LAMBERT_93)
    rows = {f"{row.osm_type}/{row.osm_id}": row for row in projected.itertuples()}
    by_notice: dict[str, list[OsmObject]] = defaultdict(list)
    for link in links:
        if link["source"] != "osm" or link["status"] != "confirmed":
            continue
        row = rows[link["entity_id"]]
        if row.geometry is None or row.geometry.is_empty:
            continue
        relation_type = (
            row.relation_type if isinstance(row.relation_type, str) else None
        )
        by_notice[link["merimee_id"]].append(
            OsmObject(
                entity_id=link["entity_id"],
                geometry=row.geometry,
                relation_type=relation_type,
                is_footprint=bool(link["is_footprint"]),
                is_primary=bool(link["is_primary"]),
                via_ref_mhs=bool(link["via_ref_mhs"]),
            )
        )
    return by_notice


def simplify(geometry: BaseGeometry) -> BaseGeometry:
    """Lighten an outline, keeping the original when simplifying would break it."""
    simplified = geometry.simplify(SIMPLIFY_TOLERANCE_METERS, preserve_topology=True)
    if simplified.is_empty:
        return geometry
    return simplified if simplified.is_valid else make_valid(simplified)


def footprint_from_areas(objects: Sequence[OsmObject]) -> Location | None:
    """Merge the objects mapped as the monument itself, or chosen by a reviewer."""
    parts = [
        item
        for item in objects
        if (item.is_footprint or item.is_primary) and item.geometry.area > 0
    ]
    if not parts:
        return None
    footprint = simplify(unary_union([part.geometry for part in parts]))
    main = max(parts, key=lambda part: (part.is_primary, part.geometry.area))
    point = simplify(main.geometry).representative_point()
    if not footprint.contains(point):
        point = footprint.representative_point()
    objects_used = tuple(sorted(part.entity_id for part in parts))
    return Location(point, "osm_footprint", footprint, "osm_footprint", objects_used)


def footprint_from_lines(
    objects: Sequence[OsmObject], notice_point: BaseGeometry | None
) -> Location | None:
    """Widen the lines of a monument mapped as such into a strip."""
    parts = [
        item
        for item in objects
        if item.geometry.geom_type in {"LineString", "MultiLineString"}
        and item.relation_type not in SURROUNDINGS_RELATION_TYPES
    ]
    if not parts:
        return None
    lines = unary_union([part.geometry for part in parts])
    footprint = simplify(lines.buffer(LINE_HALF_WIDTH_METERS))
    # The spot of the line closest to the Mérimée point is where its address is.
    if notice_point is not None:
        point = nearest_points(lines, notice_point)[0]
    else:
        point = lines.representative_point()
    objects_used = tuple(sorted(part.entity_id for part in parts))
    return Location(point, "osm_line", footprint, "osm_line", objects_used)


def standalone_point(
    objects: Sequence[OsmObject],
    notice_point: BaseGeometry | None,
    wikidata_point: BaseGeometry | None,
) -> tuple[BaseGeometry, str] | None:
    """Pick the best point for a notice that has no OSM footprint or line."""
    nodes = [
        item
        for item in objects
        if item.geometry.geom_type == "Point" and item.via_ref_mhs
    ]
    if nodes:
        if notice_point is None:
            return nodes[0].geometry, "osm_node"
        nearest = min(nodes, key=lambda node: node.geometry.distance(notice_point))
        return nearest.geometry, "osm_node"
    if notice_point is not None:
        return notice_point, "merimee"
    if wikidata_point is not None:
        return wikidata_point, "wikidata"
    return None


def locate(
    objects: Sequence[OsmObject],
    notice_point: BaseGeometry | None,
    wikidata_point: BaseGeometry | None,
    reviewed: tuple[BaseGeometry, str] | None = None,
) -> Location | None:
    """Decide the reference point and the footprint of a notice.

    `reviewed` is the point chosen by a reviewer, with its source: it replaces
    the automatic reference point.
    """
    location = footprint_from_areas(objects) or footprint_from_lines(
        objects, notice_point
    )
    if location is not None:
        if reviewed is None:
            return location
        point, point_source = reviewed
        return Location(
            point,
            point_source,
            location.footprint,
            location.footprint_source,
            location.objects,
        )
    chosen = reviewed or standalone_point(objects, notice_point, wikidata_point)
    if chosen is None:
        return None
    point, point_source = chosen
    return Location(point, point_source, point.buffer(BUFFER_RADIUS_METERS), "buffer")


def build_geometries(
    notices: Sequence[Record],
    entities: Sequence[Record],
    links: Sequence[Record],
    items: Sequence[Record],
    objects: gpd.GeoDataFrame,
    overrides: Mapping[str, Override],
) -> gpd.GeoDataFrame:
    """Compute one row per notice: reference point, footprint and where they come from."""
    notice_points = project_points(notices, "merimee_id")
    item_points = project_points(items, "qid")
    manual_points = project_points(
        [
            {"merimee_id": merimee_id, "lat": override.lat, "lon": override.lon}
            for merimee_id, override in overrides.items()
            if override.use == "manual"
        ],
        "merimee_id",
    )
    main_item = {entity["merimee_id"]: entity["wikidata_qid"] for entity in entities}
    objects_by_notice = confirmed_objects(links, objects)

    rows = []
    for notice in notices:
        merimee_id = notice["merimee_id"]
        notice_point = notice_points.get(merimee_id)
        wikidata_point = item_points.get(main_item.get(merimee_id))
        reviewed = None
        if merimee_id in overrides:
            use = overrides[merimee_id].use
            candidates = {
                "merimee": notice_point,
                "wikidata": wikidata_point,
                "manual": manual_points.get(merimee_id),
            }
            if candidates[use] is None:
                raise ValueError(
                    f"{merimee_id}: the reviewed choice {use!r} has no point"
                )
            reviewed = (candidates[use], use)
        location = locate(
            objects_by_notice.get(merimee_id, []),
            notice_point,
            wikidata_point,
            reviewed,
        )
        if location is None:
            raise ValueError(f"{merimee_id} has no point in any source")
        gap = (
            float(notice_point.distance(wikidata_point))
            if notice_point is not None and wikidata_point is not None
            else None
        )
        # Without OSM to arbitrate, two distant points mean that one is wrong.
        doubtful = (
            reviewed is None
            and location.point_source in {"merimee", "wikidata"}
            and gap is not None
            and gap > POINT_DISAGREEMENT_METERS
        )
        rows.append(
            {
                "merimee_id": merimee_id,
                "ref_point": location.point,
                "point_source": location.point_source,
                "footprint_source": location.footprint_source,
                "footprint_objects": ";".join(location.objects) or None,
                "footprint_area_m2": float(location.footprint.area),
                "point_gap_m": gap,
                "point_doubtful": doubtful,
                "point_reviewed": reviewed is not None,
                "geometry": location.footprint,
            }
        )

    frame = gpd.GeoDataFrame(pd.DataFrame(rows), geometry="geometry", crs=LAMBERT_93)
    points = gpd.GeoSeries(frame["ref_point"], crs=LAMBERT_93).to_crs(WGS84)
    frame["ref_lat"] = points.y
    frame["ref_lon"] = points.x
    return frame.to_crs(WGS84)[COLUMNS]


def map_url(lat: float, lon: float) -> str:
    """Link to OpenStreetMap with a marker on the point."""
    return f"https://www.openstreetmap.org/?mlat={lat:.6f}&mlon={lon:.6f}#map=18/{lat:.6f}/{lon:.6f}"


def build_review(
    notices: Sequence[Record],
    entities: Sequence[Record],
    items: Sequence[Record],
    geometries: gpd.GeoDataFrame,
) -> pd.DataFrame:
    """List the monuments whose two candidate points disagree, for a human to choose.

    Notices without a protection level are left out: they are cross-references or
    cancelled protections, not monuments.
    """
    notices_by_id = {notice["merimee_id"]: notice for notice in notices}
    items_by_qid = {item["qid"]: item for item in items}
    main_item = {entity["merimee_id"]: entity["wikidata_qid"] for entity in entities}
    rows = []
    for row in geometries[geometries["point_doubtful"]].itertuples():
        notice = notices_by_id[row.merimee_id]
        if notice["protection"] is None:
            continue
        item = items_by_qid[main_item[row.merimee_id]]
        rows.append(
            {
                "merimee_id": row.merimee_id,
                "name": notice["name"],
                "address": notice["address"],
                "arrondissement": notice["arrondissement"],
                "point_gap_m": round(row.point_gap_m),
                "merimee_point_url": map_url(notice["lat"], notice["lon"]),
                "wikidata_qid": item["qid"],
                "wikidata_point_url": map_url(item["lat"], item["lon"]),
                "merimee_url": f"https://pop.culture.gouv.fr/notice/merimee/{row.merimee_id}",
            }
        )
    rows.sort(key=lambda item: -item["point_gap_m"])
    return pd.DataFrame(rows, columns=REVIEW_COLUMNS)


def summarize(geometries: gpd.GeoDataFrame) -> dict[str, int]:
    """Count the outcomes that the quality report will track."""
    counts = {"notices": len(geometries)}
    for column in ("footprint_source", "point_source"):
        for value, count in geometries[column].value_counts().items():
            counts[f"{column}={value}"] = int(count)
    counts["point_doubtful"] = int(geometries["point_doubtful"].sum())
    counts["point_reviewed"] = int(geometries["point_reviewed"].sum())
    counts["footprint_vertices"] = int(
        shapely.get_num_coordinates(geometries.geometry).sum()
    )
    return counts


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Give each notice a reference point and a footprint."
    )
    parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    notices = to_records(pd.read_parquet(MERIMEE_PARQUET))
    entities = to_records(pd.read_parquet(ENTITIES_PARQUET))
    links = to_records(pd.read_parquet(ENTITY_LINKS_PARQUET))
    items = to_records(pd.read_parquet(WIKIDATA_ITEMS_PARQUET))
    objects = gpd.read_parquet(OSM_OBJECTS_PARQUET)
    overrides = read_overrides(OVERRIDES_CSV)
    stale = sorted(set(overrides) - {notice["merimee_id"] for notice in notices})
    if stale:
        logger.warning("%d corrections match no notice: %s", len(stale), stale)

    geometries = build_geometries(notices, entities, links, items, objects, overrides)
    review = build_review(notices, entities, items, geometries)
    GEOMETRIES_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    geometries.to_parquet(GEOMETRIES_PARQUET, index=False)
    review.to_csv(REVIEW_CSV, index=False)

    logger.info("Wrote %d notices to %s", len(geometries), GEOMETRIES_PARQUET)
    logger.info("Wrote %d lines to review to %s", len(review), REVIEW_CSV)
    for label, count in summarize(geometries).items():
        logger.info("  %-32s %6d", label, count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
