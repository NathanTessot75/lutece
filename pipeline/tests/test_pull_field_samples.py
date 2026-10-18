import json
import sqlite3
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from lutece_pipeline import pull_field_samples as pull
from lutece_pipeline import vision

# The table that the app creates (apps/mobile/src/db/PlayerDatabase.tsx).
SAMPLES_TABLE = """
create table samples (
  id text primary key, taken_at text not null, lat real not null, lon real not null,
  gps_accuracy_m real not null, heading_deg real, heading_level integer,
  photo_file text, vector blob, candidates text not null, decision text not null,
  label_monument_id text, oblique integer not null, hidden integer not null,
  bundle_version text not null, model text not null, app_version text not null
) strict
"""


def sample(id_: str, taken_at: str, **changes: object) -> dict[str, object]:
    """A sample as the app writes it."""
    vector = np.arange(vision.DIMENSIONS, dtype=np.float32) / 1000
    row = {
        "id": id_,
        "taken_at": taken_at,
        "lat": 48.8462,
        "lon": 2.3443,
        "gps_accuracy_m": 6.0,
        "heading_deg": 92.5,
        "heading_level": 3,
        "photo_file": f"{id_}.jpg",
        "vector": vector.tobytes(),
        "candidates": json.dumps(
            [
                {
                    "monumentId": "pantheon",
                    "distanceM": 71.2,
                    "offsetDeg": 3.0,
                    "inSight": True,
                    "geoScore": 0.62,
                    "likeness": 0.81,
                },
                {
                    "monumentId": "lycee",
                    "distanceM": 140.0,
                    "offsetDeg": -48.0,
                    "inSight": False,
                    "geoScore": 0,
                    "likeness": None,
                },
            ]
        ),
        "decision": json.dumps(
            {"kind": "capture", "monumentIds": ["pantheon"], "reason": None}
        ),
        "label_monument_id": "pantheon",
        "oblique": 0,
        "hidden": 1,
        "bundle_version": "d7eb8420d465",
        "model": "056d387b1e31",
        "app_version": "1.0.0",
    }
    return row | changes


