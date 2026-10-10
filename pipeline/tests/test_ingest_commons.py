import json
import logging
from pathlib import Path
from urllib.parse import parse_qsl

import httpx
import pandas as pd
import pytest

from lutece_pipeline import ingest_commons as commons
from lutece_pipeline import web

FIXTURES = Path(__file__).parent / "fixtures"


def form(request: httpx.Request) -> dict[str, str]:
    return dict(parse_qsl(request.content.decode()))


def stub(title: str) -> dict[str, object]:
    """A file page as Commons lists it before describing it."""
    return {"pageid": 1, "ns": 6, "title": title, "imagerepository": "local"}


def described(
    title: str,
    *,
    user: str = "Chabe01",
    width: int = 4000,
    height: int = 3000,
    mime: str = "image/jpeg",
    **metadata: str,
) -> dict[str, object]:
    """A file page as Commons describes it."""
    name = title.removeprefix("File:").replace(" ", "_")
    values = {"LicenseShortName": "CC BY-SA 4.0", "License": "cc-by-sa-4.0", **metadata}
    return {
        **stub(title),
        "imageinfo": [
            {
                "user": user,
                "size": 1_000_000,
                "width": width,
                "height": height,
                "thumburl": f"https://thumb.wikimedia.org/thumb/a/ab/{name}/960px-{name}",
                "url": f"https://upload.wikimedia.org/wikipedia/commons/a/ab/{name}",
                "descriptionurl": f"https://commons.wikimedia.org/wiki/File:{name}",
                "mime": mime,
                "extmetadata": {
                    key: {"value": value, "source": "commons-desc-page"}
                    for key, value in values.items()
                },
            }
        ],
    }


def answer(pages: list[dict[str, object]], **extra: object) -> httpx.Response:
    return httpx.Response(200, json={"query": {"pages": pages}, **extra})


def client_answering(
    answers: list[httpx.Response], requests: list[dict[str, str]] | None = None
) -> httpx.Client:
    """A client whose service gives the prepared answers one after the other."""
    remaining = iter(answers)

    def handler(request: httpx.Request) -> httpx.Response:
        if requests is not None:
            requests.append(form(request))
        return next(remaining)

    return web.make_client(transport=httpx.MockTransport(handler))


def no_pause(seconds: float) -> None:
    pass


def test_query_carries_the_common_parameters() -> None:
    requests: list[dict[str, str]] = []
    with client_answering([answer([])], requests) as client:
        commons.call_api(client, {"prop": "categoryinfo"}, pause=no_pause)
    assert requests == [
        {
            "action": "query",
            "format": "json",
            "formatversion": "2",
            "maxlag": "5",
            "prop": "categoryinfo",
        }
    ]


def test_lagging_server_is_asked_again_after_the_wait_it_states() -> None:
    lagging = httpx.Response(
        200,
        headers={"retry-after": "3"},
        json={"error": {"code": "maxlag", "info": "Waiting for a database server"}},
    )
    pauses: list[float] = []
    with client_answering([lagging, answer([stub("File:A.jpg")])]) as client:
        result = commons.call_api(client, {}, pause=pauses.append)
    assert result["query"]["pages"][0]["title"] == "File:A.jpg"
    assert pauses == [3.0]


def test_lag_that_lasts_stops_the_step() -> None:
    lagging = httpx.Response(200, json={"error": {"code": "maxlag"}})
    pauses: list[float] = []
    with (
        client_answering([lagging] * commons.MAXLAG_ATTEMPTS) as client,
        pytest.raises(RuntimeError, match="still lagging"),
    ):
        commons.call_api(client, {}, pause=pauses.append)
    assert pauses == [commons.MAXLAG_DELAY_SECONDS] * commons.MAXLAG_ATTEMPTS


def test_refused_query_stops_the_step() -> None:
    refused = httpx.Response(200, json={"error": {"code": "badvalue", "info": "no"}})
    with (
        client_answering([refused]) as client,
        pytest.raises(RuntimeError, match="Commons refused the query.*badvalue"),
    ):
        commons.call_api(client, {}, pause=no_pause)


def test_query_asks_for_the_rest_while_there_is_some() -> None:
    requests: list[dict[str, str]] = []
    answers = [
        answer(
            [stub("File:A.jpg")], **{"continue": {"cmcontinue": "x", "continue": "-||"}}
        ),
        answer(
            [stub("File:B.jpg")], **{"continue": {"cmcontinue": "y", "continue": "-||"}}
        ),
        answer([stub("File:C.jpg")], batchcomplete=True),
    ]
    pauses: list[float] = []
    with client_answering(answers, requests) as client:
        got = list(
            commons.query_all(
                client, {"list": "x"}, follow="cmcontinue", pause=pauses.append
            )
        )
    assert len(got) == 3
    assert "cmcontinue" not in requests[0]
    assert [request["cmcontinue"] for request in requests[1:]] == ["x", "y"]
    assert pauses == [commons.REQUEST_PAUSE_SECONDS] * 2


def test_other_continuations_are_not_followed() -> None:
    # A file uploaded twice: Commons offers to go on with its older version.
    # Following it replaced the current description by the archived one.
    requests: list[dict[str, str]] = []
    answers = [
        answer(
            [described("File:A.jpg", user="Current")],
            **{"continue": {"iistart": "2012-09-28T23:17:00Z", "continue": "||"}},
        ),
        answer([described("File:A.jpg", user="Archived")]),
    ]
    with client_answering(answers, requests) as client:
        records = commons.fetch_category_files(client, "Pont Neuf", pause=no_pause)
    assert len(requests) == 1
    assert [record["user"] for record in records] == ["Current"]


def test_continuation_that_does_not_move_stops_the_step() -> None:
    stuck = {"continue": {"iicontinue": "A.jpg|2020", "continue": "||"}}
    answers = [answer([stub("File:A.jpg")], **stuck) for _ in range(3)]
    with (
        client_answering(answers) as client,
        pytest.raises(RuntimeError, match="repeats the same continuation"),
    ):
        commons.fetch_category_files(client, "Pont Neuf", pause=no_pause)


def test_category_listing_gathers_descriptions_spread_over_answers() -> None:
    # Commons lists every file at once but describes 50 per answer: cut down to
    # three files and two answers, in the shape of real answers.
    requests: list[dict[str, str]] = []
    answers = [
        answer(
            [described("File:B.jpg"), stub("File:C.jpg"), described("File:A.jpg")],
            **{"continue": {"iicontinue": "C.jpg|2020", "continue": "||"}},
        ),
        answer(
            [stub("File:B.jpg"), described("File:C.jpg"), stub("File:A.jpg")],
            # More than 500 files: the rest of the category is not asked for.
            **{"continue": {"gcmcontinue": "file|D|1", "continue": "gcmcontinue||"}},
        ),
    ]
    with client_answering(answers, requests) as client:
        records = commons.fetch_category_files(client, "Pont Neuf", pause=no_pause)
    assert [record["title"] for record in records] == [
        "File:A.jpg",
        "File:B.jpg",
        "File:C.jpg",
    ]
    assert len(requests) == 2
    assert requests[0]["gcmtitle"] == "Category:Pont Neuf"
    assert requests[0]["gcmtype"] == "file"
    assert requests[0]["iiurlwidth"] == "960"
    assert requests[1]["iicontinue"] == "C.jpg|2020"


