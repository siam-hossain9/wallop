"""Streaming statistics for a load run.

Keeps everything needed for both the live HUD (cheap snapshots at frame
rate) and the final summary (exact percentiles over the whole run).
"""

from __future__ import annotations

import time
from array import array
from collections import Counter, deque
from dataclasses import dataclass, field


@dataclass
class RequestResult:
    """Outcome of a single request.

    status: HTTP status code, 0 for a transport error, -1 for a timeout.
    latency: seconds from send to fully-read body.
    """

    status: int
    latency: float
    bytes_read: int = 0
    error: str | None = None

    @property
    def status_class(self) -> str:
        if self.status == -1:
            return "timeout"
        if self.status == 0:
            return "error"
        return f"{self.status // 100}xx"


@dataclass
class StatsSnapshot:
    elapsed: float
    total: int
    rps: float
    in_flight: int
    p50: float
    p95: float
    p99: float
    class_counts: dict[str, int]
    error_rate: float
    latency_ema: float
    rps_history: list[float] = field(default_factory=list)


def percentile(sorted_values: list[float], q: float) -> float:
    """Nearest-rank percentile over a pre-sorted list. q in [0, 100]."""
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = max(1, round(q / 100 * len(sorted_values)))
    return sorted_values[min(rank, len(sorted_values)) - 1]


class StatsCollector:
    """Accumulates results; thread-unsafe by design (single event loop)."""

    RECENT_WINDOW = 4096  # latencies used for live percentiles
    RPS_WINDOW = 1.0  # seconds

    def __init__(self, clock=time.perf_counter) -> None:
        self._clock = clock
        self.started_at = clock()
        self.total = 0
        self.in_flight = 0
        self.bytes_read = 0
        self.class_counts: Counter[str] = Counter()
        self.status_counts: Counter[int] = Counter()
        self.all_latencies: array = array("d")
        self.recent_latencies: deque[float] = deque(maxlen=self.RECENT_WINDOW)
        self.completion_times: deque[float] = deque()
        self.latency_ema: float = 0.0
        self._ema_alpha = 0.1
        self.rps_history: deque[float] = deque(maxlen=80)
        self._last_history_at = self.started_at

    # -- recording -----------------------------------------------------

    def record_start(self) -> None:
        self.in_flight += 1

    def record(self, result: RequestResult) -> None:
        now = self._clock()
        self.in_flight = max(0, self.in_flight - 1)
        self.total += 1
        self.bytes_read += result.bytes_read
        self.class_counts[result.status_class] += 1
        if result.status > 0:
            self.status_counts[result.status] += 1
        self.all_latencies.append(result.latency)
        self.recent_latencies.append(result.latency)
        self.completion_times.append(now)
        if self.latency_ema == 0.0:
            self.latency_ema = result.latency
        else:
            self.latency_ema += self._ema_alpha * (result.latency - self.latency_ema)

    # -- reading -------------------------------------------------------

    def current_rps(self) -> float:
        now = self._clock()
        cutoff = now - self.RPS_WINDOW
        while self.completion_times and self.completion_times[0] < cutoff:
            self.completion_times.popleft()
        return len(self.completion_times) / self.RPS_WINDOW

    def error_rate(self) -> float:
        if self.total == 0:
            return 0.0
        bad = (
            self.class_counts["5xx"]
            + self.class_counts["error"]
            + self.class_counts["timeout"]
        )
        return bad / self.total

    def snapshot(self) -> StatsSnapshot:
        now = self._clock()
        rps = self.current_rps()
        # sample the rps history at ~4 Hz regardless of frame rate
        if now - self._last_history_at >= 0.25:
            self.rps_history.append(rps)
            self._last_history_at = now
        recent = sorted(self.recent_latencies)
        return StatsSnapshot(
            elapsed=now - self.started_at,
            total=self.total,
            rps=rps,
            in_flight=self.in_flight,
            p50=percentile(recent, 50),
            p95=percentile(recent, 95),
            p99=percentile(recent, 99),
            class_counts=dict(self.class_counts),
            error_rate=self.error_rate(),
            latency_ema=self.latency_ema or 0.3,
            rps_history=list(self.rps_history),
        )

    def final_summary(self) -> dict:
        elapsed = max(1e-9, self._clock() - self.started_at)
        latencies = sorted(self.all_latencies)
        return {
            "elapsed": elapsed,
            "total": self.total,
            "rps": self.total / elapsed,
            "p50": percentile(latencies, 50),
            "p90": percentile(latencies, 90),
            "p95": percentile(latencies, 95),
            "p99": percentile(latencies, 99),
            "min": latencies[0] if latencies else 0.0,
            "max": latencies[-1] if latencies else 0.0,
            "class_counts": dict(self.class_counts),
            "status_counts": dict(self.status_counts),
            "bytes_read": self.bytes_read,
        }


def fmt_duration(seconds: float) -> str:
    if seconds < 1:
        return f"{seconds * 1000:.1f}ms"
    if seconds < 60:
        return f"{seconds:.1f}s"
    return f"{int(seconds // 60)}m{seconds % 60:04.1f}s"


def fmt_latency(seconds: float) -> str:
    if seconds <= 0:
        return "-"
    if seconds < 0.001:
        return f"{seconds * 1_000_000:.0f}us"
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    return f"{seconds:.2f}s"


def fmt_bytes(n: int) -> str:
    value = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} TB"
