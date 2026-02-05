# Affinity Specification

**Version:** 0.4
**Target Platform:** Evennia
**Purpose:** Define relationship intelligence as emergent world behavior

---

## 1. Core Concept

Affinity is **accumulated relational memory** stored in world entities. It is not a reputation system, not a morality meter, and never speaks. Affinity answers: *How does this place/object/culture feel about this actor or behavior, given everything that has happened here?*

Key principles:

- **No judgments, only correlations.** The system stores "elf + fire → harm happened" not "elves are bad." Valence (good/bad) lives in each entity's values, not in the global model.
- **No dialogue.** Entities express affinity through affordance modulation, never speech.
- **Slow drift.** Changes accumulate over hours/days, not seconds.
- **Emergent meaning.** Players infer relationships; the system never explains.
- **The world breathes.** Entities evolve even when unobserved.

---

## 2. Entity Taxonomy

All world objects fall into four conceptual roles. These are not necessarily distinct classes—an object may fulfill multiple roles—but they define how affinity flows.

### 2.1 Actor

**Definition:** An entity with intent that initiates events.

| Subtype | Description | Affinity Role |
|---------|-------------|---------------|
| Player | Human-controlled character | Primary affinity target; leaves memory traces across entities |
| NPC | World-controlled agent | Can be affinity source or target; may reference institutional memory |
| Spirit | Manifested supernatural entity | Rare; typically bound to Location or Artifact |

**Key properties:**
- `actor_id`: Unique identifier
- `actor_tags`: Set of categorical markers (e.g., `{"elf", "mage", "outsider"}`)
- `behavior_signature`: Rolling window of recent action types

### 2.2 Location (Substrate)

**Definition:** A persistent place that accumulates memory even when empty.

| Examples | Memory Focus |
|----------|--------------|
| Forest, Grove | Ecological harm, reverence, extraction |
| City, Market | Commerce, violence, cultural mixing |
| Ruin, Battlefield | Death, desecration, remembrance |
| Sacred Site, Temple | Ritual correctness, devotion, transgression |
| River, Mountain | Passage, offering, obstruction |

**Key properties:**
- `location_id`: Unique identifier
- `personal_traces`: Dict mapping `(actor_id, event_type) → TraceRecord` — individual history
- `group_traces`: Dict mapping `(actor_tag, event_type) → TraceRecord` — categorical history
- `behavior_traces`: Dict mapping `event_type → TraceRecord` — what happens here generally
- `valuation_profile`: Dict mapping `event_type → float` — this place's values (not universal ethics)
- `saturation`: `SaturationState` object (per-channel, see §4.5)
- `last_tick`: Timestamp of last housekeeping pass

### 2.3 Artifact

**Definition:** A mobile object that carries pressure and learns its bearer.

| Examples | Pressure Style |
|----------|----------------|
| Ring, Amulet | Amplifies existing desires |
| Weapon | Biases toward/against violence |
| Book, Song | Shapes perception and knowledge |
| Relic | Connects bearer to institutional memory |
| Cursed Tool | Creates dependency, fatigue, obsession |

**Key properties:**
- `artifact_id`: Unique identifier
- `origin_tags`: Set of source associations (e.g., `{"elven", "old_kingdom"}`)
- `bearer_traces`: Dict mapping `bearer_id → BearerRecord`
- `valuation_profile`: Dict mapping `event_type → float` — the artifact's biases
- `pressure_vectors`: List of `PressureRule` objects
- `influence_accumulator`: Float tracking current grip on bearer

### 2.4 Institution (Field)

**Definition:** A distributed pattern across multiple objects with its own persistent drift.

| Examples | Manifestation |
|----------|---------------|
| Elven Culture | Shared memory in forests, elven NPCs, elven artifacts |
| The Empire | Biases in imperial cities, soldier NPCs, official documents |
| Fire Magic Tradition | Spell behavior, mage NPCs, enchanted items |
| The Old Ways | Sacred sites, oral tradition, ancestral artifacts |

**Key properties:**
- `institution_id`: Unique identifier
- `affiliated_tags`: Set of entity tags that contribute to this institution
- `cached_stance`: Dict mapping `actor_tag → float` — slowly-decaying aggregate
- `drift_rate`: How quickly cached stance updates from constituents
- `inertia`: Resistance to rapid change (institutions are slow)
- `last_computed`: Timestamp of last aggregate refresh

**Implementation note:** Institutions are **virtual entities**—no physical presence, no direct interaction—but they persist, drift, and bias other systems. They are computed from constituents but maintain their own decaying state, allowing them to be "wrong" in persistent ways (which is how folklore works).

```python
@dataclass
class Institution:
    institution_id: str
    affiliated_tags: Set[str]
    cached_stance: Dict[str, float]  # actor_tag → affinity
    drift_rate: float = 0.1          # blend rate toward fresh query
    inertia: float = 0.9             # resistance to change
    half_life_days: float = 90.0     # institutional memory is long
    last_computed: float = 0.0
```

