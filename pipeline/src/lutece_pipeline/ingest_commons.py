"""Step 7 - list the photos that Wikimedia Commons holds for each monument.

Wikidata gives most monuments a Commons category and a main image. The step
lists the files of each category, reads their size, author, licence and date,
and keeps those that can serve as a reference photo: a recent photograph of the
outside, large enough, under a free licence. Up to 15 of them are selected for
each monument, from different authors and years.

It only reads descriptions: the images themselves are not downloaded. A word
in a file name is all that tells a staircase from a street front, so the step
also compares its choices with photos that a reviewer looked at.

Run with: uv run python -m lutece_pipeline.ingest_commons
"""

import argparse
import csv
import html
import json
import logging
import re
import time
import unicodedata
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import nullcontext
from dataclasses import dataclass, field
from datetime import UTC, datetime
from itertools import batched
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
import pyarrow as pa

from lutece_pipeline import ingest_merimee, ingest_wikidata, resolve_entities
from lutece_pipeline.paths import INTERIM_DIR, RAW_DIR, REVIEW_DIR
from lutece_pipeline.tables import from_rows, to_records, write_parquet
from lutece_pipeline.web import Pause, make_client, post_form

logger = logging.getLogger(__name__)

API_URL = "https://commons.wikimedia.org/w/api.php"
# maxlag asks the servers to refuse the request when they are busy replicating.
BASE_PARAMS = {"action": "query", "format": "json", "formatversion": "2", "maxlag": "5"}
MAXLAG_ATTEMPTS = 5
MAXLAG_DELAY_SECONDS = 5.0
REQUEST_PAUSE_SECONDS = 0.1
TITLES_PER_REQUEST = 50
# The width asked for the thumbnail of each file: one of the sizes Commons keeps ready.
THUMBNAIL_WIDTH = 960
FILE_PARAMS = {
    "prop": "imageinfo",
    "iiprop": "url|size|mime|user|extmetadata",
    "iiurlwidth": str(THUMBNAIL_WIDTH),
    "iiextmetadatafilter": (
        "Artist|Assessments|Categories|DateTimeOriginal|GPSLatitude|GPSLongitude"
        "|License|LicenseShortName|LicenseUrl"
    ),
}

JPEG = "image/jpeg"
# Shorter side of the original, in pixels, under which a photo is too coarse.
# The image model reads 224 px; most photos set aside at 1000 px were good ones.
MIN_SHORT_SIDE = 640
# Older images show another state of the monument, or are drawings and engravings.
OLDEST_YEAR = 1950
MAX_SELECTED = 15
# A monument with fewer kept photos than this also gets those of its subcategories.
ENOUGH_PHOTOS = 5

HTML_TAG = re.compile(r"<[^>]+>")
YEAR = re.compile(r"(?<!\d)(1\d{3}|20\d{2})(?!\d)")
# The date that Commons templates add for machines: "date QS:P571,+1650-00-00T00:00:00Z/7".
MACHINE_DATE = "date QS:"
MACHINE_YEAR = re.compile(r"\+(\d{4})-")
# Licences whose terms the app can meet with a credit line: a name, a link.
FREE_LICENCE = re.compile(r"cc0|cc-zero|pd|cc-by(?:-sa)?-\d")
# Free licences that Commons names without giving them a code.
FREE_LICENCE_NAMES = frozenset(
    {"Attribution", "Copyrighted free use", "Licence Ouverte", "No restrictions"}
)
# Words, in a file name or in its categories, that tell the picture does not show
# the outside of the monument as a passer-by sees it. They are compared with the
# text in lower case and without accents; an underscore stands for a space.
UNWANTED_WORDS = {
    "inside": (
        r"interieure?s? interiors? inside innen\w*"
        r" escaliers? stair\w* couloirs? corridors? vestibules?"
        " (?<!town_)(?<!city_)hall lecture_halls? salles? salons? rooms? foyers?"
        r" stacks bookshel\w+ plafonds? ceilings? cellars? cryptes? crypts?"
        " sacristies? nefs? naves? choeurs? choirs? autels? altars? orgues? organs?"
        " chaires? pulpits? vitrail vitraux stained fresques? frescos? platforms?"
    ),
    "detail": "details? close-?ups? gros_plans? plaques? inscriptions?",
    "document": (
        "plans? maps? elevations? coupes? maquettes? models? dessins? drawings?"
        r" gravures? engravings? estampes? prints? etchings? lithograph\w*"
        " peintures? paintings? tableaux? aquarelles? watercolou?rs?"
        " postcards? cartes?_postales? affiches? posters? logos? medailles?"
        " medals? stamps? artworks? in_art collections?_of openstreetmap"
        " black_and_white sepia monochrome historical_images? vieux_paris atget"
        " marville carnavalet paris_musees gallica bibliotheque_nationale"
        " base_memoire gwtoolset rijksmuseum"
    ),
    "other": (
        r"portraits? musicians? performers? funeral obseques events? ceremon\w+"
        " concerts? demonstrations? manifestations? expositions? exhibitions?"
        r" blocus blockades? protests? wikimania olympi\w+ alumni visitors?"
        " inaugurations? history_of"
        " food_and_drink trains_in travaux chantier construction demolition"
        r" restoration restauration scaffold\w* echafaud\w* incendie"
        " incidental aerial remote_views? views?_from graffiti"
    ),
}
# Words that only count in a file name, where they give the subject of the
# picture. As a category they often describe something the picture merely
# contains: "Windows in Paris" is found on whole fronts.
NAME_ONLY_WORDS = {
    "inside": "antichambres? chambres? cabinets?",
    "detail": (
        "panneaux? signs? enseignes? blasons? coats?_of_arms chapiteaux? capitals?"
        r" frontons? pediments? tympan\w* balcons? balcon\w+ wrought railings?"
        r" ferronner\w+ fenetres? (?<!shop_)windows? heurtoirs? knockers?"
        " cadrans? sundials? mosaiques? mosaics?"
    ),
    "sculpture": (
        r"statues? sculptures? reliefs? bas-reliefs? mascarons? caryatid\w*"
        " atlantes? gargouilles? gargoyles? medaillons?"
    ),
}
SUBJECT_KINDS = ("inside", "detail", "sculpture", "document", "other")


