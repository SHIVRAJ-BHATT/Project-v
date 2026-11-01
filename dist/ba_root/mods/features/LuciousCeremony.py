# Released under the MIT License. See LICENSE for details.
# ba_meta require api 9
"""Lucious Royal Ceremony - cinematic score-screen awards (API 9).

Letterbox bars, orbiting rainbow stage lights, falling crowns, a gold /
silver / bronze podium for the top 3, and an ALL HAIL <CHAMPION> banner
in the tag-font letter style.

Standings come from sessionteam.customdata['score'] (series wins).
Live commands (level 80): /ceremony on|off|rain|lights|bars|podium|sound
                          /ceremony scale <n> | y <n> | info
Config (config.json -> "ceremony": {...}); every key is optional.
"""

from __future__ import annotations

import colorsys
import functools
import logging
import math
import random
from typing import Any

import bascenev1 as bs

try:
    from lucious import config as _config
except Exception:
    _config = None
try:
    from lucious.commands import command as _command
except Exception:
    _command = None

_LOG = logging.getLogger('LuciousCeremony')
_ATTR = '_lucious_ceremony'
CROWN = '\ue043'

DEFAULTS: dict[str, Any] = {
    'enabled': True,
    'bars': True,
    'lights': True,
    'rain': True,
    'podium': True,
    'sound': True,
    'announce': True,
    'rain_scale': 0.16,     # in-world crown size
    'rain_max': 22,         # max crowns alive at once
    'podium_y': 54.0,       # podium base, pixels above the screen bottom
    'block_w': 150.0,
    'brand': 'LUCIOUS ROYAL CEREMONY',
}

WAVE_PERIOD = 2.4
RAINBOW_PERIOD = 3.2
SHINE_PERIOD = 5.0
ADV = 23.0
BAR_H = 46.0

GOLDS = [(1.0, 0.84, 0.15), (1.0, 0.96, 0.60), (1.0, 0.66, 0.12)]
PLACE_COLORS = [(1.0, 0.82, 0.20), (0.80, 0.86, 0.96), (0.86, 0.50, 0.25)]


# ----------------------------------------------------------------- config --
def _cfg(key: str) -> Any:
    default = DEFAULTS[key]
    value: Any = None
    if _config is not None:
        path = 'ceremony.' + key
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
    except (TypeError, ValueError):
        return default
    return value


def _set_cfg(key: str, value: Any) -> bool:
    if _config is None:
        return False
    path = 'ceremony.' + key
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
    if done:
        save = getattr(_config, 'save', None)
        if callable(save):
            try:
                save()
            except Exception:
                pass
    return done


# ---------------------------------------------------------------- helpers --
def _alive(node: Any) -> bool:
    try:
        return node is not None and node.exists()
    except Exception:
        return False


def _safe_delete(node: Any) -> None:
    if _alive(node):
        try:
            node.delete()
        except Exception:
            pass


def _tex(name: str) -> Any:
    try:
        return bs.gettexture(name)
    except Exception:
        return None


def _play(name: str, volume: float = 1.0) -> None:
    if not _cfg('sound'):
        return
    try:
        bs.getsound(name).play(volume=volume)
    except Exception:
        pass


def _hsv(h: float) -> tuple[float, float, float]:
    return colorsys.hsv_to_rgb(h % 1.0, 0.85, 1.0)


def _rainbow_keys(period: float, phase: float, steps: int = 8) -> dict:
    return {period * k / steps: _hsv(phase + k / steps)
            for k in range(steps + 1)}


def _color_keys(colors: list, step: float) -> dict:
    seq = list(colors) + [colors[0]]
    return {i * step: tuple(c) for i, c in enumerate(seq)}


def _wave_keys(x: float, y: float, amp: float, period: float,
               phase: float, steps: int = 12) -> dict:
    return {period * k / steps:
            (x, y + amp * math.sin(2 * math.pi * k / steps - phase))
            for k in range(steps + 1)}


def _gf(ch: str) -> float:
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


