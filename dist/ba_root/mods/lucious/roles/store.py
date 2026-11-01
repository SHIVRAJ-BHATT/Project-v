# lucious/roles/store.py
"""Timed and permanent role grants (SQLite) with an in-memory cache."""
from __future__ import annotations

import os
import sqlite3
import threading
import time

from lucious.config import DATA_DIR

DB_PATH = os.path.join(DATA_DIR, 'roles.db')
_conn: sqlite3.Connection | None = None
_lock = threading.RLock()
_cache: dict[str, dict[str, float | None]] = {}


def open_db() -> None:
    global _conn
    with _lock:
        if _conn is not None:
            return
        os.makedirs(DATA_DIR, exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False,
                                isolation_level=None)
        _conn.execute('PRAGMA journal_mode=WAL')
        _conn.execute('CREATE TABLE IF NOT EXISTS grants(account TEXT NOT NULL,'
                      ' role TEXT NOT NULL, expires REAL, by TEXT, created REAL,'
                      ' PRIMARY KEY(account, role))')
        _conn.execute('DELETE FROM grants WHERE expires IS NOT NULL '
                      'AND expires<=?', (time.time(),))
        _cache.clear()
        for acc, role, exp in _conn.execute(
                'SELECT account, role, expires FROM grants'):
            _cache.setdefault(acc, {})[role] = exp


def close_db() -> None:
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
            _conn = None


def grants_of(account: str) -> dict[str, float | None]:
    if _conn is None:
        open_db()
    now = time.time()
    return {r: e for r, e in _cache.get(account, {}).items()
            if e is None or e > now}


def members_of(role: str) -> list[str]:
    if _conn is None:
        open_db()
    return [a for a in list(_cache) if role in grants_of(a)]


def grant(account: str, role: str, seconds: float | None = None,
          by: str = 'system') -> float | None:
    """Grant or extend. A permanent grant stays permanent."""
    if _conn is None:
        open_db()
    now = time.time()
    current = grants_of(account)
    if role in current and current[role] is None:
        return None
    base = current.get(role) or now
    expires = None if seconds is None else base + seconds
    with _lock:
        _conn.execute(
            'INSERT INTO grants(account,role,expires,by,created) '
            'VALUES(?,?,?,?,?) ON CONFLICT(account,role) DO UPDATE SET '
            'expires=excluded.expires, by=excluded.by',
            (account, role, expires, by, now))
    _cache.setdefault(account, {})[role] = expires
    return expires


def revoke(account: str, role: str) -> bool:
    if _conn is None:
        open_db()
    with _lock:
        cur = _conn.execute('DELETE FROM grants WHERE account=? AND role=?',
                            (account, role))
    _cache.get(account, {}).pop(role, None)
    return cur.rowcount > 0


def purge_role(role: str) -> None:
    for acc in list(_cache):
        revoke(acc, role)
