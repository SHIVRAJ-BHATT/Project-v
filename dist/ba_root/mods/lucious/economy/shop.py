# lucious/economy/shop.py
"""Catalog, purchases, effect application and shop-only perk commands."""
from __future__ import annotations

import time

import bascenev1 as bs

from lucious import config, utils
from lucious.commands import command
from lucious.economy import store
from lucious.roles import store as rolestore

DEFAULT_ITEMS = {
    'sparks':  {'kind': 'effect', 'name': 'Spark Trail', 'price': 400, 'days': 7},
    'frost':   {'kind': 'effect', 'name': 'Frost Trail', 'price': 400, 'days': 7},
    'slime':   {'kind': 'effect', 'name': 'Slime Trail', 'price': 350, 'days': 7},
    'rainbow': {'kind': 'effect', 'name': 'Rainbow Skin', 'price': 900, 'days': 7},
    'aura':    {'kind': 'effect', 'name': 'Glow Aura', 'price': 600, 'days': 7},
    'heal':    {'kind': 'command', 'name': '/heal', 'command': 'heal',
                'price': 800, 'days': 7},
    'shield':  {'kind': 'command', 'name': '/shield', 'command': 'shield',
                'price': 800, 'days': 7},
    'gloves':  {'kind': 'command', 'name': '/gloves', 'command': 'gloves',
                'price': 800, 'days': 7},
    'vip_week': {'kind': 'role', 'name': 'VIP (7 days)', 'role': 'vip',
                 'price': 5000, 'days': 7},
}
_cd: dict[tuple, float] = {}
TRAILS = {'sparks': 'spark', 'frost': 'ice', 'slime': 'slime'}


def catalog() -> dict:
    return config.get('shop.items') or DEFAULT_ITEMS


def buy(acc: str, item_id: str) -> tuple[bool, str]:
    it = catalog().get(item_id)
    if not it:
        return False, 'No such item. Try /shop'
    kind, price = it['kind'], int(it['price'])
    seconds = it['days'] * 86400 if it.get('days') else None
    if kind == 'role':
        role = (config.get('roles') or {}).get(it.get('role', ''))
        if role is None:
            return False, 'That role is not configured on this server.'
        if int(role.get('level', 0)) >= int(
                config.get('security.staff_bypass_level', 50)):
            return False, 'Staff roles cannot be sold.'
    if not store.spend(acc, price, f'buy:{item_id}'):
        return False, f'Not enough coins ({store.balance(acc)}/{price}).'
    try:
        if kind == 'role':
            rolestore.grant(acc, it['role'], seconds, by='shop')
        else:
            store.give(acc, item_id, kind, seconds)
    except Exception:
        store.add(acc, price, f'refund:{item_id}', earned=False)
        return False, 'Purchase failed, coins refunded.'
    tail = {'effect': ' Use /equip ' + item_id,
            'command': f" Use /{it.get('command', item_id)} in game.",
            'role': ' Your role is active now.'}[kind]
    return True, f"Bought {it.get('name', item_id)}!{tail}"


def access(account, cmd_name: str) -> bool:
    """Command access provider: owning a shop command unlocks it."""
    if not account:
        return False
    return any(it.get('kind') == 'command' and it.get('command') == cmd_name
               and store.own(account, iid) for iid, it in catalog().items())


# ---- effects -----------------------------------------------------------
def _puff(node, chunk: str) -> None:
    if node.exists():
        p = node.position
        bs.emitfx(position=(p[0], p[1] + 0.2, p[2]), velocity=(0, 0.5, 0),
                  count=2, scale=0.5, spread=0.3, chunk_type=chunk)


def apply_effect(actor, fx: str) -> None:
    node = actor.node
    if fx == 'rainbow':
        bs.animate_array(node, 'color', 3, {
            0.0: (1, 0.2, 0.2), 1.0: (1, 1, 0.2), 2.0: (0.2, 1, 0.3),
            3.0: (0.2, 0.8, 1), 4.0: (0.7, 0.3, 1), 5.0: (1, 0.2, 0.2)},
            loop=True)
    elif fx == 'aura':
        light = bs.newnode('light', owner=node, attrs={
            'color': (0.6, 0.8, 1.0), 'radius': 0.12, 'intensity': 0.6,
            'volume_intensity_scale': 0.5})
        node.connectattr('position', light, 'position')
    elif fx in TRAILS:
        chunk = TRAILS[fx]
        actor._lc_fx = bs.Timer(0.1, lambda: _puff(node, chunk), repeat=True)


def _scan() -> None:
    activity = bs.getactivity()
    for p in activity.players:
        try:
            actor = p.actor
            if (actor is None or not actor.is_alive()
                    or getattr(actor, '_lc_fx_done', False)):
                continue
            actor._lc_fx_done = True
            cid = p.sessionplayer.inputdevice.client_id
            acc = utils.account_of(cid) if cid != utils.HOST else None
            item = store.equipped(acc, 'effect') if acc else None
            if item:
                apply_effect(actor, catalog().get(item, {}).get('fx', item))
        except Exception:
            continue


def on_begin(activity) -> None:
    if hasattr(activity, 'map'):
        activity._lc_fx_timer = bs.Timer(0.5, _scan, repeat=True)


# ---- shop-only perk commands (level 100 = owner, others must buy) -------
def _powerup(ctx, kind: str) -> bool:
    activity = bs.get_foreground_host_activity()
    if activity is None:
        return False
    with activity.context:
        for p in activity.players:
            try:
                if (p.sessionplayer.inputdevice.client_id == ctx.client_id
                        and p.actor and p.actor.is_alive()):
                    p.actor.handlemessage(bs.PowerupMessage(kind))
                    return True
            except Exception:
                continue
    return False


def _perk(ctx, name: str, powerup: str, cooldown: int = 45) -> None:
    key, now = (ctx.client_id, name), time.time()
    left = _cd.get(key, 0) + cooldown - now
    if left > 0:
        return ctx.error(f'/{name} ready in {int(left)}s.')
    if _powerup(ctx, powerup):
        _cd[key] = now
    else:
        ctx.error('You must be alive in a game.')


@command('heal', level=100, usage='/heal', help='Restore health (shop)')
def cmd_heal(ctx):
    _perk(ctx, 'heal', 'health')


@command('shield', level=100, usage='/shield', help='Get a shield (shop)')
def cmd_shield(ctx):
    _perk(ctx, 'shield', 'shield', 60)


@command('gloves', level=100, usage='/gloves', help='Boxing gloves (shop)')
def cmd_gloves(ctx):
    _perk(ctx, 'gloves', 'punch', 60)
