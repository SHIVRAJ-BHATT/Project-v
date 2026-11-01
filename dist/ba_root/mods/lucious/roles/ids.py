# lucious/roles/ids.py
"""Account-id helpers. V1 ids look like pb-XXXX, V2 ids like a-XXXX."""
from __future__ import annotations

import re

from lucious import utils

_ID = re.compile(r'^(pb|a)-[A-Za-z0-9_\-]{4,}$')


def is_account_id(text: str) -> bool:
    return bool(_ID.match(text.strip()))


def kind(account: str) -> str:
    return 'v1' if account.startswith('pb-') else (
        'v2' if account.startswith('a-') else 'unknown')


def resolve(arg: str):
    """-> (account | None, display name, error | None). Accepts ids or names."""
    arg = arg.strip()
    if is_account_id(arg):
        return arg, arg, None
    _cid, acc, name, err = utils.resolve_target(arg)
    if err:
        return None, name, err
    if not acc:
        return None, name, f'{name} has no verified account yet.'
    return acc, name, None
