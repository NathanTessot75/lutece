import math
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import LineString, Point, Polygon, box
from shapely.geometry.base import BaseGeometry

from lutece_pipeline import geometry

# Synthetic geometries are written directly in Lambert-93 meters.
ORIGIN = Point(652_000, 6_862_000)


def osm_object(
    entity_id: str,
    shape: BaseGeometry,
    *,
    relation_type: str | None = None,
    is_footprint: bool = False,
    is_primary: bool = False,
    via_ref_mhs: bool = False,
) -> geometry.OsmObject:
    return geometry.OsmObject(
        entity_id, shape, relation_type, is_footprint, is_primary, via_ref_mhs
    )


def square(x: float, y: float, size: float) -> Polygon:
    return box(x, y, x + size, y + size)


def run_main(
    folder: Path, out: Path, monkeypatch: pytest.MonkeyPatch, overrides: str = ""
) -> None:
    out.mkdir(exist_ok=True)
    overrides_csv = out / "geometry_overrides.csv"
    if overrides:
        overrides_csv.write_text("merimee_id,use,lat,lon,note\n" + overrides)
    monkeypatch.setattr(geometry, "MERIMEE_PARQUET", folder / "merimee.parquet")
    monkeypatch.setattr(
        geometry, "WIKIDATA_ITEMS_PARQUET", folder / "wikidata_items.parquet"
    )
    monkeypatch.setattr(geometry, "OSM_OBJECTS_PARQUET", folder / "osm_objects.parquet")
    monkeypatch.setattr(geometry, "ENTITIES_PARQUET", folder / "entities.parquet")
    monkeypatch.setattr(
        geometry, "ENTITY_LINKS_PARQUET", folder / "entity_links.parquet"
    )
    monkeypatch.setattr(geometry, "OVERRIDES_CSV", overrides_csv)
    monkeypatch.setattr(geometry, "GEOMETRIES_PARQUET", out / "geometries.parquet")
    monkeypatch.setattr(geometry, "REVIEW_CSV", out / "geometries_to_review.csv")
    assert geometry.main([]) == 0


def test_confirmed_footprints_are_merged() -> None:
    church = osm_object("way/1", square(0, 0, 20), is_footprint=True, is_primary=True)
    chapel = osm_object("way/2", square(30, 0, 10), is_footprint=True)
    entrance = osm_object("node/3", Point(5, 5))
    location = geometry.footprint_from_areas([chapel, entrance, church])
    assert location is not None
    assert location.footprint_source == "osm_footprint"
    assert location.footprint.area == pytest.approx(400 + 100)
    assert location.objects == ("way/1", "way/2")
    # The reference point lies in the main footprint, not just anywhere in the union.
    assert church.geometry.contains(location.point)


def test_object_chosen_by_a_reviewer_counts_as_a_footprint() -> None:
    cemetery = osm_object(
        "relation/9", square(0, 0, 100), relation_type="street", is_primary=True
    )
    tomb = osm_object("way/1", square(10, 10, 2), is_footprint=True)
    location = geometry.footprint_from_areas([tomb, cemetery])
    assert location is not None
    assert location.footprint.area == pytest.approx(10_000)
    assert location.objects == ("relation/9", "way/1")


def test_notice_without_area_has_no_merged_footprint() -> None:
    line = osm_object("way/1", LineString([(0, 0), (10, 0)]))
    assert geometry.footprint_from_areas([line]) is None
    assert geometry.footprint_from_areas([]) is None


def test_line_is_widened_into_a_strip() -> None:
    passage = osm_object("way/1", LineString([(0, 0), (100, 0)]))
    location = geometry.footprint_from_lines([passage], Point(40, 25))
    assert location is not None
    assert location.footprint_source == "osm_line"
    width = 2 * geometry.LINE_HALF_WIDTH_METERS
    assert location.footprint.area == pytest.approx(100 * width + math.pi * 9, rel=0.02)
    # The reference point is the spot of the line closest to the Mérimée point.
    assert (location.point.x, location.point.y) == pytest.approx((40, 0))


def test_line_without_a_merimee_point_still_gets_a_reference() -> None:
    passage = osm_object("way/1", LineString([(0, 0), (100, 0)]))
    location = geometry.footprint_from_lines([passage], None)
    assert location is not None
    assert location.footprint.contains(location.point)


