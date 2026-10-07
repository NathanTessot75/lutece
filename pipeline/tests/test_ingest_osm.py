import json
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import geopandas as gpd
import httpx
import pandas as pd
import pytest

from lutece_pipeline import ingest_merimee as merimee
from lutece_pipeline import ingest_osm as osm
from lutece_pipeline import ingest_wikidata as wikidata
from lutece_pipeline.tables import write_parquet

FIXTURES = Path(__file__).parent / "fixtures"
# Real Overpass elements (© OpenStreetMap contributors, ODbL) linked to the 11 Paris
# notices of the Mérimée fixture, recorded on 2026-10-07: 3 nodes, 6 ways, 3 relations.
SNAPSHOT_PATH = FIXTURES / "osm_snapshot.json"
ELEMENTS = json.loads(SNAPSHOT_PATH.read_text())["elements"]
WIKIDATA_LINK_ROWS = json.loads((FIXTURES / "wikidata_snapshot.json").read_text())[
    "links"
]

type Element = dict[str, Any]


def points(*coordinates: tuple[float, float]) -> list[dict[str, float]]:
    """Overpass geometry for (lon, lat) pairs."""
    return [{"lon": lon, "lat": lat} for lon, lat in coordinates]


def square(x: float, y: float, size: float) -> list[tuple[float, float]]:
    return [(x, y), (x + size, y), (x + size, y + size), (x, y + size), (x, y)]


def way(osm_id: int, coordinates: list[tuple[float, float]], **tags: str) -> Element:
    return {"type": "way", "id": osm_id, "geometry": points(*coordinates), "tags": tags}


def member(coordinates: list[tuple[float, float]], role: str = "") -> Element:
    return {"type": "way", "ref": 1, "role": role, "geometry": points(*coordinates)}


def relation(osm_id: int, kind: str, members: list[Element]) -> Element:
    return {
        "type": "relation",
        "id": osm_id,
        "members": members,
        "tags": {"type": kind},
    }


def overpass_response(elements: list[Element]) -> httpx.Response:
    return httpx.Response(200, json={"elements": elements})


def sent_query(request: httpx.Request) -> str:
    return parse_qs(request.content.decode())["data"][0]


@pytest.fixture(scope="module")
def merimee_ids() -> set[str]:
    return set(merimee.read_paris_notices(FIXTURES / "merimee_sample.csv")["Reference"])


@pytest.fixture(scope="module")
def links(merimee_ids: set[str]) -> pd.DataFrame:
    notices_by_qid = osm.notices_by_item(wikidata.build_links(WIKIDATA_LINK_ROWS))
    return osm.build_links(ELEMENTS, merimee_ids, notices_by_qid)


@pytest.fixture(scope="module")
def objects() -> gpd.GeoDataFrame:
    return osm.build_objects(ELEMENTS)


def test_geometry_query_groups_identifiers_by_type() -> None:
    query = osm.geometry_query([("way", 2), ("node", 1), ("way", 1), ("relation", 9)])
    assert (
        query
        == "[out:json][timeout:180];(node(id:1);relation(id:9);way(id:1,2););out geom;"
    )


def test_node_is_a_point() -> None:
    geometry = osm.element_geometry(
        {"type": "node", "id": 1, "lon": 2.35, "lat": 48.86}
    )
    assert geometry is not None
    assert (geometry.x, geometry.y) == (2.35, 48.86)


def test_closed_way_is_a_polygon() -> None:
    geometry = osm.element_geometry(way(1, square(0, 0, 2), building="yes"))
    assert geometry is not None
    assert geometry.geom_type == "Polygon"
    assert geometry.area == pytest.approx(4)


def test_open_way_is_a_line() -> None:
    geometry = osm.element_geometry(way(1, [(0, 0), (1, 0), (1, 1)]))
    assert geometry is not None
    assert geometry.geom_type == "LineString"


def test_closed_road_stays_a_line_unless_tagged_as_an_area() -> None:
    loop = osm.element_geometry(way(1, square(0, 0, 2), highway="pedestrian"))
    plaza = osm.element_geometry(
        way(2, square(0, 0, 2), highway="pedestrian", area="yes")
    )
    assert loop is not None
    assert plaza is not None
    assert loop.geom_type == "LineString"
    assert plaza.geom_type == "Polygon"


def test_way_without_enough_points_has_no_geometry() -> None:
    assert osm.element_geometry(way(1, [(0, 0)])) is None


def test_self_crossing_outline_is_repaired() -> None:
    bow_tie = way(1, [(0, 0), (2, 2), (2, 0), (0, 2), (0, 0)], building="yes")
    geometry = osm.element_geometry(bow_tie)
    assert geometry is not None
    assert geometry.is_valid
    assert geometry.area == pytest.approx(2)


def test_multipolygon_rings_are_stitched_and_holes_removed() -> None:
    # The outer ring comes as two open ways, listed out of order.
    outer_top = member([(4, 0), (4, 4), (0, 4), (0, 0)], role="outer")
    outer_bottom = member([(0, 0), (4, 0)], role="outer")
    hole = member(square(1, 1, 2), role="inner")
    geometry = osm.element_geometry(
        relation(1, "multipolygon", [outer_top, hole, outer_bottom])
    )
    assert geometry is not None
    assert geometry.geom_type == "Polygon"
    assert geometry.area == pytest.approx(16 - 4)
    assert len(geometry.interiors) == 1


