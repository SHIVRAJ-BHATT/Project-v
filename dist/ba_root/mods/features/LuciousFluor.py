# ba_meta require api 9
# LuciousFluor v2 - neon players/bots/names, scoreboard bars, bomb shells. No light pools.
from __future__ import annotations

import logging

import bascenev1 as bs

from lucious import config
from lucious.commands import command

log = logging.getLogger('lucious')

# From color.pdf: fully saturated entries only (one channel 1, one 0).
PALETTE = [
    (1.0, 0.0, 0.0), (1.0, 0.5, 0.0), (1.0, 1.0, 0.0), (0.5, 1.0, 0.0),
    (0.0, 1.0, 0.0), (0.0, 1.0, 0.5), (0.0, 1.0, 1.0), (0.0, 0.5, 1.0),
    (0.5, 0.0, 1.0), (1.0, 0.0, 1.0), (1.0, 0.0, 0.5),
]
BOMB_COLORS = {
    'normal': (1.0, 0.5, 0.0), 'ice': (0.0, 1.0, 1.0),
    'impact': (1.0, 0.0, 1.0), 'sticky': (0.5, 1.0, 0.0),
    'land_mine': (1.0, 1.0, 0.0), 'tnt': (1.0, 0.0, 0.0),
}
DEFAULTS = {'players': True, 'names': True, 'scoreboard': True,
            'bombs': True, 'rainbow_bombs': False}
_FLAGS = tuple(DEFAULTS)
_neutral = [0]
_patched: list = []


def _on(key):
    try:
        return bool(config.get('fluor.' + key, DEFAULTS[key]))
    except Exception:
        return DEFAULTS[key]


def _num(key, default, lo, hi):
    try:
        return max(lo, min(hi, float(config.get('fluor.' + key, default))))
    except Exception:
        return default


def _snap(color):
    """Nearest neon colour, keeping the hue so teams stay distinguishable."""
    r, g, b = (float(c) for c in color[:3])
    mx = max(r, g, b)
    if mx <= 0.0 or mx - min(r, g, b) < 0.2:       # grey/white: no hue
        _neutral[0] = (_neutral[0] + 1) % len(PALETTE)
        return PALETTE[_neutral[0]]
    n = (r / mx, g / mx, b / mx)
    return min(PALETTE, key=lambda p: sum((a - c) ** 2 for a, c in zip(p, n)))


def _bright(c, k):
    return tuple(x * k for x in c)


# ---------------------------------------------------------------- characters
def _patch_spaz():
    from bascenev1lib.actor import spaz as mod
    cls = mod.Spaz
    orig = getattr(cls, '_lucious_orig_init', None) or cls.__init__
    cls._lucious_orig_init = orig

    def init(self, *a, **k):
        body = None
        if _on('players'):
            try:
                a = list(a)
                for i, key in enumerate(('color', 'highlight')):
                    src = a[i] if len(a) > i else k.get(key)
                    if src is None:
                        continue
                    new = _bright(_snap(src), _num('glow', 1.3, 0.5, 3.0))
                    if key == 'color':
                        body = new
                    if len(a) > i:
                        a[i] = new
                    else:
                        k[key] = new
            except Exception:
                log.exception('[Lucious] fluor colour failed')
        orig(self, *a, **k)
        if _on('names'):
            try:
                n = self.node
                if n and n.exists():
                    n.name_color = body or _bright(
                        _snap(n.name_color), _num('glow', 1.3, 0.5, 3.0))
            except Exception:
                log.exception('[Lucious] fluor name colour failed')

    cls.__init__ = init
    _patched.append((cls, orig))


