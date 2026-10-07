import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from lutece_pipeline import ingest_merimee as merimee
from lutece_pipeline import ingest_osm as osm
from lutece_pipeline import ingest_wikidata as wikidata
from lutece_pipeline import resolve_entities as resolve
from lutece_pipeline.tables import to_records, write_parquet

FIXTURES = Path(__file__).parent / "fixtures"

type Pair = dict[str, Any]


def pair(
    merimee_id: str = "PA1", source: str = "wikidata", **overrides: object
) -> Pair:
    """A measured pair with neutral evidence, to be adjusted by each test."""
    entity_id = "Q1" if source == "wikidata" else "way/1"
    is_osm = source == "osm"
    base: Pair = {
        "merimee_id": merimee_id,
        "source": source,
        "entity_id": entity_id,
        "entity_name": None,
        "distance_m": None,
        "name_similarity": None,
        "address_match": False,
        "via_ref_mhs": False if is_osm else None,
        "via_wikidata": True if is_osm else None,
        "is_footprint": True if is_osm else None,
        "area_m2": 100.0 if is_osm else None,
        "sitelinks": 0,
    }
    return base | overrides


def resolved(
    pairs: list[Pair], decisions: dict[tuple[str, str], str] | None = None
) -> list[Pair]:
    resolve.apply_decisions(pairs, decisions or {})
    resolve.choose_primaries(pairs)
    return pairs


def primary_of(pairs: list[Pair], source: str = "wikidata") -> str | None:
    chosen = [
        item["entity_id"]
        for item in pairs
        if item["is_primary"] and item["source"] == source
    ]
    assert len(chosen) <= 1
    return chosen[0] if chosen else None


def notice(merimee_id: str = "PA1", **overrides: object) -> dict[str, Any]:
    base = {
        "merimee_id": merimee_id,
        "name": "Immeuble",
        "address": None,
        "arrondissement": 1,
    }
    return base | overrides


