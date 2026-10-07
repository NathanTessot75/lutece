"""Step 2 - fetch the Wikidata items linked to our Mérimée notices.

Wikidata ties an item to its Mérimée notice with property P380. The step joins on
the identifiers produced by ingest_merimee, then reads a few properties of every
matched item from the Wikidata Query Service (CC0 data).

Run with: uv run python -m lutece_pipeline.ingest_wikidata
"""

import argparse
import json
import logging
import re
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from itertools import batched
from pathlib import Path
from urllib.parse import unquote

import httpx
import pandas as pd
import pyarrow as pa

from lutece_pipeline import ingest_merimee, web
from lutece_pipeline.geo import is_in_paris
from lutece_pipeline.paths import INTERIM_DIR, RAW_DIR
from lutece_pipeline.tables import from_rows, write_parquet
from lutece_pipeline.web import Pause

logger = logging.getLogger(__name__)

WDQS_URL = "https://query.wikidata.org/sparql"
LINK_BATCH_SIZE = 300
ITEM_BATCH_SIZE = 250
# Pause between two batches, to stay a polite client of the public endpoint.
BATCH_PAUSE_SECONDS = 1.0
SEPARATOR = "|"

MERIMEE_PARQUET = ingest_merimee.OUTPUT_PARQUET
RAW_SNAPSHOT = RAW_DIR / "wikidata" / "snapshot.json"
ITEMS_PARQUET = INTERIM_DIR / "wikidata_items.parquet"
LINKS_PARQUET = INTERIM_DIR / "wikidata_merimee_links.parquet"

LINKS_QUERY = """
SELECT ?item ?merimee WHERE {
  VALUES ?merimee { %s }
  ?item wdt:P380 ?merimee .
}
"""

# One row per item: multi-valued properties are concatenated and split again here,
# so that the choice among several values is made deterministically on our side.
ITEMS_QUERY = """
SELECT ?item ?label ?sitelinks ?article ?articleTitle
  (GROUP_CONCAT(DISTINCT STR(?coord); separator="|") AS ?coords)
  (GROUP_CONCAT(DISTINCT ?commonsCat; separator="|") AS ?commonsCats)
  (GROUP_CONCAT(DISTINCT STR(?image); separator="|") AS ?images)
  (GROUP_CONCAT(DISTINCT STR(?inception); separator="|") AS ?inceptions)
  (GROUP_CONCAT(DISTINCT ?architectLabel; separator="|") AS ?architects)
  (GROUP_CONCAT(DISTINCT ?typeLabel; separator="|") AS ?types)
WHERE {
  VALUES ?item { %s }
  OPTIONAL { ?item rdfs:label ?label FILTER(LANG(?label) = "fr") }
  OPTIONAL { ?item wikibase:sitelinks ?sitelinks }
  OPTIONAL {
    ?article schema:about ?item ;
             schema:isPartOf <https://fr.wikipedia.org/> ;
             schema:name ?articleTitle .
  }
  OPTIONAL { ?item wdt:P625 ?coord }
  OPTIONAL { ?item wdt:P373 ?commonsCat }
  OPTIONAL { ?item wdt:P18 ?image }
  OPTIONAL { ?item wdt:P571 ?inception }
  OPTIONAL {
    ?item wdt:P84/rdfs:label ?architectLabel FILTER(LANG(?architectLabel) = "fr")
  }
  OPTIONAL { ?item wdt:P31/rdfs:label ?typeLabel FILTER(LANG(?typeLabel) = "fr") }
}
GROUP BY ?item ?label ?sitelinks ?article ?articleTitle
"""

LINKS_SCHEMA = pa.schema([("merimee_id", pa.string()), ("qid", pa.string())])

ITEMS_SCHEMA = pa.schema(
    [
        ("qid", pa.string()),
        ("label_fr", pa.string()),
        ("lat", pa.float64()),
        ("lon", pa.float64()),
        ("commons_category", pa.string()),
        ("frwiki_title", pa.string()),
        ("frwiki_url", pa.string()),
        ("image_file", pa.string()),
        ("inception_year", pa.int16()),
        ("architects", pa.list_(pa.string())),
        ("instance_of", pa.list_(pa.string())),
        ("sitelinks", pa.int16()),
    ]
)

