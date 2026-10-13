import json
from pathlib import Path

import geopandas as gpd
import httpx
import pandas as pd
import pytest
from shapely.geometry import box

from lutece_pipeline import ingest_wikidata, landmarks, selection, web
from lutece_pipeline.landmarks import Scale
from lutece_pipeline.tables import to_records

ENTITY = "http://www.wikidata.org/entity/"
# A monument 111 m long and 73 m wide, north-east of the point (48.85, 2.35).
PALACE = box(2.35, 48.85, 2.351, 48.851)


def place(qid: str, name: str, *kinds: str, **changes: object) -> dict[str, object]:
    """An item as `ingest_wikidata.build_item` gives it."""
    return {
        "qid": qid,
        "label_fr": name,
        "lat": 48.86,
        "lon": 2.34,
        "frwiki_title": name,
        "instance_of": list(kinds),
        "sitelinks": 30,
        **changes,
    }


def monument(rank: int, views: int, languages: int) -> dict[str, object]:
    return {"rank": rank, "views": views, "languages": languages}


# Four monuments, of which the app shows the first two.
SCALE = Scale(
    [
        monument(1, 9000, 90),
        monument(2, 3000, 10),
        monument(3, 500, 4),
        monument(4, 100, 2),
    ],
    last_rank_shown=2,
)


def test_place_is_scored_among_the_monuments() -> None:
    # As read as the best known and in as many languages: at the top.
    assert SCALE.score(9000, 90) == 1.0
    assert SCALE.score(50_000, 200) == 1.0
    # Less known than any of them.
    assert SCALE.score(10, 1) == 0.0
    # Read like the second, translated like the third.
    assert SCALE.score(3000, 4) == pytest.approx((0.75 + 0.5) / 2)
    # The bar is what the last monument shown scores.
    assert SCALE.bar == pytest.approx(0.75)


@pytest.mark.parametrize(
    ("kinds", "expected"),
    [
        (("gratte-ciel",), ("keep", None)),
        (("musée d'art", "bâtiment"), ("keep", None)),
        (("place",), ("keep", None)),
        (("cabaret",), ("keep", None)),
        (("gare ferroviaire",), ("keep", None)),
        ((), ("keep", None)),
        (("arrondissement municipal en France",), ("drop", "not_a_place")),
        (("station de métro",), ("drop", "not_a_place")),
        (("attaque terroriste",), ("drop", "not_a_place")),
        (("université publique",), ("drop", "not_a_place")),
        (("boulevard",), ("drop", "not_a_place")),
        (("jardin public",), ("drop", "open_ground")),
        (("cimetière",), ("drop", "open_ground")),
    ],
)
def test_only_places_to_stand_in_front_of_are_suggested(
    kinds: tuple[str, ...], expected: tuple[str, str | None]
) -> None:
    found = place("Q1", "Lieu", *kinds)
    assert landmarks.judge(found, gone=False, host=None, known_enough=True) == expected


def test_first_reason_to_leave_a_place_out_is_given() -> None:
    tower = place("Q1", "Tour Montparnasse", "gratte-ciel")

    def judge(**changes: object) -> tuple[str, str | None]:
        facts = {"gone": False, "host": None, "known_enough": True, **changes}
        return landmarks.judge(tower, **facts)  # type: ignore[arg-type]

    assert judge() == ("keep", None)
    assert judge(gone=True) == ("drop", "no_longer_there")
    assert judge(host="Palais du Louvre") == ("drop", "already_on_the_map")
    assert judge(known_enough=False) == ("drop", "too_little_known")
    assert judge(gone=True, host="Palais", known_enough=False) == (
        "drop",
        "no_longer_there",
    )
    # A place that Wikidata does not locate in Paris cannot be put on the map.
    lost = {**tower, "lat": None, "lon": None}
    assert landmarks.judge(lost, gone=False, host=None, known_enough=True) == (
        "drop",
        "not_a_place",
    )


def test_place_in_or_against_a_monument_shown_is_matched_to_it() -> None:
    palaces = [
        {"name": "Palais du Louvre", "geometry": PALACE},
        {"name": "Hôtel de Sully", "geometry": box(2.36, 48.85, 2.3601, 48.8501)},
    ]
    places = [
        place("Q1", "Musée du Louvre", lat=48.8505, lon=2.3505),
        # Ten metres west of the palace: against it.
        place("Q2", "Pyramide", lat=48.8505, lon=2.34987),
        # A hundred metres west: another place.
        place("Q3", "Tour", lat=48.8505, lon=2.3486),
        place("Q4", "Nulle part", lat=None, lon=None),
    ]
    assert landmarks.find_hosts(places, palaces) == {
        "Q1": "Palais du Louvre",
        "Q2": "Palais du Louvre",
    }
    assert landmarks.find_hosts(places, []) == {}
    assert landmarks.find_hosts([], palaces) == {}