---

## 3. Event Ontology

Events are the atomic unit of affinity change. Every logged event has:

```python
@dataclass
class AffinityEvent:
    event_type: str           # From controlled vocabulary
    actor_id: str             # Who initiated
    actor_tags: Set[str]      # Categorical markers at time of event
    target_id: Optional[str]  # Affected entity, if any
    location_id: str          # Where it happened
    intensity: float          # 0.0–1.0, magnitude of action
    timestamp: float          # Unix time
    context_tags: Set[str]    # Additional qualifiers
```

### 3.1 Event Type Vocabulary

| Category | Event Types | Typical Intensity |
|----------|-------------|-------------------|
| **Harm** | `harm.physical`, `harm.fire`, `harm.poison`, `harm.magical` | 0.3–1.0 |
| **Healing** | `heal.physical`, `heal.magical`, `heal.rest` | 0.2–0.6 |
| **Death** | `death.combat`, `death.sacrifice`, `death.natural` | 0.8–1.0 |
| **Extraction** | `extract.harvest`, `extract.mine`, `extract.hunt`, `extract.loot` | 0.2–0.7 |
| **Creation** | `create.build`, `create.plant`, `create.craft`, `create.ritual` | 0.2–0.6 |
| **Trespass** | `trespass.enter`, `trespass.defile`, `trespass.observe` | 0.1–0.5 |
| **Offering** | `offer.gift`, `offer.sacrifice`, `offer.prayer` | 0.2–0.8 |
| **Commerce** | `trade.fair`, `trade.exploit`, `trade.gift` | 0.1–0.4 |
| **Magic** | `magic.cast`, `magic.summon`, `magic.bind`, `magic.dispel` | 0.3–0.9 |
| **Social** | `social.aid`, `social.betray`, `social.honor`, `social.insult` | 0.2–0.7 |
| **Movement** | `move.pass`, `move.flee`, `move.pursue` | 0.05–0.2 |

### 3.2 Context Tags

Context tags qualify events without creating new event types:

- `violent`, `peaceful`
- `public`, `secret`
- `ritual`, `mundane`
- `first_time`, `repeated`
- `sanctioned`, `forbidden`

### 3.3 Valuation Profiles (Per-Entity Values)

The system stores **correlations only**. Meaning emerges from each entity's `valuation_profile`.

```python
# A forest's values
forest_valuation = {
    "harm": -0.3,              # dislikes harm generally
    "harm.fire": -0.8,         # especially hates fire
    "extract": -0.2,           # mild concern about extraction
    "extract.hunt": -0.4,      # dislikes hunting specifically
    "offer": +0.4,             # appreciates offerings generally
    "offer.gift": +0.5,        # especially likes gifts
    "create.plant": +0.4,      # likes planting
}

# A frontier town's values
town_valuation = {
    "extract.hunt": +0.2,      # hunting is trade
    "trade": +0.2,             # commerce welcome generally
    "trade.fair": +0.3,        # especially fair trade
    "harm.physical": -0.4,     # dislikes violence
    "create.build": +0.3,      # likes construction
}
```

**Valuation lookup with fallback:**

```python
def get_valuation(profile: Dict[str, float], event_type: str) -> float:
    """
    Lookup order:
    1. Exact match: "harm.fire"
    2. Category match: "harm" (prefix before first dot)
    3. Default: 0.0
    """
    # Try exact match
    if event_type in profile:
        return profile[event_type]

    # Try category match
    category = event_type.split('.')[0]
    if category in profile:
        return profile[category]

    # Default: neutral
    return 0.0
```

This keeps the model descriptive. The forest remembers "elf used fire here." Whether that's bad depends on the forest's values, not a global ethics table. Category fallbacks prevent silent 0.0 returns when new event types are added.

**Magnitude guidelines:**

| Level | Magnitude | Use For |
|-------|-----------|---------|
| Category defaults | ±0.1 to ±0.2 | Soft baseline ("harm is mildly bad") |
| Specific events | ±0.3 to ±0.5 | Normal valuation ("hunting bothers me") |
| Strong reactions | ±0.6 to ±0.8 | Defining traits ("fire is anathema here") |

Keep category weights **small**. If you set `harm: -0.8`, the forest hates *all* harm equally—losing the nuance between a scraped knee and arson. Let exact event types carry the strong opinions.

**Example event:**
```python
AffinityEvent(
    event_type="extract.hunt",
    actor_id="player_0042",
    actor_tags={"human", "hunter", "outsider"},
    target_id="deer_entity",
    location_id="whispering_woods",
    intensity=0.4,
    timestamp=1703520000.0,
    context_tags={"first_time", "mundane"}
)
```

