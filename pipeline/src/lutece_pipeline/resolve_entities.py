"""Step 4 - reconcile each Mérimée notice with its Wikidata item and its OSM footprint.

The ingestion steps linked notices to Wikidata items and OSM objects through
shared identifiers. A few of those links are wrong and many notices have several
candidates, so this step measures every pair (distance, name similarity), marks
the ones that need a human look, applies the decisions already recorded in
review/entity_decisions.csv and picks one main item and one main footprint per
notice. In version 1 a monument is exactly one Mérimée notice.

Run with: uv run python -m lutece_pipeline.resolve_entities
"""

import argparse
import csv
import logging
import math
import re
import unicodedata
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import pyarrow as pa
from rapidfuzz import fuzz
from shapely.geometry.base import BaseGeometry

from lutece_pipeline import ingest_merimee, ingest_osm, ingest_wikidata
from lutece_pipeline.ingest_merimee import split_values
from lutece_pipeline.paths import INTERIM_DIR, REVIEW_DIR
from lutece_pipeline.tables import from_rows, to_records, write_parquet

logger = logging.getLogger(__name__)

LAMBERT_93 = "EPSG:2154"  # the metric projection used in France
# A Wikidata point this close to the Mérimée point confirms the link (94 % of pairs).
NEAR_ITEM_METERS = 100.0
# Same for an OSM geometry: the Mérimée point lies inside 78 % of the footprints.
NEAR_FOOTPRINT_METERS = 50.0
# Score above which two names are held to be the same.
SAME_NAME_SCORE = 90.0
IGNORED_WORDS = frozenset(
    {
        "a", "ancien", "ancienne", "anciens", "anciennes", "au", "aux", "d", "de",
        "des", "du", "en", "et", "l", "la", "le", "les", "ou", "un", "une",
    }
)  # fmt: skip
DECISIONS = frozenset({"accept", "reject", "primary"})

MERIMEE_PARQUET = ingest_merimee.OUTPUT_PARQUET
WIKIDATA_ITEMS_PARQUET = ingest_wikidata.ITEMS_PARQUET
WIKIDATA_LINKS_PARQUET = ingest_wikidata.LINKS_PARQUET
OSM_OBJECTS_PARQUET = ingest_osm.OBJECTS_PARQUET
OSM_LINKS_PARQUET = ingest_osm.LINKS_PARQUET
DECISIONS_CSV = REVIEW_DIR / "entity_decisions.csv"
LINKS_PARQUET = INTERIM_DIR / "entity_links.parquet"
ENTITIES_PARQUET = INTERIM_DIR / "entities.parquet"
REVIEW_CSV = INTERIM_DIR / "entities_to_review.csv"

LINKS_SCHEMA = pa.schema(
    [
        ("merimee_id", pa.string()),
        ("source", pa.string()),
        ("entity_id", pa.string()),
        ("entity_name", pa.string()),
        ("distance_m", pa.float64()),
        ("name_similarity", pa.float64()),
        ("address_match", pa.bool_()),
        ("via_ref_mhs", pa.bool_()),
        ("via_wikidata", pa.bool_()),
        ("is_footprint", pa.bool_()),
        ("area_m2", pa.float64()),
        ("status", pa.string()),
        ("reviewed", pa.bool_()),
        ("is_primary", pa.bool_()),
    ]
)

ENTITIES_SCHEMA = pa.schema(
    [
        ("merimee_id", pa.string()),
        ("wikidata_qid", pa.string()),
        ("wikidata_status", pa.string()),
        ("wikidata_count", pa.int16()),
        ("osm_footprint", pa.string()),
        ("osm_status", pa.string()),
        ("osm_footprint_count", pa.int16()),
        ("osm_object_count", pa.int16()),
    ]
)

REVIEW_COLUMNS = [
    "merimee_id",
    "name",
    "address",
    "arrondissement",
    "source",
    "entity_id",
    "entity_name",
    "distance_m",
    "name_similarity",
    "reason",
    "merimee_url",
    "entity_url",
]

type Record = Mapping[str, Any]
type Pair = dict[str, Any]


def normalize_name(text: str | None) -> str:
    """Lowercase a name, strip its accents and punctuation, and drop small words."""
    lowered = (text or "").casefold().replace("œ", "oe").replace("æ", "ae")
    decomposed = unicodedata.normalize("NFKD", lowered)
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    words = re.findall(r"[a-z0-9]+", plain)
    return " ".join(word for word in words if word not in IGNORED_WORDS)


def name_similarity(left: str | None, right: str | None) -> float | None:
    """Score from 0 to 100 how alike two names are, or None when one is missing.

    Words are compared regardless of their order, but a name that merely
    contains the other does not score high: "Place Vendôme" must not match
    every mansion that stands on it.
    """
    first, second = normalize_name(left), normalize_name(right)
    if not first or not second:
        return None
    return float(fuzz.token_sort_ratio(first, second))


