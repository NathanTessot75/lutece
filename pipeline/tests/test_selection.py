import json
from pathlib import Path

import httpx
import pandas as pd
import pytest

from lutece_pipeline import ingest_wikidata, selection, web
from lutece_pipeline.selection import Article
from lutece_pipeline.tables import to_records

ENTITY = "http://www.wikidata.org/entity/"
# Every notice of the tests stands on its street, unless a test says otherwise.
SEEN = [
    {"merimee_id": f"PA{number}", "visibility": "visible", "reason": "whole_monument"}
    for number in range(1, 5)
]


def notice(
    merimee_id: str,
    name: str = "Lycée Louis-le-Grand",
    denominations: tuple[str, ...] = ("lycée",),
) -> dict[str, object]:
    return {
        "merimee_id": merimee_id,
        "name": name,
        "protection": "inscrit",
        "denominations": list(denominations),
        "arrondissement": 5,
    }


def entity(merimee_id: str, qid: str | None) -> dict[str, object]:
    return {"merimee_id": merimee_id, "wikidata_qid": qid}


def item(qid: str, article: str | None = None, sitelinks: int = 3) -> dict[str, object]:
    return {"qid": qid, "frwiki_title": article, "sitelinks": sitelinks}


def found(
    merimee_id: str,
    article: str | None = None,
    languages: int | None = None,
    *,
    reason: str | None = "article",
    excluded: bool = False,
    approachable: bool = True,
) -> dict[str, object]:
    """A line of `find_articles`."""
    return {
        "merimee_id": merimee_id,
        "excluded": excluded,
        "approachable": approachable,
        "reason": reason if article is not None else None,
        "article": article,
        "languages": languages if article is not None else None,
    }


def select(
    lines: list[dict[str, object]],
    views: dict[str, int] | None = None,
    overrides: dict[str, str] | None = None,
) -> dict[str, dict[str, object]]:
    chosen = selection.build_selection(lines, views or {}, overrides or {})
    return {row["merimee_id"]: row for row in to_records(chosen)}


def test_article_of_a_monument_is_the_one_of_its_item() -> None:
    lines = selection.find_articles(
        [notice("PA1"), notice("PA2"), notice("PA3")],
        [entity("PA1", "Q1"), entity("PA2", "Q2")],
        [item("Q1", "Lycée Louis-le-Grand", sitelinks=12), item("Q2")],
        {},
        SEEN,
    )
    assert lines == [
        found("PA1", "Lycée Louis-le-Grand", 12),
        # An item without an article, and a notice without an item.
        found("PA2"),
        found("PA3"),
    ]


def test_named_monument_takes_the_article_of_what_it_holds() -> None:
    # The article is about the school, the notice about its building.
    lines = selection.find_articles(
        [notice("PA1"), notice("PA2", name="Lycée")],
        [entity("PA1", "Q1"), entity("PA2", "Q2")],
        [item("Q1"), item("Q2")],
        {"Q1": Article("Lycée Louis-le-Grand", 40), "Q2": Article("Zara", 60)},
        SEEN,
    )
    assert lines[0] == found(
        "PA1", "Lycée Louis-le-Grand", 40, reason="neighbour_article"
    )
    # A building without a name of its own is not shown for its tenant.
    assert lines[1] == found("PA2")


def test_its_own_article_comes_before_the_one_of_a_neighbour() -> None:
    (line,) = selection.find_articles(
        [notice("PA1")],
        [entity("PA1", "Q1")],
        [item("Q1", "Hôtel Carnavalet", sitelinks=4)],
        {"Q1": Article("Musée Carnavalet", 30)},
        SEEN,
    )
    assert line == found("PA1", "Hôtel Carnavalet", 4)


def test_metro_stations_and_notices_without_protection_are_marked() -> None:
    station = notice("PA1", "Métropolitain, station Abbesses", ("station de métro",))
    cancelled = {**notice("PA2"), "protection": None}
    lines = selection.find_articles(
        [station, cancelled, notice("PA3")],
        [entity("PA1", "Q1")],
        [item("Q1", "Abbesses (métro de Paris)")],
        {},
        SEEN,
    )
    assert [(line["merimee_id"], line["excluded"]) for line in lines] == [
        ("PA1", True),
        ("PA3", False),
    ]