def test_candidates_are_listed_from_the_best_known_with_a_suggestion() -> None:
    places = [
        place("Q3", "Musée du Louvre", "musée d'art", sitelinks=170),
        place("Q1", "Tour Montparnasse", "gratte-ciel", sitelinks=48),
        place("Q2", "Café inconnu", "café", sitelinks=4),
        place("Q4", "Bastille", "château fort", sitelinks=86),
    ]
    views = {"Musée du Louvre": 900_000, "Tour Montparnasse": 80_000, "Bastille": 5000}
    table = landmarks.build_candidates(
        places, views, ["Q4"], {"Q3": "Palais du Louvre"}, SCALE
    )
    rows = to_records(table)
    assert [row["qid"] for row in rows] == ["Q3", "Q1", "Q4", "Q2"]
    assert [(row["suggestion"], row["why"]) for row in rows] == [
        ("drop", "already_on_the_map"),
        ("keep", None),
        ("drop", "no_longer_there"),
        ("drop", "too_little_known"),
    ]
    assert rows[0]["inside"] == "Palais du Louvre"
    assert rows[1] == {
        "qid": "Q1",
        "name": "Tour Montparnasse",
        "kinds": "gratte-ciel",
        "article": "Tour Montparnasse",
        "lat": 48.86,
        "lon": 2.34,
        "views": 80_000,
        "languages": 48,
        "score": pytest.approx((1.0 + 0.75) / 2),
        "suggestion": "keep",
        "why": None,
        "inside": None,
    }
    # An article that nobody read counts for nothing.
    assert rows[3]["views"] == 0
    assert landmarks.summarize(table) == {
        "places": 4,
        "suggested": 1,
        "left_out_already_on_the_map": 1,
        "left_out_no_longer_there": 1,
        "left_out_too_little_known": 1,
    }


def test_places_and_those_that_are_gone_are_asked_to_wikidata() -> None:
    queries: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        query = httpx.QueryParams(request.content.decode())["query"]
        queries.append(query)
        found = ["Q30", "Q4"] if "wdt:P131+" in query else ["Q30"]
        bindings = [{"item": {"value": ENTITY + qid}} for qid in found]
        return httpx.Response(200, json={"results": {"bindings": bindings}})

    pauses: list[float] = []
    with ingest_wikidata.make_client(httpx.MockTransport(answer)) as client:
        qids = landmarks.fetch_places(client, pause=pauses.append)
        gone = landmarks.fetch_gone(client, qids, pause=pauses.append)

    assert qids == ["Q4", "Q30"]
    assert gone == ["Q30"]
    assert f"FILTER(?links >= {landmarks.MIN_LINKS})" in queries[0]
    # Only the notices of protected monuments, which start with PA, rule a place out.
    assert 'FILTER(STRSTARTS(?notice, "PA"))' in queries[0]
    assert "wd:Q4 wd:Q30" in queries[1]
    assert "wdt:P576" in queries[1]


def test_candidates_are_built_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def item(qid: str, name: str, kind: str, links: int, point: str) -> dict[str, str]:
        return {
            "item": ENTITY + qid,
            "label": name,
            "sitelinks": str(links),
            "articleTitle": name,
            "coords": point,
            "types": kind,
        }

    items = [
        item("Q1", "Tour Montparnasse", "gratte-ciel", 48, "Point(2.3219 48.8421)"),
        item("Q2", "Musée du Louvre", "musée d'art", 170, "Point(2.3505 48.8505)"),
        item("Q3", "Bastille", "château fort", 86, "Point(2.3692 48.8533)"),
        # Without an article in French, a place is not a candidate.
        {"item": ENTITY + "Q4", "sitelinks": "60", "coords": "Point(2.33 48.86)"},
    ]
    (tmp_path / "landmarks.json").write_text(
        json.dumps({"items": items, "gone": ["Q3"]})
    )
    views = {"Tour Montparnasse": 80_000, "Musée du Louvre": 900_000, "Bastille": 9000}
    (tmp_path / "views.json").write_text(json.dumps({"views": views}))
    pd.DataFrame(
        [
            {"merimee_id": "PA1", "name": "Palais du Louvre"},
            {"merimee_id": "PA2", "name": "Hôtel d'Aumont"},
        ]
    ).to_parquet(tmp_path / "merimee.parquet")
    gpd.GeoDataFrame(
        {"merimee_id": ["PA1", "PA2"]},
        geometry=[PALACE, box(2.36, 48.85, 2.3601, 48.8501)],
        crs="EPSG:4326",
    ).to_parquet(tmp_path / "geometries.parquet")
    pd.DataFrame(
        [
            {"merimee_id": "PA1", "shown": True, "rank": 1, "views": 60_000},
            {"merimee_id": "PA2", "shown": True, "rank": 2, "views": 2000},
        ]
    ).assign(languages=[120, 8]).to_parquet(tmp_path / "selection.parquet")
    paths = {
        "MERIMEE_PARQUET": tmp_path / "merimee.parquet",
        "GEOMETRIES_PARQUET": tmp_path / "geometries.parquet",
        "SELECTION_PARQUET": tmp_path / "selection.parquet",
        "ITEMS_SNAPSHOT": tmp_path / "landmarks.json",
        "VIEWS_SNAPSHOT": tmp_path / "views.json",
        "CANDIDATES_PARQUET": tmp_path / "candidates.parquet",
        "CANDIDATES_CSV": tmp_path / "candidates.csv",
    }
    for name, path in paths.items():
        monkeypatch.setattr(landmarks, name, path)
    monkeypatch.setattr(selection, "LAST_RANK_SHOWN", 2)

    def no_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("the offline run must not open a connection")

    monkeypatch.setattr(ingest_wikidata, "make_client", no_network)
    monkeypatch.setattr(web, "make_client", no_network)
    assert landmarks.main(["--offline"]) == 0

    listed = pd.read_csv(tmp_path / "candidates.csv")
    assert list(listed["name"]) == ["Musée du Louvre", "Tour Montparnasse", "Bastille"]
    assert list(listed["suggestion"]) == ["drop", "keep", "drop"]
    assert listed.loc[0, "inside"] == "Palais du Louvre"
    assert listed.loc[2, "why"] == "no_longer_there"
    stored = pd.read_parquet(tmp_path / "candidates.parquet")
    assert list(stored["qid"]) == ["Q2", "Q1", "Q3"]
