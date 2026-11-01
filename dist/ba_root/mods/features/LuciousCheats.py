# Released under the MIT License. See LICENSE for details.
# ba_meta require api 9
"""Lucious Cheats - player commands in the imayushsaini style.

Target: nothing = you, 'all', a name, a client id, or a pb-/a- id.
Level 80, or a role grant (/addcmd). Anyone else who owns the command
(shop) can only use it on themselves, with a cooldown.
Harmful commands skip players whose role level >= yours.

kill/die heal/heath shield/protect gloves/punch sleep superpunch/sp
freeze/icy unfreeze/thaw godmode/gm fly invisible/inv headless/hl
creepy/creep celebrate/celeb spaz (restore)   speed  floater/flo
slow night day   lm  gp  remove/rm
"""

from __future__ import annotations

import logging
import math
import time

import babase
import bascenev1 as bs

try:
    import _babase
except Exception:
    _babase = None

from lucious import config, roles, utils
from lucious.commands import command

log = logging.getLogger('lucious')
STAFF = 80
_cd: dict = {}


# ------------------------------------------------------------- helpers ----
def _activity():
    try:
        return bs.get_foreground_host_activity()
    except Exception:
        return None


def _cid(p):
    try:
        return p.sessionplayer.inputdevice.client_id
    except Exception:
        return None


def _alive(p) -> bool:
    try:
        return bool(p.is_alive() and p.actor.node.exists())
    except Exception:
        return False


def _granted(account, name: str) -> bool:
    if not account:
        return False
    defs = config.get('roles') or {}
    for role in roles.roles_of(account):
        got = (defs.get(role) or {}).get('commands') or []
        if 'all' in got or name in got:
            return True
    return False


def _priv(ctx, name: str) -> bool:
    return ctx.level >= STAFF or _granted(ctx.account, name)


def _resolve(ctx, act, arg: str) -> list:
    try:
        alive = [p for p in act.players if _alive(p)]
    except Exception:
        ctx.error('No game is running.')
        return []
    if not arg:
        mine = [p for p in alive if _cid(p) == ctx.client_id]
        if not mine:
            ctx.error('You are not alive in this game.')
        return mine
    if arg.lower() == 'all':
        return alive
    cid, _acc, name, err = utils.resolve_target(arg)
    if err or cid is None:
        ctx.error(err or 'Player is offline.')
        return []
    hit = [p for p in alive if _cid(p) == cid]
    if not hit:
        ctx.error(f'{name} is not alive in this game.')
    return hit


def _protected(ctx, cid) -> bool:
    if ctx.level >= 1000 or cid == ctx.client_id or cid is None:
        return False
    acc = utils.account_of(cid) if cid != utils.HOST else None
    return roles.level_of(acc) >= ctx.level


def _pick(ctx, name: str, harmful: bool, cooldown: int):
    act = _activity()
    if act is None:
        ctx.error('No active game.')
        return None, []
    priv = _priv(ctx, name)
    arg = ctx.args[0] if ctx.args else ''
    key = (ctx.client_id, name)
    if not priv:
        if arg:
            ctx.error('You can only use this on yourself.')
            return None, []
        if cooldown:
            left = _cd.get(key, 0) + cooldown - time.time()
            if left > 0:
                ctx.error(f'/{name} ready in {int(left)}s.')
                return None, []
    players = _resolve(ctx, act, arg)
    if not players:
        return None, []
    if harmful:
        kept = [p for p in players if not _protected(ctx, _cid(p))]
        if len(kept) < len(players):
            ctx.reply(f'{len(players) - len(kept)} protected player(s) '
                      'skipped.', utils.YELLOW)
        players = kept
        if not players:
            return None, []
    if not priv and cooldown:
        _cd[key] = time.time()
    return act, players


def cheat(name: str, *, aliases=(), help='', harmful=False, cooldown=0):
    """Register /name; action(actor, player) runs inside the game context."""
    def deco(action):
        def handler(ctx):
            act, picks = _pick(ctx, name, harmful, cooldown)
            if not picks:
                return
            done = 0
            with act.context:
                for p in picks:
                    try:
                        if action(p.actor, p) is not False:
                            done += 1
                    except Exception:
                        log.exception('[Lucious] /%s failed', name)
            ctx.reply(f'/{name}: {done} player(s).')
        handler.__name__ = f'cmd_{name}'
        command(name, level=STAFF, aliases=tuple(aliases),
                usage=f'/{name} [player|id|all]', help=help)(handler)
        return action
    return deco


# --------------------------------------------------------- the commands ----
@cheat('kill', aliases=('die',), harmful=True, help='Kill players')
def _kill(actor, p):
    actor.handlemessage(bs.DieMessage())


@cheat('heal', aliases=('heath',), cooldown=45, help='Restore health')
def _heal(actor, p):
    actor.handlemessage(bs.PowerupMessage(poweruptype='health'))