def _layout(chars: list[str], scale: float) -> tuple[list[float], float]:
    widths = [ADV * scale * _gf(c) for c in chars]
    gap = 2.0 * scale
    total = sum(widths) + gap * max(0, len(widths) - 1)
    cursor = -total / 2
    xs = []
    for w in widths:
        xs.append(cursor + w / 2)
        cursor += w + gap
    return xs, total


def _fit(chars: list[str], scale: float,
         max_w: float) -> tuple[list[float], float]:
    xs, total = _layout(chars, scale)
    if total > max_w:
        scale *= max_w / total
        xs, total = _layout(chars, scale)
    return xs, scale


def _nice(color: Any) -> tuple[float, float, float]:
    """Brighten a team colour so names stay readable on dark screens."""
    try:
        r, g, b = (float(c) for c in tuple(color)[:3])
    except Exception:
        return (1.0, 1.0, 1.0)
    m = max(r, g, b, 0.01)
    k = 1.0 / m
    return (min(1.0, 0.35 + r * k * 0.65), min(1.0, 0.35 + g * k * 0.65),
            min(1.0, 0.35 + b * k * 0.65))


# -------------------------------------------------------------- standings --
def _standings(act: Any) -> list[tuple[int, str, Any]]:
    session = getattr(act, 'session', None)
    if session is None:
        try:
            session = bs.get_foreground_host_session()
        except Exception:
            session = None
    rows: list[tuple[int, str, Any]] = []
    for team in list(getattr(session, 'sessionteams', None) or []):
        try:
            score = int(team.customdata.get('score', 0))
        except Exception:
            score = 0
        name: Any = getattr(team, 'name', '?')
        try:
            name = name.evaluate()
        except Exception:
            name = str(name)
        rows.append((score, str(name).upper()[:18],
                     getattr(team, 'color', (1, 1, 1))))
    rows.sort(key=lambda r: -r[0])
    return rows


