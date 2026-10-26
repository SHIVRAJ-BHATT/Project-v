"""Boot, module lifecycle and hot reload."""
from __future__ import annotations

import importlib
import logging
import sys
import time

from lucious import __version__, commands, config, hooks
from lucious.events import bus

log = logging.getLogger('lucious')
CORE_MODULES = ('lucious.builtin',)
STATE: dict[str, dict] = {}


def boot() -> None:
    t0 = time.perf_counter()
    config.load()
    hooks.install()
    bus.subscribe('chat', commands.chat_filter, priority=20)
    names = list(CORE_MODULES) + [
        n for n, on in (config.get('modules') or {}).items() if on]
    for name in names:
        load(name)
    ok = sum(1 for s in STATE.values() if s['ok'])
    print(f'[Lucious] v{__version__} ready - {ok}/{len(STATE)} modules in '
          f'{(time.perf_counter() - t0) * 1000:.0f} ms', flush=True)
    for name, st in STATE.items():
        extra = '' if st['ok'] else f" -> {st['error']}"
        print(f"   {'OK ' if st['ok'] else 'ERR'} {name}{extra}", flush=True)


def load(name: str) -> bool:
    t = time.perf_counter()
    try:
        mod = importlib.import_module(name)
        setup = getattr(mod, 'setup', None)
        if callable(setup):
            setup()
        STATE[name] = {'ok': True, 'error': '',
                       'ms': (time.perf_counter() - t) * 1000}
        return True
    except Exception as exc:
        log.exception('[Lucious] module %s failed to load', name)
        STATE[name] = {'ok': False, 'error': f'{type(exc).__name__}: {exc}',
                       'ms': (time.perf_counter() - t) * 1000}
        return False


def unload(name: str) -> None:
    mod = sys.modules.get(name)
    if mod is not None and callable(getattr(mod, 'teardown', None)):
        try:
            mod.teardown()
        except Exception:
            log.exception('[Lucious] teardown of %s failed', name)
    bus.remove_owner(name)
    commands.remove_owner(name)
    STATE.pop(name, None)


def reload(name: str) -> bool:
    unload(name)
    try:
        mod = sys.modules.get(name)
        if mod is not None:
            for sub in getattr(mod, '__reload_order__', ()):
                if sub in sys.modules:
                    importlib.reload(sys.modules[sub])
            importlib.reload(mod)
    except Exception as exc:
        log.exception('[Lucious] reload of %s failed', name)
        STATE[name] = {'ok': False, 'error': str(exc), 'ms': 0.0}
        return False
    return load(name)


def shutdown() -> None:
    for name in reversed(list(STATE)):
        unload(name)
