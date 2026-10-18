"""Thematic series of places to complete: the bridges, the covered passages...

SPEC §2 gives the players series to complete, besides the arrondissements. A
series gathers the places of the app whose kind is among those it lists, in
the arrondissements it names, if any: the kind is the one the app shows, the
first denomination of the notice or the kind of a place without a notice. The
series are described in `review/series.csv`, in the order the app shows them,
and a review adds or removes places that their kind ranks wrongly in
`review/series_overrides.csv`. A place may be in several series, or in none.

Run with: uv run python -m lutece_pipeline.series
"""

import argparse
import csv
import logging
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, NamedTuple

import pandas as pd
import pyarrow as pa

from lutece_pipeline import ingest_merimee, landmark_places, load_postgres, selection
from lutece_pipeline.paths import INTERIM_DIR, REVIEW_DIR
from lutece_pipeline.tables import from_rows, to_records, write_parquet

logger = logging.getLogger(__name__)

# Several kinds or arrondissements in one cell of the description are
# separated this way.
LIST_SEPARATOR = ";"
SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
ADD, REMOVE = "add", "remove"

SELECTION_PARQUET = selection.SELECTION_PARQUET
MERIMEE_PARQUET = ingest_merimee.OUTPUT_PARQUET
LANDMARKS_PARQUET = landmark_places.PLACES_PARQUET
SERIES_CSV = REVIEW_DIR / "series.csv"
OVERRIDES_CSV = REVIEW_DIR / "series_overrides.csv"
SERIES_PARQUET = INTERIM_DIR / "series.parquet"
MEMBERS_PARQUET = INTERIM_DIR / "series_members.parquet"
# Every place with its series, those in none first, to review the rules.
REVIEW_CSV = INTERIM_DIR / "series_review.csv"

SERIES_SCHEMA = pa.schema(
    [
        ("slug", pa.string()),
        ("name", pa.string()),
        ("description", pa.string()),
        # 1 for the first series that the app shows.
        ("position", pa.int32()),
    ]
)
MEMBERS_SCHEMA = pa.schema(
    [
        ("slug", pa.string()),
        # The Mérimée reference of a monument, or the Wikidata item of a place
        # without a notice.
        ("key", pa.string()),
    ]
)

type Record = Mapping[str, Any]


class Series(NamedTuple):
    slug: str
    name: str
    description: str
    kinds: frozenset[str]
    # None when the series takes its kinds from all Paris.
    arrondissements: frozenset[int] | None


def split(cell: str) -> list[str]:
    return [part.strip() for part in cell.split(LIST_SEPARATOR) if part.strip()]


def read_series(path: Path) -> list[Series]:
    """Read the series that a review describes, in the order the app shows them."""
    found: list[Series] = []
    with path.open(newline="", encoding="utf-8") as file:
        for line_number, row in enumerate(csv.DictReader(file), start=2):
            where = f"{path.name} line {line_number}"
            slug = row["slug"]
            if not SLUG.match(slug):
                raise ValueError(f"{where}: {slug!r} is not a slug")
            if slug in {series.slug for series in found}:
                raise ValueError(f"{where}: {slug} appears twice")
            if not row["name"].strip() or not row["description"].strip():
                raise ValueError(f"{where}: {slug} needs a name and a description")
            kinds = split(row["categories"])
            if not kinds:
                raise ValueError(f"{where}: {slug} lists no kind")
            numbers = split(row["arrondissements"])
            if not all(
                number.isdecimal() and 1 <= int(number) <= 20 for number in numbers
            ):
                raise ValueError(
                    f"{where}: {row['arrondissements']!r} are not arrondissements"
                )
            found.append(
                Series(
                    slug=slug,
                    name=row["name"].strip(),
                    description=row["description"].strip(),
                    kinds=frozenset(kinds),
                    arrondissements=frozenset(map(int, numbers)) if numbers else None,
                )
            )
    return found


def read_overrides(path: Path, slugs: frozenset[str]) -> dict[str, dict[str, set[str]]]:
    """Read the places that a review adds to a series, or removes from it."""
    overrides: dict[str, dict[str, set[str]]] = {
        slug: {ADD: set(), REMOVE: set()} for slug in slugs
    }
    if not path.exists():
        return overrides
    with path.open(newline="", encoding="utf-8") as file:
        for line_number, row in enumerate(csv.DictReader(file), start=2):
            where = f"{path.name} line {line_number}"
            slug, key, decision = row["slug"], row["key"], row["decision"]
            if slug not in slugs:
                raise ValueError(f"{where}: no series is called {slug!r}")
            if decision not in (ADD, REMOVE):
                raise ValueError(f"{where}: unknown decision {decision!r}")
            if key in overrides[slug][ADD] | overrides[slug][REMOVE]:
                raise ValueError(f"{where}: {key} appears twice for {slug}")
            overrides[slug][decision].add(key)
    return overrides


