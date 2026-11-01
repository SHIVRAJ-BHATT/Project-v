# Released under the MIT License. See LICENSE for details.
# ba_meta require api 9
"""LUCIOUS HUD v3 - by Lucious.

    top-center ..... LUCIOUS wordmark (BombSquad logo as the "O"), rainbow
                     wave + shine sweep, rotating tagline
    bottom-left .... owner plate: OWNER LUCIOUS <-> OWNER ROBIN
    bottom-center .. thank-you line
    bottom-right ... next game, rotating tips, online count

Letters use the tag font style: one text node per character,
shadow 1.25, flatness 1.0, per-glyph widths.

Config (config.json -> "textonmap": {...}); every key is optional.
Live tuning: /hud logo <texture> | logosize | logoy | titlescale | titley | reload
"""

from __future__ import annotations

import colorsys
import logging
import math
from typing import Any

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

_LOG = logging.getLogger('LuciousHUD')
_HUD_ATTR = '_lucious_hud3'

DEFAULTS: dict[str, Any] = {
    'enabled': True,
    'logo': True,                 # BombSquad logo replaces the first "O"
    'logo_texture': 'logo',       # try: logo, logoEaster (see /hud logo <name>)
    'logo_size': 1.0,             # multiplier
    'logo_dy': 0.0,               # + up / - down, fine alignment
    'title': 'LUCIOUS',
    'title_scale': 1.5,
    'title_y': -42.0,
    'owners': [['OWNER', 'LUCIOUS'], ['OWNER', 'ROBIN']],
    'taglines': [
        '\ue047 LUCIOUS COMMUNITY SERVER \ue048',
        '\ue043 MADE BY LUCIOUS \ue043',
        '\ue04c FAIR PLAY - NO CHEATS \ue04d',
        '\ue047 HAVE FUN, PLAY SMART \ue048',
    ],
    'tips': [
        'Hold bomb to throw further',
        'Punch near edges to push enemies off',
        'Grab powerups before your enemies do',
        'Use /info to see the server rules',
        'Stay active - AFK players get kicked',
    ],
    'show_online': True,
}

# Visual timing / layout constants
ADV = 23.0            # glyph advance per 1.0 text scale (screen units)
LOGO_SLOT = 1.35      # logo width relative to a normal letter
WAVE_PERIOD = 2.4
RAINBOW_PERIOD = 3.2
SHINE_PERIOD = 5.0
OWNER_X, OWNER_Y = 28, 36
OWNER_SCALE = 1.05


# ----------------------------------------------------------------- config --
def _cfg(key: str) -> Any:
    default = DEFAULTS[key]
    value: Any = default
    if _config is not None:
        path = 'textonmap.' + key
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
        if isinstance(default, float):
            return float(value)
        if isinstance(default, str):
            return str(value)
        if isinstance(default, list):
            return list(value) if isinstance(value, (list, tuple)) and value \
                else default
    except (TypeError, ValueError):
        return default
    return value


def _set_cfg(key: str, value: Any) -> bool:
    if _config is None:
        return False
    path = 'textonmap.' + key
    done = False
    for fn_name in ('set', 'put'):
        fn = getattr(_config, fn_name, None)
        if callable(fn):
            try:
                fn(path, value)
                done = True
                break
            except Exception:
                continue
    if not done:
        return False
    save = getattr(_config, 'save', None)
    if callable(save):
        try:
            save()
        except Exception:
            pass
    return True


# ---------------------------------------------------------------- helpers --
def _alive(node) -> bool:
    try:
        return node is not None and node.exists()
    except Exception:
        return False


def _safe_delete(node) -> None:
    if _alive(node):
        try:
            node.delete()
        except Exception:
            pass


def _gf(ch: str) -> float:
    """Per-glyph width factor (same idea as the tag font table)."""
    if ch.isspace():
        return 0.55
    if ch in ".,:;!|'iIljtfr":
        return 0.68
    if ch in 'WwMmQO@#%&G8':
        return 1.20
    if ch.isdigit():
        return 0.90
    try:
        if ord(ch) > 0xFF:
            return 1.08
    except Exception:
        pass
    return 1.0


def _layout(factors: list[float], scale: float) -> tuple[list[float], float]:
    """Centered x positions + total width."""
    widths = [ADV * scale * f for f in factors]
    gap = 2.0 * scale
    total = sum(widths) + gap * max(0, len(widths) - 1)
    cursor = -total / 2
    xs = []
    for w in widths:
        xs.append(cursor + w / 2)
        cursor += w + gap
    return xs, total


