import json
import sqlite3
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import MultiPolygon, box

from lutece_pipeline import embed_references, export_model, load_postgres
from lutece_pipeline import export_bundle as bundle
from lutece_pipeline import ingest_commons as commons
from lutece_pipeline.tables import from_rows, write_parquet

SQUARE = box(2.35, 48.85, 2.351, 48.851)


def notice(merimee_id: str, **changes: object) -> dict[str, object]:
    return {
        "merimee_id": merimee_id,
        "name": "Hôtel de Sully",
        "address": "62 rue Saint-Antoine",
        "arrondissement": 4,
        "protection": "classé",
        "denominations": ["hôtel"],
        "construction_century": 17,
        "architects": ["Jean Androuet du Cerceau"],
        **changes,
    }


def place(merimee_id: str, **changes: object) -> dict[str, object]:
    return {
        "merimee_id": merimee_id,
        "ref_lat": 48.8505,
        "ref_lon": 2.3505,
        "footprint_source": "osm_footprint",
        "geometry": SQUARE,
        **changes,
    }


def file(merimee_id: str, rank: int | None, **changes: object) -> dict[str, object]:
    return {
        "merimee_id": merimee_id,
        "title": f"File:{merimee_id} {rank}.jpg",
        "page_url": f"https://commons.wikimedia.org/wiki/File:{merimee_id}_{rank}.jpg",
        "thumb_url": f"https://thumb.wikimedia.org/960px-{merimee_id}_{rank}.jpg",
        "author": "Anne",
        "licence": "CC BY-SA 4.0",
        "licence_url": "https://creativecommons.org/licenses/by-sa/4.0",
        "rank": rank,
        "selected": rank is not None,
        **changes,
    }


@pytest.mark.parametrize(
    ("name", "address", "denominations", "expected"),
    [
        ("Hôtel de Sully", "62 rue Saint-Antoine", ["hôtel"], "Hôtel de Sully"),
        ("Immeuble", "12 rue Volta", ["immeuble"], "Immeuble, 12 rue Volta"),
        (
            "Boulangerie",
            "5 rue Lepic",
            ["magasin de commerce"],
            "Boulangerie, 5 rue Lepic",
        ),
        # A notice may list several addresses: the first one is enough.
        (
            "Immeuble",
            "211 rue Saint-Honoré ; 202 rue de Rivoli",
            ["immeuble"],
            "Immeuble, 211 rue Saint-Honoré",
        ),
        ("Maison", None, ["maison"], "Maison"),
    ],
)
def test_monument_without_a_name_is_called_after_its_address(
    name: str, address: str | None, denominations: list[str], expected: str
) -> None:
    assert bundle.display_title(name, address, denominations) == expected


def test_footprint_is_a_geojson_multipolygon_with_six_decimals() -> None:
    shape = box(2.3500001234, 48.85, 2.351, 48.851)
    written = json.loads(bundle.to_geojson(shape))
    assert written["type"] == "MultiPolygon"
    ((ring,),) = written["coordinates"]
    assert [2.35, 48.85] in ring
    assert len(ring) == 5
    pieces = MultiPolygon([SQUARE, box(2.36, 48.85, 2.361, 48.851)])
    assert len(json.loads(bundle.to_geojson(pieces))["coordinates"]) == 2


