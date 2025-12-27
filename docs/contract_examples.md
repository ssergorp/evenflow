# Contract Examples

Reference shapes for code generation. These are the canonical examples; implementations should match these structures exactly.

---

## 1. AffinityEvent

### Example: Forest Fire

```json
{
  "event_type": "harm.fire",
  "actor_id": "player_0042",
  "actor_tags": ["human", "hunter", "outsider"],
  "target_id": null,
  "location_id": "whispering_woods",
  "intensity": 0.6,
  "timestamp": 1703520000.0,
  "context_tags": ["violent", "mundane"]
}
```

### Example: Offering to Forest

```json
{
  "event_type": "offer.gift",
  "actor_id": "player_0042",
  "actor_tags": ["human", "hunter", "outsider"],
  "target_id": "ancient_oak",
  "location_id": "whispering_woods",
  "intensity": 0.5,
  "timestamp": 1703606400.0,
  "context_tags": ["peaceful", "ritual"]
}
```

### Example: Artifact Pressure Trigger

```json
{
  "event_type": "magic.bind",
  "actor_id": "player_0099",
  "actor_tags": ["elf", "mage"],
  "target_id": "spirit_entity",
  "location_id": "ruined_tower",
  "intensity": 0.7,
  "timestamp": 1703692800.0,
  "context_tags": ["ritual", "forbidden"]
}
```

---

## 2. AffordanceContext

### Example: Player Moving Through Hostile Forest

```json
{
  "actor_id": "player_0042",
  "actor_tags": ["human", "hunter", "outsider"],
  "location": {
    "location_id": "whispering_woods",
    "valuation_profile": {
      "harm": -0.2,
      "harm.fire": -0.8,
      "extract": -0.2,
      "extract.hunt": -0.4,
      "offer": 0.4,
      "offer.gift": 0.5
    }
  },
  "action_type": "move.pass",
  "action_target": "forest_clearing",
  "timestamp": 1703779200.0
}
```

### Example: Artifact Bearer Taking Action

```json
{
  "actor_id": "player_0099",
  "actor_tags": ["elf", "mage"],
  "location": {
    "artifact_id": "ring_of_binding",
    "origin_tags": ["old_kingdom", "shadow"],
    "valuation_profile": {
      "magic.bind": 0.6,
      "magic.dispel": -0.5,
      "offer.sacrifice": 0.4
    }
  },
  "action_type": "magic.dispel",
  "action_target": "ward_entity",
  "timestamp": 1703865600.0
}
```

---

## 3. AffordanceOutcome

### Example: Forest Slows Hostile Traveler

```json
{
  "adjustments": {
    "room.travel_time_modifier": 0.35
  },
  "tells": [
    "The path seems to twist away from you.",
    "Branches catch at your pack."
  ],
  "trace": {
    "timestamp": 1703779200.0,
    "location_id": "whispering_woods",
    "actor_id": "player_0042",
    "affordance_type": "pathing",
    "effect_applied": "slow",
    "severity": 0.35,
    "contributing_traces": [
      {
        "channel": "personal",
        "trace_key": "(player_0042, harm.fire)",
        "decayed_value": 0.42,
        "valuation": -0.8,
        "weighted_contribution": -0.168
      },
      {
        "channel": "group",
        "trace_key": "(human, extract.hunt)",
        "decayed_value": 0.31,
        "valuation": -0.4,
        "weighted_contribution": -0.043
      }
    ],
    "computed_affinity": -0.38,
    "threshold_crossed": "unwelcoming"
  },
  "cooldowns_consumed": ["pathing:player_0042:whispering_woods"],
  "triggered": true
}
```

### Example: No Affordance Triggered (Neutral)

```json
{
  "adjustments": {},
  "tells": [],
  "trace": {
    "timestamp": 1703779200.0,
    "location_id": "market_square",
    "actor_id": "player_0042",
    "affordance_type": "pathing",
    "effect_applied": null,
    "severity": 0.0,
    "contributing_traces": [],
    "computed_affinity": 0.05,
    "threshold_crossed": "neutral"
  },
  "cooldowns_consumed": [],
  "triggered": false
}
```

### Example: Artifact Pressure on Bearer

```json
{
  "adjustments": {
    "actor.stamina_modifier": -0.15,
    "action.skill_modifier": -0.12
  },
  "tells": [
    "The ring grows cold against your skin.",
    "Your fingers feel clumsy, reluctant."
  ],
  "trace": {
    "timestamp": 1703865600.0,
    "location_id": "ruined_tower",
    "actor_id": "player_0099",
    "affordance_type": "artifact_pressure",
    "effect_applied": "resist_dispel",
    "severity": 0.27,
    "contributing_traces": [
      {
        "channel": "bearer",
        "trace_key": "player_0099",
        "decayed_value": 0.65,
        "valuation": -0.5,
        "weighted_contribution": -0.325
      }
    ],
    "computed_affinity": -0.45,
    "threshold_crossed": "unwelcoming"
  },
  "cooldowns_consumed": ["artifact_pressure:ring_of_binding:player_0099"],
  "triggered": true
}
```

