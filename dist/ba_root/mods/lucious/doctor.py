# mods/lucious/doctor.py
"""/doctor - shows why a module is not running; /doctor enable loads strays."""
from __future__ import annotations

import os

from lucious import config, utils
from lucious.commands import command

FEATURES_DIR = os.path.join(os.path.dirname(config.BASE_DIR), 'features')


def _feature_files() -> dict[str, str]:
    out = {}
    try:
        files = sorted(os.listdir(FEATURES_DIR))
    except OSError:
        return out
    for f in files:
        if f.endswith('.py') and f.startswith('Lucious'):
            out['features.' + f[:-3]] = f
    return out


@command('doctor', level=100, usage='/doctor [enable]',
         help='Module health report')
def _doctor(ctx):
    from lucious import core
    mods = dict(config.get('modules') or {})
    lines: list[tuple[str, tuple]] = []
    if not os.path.isdir(FEATURES_DIR):
        lines.append((f'features folder missing: {FEATURES_DIR}', utils.RED))
    for name, on in mods.items():
        st = core.STATE.get(name)
        if not on:
            lines.append((f'{name}: OFF in config', utils.YELLOW))
        elif st and st['ok']:
            lines.append((f'{name}: OK', utils.GREEN))
        elif st:
            lines.append((f"{name}: ERROR {str(st['error'])[:90]}",
                          utils.RED))
        else:
            lines.append((f'{name}: enabled but never loaded '
                          '(restart the server)', utils.RED))
        if name.startswith('features.'):
            stem = name.split('.', 1)[1]
            if not stem.isidentifier():
                lines.append((f'  bad file name "{stem}" (letters, digits '
                              'and _ only)', utils.RED))
            elif not os.path.isfile(os.path.join(FEATURES_DIR, stem + '.py')):
                lines.append((f'  FILE MISSING: features/{stem}.py',
                              utils.RED))
    unlisted = {m: f for m, f in _feature_files().items() if m not in mods}
    for m, f in unlisted.items():
        lines.append((f'{f}: present but not in "modules"', utils.YELLOW))
    if ctx.args and ctx.args[0].lower() == 'enable' and unlisted:
        for m in unlisted:
            mods[m] = True
            ok = core.load(m)
            lines.append((f"enabled {m}: {'OK' if ok else 'ERROR'}",
                          utils.GREEN if ok else utils.RED))
        config.set_value('modules', mods)
    for text, color in lines:
        print('[doctor]', text, flush=True)
        ctx.reply(text, color)
    if not lines:
        ctx.reply('Nothing configured.', utils.YELLOW)
