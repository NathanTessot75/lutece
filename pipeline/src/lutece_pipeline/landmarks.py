"""Find the well-known places of Paris that are not protected monuments.

The Mérimée base only lists what the State protects. The Montparnasse tower,
the Centre Pompidou or the Moulin-Rouge are not in it, though anyone walking by
wonders about them. The step asks Wikidata for the places of Paris that have an
article in the French Wikipedia and no Mérimée notice, measures how known each
one is the way the selection step does, and writes a list to review: what the
rules would keep, and why they would leave out the rest.

Nothing enters the app from here: a place does once a review has kept it.

Run with: uv run python -m lutece_pipeline.landmarks
"""

import argparse
import json
import logging
import re
import time
from bisect import bisect_right
from collections.abc import Mapping, Sequence
from itertools import batched
from typing import Any

import geopandas as gpd
import httpx
import pandas as pd
import pyarrow as pa
import shapely

from lutece_pipeline import geometry, ingest_merimee, ingest_wikidata, selection, web
from lutece_pipeline.geo import LAMBERT_93, WGS84
from lutece_pipeline.paths import INTERIM_DIR, RAW_DIR
from lutece_pipeline.tables import from_rows, to_records, write_parquet
from lutece_pipeline.web import Pause

logger = logging.getLogger(__name__)

# Below this many sites that know a place, its article is not read enough to
# be as known as the monuments shown.
MIN_LINKS = 4
BATCH_SIZE = 200
PAUSE_SECONDS = 1.0
# A place this close to a monument shown, in metres, stands in it or against it.
SAME_PLACE_M = 20.0

MERIMEE_PARQUET = ingest_merimee.OUTPUT_PARQUET
GEOMETRIES_PARQUET = geometry.GEOMETRIES_PARQUET
SELECTION_PARQUET = selection.SELECTION_PARQUET
ITEMS_SNAPSHOT = RAW_DIR / "wikidata" / "landmarks.json"
VIEWS_SNAPSHOT = RAW_DIR / "wikipedia" / "landmark_pageviews.json"
CANDIDATES_PARQUET = INTERIM_DIR / "landmark_candidates.parquet"
# The same list, the best known first, to read and to decide from.
CANDIDATES_CSV = INTERIM_DIR / "landmark_candidates.csv"

# The places of Paris (P131, through its arrondissements and quarters) that
# have coordinates, an article in French, and no notice of a protected
# monument. Property P380 also holds the identifiers of the label
# "Architecture contemporaine remarquable", which start with ACR and protect
# nothing: the Opéra Bastille or the Cité des sciences are places to find here.
PLACES_QUERY = """
SELECT DISTINCT ?item WHERE {
  ?item wdt:P131+ wd:Q90 ;
        wikibase:sitelinks ?links ;
        wdt:P625 ?coord .
  FILTER(?links >= %d)
  FILTER NOT EXISTS { ?item wdt:P380 ?notice . FILTER(STRSTARTS(?notice, "PA")) }
  ?article schema:about ?item ;
           schema:isPartOf <https://fr.wikipedia.org/> .
}
"""
# Those that are no more: demolished, dissolved or closed (P576).
GONE_QUERY = """
SELECT DISTINCT ?item WHERE {
  VALUES ?item { %s }
  ?item wdt:P576 ?end .
}
"""

# What Wikidata calls a place that is not one to stand in front of. Each line
# reads the kinds of an item, as Wikidata names them in French.
NOT_A_PLACE = re.compile(
    r"arrondissement|quartier|circonscription|commune|ville\b|"
    r"\brue\b|\bvoie\b|avenue|boulevard|\bquai\b|périphérique|"
    r"station de métro|station du |ligne de|\bmétro\b|réseau|"
    r"fleuve|rivière|\bîle\b|colline|"
    r"attaque|attentat|incendie|massacre|fusillade|bataille|émeute|"
    r"cérémonie|événement|exposition|salon|festival|tournoi|compétition|"
    r"internationaux|discipline|épreuve|"
    r"organisation|association|entreprise|société|banque|marque|maison de haute|"
    r"parti |club|obédience|ordre |"
    r"université|faculté|école|lycée|collège|institut|académie|"
    r"établissement d'enseignement|établissement scolaire|institution|"
    r"distinction|accélérateur|chaîne|émission|journal|périodique",
    re.IGNORECASE,
)
# Wide green spaces, where aiming at something has little meaning (decision of
# 12 October 2026).
OPEN_GROUND = re.compile(
    r"jardin|\bparc\b|\bbois\b|\bsquare\b|cimetière|forêt|espace vert", re.IGNORECASE
)

