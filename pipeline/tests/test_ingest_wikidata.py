import json
import re
import shutil
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pandas as pd
import pyarrow.parquet as pq
import pytest

from lutece_pipeline import ingest_merimee as merimee
from lutece_pipeline import ingest_wikidata as wikidata
from lutece_pipeline.tables import write_parquet

FIXTURES = Path(__file__).parent / "fixtures"
# Real answers of the Wikidata Query Service for the 11 Paris notices of the
# Mérimée fixture, recorded on 2026-10-07: 12 links and 12 items.
SNAPSHOT_PATH = FIXTURES / "wikidata_snapshot.json"
SNAPSHOT = json.loads(SNAPSHOT_PATH.read_text())


def sparql_response(rows: list[dict[str, str]]) -> httpx.Response:
    bindings = [
        {name: {"type": "literal", "value": value} for name, value in row.items()}
        for row in rows
    ]
    return httpx.Response(200, json={"results": {"bindings": bindings}})


def sent_query(request: httpx.Request) -> str:
    return parse_qs(request.content.decode())["query"][0]


@pytest.fixture(scope="module")
def items() -> pd.DataFrame:
    return wikidata.build_items(SNAPSHOT["items"]).set_index("qid")


@pytest.fixture(scope="module")
def links() -> pd.DataFrame:
    return wikidata.build_links(SNAPSHOT["links"])


def test_qid_from_uri() -> None:
    assert wikidata.qid_from_uri("http://www.wikidata.org/entity/Q243") == "Q243"


def test_split_concat_sorts_and_deduplicates() -> None:
    assert wikidata.split_concat("b|a|a|") == ["a", "b"]
    assert wikidata.split_concat("") == []
    assert wikidata.split_concat(None) == []


def test_parse_point_reads_longitude_first() -> None:
    assert wikidata.parse_point("Point(2.294479 48.858296)") == (48.858296, 2.294479)
    assert wikidata.parse_point("48.858296,2.294479") is None


def test_pick_paris_point_skips_points_outside_paris() -> None:
    assert wikidata.pick_paris_point(["Point(0 0)", "Point(2.33 48.86)"]) == (
        48.86,
        2.33,
    )
    assert wikidata.pick_paris_point(["Point(0 0)", "not a point"]) is None
    assert wikidata.pick_paris_point([]) is None


@pytest.mark.parametrize(
    ("timestamp", "expected"),
    [
        ("1889-03-31T00:00:00Z", 1889),
        ("-1289-01-01T00:00:00Z", -1289),  # the Luxor obelisk
        ("unknown", None),
    ],
)
def test_parse_year(timestamp: str, expected: int | None) -> None:
    assert wikidata.parse_year(timestamp) == expected


def test_commons_file_name_is_decoded() -> None:
    url = "http://commons.wikimedia.org/wiki/Special:FilePath/Tour%20Eiffel.jpg"
    assert wikidata.commons_file_name(url) == "Tour Eiffel.jpg"


def test_build_item_picks_values_deterministically() -> None:
    item = wikidata.build_item(
        {
            "item": "http://www.wikidata.org/entity/Q1",
            "coords": "Point(0 0)|Point(2.33 48.86)",
            "commonsCats": "Zeta|Alpha",
            "images": "http://commons.wikimedia.org/wiki/Special:FilePath/b.jpg"
            "|http://commons.wikimedia.org/wiki/Special:FilePath/a.jpg",
            "inceptions": "1900-01-01T00:00:00Z|1850-01-01T00:00:00Z",
            "architects": "",
            "types": "église",
        }
    )
    assert item == {
        "qid": "Q1",
        "label_fr": None,
        "lat": 48.86,
        "lon": 2.33,
        "commons_category": "Alpha",
        "frwiki_title": None,
        "frwiki_url": None,
        "image_file": "a.jpg",
        "inception_year": 1850,
        "architects": [],
        "instance_of": ["église"],
        "sitelinks": None,
    }


def test_items_are_typed_and_sorted_by_identifier(items: pd.DataFrame) -> None:
    assert list(items.reset_index().columns) == wikidata.ITEMS_SCHEMA.names
    assert items.index[0] == "Q860172"  # numeric order, not alphabetical
    assert items.index[-1] == "Q109626718"
    assert len(items) == 12


def test_fully_described_item(items: pd.DataFrame) -> None:
    passage = items.loc["Q2055787"]
    assert passage["label_fr"] == "passage Choiseul"
    assert passage["lat"] == pytest.approx(48.86902)
    assert passage["lon"] == pytest.approx(2.335753)
    assert passage["commons_category"] == "Passage Choiseul (Paris)"
    assert passage["frwiki_title"] == "Passage Choiseul"
    assert passage["frwiki_url"] == "https://fr.wikipedia.org/wiki/Passage_Choiseul"
    assert passage["image_file"] == "Passage Choiseul.JPG"
    assert passage["inception_year"] == 1827
    assert list(passage["architects"]) == ["Antoine Tavernier", "François Mazois"]
    assert list(passage["instance_of"]) == ["passage", "passages couverts de Paris"]
    assert passage["sitelinks"] == 7


