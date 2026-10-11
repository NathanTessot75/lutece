from pathlib import Path

import pandas as pd
import pytest

from lutece_pipeline import quality_report as report
from lutece_pipeline.quality_report import APPROXIMATE, NOT_READY, READY


def notice(
    merimee_id: str, name: str = "Immeuble", **changes: object
) -> dict[str, object]:
    return {
        "merimee_id": merimee_id,
        "name": name,
        "protection": "inscrit",
        "denominations": ["immeuble"],
        "arrondissement": 4,
        "construction_century": 18,
        "architects": None,
        "history_raw": None,
        **changes,
    }


def quality(*rows: dict[str, object]) -> pd.DataFrame:
    """A quality table with the given monuments, ready ones unless stated."""
    defaults = {
        "name": "Immeuble",
        "arrondissement": 4,
        "category": "immeuble",
        "protection": "inscrit",
        "has_own_name": False,
        "has_wikidata": True,
        "has_frwiki": False,
        "has_century": True,
        "has_architect": False,
        "has_history": False,
        "footprint_source": "osm_footprint",
        "point_doubtful": False,
        "visibility": "visible",
        "photos": 3,
        "readiness": READY,
    }
    return report.from_rows([{**defaults, **row} for row in rows], report.SCHEMA)


@pytest.mark.parametrize(
    ("name", "denominations", "expected"),
    [
        ("Immeuble", ["immeuble"], False),
        ("Immeubles", ["immeuble"], False),
        ("Hôtel (ancien)", ["hôtel"], False),
        ("Ancien hôtel", ["hôtel", "immeuble"], False),
        ("Ancienne maison", ["maison"], False),
        ("Boulangerie", ["magasin de commerce"], False),
        ("Ancienne épicerie", ["magasin de commerce"], False),
        ("Café-Bar", ["café"], False),
        ("immeuble", None, False),
        ("Hôtel de Sully", ["hôtel"], True),
        ("Ancien hôtel de Bondeville", ["hôtel"], True),
        ("Fontaine Molière", ["fontaine"], True),
        ("Pont-Neuf", ["pont"], True),
        ("Sainte-Chapelle", ["chapelle"], True),
        ("Ecole normale supérieure", ["école"], True),
        ("Tour Eiffel", None, True),
    ],
)
def test_name_that_only_repeats_the_kind_of_building_is_not_a_name(
    name: str, denominations: list[str] | None, expected: bool
) -> None:
    assert report.has_own_name(name, denominations) is expected


@pytest.mark.parametrize(
    ("visible", "reason", "footprint_source", "expected"),
    [
        ("visible", "whole_monument", "osm_footprint", READY),
        ("visible", "outside_part", "osm_nearby", READY),
        ("visible", "outside_part", "osm_line", READY),
        ("visible", "whole_monument", "buffer", APPROXIMATE),
        ("visible", "whole_monument", None, APPROXIMATE),
        # Only its courtyard fronts are protected: the school is on its street.
        ("non_visible", "courtyard_only", "osm_footprint", READY),
        ("non_visible", "inside_only", "buffer", APPROXIMATE),
        ("non_visible", "reviewed", "osm_footprint", READY),
        # Under the ground, or placed by nothing: there is no standing in front.
        ("non_visible", "underground", "osm_footprint", NOT_READY),
        ("inconnu", "unplaced_item", "osm_footprint", NOT_READY),
        ("inconnu", None, "osm_footprint", NOT_READY),
    ],
)
def test_readiness(
    visible: str, reason: str | None, footprint_source: str | None, expected: str
) -> None:
    assert report.readiness(visible, reason, footprint_source) == expected


