#!/usr/bin/env python
"""
Smoke test: validate affordance definitions without pytest.

Run with:
    python -m tests.smoke_validate

This ensures validation can run in CI even before pytest is installed,
catching bad YAML/config as early as possible.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def main() -> int:
    """Run affordance validation and return exit code."""
    print("=" * 60)
    print("Smoke Test: Affordance Validation")
    print("=" * 60)

    try:
        # Import validation module
        from world.affinity.validation import (
            validate_all_affordances,
            validate_all_tells,
            AffordanceValidationError,
        )
        from world.affinity.affordances import (
            AFFORDANCE_DEFAULTS,
            TELLS,
            validate_affordance_definitions,
        )

        print("\n1. Running validate_affordance_definitions()...")
        validate_affordance_definitions()
        print("   PASS: All affordance definitions valid")

        print("\n2. Validating handle counts...")
        handle_counts = validate_all_affordances(AFFORDANCE_DEFAULTS)
        for aff_type, count in handle_counts.items():
            status = "OK" if count <= 2 else "FAIL"
            print(f"   [{status}] {aff_type}: {count} handle(s)")

        print("\n3. Validating tells...")
        tell_count = validate_all_tells(TELLS)
        print(f"   PASS: {tell_count} tells validated")

        print("\n" + "=" * 60)
        print("SMOKE TEST PASSED")
        print("=" * 60)
        return 0

    except AffordanceValidationError as e:
        print(f"\nVALIDATION FAILED:\n{e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"\nUNEXPECTED ERROR:\n{e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
