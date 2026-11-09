import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx

from lutece_pipeline import fetch_articles, web


def answer(title: str, missing: bool = False) -> dict[str, object]:
    page: dict[str, object] = {"title": title}
    if missing:
        page["missing"] = True
    else:
        page.update(
            {
                "lastrevid": 42,
                "extract": f"{title} est un lieu.\n\n== Histoire ==\nIl a une histoire.",
            }
        )
    return {"query": {"pages": [page]}}


def test_each_article_is_asked_for_once() -> None:
    chosen = [
        {"shown": True, "article": "Panthéon (Paris)"},
        {"shown": False, "article": "Immeuble"},
        {"shown": True, "article": "Panthéon (Paris)"},
        {"shown": True, "article": None},
    ]
    places = [{"article": "Tour Montparnasse"}]
    assert fetch_articles.article_titles(chosen, places) == [
        "Panthéon (Paris)",
        "Tour Montparnasse",
    ]


def test_an_answer_gives_the_text_and_its_revision() -> None:
    found = fetch_articles.read_answer("Panthéon", answer("Panthéon (Paris)"))
    assert found["page_title"] == "Panthéon (Paris)"
    assert found["revision"] == 42
    assert found["text"].startswith("Panthéon (Paris) est un lieu.")
    missing = fetch_articles.read_answer("Rien", answer("Rien", missing=True))
    assert missing["text"] is None and missing["revision"] is None


def test_articles_are_kept_as_they_come_and_not_asked_again(tmp_path: Path) -> None:
    asked = []

    def respond(request: httpx.Request) -> httpx.Response:
        title = parse_qs(urlparse(str(request.url)).query)["titles"][0]
        asked.append(title)
        return httpx.Response(200, json=answer(title))

    snapshot = tmp_path / "articles.jsonl"
    client = web.make_client(transport=httpx.MockTransport(respond))
    known = fetch_articles.fetch(client, ["A", "B"], snapshot, pause=lambda _: None)
    assert sorted(known) == ["A", "B"]
    assert len(snapshot.read_text().splitlines()) == 2
    # A second run asks only for what is missing.
    fetch_articles.fetch(client, ["A", "B", "C"], snapshot, pause=lambda _: None)
    assert asked == ["A", "B", "C"]
    table = fetch_articles.build_table(
        ["A", "C"], fetch_articles.read_snapshot(snapshot)
    )
    assert table["title"].tolist() == ["A", "C"]
    assert (
        table["characters"].tolist()
        == [len(json.loads(snapshot.read_text().splitlines()[0])["text"])] * 2
    )
