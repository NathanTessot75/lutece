"""Step 1 - ingest the Mérimée notices of protected buildings located in Paris.

Source: "Immeubles protégés au titre des Monuments Historiques", published by the
French Ministry of Culture on data.gouv.fr under the Licence Ouverte 2.0. It is a
single national CSV ("|"-separated, UTF-8) refreshed weekly.

Run with: uv run python -m lutece_pipeline.ingest_merimee
"""

import argparse
import json
import logging
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pandas as pd
import pyarrow as pa

from lutece_pipeline.geo import is_in_paris
from lutece_pipeline.paths import INTERIM_DIR, RAW_DIR
from lutece_pipeline.tables import from_rows, write_parquet

logger = logging.getLogger(__name__)

# Stable data.gouv.fr link that redirects to the latest version of the national CSV.
SOURCE_URL = (
    "https://www.data.gouv.fr/api/1/datasets/r/3a52af4a-f9da-4dcc-8110-b07774dfb3bc"
)
RAW_CSV = RAW_DIR / "merimee" / "merimee.csv"
OUTPUT_PARQUET = INTERIM_DIR / "merimee.parquet"

PARIS_DEPARTMENT = "75"

SOURCE_COLUMNS = [
    "Reference",
    "Titre_editorial_de_la_notice",
    "Typologie_du_dossier",
    "Denomination_de_l_edifice",
    "Domaine",
    "Adresse_forme_editoriale",
    "Adresse_forme_index",
    "Departement_format_numerique",
    "COG_Insee_lors_de_la_protection",
    "coordonnees_au_format_WGS84",
    "Typologie_de_la_protection",
    "Precision_de_la_protection",
    "Date_et_typologie_de_la_protection",
    "Format_abrege_du_siecle_de_construction",
    "Siecle_de_la_campagne_principale_de_construction",
    "Datation_de_l_edifice",
    "Auteur_de_l_edifice",
    "Historique",
    "Description_de_l_edifice",
    "Statut_juridique_de_l_edifice",
    "Date_de_la_derniere_mise_a_jour",
]

OUTPUT_SCHEMA = pa.schema(
    [
        ("merimee_id", pa.string()),
        ("name", pa.string()),
        ("notice_type", pa.string()),
        ("denominations", pa.list_(pa.string())),
        ("domain", pa.string()),
        ("address", pa.string()),
        ("arrondissement", pa.int8()),
        ("lat", pa.float64()),
        ("lon", pa.float64()),
        ("protection", pa.string()),
        ("protection_raw", pa.string()),
        ("protection_desc", pa.string()),
        ("protection_dates_raw", pa.string()),
        ("construction_century", pa.int8()),
        ("earliest_dated_year", pa.int16()),
        ("period_raw", pa.string()),
        ("authors", pa.list_(pa.string())),
        ("architects", pa.list_(pa.string())),
        ("history_raw", pa.string()),
        ("description_raw", pa.string()),
        ("owner_status", pa.string()),
        ("source_updated_at", pa.date32()),
    ]
)

ARCHITECT_ROLE = re.compile(r"architecte|ma[iî]tre d(?:e l)?['’]\s?(?:oe|œ)uvre")


def download_source(
    destination: Path,
    *,
    refresh: bool = False,
    transport: httpx.BaseTransport | None = None,
) -> bool:
    """Fetch the national CSV unless the local copy is already current.

    The ETag of the last download is kept next to the file, so later runs only
    transfer the 100 MB file when a new version has been published.
    Returns True when a new file was written.
    """
    metadata_path = destination.with_suffix(".meta.json")
    headers = {}
    if not refresh and destination.exists() and metadata_path.exists():
        etag = json.loads(metadata_path.read_text()).get("etag")
        if etag:
            headers["If-None-Match"] = etag

    with (
        httpx.Client(
            transport=transport, follow_redirects=True, timeout=60.0
        ) as client,
        client.stream("GET", SOURCE_URL, headers=headers) as response,
    ):
        if response.status_code == httpx.codes.NOT_MODIFIED:
            logger.info("Mérimée CSV is up to date: %s", destination)
            return False
        response.raise_for_status()

        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_suffix(".part")
        with partial.open("wb") as file:
            for chunk in response.iter_bytes():
                file.write(chunk)
        partial.replace(destination)

        metadata = {
            "source_url": SOURCE_URL,
            "resolved_url": str(response.url),
            "etag": response.headers.get("etag"),
            "last_modified": response.headers.get("last-modified"),
            "downloaded_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "bytes": destination.stat().st_size,
        }
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
    logger.info(
        "Downloaded Mérimée CSV (%d bytes) to %s", metadata["bytes"], destination
    )
    return True


