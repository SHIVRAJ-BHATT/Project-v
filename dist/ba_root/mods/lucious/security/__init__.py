"""Lucious Security Suite."""
__reload_order__ = (
    'lucious.security.storage', 'lucious.security.normalize',
    'lucious.security.alerts', 'lucious.security.punish',
    'lucious.security.chatguard', 'lucious.security.joinguard',
    'lucious.security.cmds',
)


def setup() -> None:
    from lucious.security import (alerts, chatguard, cmds,  # noqa: F401
                                  joinguard, storage)
    storage.open_db()
    alerts.start()
    chatguard.setup()
    joinguard.setup()


def teardown() -> None:
    from lucious.security import alerts, storage
    alerts.stop()
    storage.close_db()
