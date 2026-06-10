# Launch posts

## Show HN (also works for X/Twitter with the first two paragraphs)

**Title:** Show HN: Wallop – load testing where every HTTP request is a particle

I got tired of staring at p99 line charts while load testing, so I built wallop:
a terminal load tester where every request is a physical particle. Requests fly
across your terminal and hit a wall that represents your server. Latency is
literally flight time — when your service slows down, you watch particles stall
mid-air and pile up. 404s ricochet off in orange arcs. 500s explode with debris
and screen shake. Timeouts never arrive; they dissolve into smoke. The wall
itself shifts from green to red as the error rate climbs.

It's still a real load tester underneath: live RPS, p50/p95/p99, status-code
counts, a rate limiter, and a vegeta-style summary at exit. The physics never
lies about the data — effects are sampled under load, counters never are.

Try it in one command (it ships with a built-in chaos server that walks through
a scripted incident — healthy, latency creep, error storm, meltdown, recovery):

    uv tool install wallop && wallop demo

The lineage, for the curious: Logstalgia (2008) proved that watching traffic as
physical objects is genuinely informative, but it's a desktop OpenGL app that
replays access logs. Every terminal load tester since (oha, ali, and friends)
renders charts. As far as I can tell, nobody had put load generation, request
physics, and terminal rendering in the same tool — so that's what this is.

Python, one dependency (aiohttp), MIT. Honest limits: it'll comfortably drive a
few thousand req/s per core; if you need to saturate a 10 Gbps NIC, use wrk and
come back to wallop to understand what broke. Roadmap includes a --replay mode
to pipe in production access logs and watch real traffic instead of generated
load.

Repo: https://github.com/siam-hossain9/wallop

---

## LinkedIn

The most dramatic data in software engineering is a server being pushed past
its limits. And we've all agreed to render it as... line charts.

This weekend I shipped wallop, an open-source load tester that works
differently: every HTTP request is a particle flying across your terminal.

→ Latency is flight time. When your API slows down, you don't read it on an
axis — you watch requests hang mid-air and pile up in front of the server.
→ 404s ricochet. 500s explode, shake the screen, and leave embers smoldering
on the ground.
→ The server wall glows green when healthy and burns red as errors mount.
→ And it's still a real tool: live p50/p95/p99, RPS, rate limiting, and a
clean summary report when you're done.

The part I'm most proud of: the visualization isn't decoration. In every demo
I've run, people spot the incident — the latency creep, the error storm, the
recovery — *before* they look at the numbers. It turns out humans are very
good at reading physics and very bad at reading the y-axis.

One command to try it (includes a built-in chaos server, so you don't need a
target):

uv tool install wallop && wallop demo

Terminal-native, runs over SSH, ~1,300 lines of Python, one dependency, MIT
licensed. Link in the comments — and if you break it, the issues tab is open.

#opensource #devtools #loadtesting #python #sre

---

## X / Twitter (short version)

load testing tools give you line charts.

wallop gives you physics: every request is a particle. latency = flight time.
404s ricochet, 500s explode, timeouts turn to smoke.

still a real load tester underneath (p50/p95/p99, RPS, rate limits).

one command: uv tool install wallop && wallop demo

[attach demo GIF]
