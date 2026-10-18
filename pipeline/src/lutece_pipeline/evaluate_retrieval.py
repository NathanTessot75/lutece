"""Measure, from the desk, how well the image model tells the places apart.

Each reference photo plays in turn the photo of a player. It is compared with
the other photos of its place and with those of the places around, as the app
will compare a capture with the photos of its candidates. The step tells how
often the right place comes first, and how well a threshold on the likeness
separates the right place from a wrong one.

The photos of a place taken by the same author in the same year are left out
of what a photo is compared with: they are often the same view a few seconds
apart, which no player's photo will be.

These figures are a first idea, not the answer: the photos of Commons are
cleaner than those of a phone in the street (SPEC §6.3). The field test set
of phase 4 will tell.

Run with: uv run python -m lutece_pipeline.evaluate_retrieval
"""

import argparse
import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from lutece_pipeline import (
    embed_references,
    export_model,
    fetch_reference_photos,
    geometry,
    landmark_places,
    vision,
)
from lutece_pipeline.geo import LAMBERT_93
from lutece_pipeline.paths import INTERIM_DIR, PROCESSED_DIR

logger = logging.getLogger(__name__)

# SPEC §6.1: two places further apart are never candidates of the same capture
# on the strength of the GPS alone.
NEIGHBOUR_M = 150.0
# The shares of wrong places that a threshold may let through, and the shares
# of right places that it may turn down.
FALSE_ACCEPTS = (0.01, 0.05, 0.10)
FALSE_REFUSALS = (0.01, 0.05, 0.10)
# The rules of the app (src/features/capture/decision.ts), read on these photos:
# how far ahead of the second the first place must be to be taken without
# asking, and under which likeness nothing is recognised.
CLEAR_LEADS = (0.05, 0.10, 0.15)
RECOGNISED_FROM = (0.35, 0.42, 0.50)
SEED = 0

INDEX_PARQUET = fetch_reference_photos.INDEX_PARQUET
GEOMETRIES_PARQUET = geometry.GEOMETRIES_PARQUET
PLACES_PARQUET = landmark_places.PLACES_PARQUET
EMBEDDINGS_FOLDER = embed_references.EMBEDDINGS_FOLDER
REPORT_JSON = PROCESSED_DIR / "retrieval_evaluation.json"
# Written by the check of the reference photos, which reads this step's module:
# named here rather than imported.
CHECKS_PARQUET = INTERIM_DIR / "reference_photo_checks.parquet"

type Record = Mapping[str, Any]


@dataclass(frozen=True)
class Photos:
    """The reference photos, one line per place and photo, with their vectors."""

    places: list[str]
    titles: list[str]
    # Who took the photo and in which year: two photos of a session look alike.
    sessions: list[str]
    vectors: vision.Vectors


def read_footprints(
    monuments: gpd.GeoDataFrame, places: gpd.GeoDataFrame
) -> gpd.GeoSeries:
    """The outlines of the monuments and of the places, by identifier, in metres."""
    outlines = pd.concat(
        [
            monuments.set_index("merimee_id").geometry.to_crs(LAMBERT_93),
            places.set_index("qid").geometry.to_crs(LAMBERT_93),
        ]
    )
    return gpd.GeoSeries(outlines, crs=LAMBERT_93)


def find_neighbours(footprints: gpd.GeoSeries, distance: float) -> dict[str, list[str]]:
    """For each place, those whose outline lies within the distance of its own."""
    reach = footprints.buffer(distance)
    near, found = footprints.sindex.query(reach, predicate="intersects")
    neighbours: dict[str, list[str]] = {}
    for left, right in zip(near, found, strict=True):
        if left != right:
            neighbours.setdefault(footprints.index[left], []).append(
                footprints.index[right]
            )
    return {place: sorted(others) for place, others in neighbours.items()}


def gather(
    index: Sequence[Record], titles: Sequence[str], vectors: vision.Vectors
) -> Photos:
    """Give each line of the index its vector; a photo without one is left out."""
    position = {title: line for line, title in enumerate(titles)}
    kept = [row for row in index if row["title"] in position]
    return Photos(
        places=[row["merimee_id"] for row in kept],
        titles=[row["title"] for row in kept],
        sessions=[
            f"{row['author']}|{row['year']}" if row["author"] else row["title"]
            for row in kept
        ],
        vectors=vectors[[position[row["title"]] for row in kept]],
    )


