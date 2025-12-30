"""
Pytest configuration for affinity system tests.
"""

import sys
from pathlib import Path

import pytest

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


# =============================================================================
# VALIDATION ON TEST RUN
# =============================================================================

def pytest_configure(config):
    """
    Validate affordance definitions before running tests.

    This ensures bad YAML/configuration can't ship - validation errors
    surface as test collection failures.
    """
    from world.affinity.affordances import validate_affordance_definitions
    from world.affinity.validation import AffordanceValidationError

    try:
        validate_affordance_definitions()
    except AffordanceValidationError as e:
        pytest.fail(f"Affordance validation failed:\n{e}", pytrace=False)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def validation_strict():
    """
    Fixture that ensures affordance validation is enforced.

    Use this in tests that specifically test validation behavior.
    """
    from world.affinity.affordances import validate_affordance_definitions
    validate_affordance_definitions()
    return True
