# mods/lucious/tags/__init__.py
"""Head tags: role/custom tag + ping above players. Styles: clay | nm."""
from __future__ import annotations

import logging
import weakref

import bascenev1 as bs

from lucious import config, roles
from lucious.events import bus
from lucious.tags import store
from lucious.tags.view import TagView

log = logging.getLogger('lucious')
__reload_order__ = ('lucious.tags.store', 'lucious.tags.view',
                    'lucious.tags.cmds')

DEFAULT_ROLE_TAGS = {
    'owner': ('[OWNER]', None),            # None = rainbow
    'admin': ('[ADMIN]', (1.0, 0.35, 0.35)),
    'moderator': ('[MOD]', (0.4, 1.0, 0.5)),
    'vip': ('[VIP]', (1.0, 0.85, 0.3)),
}
CFG_DEFAULTS = {
    'enabled': True, 'ping': True,
    'style': 'clay',            # server default for /text
    'clay_scale': 0.009,        # clay (big font) letter scale
    'nm_scale': 0.0096,         # Lucious-script glyph scale
    'nm_height': 1.65,          # Lucious-script tag height
           # normal text scale
    'ping_scale': 0.01,
    'spacing_factor': 22.0,     # letter spacing = clay_scale * this
    'height': 1.55, 'ping_height': 1.95,
    'wave_amp': 0.07, 'wave_period': 1.6, 'rainbow_period': 3.0,
    'max_length': 14,
}
STATE: dict = {'timer': None, 'activity': None, 'views': {}, 'tick': 0,
               'warned': False}


def cfg(key: str):
    return config.get('tags.' + key, CFG_DEFAULTS[key])


def _snapshot() -> dict:
    return {k: cfg(k) for k in CFG_DEFAULTS}


def _desired(sp):
    try:
        account = sp.get_v1_account_id()
    except Exception:
        account = None
    try:
        cid = sp.inputdevice.client_id
    except Exception:
        cid = -1
    text, color = None, None
    custom = store.get(account)
    if custom:
        text, color = custom, None            # custom tags are rainbow
    elif account:
        role = roles.role_name(account)
        rc = (config.get('roles') or {}).get(role, {})
        if rc.get('tag'):
            text = rc['tag']
            color = tuple(rc['tagcolor']) if rc.get('tagcolor') else None
        elif role in DEFAULT_ROLE_TAGS:
            text, color = DEFAULT_ROLE_TAGS[role]
    style = (store.get_style(account or f'cid:{cid}') or cfg('style'))
    if style not in ('clay', 'nm'):
        style = 'clay'
    return text, color, style, cid


def _destroy_all() -> None:
    for v in list(STATE['views'].values()):
        try:
            v.destroy()
        except Exception:
            pass
    STATE['views'] = {}


def _scan() -> None:
    ref = STATE.get('activity')
    act = ref() if ref else None
    if act is None:
        return
    views = STATE['views']
    if not cfg('enabled'):
        _destroy_all()
        return
    snap = _snapshot()
    snap_sig = tuple(sorted(snap.items()))
    show_ping = bool(snap['ping'])
    seen = set()
    for player in list(act.players):
        try:
            if not player.exists():
                continue
            actor = player.actor
            node = getattr(actor, 'node', None)
            if (actor is None or node is None or not node.exists()
                    or getattr(actor, '_dead', False)):
                continue
            key = id(player)
            seen.add(key)
            text, color, style, cid = _desired(player.sessionplayer)
            sig = (id(node), text, color, style, show_ping, snap_sig)
            view = views.get(key)
            if view is None or view.sig != sig:
                if view is not None:
                    view.destroy()
                views[key] = TagView(node, text, style, color, cid,
                                     show_ping, snap, sig)
        except Exception:
            if not STATE['warned']:
                STATE['warned'] = True
                log.exception('[Lucious] tag scan error (logged once)')
    for key in set(views) - seen:
        views.pop(key).destroy()
    STATE['tick'] += 1
    if STATE['tick'] % 3 == 0:              # ping refresh every 1.5 s
        for v in views.values():
            v.update_ping()


def _on_begin(activity) -> None:
    _destroy_all()
    STATE['timer'] = None
    with activity.context:
        STATE['activity'] = weakref.ref(activity)
        STATE['timer'] = bs.Timer(0.5, _scan, repeat=True)


def setup() -> None:
    store.open_db()
    from lucious.tags import cmds  # noqa: F401  (registers commands)
    bus.subscribe('activity_begin', _on_begin, priority=60)


def teardown() -> None:
    STATE['timer'] = None
    _destroy_all()
    store.close_db()
