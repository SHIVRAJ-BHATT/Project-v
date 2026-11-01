# Released under the MIT License. See LICENSE for details.
# ba_meta require api 9
"""Lucious LagBot - keeps the server smooth without removing any effect.

* Monitor: measures how late the server loop runs (the real lag signal).
* Sweep:   deletes only stray props that fell far below the map.
* GC:      raises Python's GC threshold, freezes startup objects, and runs
           one full collection between games instead of mid-fight.
* Ping:    warns players with sustained high ping (kick is OFF by default).
Commands: /lag  (public)   /lag nodes|sweep|gc|on|off  (staff)
"""

from __future__ import annotations

import gc
import logging

import babase
import bascenev1 as bs

from features import LuciousKit as kit

try:
    import _bascenev1
except Exception:
    _bascenev1 = None

_LOG = logging.getLogger('LuciousLagBot')
TICK = 0.5

DEFAULTS = {
    'enabled': True,
    'announce': True,
    'cleanup': True,
    'gc_tune': True,
    'ping_guard': True,
    'lag_ms': 120.0,       # avg loop delay that counts as lag
    'void_y': -40.0,       # props below this height are deleted
    'ping_warn': 350.0,
    'ping_kick': 0.0,      # 0 = never kick
    'ping_strikes': 6,
    'gc_threshold': 10000,
}


def _c(key):
    return kit.cfg('lagbot', DEFAULTS, key)


class _S:
    t_tick = None
    t_sweep = None
    t_ping = None
    last = 0.0
    avg = 0.0
    peak = 0.0
    peak_t = 0.0
    slow = 0
    last_announce = -1e9
    removed = 0
    old_thr = None
    frozen = False
    strikes: dict = {}


def _sweep() -> tuple[int, dict]:
    act = bs.get_foreground_host_activity()
    if act is None or not hasattr(bs, 'getnodes'):
        return 0, {}
    removed = 0
    counts: dict = {}
    void_y = float(_c('void_y'))
    with act.context:
        for n in bs.getnodes():
            try:
                t = n.getnodetype()
                counts[t] = counts.get(t, 0) + 1
                if t == 'prop' and n.position[1] < void_y:
                    n.delete()
                    removed += 1
            except Exception:
                continue
    S.removed += removed
    return removed, counts


def _on_lag() -> None:
    if not _c('enabled'):
        return
    removed = 0
    if _c('cleanup'):
        try:
            removed, _ = _sweep()
        except Exception:
            _LOG.exception('LagBot: sweep failed')
    now = bs.apptime()
    if _c('announce') and now - S.last_announce > 90.0:
        S.last_announce = now
        extra = f' Cleaned {removed} stray objects.' if removed else ''
        kit.say(f'\ue04c LagBot: the server is catching up.{extra}',
                (1.0, 0.7, 0.2), chat=False)


def _tick() -> None:
    now = bs.apptime()
    if S.last:
        late = max(0.0, (now - S.last - TICK) * 1000.0)
        S.avg = S.avg * 0.8 + late * 0.2
        if late > S.peak or now - S.peak_t > 30.0:
            S.peak, S.peak_t = late, now
        if S.avg > float(_c('lag_ms')):
            S.slow += 1
        else:
            S.slow = 0
        if S.slow >= 3:
            S.slow = 0
            _on_lag()
    S.last = now


def _housekeeping() -> None:
    if _c('enabled') and _c('cleanup'):
        try:
            _sweep()
        except Exception:
            _LOG.exception('LagBot: housekeeping failed')


def _ping(cid):
    if _bascenev1 is None:
        return None
    try:
        return float(_bascenev1.get_client_ping(cid))
    except Exception:
        return None


