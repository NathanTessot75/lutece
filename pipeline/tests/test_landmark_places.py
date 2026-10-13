import json
from pathlib import Path

import geopandas as gpd
import httpx
import pandas as pd
import pytest
from shapely.geometry import LineString, Point, box

from lutece_pipeline import ingest_commons as commons
from lutece_pipeline import ingest_osm, ingest_wikidata, landmark_places, web
from lutece_pipeline.landmark_places import Decision

ENTITY = "http://www.wikidata.org/entity/"
HEADER = "qid,name,title,kind,group,decision,reach_m,osm,photos,note\n"
TOWER = Decision("Q323767", "Tour Montparnasse", "gratte-ciel", "Tours", 1500)
CAFE = Decision("Q1025686", "Café de Flore", "café", "Cafés", 0)
# 0.001° of longitude by 0.0005° of latitude: about 73 m by 56 m.
SQUARE = [(2.3210, 48.8415), (2.3220, 48.8415), (2.3220, 48.8420), (2.3210, 48.8420)]


def item(qid: str, name: str, **changes: object) -> dict[str, object]:
    """An item as `ingest_wikidata.build_item` gives it."""
    return {
        "qid": qid,
        "label_fr": name.lower(),
        "lat": 48.8421,
        "lon": 2.3220,
        "commons_category": name,
        "frwiki_title": name,
        "image_file": f"{name}.jpg",
        "inception_year": 1973,
        "architects": ["Eugène Beaudouin", "Jean Saubot"],
        "instance_of": ["gratte-ciel"],
        "sitelinks": 48,
        **changes,
    }


def way(
    osm_id: int, qid: str | None, corners: list[tuple[float, float]]
) -> dict[str, object]:
    """A closed way of OpenStreetMap, given by its corners as (lon, lat)."""
    ring = [*corners, corners[0]]
    tags = {"building": "yes"} | ({"wikidata": qid} if qid else {})
    return {
        "type": "way",
        "id": osm_id,
        "tags": tags,
        "geometry": [{"lon": lon, "lat": lat} for lon, lat in ring],
    }


def district(number: int, west: float, east: float) -> dict[str, object]:
    """An arrondissement of OpenStreetMap, a band between two longitudes."""
    ring = [(west, 48.80), (east, 48.80), (east, 48.90), (west, 48.90), (west, 48.80)]
    return {
        "type": "relation",
        "id": 9500 + number,
        "tags": {
            "type": "boundary",
            "admin_level": "9",
            "ref:INSEE": f"751{number:02d}",
            "wikidata": f"Q{number}",
        },
        "members": [
            {
                "type": "way",
                "role": "outer",
                "geometry": [{"lon": lon, "lat": lat} for lon, lat in ring],
            }
        ],
    }


def test_review_is_read_and_checked(tmp_path: Path) -> None:
    path = tmp_path / "landmarks.csv"
    path.write_text(
        HEADER
        + "Q323767,Tour Montparnasse,Tour Montparnasse,gratte-ciel,Tours,keep,1500,,,\n"
        + "Q9,Tour Triangle,,,Tours,drop,0,,,En chantier.\n"
        + "Q1025686,café de Flore,Café de Flore,café,Cafés,keep,0,,,\n"
        + "Q7,Tours Duo,Tours Duo,gratte-ciel,Tours,keep,500,way/12 relation/3,"
        # A file name may hold a comma: the cell is quoted, as a spreadsheet does.
        + '"Duo, côté Seine.jpg | File:Tour Duo 1.jpg",\n'
    )
    duo = Decision(
        "Q7",
        "Tours Duo",
        "gratte-ciel",
        "Tours",
        500,
        (("way", 12), ("relation", 3)),
        ("Duo, côté Seine.jpg", "Tour Duo 1.jpg"),
    )
    assert landmark_places.read_review(path) == [TOWER, CAFE, duo]
    assert landmark_places.named_objects([TOWER, CAFE, duo]) == {
        ("way", 12): "Q7",
        ("relation", 3): "Q7",
    }
    wrong = {
        "Q1,Tour,Tour,tour,Tours,maybe,0,,,\n": "line 2: unknown decision 'maybe'",
        "Q1,Tour,Tour,tour,Tours,keep,loin,,,\n": "line 2: 'loin' is not a distance",
        "Q1,Tour,,tour,Tours,keep,0,,,\n": "line 2: a place kept needs a title",
        "Q1,Tour,Tour,,Tours,keep,0,,,\n": "line 2: a place kept needs a title",
        "Q1,A,A,a,G,keep,0,,,\nQ1,A,A,a,G,drop,0,,,\n": "line 3: Q1 appears twice",
        "Q1,A,A,a,G,keep,0,way 12,,\n": "line 2: 'way' is not an object of OpenStreetMap",
        "Q1,A,A,a,G,keep,0,area/12,,\n": "line 2: 'area/12' is not an object",
    }
    for lines, message in wrong.items():
        path.write_text(HEADER + lines)
        with pytest.raises(ValueError, match=message):
            landmark_places.read_review(path)


