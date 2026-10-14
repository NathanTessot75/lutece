import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from lutece_pipeline import check_reference_photos as check
from lutece_pipeline import (
    embed_references,
    evaluate_retrieval,
    landmark_places,
    vision,
)
from lutece_pipeline import ingest_commons as commons


def unit(*vector: float) -> list[float]:
    padded = np.zeros(vision.DIMENSIONS)
    padded[: len(vector)] = vector
    return list(padded / np.linalg.norm(padded))


def photo(
    place: str, name: str, author: str | None, year: int = 2020
) -> dict[str, object]:
    """A line of the index of the reference photos."""
    return {
        "merimee_id": place,
        "title": f"File:{name}",
        "author": author,
        "year": year,
    }


# A church photographed by three people, one of whom went inside; a chapel
# that only one person photographed.
INDEX = [
    photo("church", "Façade.jpg", "Ana"),
    photo("church", "Porch.jpg", "Bo"),
    photo("church", "Nave 1.jpg", "Cy"),
    photo("church", "Nave 2.jpg", "Cy"),
    photo("chapel", "Chapel 1.jpg", "Di"),
    photo("chapel", "Chapel 2.jpg", "Di"),
]
VECTORS = np.array(
    [
        unit(1, 0.1, 0),
        unit(1, 0.3, 0),
        # The two views inside look alike, and like nothing outside.
        unit(0, 0.1, 1),
        unit(0, 0.2, 1),
        unit(0, 1, 0),
        unit(0, 1, 0.1),
    ],
    dtype=np.float32,
)
TITLES = [row["title"] for row in INDEX]


def test_likeness_is_measured_with_the_photos_of_other_authors() -> None:
    photos = evaluate_retrieval.gather(INDEX, TITLES, VECTORS)
    likeness = check.likeness_with_place(photos)
    assert likeness[0] == pytest.approx(float(VECTORS[0] @ VECTORS[1]))
    assert likeness[1] == pytest.approx(float(VECTORS[1] @ VECTORS[0]))
    # The second view inside does not vouch for the first: same author, same year.
    assert likeness[2] == pytest.approx(float(VECTORS[2] @ VECTORS[1]), abs=1e-6)
    assert likeness[2] < check.UNLIKE_BELOW
    # Nobody else photographed the chapel: nothing to compare with.
    assert likeness[4:] == [None, None]


def test_photos_unlike_their_place_are_set_aside_unless_spared() -> None:
    spared = {("church", "File:Nave 2.jpg"): "main_image"}
    checks = check.check(INDEX, TITLES, VECTORS, spared)
    rows = checks.set_index("title")
    assert list(checks.columns) == check.CHECKS_SCHEMA.names
    assert list(rows["kept"]) == [True, True, False, True, True, True]
    assert rows.loc["File:Nave 1.jpg", "why"] == "unlike_its_place"
    assert rows.loc["File:Nave 2.jpg", "why"] == "main_image"
    assert pd.isna(rows.loc["File:Façade.jpg", "why"])
    assert pd.isna(rows.loc["File:Chapel 1.jpg", "likeness"])
    assert check.summarize(checks) == {
        "photos": 6,
        "without_another_author": 2,
        "set_aside": 1,
        "spared_main_image": 1,
        "spared_named_by_review": 0,
        "places": 2,
        "places_left_without_photo": 0,
        "places_left_with_1_or_2": 1,
    }


def test_spared_photos_are_the_image_of_wikidata_and_those_the_review_names() -> None:
    names = commons.FILES_SCHEMA.names
    files = [
        dict.fromkeys(names)
        | {"merimee_id": "PA1", "title": "File:A.jpg", "source": "main_image"},
        dict.fromkeys(names)
        | {"merimee_id": "PA1", "title": "File:B.jpg", "source": "category"},
    ]
    tower = landmark_places.Decision("Q7", "Tour", "tour", "Tours", 0, (), ("Vue.jpg",))
    assert check.exempt_photos(files, [tower]) == {
        ("PA1", "File:A.jpg"): "main_image",
        ("Q7", "File:Vue.jpg"): "named_by_review",
    }


