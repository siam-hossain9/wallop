"""Terminal rendering: a half-block pixel framebuffer plus HUD.

Each terminal cell holds two vertical pixels via '▀'/'▄' with 24-bit
foreground/background colors, doubling vertical resolution. A full
frame is composed into a single string and written in one syscall.
"""

from __future__ import annotations

import os
import shutil
import sys

from .physics import Color, World, CLASS_COLORS, COLOR_2XX, COLOR_4XX, COLOR_5XX, COLOR_FLIGHT, COLOR_TIMEOUT, dim
from .stats import StatsSnapshot, fmt_duration, fmt_latency

ESC = "\x1b"
RESET = f"{ESC}[0m"
UPPER = "▀"
LOWER = "▄"
SPARK_CHARS = " ▁▂▃▄▅▆▇█"

HUD_TOP_ROWS = 1
HUD_BOTTOM_ROWS = 3


def _fg(c: Color) -> str:
    return f"{ESC}[38;2;{c[0]};{c[1]};{c[2]}m"


def _bg(c: Color) -> str:
    return f"{ESC}[48;2;{c[0]};{c[1]};{c[2]}m"


class FrameBuffer:
    """w_cells x h_cells terminal cells = w_cells x (2 * h_cells) pixels."""

    def __init__(self, w_cells: int, h_cells: int) -> None:
        self.w = w_cells
        self.h = h_cells
        self.pw = w_cells
        self.ph = h_cells * 2
        self.pixels: list[list[Color | None]] = [
            [None] * self.pw for _ in range(self.ph)
        ]

    def set_pixel(self, x: int, y: int, color: Color) -> None:
        if 0 <= x < self.pw and 0 <= y < self.ph:
            self.pixels[y][x] = color

    def cell(self, cx: int, cy: int) -> tuple[str, Color | None, Color | None]:
        """Return (char, fg, bg) for a terminal cell."""
        upper = self.pixels[cy * 2][cx]
        lower = self.pixels[cy * 2 + 1][cx]
        if upper is None and lower is None:
            return " ", None, None
        if upper is not None and lower is None:
            return UPPER, upper, None
        if upper is None and lower is not None:
            return LOWER, lower, None
        return UPPER, upper, lower

    def to_ansi_rows(self) -> list[str]:
        rows = []
        for cy in range(self.h):
            parts: list[str] = []
            cur_fg: Color | None = None
            cur_bg: Color | None = None
            dirty = True  # force initial reset
            for cx in range(self.w):
                ch, fg, bg = self.cell(cx, cy)
                if dirty or fg != cur_fg or bg != cur_bg:
                    parts.append(RESET)
                    if fg is not None:
                        parts.append(_fg(fg))
                    if bg is not None:
                        parts.append(_bg(bg))
                    cur_fg, cur_bg = fg, bg
                    dirty = False
                parts.append(ch)
            parts.append(RESET)
            rows.append("".join(parts))
        return rows


def draw_world(world: World, fb: FrameBuffer, shake_x: int = 0) -> None:
    """Rasterize the world into the framebuffer."""
    wall_px = int(world.wall_x)
    wall_color = world.wall_color()
    for y in range(fb.ph):
        fb.set_pixel(wall_px + shake_x, y, wall_color)
        fb.set_pixel(wall_px + 1 + shake_x, y, dim(wall_color, 0.45))

    for e in world.embers:
        fade = 1.0 - e.age / e.ttl
        fb.set_pixel(int(e.x) + shake_x, world.ground_y, dim(COLOR_5XX, 0.25 + 0.6 * fade))

    for d in world.debris:
        fade = max(0.15, 1.0 - d.age / d.ttl)
        fb.set_pixel(int(d.x) + shake_x, int(d.y), dim(d.color, fade))

    for p in world.particles.values():
        for i, (tx, ty) in enumerate(p.trail[:-1]):
            fade = 0.12 + 0.10 * i
            fb.set_pixel(int(tx) + shake_x, int(ty), dim(COLOR_FLIGHT, fade * p.jitter))
        x, y = p.pos()
        fb.set_pixel(int(x) + shake_x, int(y), dim(COLOR_FLIGHT, p.jitter))


