# Released under the MIT License. See LICENSE for details.
# ba_meta require api 9
"""Lucious Rules - every match: punching gloves + 2 bomb limit (players).

Commands (staff): /rules  |  /rules gloves on|off  |  /rules bombs on|off
                  /rules max <1-6>
"""

from __future__ import annotations

import logging

import bascenev1 as bs

from features import LuciousKit as kit

_LOG = logging.getLogger('LuciousRules')
_P = 'rules'
DEFAULTS = {'gloves': True, 'bombs': True, 'max_bombs': 2}
_FLAG = '_lucious_rules'
_ORIG_FN: dict = {}
_ORIG_ATTR: dict = {}


def _c(key):
    return kit.cfg(_P, DEFAULTS, key)


def _is_player(obj) -> bool:
    try:
        from bascenev1lib.actor.playerspaz import PlayerSpaz
        return isinstance(obj, PlayerSpaz)
    except Exception:
        return False


def _cap() -> int:
    return max(1, min(6, int(_c('max_bombs'))))


def _w_set(orig):
    def wrapper(self, count, *a, **k):
        if _c('bombs') and _is_player(self):
            count = min(int(count), _cap())
        return orig(self, count, *a, **k)
    return wrapper


def _w_drop(orig):
    def wrapper(self, *a, **k):
        if _c('bombs') and _is_player(self):
            cap = _cap()
            if getattr(self, '_max_bomb_count', cap) > cap:
                self._max_bomb_count = cap
            if self.bomb_count > cap:
                self.bomb_count = cap
        return orig(self, *a, **k)
    return wrapper


def _w_gloves(orig):
    def wrapper(self, *a, **k):
        result = orig(self, *a, **k)
        if _c('gloves') and _is_player(self):
            try:
                self.equip_boxing_gloves()
            except Exception:
                pass
        return result
    return wrapper


def _install() -> None:
    from bascenev1lib.actor.spaz import Spaz
    for name, maker in (('set_bomb_count', _w_set), ('drop_bomb', _w_drop),
                        ('_gloves_wear_off', _w_gloves)):
        orig = Spaz.__dict__.get(name)
        if orig is None or getattr(orig, _FLAG, False):
            continue
        wrapped = maker(orig)
        setattr(wrapped, _FLAG, True)
        _ORIG_FN[name] = orig
        setattr(Spaz, name, wrapped)


def _apply() -> None:
    from bascenev1lib.actor.playerspaz import PlayerSpaz
    for attr in ('default_boxing_gloves', 'default_bomb_count'):
        if attr not in _ORIG_ATTR:
            _ORIG_ATTR[attr] = (attr in PlayerSpaz.__dict__,
                                getattr(PlayerSpaz, attr))
    PlayerSpaz.default_boxing_gloves = (
        True if _c('gloves') else _ORIG_ATTR['default_boxing_gloves'][1])
    PlayerSpaz.default_bomb_count = (
        _cap() if _c('bombs') else _ORIG_ATTR['default_bomb_count'][1])


def _refresh_live() -> None:
    act = bs.get_foreground_host_activity()
    if act is None:
        return
    try:
        with act.context:
            for player in list(getattr(act, 'players', [])):
                spaz = getattr(player, 'actor', None)
                if spaz is None or not _is_player(spaz) or not spaz.node:
                    continue
                if _c('gloves'):
                    spaz.equip_boxing_gloves()
                if _c('bombs'):
                    cap = _cap()
                    spaz._max_bomb_count = min(spaz._max_bomb_count, cap)
                    spaz.bomb_count = min(spaz.bomb_count, cap)
    except Exception:
        _LOG.debug('live refresh failed', exc_info=True)


def _cmd(ctx) -> None:
    if not kit.staff(ctx):
        kit.reply(ctx, 'Staff only.')
        return
    args = [str(a).lower() for a in (getattr(ctx, 'args', None) or [])]
    if len(args) >= 2 and args[0] in ('gloves', 'bombs') \
            and args[1] in ('on', 'off'):
        kit.set_cfg(_P, args[0], args[1] == 'on')
    elif len(args) >= 2 and args[0] == 'max':
        try:
            kit.set_cfg(_P, 'max_bombs', max(1, min(6, int(args[1]))))
        except ValueError:
            kit.reply(ctx, 'Use a number from 1 to 6.')
            return
    _apply()
    _refresh_live()
    kit.reply(ctx, f'Rules: gloves={_c("gloves")}, bomb limit='
                   f'{_cap() if _c("bombs") else "default"}')


def setup() -> None:
    _install()
    _apply()
    _refresh_live()
    kit.add_command('rules', _cmd, level=80)


def teardown() -> None:
    try:
        from bascenev1lib.actor.spaz import Spaz
        from bascenev1lib.actor.playerspaz import PlayerSpaz
        for name, orig in _ORIG_FN.items():
            setattr(Spaz, name, orig)
        _ORIG_FN.clear()
        for attr, (own, value) in _ORIG_ATTR.items():
            if own:
                setattr(PlayerSpaz, attr, value)
            elif attr in PlayerSpaz.__dict__:
                delattr(PlayerSpaz, attr)
        _ORIG_ATTR.clear()
    except Exception:
        _LOG.exception('Rules: teardown failed')