def _hsv(h: float) -> tuple[float, float, float]:
    return colorsys.hsv_to_rgb(h % 1.0, 0.85, 1.0)


def _rainbow_keys(period: float, phase: float, steps: int = 8) -> dict:
    return {period * k / steps: _hsv(phase + k / steps)
            for k in range(steps + 1)}


def _wave_keys(x: float, y: float, amp: float, period: float,
               phase: float, steps: int = 12) -> dict:
    return {period * k / steps:
            (x, y + amp * math.sin(2 * math.pi * k / steps - phase))
            for k in range(steps + 1)}


def _color_keys(colors, step: float) -> dict:
    seq = list(colors) + [colors[0]]
    return {i * step: tuple(c) for i, c in enumerate(seq)}


# -------------------------------------------------------------------- HUD --
class Hud:
    """Built inside an activity context; dies with the activity."""

    def __init__(self) -> None:
        self.nodes: list = []
        self.timers: list = []
        self._name_bases: list = []
        self._name_gloss: list = []
        self._owner_idx = 0
        self._tip_idx = 0
        self._tag_idx = 0
        self._label = None
        self._tagline = None
        self._tagline_pos = (0.0, 0.0)
        self._tip = None
        self._tip_pos = (0.0, 0.0)
        self._online = None
        self._online_text = ''
        for name, build in (
            ('title', self._build_title),
            ('owner plate', self._build_owner),
            ('thanks', self._build_thanks),
            ('info panel', self._build_info),
        ):
            try:
                build()
            except Exception:
                _LOG.exception('LuciousHUD: could not build %s.', name)

    def destroy(self) -> None:
        self.timers.clear()
        for n in self.nodes + self._name_bases + self._name_gloss:
            _safe_delete(n)
        self.nodes.clear()
        self._name_bases = []
        self._name_gloss = []

    # ---------------------------------------------------------- primitives
    def _repeat(self, seconds: float, method) -> None:
        self.timers.append(
            bs.Timer(seconds, bs.WeakCallStrict(method), repeat=True))

    def _text(self, text, pos, *, scale=0.6, color=(1.0, 1.0, 1.0),
              h_align='center', h_attach='center', v_attach='bottom',
              opacity=1.0, shadow=1.25, bucket=None):
        node = bs.newnode('text', attrs={
            'text': str(text), 'position': pos, 'scale': scale,
            'color': color, 'h_align': h_align, 'v_align': 'center',
            'h_attach': h_attach, 'v_attach': v_attach,
            'opacity': opacity, 'shadow': shadow, 'flatness': 1.0,
        })
        (self.nodes if bucket is None else bucket).append(node)
        return node

    def _letter(self, ch, x, y, sc, i, bucket, gloss_bucket, *,
                h_attach='center', v_attach='top', amp=6.0, delay=0.0,
                shine_at=0.8):
        """One tag-font letter: pop-in, wave, rainbow, travelling shine."""
        hue = i * 0.09
        phase = i * 0.55
        pop = {0.0: 0.0, delay: 0.0, delay + 0.22: sc * 1.3,
               delay + 0.42: sc}
        base = self._text(ch, (x, y), scale=0.0, color=_hsv(hue),
                          h_attach=h_attach, v_attach=v_attach, shadow=1.25,
                          bucket=bucket)
        bs.animate(base, 'scale', pop)
        bs.animate_array(base, 'color', 3,
                         _rainbow_keys(RAINBOW_PERIOD, hue), loop=True)
        bs.animate_array(base, 'position', 2,
                         _wave_keys(x, y, amp, WAVE_PERIOD, phase), loop=True)

        t0 = delay + shine_at + i * 0.17
        gloss = self._text(ch, (x, y), scale=0.0, color=(1.0, 1.0, 1.0),
                           h_attach=h_attach, v_attach=v_attach, opacity=0.0,
                           shadow=0.0, bucket=gloss_bucket)
        bs.animate(gloss, 'scale', pop)
        bs.animate_array(gloss, 'position', 2,
                         _wave_keys(x, y, amp, WAVE_PERIOD, phase), loop=True)
        bs.animate(gloss, 'opacity', {
            0.0: 0.0, t0: 0.0, t0 + 0.14: 0.95, t0 + 0.4: 0.0,
            SHINE_PERIOD: 0.0}, loop=True)
        return base, gloss

    # --------------------------------------------------------------- title
    def _build_title(self) -> None:
        word = str(_cfg('title')).upper() or 'LUCIOUS'
        sc = float(_cfg('title_scale'))
        y = float(_cfg('title_y'))

        tex = None
        logo_i = -1
        if _cfg('logo') and 'O' in word:
            try:
                tex = bs.gettexture(str(_cfg('logo_texture')))
                logo_i = word.index('O')
            except Exception:
                _LOG.warning('LuciousHUD: logo texture "%s" unavailable; '
                             'using a normal O.', _cfg('logo_texture'))

        factors = [LOGO_SLOT if i == logo_i else _gf(c)
                   for i, c in enumerate(word)]
        xs, total = _layout(factors, sc)

        for i, ch in enumerate(word):
            if ch.isspace():
                continue
            if i == logo_i:
                self._build_logo(tex, xs[i], y, sc, i)
                continue
            self._letter(ch, xs[i], y, sc, i, self.nodes, self.nodes,
                         amp=6.0, delay=i * 0.1)

        edge = total / 2 + sc * 26
        for sign in (-1, 1):
            orn = self._text('\ue043', (sign * edge, y), scale=sc * 0.6,
                             v_attach='top', color=_hsv(0.0))
            bs.animate_array(orn, 'color', 3, _rainbow_keys(
                RAINBOW_PERIOD, 0.3 if sign < 0 else 0.8), loop=True)
            bs.animate(orn, 'opacity', {0.0: 0.4, 1.2: 1.0, 2.4: 0.4},
                       loop=True)

        taglines = [str(t) for t in _cfg('taglines') if str(t).strip()]
        if taglines:
            self._tagline_pos = (0.0, y - (12 + sc * 20))
            self._tagline = self._text(
                '', self._tagline_pos, scale=0.55, v_attach='top',
                color=(0.9, 0.9, 1.0), opacity=0.0, shadow=1.0)
            bs.animate_array(self._tagline, 'color', 3,
                             _rainbow_keys(6.0, 0.0), loop=True)
            self._show_tagline()
            self._repeat(4.0, self._cycle_tagline)

    def _build_logo(self, tex, x, y, sc, i) -> None:
        size = sc * 27.0 * float(_cfg('logo_size'))
        yy = y + float(_cfg('logo_dy'))
        node = bs.newnode('image', attrs={
            'texture': tex, 'attach': 'topCenter', 'absolute_scale': True,
            'scale': (0.0, 0.0), 'position': (x, yy), 'opacity': 1.0,
        })
        self.nodes.append(node)
        d = i * 0.1
        bs.animate_array(node, 'scale', 2, {
            0.0: (0.0, 0.0), d: (0.0, 0.0),
            d + 0.25: (size * 1.3, size * 1.3), d + 0.45: (size, size)})
        # same wave + phase as the letters, so it stays on their line
        bs.animate_array(node, 'position', 2,
                         _wave_keys(x, yy, 6.0, WAVE_PERIOD, i * 0.55),
                         loop=True)
        bs.animate_array(node, 'color', 3, {
            0.0: (1.0, 1.0, 1.0), 1.2: (1.35, 1.35, 1.35),
            2.4: (1.0, 1.0, 1.0)}, loop=True)
        bs.timer(1.2, bs.WeakCallStrict(self._logo_pulse, node, size))

    def _logo_pulse(self, node, size) -> None:
        if _alive(node):
            bs.animate_array(node, 'scale', 2, {
                0.0: (size, size), 0.7: (size * 1.1, size * 1.1),
                1.4: (size, size)}, loop=True)

    def _cycle_tagline(self) -> None:
        if _alive(self._tagline):
            bs.animate(self._tagline, 'opacity', {0.0: 1.0, 0.25: 0.0})
            bs.timer(0.3, bs.WeakCallStrict(self._show_tagline))

    def _show_tagline(self) -> None:
        node = self._tagline
        lines = [str(t) for t in _cfg('taglines') if str(t).strip()]
        if not _alive(node) or not lines:
            return
        node.text = lines[self._tag_idx % len(lines)]
        self._tag_idx += 1
        x, y = self._tagline_pos
        bs.animate_array(node, 'position', 2, {0.0: (x, y - 8), 0.35: (x, y)})
        bs.animate(node, 'opacity', {0.0: 0.0, 0.35: 1.0})

    # --------------------------------------------------------- owner plate
    def _build_owner(self) -> None:
        self._label = self._text(
            '', (OWNER_X + 4, OWNER_Y + 24), scale=0.55, h_align='left',
            h_attach='left', color=(1.0, 0.84, 0.0), shadow=1.0)
        bs.animate_array(self._label, 'color', 3, _color_keys(
            [(1.0, 0.84, 0.0), (1.0, 1.0, 0.7), (1.0, 0.6, 0.1)], 1.2),
            loop=True)
        self._show_owner()
        self._repeat(4.0, self._show_owner)

    def _owners(self) -> list[tuple[str, str]]:
        out = []
        for item in _cfg('owners'):
            try:
                out.append((str(item[0]).upper(), str(item[1]).upper()))
            except Exception:
                continue
        return out or [('OWNER', 'LUCIOUS')]

    def _retire_name(self) -> None:
        for g in self._name_gloss:
            _safe_delete(g)
        bases = self._name_bases
        for n in bases:
            if _alive(n):
                bs.animate(n, 'opacity', {0.0: 1.0, 0.25: 0.0})
        bs.timer(0.3, bs.WeakCallStrict(self._delete_nodes, list(bases)))
        self._name_bases = []
        self._name_gloss = []

    @staticmethod
    def _delete_nodes(nodes) -> None:
        for n in nodes:
            _safe_delete(n)

    def _show_owner(self) -> None:
        entries = self._owners()
        label, name = entries[self._owner_idx % len(entries)]
        self._owner_idx += 1
        self._retire_name()

        if _alive(self._label):
            self._label.text = f'\ue04c {label} \ue04d'
            bs.animate(self._label, 'opacity', {0.0: 0.0, 0.3: 1.0})

        chars = ['\ue043', ' '] + list(name)
        xs, total = _layout([_gf(c) for c in chars], OWNER_SCALE)
        for i, (ch, x) in enumerate(zip(chars, xs)):
            if ch == ' ':
                continue
            self._letter(ch, OWNER_X + total / 2 + x, OWNER_Y, OWNER_SCALE, i,
                         self._name_bases, self._name_gloss,
                         h_attach='left', v_attach='bottom', amp=3.5,
                         delay=i * 0.05, shine_at=0.5)

    # -------------------------------------------------------------- thanks
    def _build_thanks(self) -> None:
        n = self._text('\ue043 THANKS FOR PLAYING ON LUCIOUS \ue043', (0, 18),
                       scale=0.55, color=(1.0, 0.7, 0.85), shadow=1.0)
        bs.animate_array(n, 'color', 3, _color_keys(
            [(1.0, 0.7, 0.85), (0.7, 0.95, 1.0), (1.0, 0.95, 0.6)], 3.0),
            loop=True)

    # ---------------------------------------------------------- info panel
    @staticmethod
    def _next_map() -> str:
        try:
            session = bs.get_foreground_host_session()
            desc = session.get_next_game_description() if session else None
            return desc.evaluate() if desc is not None else '-'
        except Exception:
            return '-'

    def _build_info(self) -> None:
        x, y, step = -25, 16, 24
        self._text(f'\ue047 NEXT \ue048 : {self._next_map()}', (x, y),
                   scale=0.7, h_align='right', h_attach='right', shadow=1.0)
        y += step

        if [t for t in _cfg('tips') if str(t).strip()]:
            self._tip_pos = (x, y)
            self._tip = self._text('', self._tip_pos, scale=0.6,
                                   h_align='right', h_attach='right',
                                   color=(0.75, 0.9, 1.0), opacity=0.0,
                                   shadow=1.0)
            self._show_tip()
            self._repeat(6.0, self._cycle_tip)
            y += step

        if _cfg('show_online'):
            self._online = self._text('', (x, y), scale=0.6, h_align='right',
                                      h_attach='right',
                                      color=(0.55, 1.0, 0.65), shadow=1.0)
            self._update_online()
            self._repeat(5.0, self._update_online)

    def _cycle_tip(self) -> None:
        if _alive(self._tip):
            bs.animate(self._tip, 'opacity', {0.0: 1.0, 0.3: 0.0})
            bs.timer(0.3, bs.WeakCallStrict(self._show_tip))

    def _show_tip(self) -> None:
        node = self._tip
        tips = [str(t) for t in _cfg('tips') if str(t).strip()]
        if not _alive(node) or not tips:
            return
        node.text = '\ue04c ' + tips[self._tip_idx % len(tips)]
        self._tip_idx += 1
        x, y = self._tip_pos
        bs.animate_array(node, 'position', 2, {0.0: (x + 30, y), 0.35: (x, y)})
        bs.animate(node, 'opacity', {0.0: 0.0, 0.35: 1.0})

    def _update_online(self) -> None:
        node = self._online
        if not _alive(node):
            return
        try:
            session = bs.get_foreground_host_session()
            count = len(session.sessionplayers) if session else 0
            size = bs.get_public_party_max_size()
            suffix = f'/{size}' if size else ''
        except Exception:
            count, suffix = 0, ''
        text = f'\ue047 ONLINE : {count}{suffix}'
        if text != self._online_text:
            self._online_text = text
            node.text = text


