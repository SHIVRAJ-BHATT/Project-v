# ba_meta require api 9
# LuciousStats - kills/deaths/points store, rank titles, /rank, /top, leaderboard HUD.
from __future__ import annotations

import logging
import os
import sqlite3
import time

import babase
import bascenev1 as bs

from lucious import config, utils
from lucious.commands import command
from lucious.events import bus

log = logging.getLogger('lucious')

PTS_PER_KILL = 10
TIERS = [  # (points needed, title, neon colour)
    (0, 'Newbie', (0.8, 0.8, 0.8)),
    (100, 'Rookie', (0.2, 1.0, 0.2)),
    (300, 'Fighter', (0.0, 1.0, 0.5)),
    (700, 'Warrior', (0.0, 1.0, 1.0)),
    (1500, 'Veteran', (0.0, 0.5, 1.0)),
    (3000, 'Elite', (0.7, 0.3, 1.0)),
    (6000, 'Master', (1.0, 0.0, 1.0)),
    (12000, 'Grandmaster', (1.0, 0.5, 0.0)),
    (25000, 'Legend', (1.0, 0.1, 0.1)),
]
TOP_COLORS = [(1.0, 0.85, 0.0), (0.85, 0.9, 1.0), (1.0, 0.55, 0.2)]

LB = {
    'rows': 5, 'title': '\ue04c TOP 5 PLAYERS \ue04d', 'top': -96, 'right': 10,
    'width': 300, 'row_h': 22, 'name_chars': 12,
    'panel': (0.05, 0.05, 0.07), 'panel_opacity': 0.78,
    'header': (0.28, 0.19, 0.04), 'accent': (1.0, 0.76, 0.18),
    'title_colors': [(1.0, 0.72, 0.12), (1.0, 0.94, 0.52), (1.0, 0.56, 0.18)],
    'col': (0.72, 0.74, 0.80),
    'ranks': [(1.0, 0.8, 0.15), (0.8, 0.88, 1.0), (1.0, 0.55, 0.3),
              (0.45, 0.95, 0.85), (0.8, 0.62, 1.0)],
    'k': (0.45, 1.0, 0.45), 'd': (1.0, 0.42, 0.42), 'kd': (1.0, 1.0, 1.0),
}

_players: dict = {}
_pos: dict = {}
_order: list = []
_seen: dict = {}
_dirty: set = set()
_db = None
_timer = None


# ------------------------------------------------------------------ storage
def _db_path() -> str:
    try:
        from lucious.config import DATA_DIR
        base = DATA_DIR
    except Exception:
        import lucious
        base = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(lucious.__file__))), 'data')
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, 'stats.db')


def _open():
    global _db
    _db = sqlite3.connect(_db_path(), check_same_thread=False)
    _db.execute('PRAGMA journal_mode=WAL')
    _db.execute('CREATE TABLE IF NOT EXISTS players(account TEXT PRIMARY KEY,'
                'name TEXT, score INT, kills INT, deaths INT, pts INT, seen INT)')
    _db.commit()
    _players.clear()
    for a, n, s, k, d, p, _t in _db.execute('SELECT * FROM players'):
        _players[a] = {'name': n, 'score': s, 'kills': k, 'deaths': d, 'pts': p}
    _reorder()


def _reorder():
    _order[:] = sorted(_players, key=lambda a: (
        -_players[a]['pts'], -_players[a]['kills'], _players[a]['deaths']))
    _pos.clear()
    _pos.update({a: i + 1 for i, a in enumerate(_order)})


def _flush():
    if _db is None or not _dirty:
        return
    now = int(time.time())
    rows = []
    for a in list(_dirty):
        p = _players.get(a)
        if p:
            rows.append((a, p['name'], p['score'], p['kills'], p['deaths'],
                         p['pts'], now))
    _dirty.clear()
    try:
        _db.executemany('INSERT OR REPLACE INTO players VALUES(?,?,?,?,?,?,?)',
                        rows)
        _db.commit()
    except Exception:
        log.exception('[Lucious] stats flush failed')


# --------------------------------------------------------------- collection
def _account(sp):
    try:
        acct = utils.account_of(sp.inputdevice.client_id)
        if acct:
            return acct
    except Exception:
        pass
    try:
        return sp.get_v1_account_id()
    except Exception:
        return None


