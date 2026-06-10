"""The particle world.

Coordinates are in *pixels*: the playfield is `width` columns wide and
`height` pixels tall, where one terminal cell holds two vertical pixels
(rendered with half-block characters). x grows rightward, y grows
downward. Requests fly from the left edge toward the server wall on the
right; what happens when they arrive depends on the HTTP status.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

Color = tuple[int, int, int]

# Dracula-ish palette
COLOR_2XX: Color = (80, 250, 123)
COLOR_3XX: Color = (139, 233, 253)
COLOR_4XX: Color = (255, 184, 108)
COLOR_5XX: Color = (255, 85, 85)
COLOR_TIMEOUT: Color = (130, 130, 145)
COLOR_FLIGHT: Color = (241, 250, 140)

GRAVITY = 38.0  # px / s^2
MAX_DEBRIS = 700

CLASS_COLORS: dict[str, Color] = {
    "2xx": COLOR_2XX,
    "3xx": COLOR_3XX,
    "4xx": COLOR_4XX,
    "5xx": COLOR_5XX,
    "timeout": COLOR_TIMEOUT,
    "error": COLOR_5XX,
}


def dim(color: Color, factor: float) -> Color:
    return (int(color[0] * factor), int(color[1] * factor), int(color[2] * factor))


@dataclass
class Particle:
    """An in-flight request."""

    id: int
    lane: float  # base y
    born: float  # world time at spawn
    phase: float
    amplitude: float
    wavelength: float
    jitter: float  # per-particle brightness variance
    x: float = 0.0
    trail: list[tuple[float, float]] = field(default_factory=list)

    def pos(self) -> tuple[float, float]:
        return self.x, self.lane + self.amplitude * math.sin(
            2 * math.pi * self.x / self.wavelength + self.phase
        )


@dataclass
class Debris:
    x: float
    y: float
    vx: float
    vy: float
    color: Color
    ttl: float
    gravity: bool = True
    age: float = 0.0

    @property
    def alive(self) -> bool:
        return self.age < self.ttl


@dataclass
class Ember:
    """Glow left on the ground by crashed 5xx debris."""

    x: float
    ttl: float
    age: float = 0.0

    @property
    def alive(self) -> bool:
        return self.age < self.ttl


class World:
    """Owns every moving thing and steps the simulation."""

    # in-flight progress: 1 - exp(-elapsed / (k * ema)), capped so slow
    # requests visibly stall just short of the wall
    FLIGHT_K = 0.8
    FLIGHT_CAP = 0.96

    def __init__(self, width: int, height: int, rng: random.Random | None = None) -> None:
        self.width = max(20, width)
        self.height = max(10, height)
        self.rng = rng or random.Random()
        self.time = 0.0
        self.particles: dict[int, Particle] = {}
        self.debris: list[Debris] = []
        self.embers: list[Ember] = []
        self.shake = 0.0
        self.wall_pulse = 0.0
        self.recent_classes: list[str] = []  # last N outcomes, for wall mood
        self.latency_ema = 0.3

    # -- geometry --------------------------------------------------------

    @property
    def wall_x(self) -> float:
        return self.width - 2.0

    @property
    def ground_y(self) -> int:
        return self.height - 1

    def resize(self, width: int, height: int) -> None:
        self.width = max(20, width)
        self.height = max(10, height)

    # -- request lifecycle ------------------------------------------------

    def spawn_request(self, request_id: int) -> None:
        margin = max(1.0, self.height * 0.12)
        self.particles[request_id] = Particle(
            id=request_id,
            lane=self.rng.uniform(margin, self.height - margin - 2),
            born=self.time,
            phase=self.rng.uniform(0, 2 * math.pi),
            amplitude=self.rng.uniform(0.4, 1.6),
            wavelength=self.rng.uniform(14, 30),
            jitter=self.rng.uniform(0.75, 1.0),
        )

    def complete_request(self, request_id: int, status_class: str) -> None:
        particle = self.particles.pop(request_id, None)
        self.recent_classes.append(status_class)
        if len(self.recent_classes) > 80:
            self.recent_classes = self.recent_classes[-80:]
        self.wall_pulse = min(1.0, self.wall_pulse + 0.15)
        if particle is None:
            return
        _, y = particle.pos()
        y = min(max(y, 1.0), self.height - 2.0)
        if status_class in ("timeout", "error"):
            # never reached the wall: dissolve into rising smoke mid-air
            self._spawn_smoke(particle.x, y)
        elif status_class == "5xx":
            self._spawn_explosion(self.wall_x - 1, y)
            self.shake = min(2.5, self.shake + 0.9)
        elif status_class == "4xx":
            self._spawn_ricochet(self.wall_x - 1, y)
        else:
            self._spawn_impact(self.wall_x - 1, y, CLASS_COLORS[status_class])

    # -- effect spawners ---------------------------------------------------

    def _budget(self, wanted: int, priority: bool = False) -> int:
        room = MAX_DEBRIS - len(self.debris)
        if priority:
            return max(0, min(wanted, room + wanted // 2))
        return max(0, min(wanted, room))

    def _spawn_impact(self, x: float, y: float, color: Color) -> None:
        for _ in range(self._budget(self.rng.randint(2, 4))):
            self.debris.append(
                Debris(
                    x=x,
                    y=y,
                    vx=self.rng.uniform(-14, -4),
                    vy=self.rng.uniform(-7, 7),
                    color=color,
                    ttl=self.rng.uniform(0.25, 0.6),
                    gravity=False,
                )
            )

    def _spawn_ricochet(self, x: float, y: float) -> None:
        for _ in range(self._budget(self.rng.randint(3, 5))):
            self.debris.append(
                Debris(
                    x=x,
                    y=y,
                    vx=self.rng.uniform(-26, -10),
                    vy=self.rng.uniform(-16, -4),
                    color=COLOR_4XX,
                    ttl=self.rng.uniform(0.7, 1.4),
                    gravity=True,
                )
            )

    def _spawn_explosion(self, x: float, y: float) -> None:
        for _ in range(self._budget(self.rng.randint(8, 14), priority=True)):
            angle = self.rng.uniform(math.pi * 0.6, math.pi * 1.4)  # leftward arc
            speed = self.rng.uniform(8, 30)
            self.debris.append(
                Debris(
                    x=x,
                    y=y,
                    vx=math.cos(angle) * speed,
                    vy=math.sin(angle) * speed,
                    color=COLOR_5XX if self.rng.random() < 0.7 else (255, 160, 90),
                    ttl=self.rng.uniform(0.8, 1.8),
                    gravity=True,
                )
            )

    def _spawn_smoke(self, x: float, y: float) -> None:
        for _ in range(self._budget(self.rng.randint(3, 5))):
            self.debris.append(
                Debris(
                    x=x,
                    y=y,
                    vx=self.rng.uniform(-2, 2),
                    vy=self.rng.uniform(-9, -3),
                    color=COLOR_TIMEOUT,
                    ttl=self.rng.uniform(0.6, 1.2),
                    gravity=False,
                )
            )

    # -- simulation ---------------------------------------------------------

    def update(self, dt: float, latency_ema: float) -> None:
        self.time += dt
        self.latency_ema = max(1e-3, latency_ema)
        flight_span = self.wall_x - 2.0

        for particle in self.particles.values():
            elapsed = self.time - particle.born
            frac = 1.0 - math.exp(-elapsed / (self.FLIGHT_K * self.latency_ema))
            particle.x = min(frac, self.FLIGHT_CAP) * flight_span
            particle.trail.append(particle.pos())
            if len(particle.trail) > 5:
                particle.trail.pop(0)

        survivors: list[Debris] = []
        for d in self.debris:
            d.age += dt
            if not d.alive:
                continue
            if d.gravity:
                d.vy += GRAVITY * dt
            d.x += d.vx * dt
            d.y += d.vy * dt
            if d.x < 0 or d.x >= self.width:
                continue
            if d.y >= self.ground_y:
                if d.gravity and d.color == COLOR_5XX:
                    self.embers.append(Ember(x=d.x, ttl=self.rng.uniform(1.5, 3.5)))
                continue
            if d.y < 0:
                continue
            survivors.append(d)
        self.debris = survivors

        for ember in self.embers:
            ember.age += dt
        self.embers = [e for e in self.embers if e.alive]
        if len(self.embers) > 200:
            self.embers = self.embers[-200:]

        self.shake *= math.exp(-6.0 * dt)
        if self.shake < 0.02:
            self.shake = 0.0
        self.wall_pulse *= math.exp(-4.0 * dt)

    # -- wall mood ------------------------------------------------------------

    def wall_color(self) -> Color:
        """Green when healthy, shifting to red as recent errors mount."""
        if not self.recent_classes:
            base = COLOR_2XX
        else:
            bad = sum(1 for c in self.recent_classes if c in ("5xx", "error", "timeout"))
            ratio = bad / len(self.recent_classes)
            base = (
                int(80 + (255 - 80) * ratio),
                int(250 - (250 - 85) * ratio),
                int(123 - (123 - 85) * ratio),
            )
        brightness = 0.55 + 0.45 * self.wall_pulse
        return dim(base, min(1.0, brightness))
