# State of the World

**Affinity**: Locations accumulate memory traces from events; these shape world behavior toward actors through indirect affordances (no visible meters).

**Tuning**: `config/affinity_defaults.yaml` — half-lives, thresholds, probabilities, anti-griefing caps.

**Rules**: `docs/DO_NOT.md` — hard constraints (no visible meters, ≤2 handles per affordance, no invented stats).

**Validate**:
```bash
python -m tests.smoke_validate      # standalone, no pytest needed
python -m pytest tests/ -v          # full suite (82 tests)
```

**Replay**: `AffordanceSnapshot` stores final values; `replay_and_assert()` recomputes and asserts match.

**Invariants**:
- All affordances have ≤2 mechanical handles (validated at module load)
- All tells are narrative-only (no meter patterns like "+5", "25%")
- Replay is deterministic: snapshot stores final_adjustments, final_tells, final_redirect_target

**Next**:
- Wire YAML config loader to `set_config()`
- Add persistence layer for traces
- Integrate with Evennia command hooks
