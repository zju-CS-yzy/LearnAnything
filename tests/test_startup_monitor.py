from __future__ import annotations

import unittest

from app.startup_monitor import monitor_backend_startup


class FakeBackendThread:
    def __init__(self, *, alive: bool = True, error: str | None = None):
        self.alive = alive
        self.error = error

    def is_alive(self) -> bool:
        return self.alive


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def wait(self, seconds: float) -> None:
        self.now += seconds


class StartupMonitorTests(unittest.TestCase):
    def test_cold_start_continues_after_slow_threshold_until_ready(self) -> None:
        clock = FakeClock()
        slow_events: list[float] = []

        result = monitor_backend_startup(
            FakeBackendThread(),
            "http://test/health",
            slow_after=2,
            timeout=10,
            poll_interval=1,
            on_slow=slow_events.append,
            probe=lambda _url, _timeout: clock.now >= 4,
            monotonic=clock.monotonic,
            wait=clock.wait,
        )

        self.assertEqual(result.state, "ready")
        self.assertEqual(result.elapsed, 4)
        self.assertEqual(slow_events, [2])

    def test_backend_error_fails_immediately_with_detail(self) -> None:
        result = monitor_backend_startup(
            FakeBackendThread(error="address already in use"),
            "http://test/health",
            probe=lambda _url, _timeout: False,
        )

        self.assertEqual(result.state, "failed")
        self.assertIn("address already in use", result.detail)

    def test_backend_thread_exit_is_not_reported_as_timeout(self) -> None:
        result = monitor_backend_startup(
            FakeBackendThread(alive=False),
            "http://test/health",
            probe=lambda _url, _timeout: False,
        )

        self.assertEqual(result.state, "failed")
        self.assertIn("提前退出", result.detail)

    def test_hard_timeout_is_bounded(self) -> None:
        clock = FakeClock()
        result = monitor_backend_startup(
            FakeBackendThread(),
            "http://test/health",
            slow_after=1,
            timeout=3,
            poll_interval=1,
            probe=lambda _url, _timeout: False,
            monotonic=clock.monotonic,
            wait=clock.wait,
        )

        self.assertEqual(result.state, "failed")
        self.assertEqual(result.elapsed, 3)
        self.assertIn("3 秒", result.detail)


if __name__ == "__main__":
    unittest.main()
