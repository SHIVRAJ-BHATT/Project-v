# lucious/roles/cmds.py
"""/role - manage roles by player name or by pb-/a- account id."""
from __future__ import annotations

import re

from lucious import config, roles, utils
from lucious.commands import command
from lucious.roles import ids, store

BUILTIN = ('owner', 'admin', 'moderator', 'vip')
USAGE = '/role list | info [t] | add <t> <role> [30m|7d|perm] | remove <t> <role> | create <name> <lvl> [tag] | delete <name>'


def _guard(ctx, role: str):
    defs = config.get('roles') or {}
    if role not in defs:
        return f'Unknown role "{role}". Try /role list'
    if ctx.level < 100 and int(defs[role].get('level', 0)) >= ctx.level:
        return 'You can only manage roles below your own level.'
    return None


@command('role', level=80, usage='/role <list|info|add|remove|create|delete>',
         help='Manage roles (pb-/a- ids)')
def cmd_role(ctx):
    a = ctx.args
    sub = a[0].lower() if a else 'list'
    defs = config.get('roles') or {}
    if sub == 'list':
        for n, r in sorted(defs.items(), key=lambda kv: -int(kv[1].get('level', 0))):
            ctx.reply(f"{n} lvl {r.get('level', 0)} tag {r.get('tag') or '-'} | "
                      f"{len(r.get('members', []))} fixed, "
                      f"{len(store.members_of(n))} granted")
    elif sub == 'info':
        acc, name, err = (ids.resolve(a[1]) if len(a) > 1
                          else (ctx.account, ctx.name, None))
        if err or not acc:
            return ctx.error(err or 'No verified account.')
        ctx.reply(f'{name} [{ids.kind(acc)}] {acc}', utils.YELLOW)
        grants = store.grants_of(acc)
        for r in roles.roles_of(acc):
            if r in grants:
                left = ('permanent' if grants[r] is None else
                        utils.fmt_duration(grants[r] - __import__('time').time()))
            else:
                left = 'fixed'
            ctx.reply(f'  {r}: {left}')
    elif sub in ('add', 'remove') and len(a) >= 3:
        role = a[2].lower()
        msg = _guard(ctx, role)
        if msg:
            return ctx.error(msg)
        acc, name, err = ids.resolve(a[1])
        if err:
            return ctx.error(err)
        if sub == 'add':
            seconds = None
            if len(a) > 3:
                ok, seconds = utils.parse_duration(a[3])
                if not ok:
                    return ctx.error('Bad duration. Use 30m, 7d or perm.')
            store.grant(acc, role, seconds, by=ctx.name)
            ctx.reply(f'{name} now has {role} ({utils.fmt_duration(seconds)})',
                      utils.GREEN)
        else:
            fixed = list(defs[role].get('members', []))
            was_fixed = acc in fixed
            if was_fixed:
                fixed.remove(acc)
                config.set_value(f'roles.{role}.members', fixed)
            done = store.revoke(acc, role) or was_fixed
            ctx.reply(f'{name}: {role} removed' if done
                      else f'{name} does not have {role}',
                      utils.GREEN if done else utils.RED)
    elif sub == 'create' and len(a) >= 3 and a[2].isdigit():
        if ctx.level < 100:
            return ctx.error('Owner only.')
        name = a[1].lower()
        if not re.fullmatch(r'[a-z][a-z0-9_]{1,15}', name) or name in defs:
            return ctx.error('Invalid or existing role name.')
        config.set_value(f'roles.{name}', {
            'level': min(int(a[2]), 99), 'tag': a[3] if len(a) > 3 else '',
            'members': []})
        ctx.reply(f'Role {name} created.', utils.GREEN)
    elif sub == 'delete' and len(a) >= 2:
        name = a[1].lower()
        if ctx.level < 100 or name in BUILTIN or name not in defs:
            return ctx.error('Owner only, and built-in roles cannot be deleted.')
        rest = {k: v for k, v in defs.items() if k != name}
        config.set_value('roles', rest)
        store.purge_role(name)
        ctx.reply(f'Role {name} deleted.', utils.GREEN)
    else:
        ctx.error(USAGE)