def test_street_relations_are_not_the_monument() -> None:
    street = osm_object(
        "relation/1", LineString([(0, 0), (100, 0)]), relation_type="associatedStreet"
    )
    assert geometry.footprint_from_lines([street], ORIGIN) is None


def test_standalone_point_prefers_the_node_tagged_with_the_reference() -> None:
    tagged_far = osm_object("node/1", Point(50, 0), via_ref_mhs=True)
    tagged_near = osm_object("node/2", Point(8, 0), via_ref_mhs=True)
    untagged = osm_object("node/3", Point(1, 0))
    chosen = geometry.standalone_point(
        [tagged_far, untagged, tagged_near], Point(0, 0), None
    )
    assert chosen == (tagged_near.geometry, "osm_node")


def test_standalone_point_falls_back_to_merimee_then_wikidata() -> None:
    untagged = osm_object("node/3", Point(1, 0))
    merimee_point, wikidata_point = Point(0, 0), Point(5, 5)
    assert geometry.standalone_point([untagged], merimee_point, wikidata_point) == (
        merimee_point,
        "merimee",
    )
    assert geometry.standalone_point([], None, wikidata_point) == (
        wikidata_point,
        "wikidata",
    )
    assert geometry.standalone_point([], None, None) is None


def test_locate_prefers_areas_then_lines_then_a_circle() -> None:
    area = osm_object("way/1", square(0, 0, 20), is_footprint=True)
    line = osm_object("way/2", LineString([(0, 0), (100, 0)]))
    both = geometry.locate([line, area], ORIGIN, None)
    only_line = geometry.locate([line], ORIGIN, None)
    nothing = geometry.locate([], ORIGIN, None)
    assert both is not None
    assert only_line is not None
    assert nothing is not None
    assert both.footprint_source == "osm_footprint"
    assert only_line.footprint_source == "osm_line"
    assert (nothing.footprint_source, nothing.point_source) == ("buffer", "merimee")
    assert nothing.footprint.area == pytest.approx(math.pi * 10**2, rel=0.01)
    assert nothing.footprint.centroid.distance(ORIGIN) < 1e-6
    assert geometry.locate([], None, None) is None


def test_reviewed_point_replaces_the_automatic_one() -> None:
    reviewed = (Point(500, 500), "wikidata")
    circle = geometry.locate([], ORIGIN, Point(500, 500), reviewed)
    assert circle is not None
    assert circle.point_source == "wikidata"
    assert circle.footprint.centroid.distance(Point(500, 500)) < 1e-6

    area = osm_object("way/1", square(0, 0, 20), is_footprint=True)
    kept = geometry.locate([area], ORIGIN, None, (Point(3, 3), "manual"))
    assert kept is not None
    assert (kept.point_source, kept.footprint_source) == ("manual", "osm_footprint")
    assert (kept.point.x, kept.point.y) == (3, 3)


def test_simplify_drops_points_that_do_not_change_the_outline() -> None:
    jagged = Polygon([(0, 0), (5, 0.2), (10, 0), (10, 10), (5, 10.3), (0, 10)])
    simplified = geometry.simplify(jagged)
    assert simplified.is_valid
    assert len(simplified.exterior.coords) == 5
    assert simplified.area == pytest.approx(100, rel=0.02)
    tiny = square(0, 0, 0.5)
    assert not geometry.simplify(tiny).is_empty


def test_read_overrides(tmp_path: Path) -> None:
    path = tmp_path / "overrides.csv"
    assert geometry.read_overrides(path) == {}
    path.write_text(
        "merimee_id,use,lat,lon,note\n"
        'PA1,wikidata,,,"moved, see the notice title"\n'
        "PA2,manual,48.86,2.35,checked on site\n"
    )
    assert geometry.read_overrides(path) == {
        "PA1": geometry.Override("wikidata"),
        "PA2": geometry.Override("manual", 48.86, 2.35),
    }


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ("PA1,elsewhere,,,\n", "unknown choice 'elsewhere'"),
        ("PA1,merimee,,,\nPA1,wikidata,,,\n", "decided twice"),
        ("PA1,manual,48.86,,\n", "needs lat and lon"),
    ],
)
def test_invalid_overrides_are_refused(tmp_path: Path, rows: str, message: str) -> None:
    path = tmp_path / "overrides.csv"
    path.write_text("merimee_id,use,lat,lon,note\n" + rows)
    with pytest.raises(ValueError, match=message):
        geometry.read_overrides(path)


