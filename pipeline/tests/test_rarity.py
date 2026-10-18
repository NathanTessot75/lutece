from pathlib import Path

import pandas as pd
import pytest

from lutece_pipeline import rarity
from lutece_pipeline.tables import to_records


def known(key: str, views: int | None, languages: int | None) -> dict[str, object]:
    return {"key": key, "name": f"Lieu {key}", "views": views, "languages": languages}


def test_tiers_share_out_the_places_in_the_proportions_decided() -> None:
    assert rarity.tier_sizes(394) == [158, 118, 79, 39]
    assert rarity.tier_sizes(10) == [4, 3, 2, 1]
    # The last tier takes what rounding leaves.
    assert sum(rarity.tier_sizes(7)) == 7
    assert rarity.tier_sizes(0) == [0, 0, 0, 0]


def test_the_least_known_places_are_the_rarest() -> None:
    places = [known(f"P{n}", views=100 * n, languages=n) for n in range(1, 11)]
    rated = to_records(rarity.rate(places))
    # The best known first.
    assert [row["key"] for row in rated] == [f"P{n}" for n in range(10, 0, -1)]
    assert [row["rank"] for row in rated] == list(range(1, 11))
    assert [row["rarity_tier"] for row in rated] == [
        *["commun"] * 4,
        *["peu_commun"] * 3,
        *["rare"] * 2,
        "légendaire",
    ]
    assert rated[0]["notoriety"] == pytest.approx(1.0)
    assert rated[-1]["rarity_score"] == pytest.approx(0.9)
    assert all(
        row["rarity_score"] == pytest.approx(1 - row["notoriety"]) for row in rated
    )


def test_readings_and_languages_weigh_the_same() -> None:
    # Read a lot in one language, or little in many: as known as each other,
    # and both better known than a place read little in one language.
    rated = to_records(
        rarity.rate(
            [
                known("Q3", views=50, languages=1),
                known("Q1", views=9000, languages=1),
                known("Q2", views=50, languages=40),
            ]
        )
    )
    assert rated[0]["notoriety"] == rated[1]["notoriety"]
    # Places that tie are told apart by their key.
    assert [row["key"] for row in rated] == ["Q1", "Q2", "Q3"]


def test_a_place_without_measures_is_the_least_known() -> None:
    rated = to_records(
        rarity.rate([known("Q1", views=None, languages=None), known("Q2", 10, 1)])
    )
    assert [row["key"] for row in rated] == ["Q2", "Q1"]


def test_shown_monuments_and_kept_places_are_rated_together() -> None:
    chosen = [
        {"merimee_id": "PA1", "shown": True, "views": 900, "languages": 12},
        {"merimee_id": "PA2", "shown": False, "views": 5, "languages": 1},
    ]
    notices = [
        {"merimee_id": "PA1", "name": "Hôtel de Sens"},
        {"merimee_id": "PA2", "name": "Immeuble"},
    ]
    places = [
        {"qid": "Q323767", "title": "Tour Montparnasse", "views": 9000, "languages": 48}
    ]
    assert rarity.gather(chosen, notices, places) == [
        {"key": "PA1", "name": "Hôtel de Sens", "views": 900, "languages": 12},
        {"key": "Q323767", "name": "Tour Montparnasse", "views": 9000, "languages": 48},
    ]


def test_rarity_is_written_with_its_ranking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pd.DataFrame(
        [
            {"merimee_id": f"PA{n}", "shown": True, "views": 10 * n, "languages": n}
            for n in range(1, 10)
        ]
    ).to_parquet(tmp_path / "selection.parquet", index=False)
    pd.DataFrame(
        [{"merimee_id": f"PA{n}", "name": f"Église {n}"} for n in range(1, 10)]
    ).to_parquet(tmp_path / "merimee.parquet", index=False)
    pd.DataFrame(
        [{"qid": "Q1", "title": "Tour", "views": 10_000, "languages": 99}]
    ).to_parquet(tmp_path / "landmarks.parquet", index=False)
    for name, path in {
        "SELECTION_PARQUET": tmp_path / "selection.parquet",
        "MERIMEE_PARQUET": tmp_path / "merimee.parquet",
        "LANDMARKS_PARQUET": tmp_path / "landmarks.parquet",
        "RARITY_PARQUET": tmp_path / "out" / "rarity.parquet",
        "RANKING_CSV": tmp_path / "out" / "rarity_ranking.csv",
    }.items():
        monkeypatch.setattr(rarity, name, path)

    assert rarity.main([]) == 0
    rated = pd.read_parquet(tmp_path / "out" / "rarity.parquet")
    assert len(rated) == 10
    assert rated.iloc[0]["key"] == "Q1"
    assert rated.iloc[-1]["key"] == "PA1"
    assert rated["rarity_tier"].value_counts().to_dict() == {
        "commun": 4,
        "peu_commun": 3,
        "rare": 2,
        "légendaire": 1,
    }
    ranking = pd.read_csv(tmp_path / "out" / "rarity_ranking.csv")
    assert ranking["name"].tolist()[:2] == ["Tour", "Église 9"]