def compile_words(words: str) -> tuple[re.Pattern[str], ...]:
    """Turn a list of words into patterns that match them as whole words."""
    return tuple(
        re.compile(rf"\b(?:{word.replace('_', ' ')})\b") for word in words.split()
    )


UNWANTED_ANYWHERE = {
    kind: compile_words(UNWANTED_WORDS.get(kind, "")) for kind in SUBJECT_KINDS
}
UNWANTED_IN_NAMES = {
    kind: compile_words(NAME_ONLY_WORDS.get(kind, "")) for kind in SUBJECT_KINDS
}
# Kinds of unwanted subject that are the very subject of some monuments: the
# inside of a covered passage is the passage, the statues of a fountain are the
# fountain. Keyed by Mérimée denomination.
EXEMPT_KINDS = {
    "passage couvert": "inside",
    "galerie marchande": "inside",
    "fontaine": "sculpture",
    "monument": "sculpture",
    "tombeau": "sculpture",
    "monument funéraire": "sculpture",
    "chapelle funéraire": "sculpture",
    "cimetière": "sculpture",
    "arc de triomphe": "sculpture",
    "porte de ville": "sculpture",
}
# Monuments that lie underground: only their entrances show. Keyed by denomination.
ENTRANCE_ONLY = frozenset({"station de métro"})
ENTRANCE = re.compile(
    r"\b(?:acces|entrees?|entrances?|edicules?|guimard|bouches?|entourages?)\b"
)
# Subcategories that gather views of the outside: "Exterior of Église Saint-Eustache".
EXTERIOR_SUBCATEGORY = re.compile(
    rf"\b(?:exteriors?|exterieure?s?|facades?)\b|{ENTRANCE.pattern}"
)
# The other subcategories read for a monument that lacks photos: the pictures
# that Commons distinguished ("Quality images of the Eiffel Tower") and the
# addresses that make up the monument ("12 place Dauphine, Paris"). The rest
# holds too much else: replicas, events, the tenants of the building.
FALLBACK_SUBCATEGORY = re.compile(
    r"\b(?:quality|valued|featured) (?:images|pictures) of\b"
    r"|^\d[\w ,-]*? (?:rue|place|quai|boulevard|avenue|impasse|cite|passage|villa"
    r"|square|cour|allee)\b"
)

MERIMEE_PARQUET = ingest_merimee.OUTPUT_PARQUET
ENTITIES_PARQUET = resolve_entities.ENTITIES_PARQUET
WIKIDATA_ITEMS_PARQUET = ingest_wikidata.ITEMS_PARQUET
RAW_FOLDER = RAW_DIR / "commons"
LABELS_CSV = REVIEW_DIR / "commons_labels.csv"
FILES_PARQUET = INTERIM_DIR / "commons_files.parquet"
CATEGORIES_PARQUET = INTERIM_DIR / "commons_categories.parquet"
EVALUATION_CSV = INTERIM_DIR / "commons_evaluation.csv"

# What a reviewer saw on a photo: "ok" is a view of the outside of the monument.
LABELS = frozenset({"ok", "inside", "detail", "document", "other"})
# The rules were adjusted on the "dev" photos. The "test" ones were labelled
# afterwards and only measure the rules: they must not be used to change them.
SAMPLES = frozenset({"dev", "test"})
EVALUATION_COLUMNS = [
    "merimee_id",
    "title",
    "sample",
    "label",
    "reject_reason",
    "selected",
    "outcome",
]

