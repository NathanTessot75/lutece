from pathlib import Path

import pytest

from lutece_pipeline import short_titles as step
from lutece_pipeline.short_titles import Row


def test_a_wikipedia_title_loses_its_brackets_and_its_city() -> None:
    assert step.propose("Musée Picasso", "Musée Picasso (Paris)", None, False) == (
        "Musée Picasso",
        step.WIKIPEDIA,
    )
    assert step.propose("Église", "Église Saint-Roch de Paris", None, False) == (
        "Église Saint-Roch",
        step.WIKIPEDIA,
    )


def test_a_name_made_of_the_city_keeps_it() -> None:
    assert step.without_city("Théâtre de Paris") == "Théâtre de Paris"
    assert (
        step.without_city("Cathédrale Notre-Dame de Paris") == "Cathédrale Notre-Dame"
    )


def test_a_shared_article_gives_way_to_the_wikidata_label() -> None:
    proposal = step.propose(
        "Hôtel du Petit-Sully", "Hôtel de Sully", "hôtel de Sully", True
    )
    assert proposal == ("Hôtel de Sully", step.WIKIDATA)


def test_without_article_nor_label_the_notice_is_cut() -> None:
    long = "Hôtel de Noirmoutier ou de Sens, actuellement résidence du préfet de région"
    assert step.propose(long, None, None, False) == (
        "Hôtel de Noirmoutier",
        step.NOTICE,
    )
    assert step.cut_notice("Ancienne gare d'Orsay, actuellement musée d'Orsay") == (
        "Ancienne gare d'Orsay"
    )
    vivienne = "Galerie Vivienne, anciennement appelée galerie Marchoux"
    assert step.cut_notice(vivienne) == "Galerie Vivienne"
    assert step.cut_notice("Bourse") == "Bourse"


def test_proposals_cover_the_monuments_shown_and_the_places() -> None:
    rows = step.build_proposals(
        chosen=[
            {"merimee_id": "PA2", "shown": True, "article": "Hôtel de Sully"},
            {"merimee_id": "PA1", "shown": True, "article": "Hôtel de Sully"},
            {"merimee_id": "PA3", "shown": True, "article": "Galerie Vivienne"},
            {"merimee_id": "PA4", "shown": False, "article": "Bourse de Paris"},
        ],
        notices=[
            {"merimee_id": "PA1", "name": "Hôtel Béthune-Sully"},
            {"merimee_id": "PA2", "name": "Hôtel du Petit-Sully"},
            {
                "merimee_id": "PA3",
                "name": "Galerie Vivienne, anciennement galerie Marchoux",
            },
        ],
        entities=[{"merimee_id": "PA1", "wikidata_qid": "Q1"}],
        items=[{"qid": "Q1", "label_fr": "hôtel de Sully"}],
        places=[
            {
                "qid": "Q323767",
                "title": "Tour Montparnasse",
                "article": "Tour Montparnasse",
            }
        ],
    )
    assert [(row.key, row.proposal, row.rule) for row in rows] == [
        ("PA1", "Hôtel de Sully", step.WIKIDATA),
        ("PA2", "Hôtel du Petit-Sully", step.NOTICE),
        ("PA3", "Galerie Vivienne", step.WIKIPEDIA),
        ("Q323767", "Tour Montparnasse", step.LANDMARK),
    ]
    assert all(row.short_title == row.proposal for row in rows)


def row(key: str, proposal: str, short_title: str | None = None) -> Row:
    return Row(
        key, f"Notice {key}", "", proposal, step.WIKIPEDIA, short_title or proposal
    )


def test_merge_keeps_the_names_of_the_review_only() -> None:
    reviewed = {"PA1": row("PA1", "Ancien", "Panthéon"), "PA9": row("PA9", "Parti")}
    merged = step.merge([row("PA1", "Nouveau"), row("PA2", "Neuf")], reviewed)
    assert [(one.key, one.proposal, one.short_title) for one in merged] == [
        ("PA1", "Nouveau", "Panthéon"),
        ("PA2", "Neuf", "Neuf"),
    ]


def test_the_review_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "short_titles.csv"
    step.write_review(path, [row("PA1", "Panthéon", " Panthéon ")])
    assert step.read_short_titles(path) == {"PA1": "Panthéon"}
    assert step.read_review(tmp_path / "missing.csv") == {}


def test_the_review_refuses_a_key_twice_or_an_empty_name(tmp_path: Path) -> None:
    path = tmp_path / "short_titles.csv"
    step.write_review(path, [row("PA1", "Panthéon"), row("PA1", "Panthéon")])
    with pytest.raises(ValueError, match="twice"):
        step.read_review(path)
    step.write_review(path, [row("PA1", "Panthéon", " ")])
    with pytest.raises(ValueError, match="no short title"):
        step.read_review(path)
