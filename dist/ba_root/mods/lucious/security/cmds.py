"""Staff moderation commands with hierarchy protection and audit."""
from __future__ import annotations

import time

from lucious import config, roles, utils
from lucious.commands import command
from lucious.security import alerts, punish, storage
from lucious.security.normalize import name_key

MOD, ADMIN, OWNER = 50, 80, 100


def _ts(t: float | None) -> str:
    return time.strftime('%Y-%m-%d %H:%M', time.localtime(t)) if t else '-'


def _target(ctx, arg: str, need_account: bool = False):
    cid, acc, name, err = utils.resolve_target(arg)
    if err:
        ctx.error(err)
        return None
    if need_account and not acc:
        ctx.error(f'{name} has no verified account yet. Use /kick.')
        return None
    if (cid is not None and cid == ctx.client_id) or (
            acc and acc == ctx.account):
        ctx.error("You can't use this on yourself.")
        return None
    if acc and roles.level_of(acc) >= ctx.level:
        ctx.error(f'{name} has equal or higher rank.')
        return None
    return cid, acc, name


def _record(ctx, action: str, acc, name: str, detail: str,
            color: int = 0xE67E22) -> None:
    storage.audit(ctx.account or ctx.name, action, acc or name, detail)
    alerts.send(action.upper(), f'**By:** {ctx.name} (`{ctx.account}`)\n'
                f'**Target:** {name} (`{acc}`)\n**Detail:** {detail}', color)


@command('kick', level=MOD, usage='/kick <player> [reason]', help='Kick')
def cmd_kick(ctx):
    if not ctx.args:
        return ctx.error('Usage: /kick <player|id> [reason]')
    t = _target(ctx, ctx.args[0])
    if not t:
        return
    cid, acc, name = t
    if cid is None:
        return ctx.error(f'{name} is not online.')
    reason = ' '.join(ctx.args[1:]) or 'No reason'
    utils.tell(cid, f'Kicked by staff: {reason}', utils.RED)
    utils.announce(f'{name} was kicked. Reason: {reason}')
    utils.kick(cid, int(config.get('security.kick_cooldown_seconds', 60)), 1.0)
    _record(ctx, 'kick', acc, name, reason)


@command('ban', level=MOD, usage='/ban <player> <10m|2h|7d|perm> [reason]',
         help='Ban account (mods max 1d)')
def cmd_ban(ctx):
    if len(ctx.args) < 2:
        return ctx.error('Usage: /ban <player|id|pb-id> <10m|2h|7d|perm> [reason]')
    t = _target(ctx, ctx.args[0], need_account=True)
    if not t:
        return
    cid, acc, name = t
    ok, seconds = utils.parse_duration(ctx.args[1])
    if not ok:
        return ctx.error('Bad duration. Examples: 30m, 2h, 7d, perm')
    if (seconds is None or seconds > 86400) and ctx.level < ADMIN:
        return ctx.error('Moderators can ban up to 1d.')
    reason = ' '.join(ctx.args[2:]) or 'No reason'
    row = storage.add_ban('account', acc, reason, ctx.account or ctx.name,
                          seconds)
    dur = utils.fmt_duration(seconds)
    utils.announce(f'{name} was banned ({dur}). Reason: {reason}', utils.RED)
    if cid is not None:
        utils.tell(cid, f'You are banned ({dur}): {reason}', utils.RED)
        utils.kick(cid, 300, delay=1.0)
    _record(ctx, 'ban', acc, name, f'#{row["id"]} {dur} | {reason}', 0xE74C3C)
    ctx.reply(f'Ban #{row["id"]} created.', utils.GREEN)


@command('unban', level=ADMIN, usage='/unban <pb-id|#banid>', help='Unban')
def cmd_unban(ctx):
    if not ctx.args:
        return ctx.error('Usage: /unban <pb-id|#banid>')
    arg = ctx.args[0].lstrip('#')
    if arg.isdigit():
        row = storage.remove_ban_id(int(arg))
        if not row:
            return ctx.error(f'No active ban #{arg}.')
        target = row['value']
    else:
        if not storage.remove_ban('account', arg):
            return ctx.error(f'{arg} is not banned.')
        target = arg
    _record(ctx, 'unban', target, target, '', 0x2ECC71)
    ctx.reply(f'Unbanned {target}.', utils.GREEN)


@command('mute', level=MOD, usage='/mute <player> [10m|perm] [reason]',
         help='Mute chat')
def cmd_mute(ctx):
    if not ctx.args:
        return ctx.error('Usage: /mute <player> [duration] [reason]')
    t = _target(ctx, ctx.args[0], need_account=True)
    if not t:
        return
    cid, acc, name = t
    seconds: float | None = 600
    rest = ctx.args[1:]
    if rest:
        ok, parsed = utils.parse_duration(rest[0])
        if ok:
            seconds, rest = parsed, rest[1:]
    reason = ' '.join(rest) or 'No reason'
    storage.add_mute(acc, reason, ctx.account or ctx.name, seconds)
    dur = utils.fmt_duration(seconds)
    if cid is not None:
        utils.tell(cid, f'You were muted ({dur}): {reason}', utils.RED)
    utils.announce(f'{name} was muted ({dur}).')
    _record(ctx, 'mute', acc, name, f'{dur} | {reason}')


