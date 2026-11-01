# Released under the MIT License. See LICENSE for details.
# ba_meta require api 9
"""Lucious Top5 - gives [TOP 1..5] clay tags to the leaderboard leaders.

Reads the leaderboard from features.LuciousStats (or falls back to
reading stats.db), writes tags through lucious.tags.store, and only ever
removes tags that this module created itself. Manual tags always win.
Commands (staff): /top5tag now | debug | on | off | clear
"""

from __future__ import annotations

import glob
import importlib
import inspect
import logging
import os
import sqlite3

import babase
import bascenev1 as bs

from features import LuciousKit as kit

_LOG = logging.getLogger('LuciousTop5')
_P = 'top5'
DEFAULTS = {
    'enabled': True,
    'size': 5,
    'interval': 90.0,
    'announce': True,
    'tag_id': 'v1',          # which id format lucious.tags.store uses
    'format': '[TOP {n}]',
}
_REC = 'top5_tags.json'


class _S:
    ticker = None
    rec: dict = {'tagged': {}, 'ids': {}}
    route = 'not run yet'


S = _S()


def _c(key):
    return kit.cfg(_P, DEFAULTS, key)


# ----------------------------------------------------------- leaderboard --
def _row_id(row):
    if isinstance(row, str):
        return row
    if isinstance(row, dict):
        for k in ('account', 'account_id', 'acc', 'id', 'key'):
            if row.get(k):
                return str(row[k])
    if isinstance(row, (list, tuple)):
        for item in row:
            if isinstance(item, str):
                return item
    for k in ('account', 'account_id', 'acc', 'id'):
        v = getattr(row, k, None)
        if v:
            return str(v)
    return None


def _from_module(n: int):
    try:
        mod = importlib.import_module('features.LuciousStats')
    except Exception:
        return None
    for fname in ('top', 'get_top', 'top_n', 'top_players', 'leaderboard',
                  'get_leaderboard'):
        fn = getattr(mod, fname, None)
        if not callable(fn):
            continue
        try:
            rows = fn(n)
        except TypeError:
            try:
                rows = fn()
            except Exception:
                continue
        except Exception:
            continue
        ids = [i for i in (_row_id(r) for r in list(rows or [])[:n]) if i]
        if ids:
            return ids, f'LuciousStats.{fname}'
    return None


def _db_paths() -> list[str]:
    out = []
    try:
        user = babase.env().get('python_directory_user') or '.'
    except Exception:
        user = '.'
    for base in (kit.data_dir(), os.path.join(user, 'stats'), user,
                 os.path.join(os.path.dirname(__file__), '..', 'data')):
        out += glob.glob(os.path.join(base, 'stats*.db'))
    return out


def _from_db(n: int):
    id_cols = ('account', 'account_id', 'acc', 'id')
    pts_cols = ('points', 'score', 'pts', 'total_points', 'total')
    for path in _db_paths():
        try:
            con = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
            tables = [r[0] for r in con.execute(
                "select name from sqlite_master where type='table'")]
            for t in tables:
                cols = [r[1] for r in con.execute(f'pragma table_info({t})')]
                idc = next((c for c in id_cols if c in cols), None)
                pc = next((c for c in pts_cols if c in cols), None)
                if idc and pc:
                    rows = con.execute(
                        f'select {idc} from {t} order by {pc} desc '
                        f'limit {int(n)}').fetchall()
                    con.close()
                    ids = [str(r[0]) for r in rows if r[0]]
                    if ids:
                        return ids, f'{os.path.basename(path)}:{t}.{pc}'
            con.close()
        except Exception:
            continue
    return None


def _top(n: int):
    return _from_module(n) or _from_db(n) or ([], 'no leaderboard found')


# --------------------------------------------------------------- id mapping --
def _learn_ids() -> None:
    try:
        session = bs.get_foreground_host_session()
        players = list(session.sessionplayers) if session else []
    except Exception:
        return
    changed = False
    for sp in players:
        v1 = v2 = None
        try:
            v1 = sp.get_v1_account_id()
        except Exception:
            pass
        try:
            v2 = sp.get_v2_account_id()
        except Exception:
            pass
        if v1 and v2:
            entry = {'v1': str(v1), 'v2': str(v2)}
            for key in (str(v1), str(v2)):
                if S.rec['ids'].get(key) != entry:
                    S.rec['ids'][key] = entry
                    changed = True
    if changed:
        kit.save_json(_REC, S.rec)


