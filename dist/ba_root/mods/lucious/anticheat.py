# lucious/anticheat.py
"""AFK kicker. Chat spam, abuse and join protection live in lucious.security."""
from __future__ import annotations

import logging
import math
import time

import babase
import bascenev1 as bs

from lucious import config, roles, utils
from lucious.events import bus

log = logging.getLogger('lucious')
_last: dict[int, float] = {}
_prev: dict[int, tuple] = {}
_warned: set[int] = set()
_timer = None


def _cfg(key: str, default):
    return config.get(f'anticheat.afk.{key}', default)


def touch(cid: int) -> None:
    _last[cid] = time.time()
    _warned.discard(cid)


def is_afk(account: str | None) -> bool:
    if not account:
        return False
    now = time.time()
    for e in utils.roster():
        if e.get('account_id') == account:
            return now - _last.get(e['client_id'], now) >= float(
                _cfg('warn_after', 45))
    return False


def on_chat(msg, cid):
    touch(cid)
    return msg


def on_join(cid, _info=None):
    touch(cid)


def on_leave(cid, _info=None):
    for d in (_last, _prev):
        d.pop(cid, None)
    _warned.discard(cid)


def on_begin(_activity):
    for cid in list(_last):
        touch(cid)


def _sample(player):
    actor = player.actor
    if actor is None or not actor.is_alive():
        return None
    n = actor.node
    inputs = (round(n.move_left_right, 2), round(n.move_up_down, 2), n.run,
              n.jump_pressed, n.punch_pressed, n.bomb_pressed, n.pickup_pressed)
    return inputs, tuple(n.position)


def _check(player, now, warn_after, kick_after, enforce) -> None:
    try:
        cid = player.sessionplayer.inputdevice.client_id
    except Exception:
        return
    if cid == utils.HOST:
        return
    sample = _sample(player)
    if sample is None:               # dead / waiting to respawn: not AFK
        touch(cid)
        _prev.pop(cid, None)
        return
    inputs, pos = sample
    prev = _prev.get(cid)
    active = (prev is None or prev[0] != inputs
              or math.dist(prev[1], pos) > 0.5)
    _prev[cid] = (inputs, pos if active else prev[1])
    if active:
        touch(cid)
        return
    idle = now - _last.setdefault(cid, now)
    if not enforce or idle < warn_after:
        return
    acc = utils.account_of(cid)
    if roles.level_of(acc) >= int(config.get('security.staff_bypass_level', 50)):
        return
    if idle >= kick_after:
        utils.announce(f'{utils.name_of(cid)} was kicked for being AFK.')
        utils.kick(cid, int(_cfg('ban_seconds', 60)))
        touch(cid)
    elif cid not in _warned:
        _warned.add(cid)
        utils.tell(cid, f'AFK? Move within {int(kick_after - idle)}s or you '
                        'will be kicked.', utils.YELLOW)


def _tick() -> None:
    if not _cfg('enabled', True):
        return
    try:
        activity = bs.get_foreground_host_activity()
        if activity is None:
            return
        clients = [e for e in utils.roster()
                   if e.get('client_id', utils.HOST) != utils.HOST]
        enforce = len(clients) >= int(_cfg('min_players', 0))
        now = time.time()
        warn_after = float(_cfg('warn_after', 45))
        kick_after = float(_cfg('kick_after', 60))
        with activity.context:
            for p in list(activity.players):
                _check(p, now, warn_after, kick_after, enforce)
    except Exception:
        log.exception('[Lucious] afk tick failed')


def setup() -> None:
    global _timer
    bus.subscribe('chat', on_chat, priority=1)
    bus.subscribe('client_join', on_join)
    bus.subscribe('client_leave', on_leave)
    bus.subscribe('activity_begin', on_begin)
    _timer = babase.AppTimer(1.0, _tick, repeat=True)


def teardown() -> None:
    global _timer
    _timer = None
    _last.clear()
    _prev.clear()
    _warned.clear()
