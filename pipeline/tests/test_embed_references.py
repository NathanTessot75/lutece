from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from PIL import Image

from lutece_pipeline import embed_references, export_model, vision
from lutece_pipeline import fetch_reference_photos as photos


def save_photo(folder: Path, title: str, colour: str, size: tuple[int, int]) -> str:
    """Store a plain photo where the fetch step would, and give its path."""
    path = photos.photo_path(title)
    (folder / path).parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, colour).save(folder / path)
    return path


def test_vectors_are_written_and_read_back(tmp_path: Path) -> None:
    random = np.random.default_rng(1)
    vectors = random.standard_normal((3, vision.DIMENSIONS)).astype(np.float32)
    titles = ["File:A.jpg", "File:B.jpg", "File:Ç, d'été.jpg"]
    path = tmp_path / "embeddings" / "float32-crop.parquet"
    embed_references.write_embeddings(titles, vectors, path)

    read_titles, read_vectors = embed_references.read_embeddings(path)
    assert read_titles == titles
    assert read_vectors.dtype == np.float32
    assert np.array_equal(read_vectors, vectors)
    assert embed_references.embeddings_name("fp16", "squash") == "fp16-squash.parquet"


def test_photos_are_embedded_in_batches_in_their_order(
    exported_models: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    colours = ["red", "green", "blue", "white", "black"]
    paths = [
        tmp_path / save_photo(tmp_path, f"File:{colour}.jpg", colour, (60, 40))
        for colour in colours
    ]
    model = vision.open_model(exported_models / export_model.FILES["float32"])
    together = vision.embed_photos(model, paths, "crop")
    assert together.shape == (5, vision.DIMENSIONS)
    assert np.linalg.norm(together, axis=1) == pytest.approx([1.0] * 5, abs=1e-5)

    monkeypatch.setattr(vision, "BATCH_SIZE", 2)
    by_two = vision.embed_photos(model, paths, "crop")
    assert (together * by_two).sum(axis=1) == pytest.approx([1.0] * 5, abs=1e-5)
    # The same photo gives the same vector, another photo another one.
    again = vision.embed_photos(model, paths[:1], "crop")
    assert float(together[0] @ again[0]) == pytest.approx(1.0, abs=1e-5)
    assert float(together[0] @ together[1]) < 0.9999
    assert vision.embed_photos(model, [], "crop").shape == (0, vision.DIMENSIONS)


def test_reference_photos_are_embedded_once_each(
    exported_models: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "photos"
    rows = [
        {"merimee_id": "PA2", "title": "File:Dôme.jpg", "rank": 1},
        {"merimee_id": "PA2", "title": "File:Façade.jpg", "rank": 2},
        # The same file serves another place: it has one vector.
        {"merimee_id": "Q7", "title": "File:Dôme.jpg", "rank": 3},
    ]
    for row, colour in zip(rows[:2], ["grey", "orange"], strict=True):
        row["path"] = save_photo(folder, row["title"], colour, (120, 60))
    rows[2]["path"] = rows[0]["path"]
    pd.DataFrame(rows).to_parquet(tmp_path / "index.parquet")
    paths = {
        "INDEX_PARQUET": tmp_path / "index.parquet",
        "PHOTOS_FOLDER": folder,
        "MODELS_FOLDER": exported_models,
        "EMBEDDINGS_FOLDER": tmp_path / "embeddings",
    }
    for name, path in paths.items():
        monkeypatch.setattr(embed_references, name, path)

    assert embed_references.main([]) == 0
    assert embed_references.main(["--model", "fp16", "--framing", "squash"]) == 0

    titles, vectors = embed_references.read_embeddings(
        tmp_path / "embeddings" / "float32-crop.parquet"
    )
    assert titles == ["File:Dôme.jpg", "File:Façade.jpg"]
    assert vectors.shape == (2, vision.DIMENSIONS)
    assert np.linalg.norm(vectors, axis=1) == pytest.approx([1.0, 1.0], abs=1e-5)
    lighter = embed_references.read_embeddings(
        tmp_path / "embeddings" / "fp16-squash.parquet"
    )
    assert lighter[0] == titles
    with pytest.raises(SystemExit):
        embed_references.main(["--framing", "pad"])
