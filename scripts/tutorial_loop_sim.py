#!/usr/bin/env python3
"""Tutorial loop sim: 1 made guy + clocks + Evenflow.

This is a lightweight, non-Evennia simulation that demonstrates:
- 3 clocks (time/heat/exposure) + progress
- toolbelt actions mapped to 5G-ish stats
- Evenflow event logging -> location memory
- affordance evaluation (movement/pathing tells)

Run:
  source .venv/bin/activate
  python scripts/tutorial_loop_sim.py

Notes:
- This is intentionally simple: it uses the existing Evenflow affinity modules.
- It does not attempt to load a YAML location definition (no loader in repo yet).
"""

from __future__ import annotations

import random
import time
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Set, Tuple, Dict

# Ensure repo root is on sys.path when running as a script
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from world.affinity.core import Location, AffinityEvent
from world.affinity.events import log_event
from world.affinity.computation import compute_affinity, get_threshold_label
from world.affinity.affordances import AffordanceContext, evaluate_affordances, admin_reset_cooldowns
from world.affinity.config import load_config_from_yaml, set_config, reset_config


# ----------------------------
# Model
# ----------------------------

@dataclass
class MadeGuy:
    actor_id: str
    actor_tags: Set[str]
    # 5G-ish stats (0-10)
    grime: int
    game: int
    grift: int
    guns: int
    guile: int


@dataclass
class Clocks:
    progress: int = 0
    heat: int = 0
    exposure: int = 0
    tick: int = 0
    trauma: int = 0


@dataclass
class GridWorld:
    """21x21 physical grid centered on the Circle core."""

    size: int = 21
    # scalar "pressure" per cell; higher => more hostile/warded-feeling
    field: List[List[float]] = None
    # agent position (x,y), 0..size-1
    agent_x: int = 0
    agent_y: int = 0
    # core position (Claire/Circle)
    core_x: int = 0
    core_y: int = 0

    def __post_init__(self) -> None:
        if self.field is None:
            self.field = [[0.0 for _ in range(self.size)] for _ in range(self.size)]
        self.core_x = self.size // 2
        self.core_y = self.size // 2
        # start agent near an edge
        self.agent_x = 1
        self.agent_y = self.size // 2

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.size and 0 <= y < self.size

    def dist_to_core(self) -> int:
        return abs(self.agent_x - self.core_x) + abs(self.agent_y - self.core_y)

    def decay(self, rate: float = 0.92) -> None:
        for y in range(self.size):
            row = self.field[y]
            for x in range(self.size):
                row[x] *= rate

    def add_pressure_disk(self, cx: int, cy: int, radius: int, amount: float) -> None:
        r2 = radius * radius
        for y in range(cy - radius, cy + radius + 1):
            for x in range(cx - radius, cx + radius + 1):
                if not self.in_bounds(x, y):
                    continue
                dx = x - cx
                dy = y - cy
                if dx * dx + dy * dy <= r2:
                    self.field[y][x] += amount

    def step_toward_core(self) -> None:
        """Move one step toward the core (greedy Manhattan)."""
        best = (self.agent_x, self.agent_y)
        best_d = self.dist_to_core()
        for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
            nx, ny = self.agent_x + dx, self.agent_y + dy
            if not self.in_bounds(nx, ny):
                continue
            d = abs(nx - self.core_x) + abs(ny - self.core_y)
            if d < best_d:
                best = (nx, ny)
                best_d = d
        self.agent_x, self.agent_y = best

    def step_away_from_core(self) -> None:
        """Move one step away from the core (greedy Manhattan)."""
        best = (self.agent_x, self.agent_y)
        best_d = self.dist_to_core()
        for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
            nx, ny = self.agent_x + dx, self.agent_y + dy
            if not self.in_bounds(nx, ny):
                continue
            d = abs(nx - self.core_x) + abs(ny - self.core_y)
            if d > best_d:
                best = (nx, ny)
                best_d = d
        self.agent_x, self.agent_y = best

    def cell_pressure(self, x: int, y: int) -> float:
        return self.field[y][x]


