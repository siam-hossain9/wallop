# wallop — Test Case Document

**Version tested:** 0.1.0 · **Suite:** 40 automated test cases, all passing
**How to reproduce:** `uv run pytest -v` from the repo root (no setup beyond `uv` required)
**Continuous verification:** every push runs the full suite plus a live smoke run of the
application on Ubuntu, macOS, and Windows × Python 3.10 and 3.13 —
[public CI results](https://github.com/siam-hossain9/wallop/actions).

## Test strategy

The suite covers the four critical paths, each in isolation:

1. **Statistics** (`test_stats.py`) — if the numbers are wrong, the tool lies. Pure unit tests with a fake clock for determinism.
2. **Physics** (`test_physics.py`) — the visualization must encode the data truthfully. Pure simulation tests, seeded RNG.
3. **Rendering** (`test_renderer.py`) — pixels must map to the right terminal characters and colors.
4. **HTTP engine** (`test_engine.py`) — integration tests against a **real in-process HTTP server**, exercising live requests, timeouts, dropped connections, rate limiting, and shutdown.
5. **CLI** (`test_cli.py`) — argument parsing contracts.

End-to-end behavior is additionally verified in CI by booting the full application
headlessly (`wallop demo -d 4`) on all three operating systems.

## Test cases

### 1. Statistics — `tests/test_stats.py` (7 cases)

| ID | Test case | Verifies | Result |
|---|---|---|---|
| ST-01 | `test_status_classification` | HTTP codes map to the right class: 200→2xx, 301→3xx, 404→4xx, 503→5xx, −1→timeout, 0→transport error | ✅ |
| ST-02 | `test_percentile_known_values` | Percentile math is exact on a known 1–100 dataset (p50=50, p95=95, p99=99); empty and single-value edge cases | ✅ |
| ST-03 | `test_collector_counts_and_percentiles` | 101 mixed requests produce correct totals, per-class counts, in-flight bookkeeping, p50 and error rate | ✅ |
| ST-04 | `test_rps_window_prunes_old_completions` | Requests-per-second uses a sliding 1s window; old completions age out (fake clock) | ✅ |
| ST-05 | `test_latency_ema_tracks_changes` | The latency moving average converges when server speed changes (drives particle speed) | ✅ |
| ST-06 | `test_final_summary_shape` | The end-of-run report contains correct totals, status breakdown, bytes read, percentiles | ✅ |
| ST-07 | `test_formatters` | Human-readable formatting: 0.012s→"12ms", 1.5s→"1.50s", 2048 bytes→"2.0 KB" | ✅ |

### 2. Physics — `tests/test_physics.py` (12 cases)

| ID | Test case | Verifies | Result |
|---|---|---|---|
| PH-01 | `test_spawn_creates_particle_at_left_edge` | Each request spawns one particle at x=0 inside the field | ✅ |
| PH-02 | `test_flight_is_monotonic_and_stalls_short_of_wall` | A particle never moves backward and **never touches the wall before its real response arrives** (slow requests visibly stall at ~96%) | ✅ |
| PH-03 | `test_completion_removes_particle` | A finished request removes its particle | ✅ |
| PH-04 | `test_5xx_spawns_explosion_debris_and_shake` | Server errors produce ≥8 red debris particles and screen shake | ✅ |
| PH-05 | `test_2xx_spawns_small_impact_without_shake` | Successes produce a small spark (2–4 particles), no shake | ✅ |
| PH-06 | `test_timeout_smoke_rises` | Timeouts create smoke that drifts **upward** and ignores gravity | ✅ |
| PH-07 | `test_gravity_pulls_debris_down` | Debris vertical velocity increases under gravity each tick | ✅ |
| PH-08 | `test_debris_expires` | Effects have lifetimes and are removed when expired | ✅ |
| PH-09 | `test_debris_budget_is_respected` | Under 2,000 rapid completions, debris never exceeds the cap (rendering can't choke load generation) | ✅ |
| PH-10 | `test_crashed_5xx_debris_leaves_embers` | Error debris that hits the ground leaves glowing embers | ✅ |
| PH-11 | `test_wall_color_shifts_with_errors` | The wall measurably reddens as the recent error ratio rises | ✅ |
| PH-12 | `test_resize_clamps_to_minimum` | Terminal resize cannot shrink the world below a renderable minimum | ✅ |

### 3. Renderer — `tests/test_renderer.py` (7 cases)

| ID | Test case | Verifies | Result |
|---|---|---|---|
| RD-01 | `test_framebuffer_dimensions` | An 80×20-cell buffer exposes 80×40 pixels (half-block doubling) and emits 20 rows | ✅ |
| RD-02 | `test_half_block_mapping` | Pixel pairs map to the correct glyph and colors: upper-only→▀, lower-only→▄, both→▀ with fg+bg, neither→space | ✅ |
| RD-03 | `test_out_of_bounds_pixels_ignored` | Drawing outside the buffer is safely ignored (no crash during shake/resize) | ✅ |
| RD-04 | `test_ansi_rows_contain_truecolor_codes` | Output contains correct 24-bit ANSI color sequences | ✅ |
| RD-05 | `test_draw_world_renders_wall_and_particles` | A populated world rasterizes the full wall column plus particles | ✅ |
| RD-06 | `test_sparkline_normalizes` | The RPS sparkline normalizes to its peak and pads correctly | ✅ |
| RD-07 | `test_hud_contains_key_stats` | The HUD shows RPS, latency percentiles, status counts, and the quit hint | ✅ |

### 4. HTTP engine — `tests/test_engine.py` (10 cases, real HTTP against a live in-process server)

| ID | Test case | Verifies | Result |
|---|---|---|---|
| EN-01 | `test_engine_completes_requested_total` | `-n 30` sends exactly 30 requests; all latencies/bytes positive; in-flight returns to 0 | ✅ |
| EN-02 | `test_engine_every_start_gets_a_completion` | Every launched request gets exactly one completion callback (no lost/duplicate particles) | ✅ |
| EN-03 | `test_engine_records_status_codes` | Real 404 and 500 responses are recorded with exact codes and classes | ✅ |
| EN-04 | `test_engine_timeout_reported_as_timeout` | A server that hangs past the timeout is reported as a timeout, not an error | ✅ |
| EN-05 | `test_engine_dropped_connection_is_transport_error` | A server that accepts then drops the connection is reported as a transport error | ✅ |
| EN-06 | `test_engine_duration_stops_run` | `-d 0.5s` actually stops the run | ✅ |
| EN-07 | `test_engine_rate_limit_roughly_respected` | `-r 40` paces 20 requests over ≥0.35s (no thundering burst) | ✅ |
| EN-08 | `test_engine_stop_event_halts_workers` | Pressing quit stops all workers promptly | ✅ |
| EN-09 | `test_demo_server_phases` | The chaos server follows its script: healthy→latency creep→error storm→meltdown→recovery, then cycles | ✅ |
| EN-10 | `test_demo_server_serves_traffic` | End-to-end: the engine successfully load-tests the chaos server | ✅ |

### 5. CLI — `tests/test_cli.py` (4 cases)

| ID | Test case | Verifies | Result |
|---|---|---|---|
| CL-01 | `test_parse_duration` | `30s`/`90`/`2m`/`500ms`/`1.5s` parse correctly; garbage is rejected | ✅ |
| CL-02 | `test_parse_header` | `'Name: value'` headers parse; malformed input rejected | ✅ |
| CL-03 | `test_run_args_parse` | Full command line round-trips: URL, `-c`, `-d`, repeated `-H` | ✅ |
| CL-04 | `test_demo_args_parse` | `demo` subcommand options parse | ✅ |

## Platform matrix (CI, every push)

| OS | Python 3.10 | Python 3.13 |
|---|---|---|
| Ubuntu (latest) | ✅ 40/40 + smoke run | ✅ 40/40 + smoke run |
| macOS (latest) | ✅ 40/40 + smoke run | ✅ 40/40 + smoke run |
| Windows (latest) | ✅ 40/40 + smoke run | ✅ 40/40 + smoke run |

*Smoke run* = the real application booted headlessly (`wallop demo -d 4 -c 10`): it starts
the chaos server, generates live HTTP load, renders frames, and must exit cleanly.

## Known limitations / not covered by automation

- Visual appearance (colors, motion aesthetics) is verified by eye, per the policy in CONTRIBUTING.md.
- Interactive keyboard input (`q`) is platform-guarded code verified manually on Windows.
- Sustained-load soak testing (hours) has not been performed.
