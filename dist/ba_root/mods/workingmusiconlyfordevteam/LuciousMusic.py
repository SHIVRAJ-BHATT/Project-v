# ba_meta require api 9
# LuciousMusic v2 - plays tracks from your asset-package wrapper through a
# scene sound node (replicated to players), silences the stock track.
from __future__ import annotations

import importlib
import importlib.util
import logging
import os
import random
import re
import sys

import babase
import bascenev1 as bs

from lucious import config
from lucious.commands import command
from lucious.events import bus

log = logging.getLogger('lucious')

PACKAGE_HINT = 'musicluvcous'      # from a-a19262415.musicluvcous.dev261031
SKIP_DIRS = {'lucious', '__pycache__', 'data', 'stats', 'playersdata'}
STAFF = 80

_state = {'path': None, 'tracks': {}, 'order': [], 'error': None,
          'variant': None, 'last': None, 'idx': -1}


# ------------------------------------------------------------ wrapper lookup
def _roots() -> list:
    roots: list = []

    def add(p):
        if p and os.path.isdir(p):
            p = os.path.abspath(p)
            if p not in roots:
                roots.append(p)
    try:
        import lucious
        add(os.path.dirname(os.path.dirname(os.path.abspath(lucious.__file__))))
    except Exception:
        pass
    try:
        add(babase.env().get('python_directory_user'))
    except Exception:
        pass
    return roots


def _find_wrapper():
    hint = str(config.get('music.package_hint', PACKAGE_HINT)).lower()
    for root in _roots():
        for dirpath, dirnames, files in os.walk(root):
            depth = dirpath[len(root):].count(os.sep)
            dirnames[:] = ([d for d in dirnames
                            if d not in SKIP_DIRS and not d.startswith('.')]
                           if depth < 2 else [])
            for fn in sorted(files):
                if not fn.endswith('.py'):
                    continue
                p = os.path.join(dirpath, fn)
                try:
                    with open(p, 'r', encoding='utf-8', errors='ignore') as f:
                        head = f.read(3000)
                except OSError:
                    continue
                if 'bascenev1._assetref' in head and hint in head.lower():
                    return p
    return None


def _load_wrapper():
    cfgv = config.get('music.wrapper', None)      # optional manual override
    if cfgv:
        cfgv = str(cfgv)
        if not cfgv.endswith('.py') and os.sep not in cfgv:
            return importlib.import_module(cfgv), cfgv
        path = cfgv
    else:
        path = _find_wrapper()
    if not path:
        raise FileNotFoundError(
            'bascenev1 wrapper file not found. Put it in mods/ (or set '
            'music.wrapper in config.json to its path or module name).')
    name = '_lucious_music_wrapper'
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod, path