@pytest.mark.parametrize(
    ("likeness", "band"),
    [(-0.2, "<0.15"), (0.15, "0.15-0.25"), (0.349, "0.25-0.35"), (0.55, ">=0.55")],
)
def test_bands_of_likeness(likeness: float, band: str) -> None:
    assert check.band_of(likeness) == band


def test_labels_are_counted_band_by_band() -> None:
    checks = check.check(INDEX, TITLES, VECTORS, {})
    labels = [
        {"merimee_id": "church", "title": "File:Façade.jpg", "label": "ok"},
        {"merimee_id": "church", "title": "File:Nave 1.jpg", "label": "inside"},
        # A photo without a likeness, or not checked, is not counted.
        {"merimee_id": "chapel", "title": "File:Chapel 1.jpg", "label": "ok"},
        {"merimee_id": "church", "title": "File:Gone.jpg", "label": "ok"},
    ]
    table = check.evaluate(checks, labels).set_index("band")
    assert list(table.index) == [
        "<0.15",
        "0.15-0.25",
        "0.25-0.35",
        "0.35-0.45",
        "0.45-0.55",
        ">=0.55",
    ]
    # The two views inside fall low; one of them was looked at.
    assert table.loc["<0.15"].to_dict() == {
        "photos": 2,
        "looked_at": 1,
        "good_views": 0,
        "share_good": 0.0,
    }
    assert table.loc[">=0.55", "good_views"] == 1
    assert int(table["photos"].sum()) == 4
    assert pd.isna(table.loc["0.35-0.45", "share_good"])


def test_check_is_written_with_its_evaluation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pd.DataFrame(INDEX).assign(rank=1, path="x.jpg", bytes=1).to_parquet(
        tmp_path / "index.parquet"
    )
    folder = tmp_path / "embeddings"
    embed_references.write_embeddings(TITLES, VECTORS, folder / "float32-crop.parquet")
    names = commons.FILES_SCHEMA.names
    rows = [dict.fromkeys(names) | row | {"source": "category"} for row in INDEX]
    commons.from_rows(rows[:4], commons.FILES_SCHEMA).to_parquet(
        tmp_path / "files.parquet"
    )
    commons.from_rows(rows[4:], commons.FILES_SCHEMA).to_parquet(
        tmp_path / "place_files.parquet"
    )
    (tmp_path / "landmarks.csv").write_text(
        "qid,name,title,kind,group,decision,reach_m,osm,photos,note\n"
    )
    (tmp_path / "labels.csv").write_text(
        "merimee_id,title,label,note\nchurch,File:Nave 1.jpg,inside,\n"
    )
    paths = {
        "INDEX_PARQUET": tmp_path / "index.parquet",
        "FILES_PARQUET": tmp_path / "files.parquet",
        "PLACE_FILES_PARQUET": tmp_path / "place_files.parquet",
        "REVIEW_CSV": tmp_path / "landmarks.csv",
        "EMBEDDINGS_FOLDER": folder,
        "LABELS_CSV": tmp_path / "labels.csv",
        "CHECKS_PARQUET": tmp_path / "checks.parquet",
        "EVALUATION_CSV": tmp_path / "evaluation.csv",
    }
    for name, path in paths.items():
        monkeypatch.setattr(check, name, path)
    assert check.main([]) == 0

    checks = pd.read_parquet(tmp_path / "checks.parquet")
    # Nothing spares the views inside here.
    assert list(checks.loc[~checks["kept"], "title"]) == [
        "File:Nave 1.jpg",
        "File:Nave 2.jpg",
    ]
    evaluation = pd.read_csv(tmp_path / "evaluation.csv")
    assert int(evaluation["looked_at"].sum()) == 1
    assert json.dumps(list(evaluation.columns)) == json.dumps(
        ["band", "photos", "looked_at", "good_views", "share_good"]
    )
