"""Choose the monuments that the app shows, and rank them by how known they are.

The base lists every protected building, and most of them are plain blocks of
flats that nobody walking by would wonder about. A monument is a candidate when
someone found it worth an article in the French Wikipedia:

- its own Wikidata item has one;
- or it has a name of its own and the article is about what it holds or belongs
  to. The article of a school or a museum is attached to the institution, not
  to the building that the notice protects: Wikidata says that the building is
  occupied by it, part of it, or that it is located there.

Some kinds of monument are left out whatever their article. The candidates are
then ranked by two measures of how much people wonder about them: how often the
article was read in a year, and in how many languages it exists. The app shows
the best known, as long as a player can stand in front of them.

A hand-made file can show or hide a monument whatever the rule says.

Run with: uv run python -m lutece_pipeline.selection
"""

import argparse
import csv
import json
import logging
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from itertools import batched
from pathlib import Path
from typing import Any, NamedTuple
from urllib.parse import quote

import httpx
import pandas as pd
import pyarrow as pa

from lutece_pipeline import (
    ingest_merimee,
    ingest_wikidata,
    load_postgres,
    quality_report,
    resolve_entities,
    visibility,
    web,
)
from lutece_pipeline.paths import INTERIM_DIR, RAW_DIR, REVIEW_DIR
from lutece_pipeline.tables import from_rows, to_records, write_parquet
from lutece_pipeline.web import Pause

logger = logging.getLogger(__name__)

# The Wikidata service times out on larger batches of these queries.
BATCH_SIZE = 60
PAUSE_SECONDS = 1.0
# Kinds of monument that the app does not show (decision of 11 October 2026):
# the protected metro stations are their entrances, 65 of them much alike.
EXCLUDED_KINDS = frozenset({"station de métro"})
# The readings of an article over the twelve months before the decision, by
# people rather than robots, on every kind of device.
VIEWS_URL = (
    "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
    "fr.wikipedia/all-access/user/{title}/monthly/2025100100/2026093000"
)
VIEWS_PAUSE_SECONDS = 0.05
# The app shows the candidates up to this place in the ranking (decision of 11
# October 2026): beyond it, the mansions and buildings that few have heard of.
LAST_RANK_SHOWN = 350

MERIMEE_PARQUET = ingest_merimee.OUTPUT_PARQUET
ENTITIES_PARQUET = resolve_entities.ENTITIES_PARQUET
WIKIDATA_ITEMS_PARQUET = ingest_wikidata.ITEMS_PARQUET
VISIBILITY_PARQUET = visibility.VISIBILITY_PARQUET
NEIGHBOURS_SNAPSHOT = RAW_DIR / "wikidata" / "neighbours.json"
VIEWS_SNAPSHOT = RAW_DIR / "wikipedia" / "pageviews.json"
OVERRIDES_CSV = REVIEW_DIR / "selection_overrides.csv"
SELECTION_PARQUET = INTERIM_DIR / "selection.parquet"
# The ranking with names, to read and to choose where to cut.
RANKING_CSV = INTERIM_DIR / "selection_ranking.csv"

# What the building holds or belongs to: occupant (P466), part of (P361).
HOLDS_QUERY = """
SELECT ?item ?other ?title ?links WHERE {
  VALUES ?item { %s }
  VALUES ?claim { wdt:P466 wdt:P361 }
  ?item ?claim ?other .
  ?other wikibase:sitelinks ?links .
  ?article schema:about ?other ;
           schema:isPartOf <https://fr.wikipedia.org/> ;
           schema:name ?title .
}
"""
# What says it is there: headquarters (P159), location (P276), has part (P527).
HELD_QUERY = """
SELECT ?item ?other ?title ?links WHERE {
  VALUES ?item { %s }
  VALUES ?claim { wdt:P159 wdt:P276 wdt:P527 }
  ?other ?claim ?item .
  ?other wikibase:sitelinks ?links .
  ?article schema:about ?other ;
           schema:isPartOf <https://fr.wikipedia.org/> ;
           schema:name ?title .
}
"""

ARTICLE = "article"
NEIGHBOUR = "neighbour_article"
BY_HAND = "by_hand"
SHOW, HIDE = "show", "hide"
# Why a monument is not shown, from the first reason that applies.
NO_ARTICLE = "no_article"
EXCLUDED_KIND = "excluded_kind"
HIDDEN_BY_HAND = "hidden_by_hand"
OUT_OF_REACH = "cannot_be_approached"
TOO_LITTLE_KNOWN = "too_little_known"

SCHEMA = pa.schema(
    [
        ("merimee_id", pa.string()),
        ("shown", pa.bool_()),
        # Why it is shown: its article, the one of a neighbour, or a decision.
        ("reason", pa.string()),
        # Why it is not.
        ("left_out", pa.string()),
        ("article", pa.string()),
        # How known the article is: readings in a year, languages it exists in.
        ("views", pa.int64()),
        ("languages", pa.int32()),
        # From 0 to 1, and the place among the candidates: 1 is the best known.
        ("score", pa.float64()),
        ("rank", pa.int32()),
    ]
)

