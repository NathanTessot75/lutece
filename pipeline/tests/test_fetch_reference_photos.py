from pathlib import Path

import httpx
import pandas as pd
import pytest

from lutece_pipeline import fetch_reference_photos as photos
from lutece_pipeline import ingest_commons as commons
from lutece_pipeline import web

THUMBS = "https://thumb.wikimedia.org/wikipedia/commons/thumb"


def file(
    place: str, name: str, rank: int | None, **changes: object
) -> dict[str, object]:
    """A line of the Commons step: a file found for a place, ranked if kept."""
    row = dict.fromkeys(commons.FILES_SCHEMA.names)
    return row | {
        "merimee_id": place,
        "title": f"File:{name}",
        "thumb_url": f"{THUMBS}/a/ab/{name}/960px-{name}?utm_source=commons",
        "author": "Camille",
        "uploader": "Cam75",
        "year": 2021,
        "rank": rank,
        "selected": rank is not None,
        **changes,
    }


def test_references_are_the_photos_selected_for_what_the_app_shows() -> None:
    files = [
        file("PA2", "Panthéon 2.jpg", 2),
        file("PA2", "Panthéon 1.jpg", 1),
        file("PA2", "Plan.jpg", None),
        # A monument that the selection does not show.
        file("PA9", "Immeuble.jpg", 1),
    ]
    place_files = [file("Q323767", "Tour.jpg", 1), file("Q323767", "Vue.jpg", None)]
    references = photos.read_references(files, place_files, frozenset({"PA2"}))
    assert [(row["merimee_id"], row["title"]) for row in references] == [
        ("PA2", "File:Panthéon 1.jpg"),
        ("PA2", "File:Panthéon 2.jpg"),
        ("Q323767", "File:Tour.jpg"),
    ]


def test_photo_is_asked_at_the_width_the_model_needs() -> None:
    shown = f"{THUMBS}/9/95/Tour.jpg/960px-Tour.jpg?utm_source=commons"
    assert photos.photo_url(shown) == (
        f"{THUMBS}/9/95/Tour.jpg/500px-Tour.jpg?utm_source=commons"
    )
    # Only the width of the thumbnail changes, not a name that looks like one.
    odd = f"{THUMBS}/1/12/Vue-960px-.jpg/960px-Vue-960px-.jpg"
    assert photos.photo_url(odd) == f"{THUMBS}/1/12/Vue-960px-.jpg/500px-Vue-960px-.jpg"
    # A file narrower than what the app shows is taken as it is.
    original = "https://upload.wikimedia.org/wikipedia/commons/7/7a/Petite.jpg"
    assert photos.photo_url(original) == original


def test_photo_is_filed_under_a_name_made_from_its_title() -> None:
    path = photos.photo_path("File:Tour Montparnasse / vue du 6e.jpg")
    folder, name = path.split("/")
    assert len(folder) == 2 and name.startswith(folder) and name.endswith(".jpg")
    assert path == photos.photo_path("File:Tour Montparnasse / vue du 6e.jpg")
    assert path != photos.photo_path("File:Tour Montparnasse.jpg")


def test_photos_are_downloaded_once(tmp_path: Path) -> None:
    asked: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        asked.append(str(request.url))
        if "Disparue" in str(request.url):
            return httpx.Response(404)
        return httpx.Response(
            200, content=b"pixels", headers={"content-type": "image/jpeg"}
        )

    references = [
        file("PA2", "Panthéon.jpg", 1),
        # The same file serves two places: it is fetched once.
        file("PA3", "Panthéon.jpg", 4),
        file("PA3", "Disparue.jpg", 1),
    ]
    pauses: list[float] = []
    with web.make_client(transport=httpx.MockTransport(answer)) as client:
        first = photos.fetch_photos(client, references, tmp_path, pause=pauses.append)
        second = photos.fetch_photos(client, references, tmp_path, pause=pauses.append)

    assert first == {"already_there": 0, "downloaded": 1, "gone": 1}
    assert second == {"already_there": 1, "downloaded": 0, "gone": 1}
    assert len(asked) == 3
    assert "/500px-Panth" in asked[0]
    assert pauses == [photos.PAUSE_SECONDS] * 3
    stored = tmp_path / photos.photo_path("File:Panthéon.jpg")
    assert stored.read_bytes() == b"pixels"
    assert not list(tmp_path.rglob("*.part"))

    index = photos.build_index(references, tmp_path)
    assert list(index["merimee_id"]) == ["PA2", "PA3"]
    assert list(index["rank"]) == [1, 4]
    assert list(index["author"]) == ["Camille", "Camille"]
    assert list(index["bytes"]) == [6, 6]
    assert photos.summarize(references, index) == {
        "references": 3,
        "places": 2,
        "photos_wanted": 2,
        "photos_there": 1,
        "places_with_a_photo": 2,
        "megabytes": 0,
    }


def test_answer_that_is_not_a_photo_stops_the_step(tmp_path: Path) -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=b"<html>", headers={"content-type": "text/html"}
        )

    with (
        web.make_client(transport=httpx.MockTransport(answer)) as client,
        pytest.raises(RuntimeError, match="did not answer with a photo"),
    ):
        photos.fetch_photos(client, [file("PA2", "Panthéon.jpg", 1)], tmp_path)
    assert not list(tmp_path.rglob("*.jpg"))


def test_index_is_built_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = [file("PA2", "Panthéon.jpg", 1, author=None), file("PA9", "Autre.jpg", 1)]
    place_files = [file("Q323767", "Tour.jpg", 1)]
    commons.from_rows(files, commons.FILES_SCHEMA).to_parquet(
        tmp_path / "files.parquet"
    )
    commons.from_rows(place_files, commons.FILES_SCHEMA).to_parquet(
        tmp_path / "place_files.parquet"
    )
    pd.DataFrame(
        [{"merimee_id": "PA2", "shown": True}, {"merimee_id": "PA9", "shown": False}]
    ).to_parquet(tmp_path / "selection.parquet")
    folder = tmp_path / "photos"
    stored = folder / photos.photo_path("File:Panthéon.jpg")
    stored.parent.mkdir(parents=True)
    stored.write_bytes(b"pixels")
    paths = {
        "FILES_PARQUET": tmp_path / "files.parquet",
        "PLACE_FILES_PARQUET": tmp_path / "place_files.parquet",
        "SELECTION_PARQUET": tmp_path / "selection.parquet",
        "PHOTOS_FOLDER": folder,
        "INDEX_PARQUET": tmp_path / "index.parquet",
    }
    for name, path in paths.items():
        monkeypatch.setattr(photos, name, path)

    def no_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("the offline run must not open a connection")

    monkeypatch.setattr(web, "make_client", no_network)
    assert photos.main(["--offline"]) == 0

    index = pd.read_parquet(tmp_path / "index.parquet")
    assert list(index.columns) == photos.INDEX_SCHEMA.names
    # The tower is not downloaded yet; without an author, the uploader stands in.
    assert index.to_dict("records") == [
        {
            "merimee_id": "PA2",
            "title": "File:Panthéon.jpg",
            "rank": 1,
            "author": "Cam75",
            "year": 2021,
            "path": photos.photo_path("File:Panthéon.jpg"),
            "bytes": 6,
        }
    ]