---

## 4. AffordanceSnapshot

### Example: Forest Fire Replay Snapshot

```json
{
  "actor_id": "player_0042",
  "actor_tags": ["human", "hunter", "outsider"],
  "location_id": "whispering_woods",

  "personal_traces": {
    "(player_0042, harm.fire)": {
      "accumulated": 0.6,
      "last_updated": 1703520000.0,
      "event_count": 1,
      "is_scar": false
    }
  },

  "group_traces": {
    "(human, harm.fire)": {
      "accumulated": 0.6,
      "last_updated": 1703520000.0,
      "event_count": 1,
      "is_scar": false
    },
    "(human, extract.hunt)": {
      "accumulated": 0.9,
      "last_updated": 1703433600.0,
      "event_count": 2,
      "is_scar": false
    }
  },

  "behavior_traces": {
    "harm.fire": {
      "accumulated": 0.6,
      "last_updated": 1703520000.0,
      "event_count": 1,
      "is_scar": false
    },
    "extract.hunt": {
      "accumulated": 0.9,
      "last_updated": 1703433600.0,
      "event_count": 2,
      "is_scar": false
    }
  },

  "valuation_profile": {
    "harm": -0.2,
    "harm.fire": -0.8,
    "extract": -0.2,
    "extract.hunt": -0.4,
    "offer": 0.4,
    "offer.gift": 0.5
  },

  "half_lives": {
    "personal": 604800,
    "group": 2592000,
    "behavior": 7776000
  },

  "channel_weights": {
    "personal": 0.5,
    "group": 0.35,
    "behavior": 0.15
  },

  "random_seed": null,

  "computed_affinity": -0.38,
  "threshold_crossed": "unwelcoming",
  "affordance_triggered": "pathing"
}
```

### Example: Artifact Pressure Replay Snapshot

```json
{
  "actor_id": "player_0099",
  "actor_tags": ["elf", "mage"],
  "location_id": "ring_of_binding",

  "personal_traces": {},

  "group_traces": {},

  "behavior_traces": {},

  "bearer_traces": {
    "player_0099": {
      "accumulated": 0.65,
      "last_updated": 1703779200.0,
      "event_count": 5,
      "is_scar": false,
      "pressure_vectors_active": ["skill_modulation", "fatigue_timing"]
    }
  },

  "valuation_profile": {
    "magic.bind": 0.6,
    "magic.dispel": -0.5,
    "offer.sacrifice": 0.4
  },

  "half_lives": {
    "bearer": 259200
  },

  "channel_weights": {
    "bearer": 1.0
  },

  "random_seed": 42,

  "computed_affinity": -0.45,
  "threshold_crossed": "unwelcoming",
  "affordance_triggered": "resist_dispel"
}
```

---

## 5. TraceRecord (Channel Storage)

### Personal Channel Key Shape

```python
# Dict[Tuple[str, str], TraceRecord]
# Key: (actor_id, event_type)

{
    ("player_0042", "harm.fire"): TraceRecord(...),
    ("player_0042", "extract.hunt"): TraceRecord(...),
    ("player_0099", "offer.gift"): TraceRecord(...)
}
```

### Group Channel Key Shape

```python
# Dict[Tuple[str, str], TraceRecord]
# Key: (actor_tag, event_type)

{
    ("human", "harm.fire"): TraceRecord(...),
    ("human", "extract.hunt"): TraceRecord(...),
    ("elf", "offer.gift"): TraceRecord(...)
}
```

### Behavior Channel Key Shape

```python
# Dict[str, TraceRecord]
# Key: event_type

{
    "harm.fire": TraceRecord(...),
    "extract.hunt": TraceRecord(...),
    "offer.gift": TraceRecord(...)
}
```

---

## 6. Valuation Lookup Examples

### Exact Match

```python
profile = {"harm": -0.2, "harm.fire": -0.8}
get_valuation(profile, "harm.fire")  # → -0.8 (exact match)
```

### Category Fallback

```python
profile = {"harm": -0.2, "harm.fire": -0.8}
get_valuation(profile, "harm.poison")  # → -0.2 (category fallback)
```

### Default (No Match)

```python
profile = {"harm": -0.2, "harm.fire": -0.8}
get_valuation(profile, "trade.fair")  # → 0.0 (default)
```

---

*These examples are the reference implementation targets. Code generation should produce structures that serialize to these shapes.*
