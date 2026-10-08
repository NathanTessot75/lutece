import logging
from pathlib import Path

import pandas as pd
import pytest

from lutece_pipeline import visibility
from lutece_pipeline.visibility import NOT_VISIBLE, UNKNOWN, VISIBLE, Label

# The protection texts below are copied from Mérimée notices, unless stated otherwise.
STREET_AND_COURTYARD = (
    "Façade sur rue et toiture correspondante (cad. 08 : 03 BQ 44) : classement par"
    " arrêté du 23 octobre 1961 ; Façade sur cour et rampe d'escalier en fer forgé"
    " (cad. 08 : 03 BQ 44) : inscription par arrêté du 23 octobre 1961"
)
PARTS_AFTER_A_HEADING = (
    "Les parties suivantes de l’hôtel Bénazet, situé 60-62 rue de la Victoire, sur"
    " la parcelle n° 33, figurant au cadastre section AM : les trois salons du"
    " rez-de-chaussée et leur décor, tels que délimités sur le second plan annexé à"
    " l’arrêté : inscription par arrêté du 19 avril 2023"
)
COURTYARD_FRONT_AND_ROOFS = (
    "Les parties suivantes de l’hôtel néogothique, situé 1 avenue Frochot, sur la"
    " parcelle n° 31, figurant au cadastre section AE tel que délimité par un liseré"
    " rouge sur le plan annexé à l’arrêté : la façade sur cour et les toitures, sans"
    " le perron, le vestibule et son décor, l’ancienne salle à manger, actuel salon"
    " de musique, et son décor : inscription par arrêté du 24 novembre 2021"
)


def clues(text: str) -> list[tuple[str, str]]:
    return [(clue.word, clue.kind) for clue in visibility.read_text(text)]


def notice(
    merimee_id: str,
    text: str | None,
    *,
    protection: str | None = "inscrit",
    denominations: tuple[str, ...] = ("immeuble",),
) -> dict[str, object]:
    return {
        "merimee_id": merimee_id,
        "name": "Immeuble",
        "protection": protection,
        "protection_desc": text,
        "denominations": list(denominations),
    }


def run_main(
    folder: Path,
    out: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    overrides: str = "",
    labels: str = "",
) -> None:
    out.mkdir(exist_ok=True)
    overrides_csv = out / "visibility_overrides.csv"
    labels_csv = out / "visibility_labels.csv"
    if overrides:
        overrides_csv.write_text("merimee_id,visibility,note\n" + overrides)
    if labels:
        labels_csv.write_text("merimee_id,sample,label,note\n" + labels)
    monkeypatch.setattr(visibility, "MERIMEE_PARQUET", folder / "merimee.parquet")
    monkeypatch.setattr(visibility, "OVERRIDES_CSV", overrides_csv)
    monkeypatch.setattr(visibility, "LABELS_CSV", labels_csv)
    monkeypatch.setattr(visibility, "VISIBILITY_PARQUET", out / "visibility.parquet")
    monkeypatch.setattr(visibility, "REVIEW_CSV", out / "visibility_to_review.csv")
    monkeypatch.setattr(visibility, "EVALUATION_CSV", out / "visibility_evaluation.csv")
    assert visibility.main([]) == 0


def test_clauses_drop_the_decrees_and_the_cadastral_references() -> None:
    assert visibility.split_clauses(STREET_AND_COURTYARD) == [
        "facade sur rue et toiture correspondante",
        "facade sur cour et rampe d'escalier en fer forge",
    ]


def test_clauses_are_cut_at_the_dash_between_two_decrees() -> None:
    text = (
        "Le pavillon : classement par arrêté du 3 mai 1913 - Les terrains ayant fait"
        " partie du jardin de la maison entre la rue Raynouard et la rue Berton :"
        " inscription par arrêté du 13 mars 1944"
    )
    assert visibility.split_clauses(text) == [
        "le pavillon",
        (
            "les terrains ayant fait partie du jardin de la maison entre la rue"
            " raynouard et la rue berton"
        ),
    ]


def test_hyphenated_words_do_not_cut_a_clause() -> None:
    text = (
        "Les salles du rez-de-chaussée, la devanture et ses ornements (cad. AQ 162) :"
        " inscription par arrêté du 12 juin 1998"
    )
    assert visibility.split_clauses(text) == [
        "les salles du rez-de-chaussee, la devanture et ses ornements"
    ]