FILES_SCHEMA = pa.schema(
    [
        ("merimee_id", pa.string()),
        ("title", pa.string()),
        ("source", pa.string()),
        ("category", pa.string()),
        ("page_url", pa.string()),
        ("thumb_url", pa.string()),
        ("width", pa.int32()),
        ("height", pa.int32()),
        ("mime", pa.string()),
        ("author", pa.string()),
        ("uploader", pa.string()),
        ("licence", pa.string()),
        ("licence_url", pa.string()),
        ("year", pa.int16()),
        ("camera_lat", pa.float64()),
        ("camera_lon", pa.float64()),
        ("reject_reason", pa.string()),
        ("rank", pa.int16()),
        ("selected", pa.bool_()),
    ]
)
CATEGORIES_SCHEMA = pa.schema(
    [
        ("commons_category", pa.string()),
        ("files", pa.int32()),
        ("subcats", pa.int32()),
    ]
)

type Answer = dict[str, Any]
type FileRecord = dict[str, Any]
type Record = Mapping[str, Any]


@dataclass
class Cache:
    """Raw answers kept on disk, one JSON line per key.

    The step needs a few thousand requests. Each answer is appended to the file
    as soon as it arrives, so a run that failed resumes where it stopped, and
    the step can be replayed without the network.
    """

    path: Path
    entries: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def open(cls, path: Path) -> "Cache":
        entries = {}
        if path.exists():
            lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
            if lines and not lines[-1].endswith("\n"):
                # The previous run was stopped while it was writing this answer.
                lines.pop()
                path.write_text("".join(lines), encoding="utf-8")
            for line in lines:
                record = json.loads(line)
                entries[record["key"]] = record["value"]
        return cls(path, entries)

    def add(self, key: str, value: object) -> None:
        self.entries[key] = value
        record = {
            "key": key,
            "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "value": value,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")


def call_api(
    client: httpx.Client, params: Mapping[str, str], *, pause: Pause = time.sleep
) -> Answer:
    """Send one query to Commons and return its answer.

    A busy server answers with a "maxlag" error rather than a result: the query
    is sent again after a wait. Any other error stops the step.
    """
    for _ in range(MAXLAG_ATTEMPTS):
        response = post_form(client, API_URL, {**BASE_PARAMS, **params}, pause=pause)
        answer: Answer = response.json()
        error = answer.get("error")
        if error is None:
            return answer
        if error.get("code") != "maxlag":
            raise RuntimeError(f"Commons refused the query: {error}")
        retry_after = response.headers.get("retry-after", "")
        delay = float(retry_after) if retry_after.isdigit() else MAXLAG_DELAY_SECONDS
        logger.warning("Commons is lagging, retrying in %.0f s", delay)
        pause(delay)
    raise RuntimeError(f"Commons is still lagging after {MAXLAG_ATTEMPTS} attempts")


def query_all(
    client: httpx.Client,
    params: Mapping[str, str],
    *,
    follow: str,
    pause: Pause = time.sleep,
) -> Iterator[Answer]:
    """Yield the answers of a query, asking for the rest while there is some.

    Only the continuation named `follow` is followed. Commons offers others
    that lead elsewhere: "gcmcontinue" to the files beyond the first 500 of a
    category, "iistart" to the older versions of a file.
    """
    continuation: dict[str, str] = {}
    while True:
        answer = call_api(client, {**params, **continuation}, pause=pause)
        yield answer
        previous, continuation = continuation, answer.get("continue", {})
        if follow not in continuation:
            return
        if continuation == previous:
            raise RuntimeError(f"Commons repeats the same continuation: {previous}")
        pause(REQUEST_PAUSE_SECONDS)


def merge_pages(answers: Iterator[Answer]) -> dict[str, dict[str, Any]]:
    """Gather the pages of successive answers by title.

    Commons describes 50 files per answer at most: the others come as bare
    titles, and get their description in a later answer.
    """
    pages: dict[str, dict[str, Any]] = {}
    for answer in answers:
        for page in answer.get("query", {}).get("pages", []):
            pages.setdefault(page["title"], {}).update(page)
    return pages


def file_record(page: Mapping[str, Any]) -> FileRecord | None:
    """Keep what the step reads of a file page, as Commons states it."""
    descriptions = page.get("imageinfo")
    if not descriptions:
        return None
    description = descriptions[0]
    metadata = description.get("extmetadata", {})
    return {
        "title": page["title"],
        "user": description.get("user"),
        "width": description.get("width"),
        "height": description.get("height"),
        "mime": description.get("mime"),
        "page_url": description.get("descriptionurl"),
        "thumb_url": description.get("thumburl"),
        "metadata": {key: value.get("value") for key, value in metadata.items()},
    }


