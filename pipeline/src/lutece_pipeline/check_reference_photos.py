"""Set aside the reference photos that look like nothing else of their place.

The Commons step reads only words: a quarter of the photos it selects show an
interior, a detail, a document or a guest rather than the building, and no
word of their name says so. The image model can tell: a view of the building
looks like the views that other people took of it. The likeness of a photo
with its place is its best cosine with the photos of the place taken by other
authors, or in other years. Under a threshold, the photo is set aside: it is
neither shown on the page of the place nor used to recognise it.

Two kinds of photos are never set aside: the image that Wikidata gives to the
place, nearly always a good view (56 of the 57 that were looked at in phase 1),
and the photos that `review/landmarks.csv` names, which were looked at.

Run with: uv run python -m lutece_pipeline.check_reference_photos
"""

import argparse
import csv
import logging
from collections.abc import Mapping, Sequence
from itertools import pairwise
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa

from lutece_pipeline import (
    embed_references,
    evaluate_retrieval,
    fetch_reference_photos,
    landmark_places,
    vision,
)
from lutece_pipeline.paths import INTERIM_DIR, REVIEW_DIR
from lutece_pipeline.tables import from_rows, to_records, write_parquet

logger = logging.getLogger(__name__)

# Under this likeness, two photos in three that were looked at do not show the
# building (see the README, "Photos écartées").
UNLIKE_BELOW = 0.35
# The vectors the check reads: the model as trained, the centre of the photo.
MODEL, FRAMING = "float32", "crop"
# The bands of likeness in which the labelled photos are counted.
BANDS = (0.15, 0.25, 0.35, 0.45, 0.55)
GOOD = "ok"

INDEX_PARQUET = fetch_reference_photos.INDEX_PARQUET
FILES_PARQUET = fetch_reference_photos.FILES_PARQUET
PLACE_FILES_PARQUET = fetch_reference_photos.PLACE_FILES_PARQUET
REVIEW_CSV = landmark_places.REVIEW_CSV
EMBEDDINGS_FOLDER = embed_references.EMBEDDINGS_FOLDER
LABELS_CSV = REVIEW_DIR / "reference_photo_labels.csv"
CHECKS_PARQUET = INTERIM_DIR / "reference_photo_checks.parquet"
EVALUATION_CSV = INTERIM_DIR / "reference_photo_checks_evaluation.csv"

CHECKS_SCHEMA = pa.schema(
    [
        ("merimee_id", pa.string()),
        ("title", pa.string()),
        # None when no other author photographed the place: nothing to compare.
        ("likeness", pa.float32()),
        ("kept", pa.bool_()),
        # unlike_its_place, or why a photo was kept whatever its likeness.
        ("why", pa.string()),
    ]
)

type Record = Mapping[str, Any]
type Key = tuple[str, str]


def likeness_with_place(photos: evaluate_retrieval.Photos) -> list[float | None]:
    """For each line, the best cosine with the photos of its place from other sessions."""
    lines: dict[str, list[int]] = {}
    for line, place in enumerate(photos.places):
        lines.setdefault(place, []).append(line)
    likeness: list[float | None] = [None] * len(photos.places)
    for members in lines.values():
        vectors = photos.vectors[members]
        cosines = vectors @ vectors.T
        sessions = np.array([photos.sessions[line] for line in members])
        cosines[sessions[:, None] == sessions[None, :]] = -np.inf
        best = cosines.max(axis=1)
        for line, value in zip(members, best, strict=True):
            likeness[line] = float(value) if np.isfinite(value) else None
    return likeness


def exempt_photos(
    files: Sequence[Record], decisions: Sequence[landmark_places.Decision]
) -> dict[Key, str]:
    """The photos never set aside, with the reason."""
    exempt = {
        (file["merimee_id"], file["title"]): "main_image"
        for file in files
        if file["source"] == "main_image"
    }
    for decision in decisions:
        for photo in decision.photos:
            exempt[(decision.qid, f"File:{photo}")] = "named_by_review"
    return exempt


