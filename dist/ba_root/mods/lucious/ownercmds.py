# lucious/ownercmds.py
"""Owner commands: /end, /ic (invincible), /ice (freeze all), /bombshower."""
from __future__ import annotations

import random

import bascenev1 as bs
from bascenev1lib.actor.bomb import Bomb

from lucious import utils
from lucious.commands import command
from lucious.events import bus

BOMB_TYPES = ['normal', 'ice', 'sticky', 'impact', 'land_mine', 'tnt']
_invincible: set[str] = set()      # account ids, or 'cid:N' for unverified


def _game():
    activity = bs.get_foreground_host_activity()
    return activity if isinstance(activity, bs.GameActivity) else None


def _alive(activity):
    """(client_id, player) for living players. Call inside activity.context."""
    for p in activity.players:
        try:
            if p.actor is not None and p.actor.is_alive():
                yield p.sessionplayer.inputdevice.client_id, p
        except Exception:
            continue


def _key(cid: int) -> str:
    return utils.account_of(cid) or f'cid:{cid}'


@command('end', level=100, usage='/end', help='End the current game now')
def cmd_end(ctx):
    game = _game()
    if game is None:
        return ctx.error('No game is running.')
    utils.announce(f'{ctx.name} ended the game.')
    with game.context:
        game.end_game()


@command('ic', level=100, usage='/ic [player|id]',
         help='Toggle invincibility (you, or a player)')
def cmd_ic(ctx):
    game = _game()
    if game is None:
        return ctx.error('No game is running.')
    cid, name = ctx.client_id, ctx.name
    if ctx.args:
        cid, _acc, name, err = utils.resolve_target(ctx.args[0])
        if err or cid is None:
            return ctx.error(err or 'That player is offline.')
    key = _key(cid)
    on = key not in _invincible
    _invincible.add(key) if on else _invincible.discard(key)
    with game.context:
        for pcid, p in _alive(game):
            if pcid == cid:
                p.actor.node.invincible = on
    ctx.reply(f'{name}: invincible {"ON" if on else "OFF"}',
              utils.GREEN if on else utils.YELLOW)


def _ic_tick() -> None:
    """Re-apply to respawned players (new body = invincibility is lost)."""
    if not _invincible:
        return
    for cid, p in _alive(bs.getactivity()):
        if _key(cid) in _invincible and not p.actor.node.invincible:
            p.actor.node.invincible = True


def _on_begin(activity) -> None:
    if isinstance(activity, bs.GameActivity):
        with activity.context:
            activity._lc_ic_timer = bs.Timer(0.5, _ic_tick, repeat=True)


@command('ice', level=100, usage='/ice [seconds 1-30] [all]',
         help='Freeze everyone (not you, unless "all")')
def cmd_ice(ctx):
    game = _game()
    if game is None:
        return ctx.error('No game is running.')
    seconds, include_self = 5, False
    for arg in ctx.args:
        if arg.lower() == 'all':
            include_self = True
        elif arg.isdigit():
            seconds = min(max(int(arg), 1), 30)
    actors = []
    with game.context:
        for cid, p in _alive(game):
            if cid == ctx.client_id and not include_self:
                continue
            p.actor.handlemessage(bs.FreezeMessage())
            actors.append(p.actor)

        def thaw() -> None:
            for actor in actors:
                if actor.is_alive():
                    actor.handlemessage(bs.ThawMessage())
        game._lc_ice_timer = bs.Timer(float(seconds), thaw)
    utils.announce(f'FREEZE! ({len(actors)} players, {seconds}s)')


@command('bombshower', level=100, aliases=('shower',),
         usage='/bombshower [seconds 1-30] [normal|ice|sticky|impact|land_mine|tnt|all]',
         help='Rain bombs over the whole map')
def cmd_bombshower(ctx):
    game = _game()
    if game is None:
        return ctx.error('No game is running.')
    seconds, kind = 10, 'all'
    for arg in ctx.args:
        if arg.isdigit():
            seconds = min(max(int(arg), 1), 30)
        elif arg.lower() in BOMB_TYPES + ['all']:
            kind = arg.lower()
        else:
            return ctx.error('Unknown bomb type. Try tnt, ice, sticky, all...')
    b = game.map.defs.boxes['map_bounds']
    cx, cy, cz, sx, sy, sz = b[0], b[1], b[2], b[6], b[7], b[8]
    left = [int(seconds / 0.15)]

    def drop() -> None:
        if left[0] <= 0:
            game._lc_shower = None
            return
        left[0] -= 1
        Bomb(position=(random.uniform(cx - 0.45 * sx, cx + 0.45 * sx),
                       cy + 0.4 * sy,
                       random.uniform(cz - 0.45 * sz, cz + 0.45 * sz)),
             velocity=(0.0, -2.0, 0.0),
             bomb_type=random.choice(BOMB_TYPES) if kind == 'all' else kind
             ).autoretain()

    with game.context:
        game._lc_shower = bs.Timer(0.15, drop, repeat=True)
    utils.announce('BOMB SHOWER!', utils.RED)


def setup() -> None:
    bus.subscribe('activity_begin', _on_begin)


def teardown() -> None:
    _invincible.clear()