type Row = dict[str, str]


def make_client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    """Create the HTTP client used to talk to the Wikidata Query Service."""
    return web.make_client(
        accept="application/sparql-results+json", transport=transport
    )


def run_query(
    client: httpx.Client, query: str, *, pause: Pause = time.sleep
) -> list[Row]:
    """Run a SPARQL query and return its rows as {variable: value} dicts."""
    response = web.post_form(client, WDQS_URL, {"query": query}, pause=pause)
    bindings = response.json()["results"]["bindings"]
    return [
        {name: cell["value"] for name, cell in binding.items()} for binding in bindings
    ]


def fetch_links(
    client: httpx.Client, merimee_ids: Sequence[str], *, pause: Pause = time.sleep
) -> list[Row]:
    """Return the (item, merimee) pairs of the items carrying one of the identifiers."""
    rows: list[Row] = []
    for index, batch in enumerate(batched(merimee_ids, LINK_BATCH_SIZE)):
        if index:
            pause(BATCH_PAUSE_SECONDS)
        values = " ".join(json.dumps(identifier) for identifier in batch)
        rows += run_query(client, LINKS_QUERY % values, pause=pause)
    return rows


def fetch_items(
    client: httpx.Client, qids: Sequence[str], *, pause: Pause = time.sleep
) -> list[Row]:
    """Return one row of properties per Wikidata item."""
    invalid = [qid for qid in qids if not re.fullmatch(r"Q\d+", qid)]
    if invalid:
        raise ValueError(f"Not Wikidata item identifiers: {invalid}")
    rows: list[Row] = []
    for index, batch in enumerate(batched(qids, ITEM_BATCH_SIZE)):
        if index:
            pause(BATCH_PAUSE_SECONDS)
        values = " ".join(f"wd:{qid}" for qid in batch)
        rows += run_query(client, ITEMS_QUERY % values, pause=pause)
    return rows


def qid_from_uri(uri: str) -> str:
    """Return "Q243" for "http://www.wikidata.org/entity/Q243"."""
    return uri.rsplit("/", 1)[-1]


def split_concat(value: str | None) -> list[str]:
    """Split a GROUP_CONCAT cell into its sorted, distinct, non-empty values."""
    return sorted({part for part in (value or "").split(SEPARATOR) if part})


def parse_point(wkt: str) -> tuple[float, float] | None:
    """Parse a WKT point, which lists the longitude first, into (lat, lon)."""
    match = re.fullmatch(r"Point\((-?\d+(?:\.\d+)?) (-?\d+(?:\.\d+)?)\)", wkt)
    if match is None:
        return None
    return float(match.group(2)), float(match.group(1))


def pick_paris_point(wkt_points: Sequence[str]) -> tuple[float, float] | None:
    """Return the first listed point that lies in Paris, as (lat, lon)."""
    for wkt in wkt_points:
        point = parse_point(wkt)
        if point is not None and is_in_paris(*point):
            return point
    return None


def parse_year(timestamp: str) -> int | None:
    """Return the year of an xsd:dateTime such as "1889-03-31T00:00:00Z"."""
    match = re.match(r"(-?\d{1,4})-", timestamp)
    return int(match.group(1)) if match else None


def commons_file_name(url: str) -> str:
    """Return the file name behind a Special:FilePath URL, e.g. "Tour Eiffel.jpg"."""
    return unquote(url.rsplit("/", 1)[-1])


def build_item(row: Mapping[str, str]) -> dict[str, object]:
    """Map one query row to the columns of ITEMS_SCHEMA."""
    lat, lon = pick_paris_point(split_concat(row.get("coords"))) or (None, None)
    categories = split_concat(row.get("commonsCats"))
    images = split_concat(row.get("images"))
    years = [
        year
        for year in map(parse_year, split_concat(row.get("inceptions")))
        if year is not None
    ]
    return {
        "qid": qid_from_uri(row["item"]),
        "label_fr": row.get("label"),
        "lat": lat,
        "lon": lon,
        "commons_category": categories[0] if categories else None,
        "frwiki_title": row.get("articleTitle"),
        "frwiki_url": row.get("article"),
        "image_file": commons_file_name(images[0]) if images else None,
        "inception_year": min(years) if years else None,
        "architects": split_concat(row.get("architects")),
        "instance_of": split_concat(row.get("types")),
        "sitelinks": int(row["sitelinks"]) if "sitelinks" in row else None,
    }


