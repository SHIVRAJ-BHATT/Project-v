# ba_meta require api 9
# LuciousOverhead v2 - ping (left) and heart HP (right) on ONE row, rank title below.
from __future__ import annotations

import logging
import weakref

import _bascenev1
import bascenev1 as bs

from lucious import config, utils
from lucious.commands import command

log = logging.getLogger('lucious')

FLAGS = ('hp', 'rank', 'ping')
DEF = {'row': 2.0, 'rank': 1.25, 'gap': 0.22}
SCALE = {'hp': 0.0088, 'ping': 0.0088, 'rank': 0.0095}


def _on(key: str) -> bool:
    try:
        return bool(config.get('overhead.' + key, True))
    except Exception:
        return True


def _num(key: str, lo: float, hi: float) -> float:
    try:
        v = float(config.get('overhead.' + key, DEF[key]))
    except Exception:
        v = DEF[key]
    return max(lo, min(hi, v))


def _stats():
    try:
        from features import LuciousStats
        return LuciousStats
    except Exception:
        return None


def _ping_ms(cid):
    try:
        v = int(_bascenev1.get_client_ping(cid))
        return v if v >= 0 else None
    except Exception:
        return None


class Over:
    def __init__(self, spaz):
        self._ref = weakref.ref(spaz)
        self._n = 0
        self._anim = None
        self.hp = self.rank = self.ping = None
        node = spaz.node
        self.sp = None
        self.cid = None
        try:
            self.sp = spaz.player.sessionplayer
            self.cid = int(self.sp.inputdevice.client_id)
        except Exception:
            pass

        want_ping = _on('ping') and self.cid is not None and self.cid >= 0
        want_hp = _on('hp')
        both = want_ping and want_hp
        row, gap = _num('row', -3.0, 5.0), _num('gap', 0.0, 1.5)
        if want_ping:
            self.ping = self._mk(node, -gap if both else 0.0, row,
                                 SCALE['ping'], 'right' if both else 'center')
        if want_hp:
            self.hp = self._mk(node, gap if both else 0.0, row,
                               SCALE['hp'], 'left' if both else 'center')
        if _on('rank') and _stats() is not None:
            self.rank = self._mk(node, 0.0, _num('rank', -3.0, 5.0),
                                 SCALE['rank'], 'center')
        self._tick()
        self._timer = bs.Timer(0.3, bs.WeakCallStrict(self._tick),
                               repeat=True)

    @staticmethod
    def _mk(node, dx, y, scale, align):
        pos = bs.newnode('math', owner=node,
                         attrs={'input1': (dx, y, 0.0), 'operation': 'add'})
        node.connectattr('torso_position', pos, 'input2')
        txt = bs.newnode('text', owner=node, attrs={
            'text': '', 'in_world': True, 'shadow': 1.0, 'flatness': 1.0,
            'color': (1.0, 1.0, 1.0), 'scale': scale, 'h_align': align})
        pos.connectattr('output', txt, 'position')
        return txt

    def _tick(self):
        spaz = self._ref()
        try:
            alive = spaz is not None and spaz.node.exists()
        except Exception:
            alive = False
        if not alive:
            self._timer = None
            return
        self._n += 1
        try:
            if self.hp is not None:
                hp = max(0, int(spaz.hitpoints))
                mx = max(1, int(getattr(spaz, 'hitpoints_max', 1000)))
                fr = hp / mx
                self.hp.text = f'\ue047 {hp / 10:g}'
                self.hp.color = ((0.2, 1.0, 0.2) if fr > 0.6 else
                                 (1.0, 1.0, 0.0) if fr > 0.3 else
                                 (1.0, 0.15, 0.15))
            if self.rank is not None and (self._n == 1 or self._n % 10 == 0):
                self._update_rank()
            if self.ping is not None and (self._n == 1 or self._n % 5 == 0):
                ms = _ping_ms(self.cid)
                if ms is None:
                    self.ping.text = '-- ms'
                    self.ping.color = (0.75, 0.75, 0.75)
                else:
                    self.ping.text = f'{ms} ms'
                    self.ping.color = ((0.0, 1.0, 0.0) if ms < 80 else
                                       (1.0, 1.0, 0.0) if ms < 150 else
                                       (1.0, 0.1, 0.1))
        except Exception:
            log.exception('[Lucious] overhead tick failed')

    def _update_rank(self):
        acct = None
        try:
            acct = utils.account_of(self.cid) if self.cid is not None else None
            if not acct and self.sp is not None:
                acct = self.sp.get_v1_account_id()
        except Exception:
            pass
        text, col, top = _stats().title_for(acct)
        self.rank.text = text
        if self._anim is not None and not top:
            try:
                self._anim.delete()
            except Exception:
                pass
            self._anim = None
        if top and self._anim is None:
            self._anim = bs.animate_array(self.rank, 'color', 3, {
                0.0: col, 0.8: (1.0, 1.0, 1.0), 1.6: col}, loop=True)
        elif not top:
            self.rank.color = col


_patched = []


def setup():
    from bascenev1lib.actor import playerspaz as mod
    cls = mod.PlayerSpaz
    orig = getattr(cls, '_lucious_over_orig', None) or cls.__init__
    cls._lucious_over_orig = orig

    def init(self, *a, **k):
        orig(self, *a, **k)
        try:
            self._lc_over = Over(self)
        except Exception:
            log.exception('[Lucious] overhead build failed')

    cls.__init__ = init
    _patched.append((cls, orig))


def teardown():
    for cls, orig in _patched:
        try:
            cls.__init__ = orig
        except Exception:
            pass
    _patched.clear()


@command('overhead', level=80,
         usage='/overhead hp|rank|ping on|off | height row|rank <y> | gap <n>',
         help='Overhead displays (applies on next spawn).')
def _overhead(ctx):
    a = [x.lower() for x in ctx.args]
    if len(a) == 3 and a[0] == 'height' and a[1] in ('row', 'rank'):
        try:
            v = max(-3.0, min(5.0, float(a[2])))
        except ValueError:
            ctx.error('Usage: /overhead height row|rank <number>')
            return
        config.set_value('overhead.' + a[1], v)
        ctx.reply(f'{a[1]} height = {v} (next spawn)')
    elif len(a) == 2 and a[0] == 'gap':
        try:
            v = max(0.0, min(1.5, float(a[1])))
        except ValueError:
            ctx.error('Usage: /overhead gap 0-1.5')
            return
        config.set_value('overhead.gap', v)
        ctx.reply(f'gap = {v} (next spawn)')
    elif len(a) == 2 and a[0] in FLAGS and a[1] in ('on', 'off'):
        config.set_value('overhead.' + a[0], a[1] == 'on')
        ctx.reply(f'overhead {a[0]} = {a[1]} (next spawn)')
    else:
        ctx.reply(f'{", ".join(f"{k}={"on" if _on(k) else "off"}" for k in FLAGS)}'
                  f' | row={_num("row", -3, 5)} rank={_num("rank", -3, 5)}'
                  f' gap={_num("gap", 0, 1.5)}')
