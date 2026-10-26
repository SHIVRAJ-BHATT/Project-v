"""Core commands: help, id, list, lc."""
from __future__ import annotations

from lucious import commands, config, core, roles, utils
from lucious.commands import command


@command('help', aliases=('h',), usage='/help [page]', help='List commands')
def cmd_help(ctx):
    cmds = sorted((c for c in commands.all_commands() if c.level <= ctx.level),
                  key=lambda c: (c.level, c.name))
    per = 6
    pages = max(1, (len(cmds) + per - 1) // per)
    page = int(ctx.args[0]) if ctx.args and ctx.args[0].isdigit() else 1
    page = min(max(page, 1), pages)
    ctx.reply(f'Commands ({page}/{pages}):', utils.YELLOW)
    for c in cmds[(page - 1) * per:page * per]:
        ctx.reply(f'{c.usage} - {c.help}')


@command('id', usage='/id', help='Show your account id')
def cmd_id(ctx):
    ctx.reply(f'Account: {ctx.account or "not verified yet"} | '
              f'Role: {roles.role_name(ctx.account)}')


@command('list', level=50, aliases=('players',), usage='/list',
         help='Clients with ids')
def cmd_list(ctx):
    entries = [e for e in utils.roster() if e.get('client_id', -1) != -1]
    if not entries:
        return ctx.reply('No clients online.')
    for e in entries:
        acc = e.get('account_id')
        ctx.reply(f"[{e['client_id']}] {utils.display_name(e)} | "
                  f"{acc or 'unverified'} | {roles.role_name(acc)}")


@command('lc', level=100, usage='/lc status|reload <module>|config',
         help='Core control')
def cmd_lc(ctx):
    sub = ctx.args[0].lower() if ctx.args else 'status'
    if sub == 'status':
        for name, st in core.STATE.items():
            ctx.reply(f"{'OK' if st['ok'] else 'ERR'} {name} "
                      f"({st['ms']:.0f}ms) {st['error']}",
                      utils.GREEN if st['ok'] else utils.RED)
    elif sub == 'reload' and len(ctx.args) > 1:
        ok = core.reload(ctx.args[1])
        ctx.reply(f"Reload {ctx.args[1]}: {'OK' if ok else 'FAILED (see log)'}",
                  utils.GREEN if ok else utils.RED)
    elif sub == 'config':
        config.load()
        ctx.reply('Config reloaded.', utils.GREEN)
    else:
        ctx.error('Usage: /lc status | reload <module> | config')
