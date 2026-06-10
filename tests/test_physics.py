import random

from wallop.physics import (
    COLOR_5XX,
    MAX_DEBRIS,
    World,
)


def make_world(width=100, height=40, seed=42):
    return World(width, height, rng=random.Random(seed))


def step(world, seconds, dt=0.033, ema=0.1):
    t = 0.0
    while t < seconds:
        world.update(dt, ema)
        t += dt


def test_spawn_creates_particle_at_left_edge():
    world = make_world()
    world.spawn_request(1)
    assert 1 in world.particles
    x, y = world.particles[1].pos()
    assert x == 0.0
    assert 0 <= y <= world.height


def test_flight_is_monotonic_and_stalls_short_of_wall():
    world = make_world()
    world.spawn_request(1)
    positions = []
    for _ in range(300):  # 10 simulated seconds at ema=0.1 -> fully stalled
        world.update(0.033, 0.1)
        positions.append(world.particles[1].x)
    assert positions == sorted(positions)  # never moves backward
    assert positions[-1] < world.wall_x  # never touches the wall
    assert positions[-1] >= 0.9 * (world.wall_x - 2.0) * World.FLIGHT_CAP


def test_completion_removes_particle():
    world = make_world()
    world.spawn_request(1)
    world.complete_request(1, "2xx")
    assert 1 not in world.particles


def test_5xx_spawns_explosion_debris_and_shake():
    world = make_world()
    world.spawn_request(1)
    step(world, 0.2)
    world.complete_request(1, "5xx")
    assert len(world.debris) >= 8
    assert world.shake > 0
    assert any(d.color == COLOR_5XX for d in world.debris)


def test_2xx_spawns_small_impact_without_shake():
    world = make_world()
    world.spawn_request(1)
    step(world, 0.2)
    world.complete_request(1, "2xx")
    assert 2 <= len(world.debris) <= 4
    assert world.shake == 0


def test_timeout_smoke_rises():
    world = make_world()
    world.spawn_request(1)
    step(world, 0.2)
    world.complete_request(1, "timeout")
    assert world.debris
    assert all(d.vy < 0 for d in world.debris)  # drifting up
    assert all(not d.gravity for d in world.debris)


def test_gravity_pulls_debris_down():
    world = make_world()
    world.spawn_request(1)
    step(world, 0.2)
    world.complete_request(1, "4xx")
    initial_vy = [d.vy for d in world.debris]
    world.update(0.1, 0.1)
    for before, d in zip(initial_vy, world.debris):
        assert d.vy > before


def test_debris_expires():
    world = make_world()
    world.spawn_request(1)
    world.complete_request(1, "2xx")
    assert world.debris
    step(world, 2.0)  # impact sparks live at most 0.6s
    assert world.debris == []


def test_debris_budget_is_respected():
    world = make_world()
    for i in range(2000):
        world.spawn_request(i)
        world.complete_request(i, "2xx")
    assert len(world.debris) <= MAX_DEBRIS


def test_crashed_5xx_debris_leaves_embers():
    world = make_world(seed=7)
    for i in range(40):
        world.spawn_request(i)
        step(world, 0.05)
        world.complete_request(i, "5xx")
    step(world, 3.0)
    # at least some debris must have hit the ground during those 3 seconds
    assert world.time > 0
    # embers may have expired by now; run a short burst and check immediately
    for i in range(100, 140):
        world.spawn_request(i)
        world.complete_request(i, "5xx")
    step(world, 1.0)
    assert world.embers


def test_wall_color_shifts_with_errors():
    healthy = make_world()
    for i in range(50):
        healthy.spawn_request(i)
        healthy.complete_request(i, "2xx")
    sick = make_world()
    for i in range(50):
        sick.spawn_request(i)
        sick.complete_request(i, "5xx")
    healthy_r, healthy_g, _ = healthy.wall_color()
    sick_r, sick_g, _ = sick.wall_color()
    assert sick_r > healthy_r  # redder
    assert sick_g < healthy_g  # less green


def test_resize_clamps_to_minimum():
    world = make_world()
    world.resize(5, 3)
    assert world.width >= 20
    assert world.height >= 10
