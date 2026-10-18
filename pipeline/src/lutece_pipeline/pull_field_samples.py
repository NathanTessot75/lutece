"""Bring the samples of the field test set from the phone to the computer.

In collect mode, the app keeps each photo with all that it knew when the photo
was taken and the label that the player gave (SPEC §8). This step copies the
database of the player and the photos from the phone, through the developer
tools of Xcode, and writes the test set where the SPEC puts it: the metadata,
versioned, in `eval/testset/`; the photos, out of git, in `eval/testset/photos/`.

Run with: uv run python -m lutece_pipeline.pull_field_samples
"""

import argparse
import json
import logging
import shutil
import sqlite3
import subprocess
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa

from lutece_pipeline import export_bundle, vision
from lutece_pipeline.paths import INTERIM_DIR, PIPELINE_ROOT, RAW_DIR
from lutece_pipeline.tables import from_rows, write_parquet

logger = logging.getLogger(__name__)

APP_ID = "com.nathan.lutece"
# Where the app keeps the database of the player and the photos of the samples.
PLAYER_DATABASE = "Documents/SQLite/player.db"
SAMPLE_PHOTOS = "Documents/samples"

TESTSET_DIR = PIPELINE_ROOT.parent / "eval" / "testset"
SAMPLES_CSV = TESTSET_DIR / "samples.csv"
CANDIDATES_CSV = TESTSET_DIR / "candidates.csv"
PHOTOS_DIR = TESTSET_DIR / "photos"
# The last copy of the database, to rebuild the test set without the phone.
PLAYER_COPY = RAW_DIR / "field" / "player.db"
VECTORS_PARQUET = INTERIM_DIR / "field_vectors.parquet"
BUNDLE_DB = export_bundle.BUNDLE_DB

SAMPLE_COLUMNS = [
    "id",
    "taken_at",
    "lat",
    "lon",
    "gps_accuracy_m",
    "heading_deg",
    "heading_level",
    "photo_file",
    "label_monument_id",
    "label_title",
    "oblique",
    "hidden",
    "decision_kind",
    "decision_monuments",
    "decision_reason",
    "bundle_version",
    "model",
    "app_version",
]
CANDIDATE_COLUMNS = [
    "sample_id",
    "monument_id",
    "title",
    "distance_m",
    "offset_deg",
    "in_sight",
    "geo_score",
    "likeness",
]
VECTORS_SCHEMA = pa.schema(
    [
        ("sample_id", pa.string()),
        ("vector", pa.list_(pa.float32(), vision.DIMENSIONS)),
    ]
)

type Record = Mapping[str, Any]
# Copy a file or a folder of the app, given by its path in the app, to the computer.
type Copy = Callable[[str, Path], None]
type Run = Callable[[Sequence[str]], str]


def run(command: Sequence[str]) -> str:
    """Run a command and give what it wrote."""
    return subprocess.run(command, check=True, capture_output=True, text=True).stdout


def find_phone(run: Run = run) -> str:
    """The identifier of the iPhone paired with this computer and within reach."""
    with tempfile.TemporaryDirectory() as folder:
        listing = Path(folder) / "devices.json"
        run(["xcrun", "devicectl", "list", "devices", "--json-output", str(listing)])
        devices = json.loads(listing.read_text())["result"]["devices"]
    for device in devices:
        hardware, connection = (
            device["hardwareProperties"],
            device["connectionProperties"],
        )
        if (
            hardware.get("platform") == "iOS"
            and hardware.get("reality") == "physical"
            and connection.get("pairingState") == "paired"
        ):
            return device["identifier"]
    raise RuntimeError("No paired iPhone: plug it in or bring it near, unlocked")


def phone_copy(device: str, run: Run = run) -> Copy:
    """Copy from the app on a phone, through the developer tools of Xcode."""

    def copy(source: str, destination: Path) -> None:
        run(
            [
                "xcrun",
                "devicectl",
                "device",
                "copy",
                "from",
                "--device",
                device,
                "--domain-type",
                "appDataContainer",
                "--domain-identifier",
                APP_ID,
                "--source",
                source,
                "--destination",
                str(destination),
            ]
        )

    return copy


def simulator_copy(device: str, run: Run = run) -> Copy:
    """Copy from the app on a simulator, whose files are on this computer."""
    container = Path(
        run(["xcrun", "simctl", "get_app_container", device, APP_ID, "data"]).strip()
    )

    def copy(source: str, destination: Path) -> None:
        origin = container / source
        if origin.is_dir():
            shutil.copytree(origin, destination, dirs_exist_ok=True)
        else:
            shutil.copyfile(origin, destination)

    return copy


