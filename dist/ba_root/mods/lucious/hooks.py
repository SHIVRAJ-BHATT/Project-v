"""Engine hooks, installed once. Everything else uses the EventBus."""
from __future__ import annotations

import logging
import types

import babase
import bascenev1 as bs

from lucious import utils
from lucious.events import bus

log = logging.getLogger('lucious')
_installed = False
_orig_chat = None
_watcher = None


def dispatch_chat(msg: str, client_id: int):
    try:
        result = bus.filter('chat', msg, client_id)
    except Exception:
        log.exception('[Lucious] chat pipeline crashed; passing through')
        result = msg
    if result is None:
        return None
    if _orig_chat is not None:
        try:
            return _orig_chat(result, client_id)
        except Exception:
            log.exception('[Lucious] original chat filter crashed')
    return result


def _chat_trampoline(msg, client_id):
    return __import__('lucious.hooks', fromlist=['dispatch_chat']
                      ).dispatch_chat(msg, client_id)


def _install_chat() -> None:
    """Swap the code object so the engine's cached reference is redirected."""
    global _orig_chat
    from bascenev1 import _hooks
    target = _hooks.filter_chat_message
    _orig_chat = types.FunctionType(
        target.__code__, target.__globals__, 'lucious_orig_chat',
        target.__defaults__, target.__closure__)
    target.__code__ = _chat_trampoline.__code__


def _install_session() -> None:
    orig = bs.Session.on_player_request

    def on_player_request(self, player):
        if not bus.check('player_request', self, player):
            return False
        return orig(self, player)
    bs.Session.on_player_request = on_player_request


def _install_activity() -> None:
    orig_begin = bs.Activity.on_begin

    def on_begin(self):
        orig_begin(self)
        bus.emit('activity_begin', self)
    bs.Activity.on_begin = on_begin


class RosterWatcher:
    """Vanilla-safe join/leave/verified detection by polling the roster."""

    def __init__(self) -> None:
        self.known: dict[int, dict] = {}
        self.timer = babase.AppTimer(1.0, self._tick, repeat=True)

    def _tick(self) -> None:
        current = {e['client_id']: e for e in utils.roster()
                   if e.get('client_id', utils.HOST) != utils.HOST}
        for cid, info in current.items():
            prev = self.known.get(cid)
            if prev is None:
                bus.emit('client_join', cid, info)
            elif not prev.get('account_id') and info.get('account_id'):
                bus.emit('client_account', cid, info)
        for cid in set(self.known) - set(current):
            bus.emit('client_leave', cid, self.known[cid])
        self.known = current


def install() -> None:
    global _installed, _watcher
    if _installed:
        return
    for name, fn in (('chat', _install_chat), ('session', _install_session),
                     ('activity', _install_activity)):
        try:
            fn()
        except Exception:
            log.exception('[Lucious] failed to install %s hook', name)
    _watcher = RosterWatcher()
    _installed = True
