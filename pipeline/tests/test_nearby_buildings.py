from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import geopandas as gpd
import httpx
import pandas as pd
import pytest
from shapely.geometry import Point, Polygon, box
from shapely.geometry.base import BaseGeometry

from lutece_pipeline import geometry, ingest_osm
from lutece_pipeline import nearby_buildings as nearby
from lutece_pipeline.geo import LAMBERT_93

type Element = dict[str, Any]


def buildings(*shapes: tuple[str, BaseGeometry]) -> gpd.GeoDataFrame:
    """A table of buildings written directly in Lambert-93 meters."""
    frame = pd.DataFrame(
        [
            {"entity_id": entity_id, "building": "yes", "geometry": shape}
            for entity_id, shape in shapes
        ],
        columns=["entity_id", "building", "geometry"],
    )
    return gpd.GeoDataFrame(frame, geometry="geometry", crs=LAMBERT_93)


def closed_way(osm_id: int, lon: float, lat: float, **tags: str) -> Element:
    """A small square building as Overpass returns it."""
    corners = [
        (lon, lat),
        (lon + 1e-4, lat),
        (lon + 1e-4, lat + 1e-4),
        (lon, lat + 1e-4),
        (lon, lat),
    ]
    points = [{"lon": x, "lat": y} for x, y in corners]
    return {
        "type": "way",
        "id": osm_id,
        "geometry": points,
        "tags": {"building": "yes"} | tags,
    }


def sent_query(request: httpx.Request) -> str:
    return parse_qs(request.content.decode())["data"][0]


@pytest.mark.parametrize(
    ("denominations", "expected"),
    [
        (["immeuble"], True),
        (["magasin de commerce"], True),
        (["hôtel", "fontaine"], True),  # the main denomination decides
        (["station de métro"], False),
        (["fontaine", "immeuble"], False),
        ([], False),
        (None, False),
    ],
)
def test_is_building(denominations: list[str] | None, expected: bool) -> None:
    assert nearby.is_building(denominations) is expected


def test_around_query_lists_one_filter_per_point() -> None:
    query = nearby.around_query([(48.86, 2.35), (48.87, 2.36)])
    assert query == (
        "[out:json][timeout:180];("
        'wr["building"](around:30,48.860000,2.350000);'
        'wr["building"](around:30,48.870000,2.360000);'
        ");out geom;"
    )


def test_buildings_are_fetched_in_batches_without_duplicates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(nearby, "POINT_BATCH_SIZE", 2)
    queries: list[str] = []
    pauses: list[float] = []
    shared = closed_way(7, 2.35, 48.86)

    def handler(request: httpx.Request) -> httpx.Response:
        queries.append(sent_query(request))
        own = closed_way(len(queries), 2.35 + len(queries) / 100, 48.86)
        return httpx.Response(200, json={"elements": [shared, own]})

    points = [
        (48.86, 2.35),
        (48.87, 2.36),
        (48.88, 2.37),
        (48.86, 2.35),
    ]  # one duplicate
    with ingest_osm.make_client(httpx.MockTransport(handler)) as client:
        elements = nearby.fetch_buildings(client, points, pause=pauses.append)

    assert len(queries) == 2  # three distinct points, two per query
    assert [element["id"] for element in elements] == [1, 2, 7]
    assert pauses == [ingest_osm.BATCH_PAUSE_SECONDS]


def test_interrupted_fetch_resumes_where_it_stopped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(nearby, "POINT_BATCH_SIZE", 1)
    progress = tmp_path / "raw" / "partial.json"
    points = [(48.86, 2.35), (48.87, 2.36), (48.88, 2.37)]
    queries: list[str] = []

    def failing_on_the_second(request: httpx.Request) -> httpx.Response:
        queries.append(sent_query(request))
        if len(queries) == 2:
            return httpx.Response(400, request=request)
        return httpx.Response(200, json={"elements": [closed_way(1, 2.35, 48.86)]})

    with (
        ingest_osm.make_client(httpx.MockTransport(failing_on_the_second)) as client,
        pytest.raises(httpx.HTTPStatusError),
    ):
        nearby.fetch_buildings(
            client, points, pause=lambda seconds: None, progress=progress
        )
    assert len(queries) == 2

    def answering(request: httpx.Request) -> httpx.Response:
        queries.append(sent_query(request))
        return httpx.Response(
            200, json={"elements": [closed_way(len(queries), 2.36, 48.87)]}
        )

    with ingest_osm.make_client(httpx.MockTransport(answering)) as client:
        elements = nearby.fetch_buildings(
            client, points, pause=lambda seconds: None, progress=progress
        )
    # Only the two unanswered batches were asked again.
    assert len(queries) == 4
    assert queries[2:] == [nearby.around_query([point]) for point in points[1:]]
    assert [element["id"] for element in elements] == [1, 3, 4]