def test_arrondissement_is_the_one_a_point_lies_in() -> None:
    elements = [
        district(15, 2.31, 2.33),
        way(1, "Q323767", SQUARE),
        district(6, 2.33, 2.35),
        # A boundary of another level, such as a quarter, is not an arrondissement.
        district(7, 2.35, 2.37) | {"tags": {"admin_level": "10", "ref:INSEE": "75107"}},
    ]
    districts = landmark_places.read_districts(elements)
    assert [number for number, _ in districts] == [6, 15]

    def point(lon: float) -> Point:
        return gpd.GeoSeries([Point(lon, 48.85)], crs="EPSG:4326").to_crs(2154)[0]

    assert landmark_places.district_of(point(2.32), districts) == 15
    assert landmark_places.district_of(point(2.34), districts) == 6
    # Outside every arrondissement, as in a neighbouring town.
    assert landmark_places.district_of(point(2.36), districts) is None
    assert landmark_places.district_of(point(2.32), []) is None


@pytest.mark.parametrize(
    ("year", "expected"), [(1973, 20), (1900, 19), (1901, 20), (52, 1), (None, None)]
)
def test_century_of_a_year(year: int | None, expected: int | None) -> None:
    assert landmark_places.century_of(year) == expected


def test_outline_is_the_area_then_the_line_then_a_circle() -> None:
    point = Point(0, 0)
    block = box(10, 10, 60, 40)
    path = LineString([(0, 0), (100, 0)])
    node = Point(5, 5)

    footprint, centre, source = landmark_places.outline([block, path, node], point)
    assert source == "osm_footprint"
    assert footprint.equals(block)
    assert footprint.contains(centre)
    # Two buildings of the same place make one outline.
    both, _, _ = landmark_places.outline([block, box(60, 10, 90, 40)], point)
    assert both.area == pytest.approx(block.area + 30 * 30)

    strip, centre, source = landmark_places.outline([path, node], point)
    assert source == "osm_line"
    assert strip.area == pytest.approx(100 * 6, rel=0.1)
    assert strip.contains(centre)

    circle, centre, source = landmark_places.outline([node], point)
    assert source == "buffer"
    assert centre.equals(node)
    assert circle.area == pytest.approx(314, rel=0.02)

    # Without any object, the circle stands around the point of Wikidata.
    circle, centre, source = landmark_places.outline([], point)
    assert (source, centre) == ("buffer", point)


def test_objects_are_gathered_by_item_in_metres() -> None:
    elements = [
        way(1, "Q323767", SQUARE),
        {
            "type": "node",
            "id": 2,
            "lon": 2.33,
            "lat": 48.85,
            "tags": {"wikidata": "Q9"},
        },
        # An object may stand for several items.
        {
            "type": "node",
            "id": 3,
            "lon": 2.34,
            "lat": 48.86,
            "tags": {"wikidata": "Q9; Q7"},
        },
        {"type": "way", "id": 4, "tags": {"wikidata": "Q5"}, "geometry": []},
    ]
    outlines = landmark_places.group_outlines(elements)
    assert sorted(outlines) == ["Q323767", "Q7", "Q9"]
    assert len(outlines["Q9"]) == 2
    assert outlines["Q323767"][0].area == pytest.approx(73 * 56, rel=0.03)
    assert landmark_places.group_outlines([]) == {}
    # An arrondissement is tied to an item too, but it draws no place.
    assert landmark_places.group_outlines([district(15, 2.31, 2.33)]) == {}


