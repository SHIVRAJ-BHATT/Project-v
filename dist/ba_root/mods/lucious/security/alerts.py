"""Non-blocking Discord webhook alerts (background thread, rate-limited)."""
from __future__ import annotations

import json
import logging
import queue
import threading
import time
import urllib.request

from lucious import config

log = logging.getLogger('lucious')
_q: queue.Queue = queue.Queue(maxsize=200)
_stop = threading.Event()
_thread: threading.Thread | None = None


def start() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _thread = threading.Thread(target=_worker, args=(_stop,),
                               name='lucious-alerts', daemon=True)
    _thread.start()


def stop() -> None:
    _stop.set()


def send(title: str, description: str, color: int = 0xE74C3C) -> None:
    url = config.get('security.discord_webhook') or ''
    if not url:
        return
    payload = {
        'username': f"{config.get('server_tag', 'Lucious')} Security",
        'allowed_mentions': {'parse': []},
        'embeds': [{
            'title': title[:256], 'description': description[:4000],
            'color': color,
            'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        }],
    }
    try:
        _q.put_nowait((url, payload))
    except queue.Full:
        pass


def _worker(stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        try:
            url, payload = _q.get(timeout=1.0)
        except queue.Empty:
            continue
        try:
            req = urllib.request.Request(
                url, data=json.dumps(payload).encode(), method='POST',
                headers={'Content-Type': 'application/json',
                         'User-Agent': 'LuciousSecurity/1.0'})
            urllib.request.urlopen(req, timeout=10).close()
        except Exception as exc:
            log.warning('[Lucious] webhook failed: %s', exc)
        time.sleep(1.2)
