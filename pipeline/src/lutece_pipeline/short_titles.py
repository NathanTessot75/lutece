"""Step 10 - a short name for each place of the app.

The notices name places at length: "Ancienne église Sainte-Geneviève, devenue
Le Panthéon". The app shows the name a passer-by would use. This step proposes
one for each place: the title of the Wikipedia article that speaks of it,
without the words in brackets that tell it apart from other pages; the label
of its Wikidata item when several places share an article; the name of the
notice, cut before what the place was or has become, otherwise. A place
without a notice keeps the title its review gave it.

The proposals go to `review/short_titles.csv`, where a review corrects them in
the `short_title` column. A new run never changes a name already there: it
adds the places newly shown, drops those no longer shown, and refreshes the
other columns.

Run with: uv run python -m lutece_pipeline.short_titles
"""

import argparse
import csv
import logging
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from lutece_pipeline import (
    ingest_merimee,
    ingest_wikidata,
    landmark_places,
    resolve_entities,
    selection,
)
from lutece_pipeline.paths import REVIEW_DIR
from lutece_pipeline.tables import to_records

logger = logging.getLogger(__name__)

SELECTION_PARQUET = selection.SELECTION_PARQUET
MERIMEE_PARQUET = ingest_merimee.OUTPUT_PARQUET
ENTITIES_PARQUET = resolve_entities.ENTITIES_PARQUET
WIKIDATA_ITEMS_PARQUET = ingest_wikidata.ITEMS_PARQUET
LANDMARKS_PARQUET = landmark_places.PLACES_PARQUET
REVIEW_CSV = REVIEW_DIR / "short_titles.csv"

# How each proposal was made.
WIKIPEDIA = "wikipedia"
WIKIDATA = "wikidata"
NOTICE = "notice"
LANDMARK = "landmark"

# The words in brackets at the end of a Wikipedia title: "Musée Picasso (Paris)".
BRACKETS = re.compile(r"\s*\([^)]*\)\s*$")
# In an app about Paris, "Église Saint-Roch de Paris" is "Église Saint-Roch";
# "Théâtre de Paris" keeps its name.
CITY = " de Paris"
# What a notice adds after the name of the place: what it was, has become, or
# is also called.
NOTICE_TAILS = re.compile(
    r",?\s+(?:actuellement|anciennement|devenue?s?|dite?s?|ou)\s.*$",
    re.IGNORECASE,
)

type Record = Mapping[str, Any]


@dataclass(frozen=True)
class Row:
    """A line of the review file."""

    key: str
    name: str
    article: str
    proposal: str
    rule: str
    short_title: str


COLUMNS = list(Row.__dataclass_fields__)


def without_brackets(title: str) -> str:
    return BRACKETS.sub("", title).strip()


def without_city(title: str) -> str:
    """A title without "de Paris" at its end, unless one word would be left."""
    rest = title.removesuffix(CITY)
    return rest if rest != title and len(rest.split()) > 1 else title


def capitalized(label: str) -> str:
    return label[:1].upper() + label[1:]


def cut_notice(name: str) -> str:
    """The name of a notice, before what the place was or has become."""
    return NOTICE_TAILS.sub("", name).strip(" ,") or name


def propose(
    name: str, article: str | None, label: str | None, shared: bool
) -> tuple[str, str]:
    """A short name for a monument, and the rule that gave it."""
    if article and not shared:
        return without_city(without_brackets(article)), WIKIPEDIA
    if label:
        return capitalized(label), WIKIDATA
    return cut_notice(name), NOTICE