def test_monument_row_is_what_the_app_shows() -> None:
    rows = bundle.build_monuments(
        [notice("PA2", name="Immeuble", denominations=["immeuble"]), notice("PA1")],
        [{"merimee_id": "PA1", "wikidata_qid": "Q42"}],
        [{"qid": "Q42", "architects": None}],
        [place("PA1"), place("PA2", footprint_source="buffer")],
        [{"merimee_id": "PA1", "visibility": "visible"}],
        {"PA1": 15},
        {"PA1": 222, "PA2": 40},
        {"PA1": "Hôtel de Sully", "PA2": None},
    )
    # Sorted by reference, so that the file is the same at every run.
    assert [row["merimee_id"] for row in rows] == ["PA1", "PA2"]
    assert rows[0] == {
        "id": str(load_postgres.monument_id("PA1")),
        "merimee_id": "PA1",
        "title": "Hôtel de Sully",
        "name": "Hôtel de Sully",
        "address": "62 rue Saint-Antoine",
        "arrondissement": 4,
        "lat": 48.8505,
        "lon": 2.3505,
        "min_lat": 48.85,
        "max_lat": 48.851,
        "min_lon": 2.35,
        "max_lon": 2.351,
        "footprint": bundle.to_geojson(SQUARE),
        "footprint_source": "osm_footprint",
        "category": "hôtel",
        "century": 17,
        "architects": '["Jean Androuet du Cerceau"]',
        "wikidata_qid": "Q42",
        "wikipedia": "Hôtel de Sully",
        "protection": "classé",
        "visibility": "visible",
        "readiness": "ready",
        "capture_reach_m": 222,
        "photo_count": 15,
    }
    assert rows[1]["title"] == "Immeuble, 62 rue Saint-Antoine"
    assert rows[1]["wikidata_qid"] is None
    # Not seen by the visibility step: undecided, hence not offered to capture.
    assert rows[1]["visibility"] == "inconnu"
    assert rows[1]["readiness"] == "not_ready"
    assert rows[1]["photo_count"] == 0


def test_monuments_with_the_same_name_are_told_apart_by_their_address() -> None:
    name = "Immeuble en bordure du Palais-Royal"
    notices = [
        notice("PA1", name=name, address="12 rue de Montpensier ; 3 rue de Valois"),
        notice("PA2", name=name, address="14 rue de Montpensier"),
        notice("PA3", name=name, address=None),
        notice("PA4"),
    ]
    places = [place(f"PA{number}") for number in range(1, 5)]
    reaches = dict.fromkeys(["PA1", "PA2", "PA3", "PA4"], 50)
    shown = dict.fromkeys(reaches)
    rows = bundle.build_monuments(notices, [], [], places, [], {}, reaches, shown)
    assert [row["title"] for row in rows] == [
        "Immeuble en bordure du Palais-Royal, 12 rue de Montpensier",
        "Immeuble en bordure du Palais-Royal, 14 rue de Montpensier",
        "Immeuble en bordure du Palais-Royal",
        "Hôtel de Sully",
    ]


def test_notices_without_protection_or_location_are_left_out() -> None:
    notices = [notice("PA1"), notice("PA2", protection=None), notice("PA3")]
    places = [place("PA1"), place("PA2")]
    everything = dict.fromkeys(["PA1", "PA2", "PA3"])
    rows = bundle.build_monuments(
        notices, [], [], places, [], {}, {"PA1": 50}, everything
    )
    assert [row["merimee_id"] for row in rows] == ["PA1"]


def test_monuments_that_the_selection_hides_are_left_out() -> None:
    notices = [notice("PA1"), notice("PA2"), notice("PA3")]
    places = [place("PA1"), place("PA2"), place("PA3")]
    reaches = dict.fromkeys(["PA1", "PA2", "PA3"], 50)
    shown = dict.fromkeys(["PA1", "PA3", "PA9"])
    rows = bundle.build_monuments(notices, [], [], places, [], {}, reaches, shown)
    assert [row["merimee_id"] for row in rows] == ["PA1", "PA3"]


def test_only_a_distance_set_by_hand_extends_the_reach() -> None:
    # However long a palace, its size says nothing of where it is seen from.
    palace = box(2.37, 48.85, 2.38, 48.852)
    notices = [notice("PA1"), notice("PA2"), notice("PA3")]
    places = [place("PA1"), place("PA2", geometry=palace), place("PA3")]
    by_hand = {"PA3": 800, "PA9": 500}
    shown = dict.fromkeys(["PA1", "PA2", "PA3"])
    rows = bundle.build_monuments(notices, [], [], places, [], {}, by_hand, shown)
    assert [row["capture_reach_m"] for row in rows] == [0, 0, 800]


def landmark(qid: str, **changes: object) -> dict[str, object]:
    """A line of the landmark places step."""
    return {
        "qid": qid,
        "title": "Tour Montparnasse",
        "kind": "gratte-ciel",
        "arrondissement": 15,
        "ref_lat": 48.8505,
        "ref_lon": 2.3505,
        "geometry": SQUARE,
        "footprint_source": "osm_footprint",
        "century": 20,
        "architects": ["Jean Saubot", "Eugène Beaudouin"],
        "article": "Tour Montparnasse",
        "reach_m": 1500,
        **changes,
    }