# ---------------------------------------------------------------- plumbing --
def _ensure(activity, force: bool = False) -> bool:
    if not isinstance(activity, bs.GameActivity) or not _cfg('enabled'):
        return False
    old = getattr(activity, _HUD_ATTR, None)
    if old is not None:
        if not force:
            return True
        try:
            with activity.context:
                old.destroy()
        except Exception:
            _LOG.exception('LuciousHUD: old HUD cleanup failed.')
    try:
        with activity.context:
            hud = Hud()
        setattr(activity, _HUD_ATTR, hud)
        return True
    except Exception:
        _LOG.exception('LuciousHUD: could not create HUD.')
        return False


def _late() -> None:
    _ensure(bs.get_foreground_host_activity())


def _on_begin(*args, **kwargs) -> None:
    act = None
    for a in list(args) + list(kwargs.values()):
        if isinstance(a, bs.Activity):
            act = a
            break
    if act is None:
        act = bs.get_foreground_host_activity()
    if act is not None:
        _ensure(act)
    # retry once in case the activity was not ready yet (idempotent)
    try:
        bs.apptimer(0.5, _late)
    except Exception:
        pass


def _reply(ctx, msg: str) -> None:
    for name in ('reply', 'send', 'say'):
        fn = getattr(ctx, name, None)
        if callable(fn):
            try:
                fn(msg)
                return
            except Exception:
                pass
    try:
        bs.broadcastmessage(msg, color=(0.5, 1.0, 0.6), transient=True)
    except Exception:
        pass


