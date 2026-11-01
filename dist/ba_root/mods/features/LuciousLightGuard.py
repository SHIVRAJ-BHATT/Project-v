# ba_meta require api 9
from __future__ import annotations

import logging

import bascenev1 as bs

from lucious.commands import command
from lucious.events import bus

log = logging.getLogger('lucious')

FLOOR = 0.25
CHECK_AT = (2.2, 4.0, 7.0)          # after the 1.2 s map fade has finished
_FALLBACK = ((1.1, 1.1, 1.1), (1.1, 1.1, 1.1))

# tint, ambient_color taken from your map pack
MAP_LIGHT = {
    'Neo Zone': ((1.1, 1.05, 1.17), (1.2, 1.17, 1.1)),
    'Big H': ((1.1, 1.05, 1.17), (1.2, 1.17, 1.1)),
    'Powerups Factory': ((1.1, 1.1, 1.17), (1.2, 1.17, 1.1)),
    'Platforms': ((1.1, 1.05, 1.17), (1.2, 1.17, 1.1)),
    'The Limbo': ((1.2, 1.2, 1.2), (1.15, 1.25, 1.6)),
    'The Arena': ((1.2, 1.2, 1.2), (1.15, 1.25, 1.6)),
    'Island Mine': ((1.1, 1.1, 1.0), (1.1, 1.1, 1.0)),
    'Skull Temple': ((1.3, 1.2, 1.0), (1.3, 1.2, 1.0)),
    'Botton Rampage': ((1.2, 1.2, 1.2), (1.15, 1.25, 1.6)),
    'Collosal Bridgit': ((1.1, 1.2, 1.3), (1.1, 1.2, 1.3)),
    'The Crusade': ((1.2, 1.2, 1.2), (1.15, 1.25, 1.6)),
    'Collosal Monkey': ((1.1, 1.2, 1.3), (1.1, 1.2, 1.3)),
    'Tower Zoe': ((1.2, 1.1, 1.0), (1.2, 1.1, 1.0)),
    'Space Thoughts': ((1.3, 1.23, 1.0), (1.3, 1.23, 1.0)),
}


def _repair(act, force: bool = False) -> bool:
    try:
        g = act.globalsnode
        if not g.exists():
            return False
        dark_t = max(g.tint) < FLOOR
        dark_a = max(g.ambient_color) < FLOOR
        if not (force or dark_t or dark_a):
            return False
        try:
            name = act.map.getname()
        except Exception:
            name = ''
        tint, amb = MAP_LIGHT.get(name, _FALLBACK)
        if force or dark_t:
            g.tint = tint
        if force or dark_a:
            g.ambient_color = amb
        log.warning('[Lucious] LightGuard repaired lighting on %r', name)
        return True
    except Exception:
        log.exception('[Lucious] LightGuard failed')
        return False


def _check():
    act = bs.getactivity(doraise=False)
    if act is not None:
        _repair(act)


def _on_begin(*_a, **_k):
    act = bs.getactivity(doraise=False) or bs.get_foreground_host_activity()
    if act is None:
        return
    with act.context:
        for t in CHECK_AT:
            bs.timer(t, _check)


@command('lightfix', level=50, usage='/lightfix',
         help='Reset a black/dark map back to its normal lighting.')
def _lightfix(ctx):
    act = bs.get_foreground_host_activity()
    if act is None:
        ctx.error('No active game.')
        return
    _repair(act, force=True)
    ctx.reply('Lighting reset.')


def setup():
    bus.subscribe('activity_begin', _on_begin, priority=70)


def teardown():
    pass
