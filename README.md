# mythworld

An **Evennia** prototype where **locations and artifacts remember**. Instead of binary “good/evil” flags or visible reputation meters, player actions leave **memory traces** that **decay at different rates** (personal, group, behavior). The world responds indirectly via **affordances** (navigation friction, encounter bias, spell side-effects, etc.) so consequences feel **mythic and emergent**, not scripted.

LLMs are **not** used for chatty NPCs. They’re optional assistants for **summarizing recent world history** and generating **partial, sometimes-wrong folklore** that helps players infer patterns without exposing mechanics.

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
- Python 3.11+ (3.10 may work, but 3.11+ recommended)
- Evennia installed (Twisted/Django come with it)

### Setup (from repo root)
Put these commands in your terminal **from the repo root**:

```bash
# repo root
python -m venv .venv
source .venv/bin/activate

# repo root
pip install -r requirements.txt

# repo root
evennia migrate
evennia start
Create an admin account (repo root):

bash
Copy code
# repo root
evennia createsuperuser
Connect as a player (your local machine):

bash
Copy code
# in another terminal
telnet localhost 4000
Stop the server (repo root):

bash
Copy code
# repo root
evennia stop
Repo layout (planned / evolving)
docs/spec/
Design doctrine: affinity model, affordances, legibility rules, adversarial play.

config/affinity_defaults.yaml
Default parameters (half-lives, caps, cooldowns, affordance probabilities).

world/affinity/
Memory traces, affinity fields, decay jobs, query APIs.

world/affordances/
“World nudges” that express affinity indirectly.

world/artifacts/
Artifact intent/pressure systems (Ring-like behavior, no dialogue).

world/lore/
Rumors + folklore generation (truthy, incomplete, occasionally wrong).

commands/
Player verbs + admin-only debug/trace commands.

tests/
Unit tests for the affinity engine and key behaviors.

Design constraints (non-negotiable)
No player-visible affinity meters (“Forest affinity: -12” is forbidden).

Affordances must be probabilistic, subtle, and contextual.

LLM output cannot be a root cause of world actions, only a proposal/summary layer.

Every triggered affordance must be explainable via an admin trace.

Admin tools (expected)
@affinity <target>: inspect internal state (admins only)

@trace <last|id>: explain why an affordance triggered (admins only)

@toggleaff <name>: enable/disable an affordance for testing (admins only)

(Exact command names may change; see commands/.)

Roadmap
 Minimal world map (5 rooms) + movement

 Affinity engine: traces + decay + query API

 8–12 affordances (indirect response layer)

 One artifact prototype (bearer-specific pressure)

 Myth layer: rumors + environmental tells (with false lore)

 Optional Discord adapter (treat Discord as another session pipe)

Contributing
This project is opinionated. If you want to add features, align with:

persistence and memory, 2) indirect legibility, 3) admin traceability.

License
TBD