def render_grid(world: GridWorld, last_complication: Optional[str] = None) -> str:
    """Render a 21x21 ASCII grid.

    Legend:
      C = Circle core / Claire position
      @ = made guy
      ! = complication marker (on agent cell for this tick)
      . : * # = increasing pressure
    """
    lines: List[str] = []
    for y in range(world.size):
        row_chars: List[str] = []
        for x in range(world.size):
            ch: str
            if x == world.core_x and y == world.core_y:
                ch = "C"
            else:
                p = world.cell_pressure(x, y)
                if p < 0.5:
                    ch = "."
                elif p < 1.5:
                    ch = ":"
                elif p < 3.0:
                    ch = "*"
                else:
                    ch = "#"

            if x == world.agent_x and y == world.agent_y:
                ch = "@"
                if last_complication:
                    ch = "!"

            row_chars.append(ch)
        lines.append("".join(row_chars))
    return "\n".join(lines)


# ----------------------------
# Toolbelt actions
# ----------------------------

ACTIONS = ["BLEND", "PROBE", "PRESS", "ABSORB", "PAYOFF", "CUT_OUT"]


def clamp(x: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, x))


def roll(stat_total: int, rng: random.Random, dc: int = 10) -> bool:
    """Simple roll: stat_total + d10 >= dc+10.

    Keeps results somewhat noisy without being pure RNG.
    """
    return (stat_total + rng.randint(1, 10)) >= (dc + 10)


def intensity_from(low: float, high: float, t: float) -> float:
    t = max(0.0, min(1.0, t))
    return low + (high - low) * t


def log_basic_trespass(location: Location, actor: MadeGuy, now: float, intensity: float) -> None:
    log_event(
        location,
        AffinityEvent(
            event_type="trespass.enter",
            actor_id=actor.actor_id,
            actor_tags=set(actor.actor_tags),
            location_id=location.location_id,
            intensity=float(intensity),
            timestamp=now,
        ),
    )


def log_threat(location: Location, actor: MadeGuy, now: float, intensity: float) -> None:
    log_event(
        location,
        AffinityEvent(
            event_type="social.threaten",
            actor_id=actor.actor_id,
            actor_tags=set(actor.actor_tags),
            location_id=location.location_id,
            intensity=float(intensity),
            timestamp=now,
        ),
    )


# ----------------------------
# Complications
# ----------------------------

COMPLICATIONS = [
    "WRONG_TURN",
    "WATCHED",
    "LOCAL_MUSCLE",
    "WARD_RIPPLE",
]


def pick_complication(clocks: Clocks, threshold: str, rng: random.Random) -> Optional[str]:
    """Procedural complication based on exposure/heat + affinity band."""
    base = 0.15
    base += 0.05 * clocks.exposure
    base += 0.03 * clocks.heat
    if threshold in ("hostile", "unwelcoming"):
        base += 0.15
    if rng.random() > min(0.85, base):
        return None
    # Bias choice a bit
    weights = {
        "WRONG_TURN": 1.0 + (1.0 if clocks.exposure >= 3 else 0.0),
        "WATCHED": 1.0 + (1.0 if clocks.exposure >= 2 else 0.0),
        "LOCAL_MUSCLE": 1.0 + (1.0 if clocks.heat >= 2 else 0.0),
        "WARD_RIPPLE": 0.5 + (1.0 if threshold in ("hostile", "unwelcoming") else 0.0),
    }
    pool: List[Tuple[str, float]] = list(weights.items())
    total = sum(w for _, w in pool)
    r = rng.random() * total
    for k, w in pool:
        r -= w
        if r <= 0:
            return k
    return pool[-1][0]


def apply_complication(comp: str, clocks: Clocks) -> str:
    """Apply complication effects; return a short label."""
    if comp == "WRONG_TURN":
        clocks.tick += 1  # costs time
        clocks.exposure = clamp(clocks.exposure + 1, 0, 6)
        return "Wrong turn: +1 TIME, +1 EXPOSURE"
    if comp == "WATCHED":
        clocks.exposure = clamp(clocks.exposure + 1, 0, 6)
        return "Watched: +1 EXPOSURE"
    if comp == "LOCAL_MUSCLE":
        clocks.heat = clamp(clocks.heat + 1, 0, 6)
        return "Local muscle: +1 HEAT"
    if comp == "WARD_RIPPLE":
        clocks.exposure = clamp(clocks.exposure + 2, 0, 6)
        return "Ward ripple: +2 EXPOSURE"
    return "(unknown complication)"


