"""Step 8, sources - the text of the Wikipedia article of each place of the app.

The story pages (SPEC §5.4) are written from the notice Mérimée and the article
of the French Wikipedia that speaks of the place. This step downloads the
plain text of each article, with the revision read, so that a story can cite
the very version it was written from. Each answer is kept in
`data/raw/wikipedia/articles.jsonl` as it comes: after an interruption, a new
run asks only for the articles still missing.

Run with: uv run python -m lutece_pipeline.fetch_articles
"""

import argparse
import json
import logging
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
import pandas as pd
import pyarrow as pa

from lutece_pipeline import landmark_places, selection, web
from lutece_pipeline.paths import INTERIM_DIR, RAW_DIR
from lutece_pipeline.tables import from_rows, to_records, write_parquet

logger = logging.getLogger(__name__)

API_URL = "https://fr.wikipedia.org/w/api.php"
# Between two requests: the API asks automated clients not to hurry.
PAUSE_SECONDS = 0.1

SELECTION_PARQUET = selection.SELECTION_PARQUET
LANDMARKS_PARQUET = landmark_places.PLACES_PARQUET
SNAPSHOT_JSONL = RAW_DIR / "wikipedia" / "articles.jsonl"
ARTICLES_PARQUET = INTERIM_DIR / "articles.parquet"

SCHEMA = pa.schema(
    [
        # The title that the selection or the review gave.
        ("title", pa.string()),
        # The title of the page read, after redirects; none when it is missing.
        ("page_title", pa.string()),
        ("revision", pa.int64()),
        # The plain text, with its "== Section ==" headings.
        ("text", pa.string()),
        ("characters", pa.int32()),
        ("fetched_at", pa.string()),
    ]
)

type Record = Mapping[str, Any]
type Pause = web.Pause


def article_titles(chosen: Sequence[Record], places: Sequence[Record]) -> list[str]:
    """The articles of the places that the app shows, each once, in order."""
    titles = [row["article"] for row in chosen if row["shown"] and row["article"]]
    titles += [place["article"] for place in places if place["article"]]
    return sorted(set(titles))


def article_url(title: str) -> str:
    query = {
        "action": "query",
        "format": "json",
        "formatversion": "2",
        "prop": "extracts|info",
        "explaintext": "1",
        "exsectionformat": "wiki",
        "redirects": "1",
        "titles": title,
    }
    return f"{API_URL}?{urlencode(query)}"


def read_answer(title: str, answer: Mapping[str, Any]) -> dict[str, Any]:
    """The article that the API gave for a title: its text, or nothing."""
    page = answer["query"]["pages"][0]
    missing = page.get("missing", False) or "extract" not in page
    return {
        "title": title,
        "page_title": None if missing else page["title"],
        "revision": None if missing else page.get("lastrevid"),
        "text": None if missing else page["extract"],
        "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def read_snapshot(path: Path) -> dict[str, dict[str, Any]]:
    """The articles already downloaded, by title."""
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as file:
        return {(line := json.loads(row))["title"]: line for row in file if row.strip()}


def fetch(
    client: httpx.Client,
    titles: Sequence[str],
    snapshot: Path,
    *,
    pause: Pause = time.sleep,
) -> dict[str, dict[str, Any]]:
    """Download the articles not in the snapshot yet, keeping each as it comes."""
    known = read_snapshot(snapshot)
    missing = [title for title in titles if title not in known]
    if missing:
        logger.info("Downloading %d articles", len(missing))
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    with snapshot.open("a", encoding="utf-8") as file:
        for done, title in enumerate(missing, start=1):
            pause(PAUSE_SECONDS)
            response = web.get(client, article_url(title), pause=pause)
            line = read_answer(title, response.json())
            file.write(json.dumps(line, ensure_ascii=False) + "\n")
            file.flush()
            known[title] = line
            if done % 50 == 0:
                logger.info("  %d of %d", done, len(missing))
    return known


def build_table(titles: Sequence[str], known: Mapping[str, Record]) -> pd.DataFrame:
    rows = [
        {
            **{
                column: known[title][column]
                for column in SCHEMA.names
                if column in known[title]
            },
            "characters": len(known[title]["text"] or ""),
        }
        for title in titles
        if title in known
    ]
    return from_rows(rows, SCHEMA)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Download the Wikipedia article of each place of the app."
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="rebuild the table from the articles already downloaded",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    chosen = to_records(
        pd.read_parquet(SELECTION_PARQUET, columns=["shown", "article"])
    )
    places = (
        to_records(pd.read_parquet(LANDMARKS_PARQUET, columns=["article"]))
        if LANDMARKS_PARQUET.exists()
        else []
    )
    titles = article_titles(chosen, places)
    if args.offline:
        known = read_snapshot(SNAPSHOT_JSONL)
    else:
        with web.make_client() as client:
            known = fetch(client, titles, SNAPSHOT_JSONL)
    table = build_table(titles, known)
    write_parquet(table, SCHEMA, ARTICLES_PARQUET)

    found = table["text"].notna()
    logger.info("Wrote %d articles to %s", len(table), ARTICLES_PARQUET)
    logger.info("  missing on Wikipedia    %5d", int((~found).sum()))
    logger.info(
        "  median characters      %6d", int(table.loc[found, "characters"].median())
    )
    logger.info("  longest                %6d", int(table["characters"].max()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
