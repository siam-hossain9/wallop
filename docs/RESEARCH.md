# Why wallop exists — the research behind it

This project began with a question: *what genuinely doesn't exist yet?* Four landscape
sweeps (GitHub, Hacker News archives, arXiv, the open web — June 2026) later, this was
the answer. Receipts below.

## The gap, in one paragraph

Every load tester renders charts. Every visceral traffic visualizer is a desktop GUI.
Nobody has put the two together in the terminal. wallop is the intersection of three
*individually proven* ingredients that had never been combined: a load generator, a
physics scene where each request is a visible object, and terminal-native rendering.

## What exists today (verified June 2026)

### Load testers — all chart-based
| Tool | Stars | Live visualization |
| --- | --- | --- |
| wrk | ~38k | none (text summary at exit) |
| k6 | ~27k | Grafana line charts |
| locust | ~26k | web UI line charts |
| vegeta | ~25k | post-hoc HTML plot; live only via iTerm2-specific jplot |
| oha | ~10k | animated TUI **bar charts** — "hey with tui animation" is its whole pitch |
| ali | ~3.9k | braille line charts in terminal |
| rlt + ~a dozen small Rust TUI testers | <250 each | charts/gauges, all visually identical |

### Visceral traffic visualization — all GUI, none generate load
| Tool | Status |
| --- | --- |
| Logstalgia (2008) | 1.8k stars, still maintained — replays access logs as a Pong game. Desktop OpenGL. The proof this grammar works. |
| glTail (2008) | abandoned |
| nodestalgia | abandoned 2018, 35 stars |
| sflow-rt/particle | abandoned 2020, 5 stars, browser-only |
| "Logstalgia for the Web" (Show HN 2025) | 2 points, no traction |

### Terminal particle engines — toys with no data source
drift (640 stars), sparks, particle-life-cli, assorted ratatui sand sims — the rendering
technique is proven feasible; none are wired to real data.

## Why this combination, specifically

- **oha hit 10k stars largely on an animated bar chart.** Visual delight is the
  demonstrated differentiator in the load-testing category.
- **Logstalgia has survived 18 years** because watching traffic as physical objects is
  genuinely informative: error bursts, saturation, and tail latency are *legible* in the
  scene. wallop borrows that grammar and adds load generation.
- **Terminal-native dodges every failure mode** that killed the GUI art projects:
  no OpenGL, no browser, runs over SSH, GIFs beautifully, zero setup.
- **The HN record shows the appetite:** ali's thread was full of people wanting free,
  self-hosted, real-time visual load testing; Logstalgia threads keep resurfacing.

## Candidate ideas considered and rejected

| Idea | Why rejected |
| --- | --- |
| Codebase-as-city visualizer | Graveyard. JSCity/GoCity/Codeology all spiked and died; one-shot novelty, no recurring use. |
| Code/git/CI sonification | Genuinely unoccupied, but audio doesn't GIF — every prior attempt died partly because a README can't carry sound. |
| Live Python runtime animation ("watch your program think") | Strong idea, but attach/symbolication is heavy engineering with real platform risk; kept on the someday list. |
| Pure terminal physics playground | Maximum GIF-bait, zero utility — stars would be a coin flip on novelty alone. |
| Database-as-living-city | Open niche but demos poorly (needs the viewer to have an interesting database). |

wallop won on the scorecard because it's the only candidate scoring high on *all five*
axes: novelty (7+), wow (9), usefulness (8 — it's a real load tester), feasibility
(fully buildable now, ~1,300 lines, one dependency), shareability (the demo GIF writes
itself).
