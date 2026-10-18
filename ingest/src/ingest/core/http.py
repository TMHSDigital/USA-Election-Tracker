"""HTTP fetching with retries, backoff, and an offline fixture mode for tests."""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from datetime import datetime
from pathlib import Path
from typing import Protocol

import httpx

log = logging.getLogger(__name__)

USER_AGENT = (
    "USA-Election-Tracker/0.1 (+https://github.com/TMHSDigital/USA-Election-Tracker)"
)
RETRY_STATUS = {408, 425, 429, 500, 502, 503, 504}


class FetchError(RuntimeError):
    pass


@dataclass
class Response:
    url: str
    status: int
    content: bytes
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return self.content.decode("utf-8-sig", errors="replace")

    @property
    def last_modified(self) -> datetime | None:
        value = self.headers.get("last-modified")
        if not value:
            return None
        try:
            return parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None


class Http(Protocol):
    def get(self, url: str, params: dict[str, str] | None = None) -> Response: ...


class LiveHttp:
    """Real network client. Retries transient failures with jittered exponential backoff."""

    def __init__(
        self,
        attempts: int = 5,
        base_delay: float = 2.0,
        max_delay: float = 60.0,
        timeout: float = 120.0,
    ) -> None:
        self.attempts = attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )

    def get(self, url: str, params: dict[str, str] | None = None) -> Response:
        last_error: str = ""
        for attempt in range(1, self.attempts + 1):
            try:
                r = self.client.get(url, params=params)
            except httpx.HTTPError as e:
                last_error = f"{type(e).__name__}: {e}"
                retry_after = None
            else:
                if r.status_code < 400:
                    return Response(
                        url=str(r.url),
                        status=r.status_code,
                        content=r.content,
                        headers={k.lower(): v for k, v in r.headers.items()},
                    )
                last_error = f"HTTP {r.status_code}"
                if r.status_code not in RETRY_STATUS:
                    break
                retry_after = _retry_after_seconds(r.headers.get("retry-after"))
            if attempt == self.attempts:
                break
            delay = retry_after or min(self.max_delay, self.base_delay * 2 ** (attempt - 1))
            delay += random.uniform(0, delay / 4)
            log.warning("fetch %s failed (%s); retry %d in %.1fs", _redact(url), last_error,
                        attempt, delay)
            time.sleep(delay)
        raise FetchError(f"GET {_redact(url)} failed: {last_error}")


class FixtureHttp:
    """Serves saved responses from a directory. Used by adapter tests and offline builds.

    `routes` maps a URL prefix to a fixture file name relative to `root`.
    Unmatched URLs raise FetchError, which exercises the failure path.
    """

    def __init__(self, root: Path, routes: dict[str, str]) -> None:
        self.root = root
        self.routes = routes
        self.requested: list[str] = []

    def get(self, url: str, params: dict[str, str] | None = None) -> Response:
        self.requested.append(url)
        for prefix, name in self.routes.items():
            if url.startswith(prefix):
                path = self.root / name
                return Response(
                    url=url,
                    status=200,
                    content=path.read_bytes(),
                    headers={"last-modified": "Thu, 01 Oct 2026 00:00:00 GMT"},
                )
        raise FetchError(f"no fixture for {url}")


def _retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return min(300.0, float(value))
    except ValueError:
        return None


def _redact(url: str) -> str:
    """Never log API keys."""
    if "api_key=" not in url and "key=" not in url:
        return url
    import re

    return re.sub(r"((?:api_)?key=)[^&]+", r"\1REDACTED", url)