def _collect() -> bool:
    act = bs.get_foreground_host_activity()
    if act is None:
        return False
    try:
        records = list(act.stats.get_records().values())
    except Exception:
        return False
    changed = False
    for rec in records:
        try:
            acct = _account(rec.get_last_sessionplayer())
            if not acct:
                continue
            k = int(rec.accum_kill_count)
            d = int(rec.accum_killed_count)
            s = int(rec.accumscore)
            name = str(rec.name)[:32]
        except Exception:
            continue
        last = _seen.get(acct, (0, 0, 0))
        dk, dd, ds = k - last[0], d - last[1], s - last[2]
        if dk < 0 or dd < 0 or ds < 0:      # a new session started
            dk, dd, ds = k, d, s
        _seen[acct] = (k, d, s)
        p = _players.get(acct)
        if p is None:
            p = _players[acct] = {'name': name, 'score': 0, 'kills': 0,
                                  'deaths': 0, 'pts': 0}
            changed = True
            _dirty.add(acct)
        if dk or dd or ds or p['name'] != name:
            p['name'] = name
            p['kills'] += dk
            p['deaths'] += dd
            p['score'] += ds
            p['pts'] += ds + dk * PTS_PER_KILL
            _dirty.add(acct)
            changed = True
    return changed


def _tick():
    try:
        if _collect():
            _reorder()
        _flush()
    except Exception:
        log.exception('[Lucious] stats tick failed')


# ---------------------------------------------------------------- public API
def title_for(account):
    """Return (text, colour, is_top3) for the overhead rank label."""
    p = _players.get(account) if account else None
    pts = p['pts'] if p else 0
    pos = _pos.get(account, 0) if account else 0
    if p and 1 <= pos <= 3 and pts > 0:
        return f'\ue043 TOP {pos} \ue043', TOP_COLORS[pos - 1], pos == 1
    idx = max(i for i, t in enumerate(TIERS) if pts >= t[0])
    return f'{TIERS[idx][1]}[{idx}]', TIERS[idx][2], False


def _kd(p) -> str:
    return f"{(p['kills'] / p['deaths'] if p['deaths'] else float(p['kills'])):.2f}"


def _compact(v: int) -> str:
    if v >= 1_000_000:
        return f'{v / 1_000_000:.1f}M'
    if v >= 10_000:
        return f'{v / 1000:.1f}k'
    return str(v)


def top_rows(n: int):
    out = []
    for a in _order[:n]:
        p = _players[a]
        name = ' '.join(p['name'].split()) or 'Unknown'
        lim = LB['name_chars']
        if len(name) > lim:
            name = name[:lim - 1] + '.'
        out.append({'name': name, 'k': _compact(p['kills']),
                    'd': _compact(p['deaths']), 'kd': _kd(p),
                    'pts': _compact(p['pts'])})
    return out


# -------------------------------------------------------------- leaderboard
def _keys(colors, step):
    seq = list(colors) + [colors[0]]
    return {i * step: tuple(c) for i, c in enumerate(seq)}


def _txt(text, pos, scale=0.6, color=(1, 1, 1), h_align='center',
         h_attach='right', v_attach='top', opacity=1.0, maxwidth=None):
    attrs = {'text': str(text), 'position': pos, 'scale': scale,
             'color': color, 'h_align': h_align, 'v_align': 'center',
             'h_attach': h_attach, 'v_attach': v_attach, 'opacity': opacity,
             'shadow': 0.6, 'flatness': 1.0}
    if maxwidth:
        attrs['maxwidth'] = maxwidth
    return bs.newnode('text', attrs=attrs)


