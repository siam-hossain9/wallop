# Contributing to wallop

Thanks for wanting to make load testing more fun. Contributions of all sizes are welcome.

## Getting set up

```sh
git clone https://github.com/siam-hossain9/wallop && cd wallop
uv sync           # creates a venv with dev dependencies
uv run pytest     # everything should pass before you start
uv run wallop demo
```

That's it — one runtime dependency (`aiohttp`), no build steps.

## Project layout

| File | What lives there |
| --- | --- |
| `src/wallop/engine.py` | async load generation (workers, pacing, error taxonomy) |
| `src/wallop/physics.py` | the particle world — pure simulation, no I/O |
| `src/wallop/renderer.py` | half-block framebuffer, ANSI frames, HUD |
| `src/wallop/stats.py` | streaming metrics (RPS window, percentiles, EMA) |
| `src/wallop/app.py` | render loop tying engine → world → screen |
| `src/wallop/demoserver.py` | the built-in chaos server |
| `src/wallop/cli.py` | argument parsing and subcommands |

`physics.py` and `stats.py` are deliberately pure (no terminal, no network) so they're easy to test — please keep them that way.

## Guidelines

- **Add a test** for any behavior change in `engine`, `stats`, or `physics`. Rendering changes should at least keep `test_renderer.py` green.
- **Stay dependency-light.** New runtime dependencies need a strong reason.
- **Eyeball it.** For anything visual, run `wallop demo` and watch a full chaos cycle (~42s) before and after your change. Mention what you saw in the PR.
- **Keep effects honest.** The scene must never misrepresent the data — e.g. debris is sampled under load, but counters never are.

## Good first issues

- New impact effects (3xx redirect trails, HEAD-request tracers)
- Themes / alternate palettes (`--theme`)
- Braille-based rendering mode for even higher resolution
- The `--replay` access-log mode from the roadmap

## Reporting bugs

Include your OS, terminal emulator, Python version, the exact command, and — if it's a rendering glitch — a screenshot. Terminal quirks are real; we keep workarounds documented in `renderer.py`.
