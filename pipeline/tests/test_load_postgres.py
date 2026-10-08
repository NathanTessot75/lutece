import logging
import uuid
from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from shapely.geometry import MultiPolygon, Point, box

from lutece_pipeline import load_postgres as loader

SQUARE = box(2.35, 48.85, 2.351, 48.851)


def notice(merimee_id: str, **changes: object) -> dict[str, object]:
    return {
        "merimee_id": merimee_id,
        "name": "Hôtel de Sully",
        "address": "62 rue Saint-Antoine",
        "arrondissement": 4,
        "protection": "classé",
        "protection_desc": "Façades et toitures",
        "denominations": ["hôtel", "immeuble"],
        "construction_century": 17,
        "architects": ["Jean Androuet du Cerceau"],
        **changes,
    }


def place(merimee_id: str, **changes: object) -> dict[str, object]:
    return {
        "merimee_id": merimee_id,
        "ref_lat": 48.8505,
        "ref_lon": 2.3505,
        "footprint_source": "osm_footprint",
        "footprint_objects": "way/1;way/2",
        "geometry": SQUARE,
        **changes,
    }


def file(merimee_id: str, title: str, **changes: object) -> dict[str, object]:
    return {
        "merimee_id": merimee_id,
        "title": title,
        "page_url": f"https://commons.wikimedia.org/wiki/{title}",
        "thumb_url": f"https://thumb.wikimedia.org/960px-{title}",
        "author": "Anne",
        "licence": "CC BY-SA 4.0",
        "licence_url": "https://creativecommons.org/licenses/by-sa/4.0",
        "rank": 1,
        "selected": True,
        **changes,
    }


def test_identifiers_only_depend_on_the_reference() -> None:
    assert loader.monument_id("PA00086250") == loader.monument_id("PA00086250")
    assert loader.monument_id("PA00086250") != loader.monument_id("PA00086251")
    assert isinstance(loader.monument_id("PA00086250"), uuid.UUID)
    # A value that must never change: the captures of the players will point to it.
    assert (
        str(loader.monument_id("PA00086250")) == "45e3eb96-55b4-5ddc-8caa-b3219e0969e1"
    )
    same_file = loader.image_id("PA1", "File:A.jpg")
    assert same_file == loader.image_id("PA1", "File:A.jpg")
    assert same_file != loader.image_id("PA2", "File:A.jpg")
    assert same_file != loader.image_id("PA1", "File:B.jpg")


def test_geometries_are_written_the_way_postgis_reads_them() -> None:
    assert loader.to_ewkt(Point(2.3505, 48.8505)) == "SRID=4326;POINT (2.3505 48.8505)"
    # Seven decimals, about a centimetre, are enough.
    assert loader.to_ewkt(Point(2.123456789, 48.0)) == "SRID=4326;POINT (2.1234568 48)"


def test_footprint_in_one_piece_becomes_a_multipolygon() -> None:
    assert loader.as_multipolygon(SQUARE) == MultiPolygon([SQUARE])
    pieces = MultiPolygon([SQUARE, box(2.36, 48.85, 2.361, 48.851)])
    assert loader.as_multipolygon(pieces) is pieces
    assert loader.to_ewkt(loader.as_multipolygon(SQUARE)).startswith(
        "SRID=4326;MULTIPOLYGON (((2.351 48.85, "
    )


def test_sources_name_the_databases_a_monument_comes_from() -> None:
    assert loader.list_sources("PA1", "Q42", "way/7") == [
        {
            "label": "Base Mérimée",
            "url": "https://pop.culture.gouv.fr/notice/merimee/PA1",
            "licence": "Licence Ouverte 2.0",
        },
        {
            "label": "Wikidata",
            "url": "https://www.wikidata.org/wiki/Q42",
            "licence": "CC0",
        },
        {
            "label": "OpenStreetMap",
            "url": "https://www.openstreetmap.org/way/7",
            "licence": "ODbL",
        },
    ]
    assert [source["label"] for source in loader.list_sources("PA1", None, None)] == [
        "Base Mérimée"
    ]