KEEP, DROP = "keep", "drop"
NO_PLACE = "not_a_place"
GONE = "no_longer_there"
GREEN = "open_ground"
ON_MAP = "already_on_the_map"
LITTLE_KNOWN = "too_little_known"

SCHEMA = pa.schema(
    [
        ("qid", pa.string()),
        ("name", pa.string()),
        ("kinds", pa.string()),
        ("article", pa.string()),
        ("lat", pa.float64()),
        ("lon", pa.float64()),
        ("views", pa.int64()),
        ("languages", pa.int32()),
        # On the scale of the monuments: 1 for the best known of them.
        ("score", pa.float64()),
        # What the rules would do, and why they would leave the place out.
        ("suggestion", pa.string()),
        ("why", pa.string()),
        # The monument shown that the place stands in, if any.
        ("inside", pa.string()),
    ]
)

type Record = Mapping[str, Any]
type Row = dict[str, str]


def fetch_places(client: httpx.Client, *, pause: Pause = time.sleep) -> list[str]:
    """Return the identifiers of the known places of Paris without a notice."""
    rows = ingest_wikidata.run_query(client, PLACES_QUERY % MIN_LINKS, pause=pause)
    return sorted(
        {ingest_wikidata.qid_from_uri(row["item"]) for row in rows},
        key=lambda qid: int(qid[1:]),
    )


def fetch_gone(
    client: httpx.Client, qids: Sequence[str], *, pause: Pause = time.sleep
) -> list[str]:
    """Return those of the items that have an end date."""
    gone: set[str] = set()
    for batch in batched(qids, BATCH_SIZE):
        pause(PAUSE_SECONDS)
        values = " ".join(f"wd:{qid}" for qid in batch)
        rows = ingest_wikidata.run_query(client, GONE_QUERY % values, pause=pause)
        gone.update(ingest_wikidata.qid_from_uri(row["item"]) for row in rows)
    return sorted(gone, key=lambda qid: int(qid[1:]))


class Scale:
    """How known the monuments are, to place anything else among them."""

    def __init__(self, ranked: Sequence[Record], last_rank_shown: int) -> None:
        """Read the candidates of the selection, with their place in its ranking."""
        self.views = sorted(row["views"] for row in ranked)
        self.languages = sorted(row["languages"] for row in ranked)
        last = next(row for row in ranked if row["rank"] == last_rank_shown)
        # What the last monument shown scores on this scale: the bar to pass.
        self.bar = self.score(last["views"], last["languages"])

    def score(self, views: int, languages: int) -> float:
        """Place a subject among the monuments, from 0 to 1, on both measures."""
        by_views = bisect_right(self.views, views) / len(self.views)
        by_languages = bisect_right(self.languages, languages) / len(self.languages)
        return (by_views + by_languages) / 2


def find_hosts(places: Sequence[Record], monuments: Sequence[Record]) -> dict[str, str]:
    """Name the monument shown that each place stands in or against, if any."""
    located = [place for place in places if place["lat"] is not None]
    if not located or not monuments:
        return {}
    points = gpd.GeoSeries(
        gpd.points_from_xy(
            [place["lon"] for place in located], [place["lat"] for place in located]
        ),
        crs=WGS84,
    ).to_crs(LAMBERT_93)
    shapes = gpd.GeoSeries(
        [monument["geometry"] for monument in monuments], crs=WGS84
    ).to_crs(LAMBERT_93)
    tree = shapely.STRtree(shapes.values)
    hosts = {}
    for place, point in zip(located, points, strict=True):
        near = tree.query(point, predicate="dwithin", distance=SAME_PLACE_M)
        if len(near) > 0:
            nearest = min(near, key=lambda index: shapes.iloc[index].distance(point))
            hosts[place["qid"]] = monuments[nearest]["name"]
    return hosts


def judge(
    place: Record, *, gone: bool, host: str | None, known_enough: bool
) -> tuple[str, str | None]:
    """Suggest whether to keep a place, with the first reason to leave it out."""
    kinds = "; ".join(place["instance_of"])
    if place["lat"] is None or NOT_A_PLACE.search(kinds):
        return DROP, NO_PLACE
    if gone:
        return DROP, GONE
    if OPEN_GROUND.search(kinds):
        return DROP, GREEN
    if host is not None:
        return DROP, ON_MAP
    if not known_enough:
        return DROP, LITTLE_KNOWN
    return KEEP, None