def address_matches(address: str | None, entity_name: str | None) -> bool:
    """Tell whether an entity is named after one of the addresses of the notice.

    Wikidata labels such as "immeuble, 5 rue de Condé" repeat the address of an
    otherwise anonymous building. An address counts when it has a street number
    and all its words appear in the name.
    """
    name_words = set(normalize_name(entity_name).split())
    for part in split_values(address):
        words = normalize_name(part).split()
        has_number = any(word.isdigit() for word in words)
        if has_number and len(words) >= 3 and name_words.issuperset(words):
            return True
    return False


def text_or_none(value: object) -> str | None:
    """Return the value when it is text, None for the missing-value markers."""
    return value if isinstance(value, str) else None


def project_points(records: Sequence[Record], key: str) -> dict[str, BaseGeometry]:
    """Project the records that have coordinates to Lambert-93, by identifier."""
    located = [record for record in records if record["lat"] is not None]
    points = gpd.GeoSeries(
        gpd.points_from_xy(
            [record["lon"] for record in located], [record["lat"] for record in located]
        ),
        crs="EPSG:4326",
    ).to_crs(LAMBERT_93)
    return {record[key]: point for record, point in zip(located, points, strict=True)}


def distance_between(
    left: BaseGeometry | None, right: BaseGeometry | None
) -> float | None:
    """Distance in meters between two projected geometries, None when one is unknown."""
    if left is None or right is None:
        return None
    return float(left.distance(right))


def measure_wikidata_pairs(
    notices: Sequence[Record], items: Sequence[Record], links: Sequence[Record]
) -> list[Pair]:
    """Describe each (notice, Wikidata item) link: how far and how alike."""
    notices_by_id = {notice["merimee_id"]: notice for notice in notices}
    notice_points = project_points(notices, "merimee_id")
    items_by_qid = {item["qid"]: item for item in items}
    item_points = project_points(items, "qid")
    pairs = []
    for link in links:
        merimee_id, qid = link["merimee_id"], link["qid"]
        if qid not in items_by_qid:
            raise ValueError(f"{qid} is linked to {merimee_id} but has no item row")
        item = items_by_qid[qid]
        pairs.append(
            {
                "merimee_id": merimee_id,
                "source": "wikidata",
                "entity_id": qid,
                "entity_name": item["label_fr"],
                "distance_m": distance_between(
                    notice_points.get(merimee_id), item_points.get(qid)
                ),
                "name_similarity": name_similarity(
                    notices_by_id[merimee_id]["name"], item["label_fr"]
                ),
                "address_match": address_matches(
                    notices_by_id[merimee_id]["address"], item["label_fr"]
                ),
                "via_ref_mhs": None,
                "via_wikidata": None,
                "is_footprint": None,
                "area_m2": None,
                "sitelinks": item["sitelinks"] or 0,
            }
        )
    return pairs


def measure_osm_pairs(
    notices: Sequence[Record], objects: gpd.GeoDataFrame, links: Sequence[Record]
) -> list[Pair]:
    """Describe each (notice, OSM object) link, and whether the object is a footprint."""
    notices_by_id = {notice["merimee_id"]: notice for notice in notices}
    notice_points = project_points(notices, "merimee_id")
    projected = objects.to_crs(LAMBERT_93)
    objects_by_key = {(row.osm_type, row.osm_id): row for row in projected.itertuples()}
    pairs = []
    for link in links:
        merimee_id, key = link["merimee_id"], (link["osm_type"], link["osm_id"])
        if key not in objects_by_key:
            raise ValueError(f"{key} is linked to {merimee_id} but has no object row")
        row = objects_by_key[key]
        area = float(row.geometry.area) if row.geometry is not None else 0.0
        mapped_as_monument = (
            row.osm_type == "way"
            or row.relation_type in ingest_osm.FOOTPRINT_RELATION_TYPES
        )
        name = text_or_none(row.name)
        pairs.append(
            {
                "merimee_id": merimee_id,
                "source": "osm",
                "entity_id": f"{row.osm_type}/{row.osm_id}",
                "entity_name": name,
                "distance_m": distance_between(
                    notice_points.get(merimee_id), row.geometry
                ),
                "name_similarity": name_similarity(
                    notices_by_id[merimee_id]["name"], name
                ),
                "address_match": address_matches(
                    notices_by_id[merimee_id]["address"], name
                ),
                "via_ref_mhs": bool(link["via_ref_mhs"]),
                "via_wikidata": bool(link["via_wikidata"]),
                "is_footprint": area > 0 and mapped_as_monument,
                "area_m2": area,
                "sitelinks": 0,
            }
        )
    return pairs