def test_what_cannot_be_walked_up_to_is_marked() -> None:
    seen = [
        {"merimee_id": "PA1", "visibility": "non_visible", "reason": "inside_only"},
        {"merimee_id": "PA2", "visibility": "inconnu", "reason": "unplaced_item"},
        {"merimee_id": "PA3", "visibility": "non_visible", "reason": "underground"},
    ]
    notices = [notice("PA1"), notice("PA2"), notice("PA3"), notice("PA4")]
    lines = selection.find_articles(notices, [], [], {}, seen)
    # Protected inside only, the building is on its street; nothing says where
    # the second and the fourth are, and the third is under the ground.
    assert [line["approachable"] for line in lines] == [True, False, False, False]


def test_monuments_with_an_article_are_shown_and_ranked() -> None:
    chosen = select(
        [
            found("PA1", "Tour Eiffel", 190),
            found("PA2", "Hôtel de Sully", 12),
            found("PA3"),
            found("PA4", "Hôtel Dodun", 2),
        ],
        views={"Tour Eiffel": 900_000, "Hôtel de Sully": 30_000, "Hôtel Dodun": 800},
    )
    assert [chosen[key]["shown"] for key in ("PA1", "PA2", "PA3", "PA4")] == [
        True,
        True,
        False,
        True,
    ]
    assert [chosen[key]["rank"] for key in ("PA1", "PA2", "PA3", "PA4")] == [
        1,
        2,
        None,
        3,
    ]
    assert chosen["PA1"]["views"] == 900_000
    assert chosen["PA1"]["languages"] == 190
    # The best known of three on both measures, then the middle one, then the last.
    assert chosen["PA1"]["score"] == pytest.approx(1.0)
    assert chosen["PA2"]["score"] == pytest.approx(2 / 3)
    assert chosen["PA4"]["score"] == pytest.approx(1 / 3)
    assert chosen["PA3"]["score"] is None
    assert chosen["PA3"]["views"] is None
    assert chosen["PA3"]["left_out"] == "no_article"
    assert chosen["PA1"]["left_out"] is None


def test_only_the_best_known_are_shown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(selection, "LAST_RANK_SHOWN", 2)
    lines = [
        found("PA1", "Tour Eiffel", 190),
        found("PA2", "Hôtel de Sully", 12),
        found("PA3", "Hôtel Dodun", 2),
        found("PA4", "Hôtel Donon", 1),
    ]
    views = {"Tour Eiffel": 900, "Hôtel de Sully": 300, "Hôtel Dodun": 20}
    chosen = select(lines, views, {"PA4": "show"})
    assert [chosen[f"PA{n}"]["shown"] for n in (1, 2, 3, 4)] == [
        True,
        True,
        False,
        True,
    ]
    assert chosen["PA3"]["left_out"] == "too_little_known"
    # It keeps its place in the ranking, to see how far from the cut it is.
    assert chosen["PA3"]["rank"] == 3
    assert chosen["PA3"]["reason"] is None
    # Asked for by hand, the last one is shown whatever its place.
    assert (chosen["PA4"]["rank"], chosen["PA4"]["reason"]) == (4, "article")


def test_what_cannot_be_walked_up_to_is_not_shown() -> None:
    lines = [
        found("PA1", "Enceinte de Philippe Auguste", 20, approachable=False),
        found("PA2", "Hôtel de Sully", 12),
        found("PA3", "Carrière", 3, approachable=False),
    ]
    views = {"Enceinte de Philippe Auguste": 900, "Hôtel de Sully": 300}
    chosen = select(lines, views, {"PA3": "show"})
    assert chosen["PA1"]["shown"] is False
    assert chosen["PA1"]["left_out"] == "cannot_be_approached"
    # It takes its place in the ranking all the same: the cut does not move.
    assert (chosen["PA1"]["rank"], chosen["PA2"]["rank"]) == (1, 2)
    assert chosen["PA3"]["shown"] is True


def test_score_weighs_readings_and_languages_alike() -> None:
    chosen = select(
        [
            found("PA1", "Lu", 2),
            found("PA2", "Traduit", 40),
            found("PA3", "Ni l'un", 1),
        ],
        views={"Lu": 50_000, "Traduit": 900, "Ni l'un": 100},
    )
    # First on one measure and second on the other, each way round: a tie,
    # which the identifier settles so that the order never changes.
    assert chosen["PA1"]["score"] == pytest.approx(chosen["PA2"]["score"])
    assert [chosen[key]["rank"] for key in ("PA1", "PA2", "PA3")] == [1, 2, 3]


