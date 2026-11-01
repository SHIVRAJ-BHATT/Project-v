# ba_meta require api 9
"""Shared helpers for the Lucious feature modules (imported, not loaded)."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Callable

import babase
import bascenev1 as bs

try:
    from lucious import config as _config
except Exception:
    _config = None
try:
    from lucious.events import bus as _bus
except Exception:
    _bus = None
try:
    from lucious.commands import command as _command
except Exception:
    _command = None

_LOG = logging.getLogger('LuciousKit')


def cfg(prefix: str, defaults: dict, key: str) -> Any:
    default = defaults[key]
    value: Any = None
    if _config is not None:
        path = f'{prefix}.{key}'
        try:
            value = _config.get(path, default)
        except TypeError:
            try:
                value = _config.get(path)
            except Exception:
                value = None
        except Exception:
            value = None
    if value is None:
        return default
    try:
        if isinstance(default, bool):
            return bool(value)
        if isinstance(default, int):
            return int(value)
        if isinstance(default, float):
            return float(value)
        if isinstance(default, str):
            return str(value)
        if isinstance(default, list):
            return list(value)
    except (TypeError, ValueError):
        return default
    return value


def set_cfg(prefix: str, key: str, value: Any) -> bool:
    if _config is None:
        return False
    path = f'{prefix}.{key}'
    done = False
    for name in ('set', 'put'):
        fn = getattr(_config, name, None)
        if callable(fn):
            try:
                fn(path, value)
                done = True
                break
            except Exception:
                continue
    if done:
        save = getattr(_config, 'save', None)
        if callable(save):
            try:
                save()
            except Exception:
                pass
    return done


def reply(ctx: Any, msg: str, color=(0.6, 1.0, 0.7)) -> None:
    for name in ('reply', 'send', 'say'):
        fn = getattr(ctx, name, None)
        if callable(fn):
            try:
                fn(msg)
                return
            except Exception:
                pass
    try:
        bs.broadcastmessage(msg, color=color, transient=True)
    except Exception:
        pass


def say(msg: str, color=(1.0, 0.85, 0.2), chat: bool = True) -> None:
    try:
        bs.broadcastmessage(msg, color=color, transient=True)
    except Exception:
        pass
    if chat:
        try:
            bs.chatmessage(msg)
        except Exception:
            pass


def roster() -> list:
    try:
        return list(bs.get_game_roster())
    except Exception:
        return []


def _entry(cid: Any) -> dict | None:
    for r in roster():
        if r.get('client_id') == cid:
            return r
    return None


def name_of(cid: Any) -> str:
    if cid == -1:
        return 'Host'
    r = _entry(cid)
    if r:
        players = r.get('players') or []
        if players:
            return str(players[0].get('name')
                       or players[0].get('name_full') or 'Player')
        return str(r.get('display_string') or 'Player')
    return 'Player'


def account_of(cid: Any) -> str | None:
    r = _entry(cid)
    if r and r.get('account_id'):
        return str(r['account_id'])
    return None


def players_online() -> int:
    try:
        session = bs.get_foreground_host_session()
        if session is not None:
            return len(session.sessionplayers)
    except Exception:
        pass
    return len([r for r in roster() if r.get('client_id') != -1])


def level_of(cid: Any) -> int:
    if cid == -1:
        return 1000
    try:
        from lucious.roles import level_of_client
        return int(level_of_client(cid, account_of(cid)))
    except Exception:
        return 0


def staff(ctx: Any, level: int = 80) -> bool:
    if getattr(ctx, 'client_id', None) == -1:
        return True
    try:
        return int(getattr(ctx, 'level', 0)) >= level
    except Exception:
        return False


def data_dir() -> str:
    base = getattr(_config, 'DATA_DIR', None) if _config else None
    if not base:
        try:
            user = babase.env().get('python_directory_user') or '.'
        except Exception:
            user = '.'
        base = os.path.join(user, 'lucious_data')
    os.makedirs(base, exist_ok=True)
    return str(base)


def load_json(name: str, default: Any) -> Any:
    try:
        with open(os.path.join(data_dir(), name), encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default


def save_json(name: str, data: Any) -> None:
    try:
        path = os.path.join(data_dir(), name)
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    except Exception:
        _LOG.exception('save_json(%s) failed', name)


def add_command(name: str, fn: Callable, level: int = 0) -> bool:
    if _command is None:
        return False
    try:
        _command(name, level=level)(fn)
        return True
    except Exception:
        _LOG.warning('command /%s not registered', name, exc_info=True)
        return False


def on(event: str, fn: Callable, priority: int = 50) -> None:
    if _bus is not None:
        try:
            _bus.subscribe(event, fn, priority=priority)
        except Exception:
            _LOG.warning('subscribe %s failed', event, exc_info=True)


def off(event: str, fn: Callable) -> None:
    if _bus is not None:
        try:
            _bus.unsubscribe(event, fn)
        except Exception:
            pass