# --------------------------------------------------------------------- bombs
def _patch_bomb():
    from bascenev1lib.actor import bomb as mod
    cls = mod.Bomb
    orig = getattr(cls, '_lucious_orig_init', None) or cls.__init__
    cls._lucious_orig_init = orig

    def init(self, *a, **k):
        orig(self, *a, **k)
        if not _on('bombs'):
            return
        try:
            btype = a[2] if len(a) > 2 else k.get('bomb_type', 'normal')
            scale = float(a[4] if len(a) > 4 else k.get('bomb_scale', 1.0))
            col = _bright(BOMB_COLORS.get(btype, (1.0, 0.5, 0.0)),
                          _num('glow', 1.3, 0.5, 3.0))
            shell = bs.newnode('shield', owner=self.node, attrs={
                'color': col, 'radius': _num('shell', 0.32, 0.1, 2.0) * scale})
            self.node.connectattr('position', shell, 'position')
            if _on('rainbow_bombs'):
                keys = {i * 0.35: _bright(PALETTE[i], 1.3)
                        for i in range(len(PALETTE))}
                keys[len(PALETTE) * 0.35] = keys[0.0]
                bs.animate_array(shell, 'color', 3, keys, loop=True)
        except Exception:
            log.exception('[Lucious] fluor bomb shell failed')

    cls.__init__ = init
    _patched.append((cls, orig))


# ---------------------------------------------------------------- scoreboard
def _recolor_entry(e, team):
    c = _snap(team.color)
    g = _bright(c, _num('glow', 1.3, 0.5, 3.0))
    e._barcolor = c
    e._cover_color = c
    k = 0.17 if getattr(e, '_do_cover', False) else 0.1
    e._backing_color = [0.05 + x * k for x in c]
    for attr, col in (('_bar', c), ('_backing', e._backing_color),
                      ('_cover', c)):
        node = getattr(getattr(e, attr, None), 'node', None)
        if node:
            node.color = col
    st = getattr(getattr(e, '_score_text', None), 'node', None)
    if st:
        st.color = g
    nm = getattr(getattr(e, '_name_text', None), 'node', None)
    if nm:
        soft = tuple(x + (1.0 - x) * 0.45 for x in c)
        bs.animate_array(nm, 'color', 3, {0.0: g, 0.8: soft, 1.6: g},
                         loop=True)


def _patch_board():
    from bascenev1lib.actor import scoreboard as mod
    cls = mod._Entry
    orig = getattr(cls, '_lucious_orig_init', None) or cls.__init__
    cls._lucious_orig_init = orig

    def init(self, *a, **k):
        orig(self, *a, **k)
        if not _on('scoreboard'):
            return
        try:
            _recolor_entry(self, a[1] if len(a) > 1 else k.get('team'))
        except Exception:
            log.exception('[Lucious] fluor scoreboard failed')

    cls.__init__ = init
    _patched.append((cls, orig))


@command('fluor', level=80,
         usage='/fluor <players|names|scoreboard|bombs|rainbow_bombs> on|off'
               ' | /fluor glow 0.5-3 | /fluor shell 0.1-2',
         help='Fluorescent colours (new spawns / next game).')
def _fluor(ctx):
    a = [x.lower() for x in ctx.args]
    if len(a) == 2 and a[0] in ('glow', 'shell'):
        lo, hi = (0.5, 3.0) if a[0] == 'glow' else (0.1, 2.0)
        try:
            v = max(lo, min(hi, float(a[1])))
            config.set_value('fluor.' + a[0], v)
            ctx.reply(f'fluor {a[0]} = {v}')
        except Exception:
            ctx.error(f'Usage: /fluor {a[0]} {lo}-{hi}')
        return
    if len(a) == 2 and a[0] in _FLAGS and a[1] in ('on', 'off'):
        config.set_value('fluor.' + a[0], a[1] == 'on')
        ctx.reply(f'fluor {a[0]} = {a[1]} (new spawns / next game)')
        return
    ctx.reply(', '.join(f'{k}={"on" if _on(k) else "off"}' for k in _FLAGS)
              + f', glow={_num("glow", 1.3, 0.5, 3.0)}')


def setup():
    for fn in (_patch_spaz, _patch_bomb, _patch_board):
        try:
            fn()
        except Exception:
            log.exception('[Lucious] fluor patch %s failed', fn.__name__)


def teardown():
    for cls, orig in _patched:
        try:
            cls.__init__ = orig
        except Exception:
            pass
    _patched.clear()