def test_place_without_a_notice_has_the_row_of_a_monument() -> None:
    places = [
        landmark("Q323767"),
        landmark("Q13397", title="Pyramide du Louvre", footprint_source="buffer"),
    ]
    rows = bundle.build_landmarks(places, {"Q323767": 12})
    # Sorted by item, so that the file is the same at every run.
    assert [row["wikidata_qid"] for row in rows] == ["Q13397", "Q323767"]
    tower = rows[1]
    assert set(tower) == set(bundle.MONUMENT_COLUMNS)
    assert tower["id"] == bundle.landmark_id("Q323767")
    assert tower["id"] != str(load_postgres.monument_id("Q323767"))
    assert tower["merimee_id"] is None
    assert tower["protection"] is None
    assert tower["address"] is None
    assert (tower["title"], tower["name"]) == ("Tour Montparnasse",) * 2
    assert tower["category"] == "gratte-ciel"
    assert tower["architects"] == '["Jean Saubot", "Eugène Beaudouin"]'
    assert tower["wikipedia"] == "Tour Montparnasse"
    assert (tower["visibility"], tower["readiness"]) == ("visible", "ready")
    assert tower["capture_reach_m"] == 1500
    assert tower["photo_count"] == 12
    assert (tower["min_lat"], tower["max_lon"]) == (48.85, 2.351)
    # A place that OpenStreetMap does not outline is marked by a circle.
    assert rows[0]["readiness"] == "approximate"
    assert rows[0]["photo_count"] == 0


def test_distances_set_by_hand_are_read_and_checked(tmp_path: Path) -> None:
    path = tmp_path / "capture_reach.csv"
    assert bundle.read_reaches(path) == {}
    header = "merimee_id,name,reach_m,note\n"
    path.write_text(header + "PA1,Tour Eiffel,800,far\nPA2,Arc,300,\n")
    assert bundle.read_reaches(path) == {"PA1": 800, "PA2": 300}
    path.write_text(header + "PA1,Tour Eiffel,800,\nPA1,Tour Eiffel,600,\n")
    with pytest.raises(ValueError, match="line 3: PA1 appears twice"):
        bundle.read_reaches(path)
    for wrong in ("far", "0", "-5", ""):
        path.write_text(header + f"PA1,Tour Eiffel,{wrong},\n")
        with pytest.raises(ValueError, match="line 2: .* is not a distance"):
            bundle.read_reaches(path)


def test_only_the_first_photos_of_each_monument_are_kept() -> None:
    monuments = [
        {"merimee_id": "PA1", "id": "id-1"},
        {"merimee_id": "PA2", "id": "id-2"},
    ]
    files = [
        file("PA2", 1),
        file("PA1", 4),
        file("PA1", 3),
        file("PA1", 1),
        file("PA1", None),
        file("PA9", 1),
    ]
    photos = bundle.build_photos(files, monuments)
    assert [(photo["monument_id"], photo["rank"]) for photo in photos] == [
        ("id-1", 1),
        ("id-1", 3),
        ("id-2", 1),
    ]
    assert photos[0] == {
        "monument_id": "id-1",
        "rank": 1,
        "thumb_url": "https://thumb.wikimedia.org/960px-PA1_1.jpg",
        "page_url": "https://commons.wikimedia.org/wiki/File:PA1_1.jpg",
        "author": "Anne",
        "licence": "CC BY-SA 4.0",
        "licence_url": "https://creativecommons.org/licenses/by-sa/4.0",
    }


def test_version_changes_with_the_content() -> None:
    monuments = [{"merimee_id": "PA1", "title": "Hôtel de Sully"}]
    photos = [{"monument_id": "id-1", "rank": 1}]
    version = bundle.content_version(monuments, photos)
    assert len(version) == 12
    assert version == bundle.content_version(list(monuments), list(photos))
    renamed = [{"merimee_id": "PA1", "title": "Hôtel de Béthune-Sully"}]
    assert bundle.content_version(renamed, photos) != version
    assert bundle.content_version(monuments, []) != version


