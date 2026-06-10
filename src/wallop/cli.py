"""Command-line interface.

    wallop https://api.example.com -c 100 -d 30s
    wallop demo
    wallop serve --port 8080
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys

from . import __version__
from .app import App, print_summary
from .engine import LoadEngine


def parse_duration(text: str) -> float:
    match = re.fullmatch(r"(\d+(?:\.\d+)?)(ms|s|m|h)?", text.strip())
    if not match:
        raise argparse.ArgumentTypeError(
            f"invalid duration {text!r} (try 30s, 90, 2m, 500ms)"
        )
    value = float(match.group(1))
    unit = match.group(2) or "s"
    return value * {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}[unit]


def parse_header(text: str) -> tuple[str, str]:
    if ":" not in text:
        raise argparse.ArgumentTypeError(f"invalid header {text!r} (want 'Name: value')")
    name, _, value = text.partition(":")
    return name.strip(), value.strip()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wallop",
        description="HTTP load testing you can feel. "
        "Every request is a particle; watch your server take the hit.",
    )
    parser.add_argument("--version", action="version", version=f"wallop {__version__}")
    sub = parser.add_subparsers(dest="command")

    run = sub.add_parser("run", help="hammer a URL (default command)")
    _add_run_args(run, require_url=True)

    demo = sub.add_parser(
        "demo", help="spin up a built-in chaos server and hammer it"
    )
    _add_run_args(demo, require_url=False)
    demo.add_argument(
        "--port", type=int, default=0, help="port for the chaos server (default: random)"
    )

    serve = sub.add_parser("serve", help="run only the chaos server, for manual testing")
    serve.add_argument("--port", type=int, default=8089)
    return parser


def _add_run_args(parser: argparse.ArgumentParser, require_url: bool) -> None:
    if require_url:
        parser.add_argument("url", help="target URL")
    parser.add_argument(
        "-c", "--concurrency", type=int, default=50, help="concurrent workers (default 50)"
    )
    parser.add_argument(
        "-d", "--duration", type=parse_duration, default=None,
        help="how long to run, e.g. 30s, 2m (default: until q / Ctrl+C)",
    )
    parser.add_argument(
        "-n", "--requests", type=int, default=None, help="stop after N total requests"
    )
    parser.add_argument(
        "-r", "--rate", type=float, default=None, help="cap request rate (req/s)"
    )
    parser.add_argument("-m", "--method", default="GET", help="HTTP method (default GET)")
    parser.add_argument(
        "-H", "--header", action="append", type=parse_header, default=[],
        metavar="'Name: value'", help="request header (repeatable)",
    )
    parser.add_argument("-b", "--body", default=None, help="request body (or @file)")
    parser.add_argument(
        "-t", "--timeout", type=float, default=10.0, help="per-request timeout seconds"
    )
    parser.add_argument(
        "-k", "--insecure", action="store_true", help="skip TLS certificate verification"
    )
    parser.add_argument(
        "--fps", type=int, default=30, help="render frame rate (default 30)"
    )


def _read_body(spec: str | None) -> bytes | None:
    if spec is None:
        return None
    if spec.startswith("@"):
        with open(spec[1:], "rb") as f:
            return f.read()
    return spec.encode()


def _build_engine(args: argparse.Namespace, url: str) -> LoadEngine:
    return LoadEngine(
        url,
        concurrency=args.concurrency,
        rate=args.rate,
        total=args.requests,
        duration=args.duration,
        method=args.method,
        headers=dict(args.header),
        body=_read_body(args.body),
        timeout=args.timeout,
        insecure=args.insecure,
    )


async def _run(args: argparse.Namespace) -> None:
    engine = _build_engine(args, args.url)
    app = App(engine, target_label=args.url, fps=args.fps)
    summary = await app.run()
    print_summary(summary, args.url)


async def _demo(args: argparse.Namespace) -> None:
    from .demoserver import start_server

    runner, port = await start_server(args.port)
    url = f"http://127.0.0.1:{port}/"
    # demo defaults tuned so every effect is visible without drowning the screen
    if args.duration is None and args.requests is None:
        args.duration = 45.0
    args.timeout = min(args.timeout, 2.0)
    engine = _build_engine(args, url)
    app = App(engine, target_label=f"{url} (built-in chaos server)", fps=args.fps)
    try:
        summary = await app.run()
    finally:
        await runner.cleanup()
    print_summary(summary, f"{url} (built-in chaos server)")


async def _serve(args: argparse.Namespace) -> None:
    from .demoserver import start_server

    runner, port = await start_server(args.port)
    print(f"chaos server listening on http://127.0.0.1:{port}/  (Ctrl+C to stop)")
    print("phases: healthy -> latency creep -> error storm -> meltdown -> recovery")
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()


def main(argv: list[str] | None = None) -> int:
    # the renderer emits ▀/▄; make sure stdout can encode them even when
    # redirected on Windows (where the default is a legacy codepage)
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (ValueError, OSError):
            pass
    argv = list(sys.argv[1:] if argv is None else argv)
    # allow `wallop URL` without the explicit `run` subcommand
    if argv and argv[0] not in ("run", "demo", "serve", "-h", "--help", "--version"):
        argv.insert(0, "run")
    args = build_parser().parse_args(argv)

    if args.command is None:
        build_parser().print_help()
        return 2

    handler = {"run": _run, "demo": _demo, "serve": _serve}[args.command]
    try:
        asyncio.run(handler(args))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