def score_queries(
    photos: Photos, neighbours: Mapping[str, Sequence[str]]
) -> tuple[pd.DataFrame, np.ndarray]:
    """Play each photo as a capture: one line per photo, and the likeness of
    each photo with each of the places around its own.

    The likeness of a photo with a place is the best cosine between its vector
    and those of the reference photos of the place (SPEC §6.1).
    """
    lines: dict[str, list[int]] = {}
    for line, place in enumerate(photos.places):
        lines.setdefault(place, []).append(line)
    everywhere = sorted(lines)
    random = np.random.default_rng(SEED)

    rows, wrong = [], []
    for line, place in enumerate(photos.places):
        session = photos.sessions[line]
        own = [other for other in lines[place] if photos.sessions[other] != session]
        if not own:
            continue
        likeness = photos.vectors @ photos.vectors[line]
        around = []
        for other in neighbours.get(place, ()):
            # A file may serve two places: it is not compared with itself.
            references = [
                ref
                for ref in lines.get(other, ())
                if photos.titles[ref] != photos.titles[line]
            ]
            if references:
                around.append(float(likeness[references].max()))
        far = [
            other
            for other in everywhere
            if other != place and other not in neighbours.get(place, ())
        ]
        elsewhere = far[random.integers(len(far))] if far else None
        ranked = sorted(around, reverse=True)
        rows.append(
            {
                "place": place,
                "title": photos.titles[line],
                "own": float(likeness[own].max()),
                "candidates": 1 + len(around),
                "best_around": ranked[0] if ranked else np.nan,
                "second_around": ranked[1] if len(ranked) > 1 else np.nan,
                "elsewhere": (
                    float(likeness[lines[elsewhere]].max()) if elsewhere else np.nan
                ),
            }
        )
        wrong += around
    return pd.DataFrame(rows), np.array(wrong, dtype=np.float64)


def separation(right: np.ndarray, wrong: np.ndarray) -> float:
    """The chance that a right place looks more like the photo than a wrong one."""
    labels = np.concatenate([np.ones(len(right)), np.zeros(len(wrong))])
    return float(roc_auc_score(labels, np.concatenate([right, wrong])))


def read_rules(queries: pd.DataFrame) -> dict[str, list[dict[str, float]]]:
    """What the rules of the app would do with the photos played as captures.

    A place is taken without asking when the photo looks more like it than
    like the second by a clear lead; the share of such captures, and of right
    ones among them. A shot is refused when no candidate reaches a likeness;
    the share of photos refused although they show their place.
    """
    contested = queries[queries["candidates"] > 1]
    likeness = contested[["own", "best_around", "second_around"]].to_numpy()
    ordered = np.sort(np.nan_to_num(likeness, nan=-np.inf), axis=1)
    lead = ordered[:, -1] - ordered[:, -2]
    right = (contested["own"] > contested["best_around"]).to_numpy()
    leads = []
    for clear in CLEAR_LEADS:
        taken = lead >= clear
        leads.append(
            {
                "clear_lead": clear,
                "taken_without_asking": round(float(taken.mean()), 3),
                "right_among_them": round(float(right[taken].mean()), 3),
            }
        )
    best = np.fmax(queries["own"].to_numpy(), queries["best_around"].to_numpy())
    refusals = [
        {"recognised_from": level, "refused": round(float((best < level).mean()), 3)}
        for level in RECOGNISED_FROM
    ]
    return {"leads": leads, "refusals": refusals}


