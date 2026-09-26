"""SQLite persistence: extraction/embedding cache, investigation state, hash-chained audit (Req 9)."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

GENESIS = "0" * 64


def canonical(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def cache_key(model_id: str, prompt_version: str, text: str) -> str:
    return sha256(canonical([model_id, prompt_version, text]))


def event_hash(prev_hash: str, ts: str, etype: str, actor: str, payload: dict) -> str:
    return sha256(prev_hash + canonical({"ts": ts, "type": etype, "actor": actor, "payload": payload}))


class Store:
    def __init__(self, path: str | Path = ":memory:") -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript("""
                CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, kind TEXT, value TEXT, created TEXT);
                CREATE TABLE IF NOT EXISTS investigations (signal_id TEXT PRIMARY KEY, state TEXT);
                CREATE TABLE IF NOT EXISTS audit (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, type TEXT, actor TEXT,
                    payload TEXT, prev_hash TEXT, hash TEXT);
            """)
            self._db.commit()

    # ------------------------------------------------------------- cache
    def cache_get(self, key: str) -> object | None:
        with self._lock:
            row = self._db.execute("SELECT value FROM cache WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def cache_put(self, key: str, kind: str, value: object) -> None:
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO cache VALUES (?,?,?,?)",
                             (key, kind, json.dumps(value), _now()))
            self._db.commit()

    # ------------------------------------------------------ investigations
    def save_investigation(self, signal_id: str, state: dict) -> None:
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO investigations VALUES (?,?)", (signal_id, json.dumps(state)))
            self._db.commit()

    def load_investigation(self, signal_id: str) -> dict | None:
        with self._lock:
            row = self._db.execute("SELECT state FROM investigations WHERE signal_id=?", (signal_id,)).fetchone()
        return json.loads(row[0]) if row else None

    # --------------------------------------------------------------- audit
    def audit(self, etype: str, actor: str, payload: dict) -> dict:
        with self._lock:
            row = self._db.execute("SELECT hash FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
            prev = row[0] if row else GENESIS
            ts = _now()
            payload = json.loads(canonical(payload))  # normalise so re-hashing is stable
            h = event_hash(prev, ts, etype, actor, payload)
            cur = self._db.execute("INSERT INTO audit (ts,type,actor,payload,prev_hash,hash) VALUES (?,?,?,?,?,?)",
                                   (ts, etype, actor, canonical(payload), prev, h))
            self._db.commit()
            return {"seq": cur.lastrowid, "ts": ts, "type": etype, "actor": actor, "hash": h}

    def audit_events(self, limit: int = 500) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT seq,ts,type,actor,payload,prev_hash,hash FROM audit ORDER BY seq DESC LIMIT ?", (limit,)).fetchall()
        return [{"seq": r[0], "ts": r[1], "type": r[2], "actor": r[3], "payload": json.loads(r[4]),
                 "prev_hash": r[5], "hash": r[6]} for r in rows]

    def verify_chain(self) -> dict:
        with self._lock:
            rows = self._db.execute("SELECT seq,ts,type,actor,payload,prev_hash,hash FROM audit ORDER BY seq").fetchall()
        prev = GENESIS
        for seq, ts, etype, actor, payload, prev_hash, h in rows:
            if prev_hash != prev or event_hash(prev, ts, etype, actor, json.loads(payload)) != h:
                return {"valid": False, "events": len(rows), "broken_at_seq": seq}
            prev = h
        return {"valid": True, "events": len(rows), "head": prev}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")
