# lucious/economy/store.py
"""Wallets, transactions and purchases (SQLite)."""
from __future__ import annotations

import os
import sqlite3
import threading
import time

from lucious.config import DATA_DIR

DB_PATH = os.path.join(DATA_DIR, 'economy.db')
_conn: sqlite3.Connection | None = None
_lock = threading.RLock()
SCHEMA = """
CREATE TABLE IF NOT EXISTS wallets(account TEXT PRIMARY KEY,
  coins INTEGER NOT NULL DEFAULT 0, earned INTEGER NOT NULL DEFAULT 0,
  spent INTEGER NOT NULL DEFAULT 0, last_daily REAL DEFAULT 0, name TEXT);
CREATE TABLE IF NOT EXISTS tx(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL,
  account TEXT, delta INTEGER, reason TEXT, balance INTEGER);
CREATE TABLE IF NOT EXISTS purchases(account TEXT, item TEXT, kind TEXT,
  expires REAL, equipped INTEGER DEFAULT 0, PRIMARY KEY(account, item));
"""


def open_db() -> None:
    global _conn
    with _lock:
        if _conn is None:
            os.makedirs(DATA_DIR, exist_ok=True)
            _conn = sqlite3.connect(DB_PATH, check_same_thread=False,
                                    isolation_level=None)
            _conn.execute('PRAGMA journal_mode=WAL')
            _conn.executescript(SCHEMA)


def close_db() -> None:
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
            _conn = None


def _x(sql: str, args: tuple = ()):
    with _lock:
        if _conn is None:
            open_db()
        return _conn.execute(sql, args)


def balance(acc: str) -> int:
    row = _x('SELECT coins FROM wallets WHERE account=?', (acc,)).fetchone()
    return row[0] if row else 0


def _log(acc, delta, reason) -> None:
    _x('INSERT INTO tx(ts,account,delta,reason,balance) VALUES(?,?,?,?,?)',
       (time.time(), acc, delta, reason, balance(acc)))


def touch(acc: str, name: str = '') -> None:
    _x('INSERT OR IGNORE INTO wallets(account,name) VALUES(?,?)', (acc, name))
    if name:
        _x('UPDATE wallets SET name=? WHERE account=?', (name, acc))


def add(acc: str, amount: int, reason: str, name: str = '',
        earned: bool = True) -> int:
    with _lock:
        touch(acc, name)
        _x('UPDATE wallets SET coins=coins+?, earned=earned+? WHERE account=?',
           (amount, amount if earned else 0, acc))
        _log(acc, amount, reason)
        return balance(acc)


def spend(acc: str, amount: int, reason: str) -> bool:
    with _lock:
        cur = _x('UPDATE wallets SET coins=coins-?, spent=spent+? '
                 'WHERE account=? AND coins>=?', (amount, amount, acc, amount))
        if cur.rowcount != 1:
            return False
        _log(acc, -amount, reason)
        return True


def transfer(src: str, dst: str, amount: int) -> bool:
    if not spend(src, amount, f'pay:{dst}'):
        return False
    add(dst, amount, f'pay_from:{src}', earned=False)
    return True


def last_daily(acc: str) -> float:
    row = _x('SELECT last_daily FROM wallets WHERE account=?', (acc,)).fetchone()
    return row[0] or 0 if row else 0


def set_daily(acc: str) -> None:
    touch(acc)
    _x('UPDATE wallets SET last_daily=? WHERE account=?', (time.time(), acc))


def top(n: int = 3) -> list[tuple]:
    return _x('SELECT name, coins FROM wallets WHERE coins>0 '
              'ORDER BY coins DESC LIMIT ?', (n,)).fetchall()


# ---- purchases ---------------------------------------------------------
def own(acc: str, item: str):
    r = _x('SELECT item,kind,expires,equipped FROM purchases '
           'WHERE account=? AND item=?', (acc, item)).fetchone()
    if r and r[2] is not None and r[2] <= time.time():
        _x('DELETE FROM purchases WHERE account=? AND item=?', (acc, item))
        return None
    return r


def give(acc: str, item: str, kind: str, seconds: float | None):
    old = own(acc, item)
    if old and old[2] is None:
        return None
    base = old[2] if old else time.time()
    exp = None if seconds is None else base + seconds
    _x('INSERT INTO purchases(account,item,kind,expires) VALUES(?,?,?,?) '
       'ON CONFLICT(account,item) DO UPDATE SET expires=excluded.expires',
       (acc, item, kind, exp))
    return exp


def items_of(acc: str) -> list[tuple]:
    now = time.time()
    return [r for r in _x('SELECT item,kind,expires,equipped FROM purchases '
                          'WHERE account=?', (acc,)).fetchall()
            if r[2] is None or r[2] > now]


def equip(acc: str, item: str, kind: str) -> None:
    _x('UPDATE purchases SET equipped=0 WHERE account=? AND kind=?', (acc, kind))
    _x('UPDATE purchases SET equipped=1 WHERE account=? AND item=?', (acc, item))


def unequip(acc: str, kind: str) -> None:
    _x('UPDATE purchases SET equipped=0 WHERE account=? AND kind=?', (acc, kind))


def equipped(acc: str, kind: str) -> str | None:
    for item, _k, _e, eq in items_of(acc):
        if eq and _k == kind:
            return item
    return None
