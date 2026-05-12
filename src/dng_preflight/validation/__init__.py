"""Plan-time validation: hard stops invoked before any generator runs."""

from dng_preflight.validation.hard_stops import (
    HardStop,
    Severity,
    validate_plan,
)

__all__ = ["HardStop", "Severity", "validate_plan"]
