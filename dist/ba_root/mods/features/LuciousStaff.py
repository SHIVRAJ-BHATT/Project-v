# Released under the MIT License. See LICENSE for details.
# ba_meta require api 9
"""Lucious Staff - extra staff roles plus role / command management.

Roles (created once, only if missing - edit later in config.json):
    coowner 95 | leadstaff 85 | cs 40 (complaint staff) | tcs 30 (trial)
Commands: /addrole /removerole /createrole /addcmd /removecmd /rolecmds
A role's "commands" list in config.json lets that role use those commands
even below the command's normal level (via commands.ACCESS_PROVIDERS).
"""

from __future__ import annotations

import copy
import logging
import re

from lucious import commands, config, roles, utils
from lucious.commands import command
from lucious.roles import ids, store

log = logging.getLogger('lucious')

PRESETS = {
    'coowner': {'level': 95, 'tag': '[CO-OWNER]',
                'tagcolor': [1.0, 0.45, 0.85],
                'commands': ['end', 'ic', 'ice', 'bombshower'],
                'members': []},
    'leadstaff': {'level': 85, 'tag': '[LS]',
                  'tagcolor': [0.4, 0.9, 1.0],
                  'commands': [], 'members': []},
    'cs': {'level': 40, 'tag': '[CS]', 'tagcolor': [1.0, 0.65, 0.25],
           'commands': ['whois', 'warn', 'mute', 'unmute', 'kick', 'gp'],
           'members': []},
    'tcs': {'level': 30, 'tag': '[TCS]', 'tagcolor': [0.75, 0.75, 0.9],
            'commands': ['whois', 'warn', 'gp'], 'members': []},
}
ALIASES = {'ls': 'leadstaff', 'lead': 'leadstaff', 'co-owner': 'coowner',
           'co_owner': 'coowner'}
# only the owner may hand these out
BLOCKED = {'addcmd', 'removecmd', 'createrole', 'lc', 'doctor', 'restart'}


def _defs() -> dict:
    return config.get('roles') or {}


def _role(name) -> str:
    n = str(name).lower().strip()
    return ALIASES.get(n, n)


def _guard(ctx, role: str):
    defs = _defs()
    if role not in defs:
        return f'Unknown role "{role}". Try /role list'
    if ctx.level < 100 and int(defs[role].get('level', 0)) >= ctx.level:
        return 'You can only manage roles below your own level.'
    return None


def access(account, name: str) -> bool:
    """ACCESS provider: a role's own 'commands' list unlocks commands."""
    if not account:
        return False
    defs = _defs()
    for role in roles.roles_of(account):
        got = (defs.get(role) or {}).get('commands') or []
        if 'all' in got or name in got:
            return True
    return False


# ------------------------------------------------------------ roles ----
def _split(args):
    """Accept '<player> <role>' and '<role> <player>'."""
    defs = _defs()
    a, b = args[0], args[1]
    if _role(a) in defs and _role(b) not in defs:
        return _role(a), b
    return _role(b), a


@command('addrole', level=80,
         usage='/addrole <player|id> <role> [30m|7d|perm]',
         help='Give a role (name, client id, pb-/a- id)')
def cmd_addrole(ctx):
    if len(ctx.args) < 2:
        return ctx.error('Usage: /addrole <player|id> <role> [30m|7d|perm]')
    role, target = _split(ctx.args)
    msg = _guard(ctx, role)
    if msg:
        return ctx.error(msg)
    acc, name, err = ids.resolve(target)
    if err or not acc:
        return ctx.error(err or f'{name} has no verified account yet.')
    seconds = None
    if len(ctx.args) > 2:
        ok, seconds = utils.parse_duration(ctx.args[2])
        if not ok:
            return ctx.error('Bad duration. Use 30m, 7d or perm.')
    store.grant(acc, role, seconds, by=ctx.name)
    ctx.reply(f'{name} now has {role} ({utils.fmt_duration(seconds)})',
              utils.GREEN)


@command('removerole', level=80, usage='/removerole <player|id> <role>',
         help='Take a role away')
def cmd_removerole(ctx):
    if len(ctx.args) < 2:
        return ctx.error('Usage: /removerole <player|id> <role>')
    role, target = _split(ctx.args)
    msg = _guard(ctx, role)
    if msg:
        return ctx.error(msg)
    acc, name, err = ids.resolve(target)
    if err or not acc:
        return ctx.error(err or f'{name} has no verified account yet.')
    fixed = list(_defs()[role].get('members', []))
    was_fixed = acc in fixed
    if was_fixed:
        fixed.remove(acc)
        config.set_value(f'roles.{role}.members', fixed)
    done = store.revoke(acc, role) or was_fixed
    ctx.reply(f'{name}: {role} removed' if done
              else f'{name} does not have {role}',
              utils.GREEN if done else utils.RED)


