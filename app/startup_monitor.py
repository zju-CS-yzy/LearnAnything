"""Backend startup monitoring shared by the desktop launcher and tests."""

from __future__ import annotations

import time
import urllib.request
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class BackendStartupResult:
    state: str
    elapsed: float
    detail: str = ""


def probe_backend(health_url: str, timeout: float = 1.0) -> bool:
    """Return True only when the backend health endpoint returns HTTP 200."""
    try:
        request = urllib.request.Request(health_url, method="GET")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status == 200
    except Exception:
        return False


def monitor_backend_startup(
    backend_thread,
    health_url: str,
    *,
    slow_after: float = 30.0,
    timeout: float = 180.0,
    poll_interval: float = 0.5,
    on_slow: Callable[[float], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
    probe: Callable[[str, float], bool] = probe_backend,
    monotonic: Callable[[], float] = time.monotonic,
    wait: Callable[[float], None] = time.sleep,
) -> BackendStartupResult:
    """Monitor startup without treating a normal cold start as a failure.

    ``slow_after`` is informational only. A failure is returned immediately
    when the backend thread reports an exception or exits; otherwise the hard
    ``timeout`` remains the final upper bound.
    """
    should_stop = should_stop or (lambda: False)
    started_at = monotonic()
    slow_notified = False

    while True:
        elapsed = max(0.0, monotonic() - started_at)
        if should_stop():
            return BackendStartupResult("stopped", elapsed)

        if probe(health_url, min(1.0, max(0.1, poll_interval))):
            return BackendStartupResult("ready", elapsed)

        thread_error = getattr(backend_thread, "error", None)
        if thread_error:
            return BackendStartupResult("failed", elapsed, str(thread_error))
        if not backend_thread.is_alive():
            return BackendStartupResult(
                "failed",
                elapsed,
                "后端线程已提前退出，未能启动 HTTP 服务。",
            )

        if elapsed >= slow_after and not slow_notified:
            slow_notified = True
            if on_slow:
                on_slow(elapsed)

        if elapsed >= timeout:
            return BackendStartupResult(
                "failed",
                elapsed,
                f"后端进程仍在运行，但 {timeout:.0f} 秒内未通过健康检查。",
            )

        wait(poll_interval)