def sparkline(values: list[float], width: int) -> str:
    if not values:
        return " " * width
    values = values[-width:]
    peak = max(values) or 1.0
    chars = []
    for v in values:
        idx = round(v / peak * (len(SPARK_CHARS) - 1))
        chars.append(SPARK_CHARS[idx])
    return "".join(chars).rjust(width)


def _pad(text: str, width: int) -> str:
    return text[:width].ljust(width)


def hud_lines(snapshot: StatsSnapshot, target: str, width: int) -> tuple[str, list[str]]:
    """Returns (top line, bottom lines), each already colored + padded."""
    title = f" wallop ▸ {target} "
    elapsed = f" {fmt_duration(snapshot.elapsed)} "
    gap = max(1, width - len(title) - len(elapsed))
    top = (
        f"{_fg((189, 147, 249))}{title}{RESET}"
        + " " * gap
        + f"{_fg((98, 114, 164))}{elapsed}{RESET}"
    )

    cc = snapshot.class_counts
    line1 = (
        f" {_fg((241, 250, 140))}{snapshot.rps:8,.0f} req/s{RESET}   "
        f"p50 {fmt_latency(snapshot.p50):>7}  "
        f"p95 {fmt_latency(snapshot.p95):>7}  "
        f"p99 {fmt_latency(snapshot.p99):>7}   "
        f"in-flight {snapshot.in_flight:<5d}"
    )
    line2 = (
        f" {_fg(COLOR_2XX)}2xx {cc.get('2xx', 0):,}{RESET}  "
        f"{_fg(CLASS_COLORS['3xx'])}3xx {cc.get('3xx', 0):,}{RESET}  "
        f"{_fg(COLOR_4XX)}4xx {cc.get('4xx', 0):,}{RESET}  "
        f"{_fg(COLOR_5XX)}5xx {cc.get('5xx', 0):,}{RESET}  "
        f"{_fg(COLOR_TIMEOUT)}timeout {cc.get('timeout', 0):,}  "
        f"net-err {cc.get('error', 0):,}{RESET}  "
        f"errors {snapshot.error_rate * 100:.1f}%"
    )
    spark_width = max(10, width - 12)
    line3 = (
        f" {_fg((98, 114, 164))}{sparkline(snapshot.rps_history, spark_width)}{RESET}"
        f"  {_fg((98, 114, 164))}q quit{RESET}"
    )
    return top, [line1, line2, line3]


class Screen:
    """Owns the terminal: alt buffer, cursor, VT mode, frame writes."""

    def __init__(self, stream=None) -> None:
        self.stream = stream if stream is not None else sys.stdout
        self._active = False
        self._saved_termios = None

    @staticmethod
    def term_size() -> tuple[int, int]:
        size = shutil.get_terminal_size(fallback=(100, 30))
        return size.columns, size.lines

    def enter(self) -> None:
        if os.name == "nt":
            self._enable_windows_vt()
        elif sys.stdin.isatty():
            # cbreak so single keypresses (q) arrive without Enter
            import termios
            import tty

            self._saved_termios = termios.tcgetattr(sys.stdin.fileno())
            tty.setcbreak(sys.stdin.fileno())
        # alt buffer, hide cursor, disable autowrap, clear
        self.stream.write(f"{ESC}[?1049h{ESC}[?25l{ESC}[?7l{ESC}[2J")
        self.stream.flush()
        self._active = True

    def exit(self) -> None:
        if not self._active:
            return
        if self._saved_termios is not None:
            import termios

            termios.tcsetattr(
                sys.stdin.fileno(), termios.TCSADRAIN, self._saved_termios
            )
            self._saved_termios = None
        self.stream.write(f"{RESET}{ESC}[?7h{ESC}[?25h{ESC}[?1049l")
        self.stream.flush()
        self._active = False

    def draw_frame(self, fb: FrameBuffer, snapshot: StatsSnapshot, target: str) -> None:
        width = fb.w
        top, bottom = hud_lines(snapshot, target, width)
        rows = [top] + fb.to_ansi_rows() + bottom
        # home the cursor, then explicitly position each row to avoid scroll
        out = []
        for i, row in enumerate(rows):
            out.append(f"{ESC}[{i + 1};1H{ESC}[2K{row}")
        self.stream.write("".join(out))
        self.stream.flush()

    @staticmethod
    def _enable_windows_vt() -> None:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