def build_items(rows: Sequence[Mapping[str, str]]) -> pd.DataFrame:
    """Turn the query rows into one typed row per item, sorted by identifier."""
    items = sorted(map(build_item, rows), key=lambda item: int(str(item["qid"])[1:]))
    frame = from_rows(items, ITEMS_SCHEMA)
    duplicated = frame.loc[frame["qid"].duplicated(), "qid"].tolist()
    if duplicated:
        raise ValueError(f"Several rows for the same Wikidata item: {duplicated}")
    return frame


def build_links(rows: Sequence[Mapping[str, str]]) -> pd.DataFrame:
    """Turn the query rows into distinct (merimee_id, qid) pairs."""
    pairs = sorted({(row["merimee"], qid_from_uri(row["item"])) for row in rows})
    return from_rows(
        [{"merimee_id": merimee_id, "qid": qid} for merimee_id, qid in pairs],
        LINKS_SCHEMA,
    )


def save_snapshot(
    path: Path, link_rows: Sequence[Row], item_rows: Sequence[Row]
) -> None:
    """Keep the raw answers, so that the step can be replayed offline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    snapshot = {
        "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "links": link_rows,
        "items": item_rows,
    }
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1) + "\n")


def summarize(
    merimee_ids: Sequence[str], links: pd.DataFrame, items: pd.DataFrame
) -> dict[str, int]:
    """Count the matches and the coverage gaps that the quality report will track."""
    items_per_notice = links.groupby("merimee_id")["qid"].nunique()
    notices_per_item = links.groupby("qid")["merimee_id"].nunique()
    return {
        "notices": len(merimee_ids),
        "notices_without_item": len(set(merimee_ids) - set(links["merimee_id"])),
        "notices_with_several_items": int((items_per_notice > 1).sum()),
        "items": len(items),
        "items_with_several_notices": int((notices_per_item > 1).sum()),
        "missing_coordinates": int(items["lat"].isna().sum()),
        "missing_commons_category": int(items["commons_category"].isna().sum()),
        "missing_frwiki_article": int(items["frwiki_title"].isna().sum()),
        "missing_image": int(items["image_file"].isna().sum()),
        "missing_architects": int((items["architects"].list.len() == 0).sum()),
        "missing_inception": int(items["inception_year"].isna().sum()),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch the Wikidata items linked to our Mérimée notices."
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="reuse the last saved Wikidata answers instead of querying the service",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    notices = pd.read_parquet(MERIMEE_PARQUET, columns=["merimee_id"])
    merimee_ids = notices["merimee_id"].tolist()
    if args.offline:
        snapshot = json.loads(RAW_SNAPSHOT.read_text())
        link_rows, item_rows = snapshot["links"], snapshot["items"]
    else:
        with make_client() as client:
            link_rows = fetch_links(client, merimee_ids)
            qids = sorted({qid_from_uri(row["item"]) for row in link_rows})
            item_rows = fetch_items(client, qids)
        save_snapshot(RAW_SNAPSHOT, link_rows, item_rows)

    links = build_links(link_rows)
    items = build_items(item_rows)
    write_parquet(links, LINKS_SCHEMA, LINKS_PARQUET)
    write_parquet(items, ITEMS_SCHEMA, ITEMS_PARQUET)

    logger.info("Wrote %d links to %s", len(links), LINKS_PARQUET)
    logger.info("Wrote %d items to %s", len(items), ITEMS_PARQUET)
    for label, count in summarize(merimee_ids, links, items).items():
        logger.info("  %-28s %5d", label, count)
    unmatched = sorted(set(merimee_ids) - set(links["merimee_id"]))
    if unmatched:
        logger.info("Notices without a Wikidata item: %s", ", ".join(unmatched))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
