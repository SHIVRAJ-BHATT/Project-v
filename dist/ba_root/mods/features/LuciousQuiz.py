# Released under the MIT License. See LICENSE for details.
# ba_meta require api 9
"""Lucious Quiz Bot - easy daily-life questions + server questions.

A question is asked every `interval` seconds. Answer with /a <answer>
(always works) or just type it in chat (best effort). First correct wins.
Commands: /quiz [top|me]  /a <answer>  and staff: /quiz now|skip|on|off|
          add <question> | <answer>[, alias...]
Config (config.json -> "quiz"): server_questions = [[question, [answers]]]
"""

from __future__ import annotations

import functools
import logging
import random
import re

import bascenev1 as bs

from features import LuciousKit as kit

_LOG = logging.getLogger('LuciousQuiz')
_P = 'quiz'

DEFAULTS = {
    'enabled': True,
    'interval': 240.0,
    'answer_time': 30.0,
    'min_players': 1,
    'points': 10,
    'chat_answers': True,
    # Edit these in config.json so they match your server.
    'server_questions': [
        ['Who is the owner of this server?', ['lucious']],
        ['Who created this server?', ['lucious']],
        ['Name the second owner of this server.', ['robin']],
        ['What is the name of this server?',
         ['lucious', 'lucious server', 'lucious community server']],
    ],
    'extra': [],
}

BANK = [
    ('How many days are in a week?', ['7', 'seven']),
    ('How many months are in a year?', ['12', 'twelve']),
    ('What color is the sky on a clear day?', ['blue']),
    ('What color is a ripe banana?', ['yellow']),
    ('What do bees make?', ['honey']),
    ('How many legs does a spider have?', ['8', 'eight']),
    ('What is 5 + 7?', ['12', 'twelve']),
    ('What is 9 x 3?', ['27']),
    ('What is 100 - 45?', ['55']),
    ('What is 8 x 8?', ['64']),
    ('What is half of 50?', ['25']),
    ('Which animal says meow?', ['cat']),
    ('Which animal says woof?', ['dog']),
    ('Which animal gives us milk?', ['cow']),
    ('Which fruit keeps the doctor away?', ['apple']),
    ('What is frozen water called?', ['ice']),
    ('What do you use to brush your teeth?', ['toothbrush', 'brush']),
    ('Which planet do we live on?', ['earth']),
    ('Which star gives us light in the day?', ['sun']),
    ('Which month comes after March?', ['april']),
    ('Which day comes after Friday?', ['saturday']),
    ('What is the opposite of hot?', ['cold']),
    ('What is the opposite of up?', ['down']),
    ('How many hours are in one day?', ['24', 'twenty four']),
    ('How many minutes are in one hour?', ['60', 'sixty']),
    ('How many seconds are in one minute?', ['60', 'sixty']),
    ('What is the capital of India?', ['delhi', 'new delhi']),
    ('What is the national animal of India?', ['tiger', 'bengal tiger']),
    ('What is the national bird of India?', ['peacock']),
    ('Which festival is called the festival of lights?', ['diwali']),
    ('Who is called the Father of the Nation in India?',
     ['gandhi', 'mahatma gandhi']),
    ('What is the currency of India?', ['rupee', 'rupees', 'inr']),
    ('How many colors are in a rainbow?', ['7', 'seven']),
    ('What do you wear on your feet?', ['shoes', 'shoe', 'socks', 'sandals']),
    ('Which meal do we eat in the morning?', ['breakfast']),
    ('What do we call a baby dog?', ['puppy']),
    ('What do we call a baby cat?', ['kitten']),
    ('Which animal is called the king of the jungle?', ['lion']),
    ('Which is the largest animal on land?', ['elephant']),
    ('Which is the tallest animal?', ['giraffe']),
    ('What do plants need from the sun to make food?',
     ['sunlight', 'light', 'sun']),
    ('Which gas do humans breathe in to live?', ['oxygen']),
    ('Which liquid do we drink every day?', ['water']),
    ('In which direction does the sun rise?', ['east']),
    ('In which direction does the sun set?', ['west']),
    ('How many sides does a triangle have?', ['3', 'three']),
    ('How many sides does a square have?', ['4', 'four']),
    ('How many wheels does a bicycle have?', ['2', 'two']),
    ('Which vehicle flies in the sky?', ['airplane', 'plane', 'aeroplane']),
    ('What do we look at to see the time?', ['clock', 'watch']),
    ('What is the first letter of the English alphabet?', ['a']),
    ('How many letters are in the English alphabet?', ['26']),
    ('Which organ pumps blood in our body?', ['heart']),
    ('Which animal is called the ship of the desert?', ['camel']),
    ('Where do you buy medicine?',
     ['pharmacy', 'medical', 'medical store', 'chemist']),
    ('What game is this server for?', ['bombsquad', 'bomb squad']),
    ('Which BombSquad bomb freezes players?', ['ice', 'ice bomb']),
    ('Which BombSquad powerup protects you?', ['shield']),
    ('Which BombSquad powerup heals you?', ['health', 'health pack']),
    ('How many bombs does the triple bomb powerup give?', ['3', 'three']),
    ('Which BombSquad bomb sticks to players?', ['sticky', 'sticky bomb']),
    ('Which powerup makes your punch stronger?',
     ['punch', 'boxing gloves', 'gloves']),
]


