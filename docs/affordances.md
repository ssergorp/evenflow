# Affordances Catalog

**Version:** 1.0
**Purpose:** Indirect, probabilistic world responses to affinity bias

---

## Design Philosophy

Affordances are how the world *shows* instead of *tells*. They must be:

1. **Indirect** — Never "the forest is angry at you"; only "the path twists unexpectedly"
2. **Probabilistic** — No guaranteed effects; patterns emerge over time
3. **Deniable** — A single event could be coincidence; only repetition reveals truth
4. **Mechanical** — Real game impact, not just flavor text
5. **Recoverable** — Every negative affordance has counterplay

**Critical constraints (see DO_NOT.md):**
- No player-visible affinity meters
- No explicit cause-effect statements
- Maximum 2 mechanical handles per affordance
- No invented stats; use existing game variables

---

## 1. Path Friction

**Concept:** Hostile terrain costs extra movement; friendly terrain flows easily.

| Aspect | Value |
|--------|-------|
| Handle | `room.travel_time_modifier` |
| Cooldown | 1 hour |
| Hostile Clamp | +50% travel time |
| Favorable Clamp | -30% travel time |
| Threshold | Hostile: < -0.3, Favorable: > +0.3 |

**Hostile tells:**
- "The path seems longer than you remember."
- "Brambles catch at your clothes."
- "You keep losing your footing on loose stones."
- "The trail doubles back unexpectedly."

**Favorable tells:**
- "An easy path opens through the undergrowth."
- "Your feet find sure footing on the trail."
- "The journey passes quickly."
- "A shortcut appears, as if made for you."

**Counterplay:** Offerings, planting, time without harm.

---

## 2. Misleading Navigation

**Concept:** Rare redirects to adjacent rooms. Extremely subtle; players must notice patterns.

| Aspect | Value |
|--------|-------|
| Handle | `room.redirect_target` (override destination) |
| Cooldown | 4 hours |
| Base Probability | 5% when hostile, 0% otherwise |
| Hostile Clamp | Max 15% redirect chance |
| Favorable Clamp | N/A (only triggers when hostile) |
| Threshold | Only < -0.5 (strongly hostile) |

**Implementation:**
- On movement, roll against redirect chance
- If triggered, send player to adjacent room instead of intended destination
- Adjacent room must be valid and not more dangerous
- Never redirect into combat or death

**Hostile tells:**
- "Wait... this isn't where you meant to go."
- "The familiar landmark was wrong."
- "You emerge somewhere unexpected."

**Favorable tells:** (rare, when aligned)
- "Your path curves, but you end up exactly where you needed to be."

**Counterplay:** Only triggers at strong hostility. Recovery through sustained positive actions.

---

## 3. Encounter Bias

**Concept:** Animals and creatures respond to the land's feeling about you.

| Aspect | Value |
|--------|-------|
| Handle 1 | `room.encounter_rate_modifier` |
| Handle 2 | `npc.aggro_radius_modifier` |
| Cooldown | 30 minutes |
| Hostile Clamp | +100% encounter rate, +50% aggro radius |
| Favorable Clamp | -50% encounter rate, -50% aggro radius |
| Threshold | Hostile: < -0.4, Favorable: > +0.4 |

**Hostile behaviors:**
- More frequent hostile encounters
- Animals attack sooner (larger aggro radius)
- Predators drawn to location

**Favorable behaviors:**
- Fewer hostile encounters
- Animals flee before combat starts
- Peaceful creatures approach

**Hostile tells:**
- "Something watches from the shadows."
- "Wolves circle at the edge of vision."
- "The forest's creatures are restless."
- "Eyes gleam in the underbrush."

**Favorable tells:**
- "The usual dangers keep their distance."
- "A deer watches you calmly."
- "Birdsong fills the air."
- "Small creatures go about their business, unconcerned."

**Counterplay:** Abstention from hunting/harm; offerings of food.

---

## 4. Resource Scarcity

**Concept:** The land yields grudgingly to those it dislikes.