def player_database(path: Path, samples: Sequence[dict[str, object]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    database = sqlite3.connect(path)
    database.execute(SAMPLES_TABLE)
    for row in samples:
        marks = ", ".join(f":{key}" for key in row)
        database.execute(
            f"insert into samples ({', '.join(row)}) values ({marks})", row
        )
    database.commit()
    database.close()
    return path


def bundle(path: Path) -> Path:
    database = sqlite3.connect(path)
    database.execute("create table monuments (id text primary key, title text)")
    database.executemany(
        "insert into monuments values (?, ?)",
        [("pantheon", "Panthéon"), ("lycee", "Lycée Saint-Louis")],
    )
    database.commit()
    database.close()
    return path


SAMPLES = [
    sample("b", "2026-10-19T10:05:00.000Z"),
    # A trap: a photo of no monument of the app, with no camera at hand.
    sample(
        "a",
        "2026-10-19T09:00:00.000Z",
        photo_file=None,
        vector=None,
        label_monument_id=None,
        decision=json.dumps(
            {"kind": "nothing", "monumentIds": [], "reason": "not_recognised"}
        ),
    ),
]


def test_samples_are_read_from_a_copy_of_the_player_database(tmp_path: Path) -> None:
    samples = pull.read_samples(player_database(tmp_path / "player.db", SAMPLES))
    assert [row["id"] for row in samples] == ["a", "b"]
    first, second = samples
    assert first["vector"] is None
    assert second["vector"].dtype == np.float32
    assert second["vector"][:2].tolist() == pytest.approx([0.0, 0.001])
    assert second["candidates"][0]["monumentId"] == "pantheon"
    assert second["decision"] == {
        "kind": "capture",
        "monumentIds": ["pantheon"],
        "reason": None,
    }
    # A phone on which the collect mode was never opened has no samples yet.
    empty = tmp_path / "empty.db"
    sqlite3.connect(empty).close()
    assert pull.read_samples(empty) == []


def test_test_set_has_a_line_per_sample_and_per_candidate(tmp_path: Path) -> None:
    samples = pull.read_samples(player_database(tmp_path / "player.db", SAMPLES))
    titles = pull.read_titles(bundle(tmp_path / "lutece.db"))
    sample_table, candidate_table = pull.build_tables(samples, titles)

    assert list(sample_table.columns) == pull.SAMPLE_COLUMNS
    trap, shot = sample_table.to_dict("records")
    assert shot["label_title"] == "Panthéon"
    assert (shot["oblique"], shot["hidden"]) == (False, True)
    assert (shot["decision_kind"], shot["decision_monuments"]) == (
        "capture",
        "pantheon",
    )
    assert pd.isna(trap["label_title"])
    assert (trap["decision_kind"], trap["decision_reason"]) == (
        "nothing",
        "not_recognised",
    )

    assert list(candidate_table.columns) == pull.CANDIDATE_COLUMNS
    assert len(candidate_table) == 4
    lycee = candidate_table[candidate_table["monument_id"] == "lycee"].iloc[0]
    assert (lycee["title"], lycee["in_sight"]) == ("Lycée Saint-Louis", False)
    assert pd.isna(lycee["likeness"])

    vectors = pull.build_vectors(samples)
    assert list(vectors["sample_id"]) == ["b"]
    assert pull.summarize(sample_table, tmp_path) == {
        "samples": 2,
        "with_a_monument": 1,
        "without_a_monument": 1,
        "monuments": 1,
        "photos_on_this_computer": 0,
    }


def test_the_phone_is_found_and_read_through_the_developer_tools(
    tmp_path: Path,
) -> None:
    commands: list[list[str]] = []

    def run(command: Sequence[str]) -> str:
        commands.append(list(command))
        if "list" in command:
            listing = Path(command[command.index("--json-output") + 1])
            devices = [
                {
                    "identifier": "WATCH",
                    "hardwareProperties": {
                        "platform": "watchOS",
                        "reality": "physical",
                    },
                    "connectionProperties": {"pairingState": "paired"},
                },
                {
                    "identifier": "PHONE",
                    "hardwareProperties": {"platform": "iOS", "reality": "physical"},
                    "connectionProperties": {"pairingState": "paired"},
                },
            ]
            listing.write_text(json.dumps({"result": {"devices": devices}}))
        return ""

    assert pull.find_phone(run) == "PHONE"
    copy = pull.phone_copy("PHONE", run)
    copy("Documents/SQLite/player.db", tmp_path / "player.db")
    assert commands[-1] == [
        "xcrun",
        "devicectl",
        "device",
        "copy",
        "from",
        "--device",
        "PHONE",
        "--domain-type",
        "appDataContainer",
        "--domain-identifier",
        "com.nathan.lutece",
        "--source",
        "Documents/SQLite/player.db",
        "--destination",
        str(tmp_path / "player.db"),
    ]

    def nothing(command: Sequence[str]) -> str:
        listing = Path(command[command.index("--json-output") + 1])
        listing.write_text(json.dumps({"result": {"devices": []}}))
        return ""

    with pytest.raises(RuntimeError, match="No paired iPhone"):
        pull.find_phone(nothing)


def test_photos_are_copied_only_when_some_are_missing(tmp_path: Path) -> None:
    container = tmp_path / "container"
    player_database(container / pull.PLAYER_DATABASE, SAMPLES)
    (container / pull.SAMPLE_PHOTOS).mkdir(parents=True)
    (container / pull.SAMPLE_PHOTOS / "b.jpg").write_bytes(b"photo")
    copy = pull.simulator_copy("SIM", lambda command: f"{container}\n")

    copied: list[str] = []

    def counting(source: str, destination: Path) -> None:
        copied.append(source)
        copy(source, destination)

    photos = tmp_path / "photos"
    samples = pull.pull(counting, tmp_path / "raw" / "player.db", photos)
    assert [row["id"] for row in samples] == ["a", "b"]
    assert (photos / "b.jpg").read_bytes() == b"photo"
    assert copied == [pull.PLAYER_DATABASE, pull.SAMPLE_PHOTOS]
    # Once the photos are here, only the database is read again.
    pull.pull(counting, tmp_path / "raw" / "player.db", photos)
    assert copied[2:] == [pull.PLAYER_DATABASE]


def test_test_set_is_rebuilt_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    testset = tmp_path / "testset"
    paths = {
        "TESTSET_DIR": testset,
        "SAMPLES_CSV": testset / "samples.csv",
        "CANDIDATES_CSV": testset / "candidates.csv",
        "PHOTOS_DIR": testset / "photos",
        "PLAYER_COPY": player_database(tmp_path / "raw" / "player.db", SAMPLES),
        "VECTORS_PARQUET": tmp_path / "vectors.parquet",
        "BUNDLE_DB": bundle(tmp_path / "lutece.db"),
    }
    for name, path in paths.items():
        monkeypatch.setattr(pull, name, path)

    def no_phone(*args: object, **kwargs: object) -> None:
        raise AssertionError("the offline run must not reach the phone")

    monkeypatch.setattr(pull, "run", no_phone)
    assert pull.main(["--offline"]) == 0

    samples = pd.read_csv(testset / "samples.csv")
    assert list(samples["id"]) == ["a", "b"]
    assert len(pd.read_csv(testset / "candidates.csv")) == 4
    assert len(pd.read_parquet(tmp_path / "vectors.parquet")) == 1