# --------------------------------------------------------------- ceremony --
class Ceremony:
    """Built inside the score-screen activity context; dies with it."""

    def __init__(self, act: Any) -> None:
        self.nodes: list = []
        self.timers: list = []
        self.crowns: list = []
        rows = _standings(act)
        self.rows = rows
        has_winner = bool(rows) and rows[0][0] > 0

        for name, build in (
            ('bars', self._build_bars),
            ('lights', self._build_lights),
            ('rain', self._build_rain),
        ):
            if name == 'rain' or _cfg(name):
                try:
                    build()
                except Exception:
                    _LOG.exception('Ceremony: %s failed.', name)

        if has_winner:
            try:
                reveal = 2.3
                if _cfg('podium'):
                    self._build_podium(rows[:3])
                self._build_title(rows, reveal)
                self._schedule_reveal(rows, reveal)
            except Exception:
                _LOG.exception('Ceremony: champion part failed.')

    # ---------------------------------------------------------- primitives
    def _text(self, text, pos, *, scale=0.6, color=(1.0, 1.0, 1.0),
              h_attach='center', v_attach='bottom', opacity=1.0,
              shadow=1.25, maxwidth=0.0, bucket=None):
        attrs = {
            'text': str(text), 'position': pos, 'scale': scale,
            'color': color, 'h_align': 'center', 'v_align': 'center',
            'h_attach': h_attach, 'v_attach': v_attach,
            'opacity': opacity, 'shadow': shadow, 'flatness': 1.0,
        }
        if maxwidth:
            attrs['maxwidth'] = maxwidth
        node = bs.newnode('text', attrs=attrs)
        (self.nodes if bucket is None else bucket).append(node)
        return node

    def _later(self, delay: float, fn, *args) -> None:
        bs.timer(delay, functools.partial(fn, *args))

    # ---------------------------------------------------------------- bars
    def _build_bars(self) -> None:
        tex = _tex('white')
        if tex is None:
            return
        for attach, sign in (('topCenter', -1.0), ('bottomCenter', 1.0)):
            node = bs.newnode('image', attrs={
                'texture': tex, 'attach': attach, 'absolute_scale': True,
                'scale': (2600.0, 0.0), 'position': (0.0, 0.0),
                'color': (0.0, 0.0, 0.0), 'opacity': 1.0})
            self.nodes.append(node)
            bs.animate_array(node, 'scale', 2, {
                0.0: (2600.0, 0.0), 0.8: (2600.0, BAR_H)})
            bs.animate_array(node, 'position', 2, {
                0.0: (0.0, 0.0), 0.8: (0.0, sign * BAR_H / 2)})
        brand = str(_cfg('brand'))
        if brand:
            n = self._text(f'{CROWN}  {brand}  {CROWN}', (0, BAR_H / 2),
                           scale=0.5, shadow=0.0, opacity=0.0)
            bs.animate_array(n, 'color', 3, _color_keys(GOLDS, 1.5),
                             loop=True)
            bs.animate(n, 'opacity', {0.0: 0.0, 1.0: 0.0, 1.6: 1.0})

    # -------------------------------------------------------------- lights
    def _build_lights(self) -> None:
        radius, period, steps = 9.0, 9.0, 16
        for k in range(3):
            off = k * 2 * math.pi / 3
            light = bs.newnode('light', attrs={
                'position': (radius, 7.0, 0.0), 'radius': 1.6,
                'intensity': 0.0, 'color': _hsv(k / 3),
                'height_attenuated': False, 'volume_intensity_scale': 8.0})
            self.nodes.append(light)
            keys = {}
            for s in range(steps + 1):
                a = 2 * math.pi * s / steps + off
                keys[period * s / steps] = (
                    radius * math.cos(a), 7.0 + 1.5 * math.sin(a * 2),
                    radius * 0.6 * math.sin(a))
            bs.animate_array(light, 'position', 3, keys, loop=True)
            bs.animate_array(light, 'color', 3,
                             _rainbow_keys(6.0, k / 3), loop=True)
            bs.animate(light, 'intensity', {0.0: 0.0, 1.0: 1.4})

    # ---------------------------------------------------------------- rain
    def _build_rain(self) -> None:
        if not _cfg('rain'):
            return
        self.timers.append(
            bs.Timer(0.45, bs.WeakCallStrict(self._drop_crown), repeat=True))

    def _drop_crown(self) -> None:
        self.crowns = [n for n in self.crowns if _alive(n)]
        if len(self.crowns) >= int(_cfg('rain_max')):
            return
        x = random.uniform(-14.0, 14.0)
        z = random.uniform(-8.0, 6.0)
        drift = random.uniform(-1.5, 1.5)
        fall = random.uniform(2.6, 4.0)
        sc = float(_cfg('rain_scale')) * random.uniform(0.7, 1.3)
        node = bs.newnode('text', attrs={
            'text': CROWN, 'in_world': True, 'position': (x, 16.0, z),
            'scale': sc, 'color': random.choice(GOLDS),
            'h_align': 'center', 'v_align': 'center',
            'shadow': 0.0, 'flatness': 1.0})
        bs.animate_array(node, 'position', 3, {
            0.0: (x, 16.0, z), fall: (x + drift, -2.0, z)})
        bs.animate(node, 'opacity', {
            0.0: 0.0, 0.3: 1.0, fall - 0.4: 1.0, fall: 0.0})
        self.crowns.append(node)
        bs.timer(fall + 0.1, functools.partial(_safe_delete, node))

    # -------------------------------------------------------------- podium
    def _build_podium(self, rows) -> None:
        tex = _tex('white')
        base = float(_cfg('podium_y'))
        width = float(_cfg('block_w'))
        gap = 10.0
        # (side, height) for place 1, 2, 3
        slots = [(0, 112.0), (-1, 82.0), (1, 60.0)]
        last_delay = 0.0
        for place, (side, h) in enumerate(slots):
            if place >= len(rows):
                break
            score, name, tcolor = rows[place]
            x = side * (width + gap)
            delay = 0.6 + (2 - place) * 0.7
            done = delay + 0.6
            last_delay = max(last_delay, done)
            col = PLACE_COLORS[place]
            if tex is not None:
                block = bs.newnode('image', attrs={
                    'texture': tex, 'attach': 'bottomCenter',
                    'absolute_scale': True, 'scale': (width, 0.0),
                    'position': (x, base), 'color': tuple(c * 0.55
                                                          for c in col),
                    'opacity': 1.0})
                self.nodes.append(block)
                bs.animate_array(block, 'scale', 2, {
                    0.0: (width, 0.0), delay: (width, 0.0),
                    done: (width, h)})
                bs.animate_array(block, 'position', 2, {
                    0.0: (x, base), delay: (x, base),
                    done: (x, base + h / 2)})
                strip = bs.newnode('image', attrs={
                    'texture': tex, 'attach': 'bottomCenter',
                    'absolute_scale': True, 'scale': (width, 6.0),
                    'position': (x, base + h - 3), 'color': col,
                    'opacity': 0.0})
                self.nodes.append(strip)
                bs.animate(strip, 'opacity', {
                    0.0: 0.0, done: 0.0, done + 0.3: 1.0})
            num = self._text(str(place + 1), (x, base + h / 2 + 8),
                             scale=1.7, color=col, opacity=0.0)
            bs.animate(num, 'opacity', {0.0: 0.0, done: 0.0,
                                        done + 0.3: 0.9})
            pts = self._text(f'{score} WIN' + ('' if score == 1 else 'S'),
                             (x, base + h / 2 - 26), scale=0.5,
                             color=(1.0, 1.0, 1.0), shadow=1.0,
                             opacity=0.0)
            bs.animate(pts, 'opacity', {0.0: 0.0, done: 0.0,
                                        done + 0.3: 0.9})
            nm = self._text(name, (x, base + h + 22), scale=0.0,
                            color=_nice(tcolor), maxwidth=width + 30)
            bs.animate(nm, 'scale', {
                0.0: 0.0, done: 0.0, done + 0.2: 0.95, done + 0.4: 0.8})
            if place == 0:
                crown = self._text(CROWN, (x, base + h + 62), scale=0.0,
                                   color=GOLDS[0], shadow=1.0)
                bs.animate(crown, 'scale', {
                    0.0: 0.0, done + 0.4: 0.0, done + 0.8: 2.2,
                    done + 1.0: 1.8})
                bs.animate_array(crown, 'position', 2, {
                    0.0: (x, base + h + 62), 1.0: (x, base + h + 70),
                    2.0: (x, base + h + 62)}, loop=True)
                bs.animate_array(crown, 'color', 3,
                                 _color_keys(GOLDS, 0.8), loop=True)

    # --------------------------------------------------------------- title
    def _letter(self, ch, x, y, sc, i, delay, gold, amp) -> None:
        hue, phase = i * 0.09, i * 0.55
        pop = {0.0: 0.0, delay: 0.0, delay + 0.22: sc * 1.3,
               delay + 0.42: sc}
        base = self._text(ch, (x, y), scale=0.0, color=GOLDS[0],
                          v_attach='top')
        bs.animate(base, 'scale', pop)
        keys = (_color_keys(GOLDS, 0.9) if gold
                else _rainbow_keys(RAINBOW_PERIOD, hue))
        bs.animate_array(base, 'color', 3, keys, loop=True)
        bs.animate_array(base, 'position', 2,
                         _wave_keys(x, y, amp, WAVE_PERIOD, phase),
                         loop=True)
        t0 = delay + 0.8 + i * 0.15
        gloss = self._text(ch, (x, y), scale=0.0, v_attach='top',
                           opacity=0.0, shadow=0.0)
        bs.animate(gloss, 'scale', pop)
        bs.animate_array(gloss, 'position', 2,
                         _wave_keys(x, y, amp, WAVE_PERIOD, phase),
                         loop=True)
        bs.animate(gloss, 'opacity', {
            0.0: 0.0, t0: 0.0, t0 + 0.14: 0.95, t0 + 0.4: 0.0,
            SHINE_PERIOD: 0.0}, loop=True)

    def _word(self, text: str, y: float, scale: float, max_w: float,
              start: float, gold: bool, amp: float) -> None:
        chars = list(text)
        xs, sc = _fit(chars, scale, max_w)
        for i, (ch, x) in enumerate(zip(chars, xs)):
            if ch.isspace():
                continue
            self._letter(ch, x, y, sc, i, start + i * 0.07, gold, amp)

    def _champion(self, rows) -> tuple[str, str]:
        top = rows[0][0]
        winners = [r[1] for r in rows if r[0] == top][:2]
        if len(winners) > 1:
            return 'CO-CHAMPIONS', ' & '.join(winners)
        return 'ALL HAIL', winners[0]

    def _build_title(self, rows, start: float) -> None:
        head, name = self._champion(rows)
        y1 = -(BAR_H + 26.0)
        self._word(f'{CROWN} {head} {CROWN}', y1, 0.95, 640.0, start,
                   True, 4.0)
        self._word(name, y1 - 46.0, 1.55, 820.0, start + 0.5, False, 6.0)

    # -------------------------------------------------------------- reveal
    def _schedule_reveal(self, rows, start: float) -> None:
        self._later(start, _play, 'gong', 1.0)
        self._later(start + 0.25, _play, 'orchestraHit', 0.9)
        self._later(start + 0.5, _play, 'cheer', 1.0)
        for i in range(6):
            self._later(start + 0.3 + i * 0.45, self._burst)
        if _cfg('announce'):
            _head, name = self._champion(rows)
            self._later(start + 0.6, self._announce, name)

    def _burst(self) -> None:
        pos = (random.uniform(-9.0, 9.0), random.uniform(5.0, 9.0),
               random.uniform(-3.0, 3.0))
        color = random.choice(GOLDS + [_hsv(random.random())])
        try:
            node = bs.newnode('explosion', attrs={
                'position': pos, 'radius': 3.0, 'big': False})
            node.color = tuple(c * 1.6 for c in color)
            bs.timer(1.0, functools.partial(_safe_delete, node))
            bs.emitfx(position=pos, velocity=(0.0, 0.0, 0.0), count=30,
                      scale=1.5, spread=1.2, chunk_type='spark')
        except Exception:
            pass

    @staticmethod
    def _announce(name: str) -> None:
        try:
            bs.broadcastmessage(f'{CROWN} {name} RULES THE SERVER {CROWN}',
                                color=(1.0, 0.85, 0.2), transient=True)
        except Exception:
            pass

    def destroy(self) -> None:
        self.timers.clear()
        for n in self.nodes + self.crowns:
            _safe_delete(n)
        self.nodes.clear()
        self.crowns.clear()


