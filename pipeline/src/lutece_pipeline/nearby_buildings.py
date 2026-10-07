"""Step 5, first part - find the building of the monuments that OSM does not link.

Many protected buildings carry no OSM tag that ties them to their notice. For
those, the building standing at the reference point is most likely the monument:
this step fetches the OSM buildings around each such point and keeps the one
that contains it, else the closest one. The geometry step then uses that
building instead of a circle.

The rule is also applied to a sample of notices whose footprint is already known,
to measure how often it picks the right building.

Run with: uv run python -m lutece_pipeline.nearby_buildings
"""

import argparse
import json
import logging
import random
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import batched
from pathlib import Path
from typing import Any

import geopandas as gpd
import httpx
import pandas as pd
from shapely.geometry.base import BaseGeometry

from lutece_pipeline import geometry, ingest_osm
from lutece_pipeline.geo import LAMBERT_93, WGS84, project_points
from lutece_pipeline.ingest_osm import element_geometry, element_key
from lutece_pipeline.paths import INTERIM_DIR, RAW_DIR
from lutece_pipeline.tables import to_records
from lutece_pipeline.web import Pause

logger = logging.getLogger(__name__)

SEARCH_RADIUS_METERS = 30
# A point outside every building is paired with the closest one within this reach.
NEAREST_MAX_METERS = 15.0
# Small batches: the public server times out on heavier queries when it is busy.
POINT_BATCH_SIZE = 30
EVALUATION_SAMPLE_SIZE = 300
EVALUATION_SEED = 0
# A chosen building is the right one when at least half of it lies in the known footprint.
OVERLAP_SHARE = 0.5
# Main denominations of the notices that are not a single building: small objects,
# linear works, open spaces, groups of buildings and underground works.
NOT_A_BUILDING = frozenset(
    {
        "aqueduc",
        "arc de triomphe",
        "canal",
        "carrière",
        "carrière souterraine",
        "cimetière",
        "cité",
        "cité ouvrière",
        "cité universitaire",
        "fabrique de jardin",
        "fontaine",
        "fortification d'agglomération",
        "galerie marchande",
        "grand ensemble",
        "ilôt",
        "jardin",
        "jardin botanique",
        "jardin fleuriste",
        "jardin public",
        "latrine",
        "lotissement concerté",
        "mire",
        "monument",
        "monument funéraire",
        "parc",
        "passage couvert",
        "passerelle",
        "place",
        "pont",
        "porte de ville",
        "regard",
        "secteur urbain concerté",
        "square",
        "station de métro",
        "tombeau",
        "transformateur (abri)",
        "établissement des eaux",
    }
)

RAW_SNAPSHOT = RAW_DIR / "osm" / "nearby_buildings.json"
PROGRESS_FILE = RAW_DIR / "osm" / "nearby_buildings.partial.json"
NEARBY_PARQUET = geometry.NEARBY_PARQUET
EVALUATION_CSV = INTERIM_DIR / "nearby_buildings_evaluation.csv"

NEARBY_COLUMNS = [
    "merimee_id",
    "entity_id",
    "match",
    "distance_m",
    "building",
    "geometry",
]
EVALUATION_COLUMNS = [
    "merimee_id",
    "outcome",
    "match",
    "distance_m",
    "entity_id",
    "overlap_share",
]

type Element = dict[str, Any]
type LatLon = tuple[float, float]


@dataclass(frozen=True)
class Match:
    """The building chosen for a point, with its geometry in Lambert-93."""

    entity_id: str
    geometry: BaseGeometry
    distance_m: float
    kind: str
    building: str | None


def is_building(denominations: Sequence[str] | None) -> bool:
    """Tell from its main denomination whether a notice describes a single building."""
    if denominations is None or len(denominations) == 0:
        return False
    return denominations[0] not in NOT_A_BUILDING


def around_query(points: Sequence[LatLon]) -> str:
    """Build the query returning the buildings near any of the (lat, lon) points."""
    filters = "".join(
        f'wr["building"](around:{SEARCH_RADIUS_METERS},{lat:.6f},{lon:.6f});'
        for lat, lon in points
    )
    return f"{ingest_osm.QUERY_HEADER}({filters});out geom;"


