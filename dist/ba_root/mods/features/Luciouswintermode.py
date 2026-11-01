# mods/features/Luciouswintermode.py
# ba_meta require api 9
"""Lucious winter mode: particle snowfall, cold tint, optional ice."""
from __future__ import annotations

import logging
import random
from typing import Any

import bascenev1 as bs
from bascenev1lib.gameutils import SharedObjects

from lucious import config
from lucious.commands import command
from lucious.events import bus

log = logging.getLogger('lucious')

DEFAULTS = {'enabled': True, 'snow': True, 'tint': True, 'ice': False,
            'size': 0.75, 'speed': 50.0, 'density': 10}
NO_TINT = ('Lake Frigid', 'Happy Thoughts')
TINT_NODES = ('node', 'floor', 'background', 'bg2', 'stands', 'stem')
TINT_MUL = (1.15, 1.2, 1.35)
STATE: dict[str, Any] = {
    'field': None, 'timer': None, 'tint_orig': {}, 'gtint': None,
    'ice_mat': None, 'ice_orig': {}, 'ice_on': False, 'ice_timer': None,
    'warned': False}


def cfg(key: str):
    return config.get('winter.' + key, DEFAULTS[key])


def _game_activity():
    try:
        act = bs.get_foreground_host_activity()
    except Exception:
        return None
    return act if isinstance(act, bs.GameActivity) else None


# ---------------------------------------------------------------- snow ----
def _field(act):
    """(xmin, xmax, zmin, zmax, top, center_x) from the map bounds."""
    try:
        x0, _y0, z0, x1, y1, z1 = act.map.get_def_bound_box('map_bounds')
    except Exception:
        return None
    cx, cz = (x0 + x1) / 2.0, (z0 + z1) / 2.0
    hx = min((x1 - x0) / 2.0, 25.0)
    hz = min((z1 - z0) / 2.0, 25.0)
    top = min(max(float(y1), 8.0), 18.0)
    return (cx - hx, cx + hx, cz - hz, cz + hz, top, cx)


def _emit() -> None:
    f = STATE['field']
    if f is None:
        return
    try:
        x = random.uniform(f[0], f[1])
        z = random.uniform(f[2], f[3])
        d = -1.0 if x > f[5] else 1.0
        bs.emitfx(
            position=(x, f[4], z),
            velocity=(random.uniform(-5.0, 25.0) * d,
                      -float(cfg('speed')),
                      random.uniform(-5.0, 25.0) * d),
            count=int(cfg('density')),
            scale=(1.0 + random.random()) * float(cfg('size')),
            spread=0.0, chunk_type='spark')
    except Exception:
        if not STATE['warned']:
            STATE['warned'] = True
            log.exception('[Lucious] snow emit failed (logged once)')


def _start_snow(act) -> None:
    STATE['field'] = _field(act)
    if STATE['field'] is not None:
        STATE['timer'] = bs.BaseTimer(0.04, _emit, repeat=True)


def _stop_snow() -> None:
    STATE['timer'] = None
    STATE['field'] = None


# ---------------------------------------------------------------- tint ----
def _cool(act) -> None:
    try:
        if act.map.getname() in NO_TINT:
            return
    except Exception:
        return
    for attr in TINT_NODES:
        n = getattr(act.map, attr, None)
        try:
            if n is None or not n.exists() or attr in STATE['tint_orig']:
                continue
            c = tuple(n.color)
            STATE['tint_orig'][attr] = (n, c)
            n.color = tuple(min(1.6, v * k) for v, k in zip(c, TINT_MUL))
        except Exception:
            continue
    g = act.globalsnode
    t = tuple(g.tint)
    STATE['gtint'] = t
    bs.animate_array(g, 'tint', 3, {
        0.0: t, 1.5: (t[0] * 0.92, t[1] * 0.97, t[2] * 1.12)})


def _uncool(act) -> None:
    for n, c in STATE['tint_orig'].values():
        try:
            if n.exists():
                n.color = c
        except Exception:
            pass
    STATE['tint_orig'] = {}
    if STATE['gtint'] is not None:
        try:
            act.globalsnode.tint = STATE['gtint']
        except Exception:
            pass
        STATE['gtint'] = None


