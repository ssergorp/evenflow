# DO NOT

**For CI reviewers and code contributors.**

These are hard violations. If a PR contains any of these, it must be rejected.

---

## 1. No Global EVENT_WEIGHTS

```python
# ❌ WRONG: Global valuation table
EVENT_WEIGHTS = {
    "harm.fire": -0.8,
    "offer.gift": +0.5,
}

# ✅ RIGHT: Valuation lives in each entity
forest.valuation_profile = {"harm.fire": -0.8}
town.valuation_profile = {"harm.fire": -0.2}  # different place, different values
```

**Why:** Global weights encode universal morality. The whole point is that meaning emerges from place-specific values.

---

## 2. No Player-Visible Meters, Ever

```python
# ❌ WRONG: Any of these
player.show("Affinity: -0.35")
player.show("The forest's hostility: ████░░░░ 40%")
player.show("[Forest reputation: Unwelcoming]")

# ✅ RIGHT: Narrative tells only
player.show("The path seems to twist away from you.")
player.show("Branches catch at your pack.")
```

**Why:** Meters invite gaming. Players should infer relationships through patterns, not read dashboards.

---

## 3. No Affordance Touching >2 Handles

```python
# ❌ WRONG: Affordance modifies 4 variables
outcome.adjustments = {
    "room.travel_time_modifier": 0.3,
    "actor.stamina_modifier": -0.1,
    "spell.power_modifier": -0.2,
    "npc.disposition_modifier": -0.15,
}

# ✅ RIGHT: Max 2 handles per affordance
outcome.adjustments = {
    "room.travel_time_modifier": 0.3,
}
```

**Why:** Complexity explodes. Two handles is enough for meaningful effect. More makes debugging impossible.

---

## 4. No Invented Stats System

```python
# ❌ WRONG: Invented to satisfy an affordance
class Actor:
    motivation: float      # didn't exist before
    luck: float            # didn't exist before
    cosmic_alignment: float  # what even is this

# ✅ RIGHT: Use existing game variables or mark "flavor only"
# If you need a new stat, that's a game design decision
# requiring its own spec—not something slipped in via affordance
```

**Why:** Affordances should modulate existing systems, not invent new ones. If an affordance needs a handle that doesn't exist, the affordance is "flavor only" until game design adds the stat.

---

## 5. No "Forest Says..." Dialogue

```python
# ❌ WRONG: Entity speaks
player.show("The forest whispers: 'You are not welcome here.'")
player.show("The ring urges you to keep it.")
player.show("The ancient oak says: 'Remember what you did.'")

# ✅ RIGHT: Entity acts, player infers
player.show("The shadows seem deeper here.")
player.show("Your fingers tighten around the ring unbidden.")
player.show("The oak's branches creak, though there is no wind.")
```

**Why:** Dialogue implies consciousness. These entities have *memory* and *bias*, not minds. They filter outcomes, not converse.

---

## 6. No Non-Deterministic Replay

```python
# ❌ WRONG: Replay uses current state or random
def replay(trigger_id):
    snapshot = load_snapshot(trigger_id)
    # Uses current traces, not frozen ones
    result = compute_affinity(current_location, snapshot.actor_id)
    return result

# ✅ RIGHT: Replay uses only snapshot data
def replay(trigger_id):
    snapshot = load_snapshot(trigger_id)
    result = compute_affinity_from_snapshot(
        snapshot.personal_traces,
        snapshot.group_traces,
        snapshot.behavior_traces,
        snapshot.valuation_profile,
        snapshot.half_lives,
        snapshot.channel_weights,
        snapshot.random_seed,  # if stochastic
    )
    assert result == snapshot.computed_affinity  # must match exactly
    return result
```

**Why:** If replay doesn't produce identical results, debugging is guesswork. Snapshot = frozen state = deterministic verification.

---

## Quick Reference

| Rule | One-liner |
|------|-----------|
| No global EVENT_WEIGHTS | Valuation is per-entity, not universal |
| No player-visible meters | Tells only, no numbers |
| No >2 handles per affordance | Keep it simple, keep it debuggable |
| No invented stats | Use existing game vars or "flavor only" |
| No entity dialogue | Entities act, they don't speak |
| No non-deterministic replay | Snapshot in = identical result out |

---

## How to Enforce

1. **Grep for violations** in CI:
   ```bash
   # Global weights
   grep -r "EVENT_WEIGHTS" --include="*.py" && exit 1

   # Player-visible numbers
   grep -rE "Affinity:|reputation:|hostility:" --include="*.py" && exit 1

   # Entity dialogue
   grep -rE "(forest|ring|artifact|location)\s+(says|whispers|urges|speaks)" --include="*.py" && exit 1
   ```

2. **Review checklist** for PRs:
   - [ ] No global valuation tables
   - [ ] No meters/numbers in player output
   - [ ] Each affordance touches ≤2 handles
   - [ ] No new stats invented
   - [ ] No entity dialogue
   - [ ] Replay tests use frozen snapshots

---

*If you're not sure, ask. If you're sure it's fine, ask anyway.*