def initial_status(pair: Record) -> str:
    """Confirm a pair that is close enough, bears the same name or is named after
    the address of the notice; doubt the others."""
    limit = NEAR_ITEM_METERS if pair["source"] == "wikidata" else NEAR_FOOTPRINT_METERS
    is_near = pair["distance_m"] is not None and pair["distance_m"] <= limit
    has_same_name = (
        pair["name_similarity"] is not None
        and pair["name_similarity"] >= SAME_NAME_SCORE
    )
    confirmed = is_near or has_same_name or pair["address_match"]
    return "confirmed" if confirmed else "doubtful"


def read_decisions(path: Path) -> dict[tuple[str, str], str]:
    """Read the reviewed decisions, keyed by (merimee_id, entity_id)."""
    if not path.exists():
        return {}
    decisions: dict[tuple[str, str], str] = {}
    with path.open(newline="", encoding="utf-8") as file:
        for line_number, row in enumerate(csv.DictReader(file), start=2):
            key = (row["merimee_id"], row["entity_id"])
            if row["decision"] not in DECISIONS:
                raise ValueError(
                    f"{path.name} line {line_number}: unknown decision {row['decision']!r}"
                )
            if key in decisions:
                raise ValueError(
                    f"{path.name} line {line_number}: {key} is decided twice"
                )
            decisions[key] = row["decision"]
    return decisions


def apply_decisions(
    pairs: Sequence[Pair], decisions: Mapping[tuple[str, str], str]
) -> None:
    """Set the status of each pair, letting the reviewed decisions overrule the rules."""
    for pair in pairs:
        decision = decisions.get((pair["merimee_id"], pair["entity_id"]))
        pair["reviewed"] = decision is not None
        pair["forced_primary"] = decision == "primary"
        if decision is None:
            pair["status"] = initial_status(pair)
        else:
            pair["status"] = "rejected" if decision == "reject" else "confirmed"
    known = {(pair["merimee_id"], pair["entity_id"]) for pair in pairs}
    stale = sorted(set(decisions) - known)
    if stale:
        logger.warning("%d decisions match no current pair: %s", len(stale), stale)


def ranking(pair: Record) -> tuple[Any, ...]:
    """Sort key that puts the best candidate of a notice first.

    A reviewed choice wins, then a confirmed pair. Wikidata items are then ranked
    by name, distance and notoriety; OSM footprints by the explicit Mérimée tag,
    distance and size.
    """
    distance = pair["distance_m"] if pair["distance_m"] is not None else math.inf
    common = (not pair["forced_primary"], pair["status"] != "confirmed")
    if pair["source"] == "wikidata":
        similarity = pair["name_similarity"] or 0.0
        number = int(pair["entity_id"][1:])
        return (*common, -similarity, distance, -pair["sitelinks"], number)
    return (
        *common,
        not pair["via_ref_mhs"],
        distance,
        -pair["area_m2"],
        pair["entity_id"],
    )


def is_candidate(pair: Record) -> bool:
    """Tell whether a pair may be the main item or the main footprint of its notice."""
    if pair["status"] == "rejected":
        return False
    # A reviewer may promote an object that the rules do not see as a footprint.
    if pair["forced_primary"]:
        return True
    return pair["source"] == "wikidata" or bool(pair["is_footprint"])


def choose_primaries(pairs: Sequence[Pair]) -> None:
    """Flag, for each notice and source, the best candidate as primary."""
    candidates: dict[tuple[str, str], list[Pair]] = defaultdict(list)
    for pair in pairs:
        pair["is_primary"] = False
        if is_candidate(pair):
            candidates[pair["merimee_id"], pair["source"]].append(pair)
    for group in candidates.values():
        min(group, key=ranking)["is_primary"] = True


def build_entities(notices: Sequence[Record], pairs: Sequence[Record]) -> pd.DataFrame:
    """Summarize, for each notice, the item and the footprint retained."""
    kept: dict[tuple[str, str], list[Record]] = defaultdict(list)
    for pair in pairs:
        if pair["status"] != "rejected":
            kept[pair["merimee_id"], pair["source"]].append(pair)

    rows = []
    for notice in notices:
        merimee_id = notice["merimee_id"]
        items = kept[merimee_id, "wikidata"]
        objects = kept[merimee_id, "osm"]
        item = next((pair for pair in items if pair["is_primary"]), None)
        footprint = next((pair for pair in objects if pair["is_primary"]), None)
        rows.append(
            {
                "merimee_id": merimee_id,
                "wikidata_qid": item["entity_id"] if item else None,
                "wikidata_status": item["status"] if item else None,
                "wikidata_count": len(items),
                "osm_footprint": footprint["entity_id"] if footprint else None,
                "osm_status": footprint["status"] if footprint else None,
                "osm_footprint_count": sum(
                    1 for pair in objects if pair["is_footprint"]
                ),
                "osm_object_count": len(objects),
            }
        )
    return from_rows(rows, ENTITIES_SCHEMA)


