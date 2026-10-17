"""Checking the public releases-only repo for a newer version (spec §10)."""
from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass
from typing import Callable

from . import config


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    url: str


def parse_version(tag: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", tag))


def http_fetch(url: str) -> str | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": config.UA, "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.read().decode("utf-8")
    except Exception:
        return None


def check_latest(repo: str, current: str, fetch: Callable[[str], str | None] = http_fetch) -> UpdateInfo | None:
    if not repo:
        return None
    body = fetch(f"https://api.github.com/repos/{repo}/releases/latest")
    if not body:
        return None
    try:
        data = json.loads(body)
        tag, url = data["tag_name"], data["html_url"]
    except (ValueError, KeyError, TypeError):
        return None
    if parse_version(tag) > parse_version(current):
        return UpdateInfo(tag.lstrip("vV"), url)
    return None
