"""Chat guard: rate limit, mute, duplicates, links, bad words, caps."""
from __future__ import annotations

import re
import time
from collections import deque

from lucious import config, roles, utils
from lucious.events import bus
from lucious.security import punish, storage
from lucious.security.normalize import censor, skeleton, squash

_rate: dict[int, deque] = {}
_recent: dict[int, deque] = {}

LINK_RE = re.compile(
    r'(https?://|www\.|discord(?:app)?\.(?:gg|com/invite)'
    r'|\b[a-z0-9-]{2,}(?:\.|\s+dot\s+)(?:com|net|org|gg|io|xyz|me|ly|tk|ru)\b'
    r'|\b\d{1,3}(?:\.\d{1,3}){3}\b)', re.I)


def _bypass(cid: int, acc: str | None) -> bool:
    return cid == utils.HOST or roles.level_of(acc) >= int(
        config.get('security.staff_bypass_level', 50))


def rate_filter(msg: str, cid: int):
    """Priority 5: runs before commands so command spam is limited too."""
    acc = utils.account_of(cid)
    if _bypass(cid, acc):
        return msg
    c = config.get('security.chat', {}) or {}
    max_len = int(c.get('max_length', 120))
    if len(msg) > max_len:
        utils.tell(cid, f'Message too long (max {max_len}).', utils.RED)
        return None
    rate = c.get('rate', {})
    limit, window = int(rate.get('messages', 5)), float(rate.get('window', 6))
    dq = _rate.setdefault(cid, deque())
    now = time.time()
    while dq and now - dq[0] > window:
        dq.popleft()
    dq.append(now)
    if len(dq) > limit:
        dq.clear()
        punish.add_strike(cid, acc, 'Chat spam')
        return None
    return msg


def content_filter(msg: str, cid: int):
    """Priority 30: runs after commands (normal chat only)."""
    acc = utils.account_of(cid)
    if _bypass(cid, acc):
        return msg
    mute = storage.get_mute(acc)
    if mute:
        left = ('permanently' if mute['expires'] is None else
                f"for {utils.fmt_duration(mute['expires'] - time.time())}")
        utils.tell(cid, f"You are muted {left}. Reason: {mute['reason']}",
                   utils.RED)
        return None
    c = config.get('security.chat', {}) or {}

    key = squash(skeleton(msg))
    if key:
        dup = c.get('duplicate', {})
        count, window = int(dup.get('count', 3)), float(dup.get('window', 30))
        rq = _recent.setdefault(cid, deque())
        now = time.time()
        while rq and now - rq[0][0] > window:
            rq.popleft()
        same = sum(1 for _, k in rq if k == key)
        rq.append((now, key))
        if same + 1 >= count:
            punish.add_strike(cid, acc, 'Repeating messages')
            return None

    if c.get('block_links', True) and LINK_RE.search(msg):
        low = msg.lower()
        if not any(w.lower() in low for w in c.get('link_whitelist', [])):
            punish.add_strike(cid, acc, 'Advertising / links', weight=2)
            return None

    words = c.get('bad_words') or []
    if words:
        censored, hit = censor(msg, words)
        if hit:
            punish.add_strike(cid, acc, 'Bad language')
            if c.get('bad_word_action', 'censor') == 'block':
                return None
            msg = censored

    caps = c.get('caps', {})
    letters = [ch for ch in msg if ch.isalpha()]
    if len(letters) >= int(caps.get('min_length', 10)):
        if sum(ch.isupper() for ch in letters) / len(letters) > float(
                caps.get('max_ratio', 0.75)):
            msg = msg.lower()
    return msg


def on_leave(cid: int, _info: dict) -> None:
    _rate.pop(cid, None)
    _recent.pop(cid, None)


def setup() -> None:
    bus.subscribe('chat', rate_filter, priority=5)
    bus.subscribe('chat', content_filter, priority=30)
    bus.subscribe('client_leave', on_leave)
