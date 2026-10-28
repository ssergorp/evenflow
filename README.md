# mythworld

A prototype Evennia world where locations and artifacts have persistent “affinity” memory, not morality meters. Player actions leave traces, those traces decay over time at different rates (personal vs group vs behavior), and the world responds indirectly by modulating affordances, navigation, encounters, and magic side-effects, so consequences feel mythic and emergent rather than scripted.

LLMs aren’t used for chatty NPCs, they’re used as limited assistants to summarize recent world history and generate partial, sometimes-wrong folklore that helps players infer patterns without ever seeing the underlying mechanics. The end goal is a small playable sandbox that demonstrates “agency without dialogue”: places that remember, objects that pressure, and institutions that drift over long timescales.

An **Evennia** prototype where **locations and artifacts remember**. Instead of binary “good/evil” flags or visible reputation meters, player actions leave **memory traces** that **decay at different rates** (personal, group, behavior). The world responds indirectly via **affordances** (navigation friction, encounter bias, spell side-effects, etc.) so consequences feel **mythic and emergent**, not scripted.

## Status

Early prototype. Expect fast iteration and breaking changes.

## Core ideas

- **Affinity = relationship intelligence**, not “karma”
- **Places remember being hurt**, quietly
- **Artifacts apply pressure**, without dialogue
- **Discovery is indirect** (tells, rumors, drift), not UI meters
- **Admin tracing is mandatory** for tuning (“why did this happen?”)

## Quick start

### Requirements
- Python 3.11+ (Evennia 5 requires it)

### Run the game (from the repo root)

```bash
python -m venv .venv
source .venv/bin/activate        # evennia needs the venv on PATH
pip install -r requirements.txt

evennia migrate
evennia start                    # first start asks for an admin account, then builds the map
```

Connect from another terminal:

```bash
telnet localhost 4000
```

Then `create <name> <password>` and `connect <name> <password>` for a player, or connect as the admin account.

Stop the server with `evennia stop`. Memory is saved in the database, so places still remember after a restart.

### Run the tests (no Evennia needed, Python 3.10+)

```bash
pip install -r requirements-dev.txt
python -m pytest tests/
python -m tests.smoke_validate   # standalone config/affordance check
```

## How to play

New characters start in **Hollowmere**. The starter map:

```
Hollowmere ── east ── Forest Edge ── north ── Whispering Woods ── north ── The Old Grove
                          │                         │
                          └──── east ── Riverbank ──┘ (west)
```

Each place has its own values (`world/locations/*.yaml`). The woods hate fire; the river cares about its water; the village cares about its people.

| Verb | Leaves a memory of |
|------|--------------------|
| `burn` | `harm.fire` |
| `plant` | `create.plant` |
| `offer` | `offer.gift` |
| `hunt` | `extract.hunt` |
| `forage` | `extract.harvest` |
| `rest` | nothing; the place just answers |

Places answer only through narrative tells, and through travel: a place that dislikes you may slow your departure or, if it truly hates you, lead you somewhere you did not mean to go. Places remember **you**, **your kind** (character tags such as `human`, `outsider`), and **what happens here** generally, and forget each at a different speed.

Try it: set a few fires in the Whispering Woods, then walk out. Then leave offerings, or wait.

### Admin commands (Builder and above)

| Command | Does |
|---------|------|
| `@affinity [<character>]` | How this room feels about someone, and the memories behind it |
| `@affinity/age <days>` | Make this room's memories older, to watch it forgive |
| `@affinity/forget` | Wipe this room's memory |
| `@trace [<character>] [= <count>]` | Why recent affordances did or did not trigger |
| `@toggleaff [<affordance> on\|off]` | List affordances, or switch one on or off |

Change a character's group identity with Evennia tags, e.g. `tag me = elf:affinity`.

On a database that predates the map, build it in-game as superuser: `py from world.build import build_world; build_world()`.

## Repo layout

| Path | What |
|------|------|
| `config/affinity_defaults.yaml` | All tuning: half-lives, channel weights, affordance thresholds, probabilities, cooldowns |
| `world/affinity/` | The affinity engine: traces, decay, affinity, affordances. Plain Python, no Evennia |
| `world/bridge.py` | Glue between the engine and the game. Plain Python, tested with pytest |
| `world/locations/` | One YAML file per place: description, values, travel time |
| `world/build.py` | Builds the starter map |
| `typeclasses/` | Evennia rooms that remember, exits that consult them, characters with affinity tags |
| `commands/affinity.py` | Player verbs and admin commands |
| `server/` | Evennia server config |
| `docs/` | Design doctrine: `affinity_spec.md`, `affordances.md`, `DO_NOT.md`, `STATE.md` |
| `tests/` | Engine, bridge and config tests |

Planned: `world/artifacts/` (bearer-specific pressure) and `world/lore/` (rumors and folklore).

## Design constraints (non-negotiable)

- No player-visible affinity meters ("Forest affinity: -12" is forbidden).
- Affordances must be probabilistic, subtle, and contextual.
- LLM output cannot be a root cause of world actions, only a proposal/summary layer.
- Every triggered affordance must be explainable via an admin trace.

See `docs/DO_NOT.md` for the full list.

## Roadmap

- [x] Affinity engine: traces + decay + query API
- [x] 8–12 affordances (indirect response layer)
- [x] Minimal world map (5 rooms) + movement
- [ ] One artifact prototype (bearer-specific pressure)
- [ ] Myth layer: rumors + environmental tells (with false lore)
- [ ] Optional Discord adapter (treat Discord as another session pipe)

## Contributing

This project is opinionated. If you want to add features, align with: 1) persistence and memory, 2) indirect legibility, 3) admin traceability.

## License

TBD