def test_quality_crosses_what_each_step_knows_of_a_monument() -> None:
    notices = [
        notice("PA1", "Hôtel de Sully", denominations=["hôtel"], history_raw="1624."),
        notice("PA2", protection=None),
        notice("PA3", architects=["Jean Bullant"], construction_century=None),
        notice("PA4", denominations=None),
    ]
    entities = [
        {"merimee_id": "PA1", "wikidata_qid": "Q1"},
        {"merimee_id": "PA3", "wikidata_qid": "Q3"},
        {"merimee_id": "PA4", "wikidata_qid": None},
    ]
    items = [
        {
            "qid": "Q1",
            "frwiki_title": "Hôtel de Sully",
            "architects": ["Jean Androuet"],
        },
        {"qid": "Q3", "frwiki_title": None, "architects": None},
    ]
    geometries = [
        {
            "merimee_id": "PA1",
            "footprint_source": "osm_footprint",
            "point_doubtful": False,
        },
        {"merimee_id": "PA3", "footprint_source": "buffer", "point_doubtful": True},
    ]
    visibilities = [
        {"merimee_id": "PA1", "visibility": "visible"},
        {"merimee_id": "PA3", "visibility": "visible"},
        {"merimee_id": "PA4", "visibility": "non_visible", "reason": "underground"},
    ]
    table = report.build_quality(
        notices, entities, items, geometries, visibilities, {"PA1": 15, "PA4": 2}
    )
    assert table.to_dict("records") == [
        {
            "merimee_id": "PA1",
            "name": "Hôtel de Sully",
            "arrondissement": 4,
            "category": "hôtel",
            "protection": "inscrit",
            "has_own_name": True,
            "has_wikidata": True,
            "has_frwiki": True,
            "has_century": True,
            "has_architect": True,
            "has_history": True,
            "footprint_source": "osm_footprint",
            "point_doubtful": False,
            "visibility": "visible",
            "photos": 15,
            "readiness": READY,
        },
        {
            "merimee_id": "PA3",
            "name": "Immeuble",
            "arrondissement": 4,
            "category": "immeuble",
            "protection": "inscrit",
            "has_own_name": False,
            "has_wikidata": True,
            "has_frwiki": False,
            "has_century": False,
            # The architect comes from the notice, Wikidata has none.
            "has_architect": True,
            "has_history": False,
            "footprint_source": "buffer",
            "point_doubtful": True,
            "visibility": "visible",
            "photos": 0,
            "readiness": APPROXIMATE,
        },
        {
            "merimee_id": "PA4",
            "name": "Immeuble",
            "arrondissement": 4,
            "category": None,
            "protection": "inscrit",
            "has_own_name": False,
            "has_wikidata": False,
            "has_frwiki": False,
            "has_century": True,
            "has_architect": False,
            "has_history": False,
            # No geometry was computed for it.
            "footprint_source": None,
            "point_doubtful": False,
            "visibility": "non_visible",
            "photos": 2,
            "readiness": NOT_READY,
        },
    ]


def test_monument_missing_from_the_visibility_table_is_undecided() -> None:
    table = report.build_quality([notice("PA1")], [], [], [], [], {})
    assert table.loc[0, "visibility"] == "inconnu"
    assert table.loc[0, "readiness"] == NOT_READY


def test_problems_are_listed_one_per_monument_and_kind() -> None:
    table = quality(
        {"merimee_id": "PA1"},
        {"merimee_id": "PA2", "has_wikidata": False, "photos": 0},
        {"merimee_id": "PA3", "footprint_source": "buffer", "point_doubtful": True},
        {"merimee_id": "PA4", "visibility": "inconnu", "photos": 0},
        {"merimee_id": "PA5", "visibility": "non_visible", "photos": 0},
        {"merimee_id": "PA6", "footprint_source": None},
    )
    problems = report.find_problems(table)
    assert list(problems.columns) == report.PROBLEM_COLUMNS
    assert sorted(zip(problems["merimee_id"], problems["problem"], strict=True)) == [
        ("PA2", "no_photo"),
        ("PA2", "no_wikidata_item"),
        ("PA3", "doubtful_point"),
        ("PA3", "no_footprint"),
        # Without a photo, but nobody can photograph it from the street anyway.
        ("PA4", "visibility_unknown"),
        ("PA6", "no_footprint"),
    ]
    first = problems.iloc[0]
    assert first["merimee_url"] == "https://pop.culture.gouv.fr/notice/merimee/PA2"
    assert report.find_problems(quality({"merimee_id": "PA1"})).empty


def test_numbers_are_written_the_french_way() -> None:
    assert report.count(1878) == "1 878"
    assert report.count(40295.0) == "40 295"
    assert report.share(1749, 1878) == "1 749 (93 %)"
    assert report.share(0, 0) == "0"
    assert report.table(["A", "B"], [(1, "x"), (2, "y")]) == [
        "| A | B |",
        "|---|---|",
        "| 1 | x |",
        "| 2 | y |",
    ]