# ---------------------------------------------------------------- plumbing --
def _is_score(act: Any) -> bool:
    base = getattr(bs, 'ScoreScreenActivity', None)
    return base is not None and isinstance(act, base)


def _ensure(act: Any, force: bool = False) -> bool:
    if act is None or not _is_score(act) or not _cfg('enabled'):
        return False
    old = getattr(act, _ATTR, None)
    if old is not None:
        if not force:
            return True
        try:
            with act.context:
                old.destroy()
        except Exception:
            _LOG.exception('Ceremony: old cleanup failed.')
    try:
        with act.context:
            cer = Ceremony(act)
        setattr(act, _ATTR, cer)
        return True
    except Exception:
        _LOG.exception('Ceremony: could not build.')
        return False


_PATCH_FLAG = '_lucious_ceremony_patch'


def _wrap_begin(orig):
    @functools.wraps(orig)
    def on_begin(self, *args, **kwargs):
        result = orig(self, *args, **kwargs)
        try:
            _ensure(self)
        except Exception:
            _LOG.exception('Ceremony: on_begin hook failed.')
        return result
    setattr(on_begin, _PATCH_FLAG, True)
    return on_begin


def _install() -> None:
    cls = getattr(bs, 'ScoreScreenActivity', None)
    if cls is None:
        _LOG.warning('Ceremony: bs.ScoreScreenActivity not found.')
        return
    cur = cls.on_begin
    if getattr(cur, _PATCH_FLAG, False):
        cur = getattr(cur, '__wrapped__', cur)
    cls._lucious_ceremony_own = 'on_begin' in cls.__dict__
    cls._lucious_ceremony_orig = cur
    cls.on_begin = _wrap_begin(cur)


