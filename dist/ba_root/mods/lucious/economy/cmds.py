# lucious/economy/cmds.py
"""Player-facing economy commands."""
from __future__ import annotations

import time

from lucious import config, utils
from lucious.commands import command
from lucious.economy import shop, store
from lucious.roles import ids

KINDS = {'effects': 'effect', 'commands': 'command', 'roles': 'role'}


def _need(ctx) -> bool:
    if ctx.account:
        return True
    ctx.error('Your account is not verified yet. Try again in a few seconds.')
    return False


@command('coins', aliases=('bal', 'balance'), usage='/coins [player]',
         help='Show Lucious Coins')
def cmd_coins(ctx):
    if ctx.args:
        acc, name, err = ids.resolve(ctx.args[0])
        return ctx.error(err) if err else ctx.reply(
            f'{name}: {store.balance(acc)} coins')
    if _need(ctx):
        ctx.reply(f'You have {store.balance(ctx.account)} Lucious Coins',
                  utils.YELLOW)


@command('daily', usage='/daily', help='Claim free daily coins')
def cmd_daily(ctx):
    if not _need(ctx):
        return
    left = store.last_daily(ctx.account) + 86400 - time.time()
    if left > 0:
        return ctx.error(f'Next daily in {utils.fmt_duration(left)}.')
    amount = int(config.get('economy.daily', 100))
    store.set_daily(ctx.account)
    bal = store.add(ctx.account, amount, 'daily', ctx.name)
    ctx.reply(f'+{amount} coins! Balance: {bal}', utils.GREEN)


@command('pay', usage='/pay <player|id> <amount>', help='Send coins')
def cmd_pay(ctx):
    if not _need(ctx):
        return
    if len(ctx.args) < 2 or not ctx.args[1].isdigit():
        return ctx.error('Usage: /pay <player|id> <amount>')
    acc, name, err = ids.resolve(ctx.args[0])
    amount = int(ctx.args[1])
    if err:
        return ctx.error(err)
    if acc == ctx.account or not 1 <= amount <= int(config.get('economy.max_pay', 5000)):
        return ctx.error('Invalid target or amount.')
    if store.transfer(ctx.account, acc, amount):
        ctx.reply(f'Sent {amount} coins to {name}.', utils.GREEN)
    else:
        ctx.error('Not enough coins.')


@command('shop', aliases=('store',), usage='/shop [effects|commands|roles]',
         help='Lucious Coin Store')
def cmd_shop(ctx):
    kind = KINDS.get(ctx.args[0].lower()) if ctx.args else None
    if not kind:
        ctx.reply('LUCIOUS COIN STORE', utils.YELLOW)
        ctx.reply('/shop effects | /shop commands | /shop roles')
        if ctx.account:
            ctx.reply(f'Your coins: {store.balance(ctx.account)}')
        return
    for iid, it in shop.catalog().items():
        if it.get('kind') == kind:
            span = f"{it['days']}d" if it.get('days') else 'forever'
            ctx.reply(f"{iid}: {it.get('name', iid)} - {it['price']} coins ({span})")
    ctx.reply('Buy with /buy <id>')


@command('buy', usage='/buy <item id>', help='Buy a shop item')
def cmd_buy(ctx):
    if not _need(ctx):
        return
    if not ctx.args:
        return ctx.error('Usage: /buy <item id>')
    ok, msg = shop.buy(ctx.account, ctx.args[0].lower())
    ctx.reply(msg, utils.GREEN) if ok else ctx.error(msg)


@command('inv', aliases=('inventory',), usage='/inv', help='Your purchases')
def cmd_inv(ctx):
    if not _need(ctx):
        return
    rows = store.items_of(ctx.account)
    if not rows:
        return ctx.reply('Nothing owned yet. Try /shop')
    for item, kind, exp, eq in rows:
        left = 'forever' if exp is None else utils.fmt_duration(exp - time.time())
        ctx.reply(f"{item} ({kind}) - {left}{' [equipped]' if eq else ''}")


@command('equip', usage='/equip <effect id>', help='Equip an owned effect')
def cmd_equip(ctx):
    if not _need(ctx):
        return
    item = ctx.args[0].lower() if ctx.args else ''
    if not store.own(ctx.account, item) or \
            shop.catalog().get(item, {}).get('kind') != 'effect':
        return ctx.error('You do not own that effect. See /inv')
    store.equip(ctx.account, item, 'effect')
    ctx.reply(f'{item} equipped - active from your next spawn.', utils.GREEN)


@command('unequip', usage='/unequip', help='Remove your effect')
def cmd_unequip(ctx):
    if _need(ctx):
        store.unequip(ctx.account, 'effect')
        ctx.reply('Effect removed.', utils.GREEN)


@command('addcoins', level=100, usage='/addcoins <player|id> <amount>',
         help='Give coins (negative takes)')
def cmd_addcoins(ctx):
    try:
        acc, name, err = ids.resolve(ctx.args[0])
        amount = int(ctx.args[1])
    except (IndexError, ValueError):
        return ctx.error('Usage: /addcoins <player|id> <amount>')
    if err:
        return ctx.error(err)
    if amount < 0:
        amount = -min(-amount, store.balance(acc))
        ok = amount == 0 or store.spend(acc, -amount, f'admin:{ctx.name}')
        return ctx.reply(f'{name} now has {store.balance(acc)}') if ok else ctx.error('Failed.')
    ctx.reply(f'{name} now has {store.add(acc, amount, f"admin:{ctx.name}", earned=False)}')
