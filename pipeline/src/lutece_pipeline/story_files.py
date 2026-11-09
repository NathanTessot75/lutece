"""The review files of the story pages: one per place, read and corrected by hand.

`write_stories` drafts them; a person reads each one, corrects it and marks it
"relu"; `export_bundle` reads them into the file the app carries.
"""

import re
from pathlib import Path
from typing import Any

from lutece_pipeline.paths import REVIEW_DIR

STORIES_DIR = REVIEW_DIR / "stories"

TO_REVIEW = "à relire"
REVIEWED = "relu"
TO_ENRICH = "à enrichir"
STATUSES = (TO_REVIEW, REVIEWED, TO_ENRICH)


SECTION = re.compile(r"^## (.+)$", re.MULTILINE)
SECTIONS = {
    "En bref": "summary",
    "Histoire": "story",
    "Le saviez-vous ?": "did_you_know",
}


def parse_story(text: str, where: str) -> dict[str, Any]:
    """Read a review file back: its fields and its sections."""
    if not text.startswith("---\n"):
        raise ValueError(f"{where}: no header")
    header, _, body = text[4:].partition("\n---\n")
    fields = {}
    for line in header.splitlines():
        name, separator, value = line.partition(":")
        if separator:
            fields[name.strip()] = value.strip()
    if fields.get("statut") not in STATUSES:
        raise ValueError(f"{where}: statut must be one of {STATUSES}")
    story: dict[str, Any] = {
        "key": fields["cle"],
        "status": fields["statut"],
        "sources": [
            source.strip()
            for source in fields.get("sources", "").split(",")
            if source.strip()
        ],
        "wikipedia": fields.get("wikipedia"),
        "revision": int(fields["revision"]) if fields.get("revision") else None,
        "summary": None,
        "story": None,
        "did_you_know": None,
    }
    parts = SECTION.split(body)
    for title, content in zip(parts[1::2], parts[2::2], strict=True):
        if title.strip() not in SECTIONS:
            raise ValueError(f"{where}: unknown section {title!r}")
        story[SECTIONS[title.strip()]] = content.strip() or None
    if story["status"] != TO_ENRICH and (
        story["summary"] is None or story["story"] is None
    ):
        raise ValueError(f"{where}: a story needs « En bref » and « Histoire »")
    return story


def read_stories(folder: Path) -> dict[str, dict[str, Any]]:
    """Every review file, by place."""
    stories = {}
    for path in sorted(folder.glob("*.md")):
        story = parse_story(path.read_text(encoding="utf-8"), path.name)
        stories[story["key"]] = story
    return stories


def file_name(key: str) -> str:
    return f"{key}.md"
