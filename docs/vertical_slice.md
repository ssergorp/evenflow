# Vertical Slice: Whispering Woods

The "golden path" implementation. This is the canonical testbed for the affinity system. All new affordances, artifacts, and behaviors should be validated against this slice first.

---

## Scope

| Component | Implementation |
|-----------|----------------|
| **Location** | `whispering_woods` |
| **Events** | `harm.fire`, `offer.gift` |
| **Affordance** | Pathing (travel time modifier) + narrative tells |
| **Counterplay** | `offer.gift` reduces hostility over time |
| **Admin tools** | `affinity/why`, `affinity/replay` |

---

## Implementation Checklist

### Phase 1: Core Data Structures

- [ ] **1.1** Create `TraceRecord` dataclass
  ```python
  @dataclass
  class TraceRecord:
      accumulated: float
      last_updated: float
      event_count: int
      is_scar: bool = False
  ```

- [ ] **1.2** Create `AffinityEvent` dataclass (see `contract_examples.md`)

- [ ] **1.3** Create `Location` class with three-channel trace storage
  - `personal_traces: Dict[Tuple[str, str], TraceRecord]`
  - `group_traces: Dict[Tuple[str, str], TraceRecord]`
  - `behavior_traces: Dict[str, TraceRecord]`
  - `valuation_profile: Dict[str, float]`

- [ ] **1.4** Load `whispering_woods.yaml` into a Location instance

### Phase 2: Event Logging

- [ ] **2.1** Implement `log_event(location, event: AffinityEvent)`
  - Updates personal trace `(actor_id, event_type)`
  - Updates group traces for each `actor_tag`
  - Updates behavior trace `event_type`

- [ ] **2.2** Test: Log `harm.fire` event, verify all three channels updated

- [ ] **2.3** Test: Log `offer.gift` event, verify accumulation

### Phase 3: Decay & Valuation

- [ ] **3.1** Implement `get_decayed_value(trace, half_life_seconds)`
  ```python
  elapsed = current_time() - trace.last_updated
  decay_factor = 0.5 ** (elapsed / half_life_seconds)
  return trace.accumulated * decay_factor
  ```

- [ ] **3.2** Implement `get_valuation(profile, event_type)` with fallback
  - Exact match → category match → 0.0

- [ ] **3.3** Test: Decay math correctness
  - After 1 half-life, value should be 50%
  - After 2 half-lives, value should be 25%

- [ ] **3.4** Test: Valuation fallback
  - `harm.fire` → -0.8 (exact)
  - `harm.poison` → -0.15 (category)
  - `trade.fair` → 0.0 (default)

### Phase 4: Affinity Computation

- [ ] **4.1** Implement `score_personal(traces, actor_id, half_life, profile)`

- [ ] **4.2** Implement `score_group(traces, actor_tags, half_life, profile)`

- [ ] **4.3** Implement `score_behavior(traces, half_life, profile)`

- [ ] **4.4** Implement `compute_affinity(location, actor_id, actor_tags)`
  - Blend channels with weights from config
  - Return `tanh(raw / affinity_scale)`

- [ ] **4.5** Implement `MoodBand` caching (derived, disposable)

- [ ] **4.6** Test: Fire event → negative affinity
  - After `harm.fire` intensity 0.6, affinity should be ≈ -0.35

### Phase 5: Affordance Pipeline

- [ ] **5.1** Create `AffordanceContext` and `AffordanceOutcome` dataclasses

- [ ] **5.2** Implement `evaluate_affordances(ctx) -> AffordanceOutcome`
  1. Compute affinity
  2. Check threshold (-0.7, -0.3, +0.3, +0.7)
  3. Check cooldown
  4. Apply severity clamp
  5. Generate tells
  6. Return outcome

- [ ] **5.3** Implement pathing affordance
  - Handle: `room.travel_time_modifier`
  - Tells from `whispering_woods.yaml`
  - Cooldown: 1 hour
  - Clamp: +50% / -30%

- [ ] **5.4** Implement cooldown tracking
  - Key: `{affordance}:{actor_id}:{location_id}`
  - Store expiry timestamp

