# ba_meta require api 9
# LuciousRing - rainbow circle under the owner's feet (owner only).
from __future__ import annotations

import logging

import bascenev1 as bs

from lucious import config, roles, utils
from lucious.commands import command

log = logging.getLogger('lucious')

PALETTE = [
    (1.0, 0.0, 0.0), (1.0, 0.5, 0.0), (1.0, 1.0, 0.0), (0.5, 1.0, 0.0),
    (0.0, 1.0, 0.0), (0.0, 1.0, 0.5), (0.0, 1.0, 1.0), (0.0, 0.5, 1.0),
    (0.5, 0.0, 1.0), (1.0, 0.0, 1.0), (1.0, 0.0, 0.5),
]
DEFAULTS = {'enabled': True, 'size': 2.4, 'y': 0.05, 'opacity': 0.6,
            'speed': 0.3, 'min_level': 100}
_patched: list = []


def _f(key, lo, hi):
    try:
        v = float(config.get('ring.' + key, DEFAULTS[key]))
    except Exception:
        v = float(DEFAULTS[key])
    return max(lo, min(hi, v))


def _enabled() -> bool:
    try:
        return bool(config.get('ring.enabled', True))
    except Exception:
        return True


def _is_owner(spaz) -> bool:
    try:
        cid = int(spaz.player.sessionplayer.inputdevice.client_id)
        acct = utils.account_of(cid)
        return roles.level_of_client(cid, acct) >= int(
            _f('min_level', 1, 1000))
    except Exception:
        return False


def _build(spaz):
    node = spaz.node
    size = _f('size', 0.5, 8.0)
    step = _f('speed', 0.05, 3.0)
    loc = bs.newnode('locator', owner=node, attrs={
        'shape': 'circle', 'color': PALETTE[0],
        'opacity': _f('opacity', 0.1, 1.0),
        'draw_beauty': True, 'additive': True, 'size': [size]})
    pos = bs.newnode('math', owner=node, attrs={
        'input1': (0.0, _f('y', -1.0, 2.0), 0.0), 'operation': 'add'})
    node.connectattr('position', pos, 'input2')
    pos.connectattr('output', loc, 'position')

    keys = {i * step: c for i, c in enumerate(PALETTE)}
    keys[len(PALETTE) * step] = PALETTE[0]
    bs.animate_array(loc, 'color', 3, keys, loop=True)
    bs.animate_array(loc, 'size', 1, {
        0.0: [size], 0.8: [size * 1.1], 1.6: [size]}, loop=True)


def setup():
    from bascenev1lib.actor import playerspaz as mod
    cls = mod.PlayerSpaz
    orig = getattr(cls, '_lucious_ring_orig', None) or cls.__init__
    cls._lucious_ring_orig = orig

    def init(self, *a, **k):
        orig(self, *a, **k)
        if not _enabled():
            return
        try:
            if _is_owner(self):
                _build(self)
        except Exception:
            log.exception('[Lucious] owner ring failed')

    cls.__init__ = init
    _patched.append((cls, orig))


def teardown():
    for cls, orig in _patched:
        try:
            cls.__init__ = orig
        except Exception:
            pass
    _patched.clear()


@command('ring', level=100,
         usage='/ring on|off | /ring size|y|opacity|speed <n>',
         help='Owner rainbow ring (applies on next spawn).')
def _ring(ctx):
    a = [x.lower() for x in ctx.args]
    limits = {'size': (0.5, 8.0), 'y': (-1.0, 2.0),
              'opacity': (0.1, 1.0), 'speed': (0.05, 3.0)}
    if len(a) == 1 and a[0] in ('on', 'off'):
        config.set_value('ring.enabled', a[0] == 'on')
        ctx.reply(f'ring {a[0]} (next spawn)')
    elif len(a) == 2 and a[0] in limits:
        lo, hi = limits[a[0]]
        try:
            v = max(lo, min(hi, float(a[1])))
        except ValueError:
            ctx.error(f'Usage: /ring {a[0]} {lo}-{hi}')
            return
        config.set_value('ring.' + a[0], v)
        ctx.reply(f'ring {a[0]} = {v} (next spawn)')
    else:
        ctx.reply(f'ring={"on" if _enabled() else "off"}, '
                  f'size={_f("size", 0.5, 8)}, y={_f("y", -1, 2)}, '
                  f'opacity={_f("opacity", 0.1, 1)}, '
                  f'speed={_f("speed", 0.05, 3)}')
