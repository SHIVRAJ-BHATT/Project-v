# ba_meta require api 9
"""Lucious entry point. Boots the framework once the app is running."""
from __future__ import annotations

import logging

import babase


# ba_meta export babase.Plugin
class LuciousLoader(babase.Plugin):
    def on_app_running(self) -> None:
        try:
            from lucious import core
            core.boot()
        except Exception:
            logging.exception('[Lucious] FATAL: boot failed')

    def on_app_shutdown(self) -> None:
        try:
            from lucious import core
            core.shutdown()
        except Exception:
            logging.exception('[Lucious] shutdown error')