- [ ] **5.5** Test: Hostile forest slows traveler
  - After fire, pathing should return +0.35 modifier

### Phase 6: Counterplay

- [ ] **6.1** Verify `offer.gift` creates positive trace
  - Personal: `(actor_id, offer.gift)`
  - Group: `(actor_tags, offer.gift)`
  - Behavior: `offer.gift`

- [ ] **6.2** Test counterplay loop
  - Fire → hostile
  - Gift → less hostile
  - More gifts over time → neutral

- [ ] **6.3** Test abstention
  - Fire → hostile
  - 14 days no events → affinity decays toward 0

### Phase 7: Admin Tools

- [ ] **7.1** Implement `AffordanceTriggerLog` recording

- [ ] **7.2** Implement `AffordanceSnapshot` capture
  - Freeze traces, config, computed results

- [ ] **7.3** Implement `affinity/inspect <location>`
  - Show current affinity toward caller
  - List top contributing traces

- [ ] **7.4** Implement `affinity/why <location> <actor>`
  - Explain channel scores
  - Show top traces per channel

- [ ] **7.5** Implement `affinity/replay <trigger_id>`
  - Load snapshot
  - Recompute from frozen state
  - Compare to logged result

- [ ] **7.6** Test: Replay determinism
  - Capture snapshot
  - Replay
  - Assert identical result

### Phase 8: Integration Tests

- [ ] **8.1** End-to-end: Fire → pathing slow → gift → less slow
  ```python
  def test_fire_gift_cycle():
      loc = load_location("whispering_woods")
      actor = Actor("player_0042", {"human", "hunter"})

      # Fire event
      log_event(loc, AffinityEvent("harm.fire", actor, 0.6))
      assert compute_affinity(loc, actor) < -0.3

      # Check pathing
      ctx = AffordanceContext(actor, loc, "move.pass")
      outcome = evaluate_affordances(ctx)
      assert outcome.adjustments["room.travel_time_modifier"] > 0.3

      # Gift over time
      for _ in range(3):
          log_event(loc, AffinityEvent("offer.gift", actor, 0.5))
          advance_time(days=3)

      # Should be near neutral
      assert -0.1 < compute_affinity(loc, actor) < 0.1
  ```

- [ ] **8.2** Snapshot round-trip test
  ```python
  def test_snapshot_replay():
      # Trigger affordance, capture snapshot
      snapshot = capture_snapshot(trigger_id)

      # Replay from snapshot
      result = replay_from_snapshot(snapshot)

      # Must match exactly
      assert result.computed_affinity == snapshot.computed_affinity
      assert result.threshold_crossed == snapshot.threshold_crossed
  ```

- [ ] **8.3** Decay progression test
  ```python
  def test_decay_over_time():
      loc = load_location("whispering_woods")
      log_event(loc, AffinityEvent("harm.fire", ..., 0.6))

      initial = compute_affinity(loc, actor)
      advance_time(days=7)  # personal half-life
      after_week = compute_affinity(loc, actor)

      # Personal should be ~50% of original contribution
      assert abs(after_week) < abs(initial) * 0.7
  ```

---

## Success Criteria

The vertical slice is complete when:

1. ✅ Fire event creates negative affinity
2. ✅ Pathing affordance slows hostile travelers
3. ✅ Gift counterplay reduces hostility over time
4. ✅ Decay works correctly over time
5. ✅ Admin can explain "why" for any affordance trigger
6. ✅ Replay produces identical results from snapshot
7. ✅ All tests pass

---

## Files Created

```
world/locations/whispering_woods.yaml   # Location definition
tests/test_decay.py                      # Decay math tests
tests/test_valuation.py                  # Valuation fallback tests
tests/test_replay.py                     # Replay determinism tests
tests/test_vertical_slice.py             # End-to-end integration tests
```

---

## Next Steps After Vertical Slice

Once this slice works:

1. Add second location with different valuation profile
2. Add artifact with pressure vectors
3. Add institution affecting both
4. Add second affordance (encounter rate)
5. Add memory compaction
6. Add world tick scheduler

Each addition should be validated against the Whispering Woods testbed before moving to production.
