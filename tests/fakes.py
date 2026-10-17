"""Test doubles shared by several test modules."""
from __future__ import annotations

import io
import urllib.error


class FakeResponse:
    def __init__(self, status: int, body: str):
        self.status = status
        self._body = body.encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeOpener:
    """Returns queued (status, body) answers in order; records requests."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.requests = []

    def open(self, request, timeout=None):
        self.requests.append(request)
        answer = self.answers.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        status, body = answer
        if status >= 400:
            raise urllib.error.HTTPError(request.full_url, status, "err", {}, io.BytesIO(body.encode("utf-8")))
        return FakeResponse(status, body)


def ac_body(*items: tuple[str, str], method: str = "read_street") -> str:
    import json
    return json.dumps([
        {"value": v, "label": f'<div class="change_api_autocomplit" data-method="{method}" data-id="{i}">{v}</div>'}
        for v, i in items
    ])
