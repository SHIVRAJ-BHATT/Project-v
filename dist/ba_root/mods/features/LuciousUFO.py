# ba_meta require api 9
# LuciousUFO v4 - land-mine body, 4 impact bombs, 7 bunny heads.
# Direct-position movement, closure timer, auto re-grab, safe bounds.
from __future__ import annotations

import logging
import math
import random
import time
import weakref

import babase
import bascenev1 as bs
from bascenev1lib.actor.bomb import Bomb
from bascenev1lib.gameutils import SharedObjects

from lucious import config
from lucious.commands import command

log = logging.getLogger('lucious')

BOMB_TYPES = ('normal', 'ice', 'impact', 'sticky', 'land_mine', 'tnt')
TICK = 0.02

# ---- look (all multiplied by /ufo size) -----------------------------------
BODY_SCALE = 3.1        # land mine body
SIDE_BOMB_SCALE = 3.2   # the 4 round impact bombs
SIDE_BOMB_DIST = 2.2
BUNNY_COUNT = 7
BUNNY_SCALE = 2.6
BUNNY_STEP = 1.0
BUNNY_Y = 2.1

_live: list = []


def _cfg(key: str, default: float) -> float:
    try:
        val = config.get('ufo.' + key, default)
        return default if val is None else float(val)
    except Exception:
        return default


