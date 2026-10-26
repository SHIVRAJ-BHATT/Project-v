"""Strike ladder: warn -> mute -> kick -> tempban, with decay."""
from __future__ import annotations

import time

from lucious import config, roles, utils
from lucious.security import alerts, storage

_strikes: dict[str, list[float]] = {}


def _bypass(cid: int, acc: str | None) -> bool:
    return cid == utils.HOST or roles.level_of(acc) >= int(
        config.get('security.staff_bypass_level', 50))


def strikes_of(acc: str) -> int:
    decay = float(config.get('security.strikes.decay_minutes', 30)) * 60
    now = time.time()
    return len([t for t in _strikes.get(acc, []) if now - t < decay])


def add_strike(cid: int, acc: str | None, reason: str, weight: int = 1) -> None:
    if _bypass(cid, acc):
        return
    cfg = config.get('security.strikes', {}) or {}
    decay = float(cfg.get('decay_minutes', 30)) * 60
    now = time.time()
    key = acc or f'cid:{cid}'
    lst = [t for t in _strikes.get(key, []) if now - t < decay]
    prev = len(lst)
    lst.extend([now] * max(1, int(weight)))
    _strikes[key] = lst
    total = len(lst)
    crossed = [s for s in cfg.get('ladder', [])
               if prev < int(s.get('at', 0)) <= total]
    if not crossed:
        utils.tell(cid, f'Warning: {reason} [{total} strike(s)]', utils.YELLOW)
        return
    step = max(crossed, key=lambda s: int(s['at']))
    apply_action(cid, acc, step.get('action', 'warn'), reason,
                 minutes=step.get('minutes'))


def apply_action(cid: int, acc: str | None, action: str, reason: str,
                 by: str = 'AutoMod', minutes: float | None = None) -> None:
    name = utils.name_of(cid)
    seconds = float(minutes) * 60 if minutes else None
    if action in ('mute', 'tempban') and not acc:
        action = 'kick'
    if action == 'warn':
        if acc:
            storage.add_warn(acc, reason, by)
        utils.tell(cid, f'FINAL WARNING: {reason}. Next = punishment.',
                   utils.RED)
    elif action == 'mute':
        storage.add_mute(acc, reason, by, seconds or 300)
        utils.tell(cid, f'Muted {utils.fmt_duration(seconds or 300)}: '
                        f'{reason}', utils.RED)
        utils.announce(f'{name} was muted ({reason}).')
    elif action == 'kick':
        utils.tell(cid, f'Kicked: {reason}', utils.RED)
        utils.announce(f'{name} was kicked ({reason}).')
        utils.kick(cid, int(config.get('security.kick_cooldown_seconds', 60)),
                   delay=1.0)
    elif action == 'tempban':
        storage.add_ban('account', acc, reason, by, seconds or 3600)
        utils.tell(cid, f'Banned {utils.fmt_duration(seconds or 3600)}: '
                        f'{reason}', utils.RED)
        utils.announce(f'{name} was banned ({reason}).', utils.RED)
        utils.kick(cid, 300, delay=1.0)
    else:
        return
    storage.audit(by, f'auto_{action}', acc or f'cid:{cid}', reason)
    alerts.send(f'AutoMod: {action}',
                f'**Player:** {name} (`{acc}`)\n**Reason:** {reason}')


def reset(acc: str) -> None:
    _strikes.pop(acc, None)
