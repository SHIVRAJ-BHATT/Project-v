"""SQLite (WAL) storage with in-memory caches for hot-path checks."""
from __future__ import annotations

import logging
import os
import sqlite3
import threading
import time

from lucious.config import DATA_DIR

log = logging.getLogger('lucious')
DB_PATH = os.path.join(DATA_DIR, 'security.db')

_conn: sqlite3.Connection | None = None
_lock = threading.RLock()
_bans: dict[tuple[str, str], dict] = {}
_mutes: dict[str, dict] = {}

SCHEMA = """
CREATE TABLE IF NOT EXISTS bans(id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL, value TEXT NOT NULL, reason TEXT, by TEXT,
  created REAL, expires REAL, active INTEGER DEFAULT 1);
CREATE INDEX IF NOT EXISTS idx_bans ON bans(kind, value, active);
CREATE TABLE IF NOT EXISTS mutes(account TEXT PRIMARY KEY, reason TEXT,
  by TEXT, created REAL, expires REAL);
CREATE TABLE IF NOT EXISTS warns(id INTEGER PRIMARY KEY AUTOINCREMENT,
  account TEXT, reason TEXT, by TEXT, created REAL);
CREATE TABLE IF NOT EXISTS players(account TEXT PRIMARY KEY, last_name TEXT,
  first_seen REAL, last_seen REAL, joins INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS names(account TEXT, name TEXT, seen REAL,
  PRIMARY KEY(account, name));
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL, actor TEXT, action TEXT, target TEXT, detail TEXT);
"""


def open_db() -> None:
    global _conn
    os.makedirs(DATA_DIR, exist_ok=True)
    with _lock:
        if _conn is not None:
            return
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False,
                                isolation_level=None)
        _conn.row_factory = sqlite3.Row
        _conn.execute('PRAGMA journal_mode=WAL')
        _conn.execute('PRAGMA synchronous=NORMAL')
        _conn.executescript(SCHEMA)
    _reload_cache()


def close_db() -> None:
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
            _conn = None


def _exec(sql: str, args: tuple = ()):
    with _lock:
        if _conn is None:
            raise RuntimeError('security db not open')
        return _conn.execute(sql, args)


def _rows(sql: str, args: tuple = ()) -> list[dict]:
    with _lock:
        return [dict(r) for r in _exec(sql, args).fetchall()]


def _expired(row: dict) -> bool:
    return row.get('expires') is not None and row['expires'] <= time.time()


def _reload_cache() -> None:
    now = time.time()
    _exec('UPDATE bans SET active=0 WHERE active=1 AND expires IS NOT NULL '
          'AND expires<=?', (now,))
    _exec('DELETE FROM mutes WHERE expires IS NOT NULL AND expires<=?', (now,))
    _bans.clear()
    for r in _rows('SELECT * FROM bans WHERE active=1'):
        _bans[(r['kind'], r['value'])] = r
    _mutes.clear()
    for r in _rows('SELECT * FROM mutes'):
        _mutes[r['account']] = r


# ---- bans --------------------------------------------------------------
def find_ban(kind: str, value: str | None) -> dict | None:
    if not value:
        return None
    row = _bans.get((kind, value))
    if row and _expired(row):
        _exec('UPDATE bans SET active=0 WHERE id=?', (row['id'],))
        _bans.pop((kind, value), None)
        return None
    return row


def name_ban_patterns() -> list[dict]:
    return [r for (k, _), r in list(_bans.items())
            if k == 'name' and not _expired(r)]


def add_ban(kind: str, value: str, reason: str, by: str,
            seconds: float | None) -> dict:
    now = time.time()
    expires = now + seconds if seconds else None
    _exec('UPDATE bans SET active=0 WHERE kind=? AND value=? AND active=1',
          (kind, value))
    cur = _exec('INSERT INTO bans(kind,value,reason,by,created,expires,active)'
                ' VALUES(?,?,?,?,?,?,1)',
                (kind, value, reason, by, now, expires))
    row = {'id': cur.lastrowid, 'kind': kind, 'value': value,
           'reason': reason, 'by': by, 'created': now, 'expires': expires,
           'active': 1}
    _bans[(kind, value)] = row
    return row