def test_missing_properties_stay_empty(items: pd.DataFrame) -> None:
    assert pd.isna(items.loc["Q22920960", "frwiki_title"])  # no French article
    assert pd.isna(items.loc["Q15950844", "commons_category"])
    assert pd.isna(items.loc["Q15950844", "image_file"])
    assert pd.isna(items.loc["Q860172", "inception_year"])
    assert list(items.loc["Q860172", "architects"]) == []


def test_duplicated_item_rows_are_rejected() -> None:
    rows = [SNAPSHOT["items"][0], SNAPSHOT["items"][0]]
    with pytest.raises(ValueError, match="Several rows for the same Wikidata item"):
        wikidata.build_items(rows)


def test_links_are_distinct_pairs(links: pd.DataFrame) -> None:
    assert list(links.columns) == ["merimee_id", "qid"]
    assert len(links) == 12
    assert len(wikidata.build_links(SNAPSHOT["links"] * 2)) == 12
    # One notice covers two covered passages, each with its own item.
    choiseul = links.loc[links["merimee_id"] == "PA00086088", "qid"].tolist()
    assert choiseul == ["Q2055787", "Q3368000"]


def test_summary_counts_matches_and_gaps(
    links: pd.DataFrame, items: pd.DataFrame
) -> None:
    merimee_ids = sorted(set(links["merimee_id"])) + ["PA99999999"]
    assert wikidata.summarize(merimee_ids, links, items.reset_index()) == {
        "notices": 12,
        "notices_without_item": 1,
        "notices_with_several_items": 1,
        "items": 12,
        "items_with_several_notices": 0,
        "missing_coordinates": 0,
        "missing_commons_category": 2,
        "missing_frwiki_article": 1,
        "missing_image": 1,
        "missing_architects": 9,
        "missing_inception": 5,
    }


def test_client_identifies_itself() -> None:
    with wikidata.make_client() as client:
        assert "tessotnathan75@gmail.com" in client.headers["User-Agent"]
        assert client.headers["Accept"] == "application/sparql-results+json"


def test_query_is_retried_after_a_transient_error() -> None:
    responses = iter(
        [
            httpx.Response(502),
            httpx.Response(429, headers={"retry-after": "7"}),
            sparql_response([{"item": "http://www.wikidata.org/entity/Q243"}]),
        ]
    )
    pauses: list[float] = []
    transport = httpx.MockTransport(lambda request: next(responses))

    with wikidata.make_client(transport) as client:
        rows = wikidata.run_query(client, "SELECT 1", pause=pauses.append)

    assert rows == [{"item": "http://www.wikidata.org/entity/Q243"}]
    assert pauses == [2.0, 7.0]


def test_links_are_fetched_in_batches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(wikidata, "LINK_BATCH_SIZE", 2)
    queries: list[str] = []
    pauses: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        query = sent_query(request)
        queries.append(query)
        identifiers = re.findall(r'"(PA\d+)"', query)
        return sparql_response(
            [
                {
                    "item": f"http://www.wikidata.org/entity/Q{identifier[2:]}",
                    "merimee": identifier,
                }
                for identifier in identifiers
            ]
        )

    merimee_ids = ["PA1", "PA2", "PA3", "PA4", "PA5"]
    with wikidata.make_client(httpx.MockTransport(handler)) as client:
        rows = wikidata.fetch_links(client, merimee_ids, pause=pauses.append)

    assert len(queries) == 3
    assert [row["merimee"] for row in rows] == merimee_ids
    assert pauses == [wikidata.BATCH_PAUSE_SECONDS] * 2


def test_items_query_only_accepts_item_identifiers() -> None:
    with (
        wikidata.make_client(
            httpx.MockTransport(lambda request: sparql_response([]))
        ) as client,
        pytest.raises(ValueError, match="Not Wikidata item identifiers"),
    ):
        wikidata.fetch_items(client, ["Q243", "Q1 } DROP"])


def test_offline_run_writes_both_tables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    notices = merimee.normalize(
        merimee.read_paris_notices(FIXTURES / "merimee_sample.csv")
    )
    merimee_parquet = tmp_path / "merimee.parquet"
    write_parquet(notices, merimee.OUTPUT_SCHEMA, merimee_parquet)
    snapshot = tmp_path / "raw" / "snapshot.json"
    snapshot.parent.mkdir()
    shutil.copy(SNAPSHOT_PATH, snapshot)
    monkeypatch.setattr(wikidata, "MERIMEE_PARQUET", merimee_parquet)
    monkeypatch.setattr(wikidata, "RAW_SNAPSHOT", snapshot)
    monkeypatch.setattr(wikidata, "ITEMS_PARQUET", tmp_path / "items.parquet")
    monkeypatch.setattr(wikidata, "LINKS_PARQUET", tmp_path / "links.parquet")

    assert wikidata.main(["--offline"]) == 0

    items_schema = pq.read_schema(tmp_path / "items.parquet")
    assert items_schema.equals(wikidata.ITEMS_SCHEMA, check_metadata=False)
    # Plain pandas reads, without Arrow dtypes, must work for the next steps.
    assert len(pd.read_parquet(tmp_path / "items.parquet")) == 12
    links = pd.read_parquet(tmp_path / "links.parquet")
    assert set(links["merimee_id"]) == set(notices["merimee_id"])