def test_vector_is_written_on_8_bits_with_its_scale() -> None:
    vector = np.random.default_rng(5).standard_normal(384).astype(np.float32)
    vector /= np.linalg.norm(vector)
    levels, scale = bundle.quantize(vector)
    assert len(levels) == 384
    restored = np.frombuffer(levels, dtype=np.int8).astype(np.float32) * scale
    assert np.linalg.norm(restored) == pytest.approx(1.0, abs=1e-6)
    assert float(restored @ vector) > 0.9999
    # The largest number takes the whole range of a byte.
    assert np.abs(np.frombuffer(levels, dtype=np.int8)).max() == 127
    assert bundle.quantize(np.zeros(384, dtype=np.float32)) == (bytes(384), 0.0)


def test_vectors_follow_the_photos_kept() -> None:
    files = [file("PA1", 1), file("PA1", 2), file("PA1", None), file("PA9", 1)]
    kept = bundle.without_set_aside(files, frozenset({("PA1", "File:PA1 1.jpg")}))
    monuments = [{"merimee_id": "PA1", "id": "uuid-1"}]
    unit = np.eye(384, dtype=np.float32)
    vectors = {
        "File:PA1 2.jpg": unit[0],
        "File:PA1 None.jpg": unit[1],
        "File:PA9 1.jpg": unit[2],
    }
    rows = bundle.build_vectors(kept, monuments, vectors)
    # The photo set aside has no vector; the next one takes its rank; neither a
    # photo that is not selected nor a monument outside the bundle counts.
    assert [(row["monument_id"], row["rank"]) for row in rows] == [("uuid-1", 1)]
    assert np.frombuffer(rows[0]["vector"], dtype=np.int8)[0] == 127
    assert bundle.build_vectors(kept, monuments, {}) == []
    version = bundle.content_version(monuments, [])
    assert bundle.content_version(monuments, [], rows) != version


def test_photos_set_aside_leave_their_place_to_the_next() -> None:
    files = [
        file("PA1", 1),
        file("PA1", 2),
        file("PA1", 3),
        file("PA1", 4),
        file("PA1", None),
        file("PA2", 1),
    ]
    set_aside = frozenset({("PA1", "File:PA1 2.jpg"), ("PA1", "File:PA1 None.jpg")})
    kept = bundle.without_set_aside(files, set_aside)
    assert [(row["title"], row["rank"]) for row in kept] == [
        ("File:PA1 1.jpg", 1),
        ("File:PA1 3.jpg", 2),
        ("File:PA1 4.jpg", 3),
        ("File:PA2 1.jpg", 1),
    ]
    # The lines given are left as they were.
    assert files[2]["rank"] == 3
    assert bundle.without_set_aside(files, frozenset()) == files
    assert bundle.count_selected(kept) == {"PA1": 3, "PA2": 1}


def test_photos_set_aside_are_read_from_the_check(tmp_path: Path) -> None:
    assert bundle.read_set_aside(tmp_path / "missing.parquet") == frozenset()
    pd.DataFrame(
        [
            {"merimee_id": "PA1", "title": "File:Four.jpg", "kept": False},
            {"merimee_id": "PA1", "title": "File:Façade.jpg", "kept": True},
        ]
    ).to_parquet(tmp_path / "checks.parquet")
    assert bundle.read_set_aside(tmp_path / "checks.parquet") == {
        ("PA1", "File:Four.jpg")
    }