def _uninstall() -> None:
    cls = getattr(bs, 'ScoreScreenActivity', None)
    if cls is None or not getattr(cls.on_begin, _PATCH_FLAG, False):
        return
    orig = getattr(cls, '_lucious_ceremony_orig', None)
    if getattr(cls, '_lucious_ceremony_own', False) and orig is not None:
        cls.on_begin = orig
    else:
        try:
            del cls.on_begin
        except Exception:
            if orig is not None:
                cls.on_begin = orig


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
        bs.broadcastmessage(msg, color=(1.0, 0.85, 0.2), transient=True)
    except Exception:
        pass


_TOGGLES = ('enabled', 'bars', 'lights', 'rain', 'podium', 'sound',
            'announce')
_ALIASES = {'on': 'enabled', 'off': 'enabled'}
_NUM = {'scale': ('rain_scale', 0.03, 0.6), 'y': ('podium_y', 20.0, 300.0)}


def _cmd(ctx) -> None:
    args = [str(a).lower() for a in (getattr(ctx, 'args', None) or [])]
    sub = args[0] if args else 'info'
    act = bs.get_foreground_host_activity()

    if sub in ('on', 'off'):
        _set_cfg('enabled', sub == 'on')
        _reply(ctx, f'Ceremony {sub}. Applies from the next score screen.')
        return
    if sub in _TOGGLES and sub != 'enabled':
        cur = bool(_cfg(sub))
        if len(args) > 1 and args[1] in ('on', 'off'):
            cur = args[1] == 'off'
        _set_cfg(sub, not cur)
        _reply(ctx, f'ceremony.{sub} = {not cur}')
        if act is not None:
            _ensure(act, force=True)
        return
    if sub in _NUM and len(args) > 1:
        key, lo, hi = _NUM[sub]
        try:
            value = max(lo, min(hi, float(args[1])))
        except ValueError:
            _reply(ctx, f'Use a number between {lo} and {hi}.')
            return
        _set_cfg(key, value)
        _reply(ctx, f'{key} = {value}')
        if act is not None:
            _ensure(act, force=True)
        return
    if sub == 'info':
        rows = _standings(act) if act is not None else []
        shown = ', '.join(f'{n}={s}' for s, n, _c in rows[:4]) or 'none'
        kind = 'score screen' if _is_score(act) else 'not a score screen'
        _reply(ctx, f'Ceremony: {kind}; standings: {shown}')
        return
    _reply(ctx, 'Usage: /ceremony on|off|rain|lights|bars|podium|sound|'
                'announce | scale <0.03-0.6> | y <20-300> | info')


def setup() -> None:
    _install()
    if _command is not None:
        try:
            _command('ceremony', level=80)(_cmd)
        except Exception:
            _LOG.warning('Ceremony: /ceremony not registered.',
                         exc_info=True)
    try:
        act = bs.get_foreground_host_activity()
        if _is_score(act):
            _ensure(act, force=True)
    except Exception:
        _LOG.exception('Ceremony: setup rebuild failed.')


def teardown() -> None:
    try:
        act = bs.get_foreground_host_activity()
        cer = getattr(act, _ATTR, None) if act is not None else None
        if cer is not None:
            with act.context:
                cer.destroy()
            setattr(act, _ATTR, None)
    except Exception:
        _LOG.exception('Ceremony: teardown failed.')
    _uninstall()