def check(
    index: Sequence[Record],
    titles: Sequence[str],
    vectors: vision.Vectors,
    exempt: Mapping[Key, str],
) -> pd.DataFrame:
    """One line per place and reference photo: its likeness, and whether it is kept."""
    photos = evaluate_retrieval.gather(index, titles, vectors)
    likeness = likeness_with_place(photos)
    rows = []
    for place, title, value in zip(photos.places, photos.titles, likeness, strict=True):
        unlike = value is not None and value < UNLIKE_BELOW
        why = exempt.get((place, title)) if unlike else None
        rows.append(
            {
                "merimee_id": place,
                "title": title,
                "likeness": value,
                "kept": not unlike or why is not None,
                "why": why or ("unlike_its_place" if unlike else None),
            }
        )
    return from_rows(rows, CHECKS_SCHEMA)


def band_of(likeness: float) -> str:
    """Name the band of likeness a photo falls in: "<0.15", "0.15-0.25"… ">=0.55"."""
    if likeness < BANDS[0]:
        return f"<{BANDS[0]}"
    for low, high in pairwise(BANDS):
        if likeness < high:
            return f"{low}-{high}"
    return f">={BANDS[-1]}"


def read_labels(path: Path) -> list[dict[str, str]]:
    """Read what a reviewer saw on a sample of the photos."""
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def evaluate(checks: pd.DataFrame, labels: Sequence[Record]) -> pd.DataFrame:
    """Count, band by band, the photos and the good views among those looked at."""
    likeness = {
        (row["merimee_id"], row["title"]): row["likeness"]
        for row in to_records(checks)
        if row["likeness"] is not None
    }
    seen = [
        (band_of(likeness[key]), label["label"] == GOOD)
        for label in labels
        if (key := (label["merimee_id"], label["title"])) in likeness
    ]
    rows = []
    for band in dict.fromkeys(band_of(value) for value in [-1.0, *BANDS]):
        in_band = [good for name, good in seen if name == band]
        photos = sum(band_of(value) == band for value in likeness.values())
        rows.append(
            {
                "band": band,
                "photos": photos,
                "looked_at": len(in_band),
                "good_views": sum(in_band),
                "share_good": round(sum(in_band) / len(in_band), 2)
                if in_band
                else None,
            }
        )
    return pd.DataFrame(rows)


def summarize(checks: pd.DataFrame) -> dict[str, int]:
    """Count the photos checked, set aside and spared, and the places left bare."""
    kept = checks[checks["kept"]]
    places = checks["merimee_id"].unique()
    left = kept.groupby("merimee_id").size().reindex(places, fill_value=0)
    return {
        "photos": len(checks),
        "without_another_author": int(checks["likeness"].isna().sum()),
        "set_aside": int((~checks["kept"]).sum()),
        "spared_main_image": int((checks["why"] == "main_image").sum()),
        "spared_named_by_review": int((checks["why"] == "named_by_review").sum()),
        "places": len(places),
        "places_left_without_photo": int((left == 0).sum()),
        "places_left_with_1_or_2": int(left.between(1, 2).sum()),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Set aside the reference photos that look like nothing else of their place."
    )
    parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    index = to_records(pd.read_parquet(INDEX_PARQUET))
    titles, vectors = embed_references.read_embeddings(
        EMBEDDINGS_FOLDER / embed_references.embeddings_name(MODEL, FRAMING)
    )
    files = to_records(pd.read_parquet(FILES_PARQUET))
    files += to_records(pd.read_parquet(PLACE_FILES_PARQUET))
    exempt = exempt_photos(files, landmark_places.read_review(REVIEW_CSV))
    checks = check(index, titles, vectors, exempt)
    write_parquet(checks, CHECKS_SCHEMA, CHECKS_PARQUET)
    logger.info("Wrote %d lines to %s", len(checks), CHECKS_PARQUET)
    for label, count in summarize(checks).items():
        logger.info("  %-28s %5d", label, count)

    labels = read_labels(LABELS_CSV)
    if labels:
        evaluation = evaluate(checks, labels)
        evaluation.to_csv(EVALUATION_CSV, index=False)
        for row in evaluation.itertuples():
            logger.info(
                "  likeness %-10s %5d photos, %2d good views of %2d looked at",
                row.band,
                row.photos,
                row.good_views,
                row.looked_at,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