def run_main(folder: Path, out: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Every notice of the sample is shown: the selection has its own tests.
    notices = pd.read_parquet(folder / "merimee.parquet", columns=["merimee_id"])
    notices.assign(shown=True, article="Un article").to_parquet(
        out / "selection.parquet", index=False
    )
    paths = {
        "MERIMEE_PARQUET": folder / "merimee.parquet",
        "ENTITIES_PARQUET": folder / "entities.parquet",
        "WIKIDATA_ITEMS_PARQUET": folder / "wikidata_items.parquet",
        "GEOMETRIES_PARQUET": folder / "geometries.parquet",
        "VISIBILITY_PARQUET": folder / "visibility.parquet",
        "COMMONS_FILES_PARQUET": folder / "commons_files.parquet",
        "BUNDLE_DB": out / "assets" / "lutece.db",
        "BUNDLE_JSON": out / "assets" / "bundle.json",
        "REACHES_CSV": folder / "capture_reach.csv",
        "SELECTION_PARQUET": out / "selection.parquet",
        "LANDMARKS_PARQUET": out / "landmarks.parquet",
        "LANDMARK_FILES_PARQUET": out / "landmark_files.parquet",
        "CHECKS_PARQUET": out / "reference_photo_checks.parquet",
        "EMBEDDINGS_PARQUET": out / "int8-crop.parquet",
        "MODEL_SOURCE": out / "dinov2-small-int8.onnx",
        "APP_MODEL_FILE": out / "assets" / "models" / "dinov2-small-int8.onnx",
    }
    for name, path in paths.items():
        monkeypatch.setattr(bundle, name, path)
    assert bundle.main([]) == 0


def test_real_notices_are_bundled(
    pipeline_tables: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_main(pipeline_tables, tmp_path, monkeypatch)
    path = tmp_path / "assets" / "lutece.db"
    summary = json.loads((tmp_path / "assets" / "bundle.json").read_text())
    # Nine protected notices in the sample, three photos each at most.
    assert summary["monuments"] == 9
    assert len(summary["version"]) == 12

    database = sqlite3.connect(path)
    database.row_factory = sqlite3.Row
    assert dict(database.execute("select key, value from meta").fetchall()) == {
        "version": summary["version"],
        "monuments": "9",
        "photos": str(summary["photos"]),
        "vectors": "0",
    }
    # Without the vectors of the photos, the model does not come either.
    assert "model" not in summary
    assert not (tmp_path / "assets" / "models").exists()
    assert database.execute("pragma integrity_check").fetchone()[0] == "ok"
    assert database.execute("pragma foreign_key_check").fetchall() == []
    church = dict(
        database.execute(
            "select * from monuments where merimee_id = 'PA00085795'"
        ).fetchone()
    )
    assert church["id"] == str(load_postgres.monument_id("PA00085795"))
    assert church["title"] == "Église Saint-Eustache"
    assert church["arrondissement"] == 1
    assert church["readiness"] == "ready"
    assert json.loads(church["footprint"])["type"] == "MultiPolygon"
    assert 48.86 < church["lat"] < 48.87
    assert 2.34 < church["lon"] < 2.35
    # No distance is set by hand in the sample: the GPS alone gives the reach.
    assert church["capture_reach_m"] == 0
    assert church["min_lat"] < church["lat"] < church["max_lat"]
    assert church["min_lon"] < church["lon"] < church["max_lon"]
    # The café has no name of its own. Only its inside is protected, which
    # does not keep a player from standing in front of it.
    cafe = database.execute(
        "select title, visibility, readiness from monuments"
        " where merimee_id = 'PA00085786'"
    ).fetchone()
    assert tuple(cafe) == (
        "Café-Bar, 3 rue Etienne-Marcel",
        "non_visible",
        "approximate",
    )
    ranks = database.execute(
        "select m.merimee_id, group_concat(p.rank) from photos p"
        " join monuments m on m.id = p.monument_id group by 1 order by 1"
    ).fetchall()
    assert ("PA00085795", "1,2,3") in [tuple(row) for row in ranks]
    assert database.execute("select max(rank) from photos").fetchone()[0] == 3
    first = database.execute(
        "select thumb_url, page_url, licence from photos p join monuments m"
        " on m.id = p.monument_id where m.merimee_id = 'PA75170009'"
    ).fetchone()
    assert first["page_url"].startswith("https://commons.wikimedia.org/wiki/File:")
    assert first["licence"] == "CC BY-SA 4.0"
    database.close()

    # The same inputs give the same file, byte for byte.
    written = path.read_bytes()
    run_main(pipeline_tables, tmp_path, monkeypatch)
    assert path.read_bytes() == written


def test_places_without_a_notice_are_bundled_with_the_monuments(
    pipeline_tables: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    place = landmark("Q323767", group="Tours", views=9, languages=48)
    place["commons_category"] = "Tour Montparnasse"
    shape = place.pop("geometry")
    gpd.GeoDataFrame([place], geometry=[shape], crs="EPSG:4326").to_parquet(
        tmp_path / "landmarks.parquet", index=False
    )
    names = commons.FILES_SCHEMA.names
    photos = [
        {**dict.fromkeys(names), **file("Q323767", rank), "source": "category"}
        for rank in (2, 1, None)
    ]
    write_parquet(
        from_rows(photos, commons.FILES_SCHEMA),
        commons.FILES_SCHEMA,
        tmp_path / "landmark_files.parquet",
    )
    run_main(pipeline_tables, tmp_path, monkeypatch)

    summary = json.loads((tmp_path / "assets" / "bundle.json").read_text())
    # The nine monuments of the sample, and the tower.
    assert summary["monuments"] == 10
    database = sqlite3.connect(tmp_path / "assets" / "lutece.db")
    database.row_factory = sqlite3.Row
    tower = dict(
        database.execute(
            "select * from monuments where wikidata_qid = 'Q323767'"
        ).fetchone()
    )
    assert tower["id"] == bundle.landmark_id("Q323767")
    assert tower["merimee_id"] is None
    assert tower["protection"] is None
    assert tower["title"] == "Tour Montparnasse"
    assert tower["wikipedia"] == "Tour Montparnasse"
    assert tower["readiness"] == "ready"
    assert tower["capture_reach_m"] == 1500
    assert tower["photo_count"] == 2
    ranks = database.execute(
        "select rank from photos where monument_id = ? order by rank", (tower["id"],)
    ).fetchall()
    assert [row["rank"] for row in ranks] == [1, 2]
    # The monuments keep their notice and the article that the selection found.
    church = database.execute(
        "select merimee_id, wikipedia, protection from monuments"
        " where merimee_id = 'PA00085795'"
    ).fetchone()
    assert tuple(church) == ("PA00085795", "Un article", "classé")
    assert database.execute("pragma foreign_key_check").fetchall() == []
    database.close()

    # Once its first photo is set aside, the tower shows the next one first.
    pd.DataFrame(
        [{"merimee_id": "Q323767", "title": "File:Q323767 1.jpg", "kept": False}]
    ).to_parquet(tmp_path / "reference_photo_checks.parquet")
    run_main(pipeline_tables, tmp_path, monkeypatch)
    database = sqlite3.connect(tmp_path / "assets" / "lutece.db")
    shown = database.execute(
        "select p.rank, p.page_url, m.photo_count from photos p"
        " join monuments m on m.id = p.monument_id where m.wikidata_qid = 'Q323767'"
    ).fetchall()
    database.close()
    assert shown == [(1, "https://commons.wikimedia.org/wiki/File:Q323767_2.jpg", 1)]


def test_vectors_and_their_model_go_with_the_bundle(
    pipeline_tables: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    church = pd.read_parquet(pipeline_tables / "commons_files.parquet")
    church = church[(church["merimee_id"] == "PA00085795") & church["selected"]]
    titles = list(church.sort_values("rank")["title"])
    random = np.random.default_rng(2)
    vectors = random.standard_normal((len(titles), 384)).astype(np.float32)
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    embed_references.write_embeddings(titles, vectors, tmp_path / "int8-crop.parquet")
    (tmp_path / "dinov2-small-int8.onnx").write_bytes(b"model")
    run_main(pipeline_tables, tmp_path, monkeypatch)

    summary = json.loads((tmp_path / "assets" / "bundle.json").read_text())
    assert summary["vectors"] == len(titles)
    copied = tmp_path / "assets" / "models" / "dinov2-small-int8.onnx"
    assert copied.read_bytes() == b"model"
    assert summary["model"] == export_model.checksum(copied)[:12]
    database = sqlite3.connect(tmp_path / "assets" / "lutece.db")
    stored = database.execute(
        "select v.rank, v.scale, v.vector from reference_vectors v"
        " join monuments m on m.id = v.monument_id"
        " where m.merimee_id = 'PA00085795' order by v.rank"
    ).fetchall()
    assert database.execute("pragma foreign_key_check").fetchall() == []
    database.close()
    assert [rank for rank, _, _ in stored] == list(range(1, len(titles) + 1))
    first = np.frombuffer(stored[0][2], dtype=np.int8).astype(np.float32) * stored[0][1]
    assert float(first @ vectors[0]) > 0.9999