class _State:
    active: dict | None = None
    deck: list = []
    qid = 0
    ticker = None
    scores: dict = {}


S = _State()


def _c(key):
    return kit.cfg(_P, DEFAULTS, key)


def _norm(text: str) -> str:
    return ' '.join(re.sub(r'[^a-z0-9 ]+', ' ', str(text).lower()).split())


def _match(text: str, answers: list) -> bool:
    t = _norm(text)
    toks = t.split()
    if not toks or len(toks) > 6:
        return False
    for a in answers:
        a = _norm(a)
        if not a:
            continue
        if t == a or (' ' in a and a in t) or (' ' not in a and a in toks):
            return True
    return False


def _pool() -> list:
    pool = [(q, list(a)) for q, a in BANK]
    for row in list(_c('server_questions')) * 2 + list(_c('extra')):
        try:
            pool.append((str(row[0]), [str(x) for x in row[1]]))
        except Exception:
            continue
    return pool


def _next() -> tuple[str, list]:
    if not S.deck:
        S.deck = _pool()
        random.shuffle(S.deck)
    return S.deck.pop()


def _hint_text(answer: str) -> str:
    return ' '.join(ch if (i == 0 or ch == ' ') else '_'
                    for i, ch in enumerate(answer))


def _ask() -> bool:
    if S.active is not None:
        return False
    q, ans = _next()
    S.qid += 1
    qid = S.qid
    S.active = {'q': q, 'a': ans, 't': bs.apptime(), 'id': qid}
    pts = int(_c('points'))
    t = float(_c('answer_time'))
    kit.say(f'\ue047 QUIZ TIME \ue048  {q}', (1.0, 0.85, 0.2))
    kit.say(f'Type /a <answer> or just chat it. First correct = {pts}+ pts!',
            (0.6, 0.9, 1.0), chat=False)
    bs.apptimer(t * 0.5, functools.partial(_hint, qid))
    bs.apptimer(t, functools.partial(_timeout, qid))
    return True


def _hint(qid: int) -> None:
    if S.active and S.active['id'] == qid:
        kit.say(f'Hint: {_hint_text(S.active["a"][0])}', (0.7, 1.0, 0.7),
                chat=False)


def _timeout(qid: int) -> None:
    if S.active and S.active['id'] == qid:
        ans = S.active['a'][0]
        S.active = None
        kit.say(f'Time up! The answer was: {ans}', (1.0, 0.6, 0.4))


def _win(key: str, name: str) -> None:
    act = S.active
    if act is None:
        return
    elapsed = bs.apptime() - act['t']
    bonus = max(0, int((float(_c('answer_time')) - elapsed) / 3.0))
    pts = int(_c('points')) + bonus
    row = S.scores.setdefault(key, {'name': name, 'points': 0, 'wins': 0})
    row['name'] = name
    row['points'] += pts
    row['wins'] += 1
    kit.save_json('quiz_scores.json', S.scores)
    S.active = None
    kit.say(f'\ue043 {name} got it! Answer: {act["a"][0]}  +{pts} pts '
            f'(total {row["points"]})', (0.5, 1.0, 0.6))


def _try_answer(cid, text: str) -> bool:
    if S.active is None or not _match(text, S.active['a']):
        return False
    name = kit.name_of(cid)
    _win(kit.account_of(cid) or name, name)
    return True


