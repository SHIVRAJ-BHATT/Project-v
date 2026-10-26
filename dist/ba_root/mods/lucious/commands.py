"""Command registry with permissions, cooldown and error isolation."""
from __future__ import annotations

import logging
import re
import shlex
import time
from dataclasses import dataclass, field
from typing import Callable

from lucious import config, roles, utils

log = logging.getLogger('lucious')


@dataclass
class Command:
    name: str
    handler: Callable
    level: int
    usage: str
    help: str
    owner: str
    aliases: tuple = field(default_factory=tuple)


@dataclass
class Ctx:
    client_id: int
    account: str | None
    level: int
    name: str
    args: list
    raw: str

    def reply(self, text: str, color=utils.CYAN) -> None:
        utils.tell(self.client_id, text, color)

    def error(self, text: str) -> None:
        utils.tell(self.client_id, text, utils.RED)


_registry: dict[str, Command] = {}
_last_use: dict[int, float] = {}
_NAME_RE = re.compile(r'^[a-z][a-z0-9_]*$')


def command(name: str, level: int = 0, aliases: tuple = (),
            usage: str = '', help: str = ''):
    def deco(fn: Callable) -> Callable:
        cmd = Command(name, fn, level, usage or f'/{name}', help,
                      fn.__module__, tuple(aliases))
        for n in (name, *aliases):
            _registry[n.lower()] = cmd
        return fn
    return deco


def all_commands() -> list[Command]:
    seen, out = set(), []
    for cmd in _registry.values():
        if cmd.name not in seen:
            seen.add(cmd.name)
            out.append(cmd)
    return out


def remove_owner(prefix: str) -> None:
    for key in [k for k, c in _registry.items()
                if c.owner == prefix or c.owner.startswith(prefix + '.')]:
        del _registry[key]


def chat_filter(msg: str, client_id: int):
    text = msg.strip()
    if len(text) < 2 or text[0] not in config.get('command_prefixes', ['/']):
        return msg
    try:
        parts = shlex.split(text[1:])
    except ValueError:
        parts = text[1:].split()
    if not parts or not _NAME_RE.match(parts[0].lower()):
        return msg
    name, args = parts[0].lower(), parts[1:]
    cmd = _registry.get(name)
    if cmd is None:
        utils.tell(client_id, f'Unknown command /{name}. Try /help',
                   utils.RED)
        return None
    now = time.time()
    if client_id != utils.HOST and now - _last_use.get(client_id, 0) < 0.8:
        utils.tell(client_id, 'Slow down.', utils.RED)
        return None
    _last_use[client_id] = now
    account = utils.account_of(client_id)
    level = roles.level_of_client(client_id, account)
    if level < cmd.level:
        utils.tell(client_id, 'You do not have permission.', utils.RED)
        return None
    ctx = Ctx(client_id, account, level, utils.name_of(client_id), args, msg)
    try:
        cmd.handler(ctx)
    except Exception:
        log.exception('[Lucious] command /%s crashed', name)
        ctx.error('Command failed (logged).')
    return None