def test_monument_row_gathers_what_the_steps_know() -> None:
    rows = loader.build_monuments(
        [notice("PA1")],
        [{"merimee_id": "PA1", "wikidata_qid": "Q42"}],
        [{"qid": "Q42", "architects": ["Somebody else"]}],
        [place("PA1")],
        [{"merimee_id": "PA1", "visibility": "visible"}],
        3,
    )
    assert rows == [
        {
            "id": loader.monument_id("PA1"),
            "merimee_id": "PA1",
            "wikidata_qid": "Q42",
            # The first object of the footprint is the main one.
            "osm_id": "way/1",
            "name": "Hôtel de Sully",
            "address": "62 rue Saint-Antoine",
            "arrondissement": 4,
            "location": "SRID=4326;POINT (2.3505 48.8505)",
            "footprint": loader.to_ewkt(MultiPolygon([SQUARE])),
            "footprint_source": "osm_footprint",
            "category": "hôtel",
            "period_start": 17,
            "architects": ["Jean Androuet du Cerceau"],
            "protection": "classé",
            "protection_desc": "Façades et toitures",
            "visibility": "visible",
            "sources": loader.list_sources("PA1", "Q42", "way/1"),
            "data_version": 3,
        }
    ]


def test_missing_pieces_of_a_monument_stay_empty() -> None:
    (row,) = loader.build_monuments(
        [notice("PA1", architects=None, denominations=None, address=None)],
        [{"merimee_id": "PA1", "wikidata_qid": "Q42"}],
        [{"qid": "Q42", "architects": ["Louis Le Vau"]}],
        [place("PA1", footprint_source="buffer", footprint_objects=None)],
        [],
        1,
    )
    assert row["osm_id"] is None
    assert row["category"] is None
    assert row["address"] is None
    # Wikidata gives the architect when the notice has none.
    assert row["architects"] == ["Louis Le Vau"]
    # A monument that the visibility step has not seen is undecided.
    assert row["visibility"] == "inconnu"
    assert [source["label"] for source in row["sources"]] == [
        "Base Mérimée",
        "Wikidata",
    ]


def test_only_located_monuments_are_loaded(caplog: pytest.LogCaptureFixture) -> None:
    notices = [notice("PA1"), notice("PA2", protection=None), notice("PA3")]
    with caplog.at_level(logging.WARNING):
        rows = loader.build_monuments(notices, [], [], [place("PA1")], [], 1)
    assert [row["merimee_id"] for row in rows] == ["PA1"]
    assert rows[0]["wikidata_qid"] is None
    assert "PA3 has no location and is not loaded" in caplog.text
    assert "PA2" not in caplog.text


def test_images_are_the_photos_selected_for_the_loaded_monuments() -> None:
    files = [
        file("PA1", "File:A.jpg", rank=2),
        file("PA1", "File:B.jpg", selected=False, rank=None),
        file("PA9", "File:C.jpg"),
    ]
    assert loader.build_images(files, [{"merimee_id": "PA1"}]) == [
        {
            "id": loader.image_id("PA1", "File:A.jpg"),
            "monument_id": loader.monument_id("PA1"),
            "source_url": "https://commons.wikimedia.org/wiki/File:A.jpg",
            "thumb_url": "https://thumb.wikimedia.org/960px-File:A.jpg",
            "author": "Anne",
            "licence": "CC BY-SA 4.0",
            "licence_url": "https://creativecommons.org/licenses/by-sa/4.0",
            "rank": 2,
        }
    ]


def test_password_is_hidden_from_the_log() -> None:
    assert (
        loader.without_password(
            "postgresql://postgres:s3cret@db.example.org:5432/postgres"
        )
        == "postgresql://postgres:***@db.example.org:5432/postgres"
    )
    assert "postgres:postgres@" not in loader.without_password(
        loader.LOCAL_DATABASE_URL
    )
    assert loader.without_password("postgresql://localhost/lutece") == (
        "postgresql://localhost/lutece"
    )


