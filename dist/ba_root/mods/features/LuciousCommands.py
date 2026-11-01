# mods/features/LuciousCommands.py
# ba_meta require api 9
"""/me /info /sm /nv /dv /tint /zm /curse /fx /restart"""
from __future__ import annotations

import logging
import math
import time
import weakref

import babase
import bascenev1 as bs

from lucious import config, roles, utils
from lucious.commands import command
from lucious.events import bus

log = logging.getLogger('lucious')
GOLD = (1.0, 0.85, 0.3)
NV_TINT, NV_AMBIENT = (0.5, 0.5, 1.0), (1.5, 1.5, 1.5)


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


def _key(p) -> str:
    try:
        acc = p.sessionplayer.get_v1_account_id()
    except Exception:
        acc = None
    return acc or f'cid:{_cid(p)}'


def _announce(text: str) -> None:
    bs.broadcastmessage(text, color=GOLD, transient=True)


def _players(act, arg: str, ctx) -> list:
    """'' = sender, 'all', or a player/id. Sends the error itself."""
    if act is None:
        ctx.error('No active game.')
        return []
    alive = [p for p in act.players if _alive(p)]
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


# ------------------------------------------------- look: sm nv dv tint zm ----
_LOOK: dict = {'ref': None, 'tint': None, 'ambient': None, 'aoi': None}


def _save_look(act) -> None:
    ref = _LOOK['ref']
    if ref is not None and ref() is act:
        return
    g = act.globalsnode
    try:
        aoi = tuple(g.area_of_interest_bounds)
    except Exception:
        aoi = None
    _LOOK.update(ref=weakref.ref(act), tint=tuple(g.tint),
                 ambient=tuple(g.ambient_color), aoi=aoi)


def _close(a, b) -> bool:
    return all(abs(x - y) < 1e-3 for x, y in zip(a, b))


@command('sm', level=50, aliases=('slowmo',), usage='/sm',
         help='Toggle slow motion')
def _sm(ctx):
    act = _activity()
    if act is None:
        return ctx.error('No active game.')
    with act.context:
        g = act.globalsnode
        g.slow_motion = not g.slow_motion
        on = g.slow_motion
    _announce(f"Slow motion {'ON' if on else 'OFF'} ({ctx.name})")


@command('nv', level=50, usage='/nv', help='Toggle night vision')
def _nv(ctx):
    act = _activity()
    if act is None:
        return ctx.error('No active game.')
    with act.context:
        _save_look(act)
        g = act.globalsnode
        was_on = _close(g.tint, NV_TINT)
        if was_on:
            g.tint, g.ambient_color = _LOOK['tint'], _LOOK['ambient']
        else:
            g.tint, g.ambient_color = NV_TINT, NV_AMBIENT
    _announce(f"Night vision {'OFF' if was_on else 'ON'} ({ctx.name})")


@command('dv', level=50, usage='/dv', help="Restore the map's own light")
def _dv(ctx):
    act = _activity()
    if act is None:
        return ctx.error('No active game.')
    with act.context:
        _save_look(act)
        g = act.globalsnode
        g.tint, g.ambient_color = _LOOK['tint'], _LOOK['ambient']
    _announce(f'Daylight ({ctx.name})')


@command('tint', level=50, usage='/tint <r> <g> <b> | /tint reset',
         help='Set the map tint')
def _tint(ctx):
    act = _activity()
    if act is None:
        return ctx.error('No active game.')
    a = ctx.args
    with act.context:
        _save_look(act)
        g = act.globalsnode
        if len(a) == 1 and a[0].lower() in ('reset', 'off'):
            g.tint = _LOOK['tint']
            return ctx.reply('Tint reset.')
        if len(a) != 3:
            return ctx.error('Usage: /tint <r> <g> <b>  e.g. /tint 1 0.5 0.5')
        try:
            vals = [float(x) for x in a]
        except ValueError:
            return ctx.error('Numbers expected.')
        if not all(math.isfinite(v) for v in vals):
            return ctx.error('Numbers expected.')
        g.tint = tuple(max(0.0, min(5.0, v)) for v in vals)
    ctx.reply('Tint set.')


@command('zm', level=50, aliases=('zoom',),
         usage='/zm [0.25-1.0 | off]',
         help='Zoom the camera in for everyone (toggle)')