def test_nested_parentheses_are_removed() -> None:
    text = (
        "Le regard : classement par arrêté du 6 février 2006 (voir notice PA75200003"
        " (eaux de Belleville) )"
    )
    assert visibility.split_clauses(text) == ["le regard"]


def test_missing_text_has_no_clause() -> None:
    assert visibility.split_clauses(None) == []
    assert visibility.split_clauses("") == []


def test_part_takes_the_side_stated_after_it() -> None:
    text = "Porte sur rue, porte sur cour et rampe d'escalier du 18s"
    assert clues(text) == [
        ("porte", "street"),
        ("porte", "courtyard"),
        ("rampe", "inside"),
        ("escalier", "inside"),
    ]


def test_matching_roof_takes_the_side_of_the_part_before() -> None:
    text = (
        "Façade et toiture sur rue ainsi que la façade sur cour et la toiture"
        " correspondante : inscription par arrêté du 30 décembre 1977"
    )
    assert clues(text) == [
        ("facade", "street"),
        ("toiture", "street"),
        ("facade", "courtyard"),
        ("toiture", "courtyard"),
    ]


def test_parts_joined_by_and_share_the_side_of_the_last_one() -> None:
    assert clues("Façades et toitures sur jardin") == [
        ("facades", "courtyard"),
        ("toitures", "courtyard"),
    ]
    assert clues("Les façades et les toitures sur rues et sur cour") == [
        ("facades", "street"),
        ("toitures", "street"),
    ]


def test_part_facing_both_a_street_and_a_courtyard_faces_the_street() -> None:
    text = "Les façades sur rue et sur cour, ainsi que l'ensemble des toitures"
    assert clues(text) == [("facades", "street"), ("toitures", "roof")]


def test_part_without_a_side_is_open_but_a_roof_says_nothing() -> None:
    assert clues("Les façades et les toitures") == [
        ("facades", "open"),
        ("toitures", "roof"),
    ]


def test_shop_fronts_face_the_street_unless_the_text_says_otherwise() -> None:
    assert clues("La devanture et le décor intérieur") == [
        ("devanture", "street"),
        ("decor", "inside"),
        ("interieur", "inside"),
    ]
    # Made-up wording: no notice places a gate on a courtyard.
    assert clues("Portail sur cour") == [("portail", "courtyard")]


def test_name_before_a_colon_is_only_a_heading_for_the_listed_parts() -> None:
    assert clues(PARTS_AFTER_A_HEADING) == [("salons", "inside"), ("decor", "inside")]


def test_monument_named_before_its_additions_counts_as_a_whole() -> None:
    text = "La cathédrale, y compris la crypte (cad. 08 : 02 AZ 13)"
    assert clues(text) == [("la cathedrale", "whole"), ("crypte", "inside")]


def test_clause_without_any_part_names_a_whole_monument() -> None:
    assert clues("Eglise (cad. 08 : 02 BE 27)") == [("eglise", "whole")]
    assert clues("L'hôtel, y compris les cours et l'ancien jardin") == [
        ("l'hotel", "whole")
    ]


def test_monument_standing_in_a_courtyard_is_hidden() -> None:
    assert clues("Fontaine sise dans la cour") == [
        ("fontaine sise dans la cour", "courtyard")
    ]
    assert clues("Immeubles sur cour") == [("immeubles sur cour", "courtyard")]
    assert clues("Le temple, situé dans l'arrière-cour") == [
        ("le temple, situe dans l'arriere-cour", "courtyard")
    ]


def test_ground_of_a_courtyard_is_hidden() -> None:
    assert clues("Le sol du jardin") == [("le sol du jardin", "courtyard")]


def test_remains_have_no_stated_place() -> None:
    assert clues("Vestiges de l'enceinte") == [("vestiges de l'enceinte", "unplaced")]


