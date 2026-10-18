from pathlib import Path

import pandas as pd
import pytest

from lutece_pipeline import series as series_step
from lutece_pipeline.series import Series

HEADER = "slug,name,description,categories,arrondissements\n"
OVERRIDES_HEADER = "slug,key,name,decision,note\n"


def place(key: str, category: str | None, arrondissement: int = 1) -> dict[str, object]:
    return {
        "key": key,
        "name": f"Lieu {key}",
        "category": category,
        "arrondissement": arrondissement,
    }


def one(slug: str, kinds: set[str], arrondissements: set[int] | None = None) -> Series:
    return Series(
        slug,
        slug.capitalize(),
        "Une série.",
        frozenset(kinds),
        None if arrondissements is None else frozenset(arrondissements),
    )


def no_overrides(*slugs: str) -> dict[str, dict[str, set[str]]]:
    return {slug: {"add": set(), "remove": set()} for slug in slugs}


def test_series_are_read_in_the_order_given(tmp_path: Path) -> None:
    path = tmp_path / "series.csv"
    path.write_text(
        HEADER
        + "ponts,Ponts,Les ponts.,pont; passerelle ,\n"
        + 'marais,Hôtels du Marais,"Dans le 3e, le 4e.",hôtel,3;4\n',
        encoding="utf-8",
    )
    assert series_step.read_series(path) == [
        Series("ponts", "Ponts", "Les ponts.", frozenset({"pont", "passerelle"}), None),
        Series(
            "marais",
            "Hôtels du Marais",
            "Dans le 3e, le 4e.",
            frozenset({"hôtel"}),
            frozenset({3, 4}),
        ),
    ]


