# hybrid/systems/flight_computer/models.py
"""Data classes for the flight computer system."""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional


@dataclass
class BurnPlan:
    """Pre-execution estimate for a maneuver."""

    command: str = ""
    estimated_time: float = 0.0
    fuel_cost: float = 0.0
    delta_v: float = 0.0
    confidence: float = 1.0
    phases: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialise to plain dict for JSON transport."""
        return asdict(self)


@dataclass
class FlightComputerStatus:
    """Snapshot of the flight computer's state at a given tick."""

    mode: str = "idle"
    command: str = ""
    phase: str = ""
    progress: float = 0.0
    eta: float = 0.0
    status_text: str = "Flight computer standing by"
    burn_plan: Optional[BurnPlan] = None

    def to_dict(self) -> dict:
        """Serialise to plain dict."""
        d = asdict(self)
        if self.burn_plan is not None:
            d["burn_plan"] = self.burn_plan.to_dict()
        return d