def measure(queries: pd.DataFrame, wrong: np.ndarray) -> dict[str, Any]:
    """Sum up what the photos played as captures say of the model."""
    contested = queries[queries["candidates"] > 1]
    own = queries["own"].to_numpy()
    elsewhere = queries["elsewhere"].dropna().to_numpy()
    # The same curve read both ways: what a strict threshold costs in right
    # places turned down, and what a lenient one still keeps out.
    strict, lenient = [], []
    for share in FALSE_ACCEPTS:
        threshold = float(np.quantile(wrong, 1 - share))
        strict.append(
            {
                "false_accept": share,
                "threshold": round(threshold, 3),
                "false_refuse": round(float((own <= threshold).mean()), 3),
            }
        )
    for share in FALSE_REFUSALS:
        threshold = float(np.quantile(own, share))
        lenient.append(
            {
                "false_refuse": share,
                "threshold": round(threshold, 3),
                "around_kept_out": round(float((wrong < threshold).mean()), 3),
                "elsewhere_kept_out": round(float((elsewhere < threshold).mean()), 3),
            }
        )
    return {
        "captures": len(queries),
        "places": int(queries["place"].nunique()),
        "captures_with_places_around": len(contested),
        "candidates_on_average": round(float(contested["candidates"].mean()), 2),
        "first_by_chance": round(float((1 / contested["candidates"]).mean()), 3),
        "first": round(float((contested["own"] > contested["best_around"]).mean()), 3),
        "separation_from_places_around": round(separation(own, wrong), 3),
        "separation_from_elsewhere": round(separation(own, elsewhere), 3),
        "likeness_own_median": round(float(np.median(own)), 3),
        "likeness_around_median": round(float(np.median(wrong)), 3),
        "likeness_elsewhere_median": round(float(np.median(elsewhere)), 3),
        "strict_thresholds": strict,
        "lenient_thresholds": lenient,
        **read_rules(queries),
    }


def agreement(expected: vision.Vectors, given: vision.Vectors) -> dict[str, float]:
    """How close the vectors of a lighter model are to those of the trained one."""
    cosines = (expected * given).sum(axis=1)
    return {
        "mean": round(float(cosines.mean()), 4),
        "least": round(float(cosines.min()), 4),
    }


def evaluate(
    index: Sequence[Record],
    neighbours: Mapping[str, Sequence[str]],
    folder: Path,
    set_aside: frozenset[tuple[str, str]] = frozenset(),
) -> list[dict[str, Any]]:
    """Measure every set of vectors found in the folder, with all the photos
    and, when some were set aside, with those that remain."""
    kept = [row for row in index if (row["merimee_id"], row["title"]) not in set_aside]
    sets = [("all", index)] + ([("kept", kept)] if set_aside else [])
    runs = []
    trained: dict[str, tuple[list[str], vision.Vectors]] = {}
    for model in sorted(export_model.FILES):
        for framing in vision.FRAMINGS:
            path = folder / embed_references.embeddings_name(model, framing)
            if not path.exists():
                continue
            titles, vectors = embed_references.read_embeddings(path)
            for photos, rows in sets:
                queries, wrong = score_queries(
                    gather(rows, titles, vectors), neighbours
                )
                run = {"model": model, "framing": framing, "photos": photos}
                run |= measure(queries, wrong)
                if model == "float32":
                    trained[framing] = (titles, vectors)
                elif framing in trained and trained[framing][0] == titles:
                    run["agreement_with_float32"] = agreement(
                        trained[framing][1], vectors
                    )
                runs.append(run)
    return runs


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure how well the image model tells the places apart."
    )
    parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    footprints = read_footprints(
        gpd.read_parquet(GEOMETRIES_PARQUET), gpd.read_parquet(PLACES_PARQUET)
    )
    index = pd.read_parquet(INDEX_PARQUET).to_dict("records")
    with_photos = sorted({row["merimee_id"] for row in index})
    neighbours = find_neighbours(footprints.loc[with_photos], NEIGHBOUR_M)
    set_aside = frozenset()
    if CHECKS_PARQUET.exists():
        checks = pd.read_parquet(CHECKS_PARQUET)
        aside = checks[~checks["kept"]]
        set_aside = frozenset(zip(aside["merimee_id"], aside["title"], strict=True))
    runs = evaluate(index, neighbours, EMBEDDINGS_FOLDER, set_aside)

    report = {"neighbour_m": NEIGHBOUR_M, "runs": runs}
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    logger.info("Wrote %d measures to %s", len(runs), REPORT_JSON)
    for run in runs:
        logger.info(
            "  %-8s %-7s %-4s first %.3f (chance %.3f)   separation %.3f around, %.3f elsewhere",
            run["model"],
            run["framing"],
            run["photos"],
            run["first"],
            run["first_by_chance"],
            run["separation_from_places_around"],
            run["separation_from_elsewhere"],
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
