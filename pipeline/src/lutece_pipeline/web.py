"""HTTP helpers shared by the steps that query public web services."""

import logging
import time
from collections.abc import Callable, Collection, Mapping

import httpx

logger = logging.getLogger(__name__)

# Wikimedia and OpenStreetMap ask automated clients to identify themselves with a contact.
USER_AGENT = "LutecePipeline/0.1 (tessotnathan75@gmail.com)"
MAX_ATTEMPTS = 5

type Pause = Callable[[float], None]


def make_client(
    *,
    accept: str | None = None,
    timeout: float = 120.0,
    transport: httpx.BaseTransport | None = None,
) -> httpx.Client:
    """Create an HTTP client that identifies the pipeline to the service."""
    headers = {"User-Agent": USER_AGENT}
    if accept:
        headers["Accept"] = accept
    return httpx.Client(transport=transport, headers=headers, timeout=timeout)


def post_form(
    client: httpx.Client,
    url: str,
    form: Mapping[str, str],
    *,
    pause: Pause = time.sleep,
    base_delay: float = 2.0,
) -> httpx.Response:
    """POST a form and return the successful response.

    Public endpoints regularly answer 429 or 5xx for a while, so those responses
    and network errors are retried. The delay starts at base_delay seconds and
    doubles after each failure, unless the server says how long to wait.
    """
    return _send(lambda: client.post(url, data=dict(form)), url, pause, base_delay)


def get(
    client: httpx.Client,
    url: str,
    *,
    pause: Pause = time.sleep,
    base_delay: float = 2.0,
    accepted: Collection[int] = (),
) -> httpx.Response:
    """GET a page and return the response, retried like a posted form.

    `accepted` lists the error statuses that are an answer in themselves, such
    as the 404 of a service that has nothing to say about a page.
    """
    return _send(lambda: client.get(url), url, pause, base_delay, accepted)


def _send(
    request: Callable[[], httpx.Response],
    url: str,
    pause: Pause,
    base_delay: float,
    accepted: Collection[int] = (),
) -> httpx.Response:
    reason = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        delay = base_delay * 2 ** (attempt - 1)
        try:
            response = request()
        except httpx.TransportError as error:
            reason = repr(error)
        else:
            if response.status_code == httpx.codes.OK:
                return response
            if response.status_code in accepted:
                return response
            if response.status_code != 429 and response.status_code < 500:
                response.raise_for_status()
            reason = f"HTTP {response.status_code}"
            retry_after = response.headers.get("retry-after", "")
            if retry_after.isdigit():
                delay = float(retry_after)
        if attempt < MAX_ATTEMPTS:
            logger.warning("%s failed (%s), retrying in %.0f s", url, reason, delay)
            pause(delay)
    raise RuntimeError(f"{url} failed after {MAX_ATTEMPTS} attempts: {reason}")