def pull(copy: Copy, player_copy: Path, photos_dir: Path) -> list[dict[str, Any]]:
    """Copy the database of the player, then the photos when some are missing here."""
    player_copy.parent.mkdir(parents=True, exist_ok=True)
    copy(PLAYER_DATABASE, player_copy)
    samples = read_samples(player_copy)
    names = [sample["photo_file"] for sample in samples if sample["photo_file"]]
    if any(not (photos_dir / name).exists() for name in names):
        photos_dir.mkdir(parents=True, exist_ok=True)
        copy(SAMPLE_PHOTOS, photos_dir)
    return samples


def read_samples(path: Path) -> list[dict[str, Any]]:
    """Read the samples from a copy of the database of the player, the oldest first."""
    database = sqlite3.connect(path)
    database.row_factory = sqlite3.Row
    try:
        tables = {row[0] for row in database.execute("select name from sqlite_master")}
        if "samples" not in tables:
            return []
        rows = database.execute("select * from samples order by taken_at").fetchall()
    finally:
        database.close()
    samples = []
    for row in rows:
        sample = dict(row)
        sample["candidates"] = json.loads(sample["candidates"])
        sample["decision"] = json.loads(sample["decision"])
        blob = sample.pop("vector")
        sample["vector"] = (
            None if blob is None else np.frombuffer(blob, dtype=np.float32)
        )
        samples.append(sample)
    return samples


def read_titles(path: Path) -> dict[str, str]:
    """The title of each monument of the bundle, by its identifier."""
    database = sqlite3.connect(path)
    try:
        return dict(database.execute("select id, title from monuments").fetchall())
    finally:
        database.close()


def build_tables(
    samples: Sequence[Record], titles: Mapping[str, str]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """One line per sample, and one per sample and candidate within reach."""
    sample_rows, candidate_rows = [], []
    for sample in samples:
        decision = sample["decision"]
        label = sample["label_monument_id"]
        sample_rows.append(
            {
                **{
                    column: sample[column]
                    for column in SAMPLE_COLUMNS
                    if column in sample
                },
                "label_title": titles.get(label) if label else None,
                "oblique": bool(sample["oblique"]),
                "hidden": bool(sample["hidden"]),
                "decision_kind": decision["kind"],
                "decision_monuments": ";".join(decision["monumentIds"]),
                "decision_reason": decision["reason"],
            }
        )
        for candidate in sample["candidates"]:
            candidate_rows.append(
                {
                    "sample_id": sample["id"],
                    "monument_id": candidate["monumentId"],
                    "title": titles.get(candidate["monumentId"]),
                    "distance_m": candidate["distanceM"],
                    "offset_deg": candidate["offsetDeg"],
                    "in_sight": candidate["inSight"],
                    "geo_score": candidate["geoScore"],
                    "likeness": candidate["likeness"],
                }
            )
    return (
        pd.DataFrame(sample_rows, columns=SAMPLE_COLUMNS),
        pd.DataFrame(candidate_rows, columns=CANDIDATE_COLUMNS),
    )


def build_vectors(samples: Sequence[Record]) -> pd.DataFrame:
    """The vector that the phone gave each photo, to compare with the pipeline's."""
    rows = [
        {"sample_id": sample["id"], "vector": sample["vector"].tolist()}
        for sample in samples
        if sample["vector"] is not None
    ]
    return from_rows(rows, VECTORS_SCHEMA)


def summarize(samples: pd.DataFrame, photos_dir: Path) -> dict[str, int]:
    """Count the samples, those with a monument, and the photos on the computer."""
    with_photo = samples["photo_file"].dropna()
    return {
        "samples": len(samples),
        "with_a_monument": int(samples["label_monument_id"].notna().sum()),
        "without_a_monument": int(samples["label_monument_id"].isna().sum()),
        "monuments": int(samples["label_monument_id"].nunique()),
        "photos_on_this_computer": sum(
            (photos_dir / name).exists() for name in with_photo
        ),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Bring the samples of the field test set from the phone."
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--device", help="the phone to read (default: the paired iPhone)"
    )
    source.add_argument(
        "--simulator", help="read a simulator instead, by its identifier"
    )
    source.add_argument(
        "--offline",
        action="store_true",
        help="rebuild the test set from the last copy, without the phone",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if not args.offline:
        if args.simulator:
            copy = simulator_copy(args.simulator)
        else:
            copy = phone_copy(args.device or find_phone())
        samples = pull(copy, PLAYER_COPY, PHOTOS_DIR)
    else:
        samples = read_samples(PLAYER_COPY)
    sample_table, candidate_table = build_tables(samples, read_titles(BUNDLE_DB))
    TESTSET_DIR.mkdir(parents=True, exist_ok=True)
    sample_table.to_csv(SAMPLES_CSV, index=False)
    candidate_table.to_csv(CANDIDATES_CSV, index=False)
    write_parquet(build_vectors(samples), VECTORS_SCHEMA, VECTORS_PARQUET)

    logger.info("Wrote %d samples to %s", len(sample_table), TESTSET_DIR)
    for label, count in summarize(sample_table, PHOTOS_DIR).items():
        logger.info("  %-26s %5d", label, count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