class UFO(bs.Actor):
    def __init__(self, player, size: float):
        super().__init__()
        shared = SharedObjects.get()
        self.size = size
        self.player = player
        self.controlled = False
        self._dead = False
        self._lr = 0.0
        self._ud = 0.0
        self._vy = 0.0
        self._vel = [0.0, 0.0, 0.0]
        self._n = 0
        self._last_bomb = 0.0
        self._last_type = None
        self._parts: list = []
        self._bounds = None
        self._floor = -999.0
        self._t_last = time.monotonic()
        self._debug_until = 0.0
        self.lift = 0.55 + size * 0.9

        self.ghost = bs.Material()
        self.ghost.add_actions(actions=(
            ('modify_part_collision', 'collide', False),
            ('modify_part_collision', 'physical', False),
        ))

        spaz = player.actor
        px, py, pz = spaz.node.position
        start = (px, py + 1.0, pz)

        # invisible driver node: this is what we move
        self.node = bs.newnode('prop', delegate=self, owner=None, attrs={
            'position': start, 'body': 'sphere', 'body_scale': 0.3,
            'density': 999999, 'gravity_scale': 0.0,
            'shadow_size': 0.0, 'materials': [self.ghost]})
        # node the pilot's hand holds (also what the camera follows)
        self.hold = bs.newnode('prop', owner=self.node, attrs={
            'position': start, 'body': 'sphere', 'body_scale': 1.0,
            'density': 999999, 'gravity_scale': 0.0,
            'shadow_size': 0.0, 'is_area_of_interest': True,
            'materials': [shared.object_material, self.ghost]})
        self.node.connectattr('position', self.hold, 'position')
        self._safe = start

        try:
            act = bs.getactivity()
            self._bounds = tuple(act.map.get_def_bound_box('map_bounds'))
        except Exception:
            self._bounds = None

        self._build()

        ref = weakref.ref(self)

        def _tick():
            u = ref()
            if u is not None:
                u._update()

        self._timer = bs.Timer(TICK, _tick, repeat=True)

    # ------------------------------------------------------------ visuals
    def _part(self, mesh, tex, scale, offset):
        try:
            n = bs.newnode('prop', owner=self.node, attrs={
                'mesh': bs.getmesh(mesh), 'color_texture': bs.gettexture(tex),
                'body': 'sphere', 'body_scale': 0.01, 'mesh_scale': scale,
                'gravity_scale': 0.0, 'density': 999999, 'shadow_size': 0.0,
                'reflection': 'soft', 'reflection_scale': [0.3],
                'materials': [self.ghost]})
            m = bs.newnode('math', owner=n,
                           attrs={'input1': offset, 'operation': 'add'})
            self.node.connectattr('position', m, 'input2')
            m.connectattr('output', n, 'position')
            self._parts.append(n)
        except Exception:
            log.exception('[Lucious] UFO part %s failed', mesh)

    def _build(self):
        s, lift = self.size, self.lift
        self._part('landMine', 'landMine', BODY_SCALE * s, (0, lift, 0))
        d = SIDE_BOMB_DIST * s
        for ox, oz in ((d, 0), (-d, 0), (0, d), (0, -d)):
            self._part('impactBomb', 'impactBombColor', SIDE_BOMB_SCALE * s,
                       (ox, lift, oz))
        mid = (BUNNY_COUNT - 1) / 2.0
        for i in range(BUNNY_COUNT):
            self._part('bunnyHead', 'bunnyColor', BUNNY_SCALE * s,
                       ((i - mid) * BUNNY_STEP * s, lift + BUNNY_Y * s, 0.0))

    # ------------------------------------------------------------ control
    def grab(self, player) -> bool:
        spaz = player.actor
        if spaz is None or not spaz.node.exists():
            return False
        self.player = player
        px, py, pz = spaz.node.position
        self._floor = py + 1.0 - _cfg('floor_drop', 2.5)
        self.node.position = (px, py + 1.0, pz)
        self.node.velocity = (0, 0, 0)
        self._vel = [0.0, 0.0, 0.0]
        self._lr = self._ud = self._vy = 0.0
        spaz.node.invincible = True
        spaz.node.hold_node = bs.Node(None)
        spaz.node.hold_node = self.hold
        player.resetinput()
        self.controlled = True
        it = babase.InputType
        player.assigninput(it.PICK_UP_PRESS, self._up)
        player.assigninput(it.PICK_UP_RELEASE, self._up_r)
        player.assigninput(it.JUMP_PRESS, self._down)
        player.assigninput(it.JUMP_RELEASE, self._down_r)
        player.assigninput(it.BOMB_PRESS, self.drop)
        player.assigninput(it.PUNCH_PRESS, self.release)
        player.assigninput(it.UP_DOWN, self._set_ud)
        player.assigninput(it.LEFT_RIGHT, self._set_lr)
        return True

    def release(self):
        if not self.controlled:
            return
        self.controlled = False
        self._lr = self._ud = self._vy = 0.0
        self._vel = [0.0, 0.0, 0.0]
        try:
            pl = self.player
            spaz = pl.actor
            if spaz is not None and spaz.node.exists():
                spaz.node.invincible = False
                spaz.node.hold_node = bs.Node(None)
                pl.resetinput()
                spaz.connect_controls_to_player()
        except Exception:
            log.exception('[Lucious] UFO release failed')

    def _up(self): self._vy = 1.0
    def _up_r(self):
        if self._vy > 0: self._vy = 0.0
    def _down(self): self._vy = -1.0
    def _down_r(self):
        if self._vy < 0: self._vy = 0.0
    def _set_lr(self, v): self._lr = float(v)
    def _set_ud(self, v): self._ud = float(v)

    # --------------------------------------------------------------- bombs
    def drop(self):
        if not self.controlled or not self.exists():
            return
        now = time.monotonic()
        if now - self._last_bomb < _cfg('cooldown', 0.7):
            return
        self._last_bomb = now
        btype = random.choice([t for t in BOMB_TYPES if t != self._last_type])
        self._last_type = btype
        scale = random.uniform(_cfg('min_scale', 1.8), _cfg('max_scale', 3.5))
        x, y, z = self.node.position
        try:
            b = Bomb(position=(x, y - 1.6, z), velocity=(0, -2, 0),
                     bomb_type=btype, blast_radius=2.0 * scale,
                     bomb_scale=scale, source_player=self.player).autoretain()
            if btype in ('impact', 'land_mine'):
                b.arm()
        except Exception:
            log.exception('[Lucious] UFO bomb failed')

    # ---------------------------------------------------------------- tick
    def _pilot(self):
        try:
            pl = self.player
            if pl.is_alive() and pl.actor is not None \
                    and pl.actor.node.exists():
                return pl.actor
        except Exception:
            pass
        return None

    def _update(self):
        if not self.exists():
            self.destroy()
            return
        self._n += 1
        now = time.monotonic()
        dt = max(0.0, min(0.1, now - self._t_last))
        self._t_last = now
        pos = self.node.position

        if now < self._debug_until and self._n % 50 == 0:
            bs.broadcastmessage(
                f'UFO ctl={self.controlled} lr={self._lr:.2f} '
                f'ud={self._ud:.2f} vy={self._vy:.0f} y={pos[1]:.1f} '
                f'ticks={self._n}', transient=True, color=(1, 1, 0))

        if not self.controlled:
            return
        spaz = self._pilot()
        if spaz is None:               # pilot died / left
            self.release()
            return

        sp = _cfg('speed', 6.0)
        target = (sp * self._lr, sp * 0.8 * self._vy, -sp * self._ud)
        v = self._vel
        for i in range(3):
            v[i] += (target[i] - v[i]) * 0.2

        b = self._bounds
        for i in range(3):
            if b:
                lo, hi = b[i] + 1.0, b[i + 3] - 1.0
                if i == 1:
                    lo = max(lo, self._floor)
                if hi - lo < 4:
                    lo, hi = -1e9, 1e9
            else:
                lo, hi = (self._floor, 1e9) if i == 1 else (-1e9, 1e9)
            if pos[i] <= lo and v[i] < 0:
                v[i] = 0.0
            if pos[i] >= hi and v[i] > 0:
                v[i] = 0.0

        self.node.position = (pos[0] + v[0] * dt, pos[1] + v[1] * dt,
                              pos[2] + v[2] * dt)
        self.node.velocity = (0.0, 0.0, 0.0)

        if self._n % 24 == 0:
            self._safe = tuple(pos)
        if self._n % 12 == 0:
            self._keepalive(spaz, pos)

    def _keepalive(self, spaz, upos):
        try:
            spaz.node.invincible = True
            hn = spaz.node.hold_node
            held = hn is not None and hn.exists()
            if not held:
                spaz.node.hold_node = bs.Node(None)
                spaz.node.hold_node = self.hold
            p = spaz.node.position
            tx, ty, tz = upos[0], upos[1] - 1.0, upos[2]
            if math.dist(p, (tx, ty, tz)) > 3.5:
                spaz.node.handlemessage('stand', tx, ty, tz, 0)
        except Exception:
            log.exception('[Lucious] UFO keepalive failed')

    # ------------------------------------------------------------ lifecycle
    def exists(self) -> bool:
        try:
            return (not self._dead) and self.node.exists()
        except Exception:
            return False

    def handlemessage(self, msg):
        if isinstance(msg, bs.DieMessage):
            self.destroy()
        elif isinstance(msg, bs.OutOfBoundsMessage):
            try:
                self.node.position = self._safe
                self.node.velocity = (0, 0, 0)
                self._vel = [0.0, 0.0, 0.0]
            except Exception:
                pass
        else:
            return super().handlemessage(msg)
        return None

    def destroy(self):
        if self._dead:
            return
        try:
            self.release()
        except Exception:
            pass
        self._dead = True
        self._timer = None
        for n in [*self._parts, getattr(self, 'hold', None), self.node]:
            try:
                if n is not None and n.exists():
                    n.delete()
            except Exception:
                pass