def fetch_buildings(
    client: httpx.Client,
    points: Sequence[LatLon],
    *,
    pause: Pause = time.sleep,
    progress: Path | None = None,
) -> list[Element]:
    """Return the distinct OSM buildings found around the points, with their geometry.

    The public server often gives up for minutes at a time. Every answered batch
    is therefore saved to `progress`: a run that failed resumes where it stopped
    instead of asking again for what it already has.
    """
    answers: dict[str, list[Element]] = {}
    if progress is not None and progress.exists():
        answers = json.loads(progress.read_text())
    queries = [
        around_query(batch) for batch in batched(sorted(set(points)), POINT_BATCH_SIZE)
    ]
    asked = False
    for query in queries:
        if query in answers:
            continue
        if asked:
            pause(ingest_osm.BATCH_PAUSE_SECONDS)
        answers[query] = ingest_osm.run_overpass(client, query, pause=pause)
        asked = True
        if progress is not None:
            progress.parent.mkdir(parents=True, exist_ok=True)
            progress.write_text(json.dumps(answers, ensure_ascii=False))
    elements = {
        element_key(element): element for query in queries for element in answers[query]
    }
    return [elements[key] for key in sorted(elements)]


def build_buildings(elements: Sequence[Mapping[str, Any]]) -> gpd.GeoDataFrame:
    """Keep the elements that cover an area, as geometries in Lambert-93."""
    rows = []
    for element in sorted(elements, key=element_key):
        shape = element_geometry(element)
        if shape is None or shape.area == 0:
            continue
        rows.append(
            {
                "entity_id": f"{element['type']}/{element['id']}",
                "building": element.get("tags", {}).get("building"),
                "geometry": shape,
            }
        )
    frame = pd.DataFrame(rows, columns=["entity_id", "building", "geometry"])
    return gpd.GeoDataFrame(frame, geometry="geometry", crs=WGS84).to_crs(LAMBERT_93)


def match_building(point: BaseGeometry, buildings: gpd.GeoDataFrame) -> Match | None:
    """Return the building that contains the point, else the closest one within reach.

    When several outlines contain the point, the smallest is the most specific.
    """
    reach = point.buffer(NEAREST_MAX_METERS)
    nearby = buildings.iloc[buildings.sindex.query(reach)]
    if nearby.empty:
        return None
    distances = nearby.geometry.distance(point)
    containing = nearby[distances == 0]
    if not containing.empty:
        row = containing.loc[containing.geometry.area.idxmin()]
        return Match(row.entity_id, row.geometry, 0.0, "contains", row.building)
    closest = distances.idxmin()
    if distances[closest] > NEAREST_MAX_METERS:
        return None
    row = nearby.loc[closest]
    return Match(
        row.entity_id, row.geometry, float(distances[closest]), "nearest", row.building
    )


def match_targets(
    points: Mapping[str, BaseGeometry], buildings: gpd.GeoDataFrame
) -> gpd.GeoDataFrame:
    """Choose a building for each target notice that has one within reach."""
    rows = []
    for merimee_id in sorted(points):
        match = match_building(points[merimee_id], buildings)
        if match is not None:
            rows.append(
                {
                    "merimee_id": merimee_id,
                    "entity_id": match.entity_id,
                    "match": match.kind,
                    "distance_m": match.distance_m,
                    "building": match.building,
                    "geometry": match.geometry,
                }
            )
    frame = pd.DataFrame(rows, columns=NEARBY_COLUMNS)
    return gpd.GeoDataFrame(frame, geometry="geometry", crs=LAMBERT_93).to_crs(WGS84)


def evaluate(
    points: Mapping[str, BaseGeometry],
    known_footprints: Mapping[str, BaseGeometry],
    buildings: gpd.GeoDataFrame,
) -> pd.DataFrame:
    """Apply the rule to notices whose footprint is known and grade each choice."""
    rows = []
    for merimee_id in sorted(points):
        match = match_building(points[merimee_id], buildings)
        row: dict[str, Any] = dict.fromkeys(EVALUATION_COLUMNS)
        row |= {"merimee_id": merimee_id, "outcome": "none"}
        if match is not None:
            common = match.geometry.intersection(known_footprints[merimee_id]).area
            share = common / match.geometry.area
            row |= {
                "outcome": "correct" if share >= OVERLAP_SHARE else "wrong",
                "match": match.kind,
                "distance_m": round(match.distance_m, 1),
                "entity_id": match.entity_id,
                "overlap_share": round(share, 3),
            }
        rows.append(row)
    return pd.DataFrame(rows, columns=EVALUATION_COLUMNS)


