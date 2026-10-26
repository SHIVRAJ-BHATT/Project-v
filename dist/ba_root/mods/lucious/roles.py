"""Role levels from config."""
from __future__ import annotations

from lucious import config, utils


def level_of(account: str | None) -> int:
    if not account:
        return 0
    best = 0
    for role in (config.get('roles') or {}).values():
        if account in role.get('members', []):
            best = max(best, int(role.get('level', 0)))
    return best


def level_of_client(client_id: int, account: str | None) -> int:
    return 1000 if client_id == utils.HOST else level_of(account)


def role_name(account: str | None) -> str:
    best, name = 0, 'player'
    for rname, role in (config.get('roles') or {}).items():
        lvl = int(role.get('level', 0))
        if account and account in role.get('members', []) and lvl > best:
            best, name = lvl, rname
    return name


def staff_accounts() -> set[str]:
    need = int(config.get('security.staff_bypass_level', 50))
    out: set[str] = set()
    for role in (config.get('roles') or {}).values():
        if int(role.get('level', 0)) >= need:
            out.update(role.get('members', []))
    return out