@cheat('shield', aliases=('protect',), cooldown=60, help='Give a shield')
def _shield(actor, p):
    actor.handlemessage(bs.PowerupMessage(poweruptype='shield'))


@cheat('gloves', aliases=('punch',), cooldown=60, help='Boxing gloves')
def _gloves(actor, p):
    actor.handlemessage(bs.PowerupMessage(poweruptype='punch'))


@cheat('sleep', harmful=True, help='Knock out for 8 seconds')
def _sleep(actor, p):
    actor.node.handlemessage('knockout', 8000)


@cheat('superpunch', aliases=('sp',), help='Toggle super punch')
def _superpunch(actor, p):
    if getattr(actor, '_lc_sp', False):
        actor._lc_sp = False
        old = getattr(actor, '_lc_sp_prev', (1.2, 400))
        actor._punch_power_scale, actor._punch_cooldown = old
    else:
        actor._lc_sp = True
        actor._lc_sp_prev = (getattr(actor, '_punch_power_scale', 1.2),
                             getattr(actor, '_punch_cooldown', 400))
        actor._punch_power_scale = 15
        actor._punch_cooldown = 0


@cheat('freeze', aliases=('icy',), harmful=True, help='Freeze in ice')
def _freeze(actor, p):
    actor.handlemessage(bs.FreezeMessage())


@cheat('unfreeze', aliases=('thaw',), help='Unfreeze')
def _unfreeze(actor, p):
    actor.handlemessage(bs.ThawMessage())


@cheat('godmode', aliases=('gm',), help='Toggle god mode')
def _god(actor, p):
    if getattr(actor, '_lc_god', False):
        actor._lc_god = False
        actor.node.invincible = False
        old = getattr(actor, '_lc_god_prev', (1.2, 400))
        actor._punch_power_scale, actor._punch_cooldown = old
    else:
        actor._lc_god = True
        actor._lc_god_prev = (getattr(actor, '_punch_power_scale', 1.2),
                              getattr(actor, '_punch_cooldown', 400))
        actor.node.invincible = True
        actor._punch_power_scale = 7


@cheat('fly', help='Toggle flying')
def _fly(actor, p):
    actor.node.fly = not bool(getattr(actor.node, 'fly', False))


# ---- looks (invisible / headless / creepy) --------------------------------
_MESHES = ('head_mesh', 'torso_mesh', 'upper_arm_mesh', 'forearm_mesh',
           'pelvis_mesh', 'hand_mesh', 'toes_mesh', 'upper_leg_mesh',
           'lower_leg_mesh')


def _put_back(node, orig: dict) -> None:
    for k, v in orig.items():
        try:
            setattr(node, k, v)
        except Exception:
            pass


def _look(actor, kind: str) -> bool:
    """Toggle a look. True = applied, False = restored."""
    node = actor.node
    orig = getattr(actor, '_lc_orig', None)
    if getattr(actor, '_lc_look', None) == kind:
        if orig:
            _put_back(node, orig)
        actor._lc_orig = None
        actor._lc_look = None
        return False
    if orig is None:
        orig = {k: getattr(node, k, None) for k in _MESHES + ('style',)}
        actor._lc_orig = orig
    else:
        _put_back(node, orig)
    for k in (_MESHES if kind == 'invisible' else ('head_mesh',)):
        setattr(node, k, None)
    node.style = 'cyborg'
    actor._lc_look = kind
    return True


@cheat('invisible', aliases=('inv',), help='Toggle invisible')
def _invisible(actor, p):
    _look(actor, 'invisible')


@cheat('headless', aliases=('hl',), help='Toggle headless')
def _headless(actor, p):
    _look(actor, 'headless')


@cheat('creepy', aliases=('creep',), help='Headless + punch + shield')
def _creepy(actor, p):
    if _look(actor, 'creepy'):
        actor.handlemessage(bs.PowerupMessage(poweruptype='punch'))
        actor.handlemessage(bs.PowerupMessage(poweruptype='shield'))


@cheat('celebrate', aliases=('celeb',), help='Victory dance')
def _celebrate(actor, p):
    actor.handlemessage(bs.CelebrateMessage())


@cheat('spaz', help='Restore normal look and abilities')
def _spaz(actor, p):
    node = actor.node
    orig = getattr(actor, '_lc_orig', None)
    if orig:
        _put_back(node, orig)
    actor._lc_orig = None
    actor._lc_look = None
    for flag, prev in (('_lc_god', '_lc_god_prev'), ('_lc_sp', '_lc_sp_prev')):
        if getattr(actor, flag, False):
            setattr(actor, flag, False)
            old = getattr(actor, prev, None)
            if old:
                actor._punch_power_scale, actor._punch_cooldown = old
    node.invincible = False
    node.fly = False


# ---------------------------------------------------- global / other ----
def _set_speed(mult: float):
    exp = max(-2, min(2, round(math.log2(mult))))
    for mod in (babase, _babase):
        fn = getattr(mod, 'set_debug_speed_exponent', None)
        if callable(fn):
            fn(exp)
            return 2.0 ** exp
    return None