def _periodic() -> None:
    if not _c('enabled') or S.active is not None:
        return
    if kit.players_online() >= int(_c('min_players')):
        _ask()


_UID = re.compile(r'^(pb|a)-', re.I)


def _on_chat(*args, **kw) -> None:
    if S.active is None or not _c('chat_answers'):
        return
    msg = kw.get('msg') or kw.get('message') or kw.get('text')
    cid = kw.get('client_id', kw.get('cid'))
    for a in args:
        if isinstance(a, bool):
            continue
        if isinstance(a, int) and cid is None:
            cid = a
        elif isinstance(a, str) and not a.startswith('/') \
                and not _UID.match(a) and not msg:
            msg = a
    if msg and cid is not None:
        try:
            _try_answer(cid, str(msg))
        except Exception:
            _LOG.exception('Quiz: chat answer failed')


def _cmd_answer(ctx) -> None:
    if S.active is None:
        kit.reply(ctx, 'No quiz is running right now.')
        return
    cid = getattr(ctx, 'client_id', None)
    text = ' '.join(str(a) for a in (getattr(ctx, 'args', None) or []))
    if cid is None or not text:
        kit.reply(ctx, 'Usage: /a <answer>')
        return
    if not _try_answer(cid, text):
        kit.reply(ctx, 'Not correct - try again!', (1.0, 0.6, 0.5))


def _cmd_quiz(ctx) -> None:
    args = [str(a) for a in (getattr(ctx, 'args', None) or [])]
    sub = args[0].lower() if args else 'info'
    if sub in ('now', 'skip', 'on', 'off', 'add') and not kit.staff(ctx):
        kit.reply(ctx, 'Staff only.')
        return
    if sub == 'now':
        kit.reply(ctx, 'Asking...' if _ask() else 'A question is running.')
    elif sub == 'skip':
        if S.active:
            _timeout(S.active['id'])
        else:
            kit.reply(ctx, 'Nothing to skip.')
    elif sub in ('on', 'off'):
        kit.set_cfg(_P, 'enabled', sub == 'on')
        kit.reply(ctx, f'Quiz {sub}.')
    elif sub == 'add':
        raw = ' '.join(args[1:])
        if '|' not in raw:
            kit.reply(ctx, 'Usage: /quiz add <question> | <answer>, <alias>')
            return
        q, a = raw.split('|', 1)
        answers = [x.strip() for x in a.split(',') if x.strip()]
        if not q.strip() or not answers:
            kit.reply(ctx, 'Need a question and at least one answer.')
            return
        extra = list(_c('extra')) + [[q.strip(), answers]]
        kit.set_cfg(_P, 'extra', extra)
        S.deck = []
        kit.reply(ctx, f'Added. Total extra questions: {len(extra)}')
    elif sub == 'top':
        rows = sorted(S.scores.values(), key=lambda r: -r['points'])[:5]
        text = ' | '.join(f'{i}. {r["name"]} {r["points"]}'
                          for i, r in enumerate(rows, 1)) or 'no scores yet'
        kit.reply(ctx, f'Quiz top: {text}')
    elif sub == 'me':
        cid = getattr(ctx, 'client_id', None)
        key = kit.account_of(cid) or kit.name_of(cid)
        row = S.scores.get(key)
        kit.reply(ctx, f'You have {row["points"]} pts ({row["wins"]} wins).'
                  if row else 'You have no quiz points yet.')
    else:
        state = 'on' if _c('enabled') else 'off'
        kit.reply(ctx, f'Quiz is {state}: a question every '
                       f'{int(float(_c("interval")))}s. Answer with /a '
                       '<answer>. /quiz top | me')


def setup() -> None:
    S.scores = kit.load_json('quiz_scores.json', {})
    S.active = None
    S.ticker = bs.AppTimer(float(_c('interval')), _periodic, repeat=True)
    kit.on('chat', _on_chat, priority=40)
    kit.add_command('quiz', _cmd_quiz, level=0)
    kit.add_command('a', _cmd_answer, level=0)
    kit.add_command('answer', _cmd_answer, level=0)


def teardown() -> None:
    S.ticker = None
    S.qid += 1
    S.active = None
    kit.off('chat', _on_chat)
