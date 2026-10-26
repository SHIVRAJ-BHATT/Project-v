"""JSON config with deep-merged defaults and atomic saves."""
from __future__ import annotations

import copy
import json
import logging
import os
import threading
from typing import Any

log = logging.getLogger('lucious')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
CONFIG_PATH = os.path.join(DATA_DIR, 'config.json')

DEFAULTS: dict[str, Any] = {
    'server_tag': 'LUCIOUS',
    'command_prefixes': ['/', '!'],
    'modules': {'lucious.security': True},
    'roles': {
        'owner': {'level': 100, 'members': []},
        'admin': {'level': 80, 'members': []},
        'moderator': {'level': 50, 'members': []},
        'vip': {'level': 10, 'members': []},
    },
    'security': {
        'staff_bypass_level': 50,
        'require_account': True,
        'account_wait_seconds': 10,
        'max_players_per_client': 2,
        'kick_cooldown_seconds': 60,
        'warn_limit': 3,
        'warn_ban_minutes': 30,
        'lockdown': False,
        'lockdown_min_level': 10,
        'lockdown_allow_known_players': True,
        'rejoin_flood': {'joins': 4, 'window': 60, 'ban_minutes': 10},
        'names': {
            'min_length': 2,
            'max_length': 32,
            'banned_patterns': ['admin', 'owner', 'moderator'],
            'protected_names': [],
            'block_impersonation': True,
        },
        'chat': {
            'max_length': 120,
            'rate': {'messages': 5, 'window': 6},
            'duplicate': {'count': 3, 'window': 30},
            'caps': {'min_length': 10, 'max_ratio': 0.75},
            'block_links': True,
            'link_whitelist': [],
            'bad_words': [],
            'bad_word_action': 'censor',
        },
        'strikes': {
            'decay_minutes': 30,
            'ladder': [
                {'at': 2, 'action': 'warn'},
                {'at': 3, 'action': 'mute', 'minutes': 5},
                {'at': 5, 'action': 'kick'},
                {'at': 7, 'action': 'tempban', 'minutes': 60},
            ],
        },
        'discord_webhook': '',
    },
}

_lock = threading.RLock()
_data: dict[str, Any] = copy.deepcopy(DEFAULTS)


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, val in override.items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], val)
        else:
            out[key] = val
    return out


def load() -> None:
    global _data
    os.makedirs(DATA_DIR, exist_ok=True)
    user: dict = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, encoding='utf-8') as f:
                user = json.load(f)
        except Exception:
            log.exception('[Lucious] config.json invalid - using defaults '
                          '(file NOT overwritten, fix it and /lc config)')
            with _lock:
                _data = copy.deepcopy(DEFAULTS)
            return
    with _lock:
        _data = _merge(DEFAULTS, user)
    save()


def save() -> None:
    with _lock:
        tmp = CONFIG_PATH + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(_data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, CONFIG_PATH)


def get(path: str, default: Any = None) -> Any:
    with _lock:
        node: Any = _data
        for part in path.split('.'):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node


def set_value(path: str, value: Any, persist: bool = True) -> None:
    with _lock:
        node = _data
        parts = path.split('.')
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
    if persist:
        save()