@command('speed', level=STAFF, usage='/speed <0.25|0.5|1|2|4>',
         help='Game speed (snaps to a power of two)')
def _speed(ctx):
    try:
        mult = float(ctx.args[0])
        if mult <= 0:
            raise ValueError
    except (IndexError, ValueError):
        return ctx.error('Usage: /speed <0.25 | 0.5 | 1 | 2 | 4>')
    try:
        got = _set_speed(mult)
    except Exception:
        log.exception('[Lucious] /speed failed')
        got = None
    if got is None:
        return ctx.error('This build has no speed control.')
    utils.announce(f'Game speed x{got:g} ({ctx.name})')


def _lc():
    from features import LuciousCommands
    return LuciousCommands


@command('slow', level=50, usage='/slow', help='Toggle slow motion (= /sm)')
def _slow(ctx):
    _lc()._sm(ctx)


@command('night', level=50, usage='/night', help='Night vision on')
def _night(ctx):
    lc = _lc()
    act = lc._activity()
    if act is None:
        return ctx.error('No active game.')
    with act.context:
        on = lc._close(act.globalsnode.tint, lc.NV_TINT)
    if on:
        return ctx.reply('It is already night.')
    lc._nv(ctx)


@command('day', level=50, usage='/day', help='Back to daylight (= /dv)')
def _day(ctx):
    _lc()._dv(ctx)


@command('floater', level=STAFF, aliases=('flo',), usage='/floater',
         help='Spawn your Lucious UFO (same as /ufo)')
def _floater(ctx):
    try:
        from features import LuciousUFO
    except Exception:
        log.exception('[Lucious] UFO module missing')
        return ctx.error('The UFO module is not loaded.')
    LuciousUFO._ufo(ctx)


def _private(cid, text: str) -> None:
    if cid == utils.HOST:
        print(f'[Lucious] {text}')
        return
    try:
        bs.chatmessage(text, clients=[cid])
    except Exception:
        utils.tell(cid, text)


@command('lm', level=0, usage='/lm', help='Show the last chat messages (private)')
def _lm(ctx):
    try:
        lines = [str(x) for x in list(bs.get_chat_messages())[-12:]]
    except Exception:
        return ctx.error('Chat history is not available.')
    if not lines:
        return ctx.reply('No chat yet.')
    for line in lines:
        _private(ctx.client_id, line)


def _sp_cid(sp):
    try:
        return sp.inputdevice.client_id
    except Exception:
        return None


@command('gp', level=50, usage='/gp <player|client id|index>',
         help="Show a player's profile names")
def _gp(ctx):
    if not ctx.args:
        return ctx.error('Usage: /gp <player|client id|index>')
    session = bs.get_foreground_host_session()
    if session is None:
        return ctx.error('No session.')
    sps = list(session.sessionplayers)
    arg, target = ctx.args[0], None
    if arg.isdigit():
        n = int(arg)
        target = next((sp for sp in sps if _sp_cid(sp) == n), None)
        if target is None and n < len(sps):
            target = sps[n]
    else:
        needle = arg.lower()
        for sp in sps:
            try:
                name = str(sp.getname(full=True, icon=False)).lower()
            except Exception:
                continue
            if needle in name:
                target = sp
                break
    if target is None:
        return ctx.error(f'No player matches "{arg}".')
    try:
        profiles = list(target.inputdevice.get_player_profiles())
    except Exception:
        return ctx.error('Profiles are not available for that player.')
    ctx.reply(f'{len(profiles)} profile(s):', utils.YELLOW)
    for i, prof in enumerate(profiles, 1):
        ctx.reply(f'{i}) {prof}')


@command('remove', level=STAFF, aliases=('rm',),
         usage='/remove <player|client id|all>',
         help='Remove a player from the game (they can rejoin)')
def _remove(ctx):
    if not ctx.args:
        return ctx.error('Usage: /remove <player|client id|all>')
    session = bs.get_foreground_host_session()
    if session is None:
        return ctx.error('No session.')
    everyone = ctx.args[0].lower() == 'all'
    if everyone:
        targets = list(session.sessionplayers)
    else:
        cid, _acc, name, err = utils.resolve_target(ctx.args[0])
        if err or cid is None:
            return ctx.error(err or 'Player is offline.')
        targets = [sp for sp in session.sessionplayers if _sp_cid(sp) == cid]
        if not targets:
            return ctx.error(f'{name} is not in the game.')
    done = skipped = 0
    for sp in targets:
        cid = _sp_cid(sp)
        if everyone and cid == ctx.client_id:
            continue
        if _protected(ctx, cid):
            skipped += 1
            continue
        try:
            sp.remove_from_game()
            done += 1
        except Exception:
            log.exception('[Lucious] /remove failed')
    ctx.reply(f'Removed {done} player(s)'
              + (f', {skipped} protected skipped.' if skipped else '.'))


def setup() -> None:
    pass


def teardown() -> None:
    _cd.clear()
