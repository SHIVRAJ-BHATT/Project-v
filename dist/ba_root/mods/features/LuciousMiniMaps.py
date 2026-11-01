# Released under the MIT License. See LICENSE for details.
# ba_meta require api 9
"""Lucious Mini Maps - six original maps for playlists.

Lucious Rainbow Road, Lucious Sky Islands, Lucious Lava Pit,
Lucious Pillar Park, Lucious Slide Zone, Lucious Frost Arena.
Physics = invisible regions with footing material; visuals = locator boxes.
"""

from __future__ import annotations

import colorsys
import logging
from typing import Any

import bascenev1 as bs
from bascenev1lib.gameutils import SharedObjects

from features import LuciousKit as kit

_LOG = logging.getLogger('LuciousMiniMaps')
TOP = 3.0       # height of every floor surface
Y = TOP + 0.5   # spawn height


def _hsv(h: float, s: float = 0.75, v: float = 1.0):
    return colorsys.hsv_to_rgb(h % 1.0, s, v)


def _defs(*, aoi, bounds, ffa, s1, s2, flag, powerups):
    d = type('LuciousDefs', (), {})
    d.boxes = {
        'area_of_interest_bounds': aoi,
        'map_bounds': bounds,
        'edge_box': (aoi[0], aoi[1], aoi[2], 0.0, 0.0, 0.0,
                     aoi[6] * 0.8, 2.0, aoi[8] * 0.8),
    }
    d.points = {}
    for i, p in enumerate(ffa, 1):
        d.points[f'ffa_spawn{i}'] = tuple(p) + (1.5, 0.1, 1.5)
    d.points['spawn1'] = tuple(s1) + (1.5, 0.1, 1.5)
    d.points['spawn2'] = tuple(s2) + (1.5, 0.1, 1.5)
    d.points['flag1'] = tuple(s1)
    d.points['flag2'] = tuple(s2)
    d.points['flag_default'] = tuple(flag)
    for i, p in enumerate(powerups, 1):
        d.points[f'powerup_spawn{i}'] = tuple(p)
    return d


class _Scene:
    """Small builder: solid/ice/kill boxes with matching visuals."""

    def __init__(self) -> None:
        sh = SharedObjects.get()
        self.sh = sh
        self.solid = bs.Material()
        self.solid.add_actions(
            conditions=('they_are_different_node_than_us',),
            actions=(('modify_part_collision', 'collide', True),))
        self.ghost = bs.Material()
        self.ghost.add_actions(
            conditions=('they_are_different_node_than_us',),
            actions=(('modify_part_collision', 'collide', True),
                     ('modify_part_collision', 'physical', False)))
        self.ice = bs.Material()
        self.ice.add_actions(
            actions=(('modify_part_collision', 'friction', 0.01),))

    def _locator(self, color, rainbow=None):
        loc = bs.newnode('locator', attrs={
            'shape': 'box', 'color': color, 'opacity': 1.0,
            'additive': False, 'draw_beauty': True})
        try:
            loc.draw_shadow = False
        except Exception:
            pass
        if rainbow is not None:
            bs.animate_array(loc, 'color', 3, {
                k * 0.5: _hsv(rainbow + k / 8) for k in range(9)},
                loop=True)
        return loc

    def box(self, pos, size, color=(1, 1, 1), *, ice=False, kill=False,
            visible=True, rainbow=None):
        mats = [self.solid, self.sh.footing_material]
        if ice:
            mats.append(self.ice)
        if kill:
            mats = [self.ghost, self.sh.death_material]
        reg = bs.newnode('region', attrs={
            'position': pos, 'scale': size, 'type': 'box',
            'materials': mats})
        if visible:
            loc = self._locator(color, rainbow)
            reg.connectattr('position', loc, 'position')
            reg.connectattr('scale', loc, 'size')
        return reg

    def plat(self, x, top, z, w, d, color, thick=1.0, **kw):
        return self.box((x, top - thick / 2, z), (w, thick, d), color, **kw)

    def visual(self, pos, size, color, rainbow=None):
        loc = self._locator(color, rainbow)
        loc.position = pos
        loc.size = size
        return loc


def _bg(tex: str) -> None:
    try:
        bs.newnode('terrain', attrs={
            'mesh': bs.getmesh('thePadBG'), 'lighting': False,
            'background': True, 'color_texture': bs.gettexture(tex)})
    except Exception:
        _LOG.debug('background unavailable', exc_info=True)


class _LMap(bs.Map):
    """Base for all Lucious maps (not registered itself)."""
    preview = 'thePadPreview'
    bgtex = 'bg'
    tint = (1.0, 1.0, 1.0)
    ambient = (1.0, 1.0, 1.0)

    @classmethod
    def get_play_types(cls) -> list[str]:
        return ['melee', 'keep_away', 'team_flag', 'king_of_the_hill']

    @classmethod
    def get_preview_texture_name(cls) -> str:
        return cls.preview

    @classmethod
    def on_preload(cls) -> Any:
        return {}

    def __init__(self) -> None:
        super().__init__()
        _bg(self.bgtex)
        try:
            self.build(_Scene())
        except Exception:
            _LOG.exception('map %s failed to build', self.name)
        g = bs.getactivity().globalsnode
        g.tint = self.tint
        g.ambient_color = self.ambient
        g.vignette_outer = (0.85, 0.85, 0.9)
        g.vignette_inner = (0.97, 0.97, 0.97)

    def build(self, s: _Scene) -> None:
        raise NotImplementedError