def test_only_areas_are_kept_as_buildings() -> None:
    line = {
        "type": "way",
        "id": 2,
        "geometry": [{"lon": 2.35, "lat": 48.86}, {"lon": 2.36, "lat": 48.86}],
        "tags": {"building": "wall"},
    }
    node = {
        "type": "node",
        "id": 3,
        "lon": 2.35,
        "lat": 48.86,
        "tags": {"building": "yes"},
    }
    table = nearby.build_buildings(
        [line, closed_way(1, 2.35, 48.86, building="church"), node]
    )
    assert table.crs == LAMBERT_93
    assert table["entity_id"].tolist() == ["way/1"]
    assert table["building"].tolist() == ["church"]
    assert table.geometry.area.iloc[0] == pytest.approx(
        7.3 * 11.1, rel=0.05
    )  # about 1e-4 degree a side


def test_point_inside_a_building_matches_the_smallest_outline() -> None:
    block = ("relation/1", box(0, 0, 100, 100))
    house = ("way/2", box(10, 10, 30, 30))
    neighbour = ("way/3", box(40, 10, 60, 30))
    match = nearby.match_building(Point(20, 20), buildings(block, neighbour, house))
    assert match is not None
    assert (match.entity_id, match.kind, match.distance_m) == ("way/2", "contains", 0.0)


def test_point_on_the_street_matches_the_closest_building_within_reach() -> None:
    near = ("way/1", box(0, 5, 20, 25))
    farther = ("way/2", box(0, -32, 20, -12))
    match = nearby.match_building(Point(10, 0), buildings(farther, near))
    assert match is not None
    assert (match.entity_id, match.kind) == ("way/1", "nearest")
    assert match.distance_m == pytest.approx(5)


def test_point_far_from_any_building_matches_nothing() -> None:
    limit = nearby.NEAREST_MAX_METERS
    table = buildings(("way/1", box(0, limit + 1, 20, limit + 20)))
    assert nearby.match_building(Point(10, 0), table) is None
    assert nearby.match_building(Point(10, 0), buildings()) is None


def test_targets_without_a_building_are_left_out() -> None:
    table = buildings(("way/1", box(0, 0, 20, 20)))
    points = {"PA1": Point(10, 10), "PA2": Point(500, 500), "PA3": Point(25, 10)}
    matched = nearby.match_targets(points, table)
    assert matched.crs == "EPSG:4326"
    assert list(matched.columns) == nearby.NEARBY_COLUMNS
    assert matched[["merimee_id", "entity_id", "match"]].to_dict("records") == [
        {"merimee_id": "PA1", "entity_id": "way/1", "match": "contains"},
        {"merimee_id": "PA3", "entity_id": "way/1", "match": "nearest"},
    ]


def test_evaluation_grades_each_choice_against_the_known_footprint() -> None:
    table = buildings(("way/1", box(0, 0, 20, 20)), ("way/2", box(100, 0, 120, 20)))
    points = {"PA1": Point(10, 10), "PA2": Point(110, 10), "PA3": Point(500, 500)}
    known = {
        "PA1": box(0, 0, 40, 20),  # the chosen building is part of the monument
        "PA2": box(119, 0, 150, 20),  # the monument is the neighbour: barely overlaps
        "PA3": box(480, 480, 520, 520),  # no building mapped there
    }
    evaluation = nearby.evaluate(points, known, table)
    assert list(evaluation.columns) == nearby.EVALUATION_COLUMNS
    assert evaluation["outcome"].tolist() == ["correct", "wrong", "none"]
    assert evaluation["overlap_share"].tolist()[:2] == [1.0, 0.05]
    assert pd.isna(evaluation["entity_id"].iloc[2])


def test_sample_is_reproducible_and_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(nearby, "EVALUATION_SAMPLE_SIZE", 3)
    candidates = [f"PA{number}" for number in range(10)]
    first = nearby.choose_sample(candidates)
    assert len(first) == 3
    assert first == nearby.choose_sample(list(reversed(candidates)))
    assert nearby.choose_sample(["PA1", "PA2"]) == ["PA1", "PA2"]


def test_geometry_adopts_the_building_only_for_a_circle_inside_it() -> None:
    building = box(0, 0, 20, 20)
    circle = geometry.locate([], Point(10, 10), None)
    assert circle is not None
    adopted = geometry.adopt_nearby_building(circle, "way/1", building)
    assert (adopted.footprint_source, adopted.objects) == ("osm_nearby", ("way/1",))
    assert adopted.footprint.area == pytest.approx(400)
    assert adopted.point.equals(circle.point)

    # A point corrected since the search and now outside keeps its circle.
    moved = geometry.locate([], Point(23, 10), None)
    assert moved is not None
    assert (
        geometry.adopt_nearby_building(moved, "way/1", building).footprint_source
        == "buffer"
    )

    # A notice that already has an OSM footprint keeps it.
    linked = geometry.OsmObject("way/9", box(0, 0, 50, 50), None, True, True, False)
    located = geometry.locate([linked], Point(10, 10), None)
    assert located is not None
    kept = geometry.adopt_nearby_building(located, "way/1", building)
    assert kept.footprint_source == "osm_footprint"