@command('createrole', level=95, usage='/createrole <name> [level] [tag]',
         help='Create a role (below your own level)')
def cmd_createrole(ctx):
    if not ctx.args:
        return ctx.error('Usage: /createrole <name> [level] [tag]')
    name = ctx.args[0].lower()
    if not re.fullmatch(r'[a-z][a-z0-9_]{1,15}', name) or name in _defs():
        return ctx.error('Invalid or existing role name (a-z, 0-9, _).')
    rest = ctx.args[1:]
    level = 10
    if rest and rest[0].isdigit():
        level, rest = int(rest[0]), rest[1:]
    cap = 99 if ctx.level >= 100 else ctx.level - 1
    level = max(0, min(level, cap))
    tag = ' '.join(rest)[:14]
    config.set_value(f'roles.{name}', {'level': level, 'tag': tag,
                                       'members': [], 'commands': []})
    ctx.reply(f'Role {name} created (level {level}).', utils.GREEN)


# --------------------------------------------------- command grants ----
@command('addcmd', level=95, aliases=('addcommand',),
         usage='/addcmd <command> <role>',
         help='Let a role use a command')
def cmd_addcmd(ctx):
    if len(ctx.args) != 2:
        return ctx.error('Usage: /addcmd <command> <role>')
    raw, role = ctx.args[0].lower().lstrip('/!'), _role(ctx.args[1])
    msg = _guard(ctx, role)
    if msg:
        return ctx.error(msg)
    if raw == 'all':
        if ctx.level < 100:
            return ctx.error('Only the owner can grant "all".')
        canon = 'all'
    else:
        cmd = commands._registry.get(raw)
        if cmd is None:
            return ctx.error(f'Unknown command /{raw}.')
        canon = cmd.name
        if cmd.level > ctx.level:
            return ctx.error('You cannot grant a command above your level.')
        if canon in BLOCKED and ctx.level < 100:
            return ctx.error('Only the owner can grant that command.')
    cur = list(_defs()[role].get('commands') or [])
    if canon in cur:
        return ctx.reply(f'{role} already has /{canon}.')
    cur.append(canon)
    config.set_value(f'roles.{role}.commands', cur)
    ctx.reply(f'{role} can now use /{canon}.', utils.GREEN)


@command('removecmd', level=95, aliases=('removecommand',),
         usage='/removecmd <command> <role>',
         help='Take a command away from a role')
def cmd_removecmd(ctx):
    if len(ctx.args) != 2:
        return ctx.error('Usage: /removecmd <command> <role>')
    raw, role = ctx.args[0].lower().lstrip('/!'), _role(ctx.args[1])
    msg = _guard(ctx, role)
    if msg:
        return ctx.error(msg)
    cmd = commands._registry.get(raw)
    canon = cmd.name if cmd else raw
    cur = list(_defs()[role].get('commands') or [])
    if canon not in cur:
        return ctx.error(f'{role} does not have /{canon}.')
    cur.remove(canon)
    config.set_value(f'roles.{role}.commands', cur)
    ctx.reply(f'{role} lost /{canon}.', utils.GREEN)


@command('rolecmds', level=80, usage='/rolecmds [role]',
         help='Show commands granted to roles')
def cmd_rolecmds(ctx):
    defs = _defs()
    if ctx.args:
        names = [_role(ctx.args[0])]
    else:
        names = [n for n, _ in sorted(
            defs.items(), key=lambda kv: -int(kv[1].get('level', 0)))]
    for n in names:
        r = defs.get(n)
        if r is None:
            ctx.error(f'Unknown role "{n}".')
            continue
        got = r.get('commands') or []
        ctx.reply(f"{n} (lvl {r.get('level', 0)}): "
                  + (', '.join(got) if got else '-'))


# ------------------------------------------------------------ lifecycle --
def _same(p) -> bool:
    return (p.__module__, p.__qualname__) == (access.__module__,
                                              access.__qualname__)


def setup() -> None:
    defs = _defs()
    for name, spec in PRESETS.items():
        if name not in defs:
            config.set_value(f'roles.{name}', copy.deepcopy(spec))
            log.info('[Lucious] role "%s" created', name)
    commands.ACCESS_PROVIDERS[:] = [p for p in commands.ACCESS_PROVIDERS
                                    if not _same(p)]
    commands.ACCESS_PROVIDERS.append(access)


def teardown() -> None:
    commands.ACCESS_PROVIDERS[:] = [p for p in commands.ACCESS_PROVIDERS
                                    if not _same(p)]