def entity_url(pair: Record) -> str:
    """Link to the Wikidata item or to the OSM object of a pair."""
    if pair["source"] == "wikidata":
        return f"https://www.wikidata.org/wiki/{pair['entity_id']}"
    return f"https://www.openstreetmap.org/{pair['entity_id']}"


def build_review(notices: Sequence[Record], pairs: Sequence[Record]) -> pd.DataFrame:
    """List what a human should look at: doubtful main choices and missing items."""
    notices_by_id = {notice["merimee_id"]: notice for notice in notices}
    with_item = {
        pair["merimee_id"]
        for pair in pairs
        if pair["source"] == "wikidata" and pair["status"] != "rejected"
    }

    def row(merimee_id: str, reason: str, pair: Record | None = None) -> dict[str, Any]:
        notice = notices_by_id[merimee_id]
        distance = pair["distance_m"] if pair else None
        return {
            "merimee_id": merimee_id,
            "name": notice["name"],
            "address": notice["address"],
            "arrondissement": notice["arrondissement"],
            "source": pair["source"] if pair else "wikidata",
            "entity_id": pair["entity_id"] if pair else None,
            "entity_name": pair["entity_name"] if pair else None,
            "distance_m": round(distance) if distance is not None else None,
            "name_similarity": pair["name_similarity"] if pair else None,
            "reason": reason,
            "merimee_url": f"https://pop.culture.gouv.fr/notice/merimee/{merimee_id}",
            "entity_url": entity_url(pair) if pair else None,
        }

    rows = [
        row(pair["merimee_id"], f"main {pair['source']} choice is doubtful", pair)
        for pair in pairs
        if pair["is_primary"] and pair["status"] == "doubtful"
    ]
    rows += [
        row(notice["merimee_id"], "no wikidata item")
        for notice in notices
        if notice["merimee_id"] not in with_item
    ]
    rows.sort(
        key=lambda item: (item["merimee_id"], item["source"], item["entity_id"] or "")
    )
    return pd.DataFrame(rows, columns=REVIEW_COLUMNS)


def summarize(
    entities: pd.DataFrame, links: pd.DataFrame, review: pd.DataFrame
) -> dict[str, int]:
    """Count the outcomes that the quality report will track."""

    def count(column: str, status: str) -> int:
        return int((entities[column] == status).sum())

    return {
        "notices": len(entities),
        "wikidata_confirmed": count("wikidata_status", "confirmed"),
        "wikidata_doubtful": count("wikidata_status", "doubtful"),
        "wikidata_missing": int(entities["wikidata_qid"].isna().sum()),
        "footprint_confirmed": count("osm_status", "confirmed"),
        "footprint_doubtful": count("osm_status", "doubtful"),
        "footprint_missing": int(entities["osm_footprint"].isna().sum()),
        "pairs": len(links),
        "pairs_doubtful": int((links["status"] == "doubtful").sum()),
        "pairs_rejected": int((links["status"] == "rejected").sum()),
        "pairs_reviewed": int(links["reviewed"].sum()),
        "to_review": len(review),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile each Mérimée notice with its Wikidata item and OSM footprint."
    )
    parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    notices = to_records(pd.read_parquet(MERIMEE_PARQUET))
    items = to_records(pd.read_parquet(WIKIDATA_ITEMS_PARQUET))
    wikidata_links = to_records(pd.read_parquet(WIKIDATA_LINKS_PARQUET))
    objects = gpd.read_parquet(OSM_OBJECTS_PARQUET)
    osm_links = to_records(pd.read_parquet(OSM_LINKS_PARQUET))

    pairs = measure_wikidata_pairs(notices, items, wikidata_links)
    pairs += measure_osm_pairs(notices, objects, osm_links)
    apply_decisions(pairs, read_decisions(DECISIONS_CSV))
    choose_primaries(pairs)
    pairs.sort(key=lambda pair: (pair["merimee_id"], pair["source"], pair["entity_id"]))

    links = from_rows(pairs, LINKS_SCHEMA)
    entities = build_entities(notices, pairs)
    review = build_review(notices, pairs)
    write_parquet(links, LINKS_SCHEMA, LINKS_PARQUET)
    write_parquet(entities, ENTITIES_SCHEMA, ENTITIES_PARQUET)
    review.to_csv(REVIEW_CSV, index=False)

    logger.info("Wrote %d pairs to %s", len(links), LINKS_PARQUET)
    logger.info("Wrote %d notices to %s", len(entities), ENTITIES_PARQUET)
    logger.info("Wrote %d lines to review to %s", len(review), REVIEW_CSV)
    for label, count in summarize(entities, links, review).items():
        logger.info("  %-22s %5d", label, count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