def build_proposals(
    chosen: Sequence[Record],
    notices: Sequence[Record],
    entities: Sequence[Record],
    items: Sequence[Record],
    places: Sequence[Record],
) -> list[Row]:
    """One proposal per place that the app shows, by its key."""
    shown = {row["merimee_id"]: row["article"] for row in chosen if row["shown"]}
    names = {notice["merimee_id"]: notice["name"] for notice in notices}
    item_of = {entity["merimee_id"]: entity["wikidata_qid"] for entity in entities}
    labels = {item["qid"]: item["label_fr"] for item in items}
    # An article that speaks of several places names none of them in particular.
    uses = Counter(article for article in shown.values() if article)
    uses.update(place["article"] for place in places if place["article"])

    rows = []
    for merimee_id in sorted(shown):
        article = shown[merimee_id]
        name = names.get(merimee_id, merimee_id)
        label = labels.get(item_of.get(merimee_id))
        proposal, rule = propose(name, article, label, uses[article] > 1)
        rows.append(Row(merimee_id, name, article or "", proposal, rule, proposal))
    for place in sorted(places, key=lambda place: int(place["qid"][1:])):
        title = place["title"]
        rows.append(
            Row(place["qid"], title, place["article"] or "", title, LANDMARK, title)
        )
    return rows


def read_review(path: Path) -> dict[str, Row]:
    """The review file, by key; nothing when it does not exist yet."""
    if not path.exists():
        return {}
    rows: dict[str, Row] = {}
    with path.open(newline="", encoding="utf-8") as file:
        for line_number, row in enumerate(csv.DictReader(file), start=2):
            where = f"{path.name} line {line_number}"
            if row["key"] in rows:
                raise ValueError(f"{where}: {row['key']} appears twice")
            if not row["short_title"].strip():
                raise ValueError(f"{where}: {row['key']} has no short title")
            rows[row["key"]] = Row(**{column: row[column] for column in COLUMNS})
    return rows


def merge(proposals: Sequence[Row], reviewed: Mapping[str, Row]) -> list[Row]:
    """The proposals, with the names that the review already holds."""
    return [
        proposal
        if proposal.key not in reviewed
        else Row(
            **{**asdict(proposal), "short_title": reviewed[proposal.key].short_title}
        )
        for proposal in proposals
    ]


def read_short_titles(path: Path) -> dict[str, str]:
    """The short name of each place, by its key, as the review left it."""
    return {key: row.short_title.strip() for key, row in read_review(path).items()}


def write_review(path: Path, rows: Sequence[Row]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(asdict(row) for row in rows)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Propose a short name for each place of the app."
    )
    parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    places = (
        to_records(
            pd.read_parquet(LANDMARKS_PARQUET, columns=["qid", "title", "article"])
        )
        if LANDMARKS_PARQUET.exists()
        else []
    )
    proposals = build_proposals(
        to_records(
            pd.read_parquet(
                SELECTION_PARQUET, columns=["merimee_id", "shown", "article"]
            )
        ),
        to_records(pd.read_parquet(MERIMEE_PARQUET, columns=["merimee_id", "name"])),
        to_records(
            pd.read_parquet(ENTITIES_PARQUET, columns=["merimee_id", "wikidata_qid"])
        ),
        to_records(
            pd.read_parquet(WIKIDATA_ITEMS_PARQUET, columns=["qid", "label_fr"])
        ),
        places,
    )
    reviewed = read_review(REVIEW_CSV)
    rows = merge(proposals, reviewed)
    write_review(REVIEW_CSV, rows)

    kept = sum(row.key in reviewed for row in rows)
    shared = [
        title
        for title, count in Counter(row.short_title for row in rows).items()
        if count > 1
    ]
    logger.info("Wrote %d short names to %s", len(rows), REVIEW_CSV)
    logger.info("  kept from the review   %4d", kept)
    logger.info("  new                    %4d", len(rows) - kept)
    logger.info(
        "  dropped                %4d", len(set(reviewed) - {row.key for row in rows})
    )
    for rule, count in sorted(Counter(row.rule for row in rows).items()):
        logger.info("  proposed from %-9s %4d", rule, count)
    if shared:
        logger.warning("%d names are shared by several places: %s", len(shared), shared)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
