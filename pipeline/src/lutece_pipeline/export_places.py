"""Step 11, server part - the places of the app, for the server to check captures.

The leaderboards count the captures that the server accepts (SPEC §7): it must
know, as the app does, where each place stands, from how far it may be
captured, and how rare it is. This step reads them from the bundle that the
app carries and writes them as a seed of the Supabase database, which
`supabase db push --include-seed` sends to the hosted project. A place that
leaves the bundle stays on the server: captures may refer to it.

Run with: uv run python -m lutece_pipeline.export_places
"""

import argparse
import json
import logging
import sqlite3
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from lutece_pipeline import export_bundle
from lutece_pipeline.paths import PIPELINE_ROOT

logger = logging.getLogger(__name__)

BUNDLE_DB = export_bundle.BUNDLE_DB
BUNDLE_JSON = export_bundle.BUNDLE_JSON
SEED_SQL = PIPELINE_ROOT.parent / "supabase" / "seeds" / "places.sql"

COLUMNS = (
    "id",
    "title",
    "location",
    "footprint",
    "reach_m",
    "arrondissement",
    "rarity_tier",
    "bundle_version",
)

type Record = Mapping[str, Any]


def read_places(path: Path) -> list[dict[str, Any]]:
    """The places of the bundle, by identifier."""
    database = sqlite3.connect(path)
    database.row_factory = sqlite3.Row
    try:
        rows = database.execute(
            "select id, title, lat, lon, footprint, capture_reach_m, arrondissement,"
            " rarity_tier from monuments order by id"
        ).fetchall()
    finally:
        database.close()
    return [dict(row) for row in rows]


def literal(value: object) -> str:
    """A value written in SQL."""
    if value is None:
        return "null"
    if isinstance(value, int | float):
        return repr(value)
    return "'" + str(value).replace("'", "''") + "'"


def place_values(place: Record, version: str) -> str:
    """The values of one place, in the order of COLUMNS."""
    point = f"SRID=4326;POINT({place['lon']!r} {place['lat']!r})"
    return ", ".join(
        [
            literal(place["id"]),
            literal(place["title"]),
            f"extensions.st_geogfromtext({literal(point)})",
            (
                "extensions.st_setsrid(extensions.st_geomfromgeojson("
                f"{literal(place['footprint'])}), 4326)::extensions.geography"
            ),
            literal(place["capture_reach_m"]),
            literal(place["arrondissement"]),
            literal(place["rarity_tier"]),
            literal(version),
        ]
    )


def write_seed(places: Sequence[Record], version: str) -> str:
    """The seed that inserts the places, or updates those already there."""
    updates = ",\n  ".join(
        f"{column} = excluded.{column}" for column in COLUMNS if column != "id"
    )
    values = ",\n".join(f"({place_values(place, version)})" for place in places)
    return (
        "-- The places of the app, for the server to check the captures. Written by\n"
        "-- `uv run python -m lutece_pipeline.export_places` from the bundle\n"
        f"-- {version}: do not edit by hand.\n"
        f"insert into public.places ({', '.join(COLUMNS)}) values\n"
        f"{values}\n"
        f"on conflict (id) do update set\n  {updates};\n"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Write the places of the app as a seed of the server."
    )
    parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    version = json.loads(BUNDLE_JSON.read_text(encoding="utf-8"))["version"]
    places = read_places(BUNDLE_DB)
    SEED_SQL.parent.mkdir(parents=True, exist_ok=True)
    SEED_SQL.write_text(write_seed(places, version), encoding="utf-8")
    logger.info(
        "Wrote %d places of the bundle %s to %s (%d bytes)",
        len(places),
        version,
        SEED_SQL,
        SEED_SQL.stat().st_size,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