def _ping_check() -> None:
    if not (_c('enabled') and _c('ping_guard')):
        return
    warn = float(_c('ping_warn'))
    kick = float(_c('ping_kick'))
    limit = int(_c('ping_strikes'))
    seen = set()
    for r in kit.roster():
        cid = r.get('client_id')
        if cid is None or cid == -1:
            continue
        seen.add(cid)
        ping = _ping(cid)
        if ping is None:
            continue
        if ping > warn:
            S.strikes[cid] = S.strikes.get(cid, 0) + 1
        else:
            S.strikes[cid] = max(0, S.strikes.get(cid, 0) - 1)
        n = S.strikes.get(cid, 0)
        if n == 3:
            try:
                bs.broadcastmessage(
                    f'\ue04c Your ping is high ({int(ping)} ms). '
                    'Close downloads / switch to a better connection.',
                    color=(1.0, 0.6, 0.2), transient=True, clients=[cid])
            except Exception:
                pass
        if kick > 0 and ping > kick and n >= limit:
            if kit.level_of(cid) >= 50:
                continue
            try:
                bs.disconnect_client(cid, ban_time=60.0)
                kit.say(f'LagBot: {kit.name_of(cid)} removed for very '
                        'high ping.', (1.0, 0.5, 0.2), chat=False)
            except Exception:
                _LOG.exception('LagBot: kick failed')
    for cid in list(S.strikes):
        if cid not in seen:
            del S.strikes[cid]


def _gc_apply() -> None:
    if not _c('gc_tune'):
        return
    try:
        if S.old_thr is None:
            S.old_thr = gc.get_threshold()
        gc.set_threshold(int(_c('gc_threshold')), 20, 20)
        if not S.frozen:
            gc.freeze()
            S.frozen = True
    except Exception:
        _LOG.exception('LagBot: gc tuning failed')


def _collect() -> None:
    if _c('enabled') and _c('gc_tune'):
        try:
            gc.collect()
        except Exception:
            pass
    _housekeeping()


def _on_begin(*_a, **_k) -> None:
    bs.apptimer(2.0, _collect)


def _cmd(ctx) -> None:
    args = [str(a).lower() for a in (getattr(ctx, 'args', None) or [])]
    sub = args[0] if args else 'info'
    if sub != 'info' and not kit.staff(ctx):
        kit.reply(ctx, 'Staff only.')
        return
    if sub in ('on', 'off'):
        kit.set_cfg('lagbot', 'enabled', sub == 'on')
        kit.reply(ctx, f'LagBot {sub}.')
    elif sub == 'sweep':
        removed, counts = _sweep()
        kit.reply(ctx, f'Sweep done: {removed} stray props removed, '
                       f'{sum(counts.values())} nodes alive.')
    elif sub == 'gc':
        gc.collect()
        kit.reply(ctx, 'Garbage collection done.')
    elif sub == 'nodes':
        _, counts = _sweep()
        top = sorted(counts.items(), key=lambda kv: -kv[1])[:7]
        text = ', '.join(f'{k}={v}' for k, v in top) or 'unavailable'
        kit.reply(ctx, f'Nodes ({sum(counts.values())}): {text}')
    else:
        state = 'LAGGING' if S.avg > float(_c('lag_ms')) else 'smooth'
        kit.reply(ctx, f'LagBot: {state} | loop delay avg {S.avg:.0f} ms, '
                       f'peak {S.peak:.0f} ms | players '
                       f'{kit.players_online()} | stray props removed '
                       f'{S.removed}')


S = _S()


def setup() -> None:
    _gc_apply()
    S.last = 0.0
    S.t_tick = bs.AppTimer(TICK, _tick, repeat=True)
    S.t_sweep = bs.AppTimer(20.0, _housekeeping, repeat=True)
    S.t_ping = bs.AppTimer(5.0, _ping_check, repeat=True)
    kit.on('activity_begin', _on_begin, priority=90)
    kit.add_command('lag', _cmd, level=0)


def teardown() -> None:
    S.t_tick = S.t_sweep = S.t_ping = None
    kit.off('activity_begin', _on_begin)
    try:
        if S.old_thr is not None:
            gc.set_threshold(*S.old_thr)
        if S.frozen:
            gc.unfreeze()
            S.frozen = False
    except Exception:
        pass