@pytest.fixture(scope="module")
def fixture_tables(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The three ingestion outputs, built from the real fixture answers."""
    folder = tmp_path_factory.mktemp("interim")
    notices = merimee.normalize(
        merimee.read_paris_notices(FIXTURES / "merimee_sample.csv")
    )
    write_parquet(notices, merimee.OUTPUT_SCHEMA, folder / "merimee.parquet")
    snapshot = json.loads((FIXTURES / "wikidata_snapshot.json").read_text())
    wikidata_links = wikidata.build_links(snapshot["links"])
    items = wikidata.build_items(snapshot["items"])
    write_parquet(items, wikidata.ITEMS_SCHEMA, folder / "wikidata_items.parquet")
    write_parquet(
        wikidata_links, wikidata.LINKS_SCHEMA, folder / "wikidata_links.parquet"
    )
    elements = json.loads((FIXTURES / "osm_snapshot.json").read_text())["elements"]
    osm_links = osm.build_links(
        elements, set(notices["merimee_id"]), osm.notices_by_item(wikidata_links)
    )
    write_parquet(osm_links, osm.LINKS_SCHEMA, folder / "osm_links.parquet")
    osm.build_objects(elements).to_parquet(folder / "osm_objects.parquet", index=False)
    return folder


def run_main(
    folder: Path, out: Path, monkeypatch: pytest.MonkeyPatch, decisions: str = ""
) -> None:
    decisions_csv = out / "entity_decisions.csv"
    out.mkdir(exist_ok=True)
    if decisions:
        decisions_csv.write_text(
            "merimee_id,source,entity_id,decision,note\n" + decisions
        )
    monkeypatch.setattr(resolve, "MERIMEE_PARQUET", folder / "merimee.parquet")
    monkeypatch.setattr(
        resolve, "WIKIDATA_ITEMS_PARQUET", folder / "wikidata_items.parquet"
    )
    monkeypatch.setattr(
        resolve, "WIKIDATA_LINKS_PARQUET", folder / "wikidata_links.parquet"
    )
    monkeypatch.setattr(resolve, "OSM_OBJECTS_PARQUET", folder / "osm_objects.parquet")
    monkeypatch.setattr(resolve, "OSM_LINKS_PARQUET", folder / "osm_links.parquet")
    monkeypatch.setattr(resolve, "DECISIONS_CSV", decisions_csv)
    monkeypatch.setattr(resolve, "LINKS_PARQUET", out / "entity_links.parquet")
    monkeypatch.setattr(resolve, "ENTITIES_PARQUET", out / "entities.parquet")
    monkeypatch.setattr(resolve, "REVIEW_CSV", out / "entities_to_review.csv")
    assert resolve.main([]) == 0


def test_normalize_name_strips_case_accents_and_small_words() -> None:
    assert (
        resolve.normalize_name("Ancien Hôtel de l'Œuvre, Paris") == "hotel oeuvre paris"
    )
    assert resolve.normalize_name(None) == ""


def test_same_name_scores_100_whatever_the_writing() -> None:
    assert (
        resolve.name_similarity("Église Saint-Eustache", "eglise saint eustache") == 100
    )
    assert (
        resolve.name_similarity("Monument à la République", "monument de la République")
        == 100
    )


def test_a_name_contained_in_another_does_not_score_high() -> None:
    # Many mansions stand on the place Vendôme and share its Wikidata item.
    score = resolve.name_similarity("Ancien hôtel Bataille de Francès", "Place Vendôme")
    assert score is not None
    assert score < 50
    partial = resolve.name_similarity("Métropolitain, station Nation", "Nation")
    assert partial is not None
    assert partial < resolve.SAME_NAME_SCORE


def test_name_similarity_is_unknown_without_a_name() -> None:
    assert resolve.name_similarity("Immeuble", None) is None
    assert resolve.name_similarity("de la", "Immeuble") is None


@pytest.mark.parametrize(
    ("address", "name", "expected"),
    [
        ("5 rue de Condé", "immeuble, 5 rue de Condé", True),
        (
            "31, 33 rue des Francs-Bourgeois",
            "enceinte, 31-33 rue des Francs-Bourgeois",
            True,
        ),
        ("Geoffroy-l'Asnier (rue) 28", "hôtel du 28 rue Geoffroy-l'Asnier", True),
        ("6 rue Blanche ; 8 rue Verte", "immeuble, 8 rue Verte", True),
        ("4 rue d'Aboukir", "immeuble, 14 rue d'Aboukir", False),
        (
            "rue de Vaugirard",
            "palais du Luxembourg, rue de Vaugirard",
            False,
        ),  # no number
        ("5 rue de Condé", None, False),
        (None, "immeuble, 5 rue de Condé", False),
    ],
)
def test_address_matches(address: str | None, name: str | None, expected: bool) -> None:
    assert resolve.address_matches(address, name) is expected


@pytest.mark.parametrize(
    ("source", "evidence", "expected"),
    [
        ("wikidata", {"distance_m": 80.0}, "confirmed"),
        ("osm", {"distance_m": 80.0}, "doubtful"),  # footprints must be closer
        ("osm", {"distance_m": 0.0}, "confirmed"),
        ("wikidata", {"distance_m": 900.0, "name_similarity": 95.0}, "confirmed"),
        ("wikidata", {"distance_m": 900.0, "name_similarity": 60.0}, "doubtful"),
        ("wikidata", {"distance_m": 900.0, "address_match": True}, "confirmed"),
        ("wikidata", {}, "doubtful"),  # nothing to go by
    ],
)
def test_initial_status(
    source: str, evidence: dict[str, object], expected: str
) -> None:
    assert resolve.initial_status(pair(source=source, **evidence)) == expected


def test_best_named_item_is_primary_even_when_it_is_not_the_closest() -> None:
    cemetery = pair(entity_id="Q311", distance_m=60.0, name_similarity=90.0)
    tomb = pair(entity_id="Q999", distance_m=5.0, name_similarity=20.0)
    assert primary_of(resolved([tomb, cemetery])) == "Q311"


def test_confirmed_item_outranks_a_doubtful_one_with_a_better_name() -> None:
    near = pair(entity_id="Q1", distance_m=10.0, name_similarity=40.0)
    far = pair(entity_id="Q2", distance_m=900.0, name_similarity=70.0)
    assert primary_of(resolved([far, near])) == "Q1"


def test_equal_items_are_ranked_by_distance_then_notoriety() -> None:
    first = pair(entity_id="Q20", distance_m=10.0, name_similarity=100.0, sitelinks=1)
    famous = pair(entity_id="Q10", distance_m=10.0, name_similarity=100.0, sitelinks=9)
    farther = pair(entity_id="Q5", distance_m=30.0, name_similarity=100.0, sitelinks=50)
    assert primary_of(resolved([first, farther, famous])) == "Q10"


def test_footprint_tagged_with_the_reference_is_preferred() -> None:
    tagged = pair(source="osm", entity_id="way/2", distance_m=20.0, via_ref_mhs=True)
    closer = pair(source="osm", entity_id="way/1", distance_m=0.0)
    assert primary_of(resolved([closer, tagged]), "osm") == "way/2"


def test_objects_that_are_not_footprints_are_never_primary() -> None:
    node = pair(
        source="osm",
        entity_id="node/1",
        distance_m=0.0,
        is_footprint=False,
        area_m2=0.0,
    )
    assert primary_of(resolved([node]), "osm") is None


def test_rejected_pair_is_left_out() -> None:
    wrong = pair(entity_id="Q1", distance_m=10.0)
    right = pair(entity_id="Q2", distance_m=40.0)
    pairs = resolved([wrong, right], {("PA1", "Q1"): "reject"})
    assert wrong["status"] == "rejected"
    assert wrong["reviewed"] is True
    assert primary_of(pairs) == "Q2"


def test_accepted_pair_is_confirmed_despite_the_distance() -> None:
    moved = pair(distance_m=5000.0)
    resolved([moved], {("PA1", "Q1"): "accept"})
    assert moved["status"] == "confirmed"
    assert moved["reviewed"] is True


def test_reviewer_can_force_the_primary_even_for_a_non_footprint() -> None:
    tomb = pair(source="osm", entity_id="way/1", distance_m=0.0)
    cemetery = pair(
        source="osm",
        entity_id="relation/9",
        distance_m=0.0,
        is_footprint=False,
        area_m2=4e5,
    )
    pairs = resolved([tomb, cemetery], {("PA1", "relation/9"): "primary"})
    assert primary_of(pairs, "osm") == "relation/9"


def test_stale_decisions_are_reported(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger=resolve.logger.name):
        resolved([pair()], {("PA1", "Q404"): "reject"})
    assert "Q404" in caplog.text


def test_read_decisions(tmp_path: Path) -> None:
    path = tmp_path / "decisions.csv"
    assert resolve.read_decisions(path) == {}
    path.write_text(
        "merimee_id,source,entity_id,decision,note\n"
        'PA1,wikidata,Q1,accept,"moved, same building"\n'
        "PA1,osm,way/7,reject,\n"
    )
    assert resolve.read_decisions(path) == {
        ("PA1", "Q1"): "accept",
        ("PA1", "way/7"): "reject",
    }


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ("PA1,wikidata,Q1,maybe,\n", "unknown decision 'maybe'"),
        ("PA1,wikidata,Q1,accept,\nPA1,wikidata,Q1,reject,\n", "decided twice"),
    ],
)
def test_invalid_decisions_are_refused(tmp_path: Path, rows: str, message: str) -> None:
    path = tmp_path / "decisions.csv"
    path.write_text("merimee_id,source,entity_id,decision,note\n" + rows)
    with pytest.raises(ValueError, match=message):
        resolve.read_decisions(path)


def test_entities_summarize_what_is_kept() -> None:
    pairs = resolved(
        [
            pair(entity_id="Q1", distance_m=10.0),
            pair(entity_id="Q2", distance_m=20.0),
            pair(source="osm", entity_id="way/1", distance_m=0.0),
            pair(source="osm", entity_id="node/5", distance_m=0.0, is_footprint=False),
        ],
        {("PA1", "Q2"): "reject"},
    )
    entities = resolve.build_entities([notice("PA1"), notice("PA2")], pairs)
    assert entities.to_dict("records") == [
        {
            "merimee_id": "PA1",
            "wikidata_qid": "Q1",
            "wikidata_status": "confirmed",
            "wikidata_count": 1,
            "osm_footprint": "way/1",
            "osm_status": "confirmed",
            "osm_footprint_count": 1,
            "osm_object_count": 2,
        },
        {
            "merimee_id": "PA2",
            "wikidata_qid": None,
            "wikidata_status": None,
            "wikidata_count": 0,
            "osm_footprint": None,
            "osm_status": None,
            "osm_footprint_count": 0,
            "osm_object_count": 0,
        },
    ]


def test_review_lists_doubtful_choices_and_missing_items() -> None:
    notices = [notice("PA1"), notice("PA2"), notice("PA3"), notice("PA4")]
    pairs = resolved(
        [
            pair("PA1", entity_id="Q1", distance_m=10.0),
            pair("PA2", entity_id="Q2", distance_m=900.0, entity_name="ailleurs"),
            pair("PA3", entity_id="Q3", distance_m=10.0),
        ],
        {("PA3", "Q3"): "reject"},
    )
    review = resolve.build_review(notices, pairs)
    assert list(review.columns) == resolve.REVIEW_COLUMNS
    assert review["merimee_id"].tolist() == ["PA2", "PA3", "PA4"]
    assert review["reason"].tolist() == [
        "main wikidata choice is doubtful",
        "no wikidata item",
        "no wikidata item",
    ]
    assert review["entity_id"].isna().tolist() == [False, True, True]
    doubtful = review.iloc[0]
    assert doubtful["distance_m"] == 900
    assert doubtful["merimee_url"] == "https://pop.culture.gouv.fr/notice/merimee/PA2"
    assert doubtful["entity_url"] == "https://www.wikidata.org/wiki/Q2"


def test_measures_on_real_records(fixture_tables: Path) -> None:
    notices = to_records(pd.read_parquet(fixture_tables / "merimee.parquet"))
    items = to_records(pd.read_parquet(fixture_tables / "wikidata_items.parquet"))
    links = to_records(pd.read_parquet(fixture_tables / "wikidata_links.parquet"))
    pairs = {
        (item["merimee_id"], item["entity_id"]): item
        for item in resolve.measure_wikidata_pairs(notices, items, links)
    }
    # A wrong link found in Wikidata: a building of the 14th tied to a mansion of the 4th.
    wrong = pairs["PA00086620", "Q15950844"]
    assert wrong["distance_m"] == pytest.approx(2447, abs=5)
    assert resolve.initial_status(wrong) == "doubtful"
    # An anonymous café whose Wikidata label repeats its address.
    cafe = pairs["PA00085786", "Q22920960"]
    assert cafe["address_match"] is True
    # The temple has no usable Mérimée point, hence no distance.
    assert pairs["PA75110005", "Q3517708"]["distance_m"] is None


def test_run_on_real_tables(
    fixture_tables: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_main(fixture_tables, tmp_path, monkeypatch)

    links = pd.read_parquet(tmp_path / "entity_links.parquet")
    assert list(links.columns) == resolve.LINKS_SCHEMA.names
    assert len(links) == 24

    entities = pd.read_parquet(tmp_path / "entities.parquet").set_index("merimee_id")
    assert len(entities) == 11
    church = entities.loc["PA00085795"]
    assert (church["wikidata_qid"], church["wikidata_status"]) == (
        "Q1338207",
        "confirmed",
    )
    assert (church["osm_footprint"], church["osm_status"]) == (
        "way/53762963",
        "confirmed",
    )
    assert entities.loc["PA00086620", "wikidata_status"] == "doubtful"
    # The canal is only mapped as lines and a node: no footprint.
    assert pd.isna(entities.loc["PA00125441", "osm_footprint"])
    assert entities.loc["PA00125441", "osm_object_count"] == 2

    review = pd.read_csv(tmp_path / "entities_to_review.csv")
    assert sorted(zip(review["merimee_id"], review["source"], strict=True)) == [
        ("PA00086579", "wikidata"),
        ("PA00086620", "wikidata"),
        ("PA75110005", "osm"),
        ("PA75110005", "wikidata"),
    ]


def test_run_applies_the_recorded_decisions(
    fixture_tables: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    decisions = (
        "PA00086620,wikidata,Q15950844,reject,other building\n"
        "PA75110005,wikidata,Q3517708,accept,same temple\n"
        "PA75110005,osm,way/63648393,accept,same temple\n"
        "PA00086579,wikidata,Q1418711,accept,same station\n"
    )
    run_main(fixture_tables, tmp_path, monkeypatch, decisions)

    entities = pd.read_parquet(tmp_path / "entities.parquet").set_index("merimee_id")
    assert pd.isna(entities.loc["PA00086620", "wikidata_qid"])
    assert entities.loc["PA75110005", "wikidata_status"] == "confirmed"
    assert entities.loc["PA75110005", "osm_status"] == "confirmed"

    links = pd.read_parquet(tmp_path / "entity_links.parquet")
    assert int(links["reviewed"].sum()) == 4
    assert int((links["status"] == "rejected").sum()) == 1

    review = pd.read_csv(tmp_path / "entities_to_review.csv")
    assert review[["merimee_id", "reason"]].to_dict("records") == [
        {"merimee_id": "PA00086620", "reason": "no wikidata item"}
    ]