class RainbowRoad(_LMap):
    name = 'Lucious Rainbow Road'
    preview = 'bridgitPreview'
    bgtex = 'black'
    defs = _defs(
        aoi=(0, 4, 0, 0, 0, 0, 44, 12, 24),
        bounds=(0, 6, 0, 0, 0, 0, 44, 20, 24),
        ffa=[(-12, Y, -1.5), (12, Y, 1.5), (-6, Y, 1.5), (6, Y, -1.5)],
        s1=(-12, Y, 0), s2=(12, Y, 0), flag=(0, Y + 1.0, 0),
        powerups=[(-8, TOP + 1, 0), (8, TOP + 1, 0),
                  (0, TOP + 1, 2.2), (0, TOP + 1, -2.2)])

    def build(self, s: _Scene) -> None:
        for i, x in enumerate(range(-12, 13, 6)):
            s.plat(x, TOP, 0, 6.05, 6.0, _hsv(i / 5), rainbow=i / 5)
        s.plat(-3, TOP + 1.2, -1.5, 1.4, 1.4, (1, 1, 1), thick=1.2)
        s.plat(3, TOP + 1.2, 1.5, 1.4, 1.4, (1, 1, 1), thick=1.2)


class SkyIslands(_LMap):
    name = 'Lucious Sky Islands'
    preview = 'rampagePreview'
    bgtex = 'menuBG'
    tint = (0.95, 1.0, 1.15)
    defs = _defs(
        aoi=(0, 4, 0, 0, 0, 0, 34, 12, 34),
        bounds=(0, 6, 0, 0, 0, 0, 34, 20, 34),
        ffa=[(-9, Y, 0), (9, Y, 0), (0, Y, -9), (0, Y, 9)],
        s1=(-9, Y, 0), s2=(9, Y, 0), flag=(0, Y, 0),
        powerups=[(-3, TOP + 1, 0), (3, TOP + 1, 0),
                  (0, TOP + 1, -3), (0, TOP + 1, 3)])

    def build(self, s: _Scene) -> None:
        s.plat(0, TOP, 0, 7, 7, (0.9, 0.92, 1.0))
        for i, (x, z) in enumerate([(-9, 0), (9, 0), (0, -9), (0, 9)]):
            reg = s.plat(x, TOP, z, 6, 6, _hsv(i / 4 + 0.1, 0.55))
            base = TOP - 0.5
            per = 3.0 + i * 0.6
            bs.animate_array(reg, 'position', 3, {
                0.0: (x, base, z), per / 2: (x, base + 0.7, z),
                per: (x, base, z)}, loop=True)


class LavaPit(_LMap):
    name = 'Lucious Lava Pit'
    preview = 'towerDPreview'
    bgtex = 'rampageBGColor'
    tint = (1.1, 0.95, 0.9)
    defs = _defs(
        aoi=(0, 4, 0, 0, 0, 0, 30, 12, 30),
        bounds=(0, 6, 0, 0, 0, 0, 30, 20, 30),
        ffa=[(-8.5, Y, 0), (8.5, Y, 0), (0, Y, -8.5), (0, Y, 8.5)],
        s1=(-8.5, Y, 0), s2=(8.5, Y, 0), flag=(0, Y, -8.5),
        powerups=[(-9, TOP + 1, -9), (9, TOP + 1, -9),
                  (-9, TOP + 1, 9), (9, TOP + 1, 9)])

    def build(self, s: _Scene) -> None:
        for x, z, w, d in ((0, -8.5, 24, 7), (0, 8.5, 24, 7),
                           (-8.5, 0, 7, 10), (8.5, 0, 7, 10)):
            s.plat(x, TOP, z, w, d, (0.35, 0.28, 0.30))
        s.box((0, TOP - 1.3, 0), (10, 1.2, 10), kill=True, visible=False)
        lava = s.visual((0, TOP - 1.0, 0), (10, 0.2, 10), (1.0, 0.3, 0.0))
        bs.animate_array(lava, 'color', 3, {
            0.0: (1.0, 0.25, 0.0), 0.7: (1.0, 0.55, 0.05),
            1.4: (1.0, 0.25, 0.0)}, loop=True)
        for sx, sz in ((-2.5, -2.5), (2.5, -2.5), (-2.5, 2.5), (2.5, 2.5)):
            s.plat(sx, TOP, sz, 2.0, 2.0, (0.6, 0.4, 0.3))
        try:
            glow = bs.newnode('light', attrs={
                'position': (0, TOP + 1.0, 0), 'color': (1.0, 0.4, 0.1),
                'radius': 0.7, 'intensity': 1.0,
                'height_attenuated': False, 'volume_intensity_scale': 8.0})
            bs.animate(glow, 'intensity', {0.0: 0.8, 0.8: 1.5, 1.6: 0.8},
                       loop=True)
        except Exception:
            pass