---

## 4. Memory Model

Memory is how entities store and forget events. This creates the "slow drift" that makes affinity feel organic.

### 4.1 Trace Records

A trace is a single correlation stored in an entity's memory. The dict key is the key—`TraceRecord` stores only the accumulated state.

```python
@dataclass
class TraceRecord:
    accumulated: float        # Total weighted intensity
    last_updated: float       # Timestamp of last event
    event_count: int          # How many times
    is_scar: bool = False     # Preserved landmark event
```

### 4.2 Memory Channels

Locations track three parallel memory streams. Each channel uses a different key structure in its dict:

| Channel | Dict Type | Key Structure | Half-Life | Purpose |
|---------|-----------|---------------|-----------|---------|
| **Personal** | `Dict[Tuple[str, str], TraceRecord]` | `(actor_id, event_type)` | 7 days | "This one arsonist elf" |
| **Group** | `Dict[Tuple[str, str], TraceRecord]` | `(actor_tag, event_type)` | 30 days | "Elves as a category" |
| **Behavior** | `Dict[str, TraceRecord]` | `event_type` | 90 days | "Fire happens here often" |

This gives you individual history + group history + place character.

**Key principle:** The dict key carries the identity; `TraceRecord` is just the accumulator. No ambiguity about "what is `trace.key` here?"

### 4.3 Decay Function

Memory fades over time. Decay is exponential with a configurable half-life.

```
current_value = accumulated * (0.5 ^ (time_elapsed / half_life))
```

| Entity Type | Personal Half-Life | Group Half-Life | Behavior Half-Life |
|-------------|--------------------|-----------------|--------------------|
| Location | 7 days | 30 days | 90 days |
| Artifact | 3 days | 14 days | 30 days |
| NPC | 1 day | 7 days | 14 days |

**Implementation:** Decay is computed lazily on read. Store `accumulated` and `last_updated`; compute decayed value when accessed.

```python
def get_decayed_value(trace: TraceRecord, half_life_seconds: float) -> float:
    elapsed = current_time() - trace.last_updated
    decay_factor = 0.5 ** (elapsed / half_life_seconds)
    return trace.accumulated * decay_factor
```

### 4.4 Accumulation

When a new event matches an existing trace:

```python
def accumulate(trace: TraceRecord, event: AffinityEvent, half_life: float,
               saturation: float):
    # First, decay existing value to present
    decayed = get_decayed_value(trace, half_life)

    # Apply saturation dampening (per-channel)
    effective_intensity = event.intensity * (1 - saturation ** 2)

    # Add new intensity
    trace.accumulated = decayed + effective_intensity
    trace.last_updated = event.timestamp
    trace.event_count += 1
```

### 4.5 Saturation (Per-Channel)

Saturation is tracked **per channel**, not globally. A location saturated by commerce is not deaf to violence.

```python
@dataclass
class SaturationState:
    personal: float = 0.0    # 0.0–1.0
    group: float = 0.0       # 0.0–1.0
    behavior: float = 0.0    # 0.0–1.0
```

| Saturation Level | Effect |
|------------------|--------|
| 0.0–0.3 | Full sensitivity to new events |
| 0.3–0.7 | Diminishing returns; entity is "experienced" |
| 0.7–1.0 | Near-deaf; only extreme events register |

Saturation increases with trace volume in that channel. Saturation decreases slowly when no events occur.

```python
def update_saturation(channel_traces: Dict, base_capacity: int) -> float:
    total_weight = sum(get_decayed_value(t, half_life) for t in channel_traces.values())
    return min(1.0, total_weight / base_capacity)
```

### 4.6 Computing Affinity Fields

Affinity for an actor is derived from traces across all channels, weighted by the entity's `valuation_profile`.

**Channel-specific scoring functions** (explicit about key shapes):

```python
def score_personal(
    traces: Dict[Tuple[str, str], TraceRecord],  # (actor_id, event_type) → trace
    actor_id: str,
    half_life: float,
    profile: Dict[str, float]
) -> float:
    """Score personal channel. Keys are (actor_id, event_type) tuples."""
    score = 0.0
    for (trace_actor_id, event_type), trace in traces.items():
        if trace_actor_id != actor_id:
            continue
        value = get_decayed_value(trace, half_life)
        valuation = get_valuation(profile, event_type)
        score += value * valuation
    return score


def score_group(
    traces: Dict[Tuple[str, str], TraceRecord],  # (actor_tag, event_type) → trace
    actor_tags: Set[str],
    half_life: float,
    profile: Dict[str, float]
) -> float:
    """Score group channel. Keys are (actor_tag, event_type) tuples."""
    score = 0.0
    for (trace_tag, event_type), trace in traces.items():
        if trace_tag not in actor_tags:
            continue
        value = get_decayed_value(trace, half_life)
        valuation = get_valuation(profile, event_type)
        score += value * valuation
    return score


def score_behavior(
    traces: Dict[str, TraceRecord],  # event_type → trace
    half_life: float,
    profile: Dict[str, float]
) -> float:
    """Score behavior channel. Keys are event_type strings."""
    score = 0.0
    for event_type, trace in traces.items():
        value = get_decayed_value(trace, half_life)
        valuation = get_valuation(profile, event_type)
        score += value * valuation
    return score
```