def fetch_category_info(
    client: httpx.Client, categories: Sequence[str], *, pause: Pause = time.sleep
) -> dict[str, dict[str, int]]:
    """Return how many files and subcategories each existing category holds."""
    counts: dict[str, dict[str, int]] = {}
    for batch in batched(sorted(set(categories)), TITLES_PER_REQUEST):
        titles = "|".join(f"Category:{name}" for name in batch)
        answers = query_all(
            client,
            {"prop": "categoryinfo", "titles": titles},
            follow="cicontinue",
            pause=pause,
        )
        for title, page in merge_pages(answers).items():
            info = page.get("categoryinfo")
            if info is not None:
                counts[title.removeprefix("Category:")] = {
                    "files": info["files"],
                    "subcats": info["subcats"],
                }
        pause(REQUEST_PAUSE_SECONDS)
    return counts


def fetch_category_files(
    client: httpx.Client, category: str, *, pause: Pause = time.sleep
) -> list[FileRecord]:
    """Describe the files placed directly in a category, 500 at most."""
    params = {
        "generator": "categorymembers",
        "gcmtitle": f"Category:{category}",
        "gcmtype": "file",
        "gcmlimit": "max",
        **FILE_PARAMS,
    }
    # All the files are listed in the first answer, 50 are described in each.
    answers = query_all(client, params, follow="iicontinue", pause=pause)
    records = map(file_record, merge_pages(answers).values())
    return sorted(
        (record for record in records if record is not None),
        key=lambda record: record["title"],
    )


def fetch_subcategories(
    client: httpx.Client, category: str, *, pause: Pause = time.sleep
) -> list[str]:
    """Return the names of the categories placed directly in a category."""
    params = {
        "list": "categorymembers",
        "cmtitle": f"Category:{category}",
        "cmtype": "subcat",
        "cmlimit": "max",
    }
    names = [
        member["title"].removeprefix("Category:")
        for answer in query_all(client, params, follow="cmcontinue", pause=pause)
        for member in answer["query"]["categorymembers"]
    ]
    return sorted(names)


def fetch_files(
    client: httpx.Client, names: Sequence[str], *, pause: Pause = time.sleep
) -> dict[str, FileRecord | None]:
    """Describe files given by name; a file that no longer exists maps to None."""
    described: dict[str, FileRecord | None] = {}
    for batch in batched(sorted(set(names)), TITLES_PER_REQUEST):
        params = {
            "titles": "|".join(f"File:{name}" for name in batch),
            "redirects": "1",
            **FILE_PARAMS,
        }
        answers = list(query_all(client, params, follow="iicontinue", pause=pause))
        # Commons rewrites the titles it is given (underscores, first letter),
        # then follows the redirect left behind when a file was renamed.
        renamed = {
            change["from"]: change["to"]
            for kind in ("normalized", "redirects")
            for answer in answers
            for change in answer.get("query", {}).get(kind, [])
        }
        pages = merge_pages(iter(answers))
        for name in batch:
            title = f"File:{name}"
            title = renamed.get(title, title)
            title = renamed.get(title, title)
            described[name] = file_record(pages.get(title, {}))
        pause(REQUEST_PAUSE_SECONDS)
    return described


@dataclass
class Source:
    """The answers of Commons: read from the caches, completed from the service.

    Without a client the step works offline, with the answers it already has.
    """

    client: httpx.Client | None
    info: Cache
    files: Cache
    subcategories: Cache
    named: Cache
    pause: Pause = time.sleep

    @classmethod
    def open(cls, folder: Path, client: httpx.Client | None) -> "Source":
        return cls(
            client,
            Cache.open(folder / "category_info.jsonl"),
            Cache.open(folder / "category_files.jsonl"),
            Cache.open(folder / "subcategories.jsonl"),
            Cache.open(folder / "files.jsonl"),
        )

    def _complete(
        self,
        cache: Cache,
        keys: Sequence[str],
        fetch: Callable[[httpx.Client, Sequence[str]], Mapping[str, object]],
        batch_size: int,
        what: str,
    ) -> dict[str, Any]:
        """Ask the service for the keys the cache lacks, then return those it has."""
        wanted = sorted(set(keys))
        missing = [key for key in wanted if key not in cache.entries]
        if missing and self.client is None:
            logger.warning("Offline: %d %s are not in the cache", len(missing), what)
        elif missing and self.client is not None:
            logger.info("Asking Commons for %d %s", len(missing), what)
            for done, batch in enumerate(batched(missing, batch_size), start=1):
                answers = fetch(self.client, batch)
                for key in batch:
                    cache.add(key, answers.get(key))
                if done * batch_size % 200 == 0:
                    logger.info("  %d of %d", done * batch_size, len(missing))
                self.pause(REQUEST_PAUSE_SECONDS)
        return {key: cache.entries[key] for key in wanted if key in cache.entries}

    def category_info(self, categories: Sequence[str]) -> dict[str, dict[str, int]]:
        """Count the files and subcategories of the categories that exist."""

        def fetch(client: httpx.Client, batch: Sequence[str]) -> Mapping[str, object]:
            return fetch_category_info(client, batch, pause=self.pause)

        answers = self._complete(
            self.info, categories, fetch, TITLES_PER_REQUEST, "category counts"
        )
        return {name: info for name, info in answers.items() if info is not None}

    def category_files(self, categories: Sequence[str]) -> dict[str, list[FileRecord]]:
        """List the files placed directly in each category."""

        def fetch(client: httpx.Client, batch: Sequence[str]) -> Mapping[str, object]:
            return {
                name: fetch_category_files(client, name, pause=self.pause)
                for name in batch
            }

        return self._complete(self.files, categories, fetch, 1, "category listings")

    def subcategories_of(self, categories: Sequence[str]) -> dict[str, list[str]]:
        """List the names of the subcategories of each category."""

        def fetch(client: httpx.Client, batch: Sequence[str]) -> Mapping[str, object]:
            return {
                name: fetch_subcategories(client, name, pause=self.pause)
                for name in batch
            }

        return self._complete(
            self.subcategories, categories, fetch, 1, "subcategory listings"
        )

    def named_files(self, names: Sequence[str]) -> dict[str, FileRecord]:
        """Describe the files given by name that still exist."""

        def fetch(client: httpx.Client, batch: Sequence[str]) -> Mapping[str, object]:
            return fetch_files(client, batch, pause=self.pause)

        answers = self._complete(
            self.named, names, fetch, TITLES_PER_REQUEST, "files given by name"
        )
        return {name: record for name, record in answers.items() if record is not None}