def choose_sample(candidates: Sequence[str]) -> list[str]:
    """Draw the evaluation sample, always the same for the same candidates."""
    size = min(EVALUATION_SAMPLE_SIZE, len(candidates))
    return sorted(random.Random(EVALUATION_SEED).sample(sorted(candidates), size))


def project(points: Mapping[str, LatLon]) -> dict[str, BaseGeometry]:
    """Project {identifier: (lat, lon)} to Lambert-93 points."""
    records = [
        {"id": key, "lat": lat, "lon": lon} for key, (lat, lon) in points.items()
    ]
    return project_points(records, "id")


def save_snapshot(path: Path, elements: Sequence[Element]) -> None:
    """Keep the raw elements, so that the step can be replayed offline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    snapshot = {
        "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "elements": elements,
    }
    path.write_text(json.dumps(snapshot, ensure_ascii=False) + "\n")


def summarize(
    targets: Mapping[str, LatLon], nearby: gpd.GeoDataFrame, evaluation: pd.DataFrame
) -> dict[str, int]:
    """Count the matches and the evaluation outcomes."""

    def count(frame: pd.DataFrame, column: str, value: str) -> int:
        return int((frame[column] == value).sum())

    counts = {
        "targets": len(targets),
        "targets_in_a_building": count(nearby, "match", "contains"),
        "targets_next_to_a_building": count(nearby, "match", "nearest"),
        "targets_without_building": len(targets) - len(nearby),
        "evaluated": len(evaluation),
    }
    for match in ("contains", "nearest"):
        graded = evaluation[evaluation["match"] == match]
        counts[f"evaluated_{match}_correct"] = count(graded, "outcome", "correct")
        counts[f"evaluated_{match}_wrong"] = count(graded, "outcome", "wrong")
    counts["evaluated_none"] = count(evaluation, "outcome", "none")
    return counts


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Find the building of the monuments that OSM does not link."
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="reuse the last saved Overpass answers instead of querying the service",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    notices = to_records(pd.read_parquet(geometry.MERIMEE_PARQUET))
    current = geometry.build_geometries(
        notices,
        to_records(pd.read_parquet(geometry.ENTITIES_PARQUET)),
        to_records(pd.read_parquet(geometry.ENTITY_LINKS_PARQUET)),
        to_records(pd.read_parquet(geometry.WIKIDATA_ITEMS_PARQUET)),
        gpd.read_parquet(geometry.OSM_OBJECTS_PARQUET),
        geometry.read_overrides(geometry.OVERRIDES_CSV),
    )
    notices_by_id = {notice["merimee_id"]: notice for notice in notices}
    monuments = [
        row
        for row in current.itertuples()
        if notices_by_id[row.merimee_id]["protection"] is not None
        and is_building(notices_by_id[row.merimee_id]["denominations"])
    ]
    targets = {
        row.merimee_id: (row.ref_lat, row.ref_lon)
        for row in monuments
        if row.footprint_source == "buffer"
    }
    # The evaluation starts from the Mérimée point, as most targets do.
    known = [
        row.merimee_id
        for row in monuments
        if row.footprint_source == "osm_footprint"
        and notices_by_id[row.merimee_id]["lat"] is not None
    ]
    sample = {
        merimee_id: (notices_by_id[merimee_id]["lat"], notices_by_id[merimee_id]["lon"])
        for merimee_id in choose_sample(known)
    }

    if args.offline:
        elements = json.loads(RAW_SNAPSHOT.read_text())["elements"]
    else:
        with ingest_osm.make_client() as client:
            elements = fetch_buildings(
                client, [*targets.values(), *sample.values()], progress=PROGRESS_FILE
            )
        save_snapshot(RAW_SNAPSHOT, elements)
        PROGRESS_FILE.unlink(missing_ok=True)

    buildings = build_buildings(elements)
    nearby = match_targets(project(targets), buildings)
    footprints = current.set_index("merimee_id").geometry.to_crs(LAMBERT_93)
    evaluation = evaluate(
        project(sample), footprints.loc[list(sample)].to_dict(), buildings
    )

    NEARBY_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    nearby.to_parquet(NEARBY_PARQUET, index=False)
    evaluation.to_csv(EVALUATION_CSV, index=False)

    logger.info("Wrote %d buildings to %s", len(nearby), NEARBY_PARQUET)
    logger.info("Wrote %d evaluations to %s", len(evaluation), EVALUATION_CSV)
    for label, count in summarize(targets, nearby, evaluation).items():
        logger.info("  %-28s %5d", label, count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
