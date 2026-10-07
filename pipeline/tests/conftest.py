import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest

from lutece_pipeline import ingest_merimee as merimee
from lutece_pipeline import ingest_osm as osm
from lutece_pipeline import ingest_wikidata as wikidata
from lutece_pipeline import resolve_entities as resolve
from lutece_pipeline.tables import from_rows, to_records, write_parquet

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def interim_tables(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The outputs of the three ingestion steps, built from the real fixture answers."""
    folder = tmp_path_factory.mktemp("interim")
    notices = merimee.normalize(
        merimee.read_paris_notices(FIXTURES / "merimee_sample.csv")
    )
    write_parquet(notices, merimee.OUTPUT_SCHEMA, folder / "merimee.parquet")
    snapshot = json.loads((FIXTURES / "wikidata_snapshot.json").read_text())
    wikidata_links = wikidata.build_links(snapshot["links"])
    items = wikidata.build_items(snapshot["items"])
    write_parquet(items, wikidata.ITEMS_SCHEMA, folder / "wikidata_items.parquet")
    write_parquet(
        wikidata_links, wikidata.LINKS_SCHEMA, folder / "wikidata_links.parquet"
    )
    elements = json.loads((FIXTURES / "osm_snapshot.json").read_text())["elements"]
    osm_links = osm.build_links(
        elements, set(notices["merimee_id"]), osm.notices_by_item(wikidata_links)
    )
    write_parquet(osm_links, osm.LINKS_SCHEMA, folder / "osm_links.parquet")
    osm.build_objects(elements).to_parquet(folder / "osm_objects.parquet", index=False)
    return folder


@pytest.fixture(scope="session")
def resolved_tables(interim_tables: Path) -> Path:
    """The same folder with the reconciliation outputs, the temple links being accepted."""
    notices = to_records(pd.read_parquet(interim_tables / "merimee.parquet"))
    items = to_records(pd.read_parquet(interim_tables / "wikidata_items.parquet"))
    wikidata_links = to_records(
        pd.read_parquet(interim_tables / "wikidata_links.parquet")
    )
    objects = gpd.read_parquet(interim_tables / "osm_objects.parquet")
    osm_links = to_records(pd.read_parquet(interim_tables / "osm_links.parquet"))
    pairs = resolve.measure_wikidata_pairs(notices, items, wikidata_links)
    pairs += resolve.measure_osm_pairs(notices, objects, osm_links)
    decisions = {
        ("PA75110005", "Q3517708"): "accept",
        ("PA75110005", "way/63648393"): "accept",
    }
    resolve.apply_decisions(pairs, decisions)
    resolve.choose_primaries(pairs)
    links = from_rows(pairs, resolve.LINKS_SCHEMA)
    write_parquet(links, resolve.LINKS_SCHEMA, interim_tables / "entity_links.parquet")
    entities = resolve.build_entities(notices, pairs)
    write_parquet(
        entities, resolve.ENTITIES_SCHEMA, interim_tables / "entities.parquet"
    )
    return interim_tables