def test_file_answer_is_cut_down_to_what_the_step_reads() -> None:
    page = described(
        "File:Pont Neuf 1.jpg",
        user="Mbzt",
        width=3000,
        height=2000,
        Artist='<a href="//commons.wikimedia.org/wiki/User:Mbzt">Mbzt</a>',
        DateTimeOriginal="2012-05-03 10:20:30",
    )
    assert commons.file_record(page) == {
        "title": "File:Pont Neuf 1.jpg",
        "user": "Mbzt",
        "width": 3000,
        "height": 2000,
        "mime": "image/jpeg",
        "page_url": "https://commons.wikimedia.org/wiki/File:Pont_Neuf_1.jpg",
        "thumb_url": (
            "https://thumb.wikimedia.org/thumb/a/ab/Pont_Neuf_1.jpg"
            "/960px-Pont_Neuf_1.jpg"
        ),
        "metadata": {
            "LicenseShortName": "CC BY-SA 4.0",
            "License": "cc-by-sa-4.0",
            "Artist": '<a href="//commons.wikimedia.org/wiki/User:Mbzt">Mbzt</a>',
            "DateTimeOriginal": "2012-05-03 10:20:30",
        },
    }
    assert commons.file_record({**stub("File:Gone.jpg"), "missing": True}) is None


def test_category_counts_are_asked_fifty_at_a_time() -> None:
    names = [f"Monument {number:03d}" for number in range(120)]
    requests: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(form(request))
        titles = requests[-1]["titles"].split("|")
        pages = [
            {"ns": 14, "title": title, "missing": True}
            if title.endswith("007")
            else {
                "ns": 14,
                "title": title,
                "categoryinfo": {"size": 9, "pages": 1, "files": 6, "subcats": 2},
            }
            for title in titles
        ]
        return answer(pages, batchcomplete=True)

    with web.make_client(transport=httpx.MockTransport(handler)) as client:
        counts = commons.fetch_category_info(client, names, pause=no_pause)
    assert [len(request["titles"].split("|")) for request in requests] == [50, 50, 20]
    assert requests[0]["titles"].startswith("Category:Monument 000|Category:")
    assert len(counts) == 119
    assert "Monument 007" not in counts
    assert counts["Monument 119"] == {"files": 6, "subcats": 2}


def test_subcategories_are_listed_by_name() -> None:
    requests: list[dict[str, str]] = []
    members = [
        {"pageid": 2, "ns": 14, "title": "Category:Interior of Pont Neuf"},
        {"pageid": 1, "ns": 14, "title": "Category:Exterior of Pont Neuf"},
    ]
    response = httpx.Response(200, json={"query": {"categorymembers": members}})
    with client_answering([response], requests) as client:
        names = commons.fetch_subcategories(client, "Pont Neuf", pause=no_pause)
    assert names == ["Exterior of Pont Neuf", "Interior of Pont Neuf"]
    assert requests[0]["cmtitle"] == "Category:Pont Neuf"
    assert requests[0]["cmtype"] == "subcat"


def test_files_asked_by_name_are_found_under_their_current_title() -> None:
    requests: list[dict[str, str]] = []
    response = httpx.Response(
        200,
        json={
            "query": {
                "normalized": [
                    {"from": "File:Old_name.jpg", "to": "File:Old name.jpg"}
                ],
                "redirects": [{"from": "File:Old name.jpg", "to": "File:New name.jpg"}],
                "pages": [
                    described("File:New name.jpg"),
                    described("File:Plain.jpg"),
                    {**stub("File:Gone.jpg"), "missing": True},
                ],
            }
        },
    )
    with client_answering([response], requests) as client:
        found = commons.fetch_files(
            client, ["Plain.jpg", "Old_name.jpg", "Gone.jpg"], pause=no_pause
        )
    assert requests[0]["titles"] == "File:Gone.jpg|File:Old_name.jpg|File:Plain.jpg"
    assert requests[0]["redirects"] == "1"
    assert found["Gone.jpg"] is None
    assert found["Plain.jpg"]["title"] == "File:Plain.jpg"
    assert found["Old_name.jpg"]["title"] == "File:New name.jpg"


def test_cache_keeps_one_line_per_answer_between_runs(tmp_path: Path) -> None:
    path = tmp_path / "commons" / "category_files.jsonl"
    cache = commons.Cache.open(path)
    assert cache.entries == {}
    cache.add("Pont Neuf", [{"title": "File:A.jpg"}])
    cache.add("Église Saint-Eustache", [])

    lines = [json.loads(line) for line in path.read_text().splitlines()]
    assert [line["key"] for line in lines] == ["Pont Neuf", "Église Saint-Eustache"]
    assert lines[0]["value"] == [{"title": "File:A.jpg"}]
    assert lines[0]["fetched_at"].endswith("+00:00")
    assert commons.Cache.open(path).entries == cache.entries


def test_answer_cut_short_by_an_interruption_is_dropped(tmp_path: Path) -> None:
    path = tmp_path / "category_files.jsonl"
    cache = commons.Cache.open(path)
    cache.add("Pont Neuf", [{"title": "File:A.jpg"}])
    whole = path.read_text()
    path.write_text(whole + '{"key": "Pont Marie", "fetched_at": "2026-10-08T09:')

    reopened = commons.Cache.open(path)
    assert reopened.entries == {"Pont Neuf": [{"title": "File:A.jpg"}]}
    # The file is clean again: the next answer starts on its own line.
    reopened.add("Pont Marie", [])
    assert commons.Cache.open(path).entries == {
        "Pont Neuf": [{"title": "File:A.jpg"}],
        "Pont Marie": [],
    }


def test_source_only_asks_for_what_the_cache_lacks(tmp_path: Path) -> None:
    requests: list[dict[str, str]] = []
    response = httpx.Response(
        200,
        json={
            "query": {"categorymembers": [{"ns": 14, "title": "Category:Vues du pont"}]}
        },
    )
    with client_answering([response], requests) as client:
        source = commons.Source.open(tmp_path, client)
        source.pause = no_pause
        source.subcategories.add("Pont Neuf", ["Exterior of Pont Neuf"])
        children = source.subcategories_of(["Pont Neuf", "Pont Marie"])
    assert children == {
        "Pont Neuf": ["Exterior of Pont Neuf"],
        "Pont Marie": ["Vues du pont"],
    }
    assert [request["cmtitle"] for request in requests] == ["Category:Pont Marie"]
    # The new answer is on disk for the next run.
    assert commons.Cache.open(tmp_path / "subcategories.jsonl").entries == children