@dataclass(frozen=True)
class Photo:
    """A Commons file as the step reads it."""

    title: str
    page_url: str | None
    thumb_url: str | None
    width: int | None
    height: int | None
    mime: str | None
    author: str | None
    uploader: str | None
    licence: str | None
    licence_code: str | None
    licence_url: str | None
    year: int | None
    camera_lat: float | None
    camera_lon: float | None
    assessment: str | None
    categories: tuple[str, ...]


@dataclass(frozen=True)
class Monument:
    """A protected notice, and where Wikidata says its pictures are on Commons."""

    merimee_id: str
    category: str | None
    main_image: str | None
    # Its own names: a word they contain cannot count against its photos.
    names: tuple[str, ...]
    # The kinds of unwanted subject that do not apply to it.
    exempt: frozenset[str] = frozenset()
    # Whether only its entrances can be seen, the rest being underground.
    entrance_only: bool = False


@dataclass(frozen=True)
class Candidate:
    """A file found for a monument, and how it was found."""

    photo: Photo
    source: str  # main_image, category, exterior_subcategory or subcategory
    category: str | None


@dataclass(frozen=True)
class Answers:
    """What Commons said about the categories and the files of the monuments."""

    info: Mapping[str, Mapping[str, int]]
    listings: Mapping[str, Sequence[FileRecord]]
    children: Mapping[str, Sequence[str]]
    named: Mapping[str, FileRecord]
    # The categories of the monuments themselves: one is never read for another.
    taken: frozenset[str] = frozenset()


def clean_text(value: str | None) -> str | None:
    """Turn the HTML that Commons returns for a field into plain text."""
    without_tags = HTML_TAG.sub(" ", value or "")
    return " ".join(html.unescape(without_tags).split()) or None


def photo_year(value: str | None) -> int | None:
    """Read the year a picture was made from its date as written on Commons.

    The date is free text: "2014-06-21 15:02:11", "En 07–10–1903", "circa 1814",
    "17th century". The first year written wins; failing that, the one that the
    template states for machines.
    """
    written, _, for_machines = (clean_text(value) or "").partition(MACHINE_DATE)
    found = YEAR.search(written) or MACHINE_YEAR.search(for_machines)
    return int(found.group(1)) if found else None


def to_number(value: object) -> float | None:
    """Read a coordinate that Commons gives as text."""
    try:
        return float(str(value))
    except ValueError:
        return None


def describe(record: FileRecord) -> Photo:
    """Read a cached file answer."""
    metadata = record["metadata"]
    categories = (metadata.get("Categories") or "").split("|")
    return Photo(
        title=record["title"],
        page_url=record["page_url"],
        thumb_url=record["thumb_url"],
        width=record["width"],
        height=record["height"],
        mime=record["mime"],
        author=clean_text(metadata.get("Artist")),
        uploader=record["user"],
        licence=clean_text(metadata.get("LicenseShortName")),
        licence_code=metadata.get("License"),
        licence_url=metadata.get("LicenseUrl"),
        year=photo_year(metadata.get("DateTimeOriginal")),
        camera_lat=to_number(metadata.get("GPSLatitude")),
        camera_lon=to_number(metadata.get("GPSLongitude")),
        assessment=metadata.get("Assessments") or None,
        categories=tuple(name for name in categories if name),
    )


def fold(text: str) -> str:
    """Lowercase a text and strip its accents, to compare words."""
    decomposed = unicodedata.normalize("NFKD", text.lower().replace("œ", "oe"))
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def own_names(monument: Monument) -> str:
    """The names of a monument, folded into one text to search for words."""
    return fold(" | ".join(monument.names))


