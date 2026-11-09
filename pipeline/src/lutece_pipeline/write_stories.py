"""Step 8 - the story page of each place, drafted by Claude from its sources.

SPEC §5.4: a summary of 2 to 3 sentences, shown at the capture, a story of
150 to 400 words, a "Le saviez-vous ?" and the sources cited. A model drafts
them in the pipeline, never in the app, from the notice Mérimée and the
Wikipedia article only; a person then reviews them.

Each draft lands in `review/stories/<key>.md`, where it is read, corrected and
marked "relu". A file already there is never overwritten: a correction by hand
survives every run. The answers of the model are kept in
`data/raw/stories/answers.jsonl`, by place and by the fingerprint of what was
sent, so a run asks only for what changed and the files can be rewritten
without paying again.

The drafts go through the Message Batches API: half the price, an answer
within the hour.

Run with: uv run python -m lutece_pipeline.write_stories
"""

import argparse
import hashlib
import json
import logging
import sqlite3
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import anthropic
import pandas as pd
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages import MessageBatchIndividualResponse
from anthropic.types.messages.batch_create_params import Request

from lutece_pipeline import (
    export_bundle,
    fetch_articles,
    ingest_merimee,
    story_files,
    web,
)
from lutece_pipeline.paths import RAW_DIR
from lutece_pipeline.tables import to_records

logger = logging.getLogger(__name__)

MODEL = "claude-opus-5-5"
EFFORT = "medium"
MAX_TOKENS = 16000
# What is read of an article: its beginning, which tells the history, cut at
# the end of a paragraph. Most articles are shorter (median 11 000).
ARTICLE_CHARACTERS = 20_000
# Changed with the instructions, so that new drafts are asked for.
PROMPT_VERSION = "2026-11-10"
POLL_SECONDS = 30

BUNDLE_DB = export_bundle.BUNDLE_DB
MERIMEE_PARQUET = ingest_merimee.OUTPUT_PARQUET
ARTICLES_PARQUET = fetch_articles.ARTICLES_PARQUET
ANSWERS_JSONL = RAW_DIR / "stories" / "answers.jsonl"
STORIES_DIR = story_files.STORIES_DIR
SOURCES = ("merimee", "wikipedia")

SYSTEM = """Tu rédiges la fiche d'un lieu de Paris pour Lutèce, un jeu où l'on \
photographie les monuments pour les collectionner. Le lecteur est un promeneur \
curieux, debout devant le lieu ; écris pour lui un français clair et vivant, \
sans jargon inutile.

Tu n'utilises que les faits des sources fournies, jamais tes propres \
connaissances : une date, un nom, un chiffre absents des sources ne figurent pas \
dans la fiche. Reformule, sans recopier de phrases des sources. Quand les \
sources se contredisent, suis la notice Mérimée.

- summary : 2 à 3 phrases, ce qui rend le lieu remarquable, lues au moment où \
le joueur le capture.
- story : son histoire, de 150 à 400 mots, dans l'ordre du temps, en \
paragraphes séparés par une ligne vide.
- did_you_know : un fait surprenant des sources, en une phrase ; vide si aucun \
ne l'est vraiment.
- sources_used : les identifiants des sources dont viennent les faits.
- enough : false quand les sources ne suffisent pas à une fiche fidèle de \
150 mots ; summary, story et did_you_know restent alors vides."""

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "enough": {"type": "boolean"},
        "summary": {"type": "string"},
        "story": {"type": "string"},
        "did_you_know": {"type": "string"},
        "sources_used": {
            "type": "array",
            "items": {"type": "string", "enum": list(SOURCES)},
        },
    },
    "required": ["enough", "summary", "story", "did_you_know", "sources_used"],
    "additionalProperties": False,
}

type Record = Mapping[str, Any]


def place_key(row: Record) -> str:
    """A monument by its notice, a place without one by its Wikidata item."""
    return row["merimee_id"] or row["wikidata_qid"]


def read_places(path: Path) -> list[dict[str, Any]]:
    """The places of the bundle, with what a story page may say of them."""
    database = sqlite3.connect(path)
    database.row_factory = sqlite3.Row
    try:
        rows = database.execute(
            "select id, merimee_id, wikidata_qid, title, address, arrondissement,"
            " category, century, architects, wikipedia, protection from monuments"
        ).fetchall()
    finally:
        database.close()
    return sorted(
        ({**dict(row), "key": place_key(row)} for row in rows),
        key=lambda row: row["key"],
    )


