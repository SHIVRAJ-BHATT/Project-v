# mods/lucious/tags/view.py
"""Builds the nodes for one player's head tag + ping."""
from __future__ import annotations

import colorsys
import math

import bascenev1 as bs

SHORTHAND = {'\\c': '\ue043', '\\d': '\ue048', '\\s': '\ue046',
             '\\h': '\ue049', '\\f': '\ue04f', '\\t': '\ue01f',
             '\\n': '\ue04b'}
STEPS = 8
MAX_CHARS = 32
NM_ADVANCE, NM_GAP, NM_MAX_WIDTH = 0.18, 0.018, 3.6
SPECTRUM = ((1.00, 0.16, 0.18), (1.00, 0.46, 0.05), (1.00, 0.96, 0.08),
            (0.18, 1.00, 0.26), (0.05, 0.92, 1.00), (0.14, 0.42, 1.00),
            (0.62, 0.16, 1.00), (1.00, 0.18, 0.82))


def normalize(text: str) -> str:
    for key, val in SHORTHAND.items():
        text = text.replace(key, val)
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS - 1] + '\u2026'
    return text


def get_ping(client_id: int):
    if client_id is None or client_id < 0:
        return 0
    try:
        import _bascenev1
        p = _bascenev1.get_client_ping(int(client_id))
        return None if p is None or p < 0 else int(p)
    except Exception:
        return None


def ping_color(ms: int):
    if ms < 80:
        return (0.2, 1.0, 0.2)
    if ms < 160:
        return (1.0, 1.0, 0.2)
    return (1.0, 0.2, 0.2)


def _rainbow(shift: float, k: int):
    r, g, b = colorsys.hsv_to_rgb((k / STEPS + shift) % 1.0, 0.85, 1.0)
    return (r * 1.35, g * 1.35, b * 1.35)


def _glyph_factor(ch: str) -> float:
    if ch.isspace():
        return 0.55
    if ch in ".,:;!|'iIljtfr":
        return 0.68
    if ch in 'WwMmQO@#%&G8':
        return 1.20
    if ch.isdigit():
        return 0.90
    if ord(ch) > 0xFF:
        return 1.08
    return 1.0


def _nm_layout(chars, base: float):
    widths = [NM_ADVANCE * _glyph_factor(c) for c in chars]
    gaps = NM_GAP * max(0, len(chars) - 1)
    raw = sum(widths) + gaps
    f = min(1.0, NM_MAX_WIDTH / raw) if raw > 0 else 1.0
    ws = [w * f for w in widths]
    gap = NM_GAP * f
    cur = -0.5 * (sum(ws) + gap * max(0, len(chars) - 1))
    xs = []
    for w in ws:
        xs.append(cur + w * 0.5)
        cur += w + gap
    return base * f, xs


class TagView:
    def __init__(self, node, text, style, color, client_id, show_ping,
                 cfg, sig):
        self.node = node
        self.sig = sig
        self.client_id = client_id
        self.nodes: list = []
        self.ping_text = None
        text = normalize(text or '')
        if text:
            if style == 'clay':
                self._build_clay(text, color, cfg)
            else:
                self._build_nm(text, color, cfg)
        if show_ping:
            self._build_ping(cfg)

    def _anchor(self, offset):
        m = bs.newnode('math', owner=self.node,
                       attrs={'input1': offset, 'operation': 'add'})
        self.node.connectattr('torso_position', m, 'input2')
        self.nodes.append(m)
        return m

    def _text(self, **attrs):
        base = {'in_world': True, 'shadow': 1.0, 'flatness': 1.0,
                'h_align': 'center'}
        base.update(attrs)
        t = bs.newnode('text', owner=self.node, attrs=base)
        self.nodes.append(t)
        return t

    def _build_clay(self, text, color, cfg):
        scale = float(cfg['clay_scale'])
        spacing = scale * float(cfg['spacing_factor'])
        height = float(cfg['height'])
        amp = float(cfg['wave_amp'])
        period = max(0.2, float(cfg['wave_period']))
        rperiod = max(0.5, float(cfg['rainbow_period']))
        n = len(text)
        for i, ch in enumerate(text):
            if ch == ' ':
                continue
            dx = (i - (n - 1) / 2.0) * spacing
            m = self._anchor((dx, height, 0.0))
            if amp > 0:
                keys = {}
                for k in range(STEPS + 1):
                    phase = 2 * math.pi * k / STEPS - i * 0.7
                    keys[period * k / STEPS] = (
                        dx, height + amp * math.sin(phase), 0.0)
                bs.animate_array(m, 'input1', 3, keys, loop=True)
            t = self._text(text=ch, big=True, scale=scale,
                           color=tuple(color) if color else (1, 1, 1))
            m.connectattr('output', t, 'position')
            if not color:
                shift = i / max(1, n) * 0.6
                bs.animate_array(
                    t, 'color', 3,
                    {rperiod * k / STEPS: _rainbow(shift, k)
                     for k in range(STEPS + 1)}, loop=True)

    def _build_nm(self, text, color, cfg):
        """Lucious-script style: normal font, one node per glyph."""
        chars = list(text)
        scale, xs = _nm_layout(chars, float(cfg['nm_scale']))
        height = float(cfg['nm_height'])
        period = max(0.5, float(cfg['rainbow_period']))
        n = max(1, len(chars))
        for i, (ch, x) in enumerate(zip(chars, xs)):
            if ch.isspace():
                continue
            m = self._anchor((x, height, 0.0))
            t = self._text(text=ch, scale=scale, shadow=1.25,
                           color=tuple(color) if color else SPECTRUM[0])
            m.connectattr('output', t, 'position')
            offset = (i / n) * period
            if not color:
                curve = {period * k / len(SPECTRUM): c
                         for k, c in enumerate(SPECTRUM)}
                curve[period] = SPECTRUM[0]
                bs.animate_array(t, 'color', 3, curve, loop=True,
                                 offset=offset)
            bs.animate(t, 'scale',
                       {0.0: scale, period * 0.48: scale * 1.2,
                        period * 0.55: scale, period: scale},
                       loop=True, offset=offset)

    def _build_ping(self, cfg):
        m = self._anchor((0.0, float(cfg['ping_height']), 0.0))
        self.ping_text = self._text(text='', scale=float(cfg['ping_scale']),
                                    color=(0.2, 1.0, 0.2))
        m.connectattr('output', self.ping_text, 'position')
        self.update_ping()

    def update_ping(self):
        t = self.ping_text
        if t is None or not t.exists():
            return
        p = get_ping(self.client_id)
        if p is None:
            t.text, t.color = '--', (0.7, 0.7, 0.7)
        else:
            t.text, t.color = f'{p}ms', ping_color(p)

    def destroy(self):
        for n in self.nodes:
            try:
                if n.exists():
                    n.delete()
            except Exception:
                pass
        self.nodes = []
        self.ping_text = None