def test_article_that_nobody_read_counts_for_nothing() -> None:
    chosen = select([found("PA1", "Lu", 3), found("PA2", "Jamais lu", 3)], {"Lu": 10})
    assert chosen["PA2"]["views"] == 0
    assert chosen["PA2"]["rank"] == 2


def test_excluded_kinds_are_not_shown() -> None:
    chosen = select(
        [found("PA1", "Abbesses (métro de Paris)", 20, excluded=True)],
        views={"Abbesses (métro de Paris)": 80_000},
    )
    assert chosen["PA1"]["shown"] is False
    assert chosen["PA1"]["reason"] is None
    assert chosen["PA1"]["rank"] is None
    assert chosen["PA1"]["left_out"] == "excluded_kind"
    # What was found is kept, to see what the exclusion costs.
    assert chosen["PA1"]["article"] == "Abbesses (métro de Paris)"


def test_review_shows_or_hides_a_monument_against_the_rule() -> None:
    lines = [
        found("PA1", "Un article", 5),
        found("PA2"),
        found("PA3", "Autre article", 5),
        found("PA4", "Abbesses (métro de Paris)", 20, excluded=True),
    ]
    views = {"Un article": 100, "Autre article": 50, "Abbesses (métro de Paris)": 9}
    decisions = {"PA1": "hide", "PA2": "show", "PA3": "show", "PA4": "show"}
    chosen = select(lines, views, decisions)
    assert (chosen["PA1"]["shown"], chosen["PA1"]["reason"]) == (False, None)
    assert chosen["PA1"]["left_out"] == "hidden_by_hand"
    assert (chosen["PA2"]["shown"], chosen["PA2"]["reason"]) == (True, "by_hand")
    # Shown by the rule already: the reason stays the article.
    assert (chosen["PA3"]["shown"], chosen["PA3"]["reason"]) == (True, "article")
    # A decision brings back a monument of an excluded kind, with its article.
    assert (chosen["PA4"]["shown"], chosen["PA4"]["reason"]) == (True, "by_hand")
    assert chosen["PA4"]["views"] == 9
    # Without an article there is nothing to measure: it comes last.
    assert chosen["PA2"]["views"] is None
    assert chosen["PA2"]["rank"] == 4


def test_best_known_neighbour_names_the_article_whatever_the_order() -> None:
    def row(qid: str, title: str, links: int) -> dict[str, str]:
        return {"item": ENTITY + qid, "title": title, "links": str(links)}

    rows = [
        row("Q1", "Musée Pasteur", 8),
        row("Q1", "Institut Pasteur", 70),
        row("Q2", "Collège Louis-le-Grand", 3),
        row("Q2", "Bibliothèque", 3),
    ]
    expected = {
        "Q1": Article("Institut Pasteur", 70),
        # As well known: the first in alphabetical order, to stay the same.
        "Q2": Article("Bibliothèque", 3),
    }
    assert selection.neighbour_articles(rows) == expected
    assert selection.neighbour_articles(rows[::-1]) == expected


def test_neighbours_are_asked_both_ways_in_batches() -> None:
    queries: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        query = httpx.QueryParams(request.content.decode())["query"]
        queries.append(query)
        title = "Occupant" if "wdt:P466" in query else "Located"
        binding = {
            "item": {"value": ENTITY + "Q1"},
            "other": {"value": ENTITY + "Q9"},
            "title": {"value": title},
            "links": {"value": "12"},
        }
        return httpx.Response(200, json={"results": {"bindings": [binding]}})

    qids = [f"Q{number}" for number in range(1, selection.BATCH_SIZE + 2)]
    pauses: list[float] = []
    with ingest_wikidata.make_client(httpx.MockTransport(answer)) as client:
        rows = selection.fetch_neighbours(client, qids, pause=pauses.append)

    # Two batches, each asked what it holds and what is held in it.
    assert len(queries) == 4
    assert "wd:Q1 wd:Q2" in queries[0]
    assert f"wd:Q{selection.BATCH_SIZE + 1}" in queries[2]
    assert "wd:Q1 " not in queries[2]
    assert [row["title"] for row in rows] == ["Occupant", "Located"] * 2
    assert len(pauses) == 4


