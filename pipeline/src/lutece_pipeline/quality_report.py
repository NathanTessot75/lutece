"""Step 12 - measure what the base holds for each monument, and what it lacks.

The step crosses the tables of the other steps into one line per protected
monument: what is known about it, how many photos it has, and whether it is
ready for the app. It then writes a report in French with the coverage of each
piece of information, the measured reliability of the steps and the list of
problems. It reads no service.

Run with: uv run python -m lutece_pipeline.quality_report
"""

import argparse
import logging
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa

from lutece_pipeline import (
    geometry,
    ingest_commons,
    ingest_merimee,
    ingest_wikidata,
    nearby_buildings,
    resolve_entities,
    visibility,
)
from lutece_pipeline.paths import PIPELINE_ROOT, PROCESSED_DIR
from lutece_pipeline.tables import from_rows, to_records, write_parquet

logger = logging.getLogger(__name__)

# A monument that can be seen from the street is ready for the app when its
# outline is known; with a mere circle around a point, it is only approximately.
READY, APPROXIMATE, NOT_READY = "ready", "approximate", "not_ready"
ENOUGH_PHOTOS = ingest_commons.ENOUGH_PHOTOS
# Words that say a building is a former one, not what it is called.
FORMER = re.compile(r"\((?:ancien(?:ne)?s?)\)|\bancien(?:ne)?s?\b", re.IGNORECASE)
# A second capital in a one-word name makes it a proper name: "Pont-Neuf".
SECOND_CAPITAL = re.compile(r"-[A-ZÀ-Ý]")
# One-word names that are a kind of place although they carry a second capital.
COMMON_COMPOUNDS = frozenset({"café-bar"})
MOST_COMMON_CATEGORIES = 12

MERIMEE_PARQUET = ingest_merimee.OUTPUT_PARQUET
ENTITIES_PARQUET = resolve_entities.ENTITIES_PARQUET
ENTITY_LINKS_PARQUET = resolve_entities.LINKS_PARQUET
WIKIDATA_ITEMS_PARQUET = ingest_wikidata.ITEMS_PARQUET
GEOMETRIES_PARQUET = geometry.GEOMETRIES_PARQUET
VISIBILITY_PARQUET = visibility.VISIBILITY_PARQUET
COMMONS_FILES_PARQUET = ingest_commons.FILES_PARQUET
REVIEW_FILES = {
    "Rapprochements douteux": resolve_entities.REVIEW_CSV,
    "Points de référence douteux": geometry.REVIEW_CSV,
    "Visibilités à trancher": visibility.REVIEW_CSV,
}
NEARBY_EVALUATION_CSV = nearby_buildings.EVALUATION_CSV
VISIBILITY_EVALUATION_CSV = visibility.EVALUATION_CSV
COMMONS_EVALUATION_CSV = ingest_commons.EVALUATION_CSV
QUALITY_PARQUET = PROCESSED_DIR / "monuments_quality.parquet"
PROBLEMS_CSV = PROCESSED_DIR / "quality_problems.csv"
REPORT_MD = PIPELINE_ROOT.parent / "docs" / "rapport" / "qualite-donnees.md"

SCHEMA = pa.schema(
    [
        ("merimee_id", pa.string()),
        ("name", pa.string()),
        ("arrondissement", pa.int16()),
        ("category", pa.string()),
        ("protection", pa.string()),
        ("has_own_name", pa.bool_()),
        ("has_wikidata", pa.bool_()),
        ("has_frwiki", pa.bool_()),
        ("has_century", pa.bool_()),
        ("has_architect", pa.bool_()),
        ("has_history", pa.bool_()),
        ("footprint_source", pa.string()),
        ("point_doubtful", pa.bool_()),
        ("visibility", pa.string()),
        ("photos", pa.int16()),
        ("readiness", pa.string()),
    ]
)
PROBLEM_COLUMNS = ["merimee_id", "name", "arrondissement", "problem", "merimee_url"]
# What can be wrong with a monument, and how the report words it.
PROBLEMS = {
    "no_wikidata_item": "Sans fiche Wikidata",
    "no_footprint": "Repéré par un cercle, faute de contour",
    "doubtful_point": "Point de référence douteux",
    "visibility_unknown": "Visibilité à trancher",
    "no_photo": "Visible depuis la rue mais sans photo",
}

type Record = Mapping[str, Any]


