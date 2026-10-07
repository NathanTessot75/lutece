import json
import logging
from datetime import date
from pathlib import Path

import httpx
import pandas as pd
import pyarrow.parquet as pq
import pytest

from lutece_pipeline import ingest_merimee as merimee

# 13 real notices: 11 in Paris, 1 in Aix-en-Provence (13), 1 in Saint-Pierre (975).
FIXTURE = Path(__file__).parent / "fixtures" / "merimee_sample.csv"


@pytest.fixture(scope="module")
def notices() -> pd.DataFrame:
    raw = merimee.read_paris_notices(FIXTURE)
    return merimee.normalize(raw).set_index("merimee_id")


@pytest.mark.parametrize(
    ("insee_code", "expected"),
    [
        ("75101", 1),
        ("75120", 20),
        ("75100", None),
        ("75121", None),
        ("93048", None),
        (None, None),
    ],
)
def test_parse_arrondissement(insee_code: str | None, expected: int | None) -> None:
    assert merimee.parse_arrondissement(insee_code) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("48.8634011732789,2.35036014545591", (48.8634011732789, 2.35036014545591)),
        ("48.86, 2.35", (48.86, 2.35)),
        ("48.00000000000001,2", None),  # real bogus point found in the source
        ("2.35,48.86", None),  # swapped lon/lat falls outside Paris
        ("48.86", None),
        (None, None),
    ],
)
def test_parse_coordinates(
    value: str | None, expected: tuple[float, float] | None
) -> None:
    assert merimee.parse_coordinates(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("classé MH", "classé"),
        ("inscrit MH partiellement", "inscrit"),
        (
            "inscrit MH partiellement;classé MH partiellement;protection partielle",
            "classé",
        ),
        ("protection totale", None),
        (None, None),
    ],
)
def test_parse_protection_level(value: str | None, expected: str | None) -> None:
    assert merimee.parse_protection_level(value) == expected


@pytest.mark.parametrize(
    ("abbreviated", "full_text", "expected"),
    [
        ("17e s.", "2e moitié 17e siècle", 17),
        ("19e s.;20e s.", "limite 19e siècle 20e siècle", 19),
        ("limite 19e s. 20e s.", None, 19),
        ("1er s.", None, 1),
        (None, "1er quart 20e siècle", 20),
        ("Moyen Age", "Moyen Age", None),
        (None, None, None),
    ],
)
def test_parse_century(
    abbreviated: str | None, full_text: str | None, expected: int | None
) -> None:
    assert merimee.parse_century(abbreviated, full_text) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [("1864", 1864), ("1841;1930", 1841), ("1895-1896;1908-1910", 1895), (None, None)],
)
def test_parse_year(value: str | None, expected: int | None) -> None:
    assert merimee.parse_year(value) == expected


def test_split_values() -> None:
    assert merimee.split_values("immeuble; hôtel ;") == ["immeuble", "hôtel"]
    assert merimee.split_values(None) == []


def test_extract_architects_keeps_only_architect_roles() -> None:
    authors = [
        "Perret Auguste (architecte)",
        "GUIMARD Hector (maître de l'oeuvre)",
        "Lopez Raymond (architecte, urbaniste)",
        "Sandier Alexandre (céramiste)",
        "Dupont Jean (maître d'ouvrage)",
        "fonderie Thiébaut",
    ]
    assert merimee.extract_architects(authors) == [
        "Perret Auguste",
        "GUIMARD Hector",
        "Lopez Raymond",
    ]


def test_parse_notice_type() -> None:
    assert merimee.parse_notice_type("Dossier de protection") == "protection"
    assert merimee.parse_notice_type("Notice de renvoi") == "renvoi"
    assert merimee.parse_notice_type(None) == "unknown"


def test_only_paris_notices_are_kept(notices: pd.DataFrame) -> None:
    assert len(notices) == 11
    assert "PA00081001" not in notices.index  # Aix-en-Provence
    assert "PA97500009" not in notices.index  # department 975 must not match "75"


def test_normalized_columns_follow_the_schema(notices: pd.DataFrame) -> None:
    assert list(notices.reset_index().columns) == merimee.OUTPUT_SCHEMA.names