def test_objects_named_by_the_review_draw_the_place() -> None:
    elements = [
        # The café as the map has it: a point tied to the item.
        {
            "type": "node",
            "id": 2,
            "lon": 2.3215,
            "lat": 48.8417,
            "tags": {"wikidata": "Q1025686"},
        },
        # The building it is in, which the map ties to nothing or to another item.
        way(12, None, SQUARE),
        way(13, "Q99", SQUARE),
    ]
    named = {("way", 12): "Q1025686", ("way", 13): "Q1025686"}
    outlines = landmark_places.group_outlines(elements, named)
    assert sorted(outlines) == ["Q1025686", "Q99"]
    assert [shape.geom_type for shape in outlines["Q1025686"]] == [
        "Point",
        "Polygon",
        "Polygon",
    ]
    _, _, source = landmark_places.outline(outlines["Q1025686"], Point(0, 0))
    assert source == "osm_footprint"
    # An object that the map no longer has must be looked at, not passed over.
    with pytest.raises(ValueError, match="are not found: \\['relation/3'\\]"):
        landmark_places.group_outlines(elements, named | {("relation", 3): "Q7"})


def test_places_get_an_outline_and_the_facts_of_their_item() -> None:
    items = [
        item("Q323767", "Tour Montparnasse"),
        item(
            "Q1025686",
            "Café de Flore",
            lat=48.8539,
            lon=2.3325,
            inception_year=None,
            architects=[],
            commons_category=None,
        ),
    ]
    places = landmark_places.build_places(
        [CAFE, TOWER],
        items,
        {"Tour Montparnasse": 138_336},
        landmark_places.group_outlines([way(1, "Q323767", SQUARE)]),
        landmark_places.read_districts([district(15, 2.31, 2.325)]),
    )
    assert places.crs == "EPSG:4326"
    # Sorted by item, whatever the order of the review.
    assert list(places["qid"]) == ["Q323767", "Q1025686"]
    tower, cafe = places.to_dict("records")
    assert tower["title"] == "Tour Montparnasse"
    assert tower["kind"] == "gratte-ciel"
    assert tower["arrondissement"] == 15
    assert tower["footprint_source"] == "osm_footprint"
    assert tower["century"] == 20
    assert tower["architects"] == ["Eugène Beaudouin", "Jean Saubot"]
    assert (tower["views"], tower["languages"]) == (138_336, 48)
    assert tower["reach_m"] == 1500
    assert tower["geometry"].contains(Point(tower["ref_lon"], tower["ref_lat"]))
    assert 2.3210 <= tower["ref_lon"] <= 2.3220
    # No object in OpenStreetMap: a circle of 10 m around the point of Wikidata.
    assert cafe["footprint_source"] == "buffer"
    assert (cafe["ref_lat"], cafe["ref_lon"]) == pytest.approx((48.8539, 2.3325))
    # East of the only arrondissement known here.
    assert pd.isna(cafe["arrondissement"])
    assert pd.isna(cafe["century"])
    assert cafe["views"] == 0

    with pytest.raises(ValueError, match="did not find: \\['Q1025686'\\]"):
        landmark_places.build_places([CAFE], items[:1], {}, {}, [])
    lost = [item("Q323767", "Tour Montparnasse", lat=None, lon=None)]
    with pytest.raises(ValueError, match="without a point in Paris: \\['Q323767'\\]"):
        landmark_places.build_places([TOWER], lost, {}, {}, [])


def test_places_are_described_like_monuments_for_commons() -> None:
    fountain = Decision("Q7", "Fontaine Stravinsky", "fontaine", "Curiosités", 0)
    items = [
        item("Q323767", "Tour Montparnasse"),
        item("Q7", "Fontaine Stravinsky", commons_category=None, image_file=None),
    ]
    tower, basin = landmark_places.commons_subjects([TOWER, fountain], items)
    assert tower == commons.Monument(
        merimee_id="Q323767",
        category="Tour Montparnasse",
        main_image="Tour Montparnasse.jpg",
        names=("Tour Montparnasse", "gratte-ciel", "tour montparnasse"),
        exempt=frozenset(),
        entrance_only=False,
    )
    assert basin.category is None
    # A fountain is a sculpture: a file named after one is not a detail.
    assert basin.exempt == frozenset({commons.EXEMPT_KINDS["fontaine"]})