| Aspect | Value |
|--------|-------|
| Handle | `harvest.yield_modifier` |
| Cooldown | 2 hours |
| Hostile Clamp | -40% yield |
| Favorable Clamp | +40% yield |
| Threshold | Hostile: < -0.25, Favorable: > +0.25 |

**Affected resources:**
- Herb gathering
- Mining nodes
- Fishing yields
- Hunting returns
- Forage results

**Hostile tells:**
- "The herbs here are sparse and withered."
- "This vein has gone barren."
- "The fish aren't biting."
- "What you seek remains hidden."

**Favorable tells:**
- "Rich deposits practically surface themselves."
- "Herbs grow thick and healthy here."
- "The land gives freely."
- "Hidden abundance reveals itself."

**Counterplay:** Planting, restoration, offerings.

---

## 5. Spell Side-Effects

**Concept:** Magic resonates with or against the land's disposition.

| Aspect | Value |
|--------|-------|
| Handle 1 | `spell.power_modifier` |
| Handle 2 | `spell.backfire_chance` |
| Cooldown | Per-spell (no location cooldown) |
| Hostile Clamp | -25% power, +10% backfire |
| Favorable Clamp | +25% power, -5% backfire |
| Threshold | Hostile: < -0.35, Favorable: > +0.35 |

**Special rule for fire magic in forests:**
If location has `valuation.harm.fire < -0.5` AND spell is fire-based:
- Additional -15% power penalty
- Additional +10% backfire chance
- Even favorable affinity cannot fully negate (hostile land hates fire)

**Hostile tells:**
- "Your magic feels sluggish here."
- "The weave resists your touch."
- "Something dampens your power."
- "The spell sputters unexpectedly."

**Favorable tells:**
- "Magic flows easily here."
- "Your spell flares bright."
- "The land lends its strength."
- "Power wells up from the earth."

**Backfire examples:**
- Fire spell: sparks burn caster
- Healing spell: partial effect only
- Summoning: creature arrives hostile
- Teleport: short distance off

**Counterplay:** Ritual magic to attune; offerings at ley lines.

---

## 6. Rest Quality

**Concept:** Sleep and healing affected by the land's disposition.

| Aspect | Value |
|--------|-------|
| Handle | `rest.healing_modifier` |
| Cooldown | 8 hours (once per rest) |
| Hostile Clamp | -30% healing |
| Favorable Clamp | +30% healing |
| Threshold | Hostile: < -0.2, Favorable: > +0.2 |

**Hostile tells:**
- "Sleep comes fitfully."
- "You wake more tired than when you lay down."
- "Uneasy dreams trouble your rest."
- "The ground is cold and hard."
- "You startle awake repeatedly."

**Favorable tells:**
- "Deep, restorative sleep."
- "You wake refreshed and ready."
- "Peaceful dreams of distant places."
- "The earth cradles you gently."
- "Morning comes too soon, but you feel renewed."

**Counterplay:** Time without aggression; offerings before sleep.

---

## 7. Ambient Messaging

**Concept:** Room descriptions subtly shift based on affinity. Flavor only, but shapes perception.

| Aspect | Value |
|--------|-------|
| Handle | `null` (flavor only) |
| Cooldown | 1 hour |
| Threshold | Any non-neutral |

**Implementation:**
- Inject atmospheric sentences into room descriptions
- Never explicit about affinity ("the forest hates you")
- Always deniable as natural description

**Hostile atmosphere layers:**
| Affinity | Tone |
|----------|------|
| -0.25 to -0.4 | Uneasy | "Something feels off here." |
| -0.4 to -0.6 | Watchful | "You can't shake the feeling of being observed." |
| -0.6 to -0.8 | Oppressive | "The air itself seems heavy with disapproval." |
| -0.8 to -1.0 | Menacing | "Every shadow seems to reach toward you." |

**Favorable atmosphere layers:**
| Affinity | Tone |
|----------|------|
| +0.25 to +0.4 | Pleasant | "The light seems warmer here." |
| +0.4 to +0.6 | Welcoming | "You feel oddly at home." |
| +0.6 to +0.8 | Protected | "A sense of safety settles over you." |
| +0.8 to +1.0 | Blessed | "The very air seems to embrace you." |