@pytest.fixture
def connection() -> Iterator[psycopg.Connection[Any]]:
    """A transaction on the local database, undone after the test.

    The test is skipped when the local Supabase stack is not running.
    """
    try:
        opened = psycopg.connect(loader.LOCAL_DATABASE_URL, connect_timeout=2)
    except psycopg.OperationalError:
        pytest.skip("the local database is not running")
    try:
        if opened.execute("select to_regclass('public.monuments')").fetchone() == (
            None,
        ):
            pytest.skip("the migrations have not been applied")
        yield opened
    finally:
        opened.rollback()
        opened.close()


def test_load_can_be_run_again(connection: psycopg.Connection[Any]) -> None:
    def one(query: str, *values: object) -> tuple[Any, ...]:
        row = connection.execute(query, values).fetchone()
        assert row is not None
        return row

    notices = [notice("PATEST001"), notice("PATEST002", name="Maison")]
    places = [place("PATEST001"), place("PATEST002", footprint_source="buffer")]
    seen = [{"merimee_id": "PATEST001", "visibility": "visible"}]
    monuments = loader.build_monuments(notices, [], [], places, seen, 1)
    files = [file("PATEST001", "File:A.jpg"), file("PATEST001", "File:B.jpg", rank=2)]
    counts = loader.load(connection, monuments, loader.build_images(files, monuments))
    assert counts["monuments_loaded"] == 2
    assert counts["images_loaded"] == 2

    first = loader.monument_id("PATEST001")
    assert one(
        "select name, visibility, category, architects, extensions.st_astext(location),"
        " extensions.geometrytype(footprint::extensions.geometry),"
        " sources->0->>'label' from monuments where id = %s",
        first,
    ) == (
        "Hôtel de Sully",
        "visible",
        "hôtel",
        ["Jean Androuet du Cerceau"],
        "POINT(2.3505 48.8505)",
        "MULTIPOLYGON",
        "Base Mérimée",
    )
    assert one(
        "select count(*) from reference_images where monument_id = %s", first
    ) == (2,)

    # Later steps and players add to the base: a second load must keep it.
    kept = loader.image_id("PATEST001", "File:A.jpg")
    connection.execute(
        "update reference_images set embedding ="
        " array_fill(0.5, array[384])::extensions.vector where id = %s",
        (kept,),
    )
    connection.execute(
        "update monuments set story_fr = 'Une histoire' where id = %s", (first,)
    )
    contributed = uuid.uuid4()
    connection.execute(
        "insert into reference_images (id, monument_id, source_url, is_user_contributed)"
        " values (%s, %s, 'https://example.org/photo', true)",
        (contributed, first),
    )

    renamed = loader.build_monuments(
        [notice("PATEST001", name="Hôtel de Béthune-Sully")],
        [],
        [],
        places[:1],
        seen,
        2,
    )
    again = loader.load(
        connection,
        renamed,
        loader.build_images([file("PATEST001", "File:A.jpg")], renamed),
    )
    assert one(
        "select id, name, story_fr, data_version from monuments where merimee_id ="
        " 'PATEST001'"
    ) == (first, "Hôtel de Béthune-Sully", "Une histoire", 2)
    # The monument that left the pipeline is counted, not deleted.
    assert again["monuments_no_longer_in_the_pipeline"] >= 1
    assert one("select count(*) from monuments where merimee_id = 'PATEST002'") == (1,)
    # The photo that is no longer selected is gone, the others stay as they were.
    assert again["images_removed"] >= 1
    remaining = connection.execute(
        "select id, embedding is not null, is_user_contributed from reference_images"
        " where monument_id = %s order by is_user_contributed",
        (first,),
    ).fetchall()
    assert remaining == [(kept, True, False), (contributed, False, True)]