**Main computation:**

```python
def compute_affinity(location, actor_id: str, actor_tags: Set[str]) -> float:
    """
    Blend personal, group, and behavior channels.
    Half-lives come from config, not from traces.
    Valuation comes from the location's profile.
    """
    config = get_config()
    profile = location.valuation_profile

    personal = score_personal(
        location.personal_traces,
        actor_id,
        config.half_lives.location.personal,
        profile
    )

    group = score_group(
        location.group_traces,
        actor_tags,
        config.half_lives.location.group,
        profile
    )

    behavior = score_behavior(
        location.behavior_traces,
        config.half_lives.location.behavior,
        profile
    )

    W = config.channel_weights
    raw = W.personal * personal + W.group * group + W.behavior * behavior
    return math.tanh(raw / config.affinity_scale)
```

### 4.7 Memory Compaction

Traces grow unboundedly without a compression policy. The spec defines three tiers:

| Tier | Age | Treatment |
|------|-----|-----------|
| **Hot** | 0–7 days | Full detail. Raw traces with all fields. |
| **Warm** | 7–90 days | Rolled up. Aggregate into category-level EMAs. |
| **Scar** | 90+ days | Landmarks only. High-intensity events preserved with slow decay. |

```python
@dataclass
class ScarEvent:
    event_type: str
    actor_tags: Set[str]       # who did it (category, not ID)
    intensity: float           # original intensity
    timestamp: float           # when it happened
    half_life_days: float = 365.0  # scars last years
```

**Folding rules** (how keys collapse during compaction):

```python
def fold_actor_tag(tag: str, config: Config) -> Optional[str]:
    """
    Return tag if institutional, else None (discard).
    INSTITUTIONAL_TAGS comes from config, not code—
    allows fantasy worlds (elf, dwarf) and modern settings (corporate, union).
    """
    return tag if tag in config.institutional_tags else None

# Category folding: event_type → event_category
def fold_event_type(event_type: str) -> str:
    """Extract category prefix: 'harm.fire' → 'harm'"""
    return event_type.split('.')[0]
```

**Compaction rules:**

1. **Hot → Warm:** After 7 days, personal traces are discarded (individual IDs forgotten). Group traces are merged into EMAs keyed by `(folded_tag, event_category)`. Only institutional tags survive; others aggregate into a catch-all.

2. **Warm → Scar:** After 90 days, only events with `intensity > 0.7` become scars. Everything else decays to zero and is deleted.

3. **Scar persistence:** Scars decay very slowly (half-life: 1 year). They represent "the time the forest burned" or "the massacre at the crossroads."

**Implementation:** Compaction runs during the world tick (see §4.8).

### 4.8 World Tick (Breathing When Unobserved)

Lazy decay math is fine, but without periodic housekeeping, unvisited locations "freeze in time" and behave strangely when re-entered.

**Scheduled tick** (configurable: hourly default, daily for low-traffic servers):

```python
def world_tick(location):
    """Run periodically, even when no players present."""

    # 1. Compact traces (hot → warm → scar)
    compact_traces(location)

    # 2. Clear near-zero traces (decayed below threshold)
    prune_traces(location, threshold=0.01)

    # 3. Update cached mood bands (for quick affordance lookups)
    location.cached_mood = compute_mood_band(location)

    # 4. Clear expired cooldowns
    clear_expired_cooldowns(location)

    # 5. Update saturation levels
    update_saturation_state(location)

    location.last_tick = current_time()
```

**Mood bands** are cached affinity ranges for common actor tags, avoiding full recomputation on every action:

```python
@dataclass
class MoodBand:
    actor_tag: str
    affinity_range: Tuple[float, float]  # (min, max) from recent samples
    dominant_emotion: str                 # "hostile", "wary", "neutral", "warm", "aligned"
    last_updated: float
```

**Critical invariant:** Mood bands are **derived caches, disposable, never authoritative**. They can be deleted and recomputed from traces at any time. Never write mood band state back into the trace system—that creates feedback loops and drift.

### 4.9 Affinity Threshold Behaviors

Affinity values (per actor) range from -1.0 (hostile) to +1.0 (welcoming). Thresholds trigger affordance changes:

| Range | Label | Affordance Effect |
|-------|-------|-------------------|
| -1.0 to -0.7 | Hostile | Active hindrance; danger increases |
| -0.7 to -0.3 | Unwelcoming | Passive resistance; inefficiency |
| -0.3 to +0.3 | Neutral | No modification |
| +0.3 to +0.7 | Favorable | Passive assistance; luck |
| +0.7 to +1.0 | Aligned | Active cooperation; revelation |

---

## 5. Affordance Catalog

Affordances are the behavioral outputs of affinity. They modulate what happens, never what is said.

**Mechanical handle requirements:**

1. Each affordance must define what in-game variable it touches, or be explicitly marked "flavor only."
2. No affordance may touch more than **two handles**. This preserves subtlety and keeps debugging sane.
3. Handles should be existing game variables, not invented stats. If you need a new stat, that's a game design decision outside this spec.

### 5.1 Location Affordances

| Affordance | Hostile Effect | Favorable Effect | Cooldown | Severity Clamp | Mechanical Handle |
|------------|----------------|------------------|----------|----------------|-------------------|
| **Pathing** | Paths twist; travel takes longer | Shortcuts appear; travel is swift | 1 hour | +50% / -30% travel time | `room.travel_time_modifier` |
| **Encounter Rate** | Dangerous creatures more frequent | Peaceful creatures; threats avoid | 30 min | 2x / 0.5x base rate | `room.encounter_rate_modifier` |
| **Spell Efficacy** | Spells misfire, reduced power | Spells amplified, unexpected success | Per spell | ±25% power | `spell.power_modifier` |
| **Resource Yield** | Harvests poor, veins barren | Bounty appears, hidden caches | 2 hours | ±40% yield | `harvest.yield_modifier` |
| **Rest Quality** | Sleep disturbed, healing slowed | Deep rest, bonus recovery | 8 hours | ±30% healing | `rest.healing_modifier` |
| **Navigation** | Landmarks hidden, disorientation | Clear signs, intuitive direction | 1 hour | — | Flavor only |
| **Weather (local)** | Harsh micro-weather | Sheltering conditions | 4 hours | — | Flavor only |
| **Animal Behavior** | Wildlife flees or attacks | Wildlife approaches, aids | 2 hours | Aggro radius ±50% | `npc.aggro_radius_modifier` |

### 5.2 Artifact Affordances (Pressure Vectors)

| Pressure Type | Mechanism | Example | Cooldown | Severity Clamp | Mechanical Handle |
|---------------|-----------|---------|----------|----------------|-------------------|
| **Desire Amplification** | Increases existing wants | Ring makes power-hunger sharper | 1 hour | +30% | Flavor only (narrative) |
| **Fatigue Timing** | Exhaustion at critical moments | Bearer tires when trying to discard | 4 hours | -20% stamina | `actor.stamina_modifier` |
| **Coincidence Bias** | Nudges random outcomes | "Lucky" finds that serve artifact's origin | 1 hour | ±15% | `actor.luck_modifier` |
| **Skill Modulation** | Easier/harder by alignment | Elven blade flows for elves, resists orcs | Per action | ±20% | `action.skill_modifier` |
| **Perception Filter** | Notice more/less by category | Cursed gold makes other wealth invisible | 30 min | — | Flavor only (description) |
| **Dependency Curve** | Withdrawal when separated | Discomfort grows with distance | Continuous | -25% | `actor.stat_modifier` (all) |

**Pressure rules** are defined per artifact:

```python
@dataclass
class PressureRule:
    trigger: str              # "bearer_action", "bearer_state", "proximity"
    condition: str            # Expression evaluated against context
    effect_type: str          # From pressure type vocabulary
    intensity_base: float     # 0.0–1.0
    scales_with_influence: bool  # Grows as artifact learns bearer?
    cooldown_seconds: int     # Minimum time between triggers
    severity_clamp: float     # Maximum effect magnitude
```

### 5.3 Institutional Affordances

Institutions modulate through their constituent entities:

| Domain | Effect | Cooldown | Severity Clamp |
|--------|--------|----------|----------------|
| **NPC Disposition** | Affiliated NPCs slightly warmer/colder | 1 hour | ±20% disposition |
| **Artifact Attunement** | Items from institution work better/worse | Per use | ±15% efficacy |
| **Ritual Success** | Ceremonies of that tradition more/less reliable | Per ritual | ±25% success |
| **Lore Access** | Knowledge surfaces or stays hidden | 4 hours | Binary: reveal/hide |
| **Faction Perception** | Soft reputation by association | 1 day | ±10% initial stance |

### 5.4 Counterplay Patterns

Every affordance must have mythic counterplay—ways for players to repair affinity without seeing meters.