def gather(
    chosen: Sequence[Record], notices: Sequence[Record], places: Sequence[Record]
) -> list[dict[str, Any]]:
    """The places that the app shows, with the kind and arrondissement of each."""
    shown = {row["merimee_id"] for row in chosen if row["shown"]}
    gathered = []
    for notice in sorted(notices, key=lambda notice: notice["merimee_id"]):
        if notice["merimee_id"] not in shown:
            continue
        kinds = load_postgres.names(notice["denominations"])
        gathered.append(
            {
                "key": notice["merimee_id"],
                "name": notice["name"],
                "category": kinds[0] if kinds else None,
                "arrondissement": notice["arrondissement"],
            }
        )
    gathered += [
        {
            "key": place["qid"],
            "name": place["title"],
            "category": place["kind"],
            "arrondissement": place["arrondissement"],
        }
        for place in sorted(places, key=lambda place: int(place["qid"][1:]))
    ]
    return gathered


def assign(
    places: Sequence[Record],
    series: Sequence[Series],
    overrides: Mapping[str, Mapping[str, set[str]]],
) -> list[dict[str, str]]:
    """The members of each series: its kinds, its arrondissements, and the review."""
    known = {place["key"] for place in places}
    stale = sorted(
        (slug, key)
        for slug, decisions in overrides.items()
        for keys in decisions.values()
        for key in keys
        if key not in known
    )
    if stale:
        logger.warning("%d decisions match no place: %s", len(stale), stale)
    members = []
    for one in series:
        decisions = overrides.get(one.slug, {ADD: set(), REMOVE: set()})
        for place in places:
            fits = place["category"] in one.kinds and (
                one.arrondissements is None
                or place["arrondissement"] in one.arrondissements
            )
            if (fits or place["key"] in decisions[ADD]) and place[
                "key"
            ] not in decisions[REMOVE]:
                members.append({"slug": one.slug, "key": place["key"]})
    return members


def build_review(
    places: Sequence[Record], series: Sequence[Series], members: Sequence[Record]
) -> pd.DataFrame:
    """Every place with the names of its series: those in none come first."""
    names = {one.slug: one.name for one in series}
    of: dict[str, list[str]] = {}
    for member in members:
        of.setdefault(member["key"], []).append(names[member["slug"]])
    rows = [
        {
            "key": place["key"],
            "name": place["name"],
            "category": place["category"],
            "arrondissement": place["arrondissement"],
            "series": LIST_SEPARATOR.join(of.get(place["key"], [])),
        }
        for place in places
    ]
    review = pd.DataFrame(
        rows, columns=["key", "name", "category", "arrondissement", "series"]
    )
    return review.sort_values(
        ["series", "category", "name"], key=lambda column: column.fillna("")
    ).reset_index(drop=True)


def summarize(
    places: Sequence[Record], series: Sequence[Series], members: Sequence[Record]
) -> list[str]:
    """One line per series, then the places and kinds left out of all."""
    counts = Counter(member["slug"] for member in members)
    lines = [f"{one.name:<34} {counts[one.slug]:4d}" for one in series]
    placed = {member["key"] for member in members}
    left = [place for place in places if place["key"] not in placed]
    kinds = Counter(place["category"] or "(none)" for place in left)
    lines.append(f"{'in no series':<34} {len(left):4d}")
    lines.append(
        "  most common kinds: "
        + ", ".join(f"{kind} {n}" for kind, n in kinds.most_common(8))
    )
    return lines


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Gather the places of the app into thematic series."
    )
    parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    series = read_series(SERIES_CSV)
    overrides = read_overrides(OVERRIDES_CSV, frozenset(one.slug for one in series))
    chosen = to_records(
        pd.read_parquet(SELECTION_PARQUET, columns=["merimee_id", "shown"])
    )
    notices = to_records(
        pd.read_parquet(
            MERIMEE_PARQUET,
            columns=["merimee_id", "name", "denominations", "arrondissement"],
        )
    )
    landmarks = (
        to_records(
            pd.read_parquet(
                LANDMARKS_PARQUET, columns=["qid", "title", "kind", "arrondissement"]
            )
        )
        if LANDMARKS_PARQUET.exists()
        else []
    )
    places = gather(chosen, notices, landmarks)
    members = assign(places, series, overrides)

    rows = [
        {
            "slug": one.slug,
            "name": one.name,
            "description": one.description,
            "position": position,
        }
        for position, one in enumerate(series, start=1)
    ]
    write_parquet(from_rows(rows, SERIES_SCHEMA), SERIES_SCHEMA, SERIES_PARQUET)
    write_parquet(from_rows(members, MEMBERS_SCHEMA), MEMBERS_SCHEMA, MEMBERS_PARQUET)
    build_review(places, series, members).to_csv(REVIEW_CSV, index=False)

    logger.info("Wrote %d series and %d memberships", len(series), len(members))
    for line in summarize(places, series, members):
        logger.info("  %s", line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