def test_fully_described_notice(notices: pd.DataFrame) -> None:
    passage = notices.loc["PA00086088"]
    assert passage["name"] == "Passage Choiseul et passage Sainte-Anne"
    assert passage["notice_type"] == "protection"
    assert list(passage["denominations"]) == ["passage couvert"]
    assert passage["arrondissement"] == 2
    assert passage["lat"] == pytest.approx(48.867979, abs=1e-6)
    assert passage["lon"] == pytest.approx(2.336228, abs=1e-6)
    assert passage["protection"] == "inscrit"
    assert passage["protection_raw"] == "inscrit MH partiellement"
    assert passage["construction_century"] == 19
    assert passage["earliest_dated_year"] == 1825
    assert list(passage["architects"]) == ["MAZOIS François", "TAVERNIER Antoine"]
    assert passage["source_updated_at"] == date(2026, 7, 24)


def test_mixed_protection_resolves_to_the_strongest(notices: pd.DataFrame) -> None:
    assert notices.loc["PA00085809", "protection"] == "classé"


def test_authors_without_architect_role_are_not_architects(
    notices: pd.DataFrame,
) -> None:
    cafe = notices.loc["PA00085786"]
    assert list(cafe["authors"]) == ["Sandier Alexandre (céramiste)"]
    assert list(cafe["architects"]) == []


def test_century_falls_back_to_the_free_text_column(notices: pd.DataFrame) -> None:
    assert notices.loc["PA00086620", "construction_century"] == 18


def test_unparseable_period_stays_empty(notices: pd.DataFrame) -> None:
    assert pd.isna(notices.loc["PA00085795", "construction_century"])  # "Moyen Age"


def test_renvoi_notice_has_no_protection(notices: pd.DataFrame) -> None:
    canal = notices.loc["PA00125441"]
    assert canal["notice_type"] == "renvoi"
    assert pd.isna(canal["protection"])


def test_missing_coordinates_stay_empty(notices: pd.DataFrame) -> None:
    assert pd.isna(notices.loc["PA00086579", "lat"])
    assert pd.isna(notices.loc["PA00086579", "lon"])


def test_bogus_coordinates_are_dropped_with_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger=merimee.logger.name):
        temple = merimee.normalize(merimee.read_paris_notices(FIXTURE)).set_index(
            "merimee_id"
        )
    assert pd.isna(temple.loc["PA75110005", "lat"])
    assert "PA75110005" in caplog.text


def test_summary_counts_the_gaps(notices: pd.DataFrame) -> None:
    assert merimee.summarize(notices.reset_index()) == {
        "notices": 11,
        "renvoi_notices": 1,
        "missing_protection": 2,
        "missing_coordinates": 2,
        "missing_address": 1,
        "missing_period": 2,
        "missing_architects": 8,
        "missing_history": 6,
    }


def test_duplicated_references_are_rejected() -> None:
    raw = merimee.read_paris_notices(FIXTURE)
    with pytest.raises(ValueError, match="Duplicated Mérimée references"):
        merimee.normalize(pd.concat([raw, raw.head(1)]))


def test_download_only_transfers_new_versions(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.headers.get("if-none-match") == '"v1"':
            return httpx.Response(304)
        return httpx.Response(
            200, content=b"Reference|Domaine\n", headers={"etag": '"v1"'}
        )

    transport = httpx.MockTransport(handler)
    destination = tmp_path / "merimee" / "merimee.csv"

    assert merimee.download_source(destination, transport=transport) is True
    assert destination.read_bytes() == b"Reference|Domaine\n"
    metadata = json.loads(destination.with_suffix(".meta.json").read_text())
    assert metadata["etag"] == '"v1"'
    assert metadata["bytes"] == 18

    assert merimee.download_source(destination, transport=transport) is False
    assert requests[-1].headers["if-none-match"] == '"v1"'

    assert (
        merimee.download_source(destination, refresh=True, transport=transport) is True
    )
    assert "if-none-match" not in requests[-1].headers


def test_offline_run_writes_the_parquet_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "interim" / "merimee.parquet"
    monkeypatch.setattr(merimee, "RAW_CSV", FIXTURE)
    monkeypatch.setattr(merimee, "OUTPUT_PARQUET", output)

    assert merimee.main(["--offline"]) == 0

    assert pq.read_schema(output).equals(merimee.OUTPUT_SCHEMA, check_metadata=False)
    assert pq.read_metadata(output).num_rows == 11