def test_source_without_a_client_uses_the_cache_alone(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    source = commons.Source.open(tmp_path, None)
    source.files.add("Pont Neuf", [{"title": "File:A.jpg"}])
    with caplog.at_level(logging.WARNING):
        listings = source.category_files(["Pont Neuf", "Pont Marie"])
    assert listings == {"Pont Neuf": [{"title": "File:A.jpg"}]}
    assert "Offline: 1 category listings are not in the cache" in caplog.text


def test_source_remembers_what_does_not_exist(tmp_path: Path) -> None:
    requests: list[dict[str, str]] = []
    answers = [
        answer(
            [
                {"ns": 14, "title": "Category:Nowhere", "missing": True},
                {
                    "ns": 14,
                    "title": "Category:Pont Neuf",
                    "categoryinfo": {"files": 6, "subcats": 2},
                },
            ]
        ),
        answer([{**stub("File:Gone.jpg"), "missing": True}]),
    ]
    with client_answering(answers, requests) as client:
        source = commons.Source.open(tmp_path, client)
        source.pause = no_pause
        assert source.category_info(["Pont Neuf", "Nowhere"]) == {
            "Pont Neuf": {"files": 6, "subcats": 2}
        }
        assert source.named_files(["Gone.jpg"]) == {}
        # Asked once: a second call finds the absence in the cache.
        assert source.category_info(["Nowhere"]) == {}
        assert source.named_files(["Gone.jpg"]) == {}
    assert len(requests) == 2


def record(title: str, **changes: object) -> dict[str, object]:
    """A cached file answer, as `file_record` keeps it."""
    values = {"user": "Chabe01", "width": 4000, "height": 3000, "mime": "image/jpeg"}
    metadata = {"LicenseShortName": "CC BY-SA 4.0", "License": "cc-by-sa-4.0"}
    for key, value in changes.items():
        (values if key in values else metadata)[key] = value
    name = title.removeprefix("File:").replace(" ", "_")
    return {
        "title": title,
        **values,
        "page_url": f"https://commons.wikimedia.org/wiki/File:{name}",
        "thumb_url": f"https://thumb.wikimedia.org/thumb/a/ab/{name}/960px-{name}",
        "metadata": metadata,
    }


def photo(title: str, **changes: object) -> commons.Photo:
    return commons.describe(record(title, **changes))


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (
            (
                '<a href="//commons.wikimedia.org/wiki/User:Chabe01" title="User:Chabe01">'
                "Chabe01</a>"
            ),
            "Chabe01",
        ),
        (
            (
                '<a href="https://en.wikipedia.org/wiki/nl:User:Ron4">Ron4</a> at'
                ' <a href="https://en.wikipedia.org/wiki/nl:">Dutch Wikipedia</a>'
            ),
            "Ron4 at Dutch Wikipedia",
        ),
        (
            (
                '<div class="fn value">\n<p>Perelle, Adam (1638-1695). Graveur\n'
                "Silvestre, Isra&euml;l (1621-1691). Graveur\n</p></div>"
            ),
            "Perelle, Adam (1638-1695). Graveur Silvestre, Israël (1621-1691). Graveur",
        ),
        ("Pavel Krok", "Pavel Krok"),
        ("  ", None),
        (None, None),
    ],
)
def test_html_fields_become_plain_text(value: str | None, expected: str | None) -> None:
    assert commons.clean_text(value) == expected


@pytest.mark.parametrize(
    ("author", "expected"),
    [
        # Notices that real photographers wrote in the author field.
        (
            (
                "Thank you to indicate this credit line next to the image in case of "
                "reuse: Credit: Polymagou - CC BY-SA I'd appreciate if you could send a "
                "message on my user talk page if you use this picture out of the "
                "Wikimedia project scope ."
            ),
            "Polymagou",
        ),
        (
            (
                "This illustration was made by Peter Potrowl . Please credit this with : "
                "© Peter Potrowl in the immediate vicinity of the image."
            ),
            "Peter Potrowl",
        ),
        (
            (
                "This illustration was made by Citron You must credit this : "
                "Citron / CC-BY-SA-3.0"
            ),
            "Citron",
        ),
        (
            (
                "Another one of my pictures: This photograph was taken by Medium69 "
                "(William Crochot) and released under the license stated below."
            ),
            "Medium69 (William Crochot)",
        ),
        (
            (
                "This Photo was taken by Wolfgang Moroder . Feel free to use my photos, "
                "but please mention me as the author and send me a message ."
            ),
            "Wolfgang Moroder",
        ),
        (
            (
                "No machine-readable author provided. Clio20 assumed (based on "
                "copyright claims)."
            ),
            "Clio20",
        ),
        # Files moved from a Wikipedia.
        ("The original uploader was MOSSOT at French Wikipedia .", "MOSSOT"),
        ("Original uploader was Khardan at fr.wikipedia", "Khardan"),
        (
            "Patrick Giraud The original uploader was Calips at French Wikipedia .",
            "Patrick Giraud",
        ),
        (
            (
                "fr:Utilisateur:Jgremillot The original uploader was Jgremillot at "
                "French Wikipedia ."
            ),
            "Jgremillot",
        ),
        # Names, however long, are kept as they are.
        ("Chabe01", "Chabe01"),
        (
            "couscouschocolat from Issy-Les-Moulineaux, France",
            "couscouschocolat from Issy-Les-Moulineaux, France",
        ),
        (
            "Jules, Louis et Henri Séeberger © Reproduction Philippe Berthé / CMN",
            "Jules, Louis et Henri Séeberger © Reproduction Philippe Berthé / CMN",
        ),
        (
            "pcs34560 from jawp This photo was taken with Canon PowerShot G9",
            "pcs34560 from jawp This photo was taken with Canon PowerShot G9",
        ),
        (None, None),
    ],
)
def test_the_name_to_credit_is_read_from_a_notice(
    author: str | None, expected: str | None
) -> None:
    assert commons.credit_name(author) == expected


def test_a_notice_is_credited_by_name_without_changing_the_ranking() -> None:
    notice = "This illustration was made by Aaron . Please credit this with : © Aaron"
    listing = [
        record("File:First view.jpg", Artist="Chabe01", DateTimeOriginal="2020"),
        record("File:Second view.jpg", Artist=notice, DateTimeOriginal="2020"),
        record("File:Third view.jpg", Artist="Abel", DateTimeOriginal="2020"),
    ]
    files = commons.build_files([monument()], answers({"Pont Neuf": listing}))

    by_rank = files.sort_values("rank")
    assert list(by_rank["author"]) == ["Abel", "Chabe01", "Aaron"]
    # Sessions are ordered by the author as declared: "This..." comes last,
    # where "Aaron" would have come first.
    assert list(by_rank["title"]) == [
        "File:Third view.jpg",
        "File:First view.jpg",
        "File:Second view.jpg",
    ]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2014-06-21 15:02:11", 2014),
        ("2007-06", 2007),
        ("2012:05:03 10:20:30", 2012),
        ("En 07–10–1903", 1903),
        ("21–02–1899", 1899),
        ("Taken in March 1916", 1916),
        ("20 April 2007 (original upload date)", 2007),
        (
            (
                'circa 1814<div style="display: none;">date QS:P571,+1814-00-00T00:00:00Z/9,'
                "P1480,Q5727902</div>"
            ),
            1814,
        ),
        (
            (
                'between 1902 and 1903<div style="display: none;">date QS:P571,'
                "+1902-00-00T00:00:00Z/8,P1319,+1902-00-00T00:00:00Z/9</div>"
            ),
            1902,
        ),
        # No year is written: the one stated for machines is used.
        (
            (
                '17<sup>th</sup> century<div style="display: none;">date QS:P571,'
                "+1650-00-00T00:00:00Z/7</div>"
            ),
            1650,
        ),
        ("Unknown date", None),
        ("", None),
        (None, None),
    ],
)
def test_year_is_read_from_the_date_as_written(
    value: str | None, expected: int | None
) -> None:
    assert commons.photo_year(value) == expected


def test_cached_answer_is_read_into_a_photo() -> None:
    answer = record(
        "File:Pont Neuf 1.jpg",
        user="Mbzt",
        width=3000,
        height=2000,
        Artist='<a href="//commons.wikimedia.org/wiki/User:Mbzt">Mbzt</a>',
        DateTimeOriginal="2012-05-03 10:20:30",
        LicenseUrl="https://creativecommons.org/licenses/by-sa/4.0",
        GPSLatitude="48.857",
        GPSLongitude="2.341",
        Assessments="quality",
        Categories="Pont Neuf|Bridges in Paris",
    )
    assert commons.describe(answer) == commons.Photo(
        title="File:Pont Neuf 1.jpg",
        page_url="https://commons.wikimedia.org/wiki/File:Pont_Neuf_1.jpg",
        thumb_url=(
            "https://thumb.wikimedia.org/thumb/a/ab/Pont_Neuf_1.jpg"
            "/960px-Pont_Neuf_1.jpg"
        ),
        width=3000,
        height=2000,
        mime="image/jpeg",
        author="Mbzt",
        uploader="Mbzt",
        licence="CC BY-SA 4.0",
        licence_code="cc-by-sa-4.0",
        licence_url="https://creativecommons.org/licenses/by-sa/4.0",
        year=2012,
        camera_lat=48.857,
        camera_lon=2.341,
        assessment="quality",
        categories=("Pont Neuf", "Bridges in Paris"),
    )