def photo(
    qid: str, name: str, rank: int | None, source: str = "category", **changes: object
) -> dict[str, object]:
    """A line of the Commons step: a file found for a place, ranked if kept."""
    row = dict.fromkeys(commons.FILES_SCHEMA.names)
    return row | {
        "merimee_id": qid,
        "title": f"File:{name}",
        "source": source,
        "rank": rank,
        "selected": rank is not None,
        "reject_reason": None if rank is not None else "other",
        **changes,
    }


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("File:Tour Montparnasse vue du jardin du Luxembourg.jpg", True),
        ("File:Paris 4e - Centre Georges Pompidou - File d'attente.jpg", True),
        ("File:Gare de Paris-Montparnasse DSC 1465.jpg", False),
        ("File:John Badham 2026 2.jpg", False),
    ],
)
def test_file_is_named_after_a_place_when_it_holds_one_of_its_names(
    title: str, expected: bool
) -> None:
    names = ["Tour Montparnasse", "Centre Georges-Pompidou", "Zénith de Paris"]
    assert landmark_places.is_named_after(title, names) is expected
    # A name made of common words only names nothing.
    assert not landmark_places.is_named_after(title, ["Paris", "des"])


def test_names_of_a_place_come_from_the_review_and_its_item() -> None:
    items = [item("Q323767", "Tour Montparnasse", frwiki_title="Tour Maine")]
    assert landmark_places.place_names([TOWER], items) == {
        "Q323767": ("Tour Montparnasse", "tour montparnasse", "Tour Maine")
    }


def test_photos_of_a_place_are_ordered_again() -> None:
    files = commons.from_rows(
        [
            photo("Q1", "Vue depuis la tour.jpg", 1),
            photo("Q1", "Tour Montparnasse 2.jpg", 2),
            photo("Q1", "Image de Wikidata.jpg", 3, "main_image"),
            photo("Q1", "Tour Montparnasse 1.jpg", 4),
            photo("Q1", "Vue de loin.jpg", None),
            photo("Q1", "Plan.pdf", None, reject_reason="format"),
            # Another place keeps the order of the Commons step.
            photo("Q2", "Soirée.jpg", 1),
            photo("Q2", "Affiche.jpg", 2),
        ],
        commons.FILES_SCHEMA,
    )
    names = {"Q1": ["Tour Montparnasse"], "Q2": ["Zénith"]}

    def ranked(first: dict[str, list[str]]) -> list[tuple[str, str]]:
        table = landmark_places.rank_for_places(files, names, first)
        kept = table[table["rank"].notna()].sort_values(["merimee_id", "rank"])
        assert list(kept["selected"]) == [True] * len(kept)
        return [
            (qid, title.removeprefix("File:"))
            for qid, title in zip(kept["merimee_id"], kept["title"], strict=True)
        ]

    # The image of Wikidata, the files named after the place, then the others.
    assert ranked({}) == [
        ("Q1", "Image de Wikidata.jpg"),
        ("Q1", "Tour Montparnasse 2.jpg"),
        ("Q1", "Tour Montparnasse 1.jpg"),
        ("Q1", "Vue depuis la tour.jpg"),
        ("Q2", "Soirée.jpg"),
        ("Q2", "Affiche.jpg"),
    ]
    # The photos that the review names come first, in its order, even one
    # that the Commons step had set aside for its subject.
    chosen = ranked({"Q1": ["Vue de loin.jpg", "Tour Montparnasse 1.jpg"]})
    assert chosen[:4] == [
        ("Q1", "Vue de loin.jpg"),
        ("Q1", "Tour Montparnasse 1.jpg"),
        ("Q1", "Image de Wikidata.jpg"),
        ("Q1", "Tour Montparnasse 2.jpg"),
    ]
    table = landmark_places.rank_for_places(files, names, {"Q1": ["Vue de loin.jpg"]})
    far = table[table["title"] == "File:Vue de loin.jpg"].iloc[0]
    assert pd.isna(far["reject_reason"])
    assert (far["rank"], far["selected"]) == (1, True)

    with pytest.raises(ValueError, match="Q1: 'Absente.jpg', named by the review"):
        landmark_places.rank_for_places(files, names, {"Q1": ["Absente.jpg"]})
    with pytest.raises(ValueError, match="Q1: 'Plan.pdf' cannot be shown"):
        landmark_places.rank_for_places(files, names, {"Q1": ["Plan.pdf"]})