def unwanted_subject(
    name: str, categories: Sequence[str], monument: Monument
) -> str | None:
    """Name the kind of unwanted subject that a file or a category announces.

    A word that the monument's own names contain is not held against its photos:
    "salle" says nothing about the pictures of the Salle Pleyel.
    """
    in_name = fold(name)
    anywhere = fold(" | ".join([name, *categories]))
    own = own_names(monument)
    for kind in SUBJECT_KINDS:
        if kind in monument.exempt:
            continue
        searches = [
            (UNWANTED_ANYWHERE[kind], anywhere),
            (UNWANTED_IN_NAMES[kind], in_name),
        ]
        for words, text in searches:
            if any(word.search(text) and not word.search(own) for word in words):
                return kind
    return None


def reject_reason(photo: Photo, monument: Monument) -> str | None:
    """Tell why a file cannot serve as a reference photo, or None if it can."""
    if photo.mime != JPEG:
        return "format"
    if (
        not FREE_LICENCE.match(photo.licence_code or "")
        and photo.licence not in FREE_LICENCE_NAMES
    ):
        return "licence"
    if photo.year is not None and photo.year < OLDEST_YEAR:
        return "old"
    name = photo.title.removeprefix("File:").rsplit(".", 1)[0]
    subject = unwanted_subject(name, photo.categories, monument)
    if subject is not None:
        return subject
    if monument.entrance_only and not ENTRANCE.search(
        fold(" | ".join([name, *photo.categories]))
    ):
        return "inside"
    if min(photo.width or 0, photo.height or 0) < MIN_SHORT_SIDE:
        return "small"
    return None


def rank_photos(photos: Sequence[Photo], main_title: str | None) -> list[Photo]:
    """Order the photos kept for a monument; the first ones make the selection.

    The main image of the Wikidata item comes first, then the photos that
    Commons distinguished. The others alternate between sessions, an author in
    a given year, starting with the most recent: two photos of the same session
    are more likely to show the same angle in the same light.
    """
    first = [photo for photo in photos if photo.title == main_title]
    awarded = sorted(
        (
            photo
            for photo in photos
            if photo.assessment is not None and photo.title != main_title
        ),
        key=lambda photo: photo.title,
    )
    sessions: dict[tuple[int, str], list[Photo]] = {}
    for photo in sorted(photos, key=lambda photo: photo.title):
        if photo.assessment is None and photo.title != main_title:
            key = (-(photo.year or 0), photo.author or photo.uploader or "")
            sessions.setdefault(key, []).append(photo)
    ordered = [sessions[key] for key in sorted(sessions)]
    rounds = range(max(map(len, ordered), default=0))
    alternated = [
        session[turn] for turn in rounds for session in ordered if turn < len(session)
    ]
    return [*first, *awarded, *alternated]


def chosen_subcategories(
    children: Sequence[str],
    monument: Monument,
    *,
    fallback: bool,
    taken: frozenset[str] = frozenset(),
) -> list[tuple[str, str]]:
    """Pick the subcategories of a monument whose files are worth reading.

    Those that gather views of the outside always are. A few others serve a
    monument that lacks photos. None is read when its name announces another
    subject or when it is `taken`, being the category of another monument.
    Each one comes with the source to record for its files.
    """
    chosen = []
    for name in children:
        if name in taken or unwanted_subject(name, (), monument) is not None:
            continue
        if EXTERIOR_SUBCATEGORY.search(fold(name)):
            chosen.append((name, "exterior_subcategory"))
        elif fallback and FALLBACK_SUBCATEGORY.search(fold(name)):
            chosen.append((name, "subcategory"))
    return chosen


def main_record(monument: Monument, answers: Answers) -> FileRecord | None:
    """Find the description of the main image of a monument."""
    if monument.main_image is None:
        return None
    title = f"File:{monument.main_image}"
    for record in answers.listings.get(monument.category or "", ()):
        if record["title"] == title:
            return record
    return answers.named.get(monument.main_image)


def find_candidates(
    monument: Monument, answers: Answers, *, fallback: bool
) -> list[Candidate]:
    """Gather the files of a monument, each one under the first source that has it."""
    found: dict[str, Candidate] = {}

    def add(records: Sequence[FileRecord], source: str, category: str | None) -> None:
        for record in records:
            found.setdefault(
                record["title"], Candidate(describe(record), source, category)
            )

    main = main_record(monument, answers)
    if main is not None:
        add([main], "main_image", None)
    if monument.category is not None:
        add(answers.listings.get(monument.category, ()), "category", monument.category)
        children = answers.children.get(monument.category, ())
        chosen = chosen_subcategories(
            children, monument, fallback=fallback, taken=answers.taken
        )
        # The views of the outside first: a file is kept under its best source.
        for name, source in sorted(chosen, key=lambda pair: pair[1]):
            add(answers.listings.get(name, ()), source, name)
    return list(found.values())