def build_candidates(
    places: Sequence[Record],
    views: Mapping[str, int],
    gone: Sequence[str],
    hosts: Mapping[str, str],
    scale: Scale,
) -> pd.DataFrame:
    """One line per place found, the best known first, with a suggestion."""
    left = set(gone)
    rows = []
    for place in places:
        read = views.get(place["frwiki_title"], 0)
        score = scale.score(read, place["sitelinks"])
        host = hosts.get(place["qid"])
        suggestion, why = judge(
            place,
            gone=place["qid"] in left,
            host=host,
            known_enough=score >= scale.bar,
        )
        rows.append(
            {
                "qid": place["qid"],
                "name": place["label_fr"] or place["frwiki_title"],
                "kinds": "; ".join(place["instance_of"]),
                "article": place["frwiki_title"],
                "lat": place["lat"],
                "lon": place["lon"],
                "views": read,
                "languages": place["sitelinks"],
                "score": score,
                "suggestion": suggestion,
                "why": why,
                "inside": host,
            }
        )
    rows.sort(key=lambda row: (-row["score"], int(row["qid"][1:])))
    return from_rows(rows, SCHEMA)


def read_shown_monuments(
    notices: Sequence[Record], geometries: Sequence[Record], chosen: Sequence[Record]
) -> list[dict[str, Any]]:
    """The monuments that the app shows, with their name and their outline."""
    names = {notice["merimee_id"]: notice["name"] for notice in notices}
    shown = {row["merimee_id"] for row in chosen if row["shown"]}
    return [
        {"name": names[row["merimee_id"]], "geometry": row["geometry"]}
        for row in geometries
        if row["merimee_id"] in shown
    ]


def summarize(candidates: pd.DataFrame) -> dict[str, int]:
    """Count what would be kept, and what would not, by reason."""
    counts = {
        "places": len(candidates),
        "suggested": int((candidates["suggestion"] == KEEP).sum()),
    }
    for why, count in candidates["why"].value_counts().sort_index().items():
        counts[f"left_out_{why}"] = int(count)
    return counts


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Find the well-known places of Paris that are not protected."
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="reuse the last saved answers instead of querying the services",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if args.offline:
        snapshot = json.loads(ITEMS_SNAPSHOT.read_text())
        item_rows, gone = snapshot["items"], snapshot["gone"]
        views = json.loads(VIEWS_SNAPSHOT.read_text())["views"]
    else:
        with ingest_wikidata.make_client() as client:
            qids = fetch_places(client)
            item_rows = ingest_wikidata.fetch_items(client, qids)
            gone = fetch_gone(client, qids)
        selection.save_snapshot(ITEMS_SNAPSHOT, "items", item_rows)
        snapshot = json.loads(ITEMS_SNAPSHOT.read_text())
        ITEMS_SNAPSHOT.write_text(
            json.dumps({**snapshot, "gone": gone}, ensure_ascii=False, indent=1) + "\n"
        )
    places = [
        place
        for place in map(ingest_wikidata.build_item, item_rows)
        if place["frwiki_title"] is not None
    ]
    if not args.offline:
        # The readings already fetched are kept: only new articles are asked for.
        views = (
            json.loads(VIEWS_SNAPSHOT.read_text())["views"]
            if VIEWS_SNAPSHOT.exists()
            else {}
        )
        titles = sorted({str(place["frwiki_title"]) for place in places} - set(views))
        with web.make_client() as client:
            views.update(selection.fetch_views(client, titles))
        selection.save_snapshot(VIEWS_SNAPSHOT, "views", views)

    chosen = to_records(pd.read_parquet(SELECTION_PARQUET))
    ranked = [row for row in chosen if row["rank"] is not None]
    known = [row for row in ranked if row["views"] is not None]
    scale = Scale(known, selection.LAST_RANK_SHOWN)
    monuments = read_shown_monuments(
        to_records(pd.read_parquet(MERIMEE_PARQUET)),
        to_records(pd.DataFrame(gpd.read_parquet(GEOMETRIES_PARQUET))),
        chosen,
    )
    candidates = build_candidates(
        places, views, gone, find_hosts(places, monuments), scale
    )
    write_parquet(candidates, SCHEMA, CANDIDATES_PARQUET)
    candidates.to_csv(CANDIDATES_CSV, index=False)

    logger.info("Wrote %d places to %s", len(candidates), CANDIDATES_PARQUET)
    for label, count in summarize(candidates).items():
        logger.info("  %-28s %5d", label, count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
