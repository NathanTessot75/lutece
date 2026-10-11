import json
import sqlite3
from pathlib import Path

import pytest
from shapely.geometry import MultiPolygon, box

from lutece_pipeline import export_bundle as bundle
from lutece_pipeline import load_postgres

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
    rows = bundle.build_monuments(notices, [], [], places, [], {}, reaches)
    assert [row["title"] for row in rows] == [
        "Immeuble en bordure du Palais-Royal, 12 rue de Montpensier",
        "Immeuble en bordure du Palais-Royal, 14 rue de Montpensier",
        "Immeuble en bordure du Palais-Royal",
        "Hôtel de Sully",
    ]


def test_notices_without_protection_or_location_are_left_out() -> None:
    notices = [notice("PA1"), notice("PA2", protection=None), notice("PA3")]
    places = [place("PA1"), place("PA2")]
    rows = bundle.build_monuments(notices, [], [], places, [], {}, {"PA1": 50})
    assert [row["merimee_id"] for row in rows] == ["PA1"]


def test_a_monument_can_be_captured_from_twice_its_length() -> None:
    # A degree of latitude is 111 km: the square is 111 m long, 73 m wide.
    tower = box(2.36, 48.85, 2.3601, 48.8501)
    palace = box(2.37, 48.85, 2.38, 48.852)
    places = [
        place("PA1"),
        place("PA2", geometry=tower),
        place("PA3", geometry=palace),
        place("PA4", geometry=MultiPolygon([SQUARE, tower])),
    ]
    reaches = bundle.capture_reaches(places, {})
    assert reaches["PA1"] == pytest.approx(222, abs=2)
    assert reaches["PA2"] == pytest.approx(22, abs=1)
    # However long, never more than what a phone can frame.
    assert reaches["PA3"] == 300
    # In several pieces, the length is the one of the whole.
    assert reaches["PA4"] == 300


def test_a_distance_set_by_hand_can_only_extend_the_reach() -> None:
    tower = box(2.36, 48.85, 2.3601, 48.8501)
    places = [place("PA1"), place("PA2", geometry=tower)]
    reaches = bundle.capture_reaches(places, {"PA1": 100, "PA2": 800, "PA9": 500})
    assert reaches["PA1"] == pytest.approx(222, abs=2)
    assert reaches["PA2"] == 800
    assert "PA9" not in reaches


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


def run_main(folder: Path, out: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
    }
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
    # Saint-Eustache is 109 m long.
    assert church["capture_reach_m"] == pytest.approx(217, abs=3)
    assert church["min_lat"] < church["lat"] < church["max_lat"]
    assert church["min_lon"] < church["lon"] < church["max_lon"]
    # The café has no name of its own, and only its inside is protected.
    cafe = database.execute(
        "select title, readiness from monuments where merimee_id = 'PA00085786'"
    ).fetchone()
    assert tuple(cafe) == ("Café-Bar, 3 rue Etienne-Marcel", "not_ready")
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