@pytest.mark.parametrize(
    ("line", "message"),
    [
        ("Ponts,Ponts,Les ponts.,pont,", "not a slug"),
        ("ponts,,Les ponts.,pont,", "name and a description"),
        ("ponts,Ponts,Les ponts.,,", "no kind"),
        ("ponts,Ponts,Les ponts.,pont,21", "not arrondissements"),
    ],
)
def test_a_wrong_description_is_refused(
    tmp_path: Path, line: str, message: str
) -> None:
    path = tmp_path / "series.csv"
    path.write_text(HEADER + line + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        series_step.read_series(path)


def test_a_series_is_described_once(tmp_path: Path) -> None:
    path = tmp_path / "series.csv"
    path.write_text(
        HEADER + "ponts,Ponts,A.,pont,\nponts,Ponts,B.,pont,\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="appears twice"):
        series_step.read_series(path)


def test_overrides_are_read_and_checked(tmp_path: Path) -> None:
    path = tmp_path / "overrides.csv"
    path.write_text(
        OVERRIDES_HEADER
        + "couvents,PA1,Temple,remove,\ncultes,PA1,Temple,add,Un temple.\n",
        encoding="utf-8",
    )
    overrides = series_step.read_overrides(
        path, frozenset({"couvents", "cultes", "ponts"})
    )
    assert overrides == {
        "couvents": {"add": set(), "remove": {"PA1"}},
        "cultes": {"add": {"PA1"}, "remove": set()},
        "ponts": {"add": set(), "remove": set()},
    }
    path.write_text(OVERRIDES_HEADER + "gares,PA1,Gare,add,\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no series"):
        series_step.read_overrides(path, frozenset({"ponts"}))
    path.write_text(OVERRIDES_HEADER + "ponts,PA1,Pont,keep,\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown decision"):
        series_step.read_overrides(path, frozenset({"ponts"}))


def test_a_series_takes_the_places_of_its_kinds() -> None:
    places = [
        place("PA1", "pont"),
        place("PA2", "passerelle"),
        place("PA3", "église"),
        place("Q1", None),
    ]
    members = series_step.assign(places, [one("ponts", {"pont", "passerelle"})], {})
    assert members == [{"slug": "ponts", "key": "PA1"}, {"slug": "ponts", "key": "PA2"}]


def test_a_series_may_keep_to_some_arrondissements() -> None:
    places = [
        place("PA1", "hôtel", 3),
        place("PA2", "hôtel", 7),
        place("PA3", "hôtel", 4),
    ]
    series = [one("hotels", {"hôtel"}), one("marais", {"hôtel"}, {3, 4})]
    members = series_step.assign(places, series, no_overrides("hotels", "marais"))
    # A place may be in several series.
    assert [(member["slug"], member["key"]) for member in members] == [
        ("hotels", "PA1"),
        ("hotels", "PA2"),
        ("hotels", "PA3"),
        ("marais", "PA1"),
        ("marais", "PA3"),
    ]


def test_a_review_moves_a_place_its_kind_ranks_wrongly() -> None:
    places = [
        place("PA1", "couvent"),
        place("PA2", "couvent"),
        place("PA3", "synagogue"),
    ]
    series = [one("couvents", {"couvent"}), one("cultes", {"synagogue"})]
    overrides = {
        "couvents": {"add": set(), "remove": {"PA2"}},
        "cultes": {"add": {"PA2"}, "remove": set()},
    }
    members = series_step.assign(places, series, overrides)
    assert [(member["slug"], member["key"]) for member in members] == [
        ("couvents", "PA1"),
        ("cultes", "PA2"),
        ("cultes", "PA3"),
    ]


def test_places_shown_and_kept_are_gathered_with_their_kind() -> None:
    chosen = [
        {"merimee_id": "PA2", "shown": True},
        {"merimee_id": "PA1", "shown": False},
    ]
    notices = [
        {
            "merimee_id": "PA2",
            "name": "Pont-Neuf",
            "denominations": ["pont", "quai"],
            "arrondissement": 1,
        },
        {
            "merimee_id": "PA1",
            "name": "Immeuble",
            "denominations": ["immeuble"],
            "arrondissement": 2,
        },
    ]
    landmarks = [
        {"qid": "Q90", "title": "Moulin Rouge", "kind": "cabaret", "arrondissement": 18}
    ]
    assert series_step.gather(chosen, notices, landmarks) == [
        {"key": "PA2", "name": "Pont-Neuf", "category": "pont", "arrondissement": 1},
        {
            "key": "Q90",
            "name": "Moulin Rouge",
            "category": "cabaret",
            "arrondissement": 18,
        },
    ]


def test_the_review_lists_first_the_places_in_no_series() -> None:
    places = [place("PA1", "pont"), place("PA2", "immeuble")]
    series = [one("ponts", {"pont"})]
    members = series_step.assign(places, series, no_overrides("ponts"))
    review = series_step.build_review(places, series, members)
    assert review["key"].tolist() == ["PA2", "PA1"]
    assert review["series"].tolist() == ["", "Ponts"]


def test_series_and_members_are_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pd.DataFrame(
        [{"merimee_id": "PA1", "shown": True}, {"merimee_id": "PA2", "shown": True}]
    ).to_parquet(tmp_path / "selection.parquet", index=False)
    pd.DataFrame(
        [
            {
                "merimee_id": "PA1",
                "name": "Pont-Neuf",
                "denominations": ["pont"],
                "arrondissement": 1,
            },
            {
                "merimee_id": "PA2",
                "name": "Immeuble",
                "denominations": ["immeuble"],
                "arrondissement": 2,
            },
        ]
    ).to_parquet(tmp_path / "merimee.parquet", index=False)
    (tmp_path / "series.csv").write_text(
        HEADER + "ponts,Ponts,Les ponts.,pont,\ngares,Gares,Les gares.,gare,\n",
        encoding="utf-8",
    )
    for name, path in {
        "SELECTION_PARQUET": tmp_path / "selection.parquet",
        "MERIMEE_PARQUET": tmp_path / "merimee.parquet",
        "LANDMARKS_PARQUET": tmp_path / "landmarks.parquet",
        "SERIES_CSV": tmp_path / "series.csv",
        "OVERRIDES_CSV": tmp_path / "series_overrides.csv",
        "SERIES_PARQUET": tmp_path / "out" / "series.parquet",
        "MEMBERS_PARQUET": tmp_path / "out" / "series_members.parquet",
        "REVIEW_CSV": tmp_path / "out" / "series_review.csv",
    }.items():
        monkeypatch.setattr(series_step, name, path)

    assert series_step.main([]) == 0
    written = pd.read_parquet(tmp_path / "out" / "series.parquet")
    assert written[["slug", "position"]].values.tolist() == [["ponts", 1], ["gares", 2]]
    members = pd.read_parquet(tmp_path / "out" / "series_members.parquet")
    assert members.values.tolist() == [["ponts", "PA1"]]
    review = pd.read_csv(tmp_path / "out" / "series_review.csv", keep_default_na=False)
    assert review["series"].tolist() == ["", "Ponts"]