def test_photos_beyond_the_selection_are_not_selected() -> None:
    rows = [photo("Q1", f"Photo {n:02d}.jpg", n) for n in range(1, 19)]
    files = commons.from_rows(rows, commons.FILES_SCHEMA)
    table = landmark_places.rank_for_places(files, {"Q1": ["Tour"]}, {})
    assert int(table["selected"].sum()) == commons.MAX_SELECTED


def test_outlines_and_arrondissements_are_asked_in_one_query() -> None:
    queries: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        queries.append(httpx.QueryParams(request.content.decode())["data"])
        return httpx.Response(200, json={"elements": [{"type": "node", "id": 1}]})

    duo = Decision(
        "Q7",
        "Tours Duo",
        "tour",
        "Tours",
        0,
        (("way", 12), ("relation", 3), ("way", 4)),
    )
    with ingest_osm.make_client(httpx.MockTransport(answer)) as client:
        elements = landmark_places.fetch_outlines(client, [TOWER, CAFE, duo])
        landmark_places.fetch_outlines(client, [TOWER])

    assert elements == [{"type": "node", "id": 1}]
    assert queries[0].endswith(
        '(nwr["wikidata"~"^(Q323767|Q1025686|Q7)$"](area.paris);'
        "relation(id:3);way(id:4,12);"
        'rel["boundary"="administrative"]["admin_level"="9"](area.paris););out geom;'
    )
    # Without any object named, only the tagged ones and the arrondissements.
    assert '(nwr["wikidata"~"^(Q323767)$"](area.paris);rel["boundary"' in queries[1]


def test_places_are_built_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "landmarks.csv").write_text(
        HEADER
        + "Q323767,Tour Montparnasse,Tour Montparnasse,gratte-ciel,Tours,keep,1500,,,\n"
        + "Q9,Tour Triangle,,,Tours,drop,0,,,\n"
    )
    row = {
        "item": ENTITY + "Q323767",
        "label": "tour Montparnasse",
        "sitelinks": "48",
        "articleTitle": "Tour Montparnasse",
        "coords": "Point(2.3220 48.8421)",
        "inceptions": "1973-06-18T00:00:00Z",
        "architects": "Jean Saubot|Eugène Beaudouin",
    }
    snapshots = {
        "items.json": {"items": [row], "gone": []},
        "views.json": {"views": {"Tour Montparnasse": 138_336}},
        "outlines.json": {
            "elements": [way(1, "Q323767", SQUARE), district(15, 2.31, 2.33)]
        },
    }
    for name, content in snapshots.items():
        (tmp_path / name).write_text(json.dumps(content))
    paths = {
        "REVIEW_CSV": tmp_path / "landmarks.csv",
        "ITEMS_SNAPSHOT": tmp_path / "items.json",
        "VIEWS_SNAPSHOT": tmp_path / "views.json",
        "OUTLINES_SNAPSHOT": tmp_path / "outlines.json",
        "COMMONS_FOLDER": tmp_path / "commons",
        "PLACES_PARQUET": tmp_path / "landmarks.parquet",
        "FILES_PARQUET": tmp_path / "landmark_files.parquet",
    }
    for name, path in paths.items():
        monkeypatch.setattr(landmark_places, name, path)

    def no_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("the offline run must not open a connection")

    for module in (ingest_osm, ingest_wikidata, commons, web):
        monkeypatch.setattr(module, "make_client", no_network)
    assert landmark_places.main(["--offline"]) == 0

    places = gpd.read_parquet(tmp_path / "landmarks.parquet")
    assert list(places["qid"]) == ["Q323767"]
    tower = places.iloc[0]
    assert (tower["title"], tower["arrondissement"], tower["century"]) == (
        "Tour Montparnasse",
        15,
        20,
    )
    assert tower["footprint_source"] == "osm_footprint"
    assert list(tower["architects"]) == ["Eugène Beaudouin", "Jean Saubot"]
    # Without any answer of Commons in the cache, the place has no photo yet.
    files = pd.read_parquet(tmp_path / "landmark_files.parquet")
    assert list(files.columns) == commons.FILES_SCHEMA.names
    assert len(files) == 0