@pytest.mark.parametrize(
    ("text", "expected", "reason"),
    [
        (STREET_AND_COURTYARD, VISIBLE, "outside_part_on_street"),
        (
            (
                "La devanture et le décor intérieur : inscription par arrêté du 23 mai"
                " 1984"
            ),
            VISIBLE,
            "outside_part_on_street",
        ),
        (
            "Les façades et les toitures : inscription par arrêté du 15 janvier 1975",
            VISIBLE,
            "outside_part",
        ),
        (
            "Balcon à l'étage : inscription par arrêté du 18 février 1926",
            VISIBLE,
            "outside_part",
        ),
        (
            "Eglise (cad. 08 : 02 BE 27) : classement par arrêté du 5 juillet 1993",
            VISIBLE,
            "whole_monument",
        ),
        (
            (
                "Hôtel Païva, avec son décor intérieur (cad. 08 : 01 AQ 53) : classement"
                " par arrêté du 9 juillet 1980"
            ),
            VISIBLE,
            "whole_monument",
        ),
        (
            (
                "Le décor intérieur (cad. 01 : 02 AQ 83) : inscription par arrêté du 4"
                " juillet 1989"
            ),
            NOT_VISIBLE,
            "inside_only",
        ),
        (
            "La cave : inscription par arrêté du 12 février 1925",
            NOT_VISIBLE,
            "inside_only",
        ),
        (PARTS_AFTER_A_HEADING, NOT_VISIBLE, "inside_only"),
        (
            (
                "Façades sur cour et sur jardin (cad. BM 69) : inscription par arrêté du"
                " 4 novembre 1927"
            ),
            NOT_VISIBLE,
            "courtyard_only",
        ),
        (
            (
                "Les façades et les toitures des trois pavillons se trouvant au fond du"
                " parc : inscription par arrêté du 14 juin 1972"
            ),
            NOT_VISIBLE,
            "courtyard_only",
        ),
        (
            "Fontaine sise dans la cour : inscription par arrêté du 15 novembre 1961",
            NOT_VISIBLE,
            "courtyard_only",
        ),
        (COURTYARD_FRONT_AND_ROOFS, NOT_VISIBLE, "inside_and_courtyard"),
        (
            "Vestiges de l'enceinte : classement par liste de 1889",
            UNKNOWN,
            "unplaced_item",
        ),
        # Made-up wording: every notice that protects roofs names another part too.
        ("Toitures : inscription par arrêté du 1er mars 1930", UNKNOWN, "roofs_only"),
        (None, UNKNOWN, "no_text"),
    ],
)
def test_classify(text: str | None, expected: str, reason: str) -> None:
    assert visibility.classify(text, ["immeuble"])[:2] == (expected, reason)


def test_evidence_lists_the_clues_in_reading_order() -> None:
    assert visibility.classify(STREET_AND_COURTYARD, None)[2] == (
        "facade: street; toiture: street; facade: courtyard; rampe: inside;"
        " escalier: inside"
    )


def test_quarry_is_hidden_whatever_its_text_says() -> None:
    text = "Carrière souterraine et sol des parcelles correspondantes"
    assert visibility.classify(text, ["carrière souterraine"])[:2] == (
        NOT_VISIBLE,
        "underground",
    )
    assert visibility.classify(text, ["immeuble"])[0] == VISIBLE


def test_monument_in_public_grounds_is_visible() -> None:
    text = "Le square public aménagé sur la place"
    assert visibility.classify(text, ["square", "place"])[:2] == (
        VISIBLE,
        "public_grounds",
    )
    assert visibility.classify("Le sol du jardin", ["jardin public"])[0] == VISIBLE
    assert visibility.classify("Le sol du jardin", ["hôtel"])[0] == NOT_VISIBLE


def test_read_overrides(tmp_path: Path) -> None:
    path = tmp_path / "visibility_overrides.csv"
    path.write_text(
        "merimee_id,visibility,note\n"
        "PA00089004,visible,Le théâtre entier\n"
        'PA00088758,non_visible,"Mur dans la seconde cour, non visible"\n'
    )
    assert visibility.read_overrides(path) == {
        "PA00089004": VISIBLE,
        "PA00088758": NOT_VISIBLE,
    }
    assert visibility.read_overrides(tmp_path / "missing.csv") == {}


