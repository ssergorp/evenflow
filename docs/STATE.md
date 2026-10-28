# State of the World

**Affinity**: Locations accumulate memory traces from events; these shape world behavior toward actors through indirect affordances (no visible meters).

**Tuning**: `config/affinity_defaults.yaml` — half-lives, channel weights, affordance thresholds/probabilities/cooldowns. Loaded at import by `world/affinity/config.py`; `load_config_file(path)` swaps the core config at runtime (affordance parameters need a restart). Affordance `tells` in the YAML are not loaded yet; runtime tells live in `TELLS` in `affordances.py`.

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
- Add persistence layer for traces
- Integrate with Evennia command hooks