def read_paris_notices(csv_path: Path) -> pd.DataFrame:
    """Load the notices located in Paris as trimmed strings, with None for empty cells."""
    raw = pd.read_csv(
        csv_path, sep="|", usecols=SOURCE_COLUMNS, dtype=str, keep_default_na=False
    )
    raw = raw.apply(lambda column: column.str.strip())
    raw = raw[raw["Departement_format_numerique"] == PARIS_DEPARTMENT]
    return raw.astype(object).where(raw != "", None).reset_index(drop=True)


def split_values(value: str | None) -> list[str]:
    """Split a ";"-separated multi-valued cell into its trimmed, non-empty parts."""
    return [part.strip() for part in (value or "").split(";") if part.strip()]


def parse_notice_type(value: str | None) -> str:
    """Tell protection files apart from "notices de renvoi", which only point elsewhere."""
    label = (value or "").lower()
    if "renvoi" in label:
        return "renvoi"
    return "protection" if "protection" in label else "unknown"


def parse_arrondissement(insee_code: str | None) -> int | None:
    """Return the arrondissement (1-20) encoded in a Paris INSEE code such as "75104"."""
    match = re.fullmatch(r"751(\d{2})", insee_code or "")
    if match is None:
        return None
    number = int(match.group(1))
    return number if 1 <= number <= 20 else None


def parse_coordinates(value: str | None) -> tuple[float, float] | None:
    """Parse a "lat,lon" pair, rejecting points that fall outside Paris."""
    match = re.fullmatch(r"(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)", value or "")
    if match is None:
        return None
    lat, lon = float(match.group(1)), float(match.group(2))
    return (lat, lon) if is_in_paris(lat, lon) else None


def parse_protection_level(value: str | None) -> str | None:
    """Return the strongest protection listed: "classé" outranks "inscrit"."""
    labels = split_values(value)
    if any(label.startswith("classé") for label in labels):
        return "classé"
    if any(label.startswith("inscrit") for label in labels):
        return "inscrit"
    return None


def parse_century(abbreviated: str | None, full_text: str | None) -> int | None:
    """Return the earliest construction century, e.g. 17 for "17e s.;18e s.".

    The abbreviated column is preferred; the free-text one ("1er quart 20e siècle")
    is the fallback for the notices where the abbreviation is missing.
    """
    patterns = (
        (abbreviated, r"(\d{1,2})(?:er|e) s\."),
        (full_text, r"(\d{1,2})(?:er|e) siècle"),
    )
    for text, pattern in patterns:
        centuries = [int(number) for number in re.findall(pattern, text or "")]
        if centuries:
            return min(centuries)
    return None


def parse_year(value: str | None) -> int | None:
    """Return the earliest year mentioned, e.g. 1841 for "1841;1930".

    The source dates building campaigns, so this can be later than the original
    construction: the Louvre is dated 1808 while its first century is the 12th.
    """
    years = [int(number) for number in re.findall(r"\b\d{3,4}\b", value or "")]
    return min(years) if years else None


def parse_date(value: str | None) -> date | None:
    """Parse an ISO date such as "2026-07-24", returning None when it is not one."""
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def extract_architects(authors: Sequence[str]) -> list[str]:
    """Keep the authors credited as architect or "maître de l'œuvre", without the role.

    Names stay as written in the source: surname first, with inconsistent casing.
    """
    architects = []
    for author in authors:
        match = re.fullmatch(r"(.+?)\s*\(([^)]*)\)", author)
        if match and ARCHITECT_ROLE.search(match.group(2)):
            architects.append(match.group(1))
    return architects


