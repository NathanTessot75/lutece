"""Step 6 - tell whether what is protected can be seen from the public space.

The Mérimée notice describes the protected parts of each monument in a sentence
such as "Façades sur rue et toitures ; escalier avec sa rampe". The step reads
that sentence: an outside part that does not face a courtyard or a garden, or a
monument protected as a whole, makes the notice visible; a notice that only
lists inside parts or courtyard elevations is not.

It judges the text, not the site: a mansion protected as a whole may stand
behind a closed porch.

Run with: uv run python -m lutece_pipeline.visibility
"""

import argparse
import csv
import logging
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa

from lutece_pipeline import ingest_merimee
from lutece_pipeline.paths import INTERIM_DIR, REVIEW_DIR
from lutece_pipeline.tables import from_rows, to_records, write_parquet

logger = logging.getLogger(__name__)

VISIBLE, NOT_VISIBLE, UNKNOWN = "visible", "non_visible", "inconnu"
CLASSES = frozenset({VISIBLE, NOT_VISIBLE, UNKNOWN})
# The rules were adjusted on the "dev" notices. The "test" ones were labelled
# afterwards and only measure the rules: they must not be used to change them.
SAMPLES = frozenset({"dev", "test"})

# Outside parts of a building. A bare "porte" is too ambiguous to count.
OUTSIDE_PARTS = (
    r"facades?|toitures?|elevations?|couvertures?|devantures?|enseignes?|portails?"
    r"|entourages?|balcons?|clotures?|porches?|marquises?"
    r"|portes? (?:cocheres?|monumentales?|d'entree)|portes?(?= sur )"
)
INSIDE_PARTS = (
    r"escaliers?|rampes?|cages?|salons?|salles?|plafonds?|cheminees?|boiseries?|lambris"
    r"|vestibules?|caves?|sous-sols?|chambres?|appartements?|pieces?|antichambres?"
    r"|cabinets?|alcoves?|decors?|decorations?|interieure?s?|halls?|foyers?"
    r"|bibliotheques?|sacristies?|cryptes?|couloirs?|paliers?|peintures?|vitraux"
    r"|mobilier|orgues?|fresques?"
)
PART = re.compile(rf"\b(?:(?P<outside>{OUTSIDE_PARTS})|(?P<inside>{INSIDE_PARTS}))\b")
# Where an outside part faces. A part that faces a street, or whose side is not
# stated, can be seen; one that only faces a courtyard or a garden cannot.
STREET_SIDE = re.compile(
    r"\bsur (?:la |les |le |l')?(?:rues?|places?|quais?|boulevards?|bd|avenues?|voies?"
    r"|passages?|impasses?|squares?|cites?|parvis|esplanades?)\b"
    r"|\bcote rue\b|\bexterieure?s?\b|\bprincipales?\b|\banterieure?s?\b"
)
COURTYARD_SIDE = re.compile(
    r"\bsur (?:la |les |le )?(?:cours?|courettes?|jardins?|parc)\b"
    r"|\bcote (?:cour|jardin)\b|\bposterieure?s?\b|\barrieres?\b|\bau fond\b"
    r"|\b(?:entourant|bordant|autour de) (?:la |les |le )?(?:premiere |seconde )?(?:cours?|jardins?)\b"
)
# A roof whose side is not stated says nothing: it tops courtyard wings as well.
ROOF = re.compile(r"toitures?|couvertures?")
# Remains and small items whose place in the building the text does not give.
UNPLACED_ITEM = re.compile(
    r"^(?:le |la |les |l')?(?:vestiges?|restes?|mascarons?|bas-reliefs?|fragments?)\b"
)
# Outside parts that face the street by nature, unless the text says otherwise.
STREET_PARTS = re.compile(
    r"devantures?|enseignes?|portails?|entourages?"
    r"|portes? (?:cocheres?|monumentales?|d'entree)"
)
# "façades et toitures sur cour": two parts joined by "et" share the same side.
JOINED_BY_AND = re.compile(r"\s*et (?:les |la |le |l'|leurs? |des |de la |du )?\s*")
# A clause that opens by naming the monument itself rather than one of its parts.
MONUMENT_HEAD = re.compile(
    r"^(?:en totalite,? )?(?:la totalite (?:de la |de l'|du |des |de ))?"
    r"(?:l'|le |la |les |l'ancien(?:ne)? |ancien(?:ne)?s? )*"
    r"(?:eglise|cathedrale|basilique|chapelle|hotel|immeubles?|batiments?|maisons?"
    r"|pavillons?|tours?|chateau|palais|theatre|fontaine|pont|monument|temple"
    r"|synagogue|mairie|gare|halle|ecole|lycee|college|hopital|couvent|abbaye"
    r"|musee|edifice)\b"
)
# Words by which a clause adds parts to the monument instead of restricting to them.
INCLUDING = re.compile(
    r"\ben totalite\b|\bla totalite\b|\by compris\b|\bavec\b|\bainsi que\b"
)
# A monument that stands in a courtyard or a garden, or that is its very ground.
IN_COURTYARD = re.compile(
    r"\b(?:sur|dans|au fond de|au fond du) ?(?:la |le |l')?"
    r"(?:seconde |premiere |arriere-)?(?:cours?|courettes?|jardins?)\b"
)
GROUND_HEAD = re.compile(r"^(?:le |la |les |l')?(?:sols?|cours?|courettes?|jardins?)\b")
ADDED_ITEMS = re.compile(
    r"\b(?:avec|y compris|ainsi que|et (?:son|sa|ses|le|la|les|l'))"
)
ON_COURTYARD = re.compile(r"\s*sur (?:la |les |le )?(?:cours?|courettes?|jardins?)\b")
LEGAL_ENDING = re.compile(r":\s*(?:inscription|classement)\b[^;]*?(?=;|\s-\s|$)")
PARENTHESES = re.compile(r"\([^()]*\)")
CLAUSE_BREAK = re.compile(r";|\s-\s|\.\s")
# Works that lie underground whatever the wording of their protection.
UNDERGROUND = frozenset({"carrière", "carrière souterraine"})
# Open spaces that anyone can enter: their grounds are not a private courtyard.
PUBLIC_GROUNDS = frozenset(
    {
        "cimetière",
        "jardin",
        "jardin botanique",
        "jardin public",
        "parc",
        "place",
        "square",
    }
)

