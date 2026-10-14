import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box

from lutece_pipeline import embed_references, evaluate_retrieval, vision

EAST, NORTH, UP = [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]


def unit(*vector: float) -> list[float]:
    length = float(np.linalg.norm(vector))
    return [value / length for value in vector]


def photo(place: str, name: str, author: str | None, year: int) -> dict[str, object]:
    """A line of the index of the reference photos."""
    return {
        "merimee_id": place,
        "title": f"File:{name}",
        "author": author,
        "year": year,
    }


# A church and a tower 50 m apart, and a bridge at the other end of the city.
INDEX = [
    photo("church", "Church 1.jpg", "Ana", 2020),
    photo("church", "Church 2.jpg", "Ana", 2020),
    photo("church", "Church 3.jpg", "Bo", 2021),
    photo("tower", "Tower 1.jpg", "Ana", 2020),
    photo("tower", "Tower 2.jpg", "Cy", 2019),
    photo("bridge", "Bridge 1.jpg", "Bo", 2021),
    photo("bridge", "Bridge 2.jpg", None, 2021),
]
VECTORS = np.array(
    [
        unit(1, 0.1, 0),
        unit(1, 0.1, 0),
        unit(1, 0.3, 0),
        NORTH,
        # A photo of the tower in which the church takes most of the frame.
        unit(1, 0.6, 0),
        UP,
        unit(0, 0.1, 1),
    ]
)
NEIGHBOURS = {"church": ["tower"], "tower": ["church"]}


def test_places_around_are_those_within_the_distance() -> None:
    footprints = gpd.GeoSeries(
        {
            "church": box(0, 0, 40, 20),
            "tower": box(90, 0, 100, 10),
            "bridge": box(5000, 5000, 5100, 5010),
            "square": box(240, 0, 300, 50),
        },
        crs="EPSG:2154",
    )
    assert evaluate_retrieval.find_neighbours(footprints, 150.0) == {
        "church": ["tower"],
        "tower": ["church", "square"],
        "square": ["tower"],
    }
    assert evaluate_retrieval.find_neighbours(footprints, 10.0) == {}


def test_outlines_of_monuments_and_places_are_gathered_in_metres() -> None:
    monuments = gpd.GeoDataFrame(
        {"merimee_id": ["PA2"]}, geometry=[box(2.34, 48.85, 2.341, 48.851)], crs=4326
    )
    places = gpd.GeoDataFrame(
        {"qid": ["Q7"]}, geometry=[box(2.35, 48.85, 2.351, 48.851)], crs=4326
    )
    footprints = evaluate_retrieval.read_footprints(monuments, places)
    assert list(footprints.index) == ["PA2", "Q7"]
    assert footprints.crs == "EPSG:2154"
    # 0.001° of longitude by 0.001° of latitude: about 73 m by 111 m.
    assert footprints["Q7"].area == pytest.approx(73 * 111, rel=0.03)


def test_lines_of_the_index_get_their_vector_and_their_session() -> None:
    titles = [row["title"] for row in INDEX[::-1] if "Tower 1" not in row["title"]]
    vectors = np.array([v for v, row in zip(VECTORS, INDEX, strict=True)][::-1])
    vectors = np.delete(vectors, 3, axis=0)
    photos = evaluate_retrieval.gather(INDEX, titles, vectors)
    # The photo without a vector is left out; the others keep the order of the index.
    assert photos.titles == [
        row["title"] for row in INDEX if "Tower 1" not in row["title"]
    ]
    assert photos.places[:4] == ["church", "church", "church", "tower"]
    assert np.allclose(photos.vectors[0], VECTORS[0])
    assert np.allclose(photos.vectors[3], VECTORS[4])
    # Without a name, a photo is a session of its own.
    assert photos.sessions[0] == photos.sessions[1] == "Ana|2020"
    assert photos.sessions[-1] == "File:Bridge 2.jpg"


def test_each_photo_is_played_as_a_capture() -> None:
    photos = evaluate_retrieval.gather(INDEX, [row["title"] for row in INDEX], VECTORS)
    queries, wrong = evaluate_retrieval.score_queries(photos, NEIGHBOURS)
    by_title = queries.set_index("title")
    assert len(queries) == 7 and len(wrong) == 5

    first = by_title.loc["File:Church 1.jpg"]
    # Its twin of the same session is not what it is compared with.
    assert first["own"] == pytest.approx(float(VECTORS[0] @ VECTORS[2]))
    assert first["candidates"] == 2
    assert first["best_around"] == pytest.approx(float(VECTORS[0] @ VECTORS[4]))
    # The bridge is the only place that is not around the church.
    assert first["elsewhere"] == pytest.approx(float(VECTORS[0] @ VECTORS[6]))

    confusing = by_title.loc["File:Tower 2.jpg"]
    assert confusing["own"] == pytest.approx(float(VECTORS[4] @ VECTORS[3]))
    assert confusing["best_around"] > confusing["own"]
    # Nothing is around the bridge.
    assert by_title.loc["File:Bridge 1.jpg"]["candidates"] == 1
    assert np.isnan(by_title.loc["File:Bridge 1.jpg"]["best_around"])

    summary = evaluate_retrieval.measure(queries, wrong)
    assert summary["captures"] == 7
    assert summary["places"] == 3
    assert summary["captures_with_places_around"] == 5
    assert summary["candidates_on_average"] == 2.0
    assert summary["first_by_chance"] == 0.5
    # Four of the five contested photos name their place; the confusing one does not.
    assert summary["first"] == 0.8
    assert 0.5 < summary["separation_from_places_around"] < 1.0
    strict, lenient = summary["strict_thresholds"], summary["lenient_thresholds"]
    assert [row["false_accept"] for row in strict] == [0.01, 0.05, 0.1]
    assert all(0 <= row["false_refuse"] <= 1 for row in strict)
    assert [row["false_refuse"] for row in lenient] == [0.01, 0.05, 0.1]
    # A threshold under the likeness of every right place: the bridge photos,
    # which look like nothing of the church or the tower, stay out.
    assert lenient[0]["threshold"] < 0.7
    assert lenient[0]["elsewhere_kept_out"] > 0.5