def test_missing_fields_stay_empty() -> None:
    bare = commons.describe(record("File:A.jpg", Assessments="", Categories=""))
    assert bare.author is None
    assert bare.year is None
    assert bare.camera_lat is None
    assert bare.licence_url is None
    assert bare.assessment is None
    assert bare.categories == ()


def test_ranking_starts_with_the_main_image_then_the_distinguished_photos() -> None:
    photos = [
        photo("File:A.jpg", DateTimeOriginal="2024-01-01"),
        photo("File:B.jpg", DateTimeOriginal="2010-01-01", Assessments="quality"),
        photo("File:C.jpg", DateTimeOriginal="2005-01-01"),
    ]
    ranked = commons.rank_photos(photos, "File:C.jpg")
    assert [p.title for p in ranked] == ["File:C.jpg", "File:B.jpg", "File:A.jpg"]


def test_ranking_alternates_between_authors_and_years() -> None:
    photos = [
        photo("File:Anne 2020 a.jpg", Artist="Anne", DateTimeOriginal="2020-05-01"),
        photo("File:Anne 2020 b.jpg", Artist="Anne", DateTimeOriginal="2020-05-01"),
        photo("File:Anne 2020 c.jpg", Artist="Anne", DateTimeOriginal="2020-05-02"),
        photo("File:Anne 2012.jpg", Artist="Anne", DateTimeOriginal="2012-05-01"),
        photo("File:Bob 2020.jpg", Artist="Bob", DateTimeOriginal="2020-07-14"),
        photo("File:Undated.jpg", Artist="Zoé"),
    ]
    ranked = commons.rank_photos(list(reversed(photos)), None)
    # One photo of each session, the most recent first, then a second round.
    assert [p.title for p in ranked] == [
        "File:Anne 2020 a.jpg",
        "File:Bob 2020.jpg",
        "File:Anne 2012.jpg",
        "File:Undated.jpg",
        "File:Anne 2020 b.jpg",
        "File:Anne 2020 c.jpg",
    ]


def test_uploader_stands_for_a_missing_author_when_ranking() -> None:
    photos = [
        photo("File:A1.jpg", user="Anne", DateTimeOriginal="2020"),
        photo("File:A2.jpg", user="Anne", DateTimeOriginal="2020"),
        photo("File:B1.jpg", user="Bob", DateTimeOriginal="2020"),
    ]
    ranked = commons.rank_photos(photos, None)
    assert [p.title for p in ranked] == ["File:A1.jpg", "File:B1.jpg", "File:A2.jpg"]


def test_nothing_to_rank() -> None:
    assert commons.rank_photos([], "File:A.jpg") == []


def monument(
    merimee_id: str = "PA1",
    category: str | None = "Pont Neuf",
    main_image: str | None = None,
    names: tuple[str, ...] = ("Pont Neuf", "pont"),
) -> commons.Monument:
    return commons.Monument(merimee_id, category, main_image, names)


def answers(
    listings: dict[str, list[dict[str, object]]],
    children: dict[str, list[str]] | None = None,
    named: dict[str, dict[str, object]] | None = None,
) -> commons.Answers:
    info = {
        name: {"files": len(files), "subcats": 0} for name, files in listings.items()
    }
    return commons.Answers(info, listings, children or {}, named or {})


def several(prefix: str, count: int, **changes: object) -> list[dict[str, object]]:
    return [record(f"File:{prefix} {number}.jpg", **changes) for number in range(count)]


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({}, None),
        ({"mime": "image/png"}, "format"),
        ({"License": "gfdl", "LicenseShortName": "GFDL 1.2"}, "licence"),
        ({"License": "", "LicenseShortName": ""}, "licence"),
        # A free licence that Commons names without a code.
        ({"License": "", "LicenseShortName": "Licence Ouverte"}, None),
        ({"DateTimeOriginal": "En 1903"}, "old"),
        ({"DateTimeOriginal": "1950"}, None),
        ({"Categories": "Pont Neuf|Interior of Pont Neuf"}, "inside"),
        ({"width": 639, "height": 4000}, "small"),
        ({"width": 640, "height": 640}, None),
        # The first reason met is the one given.
        ({"mime": "image/tiff", "DateTimeOriginal": "1880", "width": 300}, "format"),
        ({"DateTimeOriginal": "1880", "width": 300}, "old"),
    ],
)
def test_reject_reason(changes: dict[str, object], expected: str | None) -> None:
    picture = photo("File:Pont Neuf 1.jpg", **changes)
    assert commons.reject_reason(picture, monument()) == expected


def test_unwanted_word_is_read_in_the_file_name_without_accents() -> None:
    picture = photo("File:Église Saint-Eustache - Intérieur.jpg")
    assert commons.reject_reason(picture, monument()) == "inside"


def test_word_of_the_monument_name_is_not_held_against_its_photos() -> None:
    picture = photo("File:Plan du quartier.jpg")
    assert commons.reject_reason(picture, monument()) == "document"
    street = monument(names=("Immeuble", "12 rue du Plan, Paris"))
    assert commons.reject_reason(picture, street) is None


def test_exterior_subcategories_are_always_chosen() -> None:
    children = [
        "Exterior of Église Saint-Eustache",
        "Interior of Église Saint-Eustache",
        "Quality images of Église Saint-Eustache",
        "Replicas of Église Saint-Eustache",
        "Église Saint-Eustache in art",
    ]
    church = monument(names=("Église Saint-Eustache", "église"))
    assert commons.chosen_subcategories(children, church, fallback=False) == [
        ("Exterior of Église Saint-Eustache", "exterior_subcategory")
    ]
    # A monument that lacks photos also gets the pictures that Commons distinguished.
    assert commons.chosen_subcategories(children, church, fallback=True) == [
        ("Exterior of Église Saint-Eustache", "exterior_subcategory"),
        ("Quality images of Église Saint-Eustache", "subcategory"),
    ]


def test_addresses_of_a_group_of_buildings_serve_as_a_fallback() -> None:
    children = [
        "40 rue de Provence, Paris",
        "42-44 rue de Provence, Paris",
        "11bis boulevard de Beauséjour, Paris",
        "Chapelle Taitbout",
    ]
    group = monument(names=("40-44 rue de Provence, Paris", "immeuble"))
    chosen = commons.chosen_subcategories(children, group, fallback=True)
    assert [name for name, _ in chosen] == children[:3]
    assert {source for _, source in chosen} == {"subcategory"}
    assert commons.chosen_subcategories(children, group, fallback=False) == []


def test_category_of_another_monument_is_never_read() -> None:
    # The buildings of a square have their own notices and their own photos.
    children = ["12 place Dauphine, Paris", "14 place Dauphine, Paris"]
    square = monument(names=("Place Dauphine", "place"))
    taken = frozenset({"Place Dauphine", "12 place Dauphine, Paris"})
    assert commons.chosen_subcategories(
        children, square, fallback=True, taken=taken
    ) == [("14 place Dauphine, Paris", "subcategory")]