_NUM = {
    'logosize': ('logo_size', 0.3, 3.0),
    'logoy': ('logo_dy', -40.0, 40.0),
    'titlescale': ('title_scale', 0.8, 2.5),
    'titley': ('title_y', -120.0, -10.0),
}


def _hud_cmd(ctx) -> None:
    args = [str(a) for a in (getattr(ctx, 'args', None) or [])]
    sub = args[0].lower() if args else 'info'

    if sub == 'reload':
        ok = _ensure(bs.get_foreground_host_activity(), force=True)
        _reply(ctx, 'HUD rebuilt.' if ok else 'No game activity to rebuild.')
        return

    if sub == 'logo' and len(args) > 1:
        _set_cfg('logo_texture', args[1])
        _set_cfg('logo', True)
        _ensure(bs.get_foreground_host_activity(), force=True)
        _reply(ctx, f'Logo texture: {args[1]} (blank/black = wrong name, '
                    'try logo, logoEaster).')
        return

    if sub in _NUM and len(args) > 1:
        key, lo, hi = _NUM[sub]
        try:
            value = max(lo, min(hi, float(args[1])))
        except ValueError:
            _reply(ctx, f'Use a number between {lo} and {hi}.')
            return
        _set_cfg(key, value)
        _ensure(bs.get_foreground_host_activity(), force=True)
        _reply(ctx, f'{key} = {value}')
        return

    _reply(ctx, 'Usage: /hud logo <texture> | logosize <0.3-3> | '
                'logoy <-40..40> | titlescale <0.8-2.5> | titley <-120..-10> '
                '| reload')


def setup() -> None:
    if _bus is not None:
        _bus.subscribe('activity_begin', _on_begin, priority=60)
    if _command is not None:
        try:
            _command('hud', level=80)(_hud_cmd)
        except Exception:
            _LOG.warning('LuciousHUD: /hud command not registered.',
                         exc_info=True)
    try:  # hot reload: rebuild on the running game
        act = bs.get_foreground_host_activity()
        has_begun = getattr(act, 'has_begun', None)
        if act is not None and (not callable(has_begun) or has_begun()):
            _ensure(act, force=True)
    except Exception:
        _LOG.exception('LuciousHUD: setup rebuild failed.')


def teardown() -> None:
    if _bus is not None:
        try:
            _bus.unsubscribe('activity_begin', _on_begin)
        except Exception:
            pass
    try:
        act = bs.get_foreground_host_activity()
        hud = getattr(act, _HUD_ATTR, None) if act is not None else None
        if hud is not None:
            with act.context:
                hud.destroy()
            setattr(act, _HUD_ATTR, None)
    except Exception:
        _LOG.exception('LuciousHUD: teardown failed.')
