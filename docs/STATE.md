# State of the World

**Affinity**: Locations accumulate memory traces from events; these shape world behavior toward actors through indirect affordances (no visible meters).

**Tuning**: `config/affinity_defaults.yaml` — half-lives, channel weights, affordance thresholds/probabilities/cooldowns. Loaded at import by `world/affinity/config.py`; `load_config_file(path)` swaps the core config at runtime (affordance parameters need a restart). Affordance `tells` in the YAML are not loaded yet; runtime tells live in `TELLS` in `affordances.py`.

**Game**: The repo root is an Evennia game dir. Five `AffinityRoom`s (`world/locations/*.yaml`, built by `world/build.py` on first start) store memory in `db.affinity_state` as plain data, so it persists. Player verbs (`burn`, `plant`, `offer`, `hunt`, `forage`, `rest`) log events through `world/bridge.py`; exits ask the room being left about pathing and misleading navigation; arriving asks about ambient affordances. `AffordanceContext.affordances` limits each evaluation to the affordances that fit the action. Admin: `@affinity`, `@trace`, `@toggleaff`.

**Game-layer notes**: Only pathing (departure delay) and misleading navigation (redirect) have mechanical effects; the other handles (encounter rate, yield, healing, loot, spell power) have no game system yet, so those affordances show tells only (DO_NOT.md #4). Pathing's delay is `travel_time_modifier x travel_seconds` from the location file.

**Rules**: `docs/DO_NOT.md` — hard constraints (no visible meters, ≤2 handles per affordance, no invented stats).

**Validate**:
```bash
python -m tests.smoke_validate      # standalone, no pytest needed
python -m pytest tests/ -v          # full suite
```

**Replay**: `AffordanceSnapshot` stores final values; `replay_and_assert()` recomputes and asserts match.

**Invariants**:
- All affordances have ≤2 mechanical handles (validated at module load)
- YAML affordance names match the engine exactly (validated at module load)
- All tells are narrative-only (no meter patterns like "+5", "25%")
- Replay is deterministic: snapshot stores final_adjustments, final_tells, final_redirect_target

**Next**:
- Saturation never rises: `log_event` reads `location.saturation` but nothing updates it, so diminishing returns never apply
- Affinity bands: `get_threshold_label` uses ±0.3/±0.7; the YAML `affinity_bands` say ±0.25/±0.6 and are not loaded
- Load affordance `tells` from the YAML, or drop them there
- Systems for the remaining handles (encounters, harvesting, resting, spells) so their affordances do something