def test_file_is_recorded_under_the_first_source_that_has_it() -> None:
    known = answers(
        {
            "Pont Neuf": [record("File:A.jpg"), record("File:Main.jpg")],
            "Exterior of Pont Neuf": [record("File:A.jpg"), record("File:B.jpg")],
            "Quality images of Pont Neuf": [record("File:B.jpg"), record("File:C.jpg")],
        },
        children={
            "Pont Neuf": ["Exterior of Pont Neuf", "Quality images of Pont Neuf"]
        },
    )
    bridge = monument(main_image="Main.jpg")

    found = commons.find_candidates(bridge, known, fallback=True)
    assert {c.photo.title: (c.source, c.category) for c in found} == {
        "File:Main.jpg": ("main_image", None),
        "File:A.jpg": ("category", "Pont Neuf"),
        "File:B.jpg": ("exterior_subcategory", "Exterior of Pont Neuf"),
        "File:C.jpg": ("subcategory", "Quality images of Pont Neuf"),
    }
    without = commons.find_candidates(bridge, known, fallback=False)
    assert "File:C.jpg" not in {c.photo.title for c in without}


def test_main_image_outside_the_category_is_found_by_name() -> None:
    known = answers(
        {"Pont Neuf": [record("File:A.jpg")]},
        named={"Old_name.jpg": record("File:New name.jpg")},
    )
    found = commons.find_candidates(
        monument(main_image="Old_name.jpg"), known, fallback=False
    )
    assert [(c.photo.title, c.source) for c in found] == [
        ("File:New name.jpg", "main_image"),
        ("File:A.jpg", "category"),
    ]
    # No category at all: the main image is the only photo.
    alone = commons.find_candidates(
        monument(category=None, main_image="Old_name.jpg"), known, fallback=False
    )
    assert [c.photo.title for c in alone] == ["File:New name.jpg"]


def test_other_subcategories_only_serve_a_monument_that_lacks_photos() -> None:
    children = {"Pont Neuf": ["Quality images of Pont Neuf"]}
    night = {"Quality images of Pont Neuf": several("Night", 3)}
    poor = answers({"Pont Neuf": several("Day", 4), **night}, children=children)
    rich = answers({"Pont Neuf": several("Day", 5), **night}, children=children)

    assert commons.lacks_photos(monument(), poor)
    assert not commons.lacks_photos(monument(), rich)
    assert len(commons.monument_rows(monument(), poor)) == 7
    assert len(commons.monument_rows(monument(), rich)) == 5


def test_rejected_files_do_not_count_as_photos() -> None:
    known = answers(
        {
            "Pont Neuf": [
                *several("Day", 3),
                *several("Old", 6, DateTimeOriginal="1900"),
            ],
            "Quality images of Pont Neuf": several("Night", 2),
        },
        children={"Pont Neuf": ["Quality images of Pont Neuf"]},
    )
    assert commons.lacks_photos(monument(), known)
    rows = commons.monument_rows(monument(), known)
    assert sum(row["reject_reason"] is None for row in rows) == 5
    assert sum(row["reject_reason"] == "old" for row in rows) == 6


def test_rows_describe_every_file_and_rank_the_kept_ones() -> None:
    known = answers(
        {
            "Pont Neuf": [
                record(
                    "File:B.jpg",
                    Artist="<b>Anne</b>",
                    DateTimeOriginal="2020-05-01",
                    LicenseUrl="https://creativecommons.org/licenses/by-sa/4.0",
                    GPSLatitude="48.857",
                    GPSLongitude="2.341",
                ),
                record("File:A.jpg", DateTimeOriginal="1900"),
                record("File:Main.jpg", DateTimeOriginal="2010"),
            ]
        }
    )
    rows = commons.monument_rows(monument(main_image="Main.jpg"), known)
    assert [row["title"] for row in rows] == [
        "File:A.jpg",
        "File:B.jpg",
        "File:Main.jpg",
    ]
    assert [row["reject_reason"] for row in rows] == ["old", None, None]
    assert [row["rank"] for row in rows] == [None, 2, 1]
    assert [row["selected"] for row in rows] == [False, True, True]
    assert rows[1] == {
        "merimee_id": "PA1",
        "title": "File:B.jpg",
        "source": "category",
        "category": "Pont Neuf",
        "page_url": "https://commons.wikimedia.org/wiki/File:B.jpg",
        "thumb_url": "https://thumb.wikimedia.org/thumb/a/ab/B.jpg/960px-B.jpg",
        "width": 4000,
        "height": 3000,
        "mime": "image/jpeg",
        "author": "Anne",
        "uploader": "Chabe01",
        "licence": "CC BY-SA 4.0",
        "licence_url": "https://creativecommons.org/licenses/by-sa/4.0",
        "year": 2020,
        "camera_lat": 48.857,
        "camera_lon": 2.341,
        "reject_reason": None,
        "rank": 2,
        "selected": True,
    }


def test_only_the_first_fifteen_photos_are_selected() -> None:
    known = answers({"Pont Neuf": several("Day", 20)})
    rows = commons.monument_rows(monument(), known)
    assert sum(row["selected"] for row in rows) == commons.MAX_SELECTED == 15
    assert sorted(row["rank"] for row in rows) == list(range(1, 21))
    assert all(row["selected"] == (row["rank"] <= 15) for row in rows)


def test_monuments_take_the_category_and_the_image_of_their_item() -> None:
    notices = [
        {
            "merimee_id": "PA1",
            "name": "Pont-Neuf",
            "protection": "classé",
            "denominations": ["pont"],
        },
        {
            "merimee_id": "PA2",
            "name": "Immeuble",
            "protection": None,
            "denominations": None,
        },
        {
            "merimee_id": "PA3",
            "name": "Immeuble",
            "protection": "inscrit",
            "denominations": None,
        },
        {
            "merimee_id": "PA4",
            "name": "Maison",
            "protection": "inscrit",
            "denominations": ["maison"],
        },
    ]
    entities = [
        {"merimee_id": "PA1", "wikidata_qid": "Q1"},
        {"merimee_id": "PA3", "wikidata_qid": None},
        {"merimee_id": "PA4", "wikidata_qid": "Q4"},
    ]
    items = [
        {
            "qid": "Q1",
            "label_fr": "pont Neuf",
            "commons_category": "Pont Neuf",
            "image_file": "Pont Neuf.jpg",
        },
        {
            "qid": "Q4",
            "label_fr": None,
            "commons_category": None,
            "image_file": "Maison.jpg",
        },
    ]
    assert commons.read_monuments(notices, entities, items) == [
        commons.Monument(
            "PA1",
            "Pont Neuf",
            "Pont Neuf.jpg",
            ("Pont-Neuf", "pont", "pont Neuf", "Pont Neuf"),
        ),
        # No Wikidata item: nothing to look for on Commons.
        commons.Monument("PA3", None, None, ("Immeuble",)),
        commons.Monument("PA4", None, "Maison.jpg", ("Maison", "maison")),
    ]