def has_own_name(name: str, denominations: Sequence[str] | None) -> bool:
    """Tell whether a notice has a name of its own, not just its kind of building.

    "Immeuble", "Hôtel (ancien)" or "Boulangerie" only say what the building is:
    the app will have to name such a monument after its address. A name of one
    word is a kind of building, unless it is a proper name like "Pont-Neuf".
    """
    bare = " ".join(FORMER.sub(" ", name).split())
    lowered = bare.lower()
    kinds = {kind.lower() for kind in (denominations or ())}
    if lowered in kinds or lowered.removesuffix("s") in kinds:
        return False
    if " " in bare:
        return True
    return bool(SECOND_CAPITAL.search(bare)) and lowered not in COMMON_COMPOUNDS


def readiness(visible: str, footprint_source: str | None) -> str:
    """Tell whether the app can offer a monument to capture."""
    if visible != visibility.VISIBLE:
        return NOT_READY
    return APPROXIMATE if footprint_source in (None, "buffer") else READY


def build_quality(
    notices: Sequence[Record],
    entities: Sequence[Record],
    items: Sequence[Record],
    geometries: Sequence[Record],
    visibilities: Sequence[Record],
    photos: Mapping[str, int],
) -> pd.DataFrame:
    """One line per protected monument: what is known about it, and its readiness."""
    item_of = {entity["merimee_id"]: entity["wikidata_qid"] for entity in entities}
    items_by_id = {item["qid"]: item for item in items}
    places = {row["merimee_id"]: row for row in geometries}
    seen = {row["merimee_id"]: row["visibility"] for row in visibilities}
    rows = []
    for notice in notices:
        if notice["protection"] is None:
            continue  # cancelled protections and cross-references are not monuments
        merimee_id = notice["merimee_id"]
        qid = item_of.get(merimee_id)
        item = items_by_id.get(qid, {})
        place = places.get(merimee_id, {})
        denominations = notice["denominations"]
        kinds = list(denominations) if denominations is not None else []
        architects = [notice["architects"], item.get("architects")]
        visible = seen.get(merimee_id, visibility.UNKNOWN)
        rows.append(
            {
                "merimee_id": merimee_id,
                "name": notice["name"],
                "arrondissement": notice["arrondissement"],
                "category": kinds[0] if kinds else None,
                "protection": notice["protection"],
                "has_own_name": has_own_name(notice["name"], kinds),
                "has_wikidata": qid is not None,
                "has_frwiki": item.get("frwiki_title") is not None,
                "has_century": notice["construction_century"] is not None,
                "has_architect": any(
                    names is not None and len(names) > 0 for names in architects
                ),
                "has_history": notice["history_raw"] is not None,
                "footprint_source": place.get("footprint_source"),
                "point_doubtful": bool(place.get("point_doubtful", False)),
                "visibility": visible,
                "photos": photos.get(merimee_id, 0),
                "readiness": readiness(visible, place.get("footprint_source")),
            }
        )
    return from_rows(rows, SCHEMA)


def find_problems(quality: pd.DataFrame) -> pd.DataFrame:
    """List what is wrong, one line per monument and problem."""
    visible = quality["visibility"] == visibility.VISIBLE
    found = {
        "no_wikidata_item": ~quality["has_wikidata"],
        "no_footprint": quality["footprint_source"].fillna("buffer") == "buffer",
        "doubtful_point": quality["point_doubtful"],
        "visibility_unknown": quality["visibility"] == visibility.UNKNOWN,
        "no_photo": visible & (quality["photos"] == 0),
    }
    rows = [
        {
            "merimee_id": row.merimee_id,
            "name": row.name,
            "arrondissement": row.arrondissement,
            "problem": problem,
            "merimee_url": f"https://pop.culture.gouv.fr/notice/merimee/{row.merimee_id}",
        }
        for problem, concerned in found.items()
        for row in quality[concerned.astype(bool)].itertuples(index=False)
    ]
    return pd.DataFrame(rows, columns=PROBLEM_COLUMNS)


def count(number: float) -> str:
    """Write a count the French way: 1 878."""
    return f"{int(number):,}".replace(",", " ")


def share(part: float, whole: float) -> str:
    """Write a count with its share of the whole: 1 749 (93 %)."""
    if whole == 0:
        return count(part)
    return f"{count(part)} ({round(100 * part / whole)} %)"


def table(header: Sequence[str], rows: Sequence[Sequence[object]]) -> list[str]:
    """Lay rows out as a Markdown table."""
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return lines


