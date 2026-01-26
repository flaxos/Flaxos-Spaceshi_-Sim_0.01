# hybrid/navigation/plan.py
"""Flight plan data structures for navigation sequencing."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def _parse_optional_float(value: Any, label: str) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a number") from exc


@dataclass
class PlanTrigger:
    """Trigger conditions for a flight plan step."""

    distance_remaining: Optional[float] = None
    time_to_target: Optional[float] = None

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> Optional["PlanTrigger"]:
        if not data:
            return None

        distance_remaining = _parse_optional_float(
            data.get("distance_remaining"),
            "distance_remaining",
        )
        time_to_target = _parse_optional_float(
            data.get("time_to_target"),
            "time_to_target",
        )

        return cls(distance_remaining=distance_remaining, time_to_target=time_to_target)

    def to_dict(self) -> Dict[str, float]:
        payload: Dict[str, float] = {}
        if self.distance_remaining is not None:
            payload["distance_remaining"] = self.distance_remaining
        if self.time_to_target is not None:
            payload["time_to_target"] = self.time_to_target
        return payload


@dataclass
class FlightPlanStep:
    """A single flight plan step with optional trigger conditions."""

    action: str
    detail: str = ""
    trigger: Optional[PlanTrigger] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FlightPlanStep":
        if not isinstance(data, dict):
            raise ValueError("Plan step must be a dict")

        action = data.get("action")
        if not action:
            raise ValueError("Plan step missing action")

        detail = data.get("detail", "")
        trigger = PlanTrigger.from_dict(data.get("trigger"))
        return cls(action=str(action), detail=str(detail or ""), trigger=trigger)

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "action": self.action,
            "detail": self.detail,
        }
        if self.trigger:
            trigger_payload = self.trigger.to_dict()
            if trigger_payload:
                payload["trigger"] = trigger_payload
        return payload


@dataclass
class FlightPlan:
    """Ordered flight plan with trigger-aware steps."""

    steps: List[FlightPlanStep] = field(default_factory=list)
    name: Optional[str] = None
    plan_type: Optional[str] = None
    target: Optional[Dict[str, Any]] = None
    source: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FlightPlan":
        if not isinstance(data, dict):
            raise ValueError("Plan payload must be a dict")

        steps_data = data.get("steps")
        if not isinstance(steps_data, list) or not steps_data:
            raise ValueError("Plan requires a non-empty steps list")

        steps = [FlightPlanStep.from_dict(step) for step in steps_data]
        name = data.get("name")
        plan_type = data.get("type") or data.get("plan_type")
        target = data.get("target")
        source = data.get("source")

        return cls(
            steps=steps,
            name=str(name) if name else None,
            plan_type=str(plan_type) if plan_type else None,
            target=target,
            source=str(source) if source else None,
        )

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "steps": [step.to_dict() for step in self.steps],
        }
        if self.name:
            payload["name"] = self.name
        if self.plan_type:
            payload["type"] = self.plan_type
        if self.target is not None:
            payload["target"] = self.target
        if self.source:
            payload["source"] = self.source
        return payload