def remove_ban(kind: str, value: str) -> bool:
    cur = _exec('UPDATE bans SET active=0 WHERE kind=? AND value=? '
                'AND active=1', (kind, value))
    _bans.pop((kind, value), None)
    return cur.rowcount > 0


def remove_ban_id(ban_id: int) -> dict | None:
    for key, row in list(_bans.items()):
        if row['id'] == ban_id:
            _exec('UPDATE bans SET active=0 WHERE id=?', (ban_id,))
            _bans.pop(key, None)
            return row
    return None


def active_bans(limit: int = 10) -> list[dict]:
    rows = [r for r in _bans.values() if not _expired(r)]
    return sorted(rows, key=lambda r: r['created'], reverse=True)[:limit]


# ---- mutes -------------------------------------------------------------
def add_mute(account: str, reason: str, by: str,
             seconds: float | None) -> None:
    now = time.time()
    expires = now + seconds if seconds else None
    _exec('INSERT OR REPLACE INTO mutes(account,reason,by,created,expires) '
          'VALUES(?,?,?,?,?)', (account, reason, by, now, expires))
    _mutes[account] = {'account': account, 'reason': reason, 'by': by,
                       'created': now, 'expires': expires}


def get_mute(account: str | None) -> dict | None:
    if not account:
        return None
    row = _mutes.get(account)
    if row and _expired(row):
        remove_mute(account)
        return None
    return row


def remove_mute(account: str) -> bool:
    cur = _exec('DELETE FROM mutes WHERE account=?', (account,))
    _mutes.pop(account, None)
    return cur.rowcount > 0


# ---- warns -------------------------------------------------------------
def add_warn(account: str, reason: str, by: str) -> int:
    _exec('INSERT INTO warns(account,reason,by,created) VALUES(?,?,?,?)',
          (account, reason, by, time.time()))
    return count_warns(account)


def count_warns(account: str) -> int:
    return _exec('SELECT COUNT(*) FROM warns WHERE account=?',
                 (account,)).fetchone()[0]


def warns_of(account: str, limit: int = 5) -> list[dict]:
    return _rows('SELECT * FROM warns WHERE account=? ORDER BY id DESC '
                 'LIMIT ?', (account, limit))


def clear_warns(account: str) -> None:
    _exec('DELETE FROM warns WHERE account=?', (account,))


# ---- players / names ---------------------------------------------------
def touch_player(account: str, name: str) -> None:
    now = time.time()
    _exec('INSERT INTO players(account,last_name,first_seen,last_seen,joins) '
          'VALUES(?,?,?,?,1) ON CONFLICT(account) DO UPDATE SET '
          'last_name=excluded.last_name, last_seen=excluded.last_seen, '
          'joins=joins+1', (account, name, now, now))
    _exec('INSERT INTO names(account,name,seen) VALUES(?,?,?) '
          'ON CONFLICT(account,name) DO UPDATE SET seen=excluded.seen',
          (account, name, now))


def get_player(account: str) -> dict | None:
    rows = _rows('SELECT * FROM players WHERE account=?', (account,))
    return rows[0] if rows else None


def is_known(account: str) -> bool:
    return get_player(account) is not None


def names_of(account: str, limit: int = 8) -> list[str]:
    return [r['name'] for r in _rows(
        'SELECT name FROM names WHERE account=? ORDER BY seen DESC LIMIT ?',
        (account, limit))]


# ---- audit -------------------------------------------------------------
def audit(actor: str, action: str, target: str, detail: str = '') -> None:
    log.info('[Lucious][audit] %s %s %s %s', actor, action, target, detail)
    try:
        _exec('INSERT INTO audit(ts,actor,action,target,detail) '
              'VALUES(?,?,?,?,?)',
              (time.time(), str(actor), action, str(target), detail))
    except Exception:
        log.exception('[Lucious] audit write failed')


def recent_audit(limit: int = 8) -> list[dict]:
    return _rows('SELECT * FROM audit ORDER BY id DESC LIMIT ?', (limit,))


def stats() -> dict:
    return {
        'bans': len(active_bans(10_000)),
        'mutes': len(_mutes),
        'players': _exec('SELECT COUNT(*) FROM players').fetchone()[0],
    }