type Record = Mapping[str, Any]
type Row = dict[str, str]


class Article(NamedTuple):
    """An article of the French Wikipedia, and how many sites link its subject."""

    title: str
    languages: int


def fetch_neighbours(
    client: httpx.Client, qids: Sequence[str], *, pause: Pause = time.sleep
) -> list[Row]:
    """Return the articles of the items that hold or contain the given ones."""
    rows: list[Row] = []
    for batch in batched(qids, BATCH_SIZE):
        values = " ".join(f"wd:{qid}" for qid in batch)
        for query in (HOLDS_QUERY, HELD_QUERY):
            pause(PAUSE_SECONDS)
            rows += ingest_wikidata.run_query(client, query % values, pause=pause)
    return rows


def neighbour_articles(rows: Sequence[Mapping[str, str]]) -> dict[str, Article]:
    """Name one neighbour article per item: the one that most sites know.

    A building may hold several things with an article - a museum, the
    institute that runs it. The best known tells best why people come.
    """
    best: dict[str, Article] = {}
    for row in rows:
        qid = ingest_wikidata.qid_from_uri(row["item"])
        found = Article(row["title"], int(row["links"]))
        kept = best.get(qid)
        if kept is None or (-found.languages, found.title) < (
            -kept.languages,
            kept.title,
        ):
            best[qid] = found
    return best


def fetch_views(
    client: httpx.Client, titles: Sequence[str], *, pause: Pause = time.sleep
) -> dict[str, int]:
    """Return how many times each article was read over the year."""
    views = {}
    for title in titles:
        pause(VIEWS_PAUSE_SECONDS)
        url = VIEWS_URL.format(title=quote(title.replace(" ", "_"), safe=""))
        # The service knows nothing of an article that nobody read: 404.
        response = web.get(client, url, pause=pause, accepted={404})
        months = response.json().get("items", []) if response.is_success else []
        views[title] = sum(month["views"] for month in months)
    return views


def read_overrides(path: Path) -> dict[str, str]:
    """Read the monuments that a review shows or hides against the rule."""
    if not path.exists():
        return {}
    overrides: dict[str, str] = {}
    with path.open(newline="", encoding="utf-8") as file:
        for line_number, row in enumerate(csv.DictReader(file), start=2):
            where = f"{path.name} line {line_number}"
            if row["decision"] not in (SHOW, HIDE):
                raise ValueError(f"{where}: unknown decision {row['decision']!r}")
            if row["merimee_id"] in overrides:
                raise ValueError(f"{where}: {row['merimee_id']} appears twice")
            overrides[row["merimee_id"]] = row["decision"]
    return overrides


def find_articles(
    notices: Sequence[Record],
    entities: Sequence[Record],
    items: Sequence[Record],
    neighbours: Mapping[str, Article],
    visibilities: Sequence[Record],
) -> list[dict[str, Any]]:
    """One line per protected notice, with the article that speaks of it, if any."""
    item_of = {entity["merimee_id"]: entity["wikidata_qid"] for entity in entities}
    items_by_id = {item["qid"]: item for item in items}
    seen = {row["merimee_id"]: row for row in visibilities}
    rows = []
    for notice in sorted(notices, key=lambda notice: notice["merimee_id"]):
        if notice["protection"] is None:
            continue
        qid = item_of.get(notice["merimee_id"])
        item = items_by_id.get(qid, {})
        kinds = load_postgres.names(notice["denominations"])
        named = quality_report.has_own_name(notice["name"], kinds)
        reason, article, languages = None, None, None
        if item.get("frwiki_title") is not None:
            reason, article = ARTICLE, item["frwiki_title"]
            languages = item["sitelinks"]
        elif named and qid in neighbours:
            reason = NEIGHBOUR
            article, languages = neighbours[qid]
        view = seen.get(notice["merimee_id"], {})
        rows.append(
            {
                "merimee_id": notice["merimee_id"],
                "excluded": bool(EXCLUDED_KINDS.intersection(kinds)),
                "approachable": visibility.can_be_approached(
                    view.get("visibility", visibility.UNKNOWN), view.get("reason")
                ),
                "reason": reason,
                "article": article,
                "languages": languages,
            }
        )
    return rows


