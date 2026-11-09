import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from lutece_pipeline import story_files
from lutece_pipeline import write_stories as stories

PLACE = {
    "key": "PA00086250",
    "title": "Cathédrale Notre-Dame",
    "category": "cathédrale",
    "century": 12,
    "architects": '["Viollet-le-Duc"]',
    "arrondissement": 4,
    "protection": "classé",
}
NOTICE = {"history_raw": " Construite à partir de 1163. ", "description_raw": None}
ARTICLE = {
    "text": "Notre-Dame est une cathédrale.",
    "page_title": "Cathédrale Notre-Dame de Paris",
    "revision": 7,
}
DRAFT = {
    "enough": True,
    "summary": "Une cathédrale gothique.",
    "story": "Commencée en 1163.\n\nRestaurée par Viollet-le-Duc.",
    "did_you_know": "Sa flèche est récente.",
    "sources_used": ["wikipedia", "merimee"],
}


def test_a_long_article_is_cut_at_a_paragraph() -> None:
    text = "a" * 10 + "\n\n" + "b" * 10 + "\n\n" + "c" * 10
    assert stories.shorten(text, limit=25) == "a" * 10 + "\n\n" + "b" * 10
    assert stories.shorten("court", limit=25) == "court"


def test_the_model_is_given_the_facts_and_the_sources() -> None:
    sources = stories.build_sources(PLACE, NOTICE, ARTICLE)
    assert sources == {
        "merimee": "Historique : Construite à partir de 1163.",
        "wikipedia": "Notre-Dame est une cathédrale.",
    }
    message = stories.build_message(PLACE, sources)
    assert message.startswith("Lieu : Cathédrale Notre-Dame\nGenre : cathédrale")
    assert "Architectes : Viollet-le-Duc" in message
    assert (
        '<source id="merimee">\nHistorique : Construite à partir de 1163.\n</source>'
        in message
    )
    # A place without notice nor article has nothing to draw from.
    assert stories.build_sources(PLACE, None, None) == {}


def test_a_draft_is_asked_again_only_when_what_is_sent_changes() -> None:
    first = stories.fingerprint("message")
    assert stories.fingerprint("message") == first
    assert stories.fingerprint("autre message") != first


def test_a_review_file_is_read_back_as_written() -> None:
    answer = {"draft": DRAFT, "model": "claude-opus-5-5", "drafted_at": "2026-11-10"}
    text = stories.render_story(PLACE, answer, ARTICLE)
    assert "statut: à relire" in text
    assert "sources: merimee, wikipedia" in text
    assert "revision: 7" in text
    read = story_files.parse_story(text, "PA00086250.md")
    assert read == {
        "key": "PA00086250",
        "status": "à relire",
        "sources": ["merimee", "wikipedia"],
        "wikipedia": "Cathédrale Notre-Dame de Paris",
        "revision": 7,
        "summary": "Une cathédrale gothique.",
        "story": "Commencée en 1163.\n\nRestaurée par Viollet-le-Duc.",
        "did_you_know": "Sa flèche est récente.",
    }


def test_a_place_without_enough_sources_stays_to_enrich() -> None:
    thin = {
        **DRAFT,
        "enough": False,
        "summary": "",
        "story": "",
        "did_you_know": "",
        "sources_used": [],
    }
    text = stories.render_story(
        PLACE, {"draft": thin, "model": "m", "drafted_at": "d"}, None
    )
    read = story_files.parse_story(text, "x.md")
    assert read["status"] == "à enrichir"
    assert read["story"] is None


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("pas d'en-tête", "no header"),
        ("---\ncle: PA1\nstatut: fini\n---\n", "statut"),
        ("---\ncle: PA1\nstatut: relu\n---\n## En bref\n\nCourt.\n", "needs"),
        ("---\ncle: PA1\nstatut: relu\n---\n## Autre\n\nTexte.\n", "unknown section"),
    ],
)
def test_a_wrong_review_file_is_refused(text: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        story_files.parse_story(text, "x.md")


def result(
    key: str, draft: dict[str, object] | None, kind: str = "succeeded"
) -> SimpleNamespace:
    content = (
        [] if draft is None else [SimpleNamespace(type="text", text=json.dumps(draft))]
    )
    message = SimpleNamespace(
        stop_reason="end_turn" if draft else "refusal",
        content=content,
        usage=SimpleNamespace(input_tokens=1000, output_tokens=500),
    )
    return SimpleNamespace(
        custom_id=key, result=SimpleNamespace(type=kind, message=message)
    )


class FakeBatches:
    def __init__(self, results: list[SimpleNamespace]) -> None:
        self.results_given = results
        self.asked: list[object] = []
        self.polls = 0

    def create(self, requests: list[object]) -> SimpleNamespace:
        self.asked = requests
        return SimpleNamespace(id="batch-1", processing_status="in_progress")

    def retrieve(self, batch_id: str) -> SimpleNamespace:
        self.polls += 1
        counts = SimpleNamespace(
            processing=0, succeeded=len(self.results_given), errored=0
        )
        return SimpleNamespace(
            id=batch_id, processing_status="ended", request_counts=counts
        )

    def results(self, batch_id: str) -> list[SimpleNamespace]:
        return self.results_given


def test_a_batch_is_sent_waited_for_and_kept(tmp_path: Path) -> None:
    batches = FakeBatches([result("PA1", DRAFT), result("PA2", None)])
    client = SimpleNamespace(messages=SimpleNamespace(batches=batches))
    answers = tmp_path / "answers.jsonl"
    lines = stories.draft(
        client, {"PA1": "un", "PA2": "deux"}, answers, pause=lambda _: None
    )

    assert [request["custom_id"] for request in batches.asked] == ["PA1", "PA2"]
    params = batches.asked[0]["params"]
    assert params["model"] == stories.MODEL
    assert params["output_config"]["format"]["schema"] == stories.ANSWER_SCHEMA
    assert batches.polls == 1
    assert lines[0]["draft"] == DRAFT
    # A refusal is kept too, without a draft.
    assert "draft" not in lines[1] and lines[1]["stop_reason"] == "refusal"
    kept = stories.read_answers(answers)
    assert kept[("PA1", stories.fingerprint("un"))]["usage"] == {
        "input_tokens": 1000,
        "output_tokens": 500,
    }