def coverage_rows(quality: pd.DataFrame) -> list[tuple[str, str]]:
    """How many monuments have each piece of information."""
    total = len(quality)
    known = {
        "Fiche Wikidata": quality["has_wikidata"],
        "Contour réel du bâtiment": quality["footprint_source"].fillna("buffer")
        != "buffer",
        "Visible depuis la rue": quality["visibility"] == visibility.VISIBLE,
        "Au moins une photo de référence": quality["photos"] >= 1,
        f"Au moins {ENOUGH_PHOTOS} photos de référence": quality["photos"]
        >= ENOUGH_PHOTOS,
        "Siècle de construction": quality["has_century"],
        "Article Wikipédia en français": quality["has_frwiki"],
        "Architecte connu": quality["has_architect"],
        "Historique dans la notice": quality["has_history"],
        "Nom propre, autre que « Immeuble » ou « Maison »": quality["has_own_name"],
    }
    return [(label, share(int(column.sum()), total)) for label, column in known.items()]


def group_rows(quality: pd.DataFrame, by: pd.Series) -> list[list[str]]:
    """Describe the monuments of each group: how many, how ready, how documented."""
    rows = []
    for key, group in quality.groupby(by, sort=False):
        total = len(group)
        rows.append(
            [
                str(key),
                count(total),
                share((group["readiness"] == READY).sum(), total),
                count((group["readiness"] == APPROXIMATE).sum()),
                count((group["readiness"] == NOT_READY).sum()),
                f"{group['photos'].median():g}".replace(".", ","),
                share(group["has_frwiki"].sum(), total),
            ]
        )
    return rows


def reliability_rows(
    links: pd.DataFrame,
    nearby: pd.DataFrame | None,
    seen: pd.DataFrame | None,
    photos: pd.DataFrame | None,
) -> list[tuple[str, str, str]]:
    """What each step measured about itself, on hand-checked samples."""
    rows = []
    for source, label in (("wikidata", "Wikidata"), ("osm", "OpenStreetMap")):
        pairs = links[links["source"] == source]
        confirmed = (pairs["status"] == "confirmed").sum()
        rows.append(
            (
                f"Rapprochement avec {label}",
                "liens confirmés, par les règles ou par une relecture",
                f"{count(confirmed)} sur {count(len(pairs))}",
            )
        )
    if nearby is not None:
        inside = nearby[nearby["match"] == "contains"]
        correct = (inside["outcome"] == "correct").sum()
        rows.append(
            (
                "Bâtiment trouvé autour du point",
                "bon bâtiment quand le point tombe dedans",
                f"{count(correct)} sur {count(len(inside))}",
            )
        )
    if seen is not None:
        test = seen[seen["sample"] == "test"]
        rows.append(
            (
                "Visibilité depuis la rue",
                "accord avec l'étiquette posée à la main, lot de test",
                f"{count(test['agree'].sum())} sur {count(len(test))}",
            )
        )
    if photos is not None:
        test = photos[photos["sample"] == "test"]
        kept = test[test["outcome"].str.startswith("kept")]
        rows.append(
            (
                "Photos de référence",
                "photos gardées qui montrent bien l'extérieur, lot de test",
                f"{count((kept['outcome'] == 'kept_rightly').sum())} sur {count(len(kept))}",
            )
        )
    return rows