# ----------------------------
# Simulation
# ----------------------------


def build_circle_location() -> Location:
    """Circle-like location with valuations tuned for tutorial."""
    return Location(
        location_id="circle_5th_amaranth",
        name="The Circle (5th & Amaranth)",
        description="A boundary place. You can feel it noticing you.",
        valuation_profile={
            # strong dislike of threats/coercion
            "social.threaten": -0.9,
            "social": -0.2,
            # dislikes trespass
            "trespass.enter": -0.6,
            "trespass": -0.3,
            # fire/violence is still bad here
            "harm.fire": -0.8,
            "harm": -0.2,
            # magic belongs here, but not necessarily to outsiders
            "magic": 0.1,
        },
    )


def print_state(clocks: Clocks) -> None:
    print(
        f"STATE  progress={clocks.progress}/6  time={clocks.tick}/10  heat={clocks.heat}/6  exposure={clocks.exposure}/6  trauma={clocks.trauma}"
    )


def simulate(seed: int = 42) -> int:
    rng = random.Random(seed)

    config = load_config_from_yaml("config/affinity_defaults.yaml")
    set_config(config)

    actor = MadeGuy(
        actor_id="switch",
        actor_tags={"human", "outsider", "crew"},
        grime=4,
        game=4,
        grift=7,
        guns=3,
        guile=7,
    )

    location = build_circle_location()
    admin_reset_cooldowns(location)

    clocks = Clocks()
    world = GridWorld(size=21)

    print("=" * 72)
    print("TUTORIAL LOOP SIM — 1 made guy / clocks / Evenflow")
    print(f"seed={seed}")
    print("=" * 72)

    # Start by entering the zone
    now = time.time()
    log_basic_trespass(location, actor, now, intensity=0.25)
    # seed pressure around the core (the Circle is "awake" even at baseline)
    world.add_pressure_disk(world.core_x, world.core_y, radius=5, amount=0.15)

    while True:
        # Win/lose checks
        if clocks.progress >= 6:
            print("\nWIN: Progress complete — Claire arrives / meeting achieved.")
            break
        if clocks.tick >= 10:
            print("\nLOSE: Out of time — operation collapses.")
            break
        if clocks.heat >= 6:
            print("\nLOSE: Heat maxed — blown.")
            break
        if clocks.exposure >= 6:
            print("\nLOSE: Exposure maxed — the Circle fully has you.")
            break

        now = time.time()

        # World pulse: compute affinity and apply movement affordance (pathing)
        affinity = compute_affinity(location, actor.actor_id, actor.actor_tags, now=now)
        threshold = get_threshold_label(affinity)

        ctx = AffordanceContext(
            actor_id=actor.actor_id,
            actor_tags=set(actor.actor_tags),
            location=location,
            action_type="move.pass",
            action_target=None,
            timestamp=now,
        )

        outcome = evaluate_affordances(ctx)
        tell = outcome.tells[0] if outcome.tells else None

        # World field decay each tick
        world.decay(rate=0.93)

        # Procedural complication
        comp = pick_complication(clocks, threshold, rng)
        comp_text = None
        if comp:
            comp_text = apply_complication(comp, clocks)

        print("\n--- TICK", clocks.tick + 1, "---")
        print(f"Affinity={affinity:.3f} ({threshold})")
        if tell:
            print("WORLD:", tell)
        if "room.travel_time_modifier" in outcome.adjustments:
            print(
                "MOD: travel_time_modifier=",
                f"{outcome.adjustments['room.travel_time_modifier']:+.3f}",
            )
        if comp_text:
            print("COMPLICATION:", comp_text)

        # Render grid snapshot
        print(render_grid(world, last_complication=comp))

        # Decide action (simple policy): prefer PROBE early, BLEND if heat, CUT_OUT if exposure, else PRESS sometimes
        if clocks.tick <= 1:
            action = "PROBE"
        elif clocks.progress <= 3 and clocks.exposure <= 3 and clocks.heat <= 3 and rng.random() < 0.4:
            action = "PRESS"  # push progress sometimes
        elif clocks.heat >= 4:
            action = "PAYOFF" if rng.random() < 0.6 else "BLEND"
        elif clocks.exposure >= 4:
            action = "CUT_OUT"
        else:
            action = rng.choices(
                population=["BLEND", "PROBE", "PRESS"],
                weights=[0.40, 0.35, 0.25],
                k=1,
            )[0]

        # Movement each tick (physical grid): move toward core until progress is high,
        # then start drifting away (exfiltration).
        if clocks.progress < 5:
            world.step_toward_core()
        else:
            world.step_away_from_core()

        # Standing on "hot" cells increases exposure a bit
        cell_p = world.cell_pressure(world.agent_x, world.agent_y)
        if cell_p > 1.5:
            clocks.exposure = clamp(clocks.exposure + 1, 0, 6)

        print("ACTION:", action)

        # Apply action effects
        if action == "BLEND":
            ok = roll(actor.grift + actor.game, rng, dc=9)
            clocks.heat = clamp(clocks.heat - (1 if ok else 0), 0, 6)
            clocks.progress = clamp(clocks.progress + (1 if ok and rng.random() < 0.4 else 0), 0, 6)
            clocks.tick += 1
            log_basic_trespass(location, actor, now, intensity=0.15)
            # blending cools the local cell a bit
            world.add_pressure_disk(world.agent_x, world.agent_y, radius=1, amount=-0.35)

        elif action == "PROBE":
            ok = roll(actor.guile, rng, dc=9)
            clocks.progress = clamp(clocks.progress + (1 if ok else 0), 0, 6)
            clocks.exposure = clamp(clocks.exposure + 1, 0, 6)
            clocks.tick += 1
            log_basic_trespass(location, actor, now, intensity=0.20)
            # probing stirs the field (you light up wards)
            world.add_pressure_disk(world.agent_x, world.agent_y, radius=2, amount=0.25)
            # simulate "magic.observe" ping from Claire
            log_event(
                location,
                AffinityEvent(
                    event_type="magic.observe",
                    actor_id="claire",
                    actor_tags={"witch"},
                    location_id=location.location_id,
                    intensity=0.7,
                    timestamp=now,
                ),
            )

        elif action == "PRESS":
            ok = roll(actor.guns + actor.grime, rng, dc=11)
            clocks.progress = clamp(clocks.progress + (2 if ok else 1), 0, 6)
            clocks.heat = clamp(clocks.heat + 2, 0, 6)
            clocks.exposure = clamp(clocks.exposure + 1, 0, 6)
            clocks.tick += 1
            log_threat(location, actor, now, intensity=0.65)
            # pressing spikes local hostility
            world.add_pressure_disk(world.agent_x, world.agent_y, radius=3, amount=0.55)

        elif action == "ABSORB":
            clocks.trauma += 1
            clocks.tick += 1

        elif action == "PAYOFF":
            ok = roll(actor.game, rng, dc=10)
            clocks.heat = clamp(clocks.heat - (2 if ok else 1), 0, 6)
            clocks.exposure = clamp(clocks.exposure + 1, 0, 6)
            clocks.tick += 1
            log_event(
                location,
                AffinityEvent(
                    event_type="trade.exploit" if not ok else "trade.fair",
                    actor_id=actor.actor_id,
                    actor_tags=set(actor.actor_tags),
                    location_id=location.location_id,
                    intensity=0.3,
                    timestamp=now,
                ),
            )
            # payoff calms heat locally but makes the place notice you
            world.add_pressure_disk(world.agent_x, world.agent_y, radius=1, amount=-0.15)

        elif action == "CUT_OUT":
            ok = roll(actor.grift, rng, dc=9)
            clocks.exposure = clamp(clocks.exposure - (2 if ok else 1), 0, 6)
            clocks.progress = clamp(clocks.progress - 1, 0, 6)
            clocks.tick += 1
            # cutting out reduces pressure around you
            world.add_pressure_disk(world.agent_x, world.agent_y, radius=2, amount=-0.45)

        else:
            clocks.tick += 1

        print_state(clocks)

    reset_config()
    return 0


if __name__ == "__main__":
    raise SystemExit(simulate())
