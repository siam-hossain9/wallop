import time

from wallop.stats import (
    RequestResult,
    StatsCollector,
    fmt_bytes,
    fmt_latency,
    percentile,
)


def make_result(status=200, latency=0.05, bytes_read=10):
    return RequestResult(status=status, latency=latency, bytes_read=bytes_read)


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_status_classification():
    assert make_result(status=200).status_class == "2xx"
    assert make_result(status=301).status_class == "3xx"
    assert make_result(status=404).status_class == "4xx"
    assert make_result(status=503).status_class == "5xx"
    assert make_result(status=-1).status_class == "timeout"
    assert make_result(status=0).status_class == "error"


def test_percentile_known_values():
    data = sorted(float(i) for i in range(1, 101))  # 1..100
    assert percentile(data, 50) == 50.0
    assert percentile(data, 95) == 95.0
    assert percentile(data, 99) == 99.0
    assert percentile(data, 100) == 100.0
    assert percentile([], 50) == 0.0
    assert percentile([7.0], 99) == 7.0


def test_collector_counts_and_percentiles():
    clock = FakeClock()
    stats = StatsCollector(clock=clock)
    for i in range(100):
        stats.record_start()
        stats.record(make_result(status=200, latency=(i + 1) / 1000))
    stats.record_start()
    stats.record(make_result(status=500, latency=0.5))

    assert stats.total == 101
    assert stats.class_counts["2xx"] == 100
    assert stats.class_counts["5xx"] == 1
    assert stats.in_flight == 0
    snap = stats.snapshot()
    assert 0.045 <= snap.p50 <= 0.055
    assert snap.error_rate == 1 / 101


def test_rps_window_prunes_old_completions():
    clock = FakeClock()
    stats = StatsCollector(clock=clock)
    for _ in range(30):
        stats.record_start()
        stats.record(make_result())
    assert stats.current_rps() == 30.0
    clock.t += 2.0  # all completions now older than the 1s window
    assert stats.current_rps() == 0.0


def test_latency_ema_tracks_changes():
    stats = StatsCollector()
    stats.record(make_result(latency=0.1))
    assert stats.latency_ema == 0.1
    for _ in range(200):
        stats.record(make_result(latency=0.5))
    assert 0.45 < stats.latency_ema <= 0.5


def test_final_summary_shape():
    stats = StatsCollector()
    for status in (200, 200, 404, 500):
        stats.record_start()
        stats.record(make_result(status=status, latency=0.02, bytes_read=100))
    summary = stats.final_summary()
    assert summary["total"] == 4
    assert summary["class_counts"] == {"2xx": 2, "4xx": 1, "5xx": 1}
    assert summary["status_counts"] == {200: 2, 404: 1, 500: 1}
    assert summary["bytes_read"] == 400
    assert summary["p50"] == 0.02


def test_formatters():
    assert fmt_latency(0.012) == "12ms"
    assert fmt_latency(1.5) == "1.50s"
    assert fmt_latency(0.0005) == "500us"
    assert fmt_bytes(512) == "512 B"
    assert fmt_bytes(2048) == "2.0 KB"