def test_adopted_building_always_contains_the_point() -> None:
    # A shallow bump on the wall: simplifying removes it, and the point with it.
    bumpy = Polygon([(0, 0), (20, 0), (20, 20), (10, 20.8), (0, 20)])
    assert not geometry.simplify(bumpy).contains(Point(10, 20.5))
    circle = geometry.locate([], Point(10, 20.5), None)
    assert circle is not None
    adopted = geometry.adopt_nearby_building(circle, "way/1", bumpy)
    assert adopted.footprint_source == "osm_nearby"
    assert adopted.footprint.contains(adopted.point)


def test_summary_separates_the_two_kinds_of_match() -> None:
    table = buildings(("way/1", box(0, 0, 20, 20)), ("way/2", box(100, 0, 120, 20)))
    matched = nearby.match_targets({"PA1": Point(10, 10), "PA2": Point(125, 10)}, table)
    evaluation = nearby.evaluate(
        {"PA7": Point(10, 10), "PA8": Point(125, 10), "PA9": Point(900, 900)},
        {
            "PA7": box(0, 0, 20, 20),
            "PA8": box(300, 0, 320, 20),
            "PA9": box(890, 890, 910, 910),
        },
        table,
    )
    targets = {"PA1": (48.86, 2.35), "PA2": (48.86, 2.36), "PA3": (48.86, 2.37)}
    assert nearby.summarize(targets, matched, evaluation) == {
        "targets": 3,
        "targets_in_a_building": 1,
        "targets_next_to_a_building": 1,
        "targets_without_building": 1,
        "evaluated": 3,
        "evaluated_contains_correct": 1,
        "evaluated_contains_wrong": 0,
        "evaluated_nearest_correct": 0,
        "evaluated_nearest_wrong": 1,
        "evaluated_none": 1,
    }


def run_main(
    folder: Path, out: Path, monkeypatch: pytest.MonkeyPatch, snapshot: Path
) -> None:
    out.mkdir(exist_ok=True)
    monkeypatch.setattr(geometry, "MERIMEE_PARQUET", folder / "merimee.parquet")
    monkeypatch.setattr(
        geometry, "WIKIDATA_ITEMS_PARQUET", folder / "wikidata_items.parquet"
    )
    monkeypatch.setattr(geometry, "OSM_OBJECTS_PARQUET", folder / "osm_objects.parquet")
    monkeypatch.setattr(geometry, "ENTITIES_PARQUET", folder / "entities.parquet")
    monkeypatch.setattr(
        geometry, "ENTITY_LINKS_PARQUET", folder / "entity_links.parquet"
    )
    monkeypatch.setattr(geometry, "OVERRIDES_CSV", out / "geometry_overrides.csv")
    monkeypatch.setattr(geometry, "NEARBY_PARQUET", out / "nearby_buildings.parquet")
    monkeypatch.setattr(geometry, "GEOMETRIES_PARQUET", out / "geometries.parquet")
    monkeypatch.setattr(geometry, "REVIEW_CSV", out / "geometries_to_review.csv")
    monkeypatch.setattr(nearby, "RAW_SNAPSHOT", snapshot)
    monkeypatch.setattr(nearby, "NEARBY_PARQUET", out / "nearby_buildings.parquet")
    monkeypatch.setattr(
        nearby, "EVALUATION_CSV", out / "nearby_buildings_evaluation.csv"
    )
    assert nearby.main(["--offline"]) == 0
    assert geometry.main([]) == 0


def test_offline_run_on_real_buildings(
    resolved_tables: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Real OSM buildings (© OpenStreetMap contributors, ODbL) around the fixture
    # notices that are buildings, recorded on 2026-10-07.
    snapshot = Path(__file__).parent / "fixtures" / "osm_nearby_snapshot.json"
    run_main(resolved_tables, tmp_path, monkeypatch, snapshot)

    found = gpd.read_parquet(tmp_path / "nearby_buildings.parquet").set_index(
        "merimee_id"
    )
    # Buildings without an OSM link: the café, the mansion and the former factory.
    # The metro station and the delisted stair rail are not searched.
    assert sorted(found.index) == ["PA00085786", "PA00085809", "PA75170009"]
    assert set(found["match"]) <= {"contains", "nearest"}

    evaluation = pd.read_csv(tmp_path / "nearby_buildings_evaluation.csv")
    # The two churches with a Mérimée point and a known footprint.
    assert evaluation["merimee_id"].tolist() == ["PA00085794", "PA00085795"]
    assert evaluation["outcome"].tolist() == ["correct", "correct"]

    geometries = gpd.read_parquet(tmp_path / "geometries.parquet").set_index(
        "merimee_id"
    )
    mansion = geometries.loc["PA00085809"]
    assert mansion["footprint_source"] == "osm_nearby"
    assert mansion["footprint_objects"] == found.loc["PA00085809", "entity_id"]
    assert mansion["point_source"] == "merimee"
    assert geometries.loc["PA00086579", "footprint_source"] == "buffer"  # metro station
    assert geometries.loc["PA00085795", "footprint_source"] == "osm_footprint"