def test_site_relation_is_the_union_of_its_buildings() -> None:
    members = [
        member(square(0, 0, 1)),
        member(square(5, 5, 2)),
        member([(9, 9), (10, 9)]),
    ]
    geometry = osm.element_geometry(relation(1, "site", members))
    assert geometry is not None
    assert geometry.geom_type == "MultiPolygon"
    assert geometry.area == pytest.approx(1 + 4)


def test_street_segments_forming_a_loop_do_not_become_an_area() -> None:
    # Three street segments around a block close a ring, but a street is not an area.
    segments = [
        member([(0, 0), (4, 0)], role="street"),
        member([(4, 0), (4, 4), (0, 4)], role="street"),
        member([(0, 4), (0, 0)], role="street"),
    ]
    geometry = osm.element_geometry(relation(1, "associatedStreet", segments))
    assert geometry is not None
    assert geometry.area == 0
    assert geometry.length == pytest.approx(16)


def test_relation_without_ways_falls_back_to_its_nodes() -> None:
    nodes = [{"type": "node", "ref": 1, "role": "stop", "lon": 2.3, "lat": 48.8}]
    geometry = osm.element_geometry(relation(1, "public_transport", nodes))
    assert geometry is not None
    assert geometry.geom_type == "MultiPoint"
    assert osm.element_geometry(relation(2, "site", [])) is None


def test_links_record_which_tag_designates_the_notice() -> None:
    elements = [
        {"type": "way", "id": 7, "tags": {"ref:mhs": "PA1; PA2;PA9", "wikidata": "Q1"}},
        {"type": "node", "id": 3, "tags": {"wikidata": "Q5;Q1"}},
        {"type": "node", "id": 4, "tags": {"name": "unrelated"}},
    ]
    links = osm.build_links(elements, {"PA1", "PA2", "PA3"}, {"Q1": {"PA2", "PA3"}})
    assert links.to_dict("records") == [
        {
            "merimee_id": "PA1",
            "osm_type": "way",
            "osm_id": 7,
            "via_ref_mhs": True,
            "via_wikidata": False,
        },
        {
            "merimee_id": "PA2",
            "osm_type": "node",
            "osm_id": 3,
            "via_ref_mhs": False,
            "via_wikidata": True,
        },
        {
            "merimee_id": "PA2",
            "osm_type": "way",
            "osm_id": 7,
            "via_ref_mhs": True,
            "via_wikidata": True,
        },
        {
            "merimee_id": "PA3",
            "osm_type": "node",
            "osm_id": 3,
            "via_ref_mhs": False,
            "via_wikidata": True,
        },
        {
            "merimee_id": "PA3",
            "osm_type": "way",
            "osm_id": 7,
            "via_ref_mhs": False,
            "via_wikidata": True,
        },
    ]


def test_notices_by_item_does_not_depend_on_the_dtype_backend() -> None:
    arrow_backed = wikidata.build_links(WIKIDATA_LINK_ROWS)
    numpy_backed = pd.DataFrame(arrow_backed.to_dict("records"))
    expected = {"PA00086088"}
    assert osm.notices_by_item(arrow_backed)["Q2055787"] == expected
    assert osm.notices_by_item(numpy_backed)["Q2055787"] == expected


def test_real_links(links: pd.DataFrame) -> None:
    assert list(links.columns) == osm.LINKS_SCHEMA.names
    assert len(links) == 12
    # The church carries both tags; the temple is only reachable through Wikidata.
    church = links[links["merimee_id"] == "PA00085795"].iloc[0]
    temple = links[links["merimee_id"] == "PA75110005"].iloc[0]
    assert (church["osm_type"], church["osm_id"]) == ("way", 53762963)
    assert church["via_ref_mhs"] and church["via_wikidata"]
    assert not temple["via_ref_mhs"] and temple["via_wikidata"]
    assert (links["merimee_id"] == "PA00086088").sum() == 4


def test_real_objects(objects: gpd.GeoDataFrame) -> None:
    assert list(objects.columns) == [*osm.OBJECT_COLUMNS, "geometry"]
    assert objects.crs == "EPSG:4326"
    assert len(objects) == 12
    assert objects.geometry.is_valid.all()

    by_id = objects.set_index("osm_id")
    church = by_id.loc[53762963]
    assert church["name"] == "Église Saint-Eustache"
    assert church["ref_mhs"] == "PA00085795"
    assert church["building"] == "church"
    assert json.loads(church["tags"])["wikidata"] == "Q1338207"
    assert church.geometry.geom_type == "Polygon"
    assert pd.isna(church["relation_type"])

    canal = by_id.loc[1164565]
    assert canal["relation_type"] == "waterway"
    assert canal.geometry.geom_type == "MultiLineString"
    assert by_id.loc[241928557].geometry.geom_type == "Point"