class FakeCommons:
    """A stand-in for the Commons API, answering from prepared categories and files."""

    def __init__(
        self,
        listings: dict[str, list[dict[str, object]]],
        children: dict[str, list[str]] | None = None,
        files: dict[str, dict[str, object]] | None = None,
        info: dict[str, dict[str, int]] | None = None,
    ) -> None:
        self.listings = listings
        self.children = children or {}
        self.files = files or {}
        self.info = info
        self.requests: list[dict[str, str]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        params = form(request)
        self.requests.append(params)
        if params.get("prop") == "categoryinfo":
            return answer([self.counts(title) for title in params["titles"].split("|")])
        if "gcmtitle" in params:
            return answer(self.listings[params["gcmtitle"].removeprefix("Category:")])
        if "cmtitle" in params:
            names = self.children[params["cmtitle"].removeprefix("Category:")]
            members = [{"ns": 14, "title": f"Category:{name}"} for name in names]
            return httpx.Response(200, json={"query": {"categorymembers": members}})
        names = [title.removeprefix("File:") for title in params["titles"].split("|")]
        missing = {"missing": True}
        return answer(
            [
                self.files.get(name, {**stub(f"File:{name}"), **missing})
                for name in names
            ]
        )

    def counts(self, title: str) -> dict[str, object]:
        name = title.removeprefix("Category:")
        if self.info is not None and name in self.info:
            return {"ns": 14, "title": title, "categoryinfo": self.info[name]}
        if name not in self.listings:
            return {"ns": 14, "title": title, "missing": True}
        info = {
            "files": len(self.listings[name]),
            "subcats": len(self.children.get(name, [])),
        }
        return {"ns": 14, "title": title, "categoryinfo": info}

    def asked(self) -> list[str]:
        """What each request was about, in order."""
        keys = ("gcmtitle", "cmtitle", "titles")
        return [
            next(params[key] for key in keys if key in params)
            for params in self.requests
        ]

    def client(self) -> httpx.Client:
        return web.make_client(transport=httpx.MockTransport(self))


def pages(prefix: str, count: int, **metadata: str) -> list[dict[str, object]]:
    return [
        described(f"File:{prefix} {number}.jpg", **metadata) for number in range(count)
    ]


def test_collection_asks_only_for_what_the_monuments_need(tmp_path: Path) -> None:
    service = FakeCommons(
        {
            "Pont Neuf": [*pages("Bridge", 5), described("File:Bridge main.jpg")],
            "Exterior of Pont Neuf": pages("Outside", 2),
            "Quality images of Pont Neuf": pages("Night", 2),
            "Maison Dupont": pages("House", 2),
            "Quality images of Maison Dupont": pages("House 2015", 2),
            "Interior of Maison Dupont": pages("Inside", 2),
        },
        children={
            "Pont Neuf": ["Exterior of Pont Neuf", "Quality images of Pont Neuf"],
            "Maison Dupont": [
                "Interior of Maison Dupont",
                "Quality images of Maison Dupont",
            ],
        },
        files={"Elsewhere.jpg": described("File:Elsewhere.jpg")},
    )
    monuments = [
        monument("PA1", "Pont Neuf", "Bridge main.jpg"),
        monument("PA2", "Maison Dupont", "Elsewhere.jpg", ("Maison Dupont",)),
        monument("PA3", "Deleted category", None, ("Immeuble",)),
        monument("PA4", None, "Gone.jpg", ("Immeuble",)),
    ]
    with service.client() as client:
        source = commons.Source.open(tmp_path, client)
        source.pause = no_pause
        got = commons.collect(source, monuments)

    assert service.asked() == [
        "Category:Deleted category|Category:Maison Dupont|Category:Pont Neuf",
        "Category:Maison Dupont",
        "Category:Pont Neuf",
        "Category:Maison Dupont",
        "Category:Pont Neuf",
        # The views of the outside, for every monument that has some.
        "Category:Exterior of Pont Neuf",
        # The main images that their category does not list.
        "File:Elsewhere.jpg|File:Gone.jpg",
        # The house lacks photos: its other subcategory is read, not the interior.
        "Category:Quality images of Maison Dupont",
    ]
    assert set(got.info) == {"Maison Dupont", "Pont Neuf"}
    assert set(got.listings) == {
        "Pont Neuf",
        "Exterior of Pont Neuf",
        "Maison Dupont",
        "Quality images of Maison Dupont",
    }
    assert set(got.named) == {"Elsewhere.jpg"}

    files = commons.build_files(monuments, got)
    assert files.groupby("merimee_id").size().to_dict() == {"PA1": 8, "PA2": 5}
    assert files.groupby("source").size().to_dict() == {
        "category": 7,
        "exterior_subcategory": 2,
        "main_image": 2,
        "subcategory": 2,
    }
    categories = commons.build_categories(got)
    assert categories.to_dict("records") == [
        {"commons_category": "Maison Dupont", "files": 2, "subcats": 2},
        {"commons_category": "Pont Neuf", "files": 6, "subcats": 2},
    ]


def test_second_collection_asks_nothing(tmp_path: Path) -> None:
    service = FakeCommons({"Pont Neuf": pages("Bridge", 2)})
    monuments = [monument("PA1", "Pont Neuf", None)]
    with service.client() as client:
        source = commons.Source.open(tmp_path, client)
        source.pause = no_pause
        first = commons.collect(source, monuments)
        asked = len(service.requests)
        again = commons.collect(commons.Source.open(tmp_path, client), monuments)
    assert len(service.requests) == asked
    assert again == first
    offline = commons.collect(commons.Source.open(tmp_path, None), monuments)
    assert offline == first


def test_summary_counts_the_files_and_the_monuments_served() -> None:
    known = answers(
        {
            "Pont Neuf": [
                *several("Day", 16),
                record("File:Old.jpg", DateTimeOriginal="1900"),
            ],
            "Maison Dupont": [
                record("File:House.jpg"),
                record("File:Plan.png", mime="image/png"),
            ],
        }
    )
    monuments = [
        monument("PA1", "Pont Neuf"),
        monument("PA2", "Maison Dupont", None, ("Maison Dupont",)),
        monument("PA3", None, None, ("Immeuble",)),
    ]
    files = commons.build_files(monuments, known)
    labels = [
        {
            "merimee_id": "PA1",
            "title": "File:Day 0.jpg",
            "sample": "dev",
            "label": "ok",
        },
        {
            "merimee_id": "PA1",
            "title": "File:Day 1.jpg",
            "sample": "test",
            "label": "detail",
        },
    ]
    evaluation = commons.evaluate(files, labels)
    assert commons.summarize(monuments, files, evaluation) == {
        "monuments": 3,
        "monuments_with_a_category": 2,
        "monuments_with_a_photo": 2,
        "monuments_with_5_photos": 1,
        "monuments_with_15_photos": 1,
        "files": 19,
        "files_kept": 17,
        "files_selected": 16,
        "rejected=format": 1,
        "rejected=old": 1,
        "dev_kept_rightly": 1,
        "test_kept_wrongly": 1,
    }


def test_labels_are_read(tmp_path: Path) -> None:
    path = tmp_path / "commons_labels.csv"
    path.write_text(
        "merimee_id,title,sample,label,note\n"
        'PA1,"File:Pont Neuf, vue 1.jpg",dev,ok,\n'
        "PA1,File:Escalier.jpg,test,inside,Un escalier\n"
    )
    assert commons.read_labels(path) == [
        {
            "merimee_id": "PA1",
            "title": "File:Pont Neuf, vue 1.jpg",
            "sample": "dev",
            "label": "ok",
            "note": "",
        },
        {
            "merimee_id": "PA1",
            "title": "File:Escalier.jpg",
            "sample": "test",
            "label": "inside",
            "note": "Un escalier",
        },
    ]
    assert commons.read_labels(tmp_path / "missing.csv") == []


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ("PA1,File:A.jpg,dev,belle,\n", "line 2: unknown label 'belle'"),
        ("PA1,File:A.jpg,train,ok,\n", "line 2: unknown sample 'train'"),
        (
            "PA1,File:A.jpg,dev,ok,\nPA1,File:A.jpg,test,ok,\n",
            "line 3: File:A.jpg appears twice",
        ),
    ],
)
def test_invalid_labels_are_refused(tmp_path: Path, rows: str, message: str) -> None:
    path = tmp_path / "commons_labels.csv"
    path.write_text("merimee_id,title,sample,label,note\n" + rows)
    with pytest.raises(ValueError, match=message):
        commons.read_labels(path)


