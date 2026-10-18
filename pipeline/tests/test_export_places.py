import json
import sqlite3
from pathlib import Path

import pytest

from lutece_pipeline import export_places

SQUARE = (
    '{"type":"MultiPolygon","coordinates":[[[[2.35,48.85],[2.351,48.85],'
    "[2.351,48.851],[2.35,48.851],[2.35,48.85]]]]}"
)


def make_bundle(folder: Path) -> None:
    database = sqlite3.connect(folder / "lutece.db")
    database.execute(
        "create table monuments (id text, title text, lat real, lon real, footprint text,"
        " capture_reach_m integer, arrondissement integer, rarity_tier text)"
    )
    database.executemany(
        "insert into monuments values (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            ("b-id", "Hôtel d'Aumont", 48.8505, 2.3505, SQUARE, 0, 4, "légendaire"),
            ("a-id", "Tour Eiffel", 48.858, 2.2945, SQUARE, 800, 7, None),
        ],
    )
    database.commit()
    database.close()
    (folder / "bundle.json").write_text(json.dumps({"version": "abc123"}))


def test_values_are_written_for_sql() -> None:
    assert export_places.literal("Hôtel d'Aumont") == "'Hôtel d''Aumont'"
    assert export_places.literal(None) == "null"
    assert export_places.literal(800) == "800"


def test_the_seed_inserts_or_updates_each_place(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_bundle(tmp_path)
    for name, path in {
        "BUNDLE_DB": tmp_path / "lutece.db",
        "BUNDLE_JSON": tmp_path / "bundle.json",
        "SEED_SQL": tmp_path / "seeds" / "places.sql",
    }.items():
        monkeypatch.setattr(export_places, name, path)

    assert export_places.main([]) == 0
    seed = (tmp_path / "seeds" / "places.sql").read_text(encoding="utf-8")
    assert seed.startswith("-- The places of the app")
    assert "insert into public.places (id, title, location, footprint, reach_m," in seed
    # Sorted by identifier, so that the file changes only with the bundle.
    assert seed.index("'a-id'") < seed.index("'b-id'")
    assert "'Hôtel d''Aumont'" in seed
    assert "extensions.st_geogfromtext('SRID=4326;POINT(2.3505 48.8505)')" in seed
    assert f"st_geomfromgeojson('{SQUARE}')" in seed
    assert "800, 7, null, 'abc123')" in seed
    assert seed.rstrip().endswith("bundle_version = excluded.bundle_version;")