def _to_tag_id(any_id: str):
    want = str(_c('tag_id')).lower()
    m = S.rec['ids'].get(any_id)
    if m and m.get(want):
        return m[want]
    if want == 'v1' and any_id.startswith('pb-'):
        return any_id
    if want == 'v2' and any_id.startswith('a-'):
        return any_id
    return None


# ------------------------------------------------------------------ tags --
def _store():
    from lucious.tags import store
    return store


def _has_tag(acc: str) -> bool:
    try:
        return bool(_store().get(acc))
    except Exception:
        return False


def _set_tag(acc: str, text: str) -> None:
    fn = _store().set_tag
    try:
        count = len(inspect.signature(fn).parameters)
    except Exception:
        count = 4
    args = (acc, text, 'top5', 'top5')[:max(2, min(count, 4))]
    fn(*args)


def _remove_tag(acc: str) -> None:
    _store().remove(acc)


def _refresh(announce: bool = True) -> str:
    if not _c('enabled'):
        return 'disabled'
    n = int(_c('size'))
    ids, S.route = _top(n)
    _learn_ids()
    want: dict = {}
    for rank, any_id in enumerate(ids, 1):
        tag_id = _to_tag_id(any_id)
        if tag_id:
            want[tag_id] = rank
    tagged = S.rec['tagged']
    changed = 0
    for acc, rank in want.items():
        text = str(_c('format')).format(n=rank)
        try:
            if acc in tagged:
                if tagged[acc] != rank:
                    _set_tag(acc, text)
                    tagged[acc] = rank
                    changed += 1
            elif not _has_tag(acc):
                _set_tag(acc, text)
                tagged[acc] = rank
                changed += 1
        except Exception:
            _LOG.exception('Top5: could not tag %s', acc)
    for acc in list(tagged):
        if acc not in want:
            try:
                _remove_tag(acc)
            except Exception:
                _LOG.exception('Top5: could not untag %s', acc)
            del tagged[acc]
            changed += 1
    if changed:
        kit.save_json(_REC, S.rec)
        if announce and _c('announce'):
            kit.say('\ue043 Leaderboard TOP 5 tags updated!',
                    (1.0, 0.85, 0.2), chat=False)
    return f'{len(ids)} leaders via {S.route}; {len(want)} mapped; ' \
           f'{changed} change(s)'


def _safe_refresh(*_a, **_k) -> None:
    try:
        _refresh()
    except Exception:
        _LOG.exception('Top5: refresh failed')


def _on_begin(*_a, **_k) -> None:
    bs.apptimer(3.0, _safe_refresh)


def _cmd(ctx) -> None:
    if not kit.staff(ctx):
        kit.reply(ctx, 'Staff only.')
        return
    args = [str(a).lower() for a in (getattr(ctx, 'args', None) or [])]
    sub = args[0] if args else 'now'
    if sub in ('on', 'off'):
        kit.set_cfg(_P, 'enabled', sub == 'on')
        kit.reply(ctx, f'Top5 tags {sub}.')
    elif sub == 'clear':
        for acc in list(S.rec['tagged']):
            try:
                _remove_tag(acc)
            except Exception:
                pass
        S.rec['tagged'] = {}
        kit.save_json(_REC, S.rec)
        kit.reply(ctx, 'Removed every tag this module created.')
    elif sub == 'debug':
        ids, route = _top(int(_c('size')))
        mapped = [(i, _to_tag_id(i)) for i in ids]
        kit.reply(ctx, f'route: {route}')
        kit.reply(ctx, f'leader ids: {ids}')
        kit.reply(ctx, f'-> tag ids: {mapped}')
        kit.reply(ctx, f'ours: {S.rec["tagged"]}')
    else:
        try:
            kit.reply(ctx, 'Top5: ' + _refresh())
        except Exception as exc:
            kit.reply(ctx, f'Top5 failed: {exc}')


def setup() -> None:
    saved = kit.load_json(_REC, {})
    S.rec = {'tagged': dict(saved.get('tagged', {})),
             'ids': dict(saved.get('ids', {}))}
    S.ticker = bs.AppTimer(float(_c('interval')), _safe_refresh, repeat=True)
    kit.on('activity_begin', _on_begin, priority=80)
    kit.add_command('top5tag', _cmd, level=80)


def teardown() -> None:
    S.ticker = None
    kit.off('activity_begin', _on_begin)