def build_selection(
    found: Sequence[Record],
    views: Mapping[str, int],
    overrides: Mapping[str, str],
) -> pd.DataFrame:
    """Rank the candidates by how known they are, and decide which are shown.

    A candidate has an article and is of a kind that the app shows, or was
    asked for by hand. Its score is the mean of two places among the
    candidates, each from 0 for the least to 1 for the most: by readings of the
    article, and by languages. The app shows the candidates up to
    LAST_RANK_SHOWN that a player can stand in front of; a decision by hand
    shows or hides a monument whatever its place.
    """
    rows = []
    for line in found:
        decision = overrides.get(line["merimee_id"])
        reason = None if line["excluded"] else line["reason"]
        if decision == SHOW and reason is None:
            reason = BY_HAND
        known = reason is not None and line["article"] is not None
        rows.append(
            {
                "merimee_id": line["merimee_id"],
                "reason": reason,
                "article": line["article"],
                "views": views.get(line["article"], 0) if known else None,
                "languages": line["languages"] if known else None,
                "score": None,
                "rank": None,
            }
        )
    candidates = [row for row in rows if row["reason"] is not None]
    measures = pd.DataFrame(
        {
            name: [float(-1 if row[name] is None else row[name]) for row in candidates]
            for name in ("views", "languages")
        }
    )
    scores = measures.rank(pct=True).mean(axis=1).tolist()
    for row, score in zip(candidates, scores, strict=True):
        row["score"] = score
    by_score = sorted(candidates, key=lambda row: (-row["score"], row["merimee_id"]))
    for place, row in enumerate(by_score, start=1):
        row["rank"] = place

    for row, line in zip(rows, found, strict=True):
        decision = overrides.get(line["merimee_id"])
        if row["reason"] is None:
            left_out = EXCLUDED_KIND if line["excluded"] else NO_ARTICLE
        elif decision == HIDE:
            left_out = HIDDEN_BY_HAND
        elif decision == SHOW:
            left_out = None
        elif not line["approachable"]:
            left_out = OUT_OF_REACH
        elif row["rank"] > LAST_RANK_SHOWN:
            left_out = TOO_LITTLE_KNOWN
        else:
            left_out = None
        row["left_out"] = left_out
        row["shown"] = left_out is None
        if left_out is not None:
            row["reason"] = None
    return from_rows(rows, SCHEMA)


def build_ranking(selection: pd.DataFrame, notices: Sequence[Record]) -> pd.DataFrame:
    """The candidates, the best known first, with what names them."""
    names = pd.DataFrame(
        [
            {
                "merimee_id": notice["merimee_id"],
                "name": notice["name"],
                "kind": next(iter(load_postgres.names(notice["denominations"])), None),
                "arrondissement": notice["arrondissement"],
            }
            for notice in notices
        ]
    )
    ranked = selection[selection["rank"].notna()].merge(names, on="merimee_id")
    columns = [
        "rank",
        "shown",
        "left_out",
        "name",
        "kind",
        "arrondissement",
        "article",
        "views",
        "languages",
        "score",
        "reason",
        "merimee_id",
    ]
    return ranked.sort_values("rank")[columns]


def summarize(selection: pd.DataFrame) -> dict[str, int]:
    """Count what is shown and what is not, by reason."""
    counts = {"monuments": len(selection), "shown": int(selection["shown"].sum())}
    for reason, count in selection["reason"].value_counts().sort_index().items():
        counts[f"shown_by_{reason}"] = int(count)
    for reason, count in selection["left_out"].value_counts().sort_index().items():
        counts[f"left_out_{reason}"] = int(count)
    return counts


def save_snapshot(path: Path, name: str, content: object) -> None:
    """Keep raw answers, so that the step can be replayed offline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    snapshot = {"fetched_at": datetime.now(UTC).isoformat(timespec="seconds")}
    path.write_text(
        json.dumps({**snapshot, name: content}, ensure_ascii=False, indent=1) + "\n"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Choose the monuments that the app shows, and rank them."
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="reuse the last saved answers instead of querying the services",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    notices = to_records(pd.read_parquet(MERIMEE_PARQUET))
    entities = to_records(pd.read_parquet(ENTITIES_PARQUET))
    items = to_records(pd.read_parquet(WIKIDATA_ITEMS_PARQUET))
    seen = to_records(pd.read_parquet(VISIBILITY_PARQUET))
    if args.offline:
        rows = json.loads(NEIGHBOURS_SNAPSHOT.read_text())["neighbours"]
        views = json.loads(VIEWS_SNAPSHOT.read_text())["views"]
    else:
        without_article = sorted(
            item["qid"] for item in items if item["frwiki_title"] is None
        )
        with ingest_wikidata.make_client() as client:
            rows = fetch_neighbours(client, without_article)
        save_snapshot(NEIGHBOURS_SNAPSHOT, "neighbours", rows)
    found = find_articles(notices, entities, items, neighbour_articles(rows), seen)
    if not args.offline:
        titles = sorted({line["article"] for line in found if line["article"]})
        with web.make_client() as client:
            views = fetch_views(client, titles)
        save_snapshot(VIEWS_SNAPSHOT, "views", views)

    overrides = read_overrides(OVERRIDES_CSV)
    selection = build_selection(found, views, overrides)
    stale = sorted(set(overrides) - set(selection["merimee_id"]))
    if stale:
        logger.warning("%d decisions match no monument: %s", len(stale), stale)
    write_parquet(selection, SCHEMA, SELECTION_PARQUET)
    build_ranking(selection, notices).to_csv(RANKING_CSV, index=False)

    logger.info("Wrote %d monuments to %s", len(selection), SELECTION_PARQUET)
    for label, count in summarize(selection).items():
        logger.info("  %-28s %5d", label, count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