def test_readings_of_a_year_are_added_up() -> None:
    paths: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.raw_path.decode())
        if "Jamais_lu" in paths[-1]:
            return httpx.Response(404, json={"title": "Not found."})
        months = [{"views": 1200}, {"views": 800}, {"views": 5}]
        return httpx.Response(200, json={"items": months})

    titles = ["Tour Eiffel", "Jamais lu", "Église Saint-Paul/Saint-Louis"]
    with web.make_client(transport=httpx.MockTransport(answer)) as client:
        views = selection.fetch_views(client, titles, pause=lambda seconds: None)

    assert views == {
        "Tour Eiffel": 2005,
        "Jamais lu": 0,
        "Église Saint-Paul/Saint-Louis": 2005,
    }
    assert "/fr.wikipedia/all-access/user/Tour_Eiffel/monthly/" in paths[0]
    # A slash in a title must not read as one more step of the address.
    assert "/%C3%89glise_Saint-Paul%2FSaint-Louis/monthly/" in paths[2]


def test_decisions_are_read_and_checked(tmp_path: Path) -> None:
    path = tmp_path / "selection_overrides.csv"
    assert selection.read_overrides(path) == {}
    header = "merimee_id,name,decision,note\n"
    path.write_text(header + "PA1,Archives nationales,show,\nPA2,Immeuble,hide,\n")
    assert selection.read_overrides(path) == {"PA1": "show", "PA2": "hide"}
    path.write_text(header + "PA1,Archives nationales,maybe,\n")
    with pytest.raises(ValueError, match="line 2: unknown decision 'maybe'"):
        selection.read_overrides(path)
    path.write_text(header + "PA1,A,show,\nPA1,A,hide,\n")
    with pytest.raises(ValueError, match="line 3: PA1 appears twice"):
        selection.read_overrides(path)


def test_real_notices_are_selected_offline(
    pipeline_tables: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    neighbours = tmp_path / "neighbours.json"
    neighbours.write_text(json.dumps({"neighbours": []}))
    pageviews = tmp_path / "pageviews.json"
    pageviews.write_text(json.dumps({"views": {"Église Saint-Eustache de Paris": 9}}))
    paths = {
        "MERIMEE_PARQUET": pipeline_tables / "merimee.parquet",
        "ENTITIES_PARQUET": pipeline_tables / "entities.parquet",
        "WIKIDATA_ITEMS_PARQUET": pipeline_tables / "wikidata_items.parquet",
        "VISIBILITY_PARQUET": pipeline_tables / "visibility.parquet",
        "NEIGHBOURS_SNAPSHOT": neighbours,
        "VIEWS_SNAPSHOT": pageviews,
        "OVERRIDES_CSV": tmp_path / "selection_overrides.csv",
        "SELECTION_PARQUET": tmp_path / "selection.parquet",
        "RANKING_CSV": tmp_path / "selection_ranking.csv",
    }
    for name, path in paths.items():
        monkeypatch.setattr(selection, name, path)

    def no_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("the offline run must not open a connection")

    monkeypatch.setattr(ingest_wikidata, "make_client", no_network)
    monkeypatch.setattr(web, "make_client", no_network)
    assert selection.main(["--offline"]) == 0

    chosen = pd.read_parquet(tmp_path / "selection.parquet").set_index("merimee_id")
    # Saint-Eustache has its article; the café of rue Etienne-Marcel has none.
    assert chosen.loc["PA00085795", "shown"]
    assert chosen.loc["PA00085795", "reason"] == "article"
    assert not chosen.loc["PA00085786", "shown"]
    # The entrance of a metro station is left out, article or not.
    assert not chosen.loc["PA00086579", "shown"]
    shown = int(chosen["shown"].sum())
    assert selection.summarize(chosen.reset_index())["shown"] == shown
    ranking = pd.read_csv(tmp_path / "selection_ranking.csv")
    assert list(ranking["rank"]) == list(range(1, len(ranking) + 1))
    assert set(ranking.loc[ranking["shown"], "merimee_id"]) == set(
        chosen.index[chosen["shown"]]
    )
    assert ranking["name"].notna().all()