MERIMEE_PARQUET = ingest_merimee.OUTPUT_PARQUET
OVERRIDES_CSV = REVIEW_DIR / "visibility_overrides.csv"
LABELS_CSV = REVIEW_DIR / "visibility_labels.csv"
VISIBILITY_PARQUET = INTERIM_DIR / "visibility.parquet"
REVIEW_CSV = INTERIM_DIR / "visibility_to_review.csv"
EVALUATION_CSV = INTERIM_DIR / "visibility_evaluation.csv"

SCHEMA = pa.schema(
    [
        ("merimee_id", pa.string()),
        ("visibility", pa.string()),
        ("reason", pa.string()),
        ("evidence", pa.string()),
        ("reviewed", pa.bool_()),
    ]
)

type Record = Mapping[str, Any]


@dataclass(frozen=True)
class Clue:
    """A part named in the protection text, and what it says about visibility."""

    word: str
    kind: str  # street, open, whole, courtyard, inside, roof or unplaced


@dataclass(frozen=True)
class Label:
    """The class given by hand to a notice, and the sample it was drawn in."""

    visibility: str
    sample: str


def normalize(text: str | None) -> str:
    """Lowercase a text and strip its accents, keeping the punctuation."""
    lowered = (text or "").lower().replace("œ", "oe").replace("’", "'")
    decomposed = unicodedata.normalize("NFKD", lowered)
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def split_clauses(text: str | None) -> list[str]:
    """Cut a protection text into its protected elements, without the legal wording."""
    cleaned = normalize(text)
    previous = None
    while previous != cleaned:  # parentheses can be nested
        previous, cleaned = cleaned, PARENTHESES.sub(" ", cleaned)
    cleaned = LEGAL_ENDING.sub(" ", cleaned)
    return [
        clause.strip(" :,.")
        for clause in CLAUSE_BREAK.split(cleaned)
        if clause.strip(" :,.")
    ]


def side_of(context: str) -> str | None:
    """Tell which way an outside part faces from the words that follow it."""
    if STREET_SIDE.search(context):
        return "street"
    if COURTYARD_SIDE.search(context):
        return "courtyard"
    return None


def whole_clue(text: str) -> Clue:
    """Clue for a monument named as a whole: hidden if it stands in a courtyard.

    Only the monument itself is looked at, not what the clause adds to it: in
    "l'hôtel, y compris la cour", the mansion is protected, courtyard included.
    """
    monument = ADDED_ITEMS.split(text, maxsplit=1)[0]
    word = (monument.strip(" ,") or text.strip(" ,"))[:40]
    if GROUND_HEAD.match(monument) or (
        IN_COURTYARD.search(monument) and not STREET_SIDE.search(monument)
    ):
        return Clue(word, "courtyard")
    return Clue(word, "unplaced" if UNPLACED_ITEM.match(monument) else "whole")