def test_same_file_can_be_labelled_for_two_monuments(tmp_path: Path) -> None:
    path = tmp_path / "commons_labels.csv"
    path.write_text(
        "merimee_id,title,sample,label,note\n"
        "PA1,File:A.jpg,dev,ok,\n"
        "PA2,File:A.jpg,dev,other,\n"
    )
    assert [row["label"] for row in commons.read_labels(path)] == ["ok", "other"]


def test_evaluation_judges_the_reasons_that_rest_on_the_subject(
    caplog: pytest.LogCaptureFixture,
) -> None:
    known = answers(
        {
            "Pont Neuf": [
                record("File:Good.jpg"),
                record("File:Unnamed view.jpg"),
                record("File:Interior.jpg"),
                record("File:Plan.jpg"),
                record("File:Tiny.jpg", width=300),
                record("File:Old.jpg", DateTimeOriginal="1900"),
            ]
        }
    )
    files = commons.build_files([monument()], known)

    def label(title: str, seen: str, sample: str = "dev") -> dict[str, str]:
        return {"merimee_id": "PA1", "title": title, "sample": sample, "label": seen}

    labels = [
        label("File:Good.jpg", "ok"),
        label("File:Unnamed view.jpg", "inside"),
        label("File:Interior.jpg", "inside", "test"),
        # A plan by its name, a view of the bridge in fact.
        label("File:Plan.jpg", "ok", "test"),
        label("File:Tiny.jpg", "ok"),
        label("File:Old.jpg", "document"),
        label("File:Deleted.jpg", "ok"),
    ]
    with caplog.at_level(logging.WARNING):
        evaluation = commons.evaluate(files, labels)

    assert list(evaluation.columns) == commons.EVALUATION_COLUMNS
    assert evaluation.set_index("title")["outcome"].to_dict() == {
        "File:Good.jpg": "kept_rightly",
        "File:Unnamed view.jpg": "kept_wrongly",
        "File:Interior.jpg": "rejected_rightly",
        "File:Plan.jpg": "rejected_wrongly",
        "File:Tiny.jpg": "not_judged",
        "File:Old.jpg": "not_judged",
    }
    assert list(evaluation["reject_reason"].fillna("")) == [
        "",
        "",
        "inside",
        "document",
        "small",
        "old",
    ]
    assert list(evaluation["selected"]) == [True, True, False, False, False, False]
    assert "1 labelled photos are no longer listed" in caplog.text


def test_evaluation_without_labels_is_empty() -> None:
    files = commons.build_files([monument()], answers({"Pont Neuf": several("Day", 2)}))
    evaluation = commons.evaluate(files, [])
    assert evaluation.empty
    assert list(evaluation.columns) == commons.EVALUATION_COLUMNS


def test_some_words_only_count_in_the_file_name() -> None:
    hotel = monument(names=("Hôtel de Sully", "hôtel"))
    # As a category, "windows" is found on pictures of whole fronts.
    front = photo("File:Hôtel de Sully 1.jpg", Categories="Windows in Paris")
    assert commons.reject_reason(front, hotel) is None
    window = photo("File:Hôtel de Sully - fenêtre.jpg")
    assert commons.reject_reason(window, hotel) == "detail"
    board = photo("File:Panneau Histoire de Paris - Hôtel de Sully.jpg")
    assert commons.reject_reason(board, hotel) == "detail"
    mask = photo("File:Hôtel de Sully mascaron.jpg")
    assert commons.reject_reason(mask, hotel) == "sculpture"
    masks = photo("File:Hôtel de Sully 2.jpg", Categories="Mascarons in Paris")
    assert commons.reject_reason(masks, hotel) is None


def test_other_words_count_in_the_categories_too() -> None:
    hotel = monument(names=("Hôtel de Sully", "hôtel"))
    for categories, expected in [
        ("Plaques in Paris 4e arrondissement", "detail"),
        ("Details of doors in Paris", "detail"),
        ("Staircases in Paris", "inside"),
        ("Images from Paris Musées", "document"),
        ("Black and white photographs of France", "document"),
        ("Construction sites in Paris", "other"),
        ("Shop windows in Paris|Town hall of Paris 4e arrondissement", None),
    ]:
        picture = photo("File:Hôtel de Sully 3.jpg", Categories=categories)
        assert commons.reject_reason(picture, hotel) == expected, categories


def test_subject_of_the_monument_is_not_unwanted() -> None:
    inside = photo("File:Galerie Vivienne - intérieur.jpg")
    statue = photo("File:Fontaine Molière - statue.jpg")
    hotel = monument(names=("Hôtel de Sully", "hôtel"))
    assert commons.reject_reason(inside, hotel) == "inside"
    assert commons.reject_reason(statue, hotel) == "sculpture"

    notices = [
        {
            "merimee_id": "PA1",
            "name": "Galerie Vivienne",
            "protection": "inscrit",
            "denominations": ["passage couvert"],
        },
        {
            "merimee_id": "PA2",
            "name": "Fontaine Molière",
            "protection": "classé",
            "denominations": ["fontaine"],
        },
    ]
    passage, fountain = commons.read_monuments(notices, [], [])
    assert passage.exempt == {"inside"}
    assert fountain.exempt == {"sculpture"}
    assert commons.reject_reason(inside, passage) is None
    assert commons.reject_reason(statue, fountain) is None
    # The other kinds still apply.
    assert commons.reject_reason(statue, passage) == "sculpture"
    assert commons.reject_reason(inside, fountain) == "inside"


def test_underground_monument_only_keeps_the_photos_of_its_entrances() -> None:
    notices = [
        {
            "merimee_id": "PA1",
            "name": "Métropolitain, station Nation",
            "protection": "inscrit",
            "denominations": ["station de métro"],
        }
    ]
    (station,) = commons.read_monuments(notices, [], [])
    assert station.entrance_only

    hall = photo("File:Station Nation Métro Paris - Paris XII (FR75) - 6.jpg")
    assert commons.reject_reason(hall, station) == "inside"
    entrance = photo("File:Accès Station Nation Métro Paris Place Nation.jpg")
    assert commons.reject_reason(entrance, station) is None
    corridor = photo("File:Couloir Accès Station Nation Métro Paris.jpg")
    assert commons.reject_reason(corridor, station) == "inside"
    surround = photo("File:Nation 3.jpg", Categories="Hector Guimard metro entrances")
    assert commons.reject_reason(surround, station) is None
    # The same file name says nothing against the photo of a building.
    assert not monument().entrance_only
    assert commons.reject_reason(hall, monument()) is None


def test_subcategory_of_entrances_counts_as_views_of_the_outside() -> None:
    children = [
        "Entrances of Nation metro station",
        "Platforms of Nation metro station",
    ]
    station = monument(names=("Nation (Paris Metro)", "station de métro"))
    assert commons.chosen_subcategories(children, station, fallback=True) == [
        ("Entrances of Nation metro station", "exterior_subcategory")
    ]


