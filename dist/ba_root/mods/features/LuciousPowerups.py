# mods/features/LuciousPowerups.py
# ba_meta require api 9
"""Name + countdown above powerup boxes. Self-contained."""
from __future__ import annotations

import logging
import math
import weakref

import bascenev1 as bs
from bascenev1lib.actor import powerupbox as pb

from lucious import config
from lucious.commands import command

log = logging.getLogger('lucious')
NAMES = {'triple_bombs': 'Triple Bombs', 'punch': 'Boxing Gloves',
         'ice_bombs': 'Ice Bombs', 'impact_bombs': 'Impact Bombs',
         'land_mines': 'Land Mines', 'sticky_bombs': 'Sticky Bombs',
         'shield': 'Shield', 'health': 'Health', 'curse': 'Curse'}
LIFETIME = max(1.0, float(getattr(pb, 'DEFAULT_POWERUP_INTERVAL', 8.0)) - 1.0)


def _opt(key: str) -> bool:
    return bool(config.get('powerups.' + key, True))


def _attach(box, expire: bool) -> None:
    node = getattr(box, 'node', None)
    if not node:
        return
    names, timer = _opt('names'), _opt('timer') and expire
    if not (names or timer):
        return
    ptype = str(getattr(box, 'poweruptype', ''))
    label = NAMES.get(ptype, ptype.replace('_', ' ').title())
    deadline = bs.time() + LIFETIME
    text = bs.newnode('text', owner=node, attrs={
        'text': '', 'in_world': True, 'shadow': 1.0, 'flatness': 1.0,
        'color': (1.0, 0.88, 0.35), 'scale': 0.010,
        'h_align': 'center', 'v_align': 'center'})
    anchor = bs.newnode('math', owner=node, attrs={
        'input1': (0.0, 1.0, 0.0), 'operation': 'add'})
    node.connectattr('position', anchor, 'input2')
    anchor.connectattr('output', text, 'position')
    ref = weakref.ref(box)

    def tick() -> None:
        if ref() is None or not text.exists():
            return
        lines = []
        if names:
            lines.append(label)
        if timer:
            lines.append(f'{max(1, math.ceil(deadline - bs.time()))}s')
        text.text = '\n'.join(lines)

    tick()
    box._lucious_timer = bs.Timer(0.25, tick, repeat=True)


def setup() -> None:
    cls = pb.PowerupBox
    orig = getattr(cls, '_lucious_orig_init', None)
    if orig is None:                       # first load: remember the real one
        orig = cls._lucious_orig_init = cls.__init__

    def init(self, position=(0.0, 1.0, 0.0), poweruptype='triple_bombs',
             expire=True):
        orig(self, position=position, poweruptype=poweruptype, expire=expire)
        try:
            _attach(self, bool(expire))
        except Exception:
            log.exception('[Lucious] powerup label failed')

    cls.__init__ = init                    # always wraps the REAL original


def teardown() -> None:
    cls = pb.PowerupBox
    orig = getattr(cls, '_lucious_orig_init', None)
    if orig is not None:
        cls.__init__ = orig
        del cls._lucious_orig_init


@command('powerups', level=80, aliases=('pu',),
         usage='/powerups names|timer on|off', help='Powerup box labels')
def _cmd(ctx):
    a = [x.lower() for x in ctx.args]
    if len(a) == 2 and a[0] in ('names', 'timer') and a[1] in ('on', 'off'):
        config.set_value('powerups.' + a[0], a[1] == 'on')
        return ctx.reply(f'Powerup {a[0]}: {a[1]} (new boxes only)')
    ctx.reply(f"names={_opt('names')} timer={_opt('timer')}  |  "
              '/powerups names|timer on|off')