@command('unmute', level=MOD, usage='/unmute <player|pb-id>', help='Unmute')
def cmd_unmute(ctx):
    if not ctx.args:
        return ctx.error('Usage: /unmute <player|pb-id>')
    cid, acc, name, err = utils.resolve_target(ctx.args[0])
    if err or not acc:
        return ctx.error(err or 'No account.')
    if not storage.remove_mute(acc):
        return ctx.error(f'{name} is not muted.')
    punish.reset(acc)
    if cid is not None:
        utils.tell(cid, 'You were unmuted.', utils.GREEN)
    _record(ctx, 'unmute', acc, name, '', 0x2ECC71)
    ctx.reply(f'Unmuted {name}.', utils.GREEN)


@command('warn', level=MOD, usage='/warn <player> <reason>', help='Warn')
def cmd_warn(ctx):
    if len(ctx.args) < 2:
        return ctx.error('Usage: /warn <player> <reason>')
    t = _target(ctx, ctx.args[0], need_account=True)
    if not t:
        return
    cid, acc, name = t
    reason = ' '.join(ctx.args[1:])
    total = storage.add_warn(acc, reason, ctx.account or ctx.name)
    limit = int(config.get('security.warn_limit', 3))
    if cid is not None:
        utils.tell(cid, f'WARNING ({total}/{limit}): {reason}', utils.RED)
    _record(ctx, 'warn', acc, name, f'{total}/{limit} | {reason}')
    if total >= limit:
        minutes = int(config.get('security.warn_ban_minutes', 30))
        storage.add_ban('account', acc, f'Warn limit: {reason}', 'WarnSystem',
                        minutes * 60)
        storage.clear_warns(acc)
        utils.announce(f'{name} reached the warn limit - banned {minutes}m.',
                       utils.RED)
        if cid is not None:
            utils.kick(cid, 300, delay=1.0)


@command('whois', level=MOD, usage='/whois <player|pb-id>', help='Player info')
def cmd_whois(ctx):
    if not ctx.args:
        return ctx.error('Usage: /whois <player|pb-id>')
    cid, acc, name, err = utils.resolve_target(ctx.args[0])
    if err:
        return ctx.error(err)
    if not acc:
        return ctx.reply(f'{name}: unverified account (client {cid}).')
    p = storage.get_player(acc) or {}
    ban = storage.find_ban('account', acc)
    mute = storage.get_mute(acc)
    ctx.reply(f'{name} | {acc} | {roles.role_name(acc)}', utils.YELLOW)
    ctx.reply(f"First: {_ts(p.get('first_seen'))}  Last: "
              f"{_ts(p.get('last_seen'))}  Joins: {p.get('joins', 0)}")
    ctx.reply('Names: ' + (', '.join(storage.names_of(acc, 6)) or '-'))
    ctx.reply(f"Warns: {storage.count_warns(acc)}  Strikes: "
              f"{punish.strikes_of(acc)}  Muted: {'yes' if mute else 'no'}  "
              f"Banned: {('#' + str(ban['id'])) if ban else 'no'}")


@command('bans', level=ADMIN, usage='/bans', help='Recent active bans')
def cmd_bans(ctx):
    rows = storage.active_bans(8)
    if not rows:
        return ctx.reply('No active bans.')
    for r in rows:
        left = (utils.fmt_duration(r['expires'] - time.time())
                if r['expires'] else 'perm')
        ctx.reply(f"#{r['id']} {r['kind']}:{r['value']} ({left}) - "
                  f"{r['reason']}")


@command('banname', level=ADMIN, usage='/banname <pattern> [reason]',
         help='Block names containing pattern')
def cmd_banname(ctx):
    if not ctx.args:
        return ctx.error('Usage: /banname <pattern> [reason]')
    key = name_key(ctx.args[0])
    if len(key) < 3:
        return ctx.error('Pattern too short (min 3 letters).')
    reason = ' '.join(ctx.args[1:]) or 'Blocked name'
    row = storage.add_ban('name', key, reason, ctx.account or ctx.name, None)
    _record(ctx, 'banname', key, key, reason)
    ctx.reply(f'Name pattern "{key}" blocked (#{row["id"]}).', utils.GREEN)


@command('unbanname', level=ADMIN, usage='/unbanname <pattern>',
         help='Remove name block')
def cmd_unbanname(ctx):
    if not ctx.args:
        return ctx.error('Usage: /unbanname <pattern>')
    key = name_key(ctx.args[0])
    if storage.remove_ban('name', key):
        _record(ctx, 'unbanname', key, key, '')
        ctx.reply(f'Removed "{key}".', utils.GREEN)
    else:
        ctx.error('Pattern not found.')


@command('lockdown', level=ADMIN, usage='/lockdown [on|off]',
         help='Only staff/known players can join')
def cmd_lockdown(ctx):
    cur = bool(config.get('security.lockdown', False))
    state = (not cur) if not ctx.args else ctx.args[0].lower() in ('on', '1',
                                                                   'true')
    config.set_value('security.lockdown', state)
    utils.announce(f"Server lockdown {'ENABLED' if state else 'disabled'}.",
                   utils.RED if state else utils.GREEN)
    _record(ctx, 'lockdown', '-', '-', 'on' if state else 'off')


@command('audit', level=ADMIN, usage='/audit', help='Recent audit log')
def cmd_audit(ctx):
    for r in storage.recent_audit(8):
        ctx.reply(f"{_ts(r['ts'])} {r['actor']} {r['action']} "
                  f"{r['target']} {r['detail'][:40]}")


@command('secstats', level=MOD, usage='/secstats', help='Security stats')
def cmd_secstats(ctx):
    s = storage.stats()
    ctx.reply(f"Bans: {s['bans']}  Mutes: {s['mutes']}  Known players: "
              f"{s['players']}  Lockdown: "
              f"{'ON' if config.get('security.lockdown') else 'off'}",
              utils.YELLOW)
