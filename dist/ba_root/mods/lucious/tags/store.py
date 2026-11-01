# mods/lucious/tags/store.py
"""Tag storage (SQLite WAL) + per-player text style preference."""
from __future__ import annotations

import logging
import os
import sqlite3
import threading
import time

from lucious.config import DATA_DIR

log = logging.getLogger('lucious')
DB_PATH = os.path.join(DATA_DIR, 'tags.db')
_lock = threading.RLock()
_db: sqlite3.Connection | None = None
_tags: dict[str, tuple[str, str]] = {}
_styles: dict[str, str] = {}


def open_db() -> None:
    global _db
    with _lock:
        if _db is not None:
            return
        os.makedirs(DATA_DIR, exist_ok=True)
        _db = sqlite3.connect(DB_PATH, check_same_thread=False)
        _db.execute('PRAGMA journal_mode=WAL')
        _db.execute('CREATE TABLE IF NOT EXISTS tags (account TEXT PRIMARY '
                    'KEY, text TEXT NOT NULL, name TEXT, "by" TEXT, '
                    'created REAL)')
        _db.execute('CREATE TABLE IF NOT EXISTS prefs (account TEXT PRIMARY '
                    'KEY, style TEXT NOT NULL)')
        _db.commit()
        _tags.clear()
        _styles.clear()
        for acc, text, name in _db.execute(
                'SELECT account, text, name FROM tags'):
            _tags[acc] = (text, name or '')
        for acc, style in _db.execute('SELECT account, style FROM prefs'):
            _styles[acc] = style


def close_db() -> None:
    global _db
    with _lock:
        if _db is not None:
            try:
                _db.commit()
                _db.close()
            except Exception:
                log.exception('[Lucious] tags db close failed')
        _db = None


def get(account: str | None) -> str | None:
    if not account:
        return None
    row = _tags.get(account)
    return row[0] if row else None


def set_tag(account: str, text: str, name: str = '', by: str = '') -> None:
    with _lock:
        _tags[account] = (text, name)
        if _db is not None:
            _db.execute('INSERT OR REPLACE INTO tags (account, text, name, '
                        '"by", created) VALUES (?,?,?,?,?)',
                        (account, text, name, by, time.time()))
            _db.commit()


def remove(account: str) -> bool:
    with _lock:
        existed = _tags.pop(account, None) is not None
        if _db is not None:
            _db.execute('DELETE FROM tags WHERE account=?', (account,))
            _db.commit()
        return existed


def all_tags() -> list[tuple[str, str, str]]:
    return [(a, t, n) for a, (t, n) in _tags.items()]


def get_style(key: str | None) -> str | None:
    return _styles.get(key) if key else None


def set_style(key: str, style: str | None) -> None:
    """style None = back to server default. 'cid:' keys are memory-only."""
    with _lock:
        if style is None:
            _styles.pop(key, None)
        else:
            _styles[key] = style
        if _db is not None and not key.startswith('cid:'):
            if style is None:
                _db.execute('DELETE FROM prefs WHERE account=?', (key,))
            else:
                _db.execute('INSERT OR REPLACE INTO prefs (account, style) '
                            'VALUES (?,?)', (key, style))
            _db.commit()