def test_read_labels(tmp_path: Path) -> None:
    path = tmp_path / "visibility_labels.csv"
    path.write_text(
        "merimee_id,sample,label,note\n"
        "PA00085786,dev,non_visible,Décor intérieur\n"
        "PA00085795,test,visible,\n"
    )
    assert visibility.read_labels(path) == {
        "PA00085786": Label(NOT_VISIBLE, "dev"),
        "PA00085795": Label(VISIBLE, "test"),
    }
    assert visibility.read_labels(tmp_path / "missing.csv") == {}


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ("PA00085786,dev,cachée,\n", "line 2: unknown class 'cachée'"),
        (
            "PA00085786,dev,visible,\nPA00085786,test,visible,\n",
            "line 3: PA00085786 appears twice",
        ),
        ("PA00085786,train,visible,\n", "unknown sample 'train' for PA00085786"),
    ],
)
def test_invalid_labels_are_refused(tmp_path: Path, rows: str, message: str) -> None:
    path = tmp_path / "visibility_labels.csv"
    path.write_text("merimee_id,sample,label,note\n" + rows)
    with pytest.raises(ValueError, match=message):
        visibility.read_labels(path)


def test_only_protected_notices_are_classified() -> None:
    notices = [
        notice("PA1", "Façade sur rue"),
        notice("PA2", None, protection=None),
        notice("PA3", "Escalier", protection="classé"),
    ]
    table = visibility.build_visibility(notices, {})
    assert list(table["merimee_id"]) == ["PA1", "PA3"]
    assert list(table["visibility"]) == [VISIBLE, NOT_VISIBLE]
    assert list(table["reason"]) == ["outside_part_on_street", "inside_only"]
    assert not table["reviewed"].any()


def test_reviewed_class_replaces_the_computed_one() -> None:
    notices = [notice("PA1", "Façade sur rue"), notice("PA2", "Escalier")]
    table = visibility.build_visibility(notices, {"PA2": VISIBLE})
    reviewed = table.set_index("merimee_id").loc["PA2"]
    assert reviewed["visibility"] == VISIBLE
    assert reviewed["reason"] == "reviewed"
    assert reviewed["reviewed"]
    # The clues stay, so that the correction can be compared with what was read.
    assert reviewed["evidence"] == "escalier: inside"
    assert list(table["reviewed"]) == [False, True]


def test_evaluation_compares_each_label_with_the_rules() -> None:
    notices = [
        notice("PA1", "Façade sur rue"),
        notice("PA2", "Escalier"),
        notice("PA3", "Vestiges de l'enceinte"),
    ]
    labels = {
        "PA3": Label(UNKNOWN, "test"),
        "PA1": Label(VISIBLE, "dev"),
        "PA2": Label(VISIBLE, "test"),
    }
    evaluation = visibility.evaluate(notices, labels)
    assert evaluation.to_dict("records") == [
        {
            "merimee_id": "PA1",
            "sample": "dev",
            "label": VISIBLE,
            "predicted": VISIBLE,
            "reason": "outside_part_on_street",
            "agree": True,
        },
        {
            "merimee_id": "PA2",
            "sample": "test",
            "label": VISIBLE,
            "predicted": NOT_VISIBLE,
            "reason": "inside_only",
            "agree": False,
        },
        {
            "merimee_id": "PA3",
            "sample": "test",
            "label": UNKNOWN,
            "predicted": UNKNOWN,
            "reason": "unplaced_item",
            "agree": True,
        },
    ]


def test_label_of_an_unknown_notice_is_skipped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    labels = {"PA9": Label(VISIBLE, "dev")}
    with caplog.at_level(logging.WARNING):
        evaluation = visibility.evaluate([notice("PA1", "Façade sur rue")], labels)
    assert evaluation.empty
    assert list(evaluation.columns) == [
        "merimee_id",
        "sample",
        "label",
        "predicted",
        "reason",
        "agree",
    ]
    assert "PA9 is labelled but is not a notice" in caplog.text


def test_review_lists_the_undecided_notices() -> None:
    notices = [
        notice("PA1", "Façade sur rue"),
        notice("PA2", "Vestiges de l'enceinte"),
        notice("PA3", "Escalier"),
    ]
    table = visibility.build_visibility(notices, {"PA3": UNKNOWN})
    review = visibility.build_review(notices, table)
    assert review.to_dict("records") == [
        {
            "merimee_id": "PA2",
            "name": "Immeuble",
            "protection_desc": "Vestiges de l'enceinte",
            "merimee_url": "https://pop.culture.gouv.fr/notice/merimee/PA2",
        },
        {
            "merimee_id": "PA3",
            "name": "Immeuble",
            "protection_desc": "Escalier",
            "merimee_url": "https://pop.culture.gouv.fr/notice/merimee/PA3",
        },
    ]