def shorten(text: str, limit: int = ARTICLE_CHARACTERS) -> str:
    """The beginning of a text, cut at the last paragraph within the limit."""
    if len(text) <= limit:
        return text
    cut = text.rfind("\n\n", 0, limit)
    return text[: cut if cut > 0 else limit]


def describe(place: Record) -> str:
    """The facts of the bundle, for the model to name the place right."""
    facts = [f"Lieu : {place['title']}"]
    if place["category"]:
        facts.append(f"Genre : {place['category']}")
    if place["century"]:
        facts.append(f"Siècle de construction : {place['century']}e")
    architects = json.loads(place["architects"] or "[]")
    if architects:
        facts.append(f"Architectes : {', '.join(architects)}")
    if place["arrondissement"]:
        facts.append(f"Arrondissement : {place['arrondissement']}")
    if place["protection"]:
        facts.append(f"Protection : {place['protection']} monument historique")
    return "\n".join(facts)


def build_sources(
    place: Record, notice: Record | None, article: Record | None
) -> dict[str, str]:
    """The texts given to the model, by identifier: what it may draw facts from."""
    sources = {}
    if notice is not None:
        parts = [
            f"{label} : {notice[column].strip()}"
            for label, column in (
                ("Historique", "history_raw"),
                ("Description", "description_raw"),
            )
            if notice[column] and notice[column].strip()
        ]
        if parts:
            sources["merimee"] = "\n\n".join(parts)
    if article is not None and article["text"]:
        sources["wikipedia"] = shorten(article["text"])
    return sources


def build_message(place: Record, sources: Mapping[str, str]) -> str:
    blocks = [describe(place)]
    for name, text in sources.items():
        blocks.append(f'<source id="{name}">\n{text}\n</source>')
    return "\n\n".join(blocks)


def fingerprint(message: str) -> str:
    """What makes a draft: the model, the instructions and the sources."""
    content = json.dumps(
        [MODEL, EFFORT, PROMPT_VERSION, SYSTEM, message], ensure_ascii=False
    )
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def request_params(message: str) -> MessageCreateParamsNonStreaming:
    return MessageCreateParamsNonStreaming(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM,
        output_config={
            "effort": EFFORT,
            "format": {"type": "json_schema", "schema": ANSWER_SCHEMA},
        },
        messages=[{"role": "user", "content": message}],
    )