def test_coverage_counts_each_piece_of_information() -> None:
    table = quality(
        {"merimee_id": "PA1", "has_frwiki": True, "photos": 5},
        {"merimee_id": "PA2", "footprint_source": "buffer", "photos": 0},
        {"merimee_id": "PA3", "visibility": "non_visible", "has_own_name": True},
        {"merimee_id": "PA4", "has_wikidata": False, "has_century": False},
    )
    assert dict(report.coverage_rows(table)) == {
        "Fiche Wikidata": "3 (75 %)",
        "Contour réel du bâtiment": "3 (75 %)",
        "Visible depuis la rue": "3 (75 %)",
        "Au moins une photo de référence": "3 (75 %)",
        "Au moins 5 photos de référence": "1 (25 %)",
        "Siècle de construction": "3 (75 %)",
        "Article Wikipédia en français": "1 (25 %)",
        "Architecte connu": "0 (0 %)",
        "Historique dans la notice": "0 (0 %)",
        "Nom propre, autre que « Immeuble » ou « Maison »": "1 (25 %)",
    }


def test_groups_are_described_in_the_order_given() -> None:
    table = quality(
        {"merimee_id": "PA1", "arrondissement": 4, "photos": 2, "has_frwiki": True},
        {"merimee_id": "PA2", "arrondissement": 4, "photos": 5},
        {"merimee_id": "PA3", "arrondissement": 1, "readiness": NOT_READY, "photos": 0},
        {"merimee_id": "PA4", "arrondissement": 1, "readiness": APPROXIMATE},
    )
    assert report.group_rows(table, table["arrondissement"]) == [
        ["4", "2", "2 (100 %)", "0", "0", "3,5", "1 (50 %)"],
        ["1", "2", "0 (0 %)", "1", "1", "1,5", "0 (0 %)"],
    ]


def test_reliability_reads_what_the_steps_measured() -> None:
    links = pd.DataFrame(
        {
            "source": ["wikidata", "wikidata", "osm", "osm", "osm"],
            "status": ["confirmed", "doubtful", "confirmed", "confirmed", "rejected"],
        }
    )
    nearby = pd.DataFrame(
        {
            "match": ["contains", "contains", "nearest", None],
            "outcome": ["correct", "wrong", "correct", "none"],
        }
    )
    seen = pd.DataFrame(
        {"sample": ["dev", "test", "test"], "agree": [False, True, False]}
    )
    photos = pd.DataFrame(
        {
            "sample": ["dev", "test", "test", "test", "test"],
            "outcome": [
                "kept_wrongly",
                "kept_rightly",
                "kept_wrongly",
                "rejected_rightly",
                "not_judged",
            ],
        }
    )
    rows = report.reliability_rows(links, nearby, seen, photos)
    assert [(step, result) for step, _, result in rows] == [
        ("Rapprochement avec Wikidata", "1 sur 2"),
        ("Rapprochement avec OpenStreetMap", "2 sur 3"),
        ("Bâtiment trouvé autour du point", "1 sur 2"),
        ("Visibilité depuis la rue", "1 sur 2"),
        ("Photos de référence", "1 sur 2"),
    ]
    # A step that has not been evaluated yet is left out.
    assert len(report.reliability_rows(links, None, None, None)) == 2


def test_report_gives_the_headline_figures() -> None:
    table = quality(
        {"merimee_id": "PA1", "has_frwiki": True},
        {"merimee_id": "PA2", "photos": 0},
        {"merimee_id": "PA3", "readiness": APPROXIMATE, "footprint_source": "buffer"},
        {"merimee_id": "PA4", "readiness": NOT_READY, "visibility": "inconnu"},
    )
    text = report.render_report(
        table,
        report.find_problems(table),
        [("Visibilité depuis la rue", "accord", "98 sur 100")],
        {"Visibilités à trancher": 1},
    )
    assert text.startswith("# Qualité de la base des monuments\n")
    assert "- La base compte **4 monuments** protégés à Paris." in text
    assert "- **2 (50 %) sont prêts pour l'app**" in text
    assert "- 1 (25 %) sont prêts avec réserve" in text
    assert "- 1 (25 %) ne sont pas prêts" in text
    assert "- Parmi les 3 monuments prêts, avec ou sans réserve," in text
    assert "  2 ont au moins une photo de référence et" in text
    assert "| Visibilité depuis la rue | accord | 98 sur 100 |" in text
    assert "| Repéré par un cercle, faute de contour | 1 |" in text
    assert "| Visible depuis la rue mais sans photo | 1 |" in text
    assert "| Sans fiche Wikidata | 0 |" in text
    assert "| Visibilités à trancher | 1 |" in text
    assert text.endswith("|\n")


