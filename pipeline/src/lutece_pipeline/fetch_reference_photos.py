"""Download the reference photos of the places that the app shows.

The Commons step selects, for each monument, the photos that can serve as a
reference, and the landmark places step does the same for the places that are
not monuments. The image model needs their pixels: this step fetches each of
them once, at a reduced size, and lists where they are.

Run with: uv run python -m lutece_pipeline.fetch_reference_photos
"""

import argparse
import hashlib
import logging
import re
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
import pyarrow as pa

from lutece_pipeline import ingest_commons, landmark_places, selection, web
from lutece_pipeline.paths import INTERIM_DIR
from lutece_pipeline.tables import from_rows, to_records, write_parquet
from lutece_pipeline.web import Pause

logger = logging.getLogger(__name__)

# The model reads a square of 224 px: 500 px leaves room to crop, and weighs a
# third of the 960 px that the app displays. Commons only serves a few widths.
PHOTO_WIDTH = 500
THUMBNAIL_WIDTH = re.compile(r"/\d+px-")
# Commons asks for one request at a time and no haste.
PAUSE_SECONDS = 0.1
JPEG = "image/jpeg"

FILES_PARQUET = ingest_commons.FILES_PARQUET
PLACE_FILES_PARQUET = landmark_places.FILES_PARQUET
SELECTION_PARQUET = selection.SELECTION_PARQUET
PHOTOS_FOLDER = ingest_commons.RAW_FOLDER / "photos"
INDEX_PARQUET = INTERIM_DIR / "reference_photos.parquet"

INDEX_SCHEMA = pa.schema(
    [
        # The notice of a monument, or the Wikidata item of a place without one.
        ("merimee_id", pa.string()),
        ("title", pa.string()),
        ("rank", pa.int16()),
        ("author", pa.string()),
        ("year", pa.int16()),
        # Where the photo is, from the folder of the photos.
        ("path", pa.string()),
        ("bytes", pa.int64()),
    ]
)

type Record = Mapping[str, Any]


def read_references(
    files: Sequence[Record], place_files: Sequence[Record], shown: frozenset[str]
) -> list[dict[str, Any]]:
    """The photos selected for the monuments shown and for the places, best first."""
    kept = [file for file in files if file["merimee_id"] in shown]
    selected = [file for file in [*kept, *place_files] if file["selected"]]
    return sorted(selected, key=lambda file: (file["merimee_id"], file["rank"]))


def photo_url(thumb_url: str) -> str:
    """Ask for the width that the model needs instead of the one the app shows.

    A file narrower than what the app shows has no thumbnail: its address is
    that of the original, which is taken as it is.
    """
    return THUMBNAIL_WIDTH.sub(f"/{PHOTO_WIDTH}px-", thumb_url, count=1)


def photo_path(title: str) -> str:
    """Name the file of a photo after its title, which no folder could hold."""
    digest = hashlib.sha1(title.encode("utf-8")).hexdigest()
    return f"{digest[:2]}/{digest}.jpg"


def fetch_photos(
    client: httpx.Client,
    references: Sequence[Record],
    folder: Path,
    *,
    pause: Pause = time.sleep,
) -> dict[str, int]:
    """Download the photos that are not in the folder yet, and count what happened."""
    counts = {"already_there": 0, "downloaded": 0, "gone": 0}
    addresses = {file["title"]: file["thumb_url"] for file in references}
    for title, thumb_url in addresses.items():
        destination = folder / photo_path(title)
        if destination.exists():
            counts["already_there"] += 1
            continue
        url = photo_url(thumb_url)
        response = web.get(client, url, pause=pause, accepted=(httpx.codes.NOT_FOUND,))
        pause(PAUSE_SECONDS)
        if response.status_code == httpx.codes.NOT_FOUND:
            # Deleted or renamed on Commons since the Commons step ran.
            logger.warning("%s is no longer on Commons", title)
            counts["gone"] += 1
            continue
        kind = response.headers.get("content-type", "")
        if not kind.startswith(JPEG) or not response.content:
            raise RuntimeError(f"{url} did not answer with a photo: {kind!r}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Written aside then renamed: an interrupted run leaves no half photo.
        partial = destination.with_suffix(".part")
        partial.write_bytes(response.content)
        partial.replace(destination)
        counts["downloaded"] += 1
        if counts["downloaded"] % 500 == 0:
            logger.info("Downloaded %d photos", counts["downloaded"])
    return counts


def build_index(references: Sequence[Record], folder: Path) -> pd.DataFrame:
    """One line per place and reference photo that is in the folder."""
    rows = []
    for file in references:
        path = photo_path(file["title"])
        if (folder / path).exists():
            rows.append(
                {
                    "merimee_id": file["merimee_id"],
                    "title": file["title"],
                    "rank": file["rank"],
                    "author": file["author"] or file["uploader"],
                    "year": file["year"],
                    "path": path,
                    "bytes": (folder / path).stat().st_size,
                }
            )
    return from_rows(rows, INDEX_SCHEMA)


def summarize(references: Sequence[Record], index: pd.DataFrame) -> dict[str, int]:
    """Count the photos wanted and those that are there, and the places served."""
    return {
        "references": len(references),
        "places": len({file["merimee_id"] for file in references}),
        "photos_wanted": len({file["title"] for file in references}),
        "photos_there": int(index["title"].nunique()),
        "places_with_a_photo": int(index["merimee_id"].nunique()),
        "megabytes": round(int(index.drop_duplicates("title")["bytes"].sum()) / 1e6),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Download the reference photos of the places that the app shows."
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="list the photos already downloaded without fetching the others",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    # One line per request would drown the progress of several thousand photos.
    logging.getLogger("httpx").setLevel(logging.WARNING)

    chosen = to_records(pd.read_parquet(SELECTION_PARQUET))
    shown = frozenset(row["merimee_id"] for row in chosen if row["shown"])
    references = read_references(
        to_records(pd.read_parquet(FILES_PARQUET)),
        to_records(pd.read_parquet(PLACE_FILES_PARQUET)),
        shown,
    )
    if not args.offline:
        with web.make_client() as client:
            counts = fetch_photos(client, references, PHOTOS_FOLDER)
        for label, count in counts.items():
            logger.info("  %-22s %6d", label, count)

    index = build_index(references, PHOTOS_FOLDER)
    write_parquet(index, INDEX_SCHEMA, INDEX_PARQUET)
    logger.info("Wrote %d lines to %s", len(index), INDEX_PARQUET)
    for label, count in summarize(references, index).items():
        logger.info("  %-22s %6d", label, count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