def test_photo_alone_in_its_session_and_place_is_not_played() -> None:
    index = [
        photo("church", "A.jpg", "Ana", 2020),
        photo("church", "B.jpg", "Ana", 2020),
    ]
    photos = evaluate_retrieval.gather(index, ["File:A.jpg", "File:B.jpg"], VECTORS[:2])
    queries, wrong = evaluate_retrieval.score_queries(photos, {})
    assert len(queries) == 0 and len(wrong) == 0


def test_file_that_serves_two_places_is_not_compared_with_itself() -> None:
    index = [
        photo("church", "Shared.jpg", "Ana", 2020),
        photo("church", "Church.jpg", "Bo", 2021),
        photo("tower", "Shared.jpg", "Ana", 2020),
        photo("tower", "Tower.jpg", "Cy", 2019),
    ]
    titles = ["File:Shared.jpg", "File:Church.jpg", "File:Tower.jpg"]
    vectors = np.array([EAST, unit(1, 0.2, 0), NORTH])
    photos = evaluate_retrieval.gather(index, titles, vectors)
    queries, _ = evaluate_retrieval.score_queries(photos, NEIGHBOURS)
    shared = queries[
        (queries["title"] == "File:Shared.jpg") & (queries["place"] == "church")
    ]
    # Compared with the other photo of the tower, not with its own copy there.
    assert shared["best_around"].iloc[0] == pytest.approx(0.0, abs=1e-9)


def test_measures_are_written_for_every_set_of_vectors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    random = np.random.default_rng(3)
    titles = [row["title"] for row in INDEX]
    places = {"church": EAST, "tower": NORTH, "bridge": UP}
    centre = np.zeros((len(INDEX), vision.DIMENSIONS), dtype=np.float32)
    for line, row in enumerate(INDEX):
        centre[line, :3] = places[row["merimee_id"]]
    noisy = centre + 0.05 * random.standard_normal(centre.shape).astype(np.float32)
    vectors = noisy / np.linalg.norm(noisy, axis=1, keepdims=True)
    lighter = vectors + 0.01 * random.standard_normal(vectors.shape).astype(np.float32)
    lighter /= np.linalg.norm(lighter, axis=1, keepdims=True)
    folder = tmp_path / "embeddings"
    embed_references.write_embeddings(titles, vectors, folder / "float32-crop.parquet")
    embed_references.write_embeddings(titles, lighter, folder / "int8-crop.parquet")

    pd.DataFrame(INDEX).assign(rank=1, path="x.jpg", bytes=1).to_parquet(
        tmp_path / "index.parquet"
    )
    # About 73 m per 0.001° of longitude: the tower is 70 m east of the church.
    gpd.GeoDataFrame(
        {"merimee_id": ["church", "bridge", "unseen"]},
        geometry=[
            box(2.3400, 48.850, 2.3405, 48.8505),
            box(2.4000, 48.850, 2.4010, 48.8505),
            box(2.3000, 48.850, 2.3010, 48.8505),
        ],
        crs=4326,
    ).to_parquet(tmp_path / "geometries.parquet")
    gpd.GeoDataFrame(
        {"qid": ["tower"]}, geometry=[box(2.3415, 48.850, 2.3417, 48.8502)], crs=4326
    ).to_parquet(tmp_path / "places.parquet")
    paths = {
        "INDEX_PARQUET": tmp_path / "index.parquet",
        "GEOMETRIES_PARQUET": tmp_path / "geometries.parquet",
        "PLACES_PARQUET": tmp_path / "places.parquet",
        "EMBEDDINGS_FOLDER": folder,
        "REPORT_JSON": tmp_path / "report.json",
        "CHECKS_PARQUET": tmp_path / "checks.parquet",
    }
    for name, path in paths.items():
        monkeypatch.setattr(evaluate_retrieval, name, path)
    assert evaluate_retrieval.main([]) == 0

    report = json.loads((tmp_path / "report.json").read_text())
    assert report["neighbour_m"] == 150.0
    assert [
        (run["model"], run["framing"], run["photos"]) for run in report["runs"]
    ] == [
        ("float32", "crop", "all"),
        ("int8", "crop", "all"),
    ]
    trained, light = report["runs"]
    assert trained["captures"] == 7
    assert trained["captures_with_places_around"] == 5
    assert trained["first"] == 1.0
    assert trained["separation_from_places_around"] == 1.0
    assert "agreement_with_float32" not in trained
    assert 0.9 < light["agreement_with_float32"]["least"] <= 1.0


def test_runs_with_and_without_the_photos_set_aside(tmp_path: Path) -> None:
    titles = [row["title"] for row in INDEX]
    embed_references.write_embeddings(
        titles,
        np.pad(VECTORS, ((0, 0), (0, vision.DIMENSIONS - 3))).astype(np.float32),
        tmp_path / "float32-crop.parquet",
    )
    runs = evaluate_retrieval.evaluate(
        INDEX, NEIGHBOURS, tmp_path, frozenset({("tower", "File:Tower 2.jpg")})
    )
    assert [(run["photos"], run["first"]) for run in runs] == [
        ("all", 0.8),
        ("kept", 1.0),
    ]
    assert len(evaluate_retrieval.evaluate(INDEX, NEIGHBOURS, tmp_path)) == 1
