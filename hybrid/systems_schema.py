# hybrid/systems_schema.py
"""Schema defaults for ship systems and subsystem health."""

SUBSYSTEM_HEALTH_SCHEMA = {
    "power": {
        "max_health": 120.0,
        "criticality": 5.0,
        "failure_threshold": 0.2,
    },
    "propulsion": {
        "max_health": 110.0,
        "criticality": 5.0,
        "failure_threshold": 0.25,
    },
    "sensors": {
        "max_health": 90.0,
        "criticality": 3.0,
        "failure_threshold": 0.2,
    },
    "weapons": {
        "max_health": 100.0,
        "criticality": 4.0,
        "failure_threshold": 0.25,
    },
}


def get_subsystem_health_schema() -> dict:
    """Return default subsystem health schema."""
    return SUBSYSTEM_HEALTH_SCHEMA.copy()