def read_clause(clause: str) -> list[Clue]:
    """List the clues of one protected element.

    Each outside part gets the side stated before the next part. Two parts joined
    by "et" share the side of the second one, and "toiture correspondante" takes
    the side of the part before. A clause that names the monument and then adds
    parts ("l'église, y compris la crypte") also counts for the whole monument,
    whereas a name followed by a colon is only a heading for the parts listed.
    """
    heading, colon, listed = clause.partition(":")
    if colon and not PART.search(heading) and PART.search(listed):
        clause = listed.strip()
    parts = list(PART.finditer(clause))
    if not parts:
        return [whole_clue(clause)]

    clues = []
    before_parts = clause[: parts[0].start()]
    if MONUMENT_HEAD.match(clause) and INCLUDING.search(clause):
        clues.append(whole_clue(before_parts))

    sides: list[str | None] = []
    joined: list[bool] = []
    for part, following in zip(parts, [*parts[1:], None], strict=True):
        context = clause[part.end() : following.start() if following else len(clause)]
        side = side_of(context)
        if side is None and "correspondant" in context and sides:
            side = sides[-1]
        if STREET_PARTS.fullmatch(part.group()) and not ON_COURTYARD.match(context):
            side = "street"
        sides.append(side)
        joined.append(following is not None and bool(JOINED_BY_AND.fullmatch(context)))
    for index in range(len(parts) - 2, -1, -1):
        if joined[index] and side_of(clause[parts[index].end() :]) is not None:
            sides[index] = sides[index + 1]

    for part, side in zip(parts, sides, strict=True):
        if part.group("inside"):
            kind = "inside"
        elif side is None:
            kind = "roof" if ROOF.fullmatch(part.group()) else "open"
        else:
            kind = side
        clues.append(Clue(part.group(), kind))
    return clues


def read_text(text: str | None) -> list[Clue]:
    """List the clues found in a whole protection text."""
    return [clue for clause in split_clauses(text) for clue in read_clause(clause)]


def classify(
    text: str | None, denominations: Sequence[str] | None
) -> tuple[str, str, str]:
    """Return the visibility of a notice, the reason and the clues it rests on."""
    clues = read_text(text)
    evidence = "; ".join(f"{clue.word}: {clue.kind}" for clue in clues)
    kinds = {clue.kind for clue in clues}
    names = set(denominations) if denominations is not None else set()
    if names & UNDERGROUND:
        return NOT_VISIBLE, "underground", evidence
    if names & PUBLIC_GROUNDS:
        return VISIBLE, "public_grounds", evidence
    for kind, reason in (
        ("street", "outside_part_on_street"),
        ("open", "outside_part"),
        ("whole", "whole_monument"),
    ):
        if kind in kinds:
            return VISIBLE, reason, evidence
    hidden = kinds & {"inside", "courtyard"}
    if hidden == {"inside"}:
        return NOT_VISIBLE, "inside_only", evidence
    if hidden == {"courtyard"}:
        return NOT_VISIBLE, "courtyard_only", evidence
    if hidden:
        return NOT_VISIBLE, "inside_and_courtyard", evidence
    if "unplaced" in kinds:
        return UNKNOWN, "unplaced_item", evidence
    return UNKNOWN, "roofs_only" if kinds else "no_text", evidence


def read_rows(path: Path, column: str) -> dict[str, dict[str, str]]:
    """Read a hand-made file whose `column` gives a visibility class per notice."""
    if not path.exists():
        return {}
    rows: dict[str, dict[str, str]] = {}
    with path.open(newline="", encoding="utf-8") as file:
        for line_number, row in enumerate(csv.DictReader(file), start=2):
            where = f"{path.name} line {line_number}"
            if row[column] not in CLASSES:
                raise ValueError(f"{where}: unknown class {row[column]!r}")
            if row["merimee_id"] in rows:
                raise ValueError(f"{where}: {row['merimee_id']} appears twice")
            rows[row["merimee_id"]] = row
    return rows


def read_overrides(path: Path) -> dict[str, str]:
    """Read the classes that a review gives in place of the computed ones."""
    rows = read_rows(path, "visibility")
    return {merimee_id: row["visibility"] for merimee_id, row in rows.items()}