def lacks_photos(monument: Monument, answers: Answers) -> bool:
    """Tell whether a monument has too few photos without its other subcategories."""
    candidates = find_candidates(monument, answers, fallback=False)
    kept = [
        candidate
        for candidate in candidates
        if reject_reason(candidate.photo, monument) is None
    ]
    return len(kept) < ENOUGH_PHOTOS


def monument_rows(monument: Monument, answers: Answers) -> list[dict[str, Any]]:
    """Describe every file found for a monument, kept or not, and rank the kept ones."""
    fallback = lacks_photos(monument, answers)
    candidates = find_candidates(monument, answers, fallback=fallback)
    reasons = {
        candidate.photo.title: reject_reason(candidate.photo, monument)
        for candidate in candidates
    }
    kept = [
        candidate.photo
        for candidate in candidates
        if reasons[candidate.photo.title] is None
    ]
    main = main_record(monument, answers)
    ranked = rank_photos(kept, main["title"] if main is not None else None)
    ranks = {photo.title: position for position, photo in enumerate(ranked, start=1)}
    rows = []
    for candidate in sorted(candidates, key=lambda candidate: candidate.photo.title):
        photo = candidate.photo
        rank = ranks.get(photo.title)
        rows.append(
            {
                "merimee_id": monument.merimee_id,
                "title": photo.title,
                "source": candidate.source,
                "category": candidate.category,
                "page_url": photo.page_url,
                "thumb_url": photo.thumb_url,
                "width": photo.width,
                "height": photo.height,
                "mime": photo.mime,
                "author": photo.author,
                "uploader": photo.uploader,
                "licence": photo.licence,
                "licence_url": photo.licence_url,
                "year": photo.year,
                "camera_lat": photo.camera_lat,
                "camera_lon": photo.camera_lon,
                "reject_reason": reasons[photo.title],
                "rank": rank,
                "selected": rank is not None and rank <= MAX_SELECTED,
            }
        )
    return rows


def read_monuments(
    notices: Sequence[Record], entities: Sequence[Record], items: Sequence[Record]
) -> list[Monument]:
    """Pair each protected notice with the Commons category and image of its item."""
    item_of = {entity["merimee_id"]: entity["wikidata_qid"] for entity in entities}
    items_by_id = {item["qid"]: item for item in items}
    monuments = []
    for notice in notices:
        if notice["protection"] is None:
            continue  # cancelled protections and cross-references are not monuments
        item = items_by_id.get(item_of.get(notice["merimee_id"]), {})
        denominations = notice["denominations"]
        names = [
            notice["name"],
            *(denominations if denominations is not None else ()),
            item.get("label_fr"),
            item.get("commons_category"),
        ]
        monuments.append(
            Monument(
                merimee_id=notice["merimee_id"],
                category=item.get("commons_category"),
                main_image=item.get("image_file"),
                names=tuple(name for name in names if name),
                exempt=frozenset(
                    EXEMPT_KINDS[name] for name in names if name in EXEMPT_KINDS
                ),
                entrance_only=any(name in ENTRANCE_ONLY for name in names),
            )
        )
    return monuments


def collect(source: Source, monuments: Sequence[Monument]) -> Answers:
    """Get from Commons, or from the caches, everything the monuments need."""
    taken = frozenset(m.category for m in monuments if m.category is not None)
    info = source.category_info(sorted(taken))
    listings = source.category_files(
        [name for name, counts in info.items() if counts["files"] > 0]
    )
    children = source.subcategories_of(
        [name for name, counts in info.items() if counts["subcats"] > 0]
    )

    def subcategories(monument: Monument, *, fallback: bool) -> list[str]:
        own_children = children.get(monument.category or "", ())
        chosen = chosen_subcategories(
            own_children, monument, fallback=fallback, taken=taken
        )
        return [name for name, _ in chosen]

    listings |= source.category_files(
        [name for m in monuments for name in subcategories(m, fallback=False)]
    )
    listed = {
        (name, record["title"])
        for name, records in listings.items()
        for record in records
    }
    named = source.named_files(
        [
            m.main_image
            for m in monuments
            if m.main_image is not None
            and (m.category, f"File:{m.main_image}") not in listed
        ]
    )
    answers = Answers(info, listings, children, named, taken)
    listings |= source.category_files(
        [
            name
            for m in monuments
            if lacks_photos(m, answers)
            for name in subcategories(m, fallback=True)
        ]
    )
    return Answers(info, listings, children, named, taken)


def build_files(monuments: Sequence[Monument], answers: Answers) -> pd.DataFrame:
    """One line per monument and file found for it."""
    rows = [row for monument in monuments for row in monument_rows(monument, answers)]
    return from_rows(rows, FILES_SCHEMA)