def test_real_notices_get_a_point_and_a_footprint(
    resolved_tables: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_main(resolved_tables, tmp_path, monkeypatch)

    geometries = gpd.read_parquet(tmp_path / "geometries.parquet").set_index(
        "merimee_id"
    )
    assert list(geometries.reset_index().columns) == geometry.COLUMNS
    assert geometries.crs == "EPSG:4326"
    assert len(geometries) == 11
    assert geometries.geometry.is_valid.all()
    assert geometries.geometry.geom_type.isin(["Polygon", "MultiPolygon"]).all()
    # Plain pandas reads must work too.
    assert len(pd.read_parquet(tmp_path / "geometries.parquet")) == 11

    church = geometries.loc["PA00085795"]  # Saint-Eustache, mapped as a building
    assert (church["footprint_source"], church["point_source"]) == (
        "osm_footprint",
        "osm_footprint",
    )
    assert church["footprint_objects"] == "way/53762963"
    assert church["footprint_area_m2"] == pytest.approx(4200, rel=0.03)
    assert church.geometry.contains(Point(church["ref_lon"], church["ref_lat"]))

    canal = geometries.loc["PA00125441"]  # mapped as a waterway relation
    assert canal["footprint_source"] == "osm_line"
    assert canal["footprint_objects"] == "relation/1164565"

    cafe = geometries.loc["PA00085786"]  # only an untagged shop node: Mérimée point
    assert (cafe["footprint_source"], cafe["point_source"]) == ("buffer", "merimee")
    assert cafe["footprint_area_m2"] == pytest.approx(math.pi * 100, rel=0.01)
    assert pd.isna(cafe["footprint_objects"])

    station = geometries.loc["PA00086579"]  # no Mérimée point at all
    assert (station["footprint_source"], station["point_source"]) == (
        "buffer",
        "wikidata",
    )

    temple = geometries.loc["PA75110005"]  # no Mérimée point, but an accepted footprint
    assert temple["footprint_source"] == "osm_footprint"
    assert pd.isna(temple["point_gap_m"])


def test_conflicting_points_are_flagged_but_only_monuments_are_reviewed(
    resolved_tables: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_main(resolved_tables, tmp_path, monkeypatch)

    geometries = gpd.read_parquet(tmp_path / "geometries.parquet").set_index(
        "merimee_id"
    )
    # The delisted stair rail: its two points are 2.4 km apart.
    assert geometries.loc["PA00086620", "point_gap_m"] == pytest.approx(2447, abs=5)
    assert bool(geometries.loc["PA00086620", "point_doubtful"])
    assert int(geometries["point_doubtful"].sum()) == 1
    # It is no longer protected, so nobody is asked to review it.
    assert len(pd.read_csv(tmp_path / "geometries_to_review.csv")) == 0


def test_reviewed_choice_moves_the_point_and_clears_the_doubt(
    resolved_tables: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    overrides = "PA00086620,wikidata,,,test\nPA00085786,manual,48.8640,2.3500,test\n"
    run_main(resolved_tables, tmp_path, monkeypatch, overrides)

    geometries = gpd.read_parquet(tmp_path / "geometries.parquet").set_index(
        "merimee_id"
    )
    rail = geometries.loc["PA00086620"]
    assert rail["point_source"] == "wikidata"
    assert (rail["ref_lat"], rail["ref_lon"]) == pytest.approx(
        (48.855, 2.3568), abs=1e-4
    )
    assert not rail["point_doubtful"]
    assert rail["point_reviewed"]

    cafe = geometries.loc["PA00085786"]
    assert cafe["point_source"] == "manual"
    assert (cafe["ref_lat"], cafe["ref_lon"]) == pytest.approx(
        (48.8640, 2.3500), abs=1e-6
    )
    assert cafe.geometry.contains(Point(2.3500, 48.8640))
    assert int(geometries["point_reviewed"].sum()) == 2


def test_choice_without_a_point_is_refused(
    resolved_tables: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The Nation station has no Mérimée point to fall back on.
    with pytest.raises(ValueError, match="PA00086579: the reviewed choice 'merimee'"):
        run_main(resolved_tables, tmp_path, monkeypatch, "PA00086579,merimee,,,test\n")
