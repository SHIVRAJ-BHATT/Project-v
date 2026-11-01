# mods/features/LuciousMapBG.py
# ba_meta require api 9
"""Black / shield-texture backgrounds per map."""
from __future__ import annotations

import logging
import random

import bascenev1 as bs

from lucious import config
from lucious.commands import command
from lucious.events import bus

log = logging.getLogger('lucious')
DEFAULT_MAPS = {'Rampage': 'black', 'Doom Shroom': 'black', 'Zigzag': 'black',
                'The Pad': 'black', 'Tip Top': 'shield', 'Big G': 'shield',
                'Monkey Face': 'shield', 'Crag Castle': 'shield'}


def _maps() -> dict:
    return dict(config.get('mapbg.maps', DEFAULT_MAPS))


def _apply(m, mode: str) -> bool:
    if mode == 'random':
        mode = random.choice(['black', 'shield'])
    if mode not in ('black', 'shield'):
        return False
    done = False
    for attr in ('background', 'bg2'):
        node = getattr(m, attr, None)
        if node is None or not node.exists():
            continue
        if mode == 'black':
            node.color = (0.0, 0.0, 0.0)
        else:
            node.color_texture = bs.gettexture(
                config.get('mapbg.texture', 'shield'))
            node.color = tuple(config.get('mapbg.shield_color',
                                          [0.6, 0.8, 1.2]))
        done = True
    return done


def _current_map(activity):
    try:
        return activity.map
    except Exception:
        return getattr(activity, '_map', None)


def _on_begin(activity) -> None:
    if not config.get('mapbg.enabled', True):
        return
    with activity.context:
        m = _current_map(activity)
        if m is None:
            return
        mode = _maps().get(m.getname(), config.get('mapbg.default',
                                                   'default'))
        _apply(m, mode)


def setup() -> None:
    bus.subscribe('activity_begin', _on_begin, priority=70)


def teardown() -> None:
    pass


@command('mapbg', level=80, usage='/mapbg black|shield|random|default',
         help='Set the background style for the current map')
def _mapbg(ctx):
    mode = ctx.args[0].lower() if ctx.args else ''
    if mode not in ('black', 'shield', 'random', 'default'):
        return ctx.error('Use: black, shield, random or default.')
    act = bs.get_foreground_host_activity()
    m = _current_map(act) if act else None
    if m is None:
        return ctx.error('No map is active right now.')
    maps = _maps()
    maps[m.getname()] = mode
    config.set_value('mapbg.maps', maps)
    with act.context:
        _apply(m, mode)
    ctx.reply(f'{m.getname()} background: {mode} (default = next load)')