class PillarPark(_LMap):
    name = 'Lucious Pillar Park'
    preview = 'thePadPreview'
    bgtex = 'bg'
    tint = (1.05, 1.08, 1.0)
    defs = _defs(
        aoi=(0, 4, 0, 0, 0, 0, 34, 12, 34),
        bounds=(0, 6, 0, 0, 0, 0, 34, 20, 34),
        ffa=[(-11, Y, -2), (11, Y, 2), (-2, Y, 11), (2, Y, -11)],
        s1=(-11, Y, 0), s2=(11, Y, 0), flag=(0, Y, 0),
        powerups=[(-10, TOP + 1, -10), (10, TOP + 1, -10),
                  (-10, TOP + 1, 10), (10, TOP + 1, 10)])

    def build(self, s: _Scene) -> None:
        s.plat(0, TOP, 0, 26, 26, (0.45, 0.55, 0.45))
        pillars = [(-7, -7, 3.0), (7, -7, 2.0), (-7, 7, 2.0), (7, 7, 3.0),
                   (0, -4, 1.5), (0, 4, 1.5), (-4, 0, 1.2), (4, 0, 1.2)]
        for i, (x, z, h) in enumerate(pillars):
            s.box((x, TOP + h / 2, z), (2, h, 2), _hsv(i / 8, 0.5))


class SlideZone(_LMap):
    name = 'Lucious Slide Zone'
    preview = 'zigZagPreview'
    bgtex = 'shrapnel1Color'
    defs = _defs(
        aoi=(0, 4, 0, 0, 0, 0, 42, 12, 26),
        bounds=(0, 6, 0, 0, 0, 0, 42, 20, 26),
        ffa=[(-13, Y, -3), (13, Y, 3), (-13, Y, 3), (13, Y, -3)],
        s1=(-13, Y, 0), s2=(13, Y, 0), flag=(0, Y, 0),
        powerups=[(0, TOP + 1, 0), (-13, TOP + 1, 5),
                  (13, TOP + 1, -5), (0, TOP + 1, 2)])

    def build(self, s: _Scene) -> None:
        s.plat(-13, TOP, 0, 6, 12, (0.4, 0.6, 1.0))
        s.plat(13, TOP, 0, 6, 12, (1.0, 0.5, 0.5))
        s.plat(0, TOP, 0, 5, 5, (0.9, 0.9, 0.9))
        y = TOP - 0.5
        for i, z in enumerate((-6.5, 6.5)):
            a, b = -5.5, 5.5
            if i % 2:
                a, b = b, a
            per = 4.0 + i * 0.8
            reg = s.plat(a, TOP, z, 5, 4, _hsv(0.3 + i * 0.35))
            bs.animate_array(reg, 'position', 3, {
                0.0: (a, y, z), per / 2: (b, y, z), per: (a, y, z)},
                loop=True)


class FrostArena(_LMap):
    name = 'Lucious Frost Arena'
    preview = 'lakeFrigidPreview'
    bgtex = 'menuBG'
    tint = (0.9, 1.0, 1.2)
    ambient = (0.95, 1.0, 1.15)
    defs = _defs(
        aoi=(0, 4, 0, 0, 0, 0, 32, 12, 32),
        bounds=(0, 6, 0, 0, 0, 0, 32, 20, 32),
        ffa=[(-10, Y, 0), (10, Y, 0), (0, Y, -10), (0, Y, 10)],
        s1=(-10, Y, 0), s2=(10, Y, 0), flag=(0, TOP + 2.0, 0),
        powerups=[(-5, TOP + 1, 0), (5, TOP + 1, 0),
                  (0, TOP + 1, -5), (0, TOP + 1, 5)])

    def build(self, s: _Scene) -> None:
        s.plat(0, TOP, 0, 24, 24, (0.7, 0.9, 1.0), ice=True)
        for x, z in ((-8, -8), (8, -8), (-8, 8), (8, 8)):
            s.box((x, TOP + 1.5, z), (2.5, 3.0, 2.5), (0.5, 0.75, 1.0),
                  ice=True)
        s.box((0, TOP + 0.75, 0), (4, 1.5, 4), (0.85, 0.95, 1.0), ice=True)


MAPS = [RainbowRoad, SkyIslands, LavaPit, PillarPark, SlideZone,
        FrostArena]


def _register() -> None:
    existing = {}
    try:
        existing = getattr(bs.app.classic, 'maps', {}) or {}
    except Exception:
        pass
    for cls in MAPS:
        if cls.name in existing:
            continue
        try:
            bs.register_map(cls)
        except Exception:
            try:
                from bascenev1 import _map
                _map.register_map(cls)
            except Exception:
                _LOG.exception('could not register %s', cls.name)


def _cmd(ctx) -> None:
    kit.reply(ctx, 'Lucious maps: ' + ', '.join(m.name for m in MAPS))


def setup() -> None:
    _register()
    kit.add_command('lmaps', _cmd, level=0)


def teardown() -> None:
    pass
