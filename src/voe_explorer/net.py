"""HTTP with retries; every attempt is reported so the health monitor sees it."""
from __future__ import annotations

import http.cookiejar
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from . import config


@dataclass(frozen=True)
class FetchResult:
    url: str
    at: datetime
    status: int | None
    elapsed_s: float
    body: str | None
    error: str | None

    @property
    def ok(self) -> bool:
        return self.status == 200 and self.body is not None


class Net:
    def __init__(self, opener=None, on_attempt: Callable[[FetchResult], None] | None = None,
                 sleep: Callable[[float], None] = time.sleep, base_url: str = config.BASE_URL):
        self.opener = opener or urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.on_attempt = on_attempt
        self.sleep = sleep
        self.base_url = base_url

    def get(self, path: str) -> FetchResult:
        return self._request(path, None)

    def post(self, path: str, form: dict[str, str]) -> FetchResult:
        return self._request(path, urllib.parse.urlencode(form).encode("ascii"))

    def _request(self, path: str, data: bytes | None) -> FetchResult:
        url = path if path.startswith("http") else self.base_url + path
        result = None
        for attempt in range(config.RETRIES):
            if attempt:
                self.sleep(config.RETRY_PAUSE_S)
            result = self._once(url, data)
            if self.on_attempt:
                self.on_attempt(result)
            if result.ok or (result.status is not None and result.status < 500):
                break
        return result

    def _once(self, url: str, data: bytes | None) -> FetchResult:
        req = urllib.request.Request(url, data=data, headers={
            "User-Agent": config.UA, "X-Requested-With": "XMLHttpRequest"})
        at, t0 = datetime.now(), time.monotonic()
        try:
            with self.opener.open(req, timeout=config.TIMEOUT_S) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                return FetchResult(url, at, resp.status, time.monotonic() - t0, body, None)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace") if e.fp else None
            return FetchResult(url, at, e.code, time.monotonic() - t0, body, f"HTTP {e.code}")
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            return FetchResult(url, at, None, time.monotonic() - t0, None, repr(e))
