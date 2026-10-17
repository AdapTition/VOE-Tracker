"""Local persistence in %APPDATA%\\VOE Explorer (spec §10)."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path

from .models import SavedAddress
from .net import FetchResult

KEEP_CHANGES = 10
KEEP_PROBE_DAYS = 30


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return default


class AddressStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self._items = [SavedAddress(**d) for d in _read_json(path, [])]

    def _save(self) -> None:
        _write_json(self.path, [asdict(a) for a in self._items])

    def all(self) -> list[SavedAddress]:
        with self._lock:
            return list(self._items)

    def get(self, id: str) -> SavedAddress | None:
        return next((a for a in self.all() if a.id == id), None)

    def add(self, addr: SavedAddress) -> None:
        with self._lock:
            self._items.append(addr)
            self._save()

    def rename(self, id: str, label: str) -> None:
        with self._lock:
            for a in self._items:
                if a.id == id:
                    a.label = label
            self._save()

    def move(self, id: str, delta: int) -> None:
        with self._lock:
            i = next((n for n, a in enumerate(self._items) if a.id == id), None)
            if i is None:
                return
            j = max(0, min(len(self._items) - 1, i + delta))
            self._items.insert(j, self._items.pop(i))
            self._save()

    def remove(self, id: str) -> None:
        with self._lock:
            self._items = [a for a in self._items if a.id != id]
            self._save()


class MemoryStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self._data: dict = _read_json(path, {})

    def get(self, key: str) -> dict | None:
        with self._lock:
            return self._data.get(key)

    def put(self, key: str, value: dict) -> None:
        with self._lock:
            self._data[key] = value
            _write_json(self.path, self._data)


@dataclass(frozen=True)
class StoredResponse:
    id: int
    address_id: str | None
    kind: str
    at: datetime
    status: int | None
    elapsed_s: float
    url: str
    body: str | None
    content_hash: str | None


class Db:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._con = sqlite3.connect(path, check_same_thread=False)
        self._con.executescript("""
            CREATE TABLE IF NOT EXISTS probes (at TEXT, kind TEXT, status INTEGER, elapsed REAL, state TEXT);
            CREATE INDEX IF NOT EXISTS probes_at ON probes(at);
            CREATE TABLE IF NOT EXISTS responses (
                id INTEGER PRIMARY KEY AUTOINCREMENT, address_id TEXT, kind TEXT, at TEXT,
                status INTEGER, elapsed REAL, url TEXT, body TEXT, content_hash TEXT);
        """)
        self._con.commit()

    def add_probe(self, at: datetime, kind: str, status: int | None, elapsed_s: float, state: str) -> None:
        with self._lock:
            self._con.execute("INSERT INTO probes VALUES (?,?,?,?,?)", (at.isoformat(), kind, status, elapsed_s, state))
            self._con.commit()

    def probes_between(self, start: datetime, end: datetime) -> list[tuple[datetime, str, float]]:
        with self._lock:
            rows = self._con.execute(
                "SELECT at, state, elapsed FROM probes WHERE at >= ? AND at <= ? ORDER BY at",
                (start.isoformat(), end.isoformat())).fetchall()
        return [(datetime.fromisoformat(a), s, e) for a, s, e in rows]

    def add_response(self, address_id: str | None, kind: str, result: FetchResult, content_hash: str | None) -> int:
        with self._lock:
            cur = self._con.execute(
                "INSERT INTO responses (address_id, kind, at, status, elapsed, url, body, content_hash) VALUES (?,?,?,?,?,?,?,?)",
                (address_id, kind, result.at.isoformat(), result.status, result.elapsed_s, result.url, result.body, content_hash))
            rid = cur.lastrowid
            self._prune(address_id, kind)
            self._con.commit()
            return rid

    def _prune(self, address_id: str | None, kind: str) -> None:
        rows = self._con.execute(
            "SELECT id, content_hash FROM responses WHERE address_id IS ? AND kind = ? ORDER BY id",
            (address_id, kind)).fetchall()
        if not rows:
            return
        changes = [rid for n, (rid, h) in enumerate(rows) if n == 0 or h != rows[n - 1][1]]
        keep = set(changes[-KEEP_CHANGES:]) | {rows[-1][0]}
        drop = [rid for rid, _ in rows if rid not in keep]
        if drop:
            self._con.executemany("DELETE FROM responses WHERE id = ?", [(d,) for d in drop])

    def delete_responses(self, address_id: str) -> None:
        with self._lock:
            self._con.execute("DELETE FROM responses WHERE address_id = ?", (address_id,))
            self._con.commit()

    def prune(self, now: datetime, keep_address_ids: set[str], keep_days: int = KEEP_PROBE_DAYS) -> None:
        """Drop probes older than keep_days and responses of addresses that are gone."""
        with self._lock:
            self._con.execute("DELETE FROM probes WHERE at < ?", ((now - timedelta(days=keep_days)).isoformat(),))
            ids = list(keep_address_ids)
            self._con.execute(
                f"DELETE FROM responses WHERE address_id IS NOT NULL AND address_id NOT IN ({','.join('?' * len(ids))})",
                ids)
            self._con.commit()
            self._con.execute("VACUUM")

    def _row(self, r) -> StoredResponse:
        return StoredResponse(r[0], r[1], r[2], datetime.fromisoformat(r[3]), r[4], r[5], r[6], r[7], r[8])

    def responses(self, address_id: str | None, kind: str) -> list[StoredResponse]:
        with self._lock:
            rows = self._con.execute(
                "SELECT id, address_id, kind, at, status, elapsed, url, body, content_hash FROM responses "
                "WHERE address_id IS ? AND kind = ? ORDER BY id DESC", (address_id, kind)).fetchall()
        return [self._row(r) for r in rows]

    def response(self, id: int) -> StoredResponse | None:
        with self._lock:
            r = self._con.execute(
                "SELECT id, address_id, kind, at, status, elapsed, url, body, content_hash FROM responses WHERE id = ?",
                (id,)).fetchone()
        return self._row(r) if r else None


def save_sample(dir: Path, address_id: str | None, raw: str, note: str) -> Path:
    dir.mkdir(parents=True, exist_ok=True)
    path = dir / f"{datetime.now():%Y%m%d-%H%M%S-%f}_{address_id or 'none'}.json"
    path.write_text(json.dumps({"note": note, "raw": raw}, ensure_ascii=False, indent=1), encoding="utf-8")
    return path