| Counterplay Type | Mechanism | Example |
|------------------|-----------|---------|
| **Offerings** | `offer.gift` events with appropriate items | Leave food for the forest; it softens |
| **Restorative Actions** | Opposite-valence events | Plant trees after burning; rebuild after destruction |
| **Abstention** | Time without negative events | Stay away; let the place forget you specifically |
| **Ritual Repair** | `create.ritual` events at sacred moments | Ceremony at equinox; blessing by appropriate NPC |
| **Mediation** | NPC with high affinity vouches | Druid intercedes; elder speaks for you |
| **Sacrifice** | High-intensity positive event | Return a stolen artifact; release a bound spirit |

Counterplay must be **discoverable through folklore**, not documented in help files.

### 5.5 Adversarial Play Considerations

Players will try to weaponize the system. Anticipate:

| Attack Vector | Example | Mitigation |
|---------------|---------|------------|
| **Grief by proxy** | Burn forest while disguised as enemy faction | Personal traces matter; individual ID tracked short-term |
| **Affinity farming** | Spam low-intensity positive actions | Saturation limits; diminishing returns |
| **PvP via environment** | Lure enemy to hostile location | Cooldowns prevent instant-kill affordances |
| **Artifact dumping** | Give cursed item to newbie | Bearer must hold for N hours before pressure activates |
| **Institution manipulation** | Mass-coordinate to shift institutional stance | Inertia and slow drift resist rapid change |

Design principle: **effort should scale with impact**. Shifting a forest's stance toward hostility requires sustained action, not one dramatic event.

### 5.6 Unified Affordance Interface

All affordance evaluation flows through a single contract:

```python
@dataclass
class AffordanceContext:
    """Input to affordance evaluation."""
    actor_id: str
    actor_tags: Set[str]
    location: Location              # or Artifact
    action_type: str                # what the actor is doing
    action_target: Optional[str]    # target of action, if any
    timestamp: float


@dataclass
class AffordanceOutcome:
    """Output from affordance evaluation."""
    # Mechanical adjustments (handle → delta)
    adjustments: Dict[str, float]   # e.g., {"room.travel_time_modifier": 0.3}

    # Narrative tells (strings for player-facing output)
    tells: List[str]                # e.g., ["The path seems to twist away from you."]

    # Admin trace payload (for debugging)
    trace: AffordanceTriggerLog

    # Cooldown tokens consumed
    cooldowns_consumed: List[str]   # e.g., ["pathing:player_0042"]

    # Whether any affordance actually fired
    triggered: bool


def evaluate_affordances(ctx: AffordanceContext) -> AffordanceOutcome:
    """
    Single entry point for all affordance checks.
    1. Compute affinity for actor in location
    2. Check thresholds
    3. Check cooldowns
    4. Apply severity clamps
    5. Return mechanical + narrative + trace
    """
    ...
```

This interface ensures:
- All affordance logic passes through one code path
- Mechanical effects and narrative tells are always paired
- Admin tracing is never forgotten
- Cooldowns are consistently tracked

---

## 6. Player Legibility Rules

Players must never see affinity values. They experience patterns.

### 6.1 What May Be Hinted

| Category | Permitted Hints |
|----------|-----------------|
| **Environmental description** | "The forest feels watchful." / "An easy path opens." |
| **Outcome flavor** | "Your spell flares unexpectedly bright." |
| **NPC behavior** | Wariness, warmth (no explanation why) |
| **Animal reactions** | Approach, avoidance, aggression |
| **Folklore from NPCs** | "They say elves are unwelcome in the iron hills." |
| **Contrast between characters** | Different outcomes for different actors in same place |
| **Generational echoes** | "Your family name carries weight here." |

### 6.2 What Must Never Be Shown

| Forbidden | Rationale |
|-----------|-----------|
| Numeric affinity values | Breaks immersion; invites gaming |
| Explicit cause-effect | "Because you killed the deer, the forest..." |
| System explanations | No meta-text about how affinity works |
| Progress bars, meters | No UI representation of hidden state |
| Artifact inner monologue | Objects do not speak their intent |
| Institutional stance readouts | Cultures don't issue press releases |

### 6.3 Discovery Mechanisms

Players learn affinity through:

1. **Repetition** — Same action, same place, pattern emerges
2. **Contrast** — Different character gets different treatment
3. **Folklore** — NPCs share beliefs (which may be wrong)
4. **Consequence** — Delayed effects trace back to past actions
5. **Generational memory** — New characters inherit hints of old
6. **Experimentation** — Deliberate testing by observant players

### 6.4 Admin Tracing Rules

Affinity must be debuggable without exposing internals to players.

**Mandatory logging (admin-only):**

```python
@dataclass
class AffordanceTriggerLog:
    timestamp: float
    location_id: str
    actor_id: str
    affordance_type: str
    effect_applied: str
    severity: float
    contributing_traces: List[TraceContribution]  # top N traces that mattered
    computed_affinity: float
    threshold_crossed: str
```