class Board:
    def __init__(self):
        c = LB
        self._tex = bs.gettexture('white')
        w, rh, n = c['width'], c['row_h'], c['rows']
        right = -c['right']
        left = right - w
        cx = (left + right) / 2
        top, head = c['top'], 26
        cols_y = top - head - 12
        first_y = cols_y - 22
        height = top - (first_y - (n - 1) * rh - 14)

        panel = self._img((cx, top - height / 2), (w, height), c['panel'], 0.0)
        bs.animate(panel, 'opacity', {0.0: 0.0, 0.4: c['panel_opacity']})
        self._img((cx, top - head / 2), (w, head), c['header'], 0.95)
        self._img((cx, top - head), (w, 2), c['accent'], 0.9)
        title = _txt(c['title'], (cx, top - head / 2), 0.72, c['accent'])
        bs.animate_array(title, 'color', 3, _keys(c['title_colors'], 1.2),
                         loop=True)

        col = {'rank': left + 14, 'name': left + 28, 'k': left + 158,
               'd': left + 196, 'kd': left + 236, 'pts': left + 280}
        for key, label in (('rank', '#'), ('name', 'PLAYER'), ('k', 'K'),
                           ('d', 'D'), ('kd', 'K/D'), ('pts', 'PTS')):
            _txt(label, (col[key], cols_y), 0.48, c['col'],
                 'left' if key == 'name' else 'center')

        self.rows = []
        for i in range(n):
            y = first_y - i * rh
            rc = c['ranks'][i % len(c['ranks'])]

            def cell(key, color, scale=0.58, align='center', mw=None, y=y):
                return _txt('', (col[key], y), scale, color, align,
                            opacity=0.0, maxwidth=mw)
            self.rows.append({
                'rank': cell('rank', rc, 0.66),
                'name': cell('name', rc, align='left', mw=118),
                'k': cell('k', c['k']), 'd': cell('d', c['d']),
                'kd': cell('kd', c['kd']), 'pts': cell('pts', rc),
                'sig': None})
        self.refresh()
        try:
            sec = float(config.get('stats.refresh', 10))
        except Exception:
            sec = 10.0
        self._timer = bs.Timer(max(2.0, min(sec, 600.0)),
                               bs.WeakCall(self.refresh), repeat=True)

    def _img(self, pos, size, color, opacity):
        return bs.newnode('image', attrs={
            'texture': self._tex, 'color': color, 'opacity': opacity,
            'attach': 'topRight', 'absolute_scale': True,
            'scale': size, 'position': pos})

    def refresh(self):
        data = top_rows(len(self.rows))
        for i, row in enumerate(self.rows):
            v = dict(data[i]) if i < len(data) else {
                'name': '-', 'k': '', 'd': '', 'kd': '', 'pts': ''}
            v['rank'] = str(i + 1)
            sig = tuple(v[k] for k in ('rank', 'name', 'k', 'd', 'kd', 'pts'))
            if sig == row['sig']:
                continue
            row['sig'] = sig
            for key in ('rank', 'name', 'k', 'd', 'kd', 'pts'):
                node = row[key]
                try:
                    if node.exists():
                        node.text = v[key]
                        bs.animate(node, 'opacity', {0.0: 0.0, 0.3: 1.0})
                except Exception:
                    pass


def _on_begin(*_a, **_k):
    act = bs.get_foreground_host_activity()
    if act is None or not isinstance(act, bs.GameActivity):
        return
    try:
        if not config.get('stats.board', True):
            return
    except Exception:
        pass
    if getattr(act, '_lc_board', None) is not None:
        return
    try:
        with act.context:
            act._lc_board = Board()
    except Exception:
        log.exception('[Lucious] leaderboard build failed')


# ----------------------------------------------------------------- commands
@command('rank', level=0, usage='/rank [player]',
         help='Show your rank title, position and stats.')
def _rank(ctx):
    acct, name = ctx.account, ctx.name
    if ctx.args:
        _cid, acct, name, err = utils.resolve_target(ctx.args[0])
        if err:
            ctx.error(err)
            return
    p = _players.get(acct) if acct else None
    if not p:
        ctx.reply(f'{name}: no stats yet (play a round first).')
        return
    text, color, _top = title_for(acct)
    ctx.reply(f"{name}: {text}  #{_pos.get(acct, 0)}  {p['pts']} pts  "
              f"K {p['kills']} / D {p['deaths']} ({_kd(p)})", color)


@command('top', level=0, usage='/top', help='Show the top 5 players.')
def _top(ctx):
    rows = top_rows(5)
    if not rows:
        ctx.reply('No stats yet.')
        return
    for i, r in enumerate(rows, 1):
        ctx.reply(f"#{i} {r['name']}  {r['pts']} pts  K {r['k']} D {r['d']}",
                  LB['ranks'][i - 1])


@command('board', level=80, usage='/board on|off',
         help='Leaderboard panel on/off (next game).')
def _board(ctx):
    if ctx.args and ctx.args[0].lower() in ('on', 'off'):
        config.set_value('stats.board', ctx.args[0].lower() == 'on')
        ctx.reply(f'Leaderboard {ctx.args[0].lower()} (next game).')
    else:
        ctx.error('Usage: /board on|off')


def setup():
    global _timer
    _open()
    _timer = babase.AppTimer(5.0, _tick, repeat=True)
    bus.subscribe('activity_begin', _on_begin, priority=60)


def teardown():
    global _timer, _db
    _timer = None
    try:
        _flush()
        if _db is not None:
            _db.close()
    except Exception:
        pass
    _db = None
