"""Text normalisation: defeats leetspeak, homoglyphs, zero-width, spacing."""
from __future__ import annotations

import re
import unicodedata

_ZERO_WIDTH = re.compile('[\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff\u00ad]')
_HOMOGLYPHS = str.maketrans({
    'а': 'a', 'е': 'e', 'о': 'o', 'р': 'p', 'с': 'c', 'у': 'y', 'х': 'x',
    'і': 'i', 'ј': 'j', 'ѕ': 's', 'к': 'k', 'м': 'm', 'т': 't', 'в': 'b',
    'н': 'h', 'ο': 'o', 'α': 'a', 'ε': 'e', 'ι': 'i', 'κ': 'k', 'ν': 'v',
    'ρ': 'p', 'τ': 't', 'υ': 'u'})
_LEET = str.maketrans({'0': 'o', '1': 'i', '3': 'e', '4': 'a', '5': 's',
                       '7': 't', '8': 'b', '@': 'a', '$': 's', '+': 't'})
_NON_ALPHA = re.compile('[^a-z]')
_REPEAT = re.compile(r'(.)\1+')


def clean(text: str) -> str:
    return _ZERO_WIDTH.sub('', unicodedata.normalize('NFKC', text or ''))


def skeleton(text: str) -> str:
    t = clean(text).lower().translate(_HOMOGLYPHS)
    t = ''.join(c for c in unicodedata.normalize('NFKD', t)
                if not unicodedata.combining(c))
    return _NON_ALPHA.sub('', t.translate(_LEET))


def squash(s: str) -> str:
    return _REPEAT.sub(r'\1', s)


def name_key(text: str) -> str:
    """Identity key for names: 'L-u-c-1-ö-u-s' == 'Lucious'."""
    return squash(skeleton(text)).replace('l', 'i')


def _targets(words: list[str]) -> list[tuple[str, str]]:
    out = []
    for w in words:
        raw = skeleton(w)
        if raw:
            out.append((raw, squash(raw)))
    return out


def _hit(tok: str, targets: list[tuple[str, str]]) -> bool:
    if not tok:
        return False
    for raw, sq in targets:
        if tok == raw:
            return True
        if len(tok) >= len(raw) and squash(tok) == sq:
            return True
        if len(raw) >= 5 and raw in tok:
            return True
    return False


def censor(text: str, words: list[str]) -> tuple[str, bool]:
    targets = _targets(words)
    if not targets:
        return text, False
    hit = False
    out = []
    for tok in re.split(r'(\s+)', text):
        if tok.strip() and _hit(skeleton(tok), targets):
            out.append('*' * len(tok))
            hit = True
        else:
            out.append(tok)
    result = ''.join(out)
    # spaced-out evasion: "b a d w o r d"
    run = ''
    evasion = False
    for tok in text.split() + ['__end__']:
        s = skeleton(tok)
        if len(s) == 1:
            run += s
            continue
        if len(run) >= 3 and _hit(run, targets):
            evasion = True
        run = ''
    if evasion:
        return '*' * min(len(text), 12), True
    return result, hit
