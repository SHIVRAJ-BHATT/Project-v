# mods/lucious/tags/cmds.py
from __future__ import annotations

from lucious import config, utils
from lucious.commands import command
from lucious.tags import cfg, CFG_DEFAULTS, store, view

_SCALE_KEYS = {'clay': 'clay_scale', 'nm': 'nm_scale', 'ping': 'ping_scale',
               'height': 'height', 'pingheight': 'ping_height'}


@command('tag', level=80, usage='/tag set|remove|list|ping|scale|reload',
         help='Manage head tags')
def _tag(ctx):
    sub = ctx.args[0].lower() if ctx.args else ''
    rest = ctx.args[1:]
    if sub == 'set':
        return _set(ctx, rest)
    if sub == 'remove' and rest:
        cid, acc, name, err = utils.resolve_target(rest[0])
        if err or not acc:
            return ctx.error(err or 'That player has no account yet.')
        return ctx.reply(f'Tag removed for {name}.' if store.remove(acc)
                         else f'{name} has no custom tag.')
    if sub == 'list':
        rows = store.all_tags()
        if not rows:
            return ctx.reply('No custom tags.')
        for acc, text, name in rows[:10]:
            ctx.reply(f'{name or acc}: {text}')
        if len(rows) > 10:
            ctx.reply(f'... and {len(rows) - 10} more.')
        return
    if sub == 'ping' and rest and rest[0].lower() in ('on', 'off'):
        config.set_value('tags.ping', rest[0].lower() == 'on')
        return ctx.reply(f'Head ping: {rest[0].lower()}')
    if sub == 'scale':
        if ctx.level < 100:
            return ctx.error('Owner only.')
        if len(rest) != 2 or rest[0].lower() not in _SCALE_KEYS:
            return ctx.error('Usage: /tag scale <clay|nm|ping|height|'
                             'pingheight> <number>')
        try:
            val = float(rest[1])
        except ValueError:
            return ctx.error('Number expected.')
        key = _SCALE_KEYS[rest[0].lower()]
        lo, hi = (0.003, 0.03) if 'scale' in key else (0.5, 3.0)
        val = max(lo, min(hi, val))
        config.set_value('tags.' + key, val)
        return ctx.reply(f'{key} = {val} (applies within 1 s)')
    if sub == 'reload':
        return ctx.reply('Tags re-sync every 0.5 s automatically.')
    ctx.reply('Usage: /tag set <player|id> <text> | remove <p> | list | '
              'ping on|off | scale <what> <n>')


def _set(ctx, rest):
    if len(rest) < 2:
        return ctx.error('Usage: /tag set <player|pb-id|a-id> <text>')
    cid, acc, name, err = utils.resolve_target(rest[0])
    if err:
        return ctx.error(err)
    if not acc:
        return ctx.error('That player has no verified account yet.')
    text = ' '.join(rest[1:]).strip()
    if not text or len(text) > int(cfg('max_length')):
        return ctx.error(f'Tag must be 1-{cfg("max_length")} characters.')
    store.set_tag(acc, text, name, ctx.name)
    ctx.reply(f'Tag for {name}: {text}')


@command('text', level=0, usage='/text clay|nm|default [player]',
         help='Choose your head-tag font: clay (chunky, wavy) or nm (normal)')
def _text(ctx):
    if not ctx.args:
        return ctx.reply('Usage: /text clay | nm | default')
    mode = ctx.args[0].lower()
    if mode in ('normal', 'plain'):
        mode = 'nm'
    if mode not in ('clay', 'nm', 'default'):
        return ctx.error('Use: clay, nm or default.')
    if len(ctx.args) > 1:
        if ctx.level < 80:
            return ctx.error('Only staff can change another player.')
        cid, acc, name, err = utils.resolve_target(ctx.args[1])
        if err:
            return ctx.error(err)
        key = acc or (f'cid:{cid}' if cid is not None else None)
        if key is None:
            return ctx.error('Could not identify that player.')
    else:
        key, name = ctx.account or f'cid:{ctx.client_id}', 'you'
    store.set_style(key, None if mode == 'default' else mode)
    ctx.reply(f'Tag font for {name}: {mode} (applies within 1 s)')


@command('ping', level=0, usage='/ping [player]', help='Show ping')
def _ping(ctx):
    cid, name = ctx.client_id, 'Your'
    if ctx.args:
        cid, _acc, name, err = utils.resolve_target(ctx.args[0])
        if err or cid is None:
            return ctx.error(err or 'Player is offline.')
    p = view.get_ping(cid)
    ctx.reply(f'{name} ping: ' + ('unknown' if p is None else f'{p}ms'))
