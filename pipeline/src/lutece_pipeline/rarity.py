"""Step 9 - how rare each place of the app is: the less known, the more points.

SPEC §5.5 measures how known a monument is and turns the measure round: a
place that few people know is worth more than a famous one, which sends the
players off the beaten track. The measure is the one that chose the places the
app shows (step `selection`): the readings of the article in a year and the
number of languages that have one, each as a place among the others from 0 to
1, and their mean. It is taken again among the places that the app shows, the
protected monuments and the places that are not, so that the tiers share them
out in the proportions decided. The number of photos on Commons is left out,
as for the selection: a known place may have none in its category.

Run with: uv run python -m lutece_pipeline.rarity
"""

import argparse
import logging
from collections.abc import Mapping, Sequence
from typing import Any

import pandas as pd
import pyarrow as pa

from lutece_pipeline import ingest_merimee, landmark_places, selection
from lutece_pipeline.paths import INTERIM_DIR
from lutece_pipeline.tables import from_rows, to_records, write_parquet

logger = logging.getLogger(__name__)

# The tiers, the best known first, and the share of the places in each
# (decision of 18 October 2026). The app gives each tier its points.
TIERS: tuple[tuple[str, float], ...] = (
    ("commun", 0.40),
    ("peu_commun", 0.30),
    ("rare", 0.20),
    ("légendaire", 0.10),
)

SELECTION_PARQUET = selection.SELECTION_PARQUET
LANDMARKS_PARQUET = landmark_places.PLACES_PARQUET
MERIMEE_PARQUET = ingest_merimee.OUTPUT_PARQUET
RARITY_PARQUET = INTERIM_DIR / "rarity.parquet"
# Every place, the best known first, to check the tiers by hand.
RANKING_CSV = INTERIM_DIR / "rarity_ranking.csv"

SCHEMA = pa.schema(
    [
        # The Mérimée reference of a monument, or the Wikidata item of a place
        # without a notice.
        ("key", pa.string()),
        ("name", pa.string()),
        ("views", pa.int64()),
        ("languages", pa.int32()),
        # From 0 to 1: the mean of the two places, 1 for the best known.
        ("notoriety", pa.float64()),
        # 1 minus the notoriety: the higher, the rarer.
        ("rarity_score", pa.float64()),
        # 1 for the best known.
        ("rank", pa.int32()),
        ("rarity_tier", pa.string()),
    ]
)

type Record = Mapping[str, Any]


def gather(
    chosen: Sequence[Record], notices: Sequence[Record], places: Sequence[Record]
) -> list[dict[str, Any]]:
    """The places that the app shows, with the readings and languages of each."""
    names = {notice["merimee_id"]: notice["name"] for notice in notices}
    gathered = [
        {
            "key": row["merimee_id"],
            "name": names.get(row["merimee_id"]),
            "views": row["views"],
            "languages": row["languages"],
        }
        for row in chosen
        if row["shown"]
    ]
    gathered += [
        {
            "key": place["qid"],
            "name": place["title"],
            "views": place["views"],
            "languages": place["languages"],
        }
        for place in places
    ]
    return gathered


def tier_sizes(count: int, tiers: Sequence[tuple[str, float]] = TIERS) -> list[int]:
    """How many places go in each tier: the last one takes what rounding leaves."""
    sizes = [round(share * count) for _, share in tiers[:-1]]
    return [*sizes, count - sum(sizes)]


def rate(
    places: Sequence[Record], tiers: Sequence[tuple[str, float]] = TIERS
) -> pd.DataFrame:
    """Rank the places from the best known, and cut the ranking into tiers.

    A place without readings or languages counts as the least known by that
    measure. Places that tie are told apart by their key, so that the tiers do
    not change from one run to the next.
    """
    measures = pd.DataFrame(
        {
            name: [
                float(-1 if place[name] is None else place[name]) for place in places
            ]
            for name in ("views", "languages")
        }
    )
    notoriety = measures.rank(pct=True).mean(axis=1).tolist() if places else []
    order = sorted(
        range(len(places)), key=lambda index: (-notoriety[index], places[index]["key"])
    )
    labels = [
        name
        for (name, _), size in zip(tiers, tier_sizes(len(places), tiers), strict=True)
        for _ in range(size)
    ]
    rows = [
        {
            **places[index],
            "notoriety": notoriety[index],
            "rarity_score": 1 - notoriety[index],
            "rank": rank,
            "rarity_tier": label,
        }
        for rank, (index, label) in enumerate(zip(order, labels, strict=True), start=1)
    ]
    return from_rows(rows, SCHEMA)


def summarize(rated: pd.DataFrame) -> dict[str, str]:
    """Count the places of each tier, and the readings of the article they span."""
    summary = {}
    for name, _ in TIERS:
        tier = rated[rated["rarity_tier"] == name]
        if tier.empty:
            summary[name] = "0"
            continue
        summary[name] = (
            f"{len(tier):4d} places, {int(tier['views'].min()):>7d}"
            f" to {int(tier['views'].max()):>7d} readings"
        )
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Rate how rare each place of the app is."
    )
    parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    chosen = to_records(pd.read_parquet(SELECTION_PARQUET))
    notices = to_records(
        pd.read_parquet(MERIMEE_PARQUET, columns=["merimee_id", "name"])
    )
    places = (
        to_records(
            pd.read_parquet(
                LANDMARKS_PARQUET, columns=["qid", "title", "views", "languages"]
            )
        )
        if LANDMARKS_PARQUET.exists()
        else []
    )
    rated = rate(gather(chosen, notices, places))
    write_parquet(rated, SCHEMA, RARITY_PARQUET)
    rated.to_csv(RANKING_CSV, index=False)

    logger.info("Wrote %d places to %s", len(rated), RARITY_PARQUET)
    for name, line in summarize(rated).items():
        logger.info("  %-11s %s", name, line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