# ------------------------------------------------------------------ command
def _find(ctx):
    act = bs.get_foreground_host_activity()
    if act is None:
        ctx.error('No active game right now.')
        return None, None
    for p in act.players:
        try:
            if p.sessionplayer.inputdevice.client_id == ctx.client_id \
                    and p.is_alive():
                return act, p
        except Exception:
            continue
    ctx.error('Join the game and spawn first.')
    return None, None


@command('ufo', level=80,
         usage='/ufo | /ufo take | /ufo debug | /ufo size <0.2-1.5>',
         help='Spawn or remove your Lucious UFO (owner and admin).')
def _ufo(ctx):
    sub = ctx.args[0].lower() if ctx.args else ''

    if sub == 'size':
        try:
            val = max(0.2, min(1.5, float(ctx.args[1])))
            config.set_value('ufo.size', val)
            ctx.reply(f'UFO size = {val} (applies to your next /ufo).')
        except Exception:
            ctx.error('Usage: /ufo size 0.2-1.5')
        return

    act, player = _find(ctx)
    if act is None:
        return
    _live[:] = [u for u in _live if u.exists()]
    ufo = getattr(act, '_lc_ufo', None)
    alive = ufo is not None and ufo.exists()

    if sub == 'take':
        if not alive:
            ctx.error('No UFO yet. Use /ufo.')
            return
        with act.context:
            ufo.release()
            ok = ufo.grab(player)
        ctx.reply('UFO control restored.' if ok else 'Could not grab it.')
        return

    if sub == 'debug':
        if not alive:
            ctx.error('No UFO yet. Use /ufo.')
            return
        ufo._debug_until = time.monotonic() + 15.0
        ctx.reply('Move the stick and press pickup/jump now. '
                  'Yellow lines show for 15 s.')
        return

    if alive:
        with act.context:
            ufo.destroy()
        act._lc_ufo = None
        ctx.reply('UFO removed.')
        return

    size = max(0.2, min(1.5, _cfg('size', 0.45)))
    with act.context:
        ufo = UFO(player, size)
        ufo.autoretain()
        act._lc_ufo = ufo           # strong ref so it can't be collected
        _live.append(ufo)
        ufo.grab(player)
        bs.broadcastmessage(f'Jo hukum mere aaka, {player.getname()}!',
                            color=(1.0, 0.85, 0.2), transient=True)


def setup():
    pass


def teardown():
    for u in list(_live):
        try:
            u.destroy()
        except Exception:
            pass
    _live.clear()
