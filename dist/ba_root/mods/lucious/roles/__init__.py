# lucious/roles/__init__.py
"""Role system: fixed members in config.json, timed grants in roles.db."""
from __future__ import annotations

from lucious import config, utils
from lucious.roles import ids, store  # noqa: F401

__reload_order__ = ('lucious.roles.ids', 'lucious.roles.store',
                    'lucious.roles.cmds')


def _defs() -> dict:
    return config.get('roles') or {}


def roles_of(account: str | None) -> list[str]:
    if not account:
        return []
    defs = _defs()
    out = [n for n, r in defs.items() if account in r.get('members', [])]
    out += [n for n in store.grants_of(account) if n in defs and n not in out]
    return out


def level_of(account: str | None) -> int:
    defs = _defs()
    return max((int(defs[n].get('level', 0)) for n in roles_of(account)),
               default=0)


def level_of_client(client_id: int, account: str | None) -> int:
    return 1000 if client_id == utils.HOST else level_of(account)


def role_name(account: str | None) -> str:
    defs = _defs()
    names = roles_of(account)
    return max(names, key=lambda n: int(defs[n].get('level', 0)),
               default='player')


def tag_of(account: str | None) -> str:
    return (_defs().get(role_name(account)) or {}).get('tag', '')


def staff_accounts() -> set[str]:
    need = int(config.get('security.staff_bypass_level', 50))
    out: set[str] = set()
    for n, r in _defs().items():
        if int(r.get('level', 0)) >= need:
            out.update(r.get('members', []))
            out.update(store.members_of(n))
    return out


def setup() -> None:
    store.open_db()
    from lucious.roles import cmds  # noqa: F401


def teardown() -> None:
    store.close_db()