```python
@dataclass
class TraceContribution:
    channel: str           # "personal", "group", "behavior"
    trace_key: str         # the key in that channel
    decayed_value: float   # value at trigger time
    valuation: float       # from entity's profile
    weighted_contribution: float
```

**Admin commands:**

- `affinity/inspect <location>` — Show current affinity toward caller, top traces
- `affinity/history <location> [hours]` — Recent affordance triggers
- `affinity/why <location> <actor>` — Explain top contributing factors
- `affinity/replay <trigger_id>` — Replay using logged snapshot to verify determinism
- `affinity/reeval <location> <actor>` — Recompute using current state for tuning

**Replay vs Re-eval distinction:**

| Command | Input State | Purpose |
|---------|-------------|---------|
| `replay` | Snapshot from `AffordanceTriggerLog` | "Did we compute this correctly at the time?" |
| `reeval` | Current live traces | "What would happen if this actor entered now?" |

`replay` verifies determinism; `reeval` supports tuning.

**Snapshot contents for replay:**

A replay-capable snapshot must include everything needed to reproduce the exact computation:

```python
@dataclass
class AffordanceSnapshot:
    # Input state at trigger time
    actor_id: str
    actor_tags: Set[str]
    location_id: str

    # Trace state (frozen at trigger time)
    personal_traces: Dict[Tuple[str, str], TraceRecord]
    group_traces: Dict[Tuple[str, str], TraceRecord]
    behavior_traces: Dict[str, TraceRecord]

    # Entity config (frozen)
    valuation_profile: Dict[str, float]
    half_lives: HalfLifeConfig
    channel_weights: ChannelWeights

    # Random seed if any stochastic elements
    random_seed: Optional[int]

    # Computed results (for verification)
    computed_affinity: float
    threshold_crossed: str
    affordance_triggered: str
```

Store this with each `AffordanceTriggerLog`. Replay reconstructs the computation from snapshot data, not current state.

**Principle:** Admins can always answer "why did that happen?" without exposing it to players.

---

## 7. Configuration

All tunable parameters live in config files, not code. This enables:

- Per-world customization
- A/B testing of decay rates
- Seasonal events (shorter half-lives during festivals)
- Balance patches without deploys

### 7.1 Default Configuration File

`config/affinity_defaults.yaml`:

```yaml
# Memory half-lives (in days)
half_lives:
  location:
    personal: 7
    group: 30
    behavior: 90
  artifact:
    personal: 3
    group: 14
    behavior: 30
  npc:
    personal: 1
    group: 7
    behavior: 14

# Affinity computation weights
channel_weights:
  personal: 0.5
  group: 0.35
  behavior: 0.15

# Saturation base capacities
saturation_capacity:
  personal: 50
  group: 100
  behavior: 200

# World tick interval (seconds)
world_tick_interval: 3600  # 1 hour

# Compaction thresholds
compaction:
  hot_window_days: 7
  warm_window_days: 90
  scar_intensity_threshold: 0.7
  scar_half_life_days: 365
  prune_threshold: 0.01

# Institution settings
institutions:
  drift_rate: 0.1
  inertia: 0.9
  half_life_days: 90
  refresh_interval: 86400  # 1 day

# Institutional tags: which actor_tags survive warm compaction
# Configure per-world: fantasy (elf, dwarf), modern (corporate, union), etc.
institutional_tags:
  - human
  - elf
  - dwarf
  - orc
  - imperial
  - rebel

# Affinity scale (for tanh normalization)
affinity_scale: 10.0
```

---

## 8. Implementation Checklist

A junior engineer implementing this system should build:

**Core data structures:**
- [ ] `AffinityEvent` dataclass and event logging
- [ ] `TraceRecord` with channel-aware storage
- [ ] `SaturationState` per-channel tracking
- [ ] `ScarEvent` for long-term landmarks
- [ ] `Institution` virtual entity with cached state

**Memory system:**
- [ ] Decay computation (lazy, on-read)
- [ ] Accumulation with saturation dampening
- [ ] Three-channel trace storage (personal/group/behavior)
- [ ] Memory compaction (hot → warm → scar)
- [ ] World tick scheduler

**Affinity computation:**
- [ ] `compute_affinity()` blending three channels
- [ ] Per-entity `valuation_profile` loading
- [ ] Mood band caching for quick lookups

**Affordances:**
- [ ] Modifier hooks for each system (pathing, spells, etc.)
- [ ] Cooldown tracking per actor per affordance
- [ ] Severity clamping
- [ ] Counterplay event detection

**Artifacts:**
- [ ] `PressureRule` evaluation loop
- [ ] Bearer trace accumulation
- [ ] Influence curve computation

**Institutions:**
- [ ] `InstitutionQuery` aggregator
- [ ] Cached stance with slow drift
- [ ] Periodic refresh from constituents

**Admin tools:**
- [ ] `AffordanceTriggerLog` recording
- [ ] Inspect/history/why/replay commands
- [ ] Debug visualization (admin-only)