def page_of(answer: dict[str, object]) -> dict[str, object]:
    """Turn a cached file answer back into the page that Commons sent."""
    metadata = answer["metadata"]
    assert isinstance(metadata, dict)
    return {
        **stub(str(answer["title"])),
        "imageinfo": [
            {
                "user": answer["user"],
                "width": answer["width"],
                "height": answer["height"],
                "mime": answer["mime"],
                "descriptionurl": answer["page_url"],
                "thumburl": answer["thumb_url"],
                "extmetadata": {
                    key: {"value": value} for key, value in metadata.items()
                },
            }
        ],
    }


def recorded_service() -> FakeCommons:
    """A stand-in service that gives the answers recorded for the sample notices."""
    snapshot = json.loads((FIXTURES / "commons_snapshot.json").read_text())
    return FakeCommons(
        {
            name: [page_of(answer) for answer in answers]
            for name, answers in snapshot["category_files"].items()
        },
        children=snapshot["subcategories"],
        files={name: page_of(answer) for name, answer in snapshot["files"].items()},
        info=snapshot["category_info"],
    )


def run_main(
    folder: Path,
    out: Path,
    monkeypatch: pytest.MonkeyPatch,
    service: FakeCommons | None,
    *args: str,
    labels: str = "",
) -> None:
    out.mkdir(exist_ok=True)
    labels_csv = out / "commons_labels.csv"
    if labels:
        labels_csv.write_text("merimee_id,title,sample,label,note\n" + labels)
    paths = {
        "MERIMEE_PARQUET": folder / "merimee.parquet",
        "ENTITIES_PARQUET": folder / "entities.parquet",
        "WIKIDATA_ITEMS_PARQUET": folder / "wikidata_items.parquet",
        "RAW_FOLDER": out / "raw",
        "LABELS_CSV": labels_csv,
        "FILES_PARQUET": out / "commons_files.parquet",
        "CATEGORIES_PARQUET": out / "commons_categories.parquet",
        "EVALUATION_CSV": out / "commons_evaluation.csv",
    }
    for name, path in paths.items():
        monkeypatch.setattr(commons, name, path)
    monkeypatch.setattr(commons, "REQUEST_PAUSE_SECONDS", 0)

    def make_client() -> httpx.Client:
        assert service is not None, "the step must not reach the network"
        return service.client()

    monkeypatch.setattr(commons, "make_client", make_client)
    assert commons.main(list(args)) == 0


def test_real_notices_get_their_photos(
    resolved_tables: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = recorded_service()
    run_main(resolved_tables, tmp_path, monkeypatch, service)

    files = pd.read_parquet(tmp_path / "commons_files.parquet")
    assert list(files.columns) == commons.FILES_SCHEMA.names
    # The nine protected notices of the sample all have at least their main image.
    first = files[files["rank"] == 1]
    assert sorted(first["merimee_id"]) == sorted(files["merimee_id"].unique())
    assert len(first) == 9
    assert (first["source"] == "main_image").all()
    assert files["reject_reason"].fillna("kept").value_counts().to_dict() == {
        "kept": 39,
        "old": 6,
        "inside": 5,
        "detail": 3,
        "other": 3,
        "document": 2,
        "small": 2,
        "format": 1,
    }
    assert files["selected"].sum() == 39

    # A metro station: the corridors and halls of its category are set aside,
    # the photos of its entrances come from their own subcategory.
    station = files[files["merimee_id"] == "PA00086579"]
    inside = station[station["source"] == "category"]
    assert list(inside["reject_reason"]) == ["old", *["inside"] * 5]
    entrances = station[station["source"] == "exterior_subcategory"]
    assert set(entrances["category"]) == {"Entrances to Nation metro station"}
    assert len(entrances) == 6
    assert entrances["selected"].all()

    # A church: the engravings of the museum are old, its outside has a subcategory.
    assumption = files[files["merimee_id"] == "PA00085794"]
    assert assumption["reject_reason"].fillna("kept").value_counts().to_dict() == {
        "old": 5,
        "kept": 1,
    }
    eustache = files[files["merimee_id"] == "PA00085795"]
    assert set(eustache["source"]) == {"main_image", "category", "exterior_subcategory"}
    # Its main image is not in its category: it was asked for by name.
    assert "St.-Eustache.jpg" in service.asked()[-1]

    # A notice without a Commons category only has the image of its Wikidata item.
    alone = files[files["merimee_id"] == "PA75170009"]
    assert alone[["title", "source", "author", "licence", "year"]].to_dict(
        "records"
    ) == [
        {
            "title": "File:Façade du 8 rue de Levis à Paris.jpg",
            "source": "main_image",
            "author": "Benoitdd",
            "licence": "CC BY-SA 4.0",
            "year": 2023,
        }
    ]

    categories = pd.read_parquet(tmp_path / "commons_categories.parquet")
    assert list(categories.columns) == commons.CATEGORIES_SCHEMA.names
    assert len(categories) == 8
    counts = categories.set_index("commons_category")
    assert counts.loc["Église Saint-Eustache de Paris"].to_dict() == {
        "files": 22,
        "subcats": 13,
    }
    assert pd.read_csv(tmp_path / "commons_evaluation.csv").empty


def test_offline_run_replays_the_saved_answers(
    resolved_tables: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_main(resolved_tables, tmp_path, monkeypatch, recorded_service())
    files = pd.read_parquet(tmp_path / "commons_files.parquet")
    categories = pd.read_parquet(tmp_path / "commons_categories.parquet")
    (tmp_path / "commons_files.parquet").unlink()

    # No service: any request would fail the test.
    run_main(resolved_tables, tmp_path, monkeypatch, None, "--offline")
    pd.testing.assert_frame_equal(
        pd.read_parquet(tmp_path / "commons_files.parquet"), files
    )
    pd.testing.assert_frame_equal(
        pd.read_parquet(tmp_path / "commons_categories.parquet"), categories
    )


def test_second_run_asks_nothing_unless_told_to_refresh(
    resolved_tables: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = recorded_service()
    run_main(resolved_tables, tmp_path, monkeypatch, service)
    asked = len(service.requests)
    assert asked == 18

    run_main(resolved_tables, tmp_path, monkeypatch, service)
    assert len(service.requests) == asked
    run_main(resolved_tables, tmp_path, monkeypatch, service, "--refresh")
    assert len(service.requests) == 2 * asked


def test_offline_and_refresh_cannot_be_combined(
    resolved_tables: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(SystemExit):
        run_main(resolved_tables, tmp_path, monkeypatch, None, "--offline", "--refresh")
    assert not (tmp_path / "commons_files.parquet").exists()


def test_labels_are_compared_with_the_decisions(
    resolved_tables: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_main(
        resolved_tables,
        tmp_path,
        monkeypatch,
        recorded_service(),
        labels=(
            "PA00085786,File:Paris 3 rue Étienne-Marcel 01.jpg,dev,ok,\n"
            "PA00085809,File:Hôtel Baudard de Saint-James - Plaque Chopin.jpg,test,"
            "detail,Une plaque\n"
            "PA00085809,File:Hôtel Baudard de Saint-James.jpg,test,inside,\n"
        ),
    )
    evaluation = pd.read_csv(tmp_path / "commons_evaluation.csv")
    assert evaluation[["sample", "label", "outcome"]].to_dict("records") == [
        {"sample": "dev", "label": "ok", "outcome": "kept_rightly"},
        {"sample": "test", "label": "detail", "outcome": "rejected_rightly"},
        {"sample": "test", "label": "inside", "outcome": "kept_wrongly"},
    ]