def build_categories(answers: Answers) -> pd.DataFrame:
    """One line per Commons category of a monument, with what it holds."""
    rows = [
        {
            "commons_category": name,
            "files": counts["files"],
            "subcats": counts["subcats"],
        }
        for name, counts in sorted(answers.info.items())
    ]
    return from_rows(rows, CATEGORIES_SCHEMA)


def read_labels(path: Path) -> list[dict[str, str]]:
    """Read what a reviewer saw on the photos of the two samples."""
    if not path.exists():
        return []
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    with path.open(newline="", encoding="utf-8") as file:
        for line_number, row in enumerate(csv.DictReader(file), start=2):
            where = f"{path.name} line {line_number}"
            if row["label"] not in LABELS:
                raise ValueError(f"{where}: unknown label {row['label']!r}")
            if row["sample"] not in SAMPLES:
                raise ValueError(f"{where}: unknown sample {row['sample']!r}")
            key = (row["merimee_id"], row["title"])
            if key in seen:
                raise ValueError(f"{where}: {row['title']} appears twice")
            seen.add(key)
            rows.append(row)
    return rows


def evaluate(files: pd.DataFrame, labels: Sequence[Mapping[str, str]]) -> pd.DataFrame:
    """Compare what the step decided for each labelled photo with what it shows.

    Only the reasons that rest on the subject are judged: a photo rejected for
    its size, its age, its format or its licence is not a mistake of the words.
    """
    decided = {(row.merimee_id, row.title): row for row in files.itertuples()}
    rows = []
    gone = 0
    for label in labels:
        decision = decided.get((label["merimee_id"], label["title"]))
        if decision is None:
            gone += 1
            continue
        reason = None if pd.isna(decision.reject_reason) else decision.reject_reason
        good = label["label"] == "ok"
        if reason is None:
            outcome = "kept_rightly" if good else "kept_wrongly"
        elif reason in SUBJECT_KINDS:
            outcome = "rejected_wrongly" if good else "rejected_rightly"
        else:
            outcome = "not_judged"
        rows.append(
            {
                "merimee_id": label["merimee_id"],
                "title": label["title"],
                "sample": label["sample"],
                "label": label["label"],
                "reject_reason": reason,
                "selected": bool(decision.selected),
                "outcome": outcome,
            }
        )
    if gone:
        logger.warning("%d labelled photos are no longer listed", gone)
    return pd.DataFrame(rows, columns=EVALUATION_COLUMNS)


def summarize(
    monuments: Sequence[Monument], files: pd.DataFrame, evaluation: pd.DataFrame
) -> dict[str, int]:
    """Count the files, the reasons to reject them and the monuments served."""
    selected = files[files["selected"]].groupby("merimee_id").size()
    counts = {
        "monuments": len(monuments),
        "monuments_with_a_category": sum(m.category is not None for m in monuments),
        "monuments_with_a_photo": len(selected),
        f"monuments_with_{ENOUGH_PHOTOS}_photos": int(
            (selected >= ENOUGH_PHOTOS).sum()
        ),
        f"monuments_with_{MAX_SELECTED}_photos": int((selected >= MAX_SELECTED).sum()),
        "files": len(files),
        "files_kept": int(files["reject_reason"].isna().sum()),
        "files_selected": int(files["selected"].sum()),
    }
    for reason, count in files["reject_reason"].value_counts().items():
        counts[f"rejected={reason}"] = int(count)
    outcomes = evaluation.groupby(["sample", "outcome"]).size()
    for (sample, outcome), count in outcomes.items():
        counts[f"{sample}_{outcome}"] = int(count)
    return counts


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="List the photos that Wikimedia Commons holds for each monument."
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="only use the Commons answers saved by the previous runs",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="forget the saved answers and ask Commons again for everything",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.offline and args.refresh:
        parser.error("--offline and --refresh cannot be used together")

    monuments = read_monuments(
        to_records(pd.read_parquet(MERIMEE_PARQUET)),
        to_records(pd.read_parquet(ENTITIES_PARQUET)),
        to_records(pd.read_parquet(WIKIDATA_ITEMS_PARQUET)),
    )
    if args.refresh:
        for path in RAW_FOLDER.glob("*.jsonl"):
            path.unlink()
    with nullcontext() if args.offline else make_client() as client:
        answers = collect(Source.open(RAW_FOLDER, client), monuments)

    files = build_files(monuments, answers)
    categories = build_categories(answers)
    evaluation = evaluate(files, read_labels(LABELS_CSV))
    write_parquet(files, FILES_SCHEMA, FILES_PARQUET)
    write_parquet(categories, CATEGORIES_SCHEMA, CATEGORIES_PARQUET)
    evaluation.to_csv(EVALUATION_CSV, index=False)

    logger.info("Wrote %d files to %s", len(files), FILES_PARQUET)
    logger.info("Wrote %d categories to %s", len(categories), CATEGORIES_PARQUET)
    for label, count in summarize(monuments, files, evaluation).items():
        logger.info("  %-28s %6d", label, count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