**Counterplay:** Naturally improves with affinity.

---

## 8. Loot Quality

**Concept:** Found items are better or worse based on affinity.

| Aspect | Value |
|--------|-------|
| Handle | `loot.quality_modifier` |
| Cooldown | 1 hour |
| Hostile Clamp | -2 quality tiers |
| Favorable Clamp | +2 quality tiers |
| Threshold | Hostile: < -0.3, Favorable: > +0.3 |

**Hostile tells:**
- "Rust and decay everywhere."
- "The chest's contents are disappointing."
- "Moths have been at this."
- "Whatever was here, time has claimed it."

**Favorable tells:**
- "Something glints in the corner."
- "Remarkably well-preserved."
- "A hidden cache reveals itself."
- "The best of the lot, as if waiting for you."

**Counterplay:** Time, offerings, recovery actions.

---

## 9. Weather Microclimate

**Concept:** Local weather shifts subtly for or against you.

| Aspect | Value |
|--------|-------|
| Handle | `null` (flavor only, but can affect mechanics) |
| Cooldown | 4 hours |
| Threshold | Hostile: < -0.4, Favorable: > +0.4 |

**Implementation:**
- Subtle variations in described weather
- Can optionally affect visibility, tracking, fire-starting

**Hostile tells:**
- "A sudden chill wind picks up."
- "Clouds gather overhead."
- "Mist rolls in unexpectedly."
- "The sun finds a cloud just as you arrive."

**Favorable tells:**
- "The clouds part briefly."
- "A warm breeze carries pleasant scents."
- "The mist clears as you approach."
- "Sunlight follows your path."

**Counterplay:** Seasonal rituals; weather-appropriate offerings.

---

## 10. Animal Messengers

**Concept:** Creatures behave as omens—warnings or welcomes.

| Aspect | Value |
|--------|-------|
| Handle | `null` (flavor only) |
| Cooldown | 2 hours |
| Threshold | Any non-neutral |

**Hostile tells:**
- "A crow follows overhead, watching."
- "Rats scatter at your approach."
- "A fox regards you with unusual intensity."
- "Insects swarm thicker here."
- "Something howls in the distance—at you, it seems."

**Favorable tells:**
- "A songbird alights nearby."
- "Butterflies dance in your wake."
- "A doe raises her head, unafraid."
- "Bees hum peacefully as you pass."
- "A hawk circles lazily above—a good omen."

**Counterplay:** Abstention from hunting; feeding wildlife.

---

## Admin Configuration

All affordances support admin toggles:

```yaml
# Location-level overrides
affordances:
  pathing:
    enabled: true
    debug_mode: false  # Log all evaluations
    force_hostile: false  # For testing
    force_favorable: false  # For testing

  misleading_navigation:
    enabled: true
    max_redirect_probability: 0.15
    require_adjacent_safe: true
```

**Admin commands:**
- `affordance/toggle <location> <affordance> [on|off]` — Enable/disable
- `affordance/test <location> <affordance> hostile` — Force trigger for testing
- `affordance/log <location>` — Show recent affordance triggers
- `affordance/reset <location>` — Clear all cooldowns

---

## Probability Cascade

When multiple affordances might trigger, they roll independently but narratively chain:

1. Check each affordance's threshold
2. Roll against probability (base × affinity factor)
3. Apply cooldowns
4. Concatenate tells for narrative flow

**Example hostile cascade:**
"The path twists unexpectedly. Wolves circle at the edge of vision. The herbs here are sparse and withered."

**Example favorable cascade:**
"An easy trail opens before you. Birdsong fills the air. Rich deposits practically surface themselves."

---

## Testing Checklist

For each affordance, verify:

- [ ] Triggers at correct affinity threshold
- [ ] Respects cooldown
- [ ] Severity clamp prevents extreme effects
- [ ] Admin toggle works
- [ ] No player-visible affinity values
- [ ] Tells are indirect and deniable
- [ ] Mechanical handle modifies correct value
- [ ] Counterplay is documented and achievable

---

*End of catalog.*