def test_most_common_kinds_come_first_then_the_others(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(report, "MOST_COMMON_CATEGORIES", 2)
    table = quality(
        {"merimee_id": "PA1", "category": "église"},
        {"merimee_id": "PA2", "category": "hôtel"},
        {"merimee_id": "PA3", "category": "hôtel"},
        {"merimee_id": "PA4", "category": "pont"},
        {"merimee_id": "PA5", "category": "immeuble"},
        {"merimee_id": "PA6", "category": "immeuble"},
        {"merimee_id": "PA7", "category": "immeuble"},
        {"merimee_id": "PA8", "category": None},
    )
    text = report.render_report(table, report.find_problems(table), [], {})
    kinds = text.split("## Par type de monument")[1].split("## Fiabilité")[0]
    rows = [
        line.split(" | ")[0] for line in kinds.splitlines() if line.startswith("| ")
    ]
    assert rows == ["| Type", "| immeuble", "| hôtel", "| autres"]
    assert "| autres | 3 |" in kinds


def run_main(folder: Path, out: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = {
        "MERIMEE_PARQUET": folder / "merimee.parquet",
        "ENTITIES_PARQUET": folder / "entities.parquet",
        "ENTITY_LINKS_PARQUET": folder / "entity_links.parquet",
        "WIKIDATA_ITEMS_PARQUET": folder / "wikidata_items.parquet",
        "GEOMETRIES_PARQUET": folder / "geometries.parquet",
        "VISIBILITY_PARQUET": folder / "visibility.parquet",
        "COMMONS_FILES_PARQUET": folder / "commons_files.parquet",
        "NEARBY_EVALUATION_CSV": out / "nearby_buildings_evaluation.csv",
        "VISIBILITY_EVALUATION_CSV": out / "visibility_evaluation.csv",
        "COMMONS_EVALUATION_CSV": out / "commons_evaluation.csv",
        "QUALITY_PARQUET": out / "processed" / "monuments_quality.parquet",
        "PROBLEMS_CSV": out / "processed" / "quality_problems.csv",
        "REPORT_MD": out / "docs" / "qualite-donnees.md",
    }
    for name, path in paths.items():
        monkeypatch.setattr(report, name, path)
    review = {
        "Rapprochements douteux": out / "entities_to_review.csv",
        "Visibilités à trancher": out / "visibility_to_review.csv",
    }
    monkeypatch.setattr(report, "REVIEW_FILES", review)
    assert report.main([]) == 0


def test_real_notices_are_reported(
    pipeline_tables: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "visibility_to_review.csv").write_text("merimee_id\nPA1\nPA2\n")
    (tmp_path / "visibility_evaluation.csv").write_text(
        "merimee_id,sample,agree\nPA1,test,True\nPA2,test,False\n"
    )
    run_main(pipeline_tables, tmp_path, monkeypatch)

    table = pd.read_parquet(tmp_path / "processed" / "monuments_quality.parquet")
    assert list(table.columns) == report.SCHEMA.names
    # Nine protected notices in the sample; the two others are not monuments.
    assert len(table) == 9
    rows = table.set_index("merimee_id")
    assert rows["has_wikidata"].all()
    church = rows.loc["PA00085795"]
    assert church["category"] == "église"
    assert church["has_frwiki"]
    assert church["readiness"] == READY
    assert church["photos"] >= 5
    # Only the inside of the café is protected: it is on its street all the
    # same, marked by a circle for want of a footprint.
    assert rows.loc["PA00085786", "visibility"] == "non_visible"
    assert rows.loc["PA00085786", "readiness"] == APPROXIMATE
    # A metro entrance is a point in OpenStreetMap: a circle stands for it.
    assert rows.loc["PA00086579", "footprint_source"] == "buffer"
    assert rows.loc["PA00086579", "readiness"] == APPROXIMATE
    assert not rows.loc["PA00085786", "has_own_name"]

    problems = pd.read_csv(tmp_path / "processed" / "quality_problems.csv")
    assert set(problems["problem"]) <= set(report.PROBLEMS)
    assert "PA00086579" in set(
        problems.loc[problems["problem"] == "no_footprint", "merimee_id"]
    )

    text = (tmp_path / "docs" / "qualite-donnees.md").read_text()
    assert "- La base compte **9 monuments** protégés à Paris." in text
    assert (
        "| Visibilité depuis la rue | accord avec l'étiquette posée à la main, lot de test | 1 sur 2 |"
        in text
    )
    # A review file that does not exist is left out, the other is counted.
    assert "| Visibilités à trancher | 2 |" in text
    assert "Rapprochements douteux" not in text
    assert "Photos de référence |" not in text