def _nat(s: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', s)]


def _walk(tree, group, prefix):
    for key, val in tree.items():
        if isinstance(val, dict):
            yield from _walk(val, getattr(group, key), prefix + key + '/')
        elif val == 's':
            yield prefix + key, getattr(group, key)


def _scan() -> bool:
    st = _state
    st.update(tracks={}, order=[], error=None, path=None)
    try:
        mod, path = _load_wrapper()
        tree = getattr(mod, '_TREE', None)
        if not isinstance(tree, dict):
            raise RuntimeError('wrapper has no _TREE')
        found = []
        for top, sub in tree.items():
            if isinstance(sub, dict):
                found += list(_walk(sub, getattr(mod, top), top + '/'))
            elif sub == 's':
                found.append((top, getattr(mod, top)))
        short = [f[0].split('/')[-1] for f in found]
        for (full, handle), s in zip(found, short):
            label = s if short.count(s) == 1 else full
            st['tracks'][label] = handle
        st['order'] = sorted(st['tracks'], key=_nat)
        st['path'] = path
        if not st['order']:
            raise RuntimeError('wrapper loaded but contains no sounds')
        log.info('[Lucious] music: %d track(s): %s', len(st['order']),
                 ', '.join(st['order']))
        return True
    except Exception as e:
        st['error'] = f'{type(e).__name__}: {e}'
        log.exception('[Lucious] music wrapper load failed')
        return False


# ----------------------------------------------------------------- helpers
def _on() -> bool:
    try:
        return bool(config.get('music.enabled', True))
    except Exception:
        return True


def _vol() -> float:
    try:
        return max(0.1, min(3.0, float(config.get('music.volume', 1.0))))
    except Exception:
        return 1.0


def _mode() -> str:
    m = str(config.get('music.mode', 'shuffle')).lower()
    return m if m in ('shuffle', 'order', 'fixed') else 'shuffle'


def _pick():
    order = _state['order']
    if not order:
        return None
    mode = _mode()
    if mode == 'fixed':
        t = config.get('music.track', None)
        if t in order:
            return t
    if mode == 'order':
        return _next_in_order()
    pool = [t for t in order if t != _state['last']] or order
    return random.choice(pool)


def _next_in_order():
    order = _state['order']
    if not order:
        return None
    _state['idx'] = (_state['idx'] + 1) % len(order)
    return order[_state['idx']]


def _resolve(arg: str):
    order = _state['order']
    if arg.isdigit() and 1 <= int(arg) <= len(order):
        return order[int(arg) - 1]
    a = arg.lower()
    for t in order:
        if t.lower() == a:
            return t
    hits = [t for t in order if t.lower().startswith(a)]
    return hits[0] if len(hits) == 1 else None


def _kill(act):
    for attr in ('_lc_music_node', '_lc_music_timer'):
        obj = getattr(act, attr, None)
        setattr(act, attr, None)
        try:
            if obj is not None and hasattr(obj, 'delete'):
                obj.delete()
        except Exception:
            pass


def _silence_stock():
    try:
        bs.setmusic(None)
    except Exception:
        pass


def _start(act, label: str) -> bool:
    handle = _state['tracks'].get(label)
    if handle is None:
        return False
    vol = _vol() * 5.0            # same scaling the engine uses for music
    try:
        with act.context:
            _kill(act)
            snd = handle.get()
            node, used, last_err = None, None, None
            variants = (
                {'sound': snd, 'volume': vol, 'positional': False,
                 'music': True, 'loop': True},
                {'sound': snd, 'volume': vol, 'positional': False,
                 'music': True},
                {'sound': snd, 'volume': vol, 'positional': False},
            )
            for i, attrs in enumerate(variants):
                try:
                    node = bs.newnode('sound', attrs=attrs)
                    used = i
                    break
                except Exception as e:
                    last_err = e
            if node is None:
                raise last_err
            act._lc_music_node = node
            act._lc_music_label = label
            secs = float(config.get('music.loop_seconds', 0) or 0)
            if used != 0 and secs > 0:      # no native loop: restart manually
                def again(a=act, l=label):
                    try:
                        _start(a, l)
                    except Exception:
                        pass
                act._lc_music_timer = bs.Timer(secs, again)
            _silence_stock()
            if bool(config.get('music.announce', True)):
                bs.broadcastmessage(f'\ue01f Now playing: {label}',
                                    color=(0.5, 1.0, 1.0), transient=True)
        _state['variant'] = used
        _state['last'] = label
        _state['error'] = None
        return True
    except Exception as e:
        _state['error'] = f'{type(e).__name__}: {e}'
        log.exception('[Lucious] music start failed for %s', label)
        return False


# ------------------------------------------------------------------ events
def _on_begin(*_a, **_k):
    if not _on() or not _state['order']:
        return
    act = bs.get_foreground_host_activity()
    if act is None or getattr(act, '_lc_music_node', None) is not None:
        return
    label = _pick()
    if label is None:
        return
    with act.context:
        bs.timer(0.3, lambda: _start(act, label))
        bs.timer(2.5, _silence_stock)     # in case a game sets music late


# ---------------------------------------------------------------- commands
@command('music', level=0,
         usage='/music [list|play <n|name>|next|stop|on|off|volume <0.1-3>|'
               'mode <shuffle|order|fixed>|reload|status]',
         help='Server music. Staff can control it.')
def _music(ctx):
    a = [x.lower() for x in ctx.args]
    sub = a[0] if a else ''
    staff = ctx.level >= STAFF
    order = _state['order']

    if sub in ('', 'now'):
        ctx.reply(f"Now playing: {_state['last'] or 'nothing'}  "
                  f"({len(order)} tracks, {'on' if _on() else 'off'})")
        return
    if sub == 'list':
        if not order:
            ctx.error('No tracks loaded. Try /music status.')
            return
        for i, t in enumerate(order, 1):
            ctx.reply(f"{i}. {t}{'  <- playing' if t == _state['last'] else ''}")
        return
    if not staff:
        ctx.error('Only staff can control the music.')
        return

    if sub == 'status':
        st = _state
        v = {0: 'native loop', 1: 'NO loop attr (set music.loop_seconds)',
             2: 'basic node only'}.get(st['variant'], 'not started yet')
        ctx.reply(f"wrapper: {os.path.basename(st['path'] or '') or 'NOT FOUND'}")
        ctx.reply(f"tracks: {', '.join(order) or 'none'}")
        ctx.reply(f"enabled={_on()} volume={_vol()} mode={_mode()} node={v}")
        if st['error']:
            ctx.error(f"last error: {st['error']}")
        return
    if sub == 'reload':
        ok = _scan()
        if ok:
            ctx.reply(f"Loaded {len(order)} track(s): {', '.join(_state['order'])}")
        else:
            ctx.error(f"Failed: {_state['error']}")
        return
    if sub == 'on':
        config.set_value('music.enabled', True)
        ctx.reply('Music on (starts next game, or /music next).')
        return
    if sub == 'off':
        config.set_value('music.enabled', False)
        act = bs.get_foreground_host_activity()
        if act is not None:
            with act.context:
                _kill(act)
        ctx.reply('Music off.')
        return
    if sub == 'volume':
        try:
            v = max(0.1, min(3.0, float(a[1])))
        except Exception:
            ctx.error('Usage: /music volume 0.1-3')
            return
        config.set_value('music.volume', v)
        ctx.reply(f'Volume {v} (applies to the next track).')
        return
    if sub == 'mode':
        if len(a) > 1 and a[1] in ('shuffle', 'order', 'fixed'):
            config.set_value('music.mode', a[1])
            ctx.reply(f'Mode {a[1]}.')
        else:
            ctx.error('Usage: /music mode shuffle|order|fixed')
        return

    act = bs.get_foreground_host_activity()
    if sub == 'stop':
        if act is not None:
            with act.context:
                _kill(act)
        ctx.reply('Stopped (stock music stays silent until next game).')
        return
    if sub in ('play', 'next'):
        if act is None:
            ctx.error('No active game.')
            return
        if not order:
            ctx.error(f"No tracks loaded: {_state['error'] or 'see /music status'}")
            return
        if sub == 'next':
            label = _next_in_order()
        else:
            if len(a) < 2:
                ctx.error('Usage: /music play <number|name>')
                return
            label = _resolve(a[1])
            if label is None:
                ctx.error('No such track. See /music list.')
                return
            if _mode() == 'fixed':
                config.set_value('music.track', label)
        if _start(act, label):
            ctx.reply(f'Playing {label}.')
        else:
            ctx.error(f"Could not play: {_state['error']}")
        return
    ctx.error('Unknown option. Try /music list')


def setup():
    _scan()
    bus.subscribe('activity_begin', _on_begin, priority=80)


def teardown():
    act = bs.get_foreground_host_activity()
    if act is not None:
        try:
            with act.context:
                _kill(act)
        except Exception:
            pass
