"""Join guard: bans, account verification, names, impersonation,
lockdown, rejoin flood, players-per-client."""
from __future__ import annotations

import time
from collections import deque

from lucious import config, roles, utils
from lucious.events import bus
from lucious.security import alerts, storage
from lucious.security.normalize import clean, name_key

_joins: dict[str, deque] = {}
_pending: dict[int, float] = {}
_protected: set[str] = set()
_protected_at = 0.0


def _cfg(key: str, default=None):
    return config.get(f'security.{key}', default)


def _bypass_level() -> int:
    return int(_cfg('staff_bypass_level', 50))


def _protected_names() -> set[str]:
    global _protected_at
    if time.time() - _protected_at < 60:
        return _protected
    keys = set()
    for n in _cfg('names.protected_names', []) or []:
        k = name_key(n)
        if len(k) >= 3:
            keys.add(k)
    for acc in roles.staff_accounts():
        for n in storage.names_of(acc):
            k = name_key(n)
            if len(k) >= 3:
                keys.add(k)
    _protected.clear()
    _protected.update(keys)
    _protected_at = time.time()
    return _protected


def name_problem(name: str, account: str | None) -> str | None:
    if roles.level_of(account) >= _bypass_level():
        return None
    visible = clean(name).strip()
    if len(visible) < int(_cfg('names.min_length', 2)):
        return 'Name too short / invisible.'
    if len(visible) > int(_cfg('names.max_length', 32)):
        return 'Name too long.'
    key = name_key(name)
    for pat in _cfg('names.banned_patterns', []) or []:
        p = name_key(pat)
        if p and p in key:
            return 'Name not allowed.'
    for row in storage.name_ban_patterns():
        if row['value'] and row['value'] in key:
            return f"Name banned: {row['reason']}"
    if _cfg('names.block_impersonation', True) and key in _protected_names():
        return 'Impersonating staff is not allowed.'
    return None


def _reject(cid: int, reason: str, acc: str | None, action: str,
            ban_seconds: int = 60) -> None:
    utils.tell(cid, f'Disconnected: {reason}', utils.RED)
    storage.audit('JoinGuard', action, acc or f'cid:{cid}', reason)
    utils.kick(cid, ban_seconds, delay=1.5)


def _evaluate(cid: int, acc: str, name: str) -> None:
    _pending.pop(cid, None)
    ban = storage.find_ban('account', acc)
    if ban:
        left = (utils.fmt_duration(ban['expires'] - time.time())
                if ban['expires'] else 'permanent')
        return _reject(cid, f"You are banned ({left}). Reason: "
                            f"{ban['reason']}", acc, 'banned_join', 300)
    problem = name_problem(name, acc)
    if problem:
        return _reject(cid, problem, acc, 'bad_name')
    level = roles.level_of(acc)
    if _cfg('lockdown', False) and level < int(_cfg('lockdown_min_level', 10)):
        if not (_cfg('lockdown_allow_known_players', True)
                and storage.is_known(acc)):
            return _reject(cid, 'Server is in lockdown. Try later.', acc,
                           'lockdown')
    if level < _bypass_level():
        rf = _cfg('rejoin_flood', {}) or {}
        dq = _joins.setdefault(acc, deque())
        now = time.time()
        while dq and now - dq[0] > float(rf.get('window', 60)):
            dq.popleft()
        dq.append(now)
        if len(dq) > int(rf.get('joins', 4)):
            minutes = int(rf.get('ban_minutes', 10))
            storage.add_ban('account', acc, 'Rejoin flooding', 'JoinGuard',
                            minutes * 60)
            alerts.send('Rejoin flood', f'{name} (`{acc}`) banned {minutes}m')
            dq.clear()
            return _reject(cid, f'Rejoin flooding. Banned {minutes} min.',
                           acc, 'rejoin_flood', 300)
    storage.touch_player(acc, name)
    if level >= _bypass_level():
        utils.tell(cid, f'Welcome back, {roles.role_name(acc)}.', utils.GREEN)


def _account_timeout(cid: int) -> None:
    if cid not in _pending:
        return
    acc = utils.account_of(cid)
    if acc:
        _evaluate(cid, acc, utils.name_of(cid))
        return
    _pending.pop(cid, None)
    if _cfg('require_account', True):
        _reject(cid, 'Account not verified. Sign in and rejoin.', None,
                'no_account')


def on_client_join(cid: int, info: dict) -> None:
    _pending[cid] = time.time()
    acc = info.get('account_id')
    if acc:
        _evaluate(cid, acc, utils.display_name(info))
    else:
        utils.later(float(_cfg('account_wait_seconds', 10)),
                    lambda: _account_timeout(cid))


def on_client_account(cid: int, info: dict) -> None:
    if cid in _pending:
        _evaluate(cid, info['account_id'], utils.display_name(info))


def on_client_leave(cid: int, _info: dict) -> None:
    _pending.pop(cid, None)


def on_player_request(session, sp):
    try:
        cid = sp.inputdevice.client_id
    except Exception:
        return None
    if cid == utils.HOST:
        return None
    acc = utils.account_of(cid)
    if not acc:
        if _cfg('require_account', True):
            utils.tell(cid, 'Verifying your account... try again shortly.',
                       utils.YELLOW)
            return False
    elif storage.find_ban('account', acc):
        return False
    try:
        pname = sp.getname(full=True)
    except Exception:
        pname = ''
    problem = name_problem(pname, acc) if pname else None
    if problem:
        utils.tell(cid, f'Profile name rejected: {problem}', utils.RED)
        return False
    if roles.level_of(acc) < _bypass_level():
        limit = int(_cfg('max_players_per_client', 2))
        others = 0
        for other in session.sessionplayers:
            if other is sp:
                continue
            try:
                if other.inputdevice.client_id == cid:
                    others += 1
            except Exception:
                pass
        if others >= limit:
            utils.tell(cid, f'Max {limit} players per device.', utils.RED)
            return False
    return None


def setup() -> None:
    bus.subscribe('client_join', on_client_join)
    bus.subscribe('client_account', on_client_account)
    bus.subscribe('client_leave', on_client_leave)
    bus.subscribe('player_request', on_player_request, priority=10)