def test_summary_counts_the_classes_and_the_agreement_per_sample() -> None:
    notices = [
        notice("PA1", "Façade sur rue"),
        notice("PA2", "Escalier"),
        notice("PA3", "Vestiges de l'enceinte"),
    ]
    table = visibility.build_visibility(notices, {"PA2": VISIBLE})
    labels = {
        "PA1": Label(VISIBLE, "dev"),
        "PA2": Label(VISIBLE, "test"),
        "PA3": Label(UNKNOWN, "test"),
    }
    assert visibility.summarize(table, visibility.evaluate(notices, labels)) == {
        "monuments": 3,
        "visibility=visible": 2,
        "visibility=inconnu": 1,
        "reason=outside_part_on_street": 1,
        "reason=reviewed": 1,
        "reason=unplaced_item": 1,
        "reviewed": 1,
        "dev_labelled": 1,
        "dev_agree": 1,
        "test_labelled": 2,
        "test_agree": 1,
    }


def test_real_notices_are_classified(
    interim_tables: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_main(interim_tables, tmp_path, monkeypatch)
    table = pd.read_parquet(tmp_path / "visibility.parquet")
    assert list(table.columns) == visibility.SCHEMA.names
    # The fixture holds 11 Paris notices; a cancelled protection and a
    # cross-reference are not monuments.
    assert len(table) == 9
    assert not {"PA00086620", "PA00125441"} & set(table["merimee_id"])
    rows = table.set_index("merimee_id")
    # Only its inside decoration is protected.
    assert rows.loc["PA00085786", "visibility"] == NOT_VISIBLE
    assert rows.loc["PA00085786", "reason"] == "inside_only"
    assert rows.loc["PA00085795", "reason"] == "whole_monument"
    assert rows.loc["PA00086088", "reason"] == "outside_part_on_street"
    # "Salon du premier étage ; Façades et toitures": the fronts are enough.
    assert rows.loc["PA00085809", "reason"] == "outside_part"
    assert (table["visibility"] == VISIBLE).sum() == 8
    assert not table["reviewed"].any()
    assert pd.read_csv(tmp_path / "visibility_to_review.csv").empty
    assert pd.read_csv(tmp_path / "visibility_evaluation.csv").empty


def test_corrections_apply_but_the_evaluation_ignores_them(
    interim_tables: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_main(
        interim_tables,
        tmp_path,
        monkeypatch,
        overrides="PA00085786,inconnu,À voir sur place\n",
        labels="PA00085786,dev,non_visible,\nPA00085795,test,non_visible,\n",
    )
    rows = pd.read_parquet(tmp_path / "visibility.parquet").set_index("merimee_id")
    assert rows.loc["PA00085786", "visibility"] == UNKNOWN
    assert rows.loc["PA00085786", "reason"] == "reviewed"
    assert rows["reviewed"].sum() == 1
    review = pd.read_csv(tmp_path / "visibility_to_review.csv")
    assert list(review["merimee_id"]) == ["PA00085786"]
    evaluation = pd.read_csv(tmp_path / "visibility_evaluation.csv")
    assert evaluation.to_dict("records") == [
        {
            "merimee_id": "PA00085786",
            "sample": "dev",
            "label": NOT_VISIBLE,
            "predicted": NOT_VISIBLE,
            "reason": "inside_only",
            "agree": True,
        },
        {
            "merimee_id": "PA00085795",
            "sample": "test",
            "label": NOT_VISIBLE,
            "predicted": VISIBLE,
            "reason": "whole_monument",
            "agree": False,
        },
    ]


def test_correction_that_matches_no_monument_is_reported(
    interim_tables: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        run_main(
            interim_tables,
            tmp_path,
            monkeypatch,
            # A mistyped reference, and a notice whose protection was cancelled.
            overrides="PA99999999,visible,\nPA00086620,visible,\n",
        )
    assert (
        "2 corrections match no monument: ['PA00086620', 'PA99999999']" in caplog.text
    )
    assert not pd.read_parquet(tmp_path / "visibility.parquet")["reviewed"].any()