# ----------------------------------------------------------------- ice ----
def _hockey_players(on: bool) -> None:
    act = _game_activity()
    if act is None:
        return
    for p in act.players:
        try:
            if p.actor and p.actor.is_alive():
                p.actor.node.hockey = on
        except Exception:
            pass


def _set_ice(act, on: bool) -> None:
    shared = SharedObjects.get()
    if on:
        if STATE['ice_mat'] is None:
            m = bs.Material()
            m.add_actions(actions=('modify_part_collision', 'friction', 0.01))
            STATE['ice_mat'] = m
        for attr in ('node', 'floor'):
            n = getattr(act.map, attr, None)
            try:
                if n is None or not n.exists() or attr in STATE['ice_orig']:
                    continue
                orig = list(n.materials)
                STATE['ice_orig'][attr] = (n, orig)
                n.materials = orig + [STATE['ice_mat']]
            except Exception:
                continue
        STATE['ice_timer'] = bs.Timer(
            1.0, lambda: _hockey_players(True), repeat=True)
    else:
        STATE['ice_timer'] = None
        for n, orig in STATE['ice_orig'].values():
            try:
                if n.exists():
                    n.materials = orig or [shared.footing_material]
            except Exception:
                pass
        STATE['ice_orig'] = {}
    STATE['ice_on'] = on
    _hockey_players(on)


# ----------------------------------------------------------- lifecycle ----
def _drop_state() -> None:
    STATE.update({'field': None, 'timer': None, 'tint_orig': {},
                  'gtint': None, 'ice_orig': {}, 'ice_on': False,
                  'ice_timer': None, 'warned': False})


def _apply(act) -> None:
    if cfg('snow'):
        _start_snow(act)
    if cfg('tint'):
        _cool(act)
    if cfg('ice'):
        _set_ice(act, True)


def _remove(act) -> None:
    _stop_snow()
    _uncool(act)
    _set_ice(act, False)


def _on_begin(act) -> None:
    _drop_state()
    if not isinstance(act, bs.GameActivity) or not cfg('enabled'):
        return
    try:
        with act.context:
            _apply(act)
    except Exception:
        log.exception('[Lucious] winter apply failed')


def _refresh(act) -> None:
    with act.context:
        _remove(act)
        if cfg('enabled'):
            _apply(act)


def setup() -> None:
    bus.subscribe('activity_begin', _on_begin, priority=70)


def teardown() -> None:
    act = _game_activity()
    if act is not None:
        try:
            with act.context:
                _remove(act)
        except Exception:
            pass
    _drop_state()


_USAGE = ('/winter on|off|snow|tint|ice [on|off] | '
          'size|speed|density <n> | info')


@command('winter', level=80, usage=_USAGE, help='Control winter mode')
def _winter(ctx):
    a = [x.lower() for x in ctx.args]
    sub = a[0] if a else 'info'
    act = _game_activity()
    if sub in ('on', 'off'):
        config.set_value('winter.enabled', sub == 'on')
    elif sub in ('snow', 'tint', 'ice'):
        val = (a[1] == 'on') if len(a) > 1 else not cfg(sub)
        config.set_value('winter.' + sub, val)
    elif sub in ('size', 'speed', 'density') and len(a) > 1:
        try:
            num = float(a[1])
        except ValueError:
            return ctx.error('Number expected.')
        lo, hi = {'size': (0.1, 5.0), 'speed': (1.0, 150.0),
                  'density': (1, 100)}[sub]
        num = max(lo, min(hi, num))
        config.set_value('winter.' + sub, int(num) if sub == 'density' else num)
    elif sub == 'info':
        f = STATE['field']
        return ctx.reply(
            f"enabled={cfg('enabled')} snow={cfg('snow')} tint={cfg('tint')} "
            f"ice={cfg('ice')} size={cfg('size')} speed={cfg('speed')} "
            f"density={cfg('density')} | snow field: "
            f"{'none' if f is None else tuple(round(v, 1) for v in f[:5])} | "
            f"timer {'on' if STATE['timer'] is not None else 'off'}")
    else:
        return ctx.error('Usage: ' + _USAGE)
    if act is not None:
        _refresh(act)
    ctx.reply('Winter updated.')