def read_labels(path: Path) -> dict[str, Label]:
    """Read the classes given by hand to the notices of the two samples."""
    labels = {}
    for merimee_id, row in read_rows(path, "label").items():
        if row["sample"] not in SAMPLES:
            raise ValueError(
                f"{path.name}: unknown sample {row['sample']!r} for {merimee_id}"
            )
        labels[merimee_id] = Label(row["label"], row["sample"])
    return labels


def build_visibility(
    notices: Sequence[Record], overrides: Mapping[str, str]
) -> pd.DataFrame:
    """Classify the protected notices; a reviewed class replaces the computed one."""
    rows = []
    for notice in notices:
        if notice["protection"] is None:
            continue  # cancelled protections and cross-references are not monuments
        visibility, reason, evidence = classify(
            notice["protection_desc"], notice["denominations"]
        )
        merimee_id = notice["merimee_id"]
        reviewed = merimee_id in overrides
        if reviewed:
            visibility, reason = overrides[merimee_id], "reviewed"
        rows.append(
            {
                "merimee_id": merimee_id,
                "visibility": visibility,
                "reason": reason,
                "evidence": evidence,
                "reviewed": reviewed,
            }
        )
    return from_rows(rows, SCHEMA)


def evaluate(notices: Sequence[Record], labels: Mapping[str, Label]) -> pd.DataFrame:
    """Compare the rules, before any correction, with the hand-made labels."""
    notices_by_id = {notice["merimee_id"]: notice for notice in notices}
    rows = []
    for merimee_id, label in sorted(labels.items()):
        if merimee_id not in notices_by_id:
            logger.warning("%s is labelled but is not a notice", merimee_id)
            continue
        notice = notices_by_id[merimee_id]
        predicted, reason, _ = classify(
            notice["protection_desc"], notice["denominations"]
        )
        rows.append(
            {
                "merimee_id": merimee_id,
                "sample": label.sample,
                "label": label.visibility,
                "predicted": predicted,
                "reason": reason,
                "agree": predicted == label.visibility,
            }
        )
    return pd.DataFrame(
        rows, columns=["merimee_id", "sample", "label", "predicted", "reason", "agree"]
    )


def build_review(notices: Sequence[Record], visibility: pd.DataFrame) -> pd.DataFrame:
    """List the notices that the rules could not decide."""
    notices_by_id = {notice["merimee_id"]: notice for notice in notices}
    rows = [
        {
            "merimee_id": row.merimee_id,
            "name": notices_by_id[row.merimee_id]["name"],
            "protection_desc": notices_by_id[row.merimee_id]["protection_desc"],
            "merimee_url": f"https://pop.culture.gouv.fr/notice/merimee/{row.merimee_id}",
        }
        for row in visibility.itertuples()
        if row.visibility == UNKNOWN
    ]
    return pd.DataFrame(
        rows, columns=["merimee_id", "name", "protection_desc", "merimee_url"]
    )


def summarize(visibility: pd.DataFrame, evaluation: pd.DataFrame) -> dict[str, int]:
    """Count the classes, the reasons and the agreement with the labels."""
    counts = {"monuments": len(visibility)}
    for column in ("visibility", "reason"):
        for value, count in visibility[column].value_counts().items():
            counts[f"{column}={value}"] = int(count)
    counts["reviewed"] = int(visibility["reviewed"].sum())
    for sample, rows in evaluation.groupby("sample"):
        counts[f"{sample}_labelled"] = len(rows)
        counts[f"{sample}_agree"] = int(rows["agree"].sum())
    return counts


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Tell whether what is protected can be seen from the public space."
    )
    parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    notices = to_records(pd.read_parquet(MERIMEE_PARQUET))
    overrides = read_overrides(OVERRIDES_CSV)
    visibility = build_visibility(notices, overrides)
    stale = sorted(set(overrides) - set(visibility["merimee_id"]))
    if stale:
        logger.warning("%d corrections match no monument: %s", len(stale), stale)
    evaluation = evaluate(notices, read_labels(LABELS_CSV))
    review = build_review(notices, visibility)

    write_parquet(visibility, SCHEMA, VISIBILITY_PARQUET)
    review.to_csv(REVIEW_CSV, index=False)
    evaluation.to_csv(EVALUATION_CSV, index=False)

    logger.info("Wrote %d monuments to %s", len(visibility), VISIBILITY_PARQUET)
    logger.info("Wrote %d lines to review to %s", len(review), REVIEW_CSV)
    for label, count in summarize(visibility, evaluation).items():
        logger.info("  %-34s %5d", label, count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
