# State of the World

**Affinity**: Locations accumulate memory traces from events; these shape how the world behaves toward actors through indirect affordances.

**Tuning**: `config/affinity_defaults.yaml` — half-lives, thresholds, probabilities, anti-griefing caps.

**Rules**: `docs/DO_NOT.md` — hard constraints (no visible meters, ≤2 handles, no invented stats).

**Validate**:
```bash
python -m tests.smoke_validate      # standalone, no pytest needed
python -m pytest tests/ -v          # full test suite
```

**Replay**: `AffordanceSnapshot` stores final values; `replay_and_assert()` recomputes and asserts match.

**Next**:
- Wire YAML config loader to `set_config()`
- Add persistence layer for traces
- Integrate with Evennia command hooks
