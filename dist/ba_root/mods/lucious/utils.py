"""Roster lookups, messaging, durations, target resolution."""
from __future__ import annotations

import logging
import re
from typing import Any

import babase
import bascenev1 as bs

log = logging.getLogger('lucious')

HOST = -1
RED = (1.0, 0.35, 0.35)
GREEN = (0.4, 1.0, 0.4)
YELLOW = (1.0, 0.85, 0.3)
CYAN = (0.5, 0.9, 1.0)


def roster() -> list[dict[str, Any]]:
    try:
        return list(bs.get_game_roster() or [])
    except Exception:
        return []


def client_info(client_id: int) -> dict[str, Any] | None:
    for entry in roster():
        if entry.get('client_id') == client_id:
            return entry
    return None


def display_name(entry: dict[str, Any] | None) -> str:
    if not entry:
        return '?'
    players = entry.get('players') or []
    if players:
        return players[0].get('name_full') or players[0].get('name') or '?'
    return entry.get('display_string') or f"client {entry.get('client_id')}"


def name_of(client_id: int) -> str:
    return display_name(client_info(client_id))


def account_of(client_id: int) -> str | None:
    entry = client_info(client_id)
    if entry and entry.get('account_id'):
        return entry['account_id']
    session = bs.get_foreground_host_session()
    if session is None:
        return None
    for sp in session.sessionplayers:
        try:
            if sp.inputdevice.client_id == client_id:
                return sp.get_v1_account_id()
        except Exception:
            continue
    return None


def tell(client_id: int, text: str, color=CYAN) -> None:
    if client_id == HOST:
        print(f'[Lucious] {text}')
        return
    try:
        bs.broadcastmessage(text, color=color, clients=[client_id],
                            transient=True)
    except Exception:
        log.exception('[Lucious] tell() failed')


def announce(text: str, color=YELLOW) -> None:
    try:
        bs.broadcastmessage(text, color=color, transient=True)
    except Exception:
        log.exception('[Lucious] announce() failed')


def later(seconds: float, fn) -> None:
    babase.apptimer(seconds, fn)


def kick(client_id: int, ban_seconds: int = 60, delay: float = 0.25) -> None:
    if client_id == HOST:
        return

    def _do() -> None:
        try:
            bs.disconnect_client(client_id, ban_time=int(ban_seconds))
        except Exception:
            log.exception('[Lucious] kick failed')
    later(delay, _do)


_DUR = re.compile(r'^(\d+)([smhdw]?)$')
_UNITS = {'s': 1, '': 60, 'm': 60, 'h': 3600, 'd': 86400, 'w': 604800}


def parse_duration(text: str) -> tuple[bool, float | None]:
    """'10m' -> (True, 600). 'perm' -> (True, None). Bare number = minutes."""
    t = text.lower().strip()
    if t in ('perm', 'permanent', 'forever'):
        return True, None
    m = _DUR.match(t)
    if not m or int(m.group(1)) <= 0:
        return False, None
    return True, float(int(m.group(1)) * _UNITS[m.group(2)])


def fmt_duration(seconds: float | None) -> str:
    if seconds is None:
        return 'permanent'
    s = max(0, int(seconds))
    parts = []
    for unit, size in (('d', 86400), ('h', 3600), ('m', 60), ('s', 1)):
        if s >= size:
            parts.append(f'{s // size}{unit}')
            s %= size
    return ' '.join(parts[:2]) or '0s'


def resolve_target(arg: str):
    """Returns (client_id|None, account|None, name, error|None)."""
    entries = [e for e in roster() if e.get('client_id', HOST) != HOST]
    if re.fullmatch(r'-?\d+', arg):
        cid = int(arg)
        for e in entries:
            if e.get('client_id') == cid:
                return cid, e.get('account_id'), display_name(e), None
        return None, None, arg, f'No client with id {cid}. Use /list.'
    if arg.lower().startswith('pb-'):
        for e in entries:
            if e.get('account_id') == arg:
                return e['client_id'], arg, display_name(e), None
        return None, arg, arg, None  # offline account
    needle = arg.lower()
    hits = []
    for e in entries:
        names = [e.get('display_string') or '']
        for p in e.get('players') or []:
            names += [p.get('name_full') or '', p.get('name') or '']
        if any(needle in n.lower() for n in names if n):
            hits.append(e)
    if len(hits) == 1:
        e = hits[0]
        return e['client_id'], e.get('account_id'), display_name(e), None
    if not hits:
        return None, None, arg, f'No player matches "{arg}".'
    opts = ', '.join(f"{display_name(e)}({e['client_id']})" for e in hits[:5])
    return None, None, arg, f'Ambiguous: {opts}. Use the client id.'