def _zm(ctx):
    act = _activity()
    if act is None:
        return ctx.error('No active game.')
    arg = ctx.args[0].lower() if ctx.args else ''
    with act.context:
        _save_look(act)
        base = _LOOK['aoi']
        if base is None:
            return ctx.error('Camera bounds are not available here.')
        g = act.globalsnode
        zoomed = not _close(tuple(g.area_of_interest_bounds), base)
        if arg in ('off', 'reset') or (not arg and zoomed):
            g.area_of_interest_bounds = base
            text = 'Zoom OFF'
        else:
            try:
                f = float(arg) if arg else 0.6
            except ValueError:
                return ctx.error('Usage: /zm [0.25-1.0 | off]')
            f = max(0.25, min(1.0, f))
            x0, y0, z0, x1, y1, z1 = base
            cx, cy, cz = (x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2
            hx, hy, hz = (x1 - x0) / 2 * f, (y1 - y0) / 2 * f, (z1 - z0) / 2 * f
            g.area_of_interest_bounds = (cx - hx, cy - hy, cz - hz,
                                         cx + hx, cy + hy, cz + hz)
            text = f'Zoom x{1 / f:.1f}'
    _announce(f'{text} ({ctx.name})')


# --------------------------------------------------------------- curse ----
@command('curse', level=80, aliases=('cur',),
         usage='/curse [player|id|all]', help='Curse a player (explodes soon)')
def _curse(ctx):
    act = _activity()
    targets = _players(act, ctx.args[0] if ctx.args else '', ctx)
    if not targets:
        return
    n = 0
    with act.context:
        for p in targets:
            try:
                p.actor.handlemessage(bs.PowerupMessage(poweruptype='curse'))
                n += 1
            except Exception:
                log.exception('[Lucious] /curse failed')
    ctx.reply(f'Cursed {n} player(s).')


# ----------------------------------------------------------------- fx ----
EFFECTS = {
    'spark': dict(chunk_type='spark', count=4, scale=0.7, spread=0.25),
    'sparkle': dict(chunk_type='spark', count=8, scale=0.4, spread=0.5),
    'sweat': dict(chunk_type='sweat', count=3, scale=0.8, spread=0.2),
    'ice': dict(chunk_type='ice', count=3, scale=0.7, spread=0.2),
    'slime': dict(chunk_type='slime', count=3, scale=0.7, spread=0.2),
    'metal': dict(chunk_type='metal', count=3, scale=0.6, spread=0.2),
    'rock': dict(chunk_type='rock', count=3, scale=0.6, spread=0.2),
    'splinter': dict(chunk_type='splinter', count=3, scale=0.6, spread=0.2),
    'smoke': dict(emit_type='tendrils', tendril_type='smoke', count=2,
                  scale=0.8, spread=0.2),
    'distort': dict(emit_type='distortion', count=1, scale=0.9, spread=0.2),
}
_FX: dict[str, str] = {}
_RUN: dict = {'act': None, 'timer': None}


def _fx_tick() -> None:
    ref = _RUN['act']
    act = ref() if ref else None
    if act is None or not _FX:
        return
    for p in list(act.players):
        spec = EFFECTS.get(_FX.get(_key(p), ''))
        if spec is None or not _alive(p):
            continue
        try:
            x, y, z = p.actor.node.position
            bs.emitfx(position=(x, y + 0.6, z), velocity=(0.0, 1.5, 0.0),
                      **spec)
        except Exception:
            pass


def _on_begin(act) -> None:
    _RUN['timer'] = None
    with act.context:
        _RUN['act'] = weakref.ref(act)
        _RUN['timer'] = bs.Timer(0.2, _fx_tick, repeat=True)


@command('fx', level=80,
         usage='/fx list | /fx <effect> [player|id] | /fx off [player|id]',
         help='Particle effect on a player (until restart)')
def _fxcmd(ctx):
    a = ctx.args
    if not a or a[0].lower() == 'list':
        return ctx.reply('Effects: ' + ', '.join(sorted(EFFECTS)))
    name = a[0].lower()
    if name != 'off' and name not in EFFECTS:
        return ctx.error('Unknown effect. /fx list')
    if len(a) > 1:
        cid, acc, tname, err = utils.resolve_target(a[1])
        if err:
            return ctx.error(err)
        key = acc or f'cid:{cid}'
    else:
        key, tname = ctx.account or f'cid:{ctx.client_id}', 'you'
    if name == 'off':
        _FX.pop(key, None)
    else:
        _FX[key] = name
    ctx.reply(f'Effect for {tname}: {name}')


# ----------------------------------------------------------- me / info ----
def _coins(account):
    try:
        from lucious.economy import store
    except Exception:
        return None
    for fn in ('get_balance', 'balance', 'get_coins', 'coins'):
        f = getattr(store, fn, None)
        if callable(f):
            try:
                return int(f(account))
            except Exception:
                return None
    return None


def _card(ctx, cid, account, name) -> None:
    level = (roles.level_of_client(cid, account) if cid is not None
             else roles.level_of(account))
    lines = [f'Name: {name}']
    if cid is not None:
        lines.append(f'Client ID: {cid}')
    lines.append(f"Account: {account or 'not verified yet'}")
    lines.append(f'Role: {roles.role_name(account)} (level {level})')
    try:
        from lucious.tags import store as tagstore
        tag = tagstore.get(account)
        if tag:
            lines.append(f'Tag: {tag}')
    except Exception:
        pass
    if cid is not None:
        try:
            from lucious.tags.view import get_ping
            p = get_ping(cid)
            lines.append('Ping: ' + ('?' if p is None else f'{p} ms'))
        except Exception:
            pass
    coins = _coins(account)
    if coins is not None:
        lines.append(f'Coins: {coins}')
    for line in lines:
        ctx.reply(line)


@command('me', level=0, usage='/me', help='Your player card')
def _me(ctx):
    _card(ctx, ctx.client_id, ctx.account, ctx.name)


@command('info', level=80,
         usage='/info <player|client id|pb-id|a-id>',
         help="Show a player's card")
def _info(ctx):
    if not ctx.args:
        return ctx.error('Usage: /info <player|client id|pb-id|a-id>')
    cid, acc, name, err = utils.resolve_target(ctx.args[0])
    if err:
        return ctx.error(err)
    _card(ctx, cid, acc, name)


# ------------------------------------------------------------- restart ----
_R: dict = {'timer': None, 'end': 0.0, 'sent': set()}


def _flag(on: bool) -> None:
    try:
        import _babase
        _babase.restart_scheduled = on     # your text-on-map banner may read it
    except Exception:
        pass


def _restart_tick() -> None:
    left = _R['end'] - time.monotonic()
    if left <= 0:
        _R['timer'] = None
        log.warning('[Lucious] restart: quitting now')
        babase.quit()
        return
    sec = math.ceil(left)
    if sec in (60, 30, 10, 5, 4, 3, 2, 1) and sec not in _R['sent']:
        _R['sent'].add(sec)
        bs.broadcastmessage(f'Server restarting in {sec}s',
                            color=(1.0, 0.4, 0.4), transient=True)


@command('restart', level=100, aliases=('reboot',),
         usage='/restart [seconds|now|cancel]',
         help='Quit the server (a wrapper must start it again)')
def _restart(ctx):
    arg = ctx.args[0].lower() if ctx.args else ''
    if arg == 'cancel':
        if _R['timer'] is None:
            return ctx.error('No restart is scheduled.')
        _R['timer'] = None
        _flag(False)
        return _announce('Restart cancelled.')
    if _R['timer'] is not None:
        return ctx.error('Already scheduled. /restart cancel to stop it.')
    if arg == 'now':
        secs = 0.0
    elif arg:
        try:
            secs = max(1.0, min(600.0, float(arg)))
        except ValueError:
            return ctx.error('Usage: /restart [seconds|now|cancel]')
    else:
        secs = 10.0
    _flag(True)
    log.warning('[Lucious] restart requested by %s (%.0fs)', ctx.name, secs)
    if secs <= 0:
        babase.quit()
        return
    _R['end'], _R['sent'] = time.monotonic() + secs, set()
    _R['timer'] = bs.AppTimer(1.0, _restart_tick, repeat=True)
    _announce(f'Server restarting in {secs:.0f}s ({ctx.name})')


# ------------------------------------------------------------ lifecycle ----
def setup() -> None:
    bus.subscribe('activity_begin', _on_begin, priority=80)
    act = _activity()
    if act is not None:
        try:
            _on_begin(act)
        except Exception:
            log.exception('[Lucious] fx timer start failed')


def teardown() -> None:
    _RUN['timer'] = None
    _RUN['act'] = None
    _FX.clear()
