import httpx
import pytest

from lutece_pipeline import web

URL = "https://example.org/api"


def test_client_identifies_itself() -> None:
    with web.make_client(accept="application/json") as client:
        assert client.headers["User-Agent"] == web.USER_AGENT
        assert "tessotnathan75@gmail.com" in web.USER_AGENT
        assert client.headers["Accept"] == "application/json"


def test_post_is_retried_after_transient_errors() -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    answers = iter(
        [
            fail,
            lambda request: httpx.Response(502),
            lambda request: httpx.Response(429, headers={"retry-after": "7"}),
            lambda request: httpx.Response(200, json={"ok": True}),
        ]
    )
    pauses: list[float] = []
    transport = httpx.MockTransport(lambda request: next(answers)(request))

    with web.make_client(transport=transport) as client:
        response = web.post_form(client, URL, {"q": "1"}, pause=pauses.append)

    assert response.json() == {"ok": True}
    # Exponential delay, except when the server says how long to wait.
    assert pauses == [2.0, 4.0, 7.0]


def test_post_gives_up_after_too_many_failures() -> None:
    requests: list[httpx.Request] = []
    pauses: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(503)

    with (
        web.make_client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(RuntimeError, match="HTTP 503"),
    ):
        web.post_form(client, URL, {"q": "1"}, pause=pauses.append)

    assert len(requests) == web.MAX_ATTEMPTS
    assert pauses == [2.0, 4.0, 8.0, 16.0]


def test_retry_delay_can_start_higher_for_slow_services() -> None:
    pauses: list[float] = []
    transport = httpx.MockTransport(lambda request: httpx.Response(504))

    with (
        web.make_client(transport=transport) as client,
        pytest.raises(RuntimeError, match="HTTP 504"),
    ):
        web.post_form(client, URL, {"q": "1"}, pause=pauses.append, base_delay=15.0)

    assert pauses == [15.0, 30.0, 60.0, 120.0]


def test_client_errors_are_not_retried() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(400, request=request)

    with (
        web.make_client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(httpx.HTTPStatusError),
    ):
        web.post_form(client, URL, {"q": "1"}, pause=lambda seconds: None)

    assert len(requests) == 1