def test_church_footprint_has_a_plausible_size(objects: gpd.GeoDataFrame) -> None:
    areas = objects.set_index("osm_id").geometry.to_crs("EPSG:2154").area
    assert areas.loc[53762963] == pytest.approx(4210, abs=50)  # Saint-Eustache, in m²


def test_duplicated_objects_are_rejected() -> None:
    with pytest.raises(ValueError, match="Several rows for the same OSM object"):
        osm.build_objects([ELEMENTS[0], ELEMENTS[0]])


def test_summary_counts_matches_and_gaps(
    merimee_ids: set[str], links: pd.DataFrame, objects: gpd.GeoDataFrame
) -> None:
    assert osm.summarize(merimee_ids, links, objects) == {
        "notices": 11,
        "notices_without_object": 3,
        "notices_via_ref_mhs": 4,
        "notices_via_wikidata": 8,
        "notices_via_both": 4,
        "notices_with_footprint": 4,
        "objects": 12,
        "nodes": 3,
        "ways": 6,
        "relations": 3,
        "objects_without_geometry": 0,
    }


def test_overpass_runtime_errors_are_raised() -> None:
    payload = {"elements": [], "remark": "runtime error: Query timed out"}
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    with (
        osm.make_client(transport) as client,
        pytest.raises(RuntimeError, match="timed out"),
    ):
        osm.run_overpass(client, "out;")


def test_geometry_is_only_requested_for_new_objects_of_our_items() -> None:
    queries: list[str] = []
    pauses: list[float] = []
    tagged_with_reference = way(
        1, square(0, 0, 1), **{"ref:mhs": "PA1", "wikidata": "Q1"}
    )
    extra_node = {
        "type": "node",
        "id": 5,
        "lon": 2.3,
        "lat": 48.8,
        "tags": {"wikidata": "Q1"},
    }
    extra_relation = relation(8, "site", [member(square(0, 0, 1))])
    extra_relation["tags"]["wikidata"] = "Q2;Q1"

    def handler(request: httpx.Request) -> httpx.Response:
        query = sent_query(request)
        queries.append(query)
        if query == osm.REF_MHS_QUERY:
            return overpass_response([tagged_with_reference])
        if query == osm.WIKIDATA_TAGGED_QUERY:
            return overpass_response(
                [
                    {
                        "type": "way",
                        "id": 1,
                        "tags": {"wikidata": "Q1"},
                    },  # already fetched
                    {"type": "node", "id": 5, "tags": {"wikidata": "Q1"}},
                    {
                        "type": "way",
                        "id": 7,
                        "tags": {"wikidata": "Q9"},
                    },  # not one of ours
                    {"type": "relation", "id": 8, "tags": {"wikidata": "Q2;Q1"}},
                ]
            )
        return overpass_response([extra_node, extra_relation])

    with osm.make_client(httpx.MockTransport(handler)) as client:
        elements = osm.fetch_elements(client, {"Q1"}, pause=pauses.append)

    assert queries[2] == osm.geometry_query([("node", 5), ("relation", 8)])
    assert len(queries) == 3
    assert [osm.element_key(element) for element in elements] == [
        ("way", 1),
        ("node", 5),
        ("relation", 8),
    ]
    assert pauses == [osm.BATCH_PAUSE_SECONDS] * 2


def test_offline_run_writes_both_tables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    notices = merimee.normalize(
        merimee.read_paris_notices(FIXTURES / "merimee_sample.csv")
    )
    write_parquet(notices, merimee.OUTPUT_SCHEMA, tmp_path / "merimee.parquet")
    wikidata_links = wikidata.build_links(WIKIDATA_LINK_ROWS)
    write_parquet(
        wikidata_links, wikidata.LINKS_SCHEMA, tmp_path / "wikidata_links.parquet"
    )
    shutil.copy(SNAPSHOT_PATH, tmp_path / "snapshot.json")
    monkeypatch.setattr(osm, "MERIMEE_PARQUET", tmp_path / "merimee.parquet")
    monkeypatch.setattr(
        osm, "WIKIDATA_LINKS_PARQUET", tmp_path / "wikidata_links.parquet"
    )
    monkeypatch.setattr(osm, "RAW_SNAPSHOT", tmp_path / "snapshot.json")
    monkeypatch.setattr(osm, "OBJECTS_PARQUET", tmp_path / "out" / "objects.parquet")
    monkeypatch.setattr(osm, "LINKS_PARQUET", tmp_path / "out" / "links.parquet")

    assert osm.main(["--offline"]) == 0

    objects = gpd.read_parquet(tmp_path / "out" / "objects.parquet")
    assert objects.crs == "EPSG:4326"
    assert len(objects) == 12
    # Plain pandas reads must work too: the geometry then comes as WKB bytes.
    assert isinstance(
        pd.read_parquet(tmp_path / "out" / "objects.parquet")["geometry"][0], bytes
    )
    links = pd.read_parquet(tmp_path / "out" / "links.parquet")
    assert len(links) == 12
    assert set(zip(links["osm_type"], links["osm_id"], strict=True)) == set(
        zip(objects["osm_type"], objects["osm_id"], strict=True)
    )
