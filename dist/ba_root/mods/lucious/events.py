"""Priority event bus with error isolation and owner-based cleanup."""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Callable

log = logging.getLogger('lucious')


def _owned(module: str, prefix: str) -> bool:
    return module == prefix or module.startswith(prefix + '.')


class EventBus:
    def __init__(self) -> None:
        self._h: dict[str, list[tuple[int, Callable]]] = defaultdict(list)

    def subscribe(self, event: str, fn: Callable, priority: int = 50) -> None:
        key = (fn.__module__, fn.__qualname__)
        lst = [h for h in self._h[event]
               if (h[1].__module__, h[1].__qualname__) != key]
        lst.append((priority, fn))
        lst.sort(key=lambda h: h[0])
        self._h[event] = lst

    def emit(self, event: str, *args: Any) -> None:
        for _, fn in list(self._h.get(event, ())):
            try:
                fn(*args)
            except Exception:
                log.exception('[Lucious] %s.%s failed on %r',
                              fn.__module__, fn.__qualname__, event)

    def filter(self, event: str, value: Any, *args: Any) -> Any:
        """Pipeline: each handler returns new value, or None to block."""
        for _, fn in list(self._h.get(event, ())):
            try:
                result = fn(value, *args)
            except Exception:
                log.exception('[Lucious] filter %s.%s crashed',
                              fn.__module__, fn.__qualname__)
                continue
            if result is None:
                return None
            value = result
        return value

    def check(self, event: str, *args: Any) -> bool:
        """Any handler returning False denies. Crashes fail-open."""
        for _, fn in list(self._h.get(event, ())):
            try:
                if fn(*args) is False:
                    return False
            except Exception:
                log.exception('[Lucious] check %s.%s crashed',
                              fn.__module__, fn.__qualname__)
        return True

    def remove_owner(self, prefix: str) -> None:
        for event in list(self._h):
            self._h[event] = [h for h in self._h[event]
                              if not _owned(h[1].__module__, prefix)]


bus = EventBus()