def render_report(
    quality: pd.DataFrame,
    problems: pd.DataFrame,
    reliability: Sequence[tuple[str, str, str]],
    pending: Mapping[str, int],
) -> str:
    """Write the report, in French, as Markdown."""
    total = len(quality)
    levels = quality["readiness"].value_counts()
    ready, approximate = levels.get(READY, 0), levels.get(APPROXIMATE, 0)
    usable = quality[quality["readiness"] != NOT_READY]
    with_photo = usable[usable["photos"] >= 1]
    lines = [
        "# Qualité de la base des monuments",
        "",
        "Rapport produit par `uv run python -m lutece_pipeline.quality_report`,",
        "à partir des tables du pipeline. Ne pas le modifier à la main.",
        "",
        "## En bref",
        "",
        f"- La base compte **{count(total)} monuments** protégés à Paris.",
        f"- **{share(ready, total)} sont prêts pour l'app** : visibles depuis la rue,",
        "  avec le contour de leur bâtiment.",
        f"- {share(approximate, total)} sont prêts avec réserve : visibles, mais repérés",
        "  par un simple cercle de 10 m.",
        f"- {share(levels.get(NOT_READY, 0), total)} ne sont pas prêts : non visibles",
        "  depuis la rue, ou visibilité à trancher.",
        f"- Parmi les {count(len(usable))} monuments prêts, avec ou sans réserve,",
        f"  {count(len(with_photo))} ont au moins une photo de référence et",
        f"  {count(with_photo['has_frwiki'].sum())} ont aussi un article Wikipédia.",
        "",
        "## Ce que la base sait de chaque monument",
        "",
        *table(["Information", "Monuments"], coverage_rows(quality)),
        "",
        "## Par arrondissement",
        "",
        *table(
            [
                "Arrondissement",
                "Monuments",
                "Prêts",
                "Avec réserve",
                "Pas prêts",
                "Photos (médiane)",
                "Article Wikipédia",
            ],
            group_rows(
                quality.sort_values("arrondissement"),
                quality.sort_values("arrondissement")["arrondissement"],
            ),
        ),
        "",
        "## Par type de monument",
        "",
        f"Les {MOST_COMMON_CATEGORIES} types les plus fréquents, puis tous les autres.",
        "",
    ]
    common = quality["category"].value_counts().head(MOST_COMMON_CATEGORIES).index
    kinds = quality["category"].where(quality["category"].isin(common), "autres")
    order = {kind: position for position, kind in enumerate([*common, "autres"])}
    by_kind = quality.assign(kind=kinds).sort_values(
        "kind", key=lambda column: column.map(order), kind="stable"
    )
    lines += table(
        [
            "Type",
            "Monuments",
            "Prêts",
            "Avec réserve",
            "Pas prêts",
            "Photos (médiane)",
            "Article Wikipédia",
        ],
        group_rows(by_kind, by_kind["kind"]),
    )
    lines += [
        "",
        "## Fiabilité des étapes",
        "",
        "Les rapprochements sont des jointures exactes sur un identifiant,",
        "contrôlées par la distance et le nom. Les autres étapes ont été mesurées",
        "sur un échantillon vérifié à la main. Le détail et les limites sont dans",
        "`pipeline/README.md`.",
        "",
        *table(["Étape", "Mesure", "Résultat"], reliability),
        "",
        "## Problèmes",
        "",
        "La liste complète, monument par monument, est dans",
        "`pipeline/data/processed/quality_problems.csv`.",
        "",
    ]
    found = problems["problem"].value_counts()
    lines += table(
        ["Problème", "Monuments"],
        [
            (wording, count(found.get(problem, 0)))
            for problem, wording in PROBLEMS.items()
        ],
    )
    lines += ["", "Lignes en attente d'une relecture :", ""]
    lines += table(
        ["Fichier de relecture", "Lignes"],
        [(what, count(number)) for what, number in pending.items()],
    )
    return "\n".join(lines) + "\n"


def read_optional(path: Path) -> pd.DataFrame | None:
    """Read a table that a step only writes when it has something to say."""
    return pd.read_csv(path) if path.exists() else None


def summarize(quality: pd.DataFrame, problems: pd.DataFrame) -> dict[str, int]:
    """Count the monuments by readiness and the problems by kind."""
    counts = {"monuments": len(quality)}
    for level, number in quality["readiness"].value_counts().items():
        counts[f"readiness={level}"] = int(number)
    for problem, number in problems["problem"].value_counts().items():
        counts[f"problem={problem}"] = int(number)
    return counts


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure what the base holds for each monument, and what it lacks."
    )
    parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    files = pd.read_parquet(COMMONS_FILES_PARQUET, columns=["merimee_id", "selected"])
    photos = files[files["selected"]].groupby("merimee_id").size().to_dict()
    geometries = pd.read_parquet(
        GEOMETRIES_PARQUET,
        columns=["merimee_id", "footprint_source", "point_doubtful"],
    )
    quality = build_quality(
        to_records(pd.read_parquet(MERIMEE_PARQUET)),
        to_records(pd.read_parquet(ENTITIES_PARQUET)),
        to_records(pd.read_parquet(WIKIDATA_ITEMS_PARQUET)),
        to_records(geometries),
        to_records(pd.read_parquet(VISIBILITY_PARQUET)),
        photos,
    )
    problems = find_problems(quality)
    reliability = reliability_rows(
        pd.read_parquet(ENTITY_LINKS_PARQUET, columns=["source", "status"]),
        read_optional(NEARBY_EVALUATION_CSV),
        read_optional(VISIBILITY_EVALUATION_CSV),
        read_optional(COMMONS_EVALUATION_CSV),
    )
    pending = {
        what: len(pd.read_csv(path))
        for what, path in REVIEW_FILES.items()
        if path.exists()
    }

    write_parquet(quality, SCHEMA, QUALITY_PARQUET)
    problems.to_csv(PROBLEMS_CSV, index=False)
    REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
    REPORT_MD.write_text(
        render_report(quality, problems, reliability, pending), encoding="utf-8"
    )

    logger.info("Wrote %d monuments to %s", len(quality), QUALITY_PARQUET)
    logger.info("Wrote %d problems to %s", len(problems), PROBLEMS_CSV)
    logger.info("Wrote the report to %s", REPORT_MD)
    for label, number in summarize(quality, problems).items():
        logger.info("  %-28s %5d", label, number)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