def normalize_notice(row: Mapping[str, str | None]) -> dict[str, object]:
    """Map one source row to the columns of OUTPUT_SCHEMA."""
    raw_coordinates = row["coordonnees_au_format_WGS84"]
    coordinates = parse_coordinates(raw_coordinates)
    if raw_coordinates and coordinates is None:
        logger.warning(
            "%s: coordinates %r are malformed or outside Paris, ignored",
            row["Reference"],
            raw_coordinates,
        )
    lat, lon = coordinates or (None, None)
    authors = split_values(row["Auteur_de_l_edifice"])
    return {
        "merimee_id": row["Reference"],
        "name": row["Titre_editorial_de_la_notice"],
        "notice_type": parse_notice_type(row["Typologie_du_dossier"]),
        "denominations": split_values(row["Denomination_de_l_edifice"]),
        "domain": row["Domaine"],
        "address": row["Adresse_forme_editoriale"] or row["Adresse_forme_index"],
        "arrondissement": parse_arrondissement(row["COG_Insee_lors_de_la_protection"]),
        "lat": lat,
        "lon": lon,
        "protection": parse_protection_level(row["Typologie_de_la_protection"]),
        "protection_raw": row["Typologie_de_la_protection"],
        "protection_desc": row["Precision_de_la_protection"],
        "protection_dates_raw": row["Date_et_typologie_de_la_protection"],
        "construction_century": parse_century(
            row["Format_abrege_du_siecle_de_construction"],
            row["Siecle_de_la_campagne_principale_de_construction"],
        ),
        "earliest_dated_year": parse_year(row["Datation_de_l_edifice"]),
        "period_raw": row["Siecle_de_la_campagne_principale_de_construction"],
        "authors": authors,
        "architects": extract_architects(authors),
        "history_raw": row["Historique"],
        "description_raw": row["Description_de_l_edifice"],
        "owner_status": row["Statut_juridique_de_l_edifice"],
        "source_updated_at": parse_date(row["Date_de_la_derniere_mise_a_jour"]),
    }


def normalize(raw: pd.DataFrame) -> pd.DataFrame:
    """Turn the source rows into one typed row per notice, following OUTPUT_SCHEMA."""
    rows = [normalize_notice(row) for row in raw.to_dict("records")]
    notices = from_rows(rows, OUTPUT_SCHEMA)
    duplicated = notices.loc[notices["merimee_id"].duplicated(), "merimee_id"].tolist()
    if duplicated:
        raise ValueError(f"Duplicated Mérimée references: {duplicated}")
    return notices


def summarize(notices: pd.DataFrame) -> dict[str, int]:
    """Count the coverage gaps that the quality report will track."""
    no_period = (
        notices["construction_century"].isna() & notices["earliest_dated_year"].isna()
    )
    return {
        "notices": len(notices),
        "renvoi_notices": int((notices["notice_type"] == "renvoi").sum()),
        "missing_protection": int(notices["protection"].isna().sum()),
        "missing_coordinates": int(notices["lat"].isna().sum()),
        "missing_address": int(notices["address"].isna().sum()),
        "missing_period": int(no_period.sum()),
        "missing_architects": int((notices["architects"].list.len() == 0).sum()),
        "missing_history": int(notices["history_raw"].isna().sum()),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ingest the Mérimée notices of protected buildings located in Paris."
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--refresh",
        action="store_true",
        help="download the CSV again even if the local copy is current",
    )
    source.add_argument(
        "--offline",
        action="store_true",
        help="reuse the local CSV without contacting data.gouv.fr",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if not args.offline:
        download_source(RAW_CSV, refresh=args.refresh)
    notices = normalize(read_paris_notices(RAW_CSV))
    write_parquet(notices, OUTPUT_SCHEMA, OUTPUT_PARQUET)

    logger.info("Wrote %d notices to %s", len(notices), OUTPUT_PARQUET)
    for label, count in summarize(notices).items():
        logger.info("  %-20s %5d", label, count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