def read_answers(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    """The answers kept, by place and fingerprint."""
    if not path.exists():
        return {}
    answers = {}
    with path.open(encoding="utf-8") as file:
        for line in file:
            if line.strip():
                answer = json.loads(line)
                answers[(answer["key"], answer["fingerprint"])] = answer
    return answers


def read_result(
    result: MessageBatchIndividualResponse, fingerprints: Mapping[str, str]
) -> dict[str, Any]:
    """One result of a batch, as a line of the answers kept."""
    key = result.custom_id
    line: dict[str, Any] = {
        "key": key,
        "fingerprint": fingerprints[key],
        "model": MODEL,
        "drafted_at": datetime.now(UTC).date().isoformat(),
        "outcome": result.result.type,
    }
    if result.result.type != "succeeded":
        line["error"] = str(getattr(result.result, "error", ""))
        return line
    message = result.result.message
    line["stop_reason"] = message.stop_reason
    line["usage"] = {
        "input_tokens": message.usage.input_tokens,
        "output_tokens": message.usage.output_tokens,
    }
    text = next((block.text for block in message.content if block.type == "text"), None)
    if message.stop_reason == "end_turn" and text:
        line["draft"] = json.loads(text)
    return line


def draft(
    client: anthropic.Anthropic,
    messages: Mapping[str, str],
    answers_path: Path,
    *,
    pause: web.Pause = time.sleep,
) -> list[dict[str, Any]]:
    """Send the messages as one batch, wait for it, and keep every answer."""
    fingerprints = {key: fingerprint(message) for key, message in messages.items()}
    batch = client.messages.batches.create(
        requests=[
            Request(custom_id=key, params=request_params(message))
            for key, message in messages.items()
        ]
    )
    logger.info("Batch %s: %d drafts asked", batch.id, len(messages))
    while batch.processing_status != "ended":
        pause(POLL_SECONDS)
        batch = client.messages.batches.retrieve(batch.id)
        logger.info(
            "  %s: %d processing, %d done",
            batch.processing_status,
            batch.request_counts.processing,
            batch.request_counts.succeeded + batch.request_counts.errored,
        )
    lines = [
        read_result(result, fingerprints)
        for result in client.messages.batches.results(batch.id)
    ]
    answers_path.parent.mkdir(parents=True, exist_ok=True)
    with answers_path.open("a", encoding="utf-8") as file:
        for line in lines:
            file.write(json.dumps(line, ensure_ascii=False) + "\n")
    return lines


def render_story(place: Record, answer: Record, article: Record | None) -> str:
    """The review file of a place: what the model wrote, to read and correct."""
    found = answer["draft"]
    used = [source for source in SOURCES if source in found["sources_used"]]
    header = [
        "---",
        f"cle: {place['key']}",
        f"lieu: {place['title']}",
        f"statut: {story_files.TO_REVIEW if found['enough'] else story_files.TO_ENRICH}",
        f"sources: {', '.join(used)}",
    ]
    if "wikipedia" in used and article is not None:
        header += [
            f"wikipedia: {article['page_title']}",
            f"revision: {article['revision']}",
        ]
    header += [f"redaction: {answer['model']}, {answer['drafted_at']}", "---", ""]
    body = [f"# {place['title']}", ""]
    if not found["enough"]:
        body += [
            "Les sources ne suffisent pas à une fiche : elle reste à enrichir.",
            "",
        ]
    else:
        body += [
            "## En bref",
            "",
            found["summary"].strip(),
            "",
            "## Histoire",
            "",
            found["story"].strip(),
            "",
        ]
        if found["did_you_know"].strip():
            body += ["## Le saviez-vous ?", "", found["did_you_know"].strip(), ""]
    return "\n".join(header + body)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Draft the story page of each place.")
    parser.add_argument("--keys", nargs="+", help="draft only these places")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="count what would be sent, without asking the model",
    )
    parser.add_argument(
        "--write-only",
        action="store_true",
        help="write the missing review files from the answers kept, without asking",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    places = read_places(BUNDLE_DB)
    notices = {
        row["merimee_id"]: row
        for row in to_records(
            pd.read_parquet(
                MERIMEE_PARQUET,
                columns=["merimee_id", "history_raw", "description_raw"],
            )
        )
    }
    articles = {
        row["title"]: row for row in to_records(pd.read_parquet(ARTICLES_PARQUET))
    }
    if args.keys:
        places = [place for place in places if place["key"] in set(args.keys)]

    STORIES_DIR.mkdir(parents=True, exist_ok=True)
    answers = read_answers(ANSWERS_JSONL)
    messages, ready = {}, {}
    for place in places:
        if (STORIES_DIR / story_files.file_name(place["key"])).exists():
            continue
        article = articles.get(place["wikipedia"])
        sources = build_sources(place, notices.get(place["merimee_id"]), article)
        message = build_message(place, sources)
        kept = answers.get((place["key"], fingerprint(message)))
        if kept is not None and "draft" in kept:
            ready[place["key"]] = kept
        else:
            messages[place["key"]] = message

    characters = sum(len(message) for message in messages.values()) + len(SYSTEM) * len(
        messages
    )
    logger.info(
        "%d places to draft (about %d input tokens), %d answers kept to write",
        len(messages),
        characters // 3,
        len(ready),
    )
    if messages and not (args.dry_run or args.write_only):
        for line in draft(anthropic.Anthropic(), messages, ANSWERS_JSONL):
            if "draft" in line:
                ready[line["key"]] = line
            else:
                logger.warning(
                    "  no draft for %s: %s",
                    line["key"],
                    line.get("error") or line.get("stop_reason"),
                )

    by_key = {place["key"]: place for place in places}
    for key, answer in sorted(ready.items()):
        place = by_key[key]
        story = render_story(place, answer, articles.get(place["wikipedia"]))
        (STORIES_DIR / story_files.file_name(key)).write_text(story, encoding="utf-8")
    logger.info("Wrote %d review files to %s", len(ready), STORIES_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
