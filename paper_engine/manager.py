"""Runs each active template's live paper-trading loop in its own background
thread, aligned to that template's window boundaries, reusing topbot's real
run_window() for the actual RSI decision / ladder / CLOB fill / resolution.
"""

from __future__ import annotations

import threading
import time
import traceback
from datetime import datetime, timezone

import httpx

from . import store
from .topbot_bridge import PaperExecutor, RetryState, build_config, run_window, window_start

# Bybit/Gamma/CLOB calls occasionally hit a plain network blip (TLS handshake
# timeout, read timeout, connection reset). Those are worth a couple of quick
# retries before giving up on the window; a real error (bad market, bad
# response schema) won't be helped by retrying and fails immediately instead.
TRANSIENT_EXCEPTIONS = (httpx.TimeoutException, httpx.TransportError, OSError)
MAX_ATTEMPTS = 3
RETRY_DELAY_SEC = 5.0


class TemplateManager:
    def __init__(self) -> None:
        self._threads: dict[str, threading.Thread] = {}
        self._stop_events: dict[str, threading.Event] = {}
        self._lock = threading.Lock()

    def start(self, template_id: str) -> None:
        with self._lock:
            existing = self._threads.get(template_id)
            if existing and existing.is_alive():
                return
            row = store.get_template(template_id)
            if row is None:
                return
            cfg = build_config(row)
            stop_event = threading.Event()
            thread = threading.Thread(
                target=self._loop,
                args=(template_id, cfg, stop_event),
                name=f"template-{template_id}",
                daemon=True,
            )
            self._stop_events[template_id] = stop_event
            self._threads[template_id] = thread
            thread.start()
        store.set_status(template_id, "running")

    def stop(self, template_id: str) -> None:
        with self._lock:
            stop_event = self._stop_events.get(template_id)
            if stop_event:
                stop_event.set()
        store.set_status(template_id, "stopped")

    def is_running(self, template_id: str) -> bool:
        with self._lock:
            thread = self._threads.get(template_id)
            return bool(thread and thread.is_alive())

    def resume_all_running(self) -> None:
        for row in store.list_running_templates():
            self.start(row["id"])

    def _loop(self, template_id: str, cfg, stop_event: threading.Event) -> None:
        executor = PaperExecutor(clob_host=cfg.clob_host, gamma_base=cfg.gamma_base)
        retry_state = RetryState()

        # Align once to the next upcoming window boundary. From here on,
        # `next_start` always advances by exactly one window length -- never
        # re-derived from the wall clock -- so a window is never silently
        # dropped just because the previous run_window() call ran long
        # (it blocks polling for fills/resolution well past window close).
        now = time.time()
        next_start = window_start(now, window_seconds=cfg.window_seconds)
        if now - next_start > 2.0:
            next_start += cfg.window_seconds

        while not stop_event.is_set():
            self._sleep_until(next_start, stop_event)
            if stop_event.is_set():
                return

            start = next_start
            try:
                record, retry_state = self._run_window_with_retry(
                    cfg, executor, start, retry_state, stop_event
                )
                store.save_trade(template_id, record)
            except Exception as exc:  # noqa: BLE001
                traceback.print_exc()
                store.save_trade(
                    template_id,
                    {
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "window_start": start,
                        "window_end": start + cfg.window_seconds,
                        "skipped": True,
                        "error": str(exc),
                    },
                )

            next_start += cfg.window_seconds

    @staticmethod
    def _run_window_with_retry(cfg, executor, start, retry_state, stop_event: threading.Event):
        last_exc: Exception | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                return run_window(cfg, executor, now=start, retry_state=retry_state)
            except TRANSIENT_EXCEPTIONS as exc:
                last_exc = exc
                if attempt < MAX_ATTEMPTS and not stop_event.is_set():
                    print(
                        f"[template] transient error on attempt {attempt}/{MAX_ATTEMPTS}, "
                        f"retrying in {RETRY_DELAY_SEC:.0f}s: {exc}"
                    )
                    stop_event.wait(RETRY_DELAY_SEC)
        raise last_exc

    @staticmethod
    def _sleep_until(target_ts: float, stop_event: threading.Event) -> None:
        while True:
            remaining = target_ts - time.time()
            if remaining <= 0 or stop_event.is_set():
                return
            stop_event.wait(min(remaining, 1.0))