**Configuration:**
- [ ] YAML loader for `affinity_defaults.yaml`
- [ ] Per-entity valuation profile loading
- [ ] Runtime config reload support

---

## 9. Example Scenario

**Setup:** Whispering Woods has neutral affinity toward humans. Player (human, hunter) enters.

**Woods valuation profile:**
```yaml
extract.hunt: -0.3
harm.fire: -0.8
offer.gift: +0.5
create.plant: +0.4
```

**Events over 3 sessions:**

1. Player hunts deer (`extract.hunt`, intensity 0.4)
   - Personal trace created: `(player_0042, extract.hunt)`
   - Group trace updated: `(human, extract.hunt)`
   - Behavior trace updated: `extract.hunt`

2. Player hunts again (`extract.hunt`, intensity 0.5) — traces accumulate

3. Player builds campfire carelessly (`harm.fire`, intensity 0.3) — new traces

4. Player rests (`heal.rest`, intensity 0.2) — neutral in woods valuation

**After 1 week (no visits):**

World tick has run. Personal traces decayed ~50% (7-day half-life). Group traces decayed ~16%.

**Affinity computation:**
- Personal: `(0.4 + 0.5) * 0.5 * (-0.3) + 0.3 * 0.5 * (-0.8) = -0.255`
- Group: `(0.9 * 0.84) * (-0.3) + 0.3 * 0.84 * (-0.8) = -0.428`
- Behavior: similar but muted by W_BEHAVIOR = 0.15

Computed affinity ≈ -0.22 (slightly unwelcoming)

**Player returns:**

- Pathing: Slightly longer travel times (within cooldown/severity limits)
- Encounters: One extra wolf encounter (if encounter cooldown expired)
- Rest: Sleep messages mention "uneasy dreams"
- No explanation given

**Admin log shows:**
```
AffordanceTrigger: pathing/slow
  actor: player_0042
  affinity: -0.22
  top_traces:
    - personal:(player_0042, harm.fire) → -0.12
    - group:(human, extract.hunt) → -0.08
```

**If player brings offering:**

- `offer.gift` event with intensity 0.5
- Positive traces begin countering negative (valuation: +0.5)
- Over weeks, affinity drifts toward neutral

**Player never sees:** Numbers, cause-effect statements, or "the forest forgives you."

---

## 10. Glossary

| Term | Definition |
|------|------------|
| **Affinity** | Accumulated relational memory; how an entity feels about an actor |
| **Trace** | A stored correlation: dict key → `TraceRecord` (accumulated value) |
| **Channel** | Memory stream: personal (individual), group (category), behavior (general) |
| **Decay** | Exponential memory fade over time |
| **Saturation** | Per-channel memory fullness; limits new accumulation |
| **Valuation Profile** | Entity-specific mapping of event types to good/bad weights |
| **Affordance** | Behavioral output; how affinity changes world mechanics |
| **Pressure** | Artifact influence on bearer; grows with exposure |
| **Institution** | Virtual entity representing distributed cultural patterns |
| **Scar** | High-intensity event preserved as long-term landmark |
| **Mood Band** | Cached affinity range for quick lookups |
| **World Tick** | Periodic housekeeping pass on all entities |

---

## Appendix A. Implementation Notes (Repo Behavior)

These notes document the **current behavior of the code in this repository**.
They exist to prevent accidental “spec drift” when tuning the system.

### A.1 World Tick vs Compaction

- `world.affinity.world_tick.world_tick()` currently performs:
  - trace pruning (delete traces whose *decayed magnitude* falls below `config.compaction.prune_threshold`)
  - cooldown expiry cleanup
  - saturation decay
- **It does not run memory compaction** (hot → warm → scar) as part of tick.
  - Compaction exists in `world.affinity.compaction.compact_traces()` and is tested directly.
  - Rationale: Phase 1 lifecycle tests assume tick does not change affinity due to compaction side effects.

### A.2 Movement Affordance Evaluation Policy

For movement actions (`AffordanceContext.action_type == "move.pass"`):

- The affordance evaluator runs in a **single-primary-effect mode**:
  - only the `pathing` affordance is evaluated
  - if triggered, it applies `room.travel_time_modifier` and sets `effect_applied` to `"slow"` or `"swift"`
- Cooldown semantics for movement follow naturally from this:
  - a second evaluation immediately after a triggered movement outcome should not trigger again while the `pathing` cooldown is active.

### A.3 Affinity Scaling Convention

`compute_affinity()` uses tanh compression on the blended raw score.
In this repository the normalization currently mirrors the test suite’s expected tuning:

- `normalized = tanh(raw * (affinity_scale / 10.0))`

This makes `affinity_scale=10.0` behave as the baseline (multiplier of 1.0).

*End of specification.*
