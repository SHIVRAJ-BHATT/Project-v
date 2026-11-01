# lucious/economy/__init__.py
"""Lucious Coin economy. Needs lucious.roles (loaded before it)."""
from __future__ import annotations

import sys

import babase

from lucious import config, utils
from lucious.events import bus

__reload_order__ = ('lucious.economy.store', 'lucious.economy.shop',
                    'lucious.economy.cmds')
_timer = None


def _on_account(_cid, info) -> None:
    acc = (info or {}).get('account_id')
    if acc:
        from lucious.economy import store
        store.touch(acc, utils.display_name(info))


def _pay_tick() -> None:
    from lucious.economy import store
    amount = int(config.get('economy.earn.per_minute', 2))
    afk = getattr(sys.modules.get('lucious.anticheat'), 'is_afk', None)
    seen: set[str] = set()
    for e in utils.roster():
        acc = e.get('account_id')
        if (amount <= 0 or not acc or acc in seen
                or e.get('client_id', utils.HOST) == utils.HOST):
            continue
        seen.add(acc)
        if not (afk and afk(acc)):
            store.add(acc, amount, 'playtime', utils.display_name(e))


def setup() -> None:
    global _timer
    from lucious import commands
    from lucious.economy import cmds, shop, store  # noqa: F401
    store.open_db()
    commands.ACCESS_PROVIDERS.append(shop.access)
    bus.subscribe('activity_begin', shop.on_begin)
    bus.subscribe('client_join', _on_account)
    bus.subscribe('client_account', _on_account)
    _timer = babase.AppTimer(60.0, _pay_tick, repeat=True)


def teardown() -> None:
    global _timer
    _timer = None
    from lucious.economy import store
    store.close_db()
