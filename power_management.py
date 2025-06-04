"""Simplified power management system for ships.

This module implements a basic reactor, battery and bus based
power distribution model. It is independent from the more complex
`hybrid` power systems and is used by the simple simulation code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


class Reactor:
    """Simple reactor that ramps up output when started."""

    COLD = "cold"
    SPOOLING_UP = "spooling_up"
    READY = "ready"

    def __init__(self, max_output: float, ramp_rate: float = 100.0):
        self.max_output = max_output
        self.current_output = 0.0
        self.ramp_rate = ramp_rate
        self.state = self.COLD

    def start(self) -> None:
        if self.state == self.COLD:
            self.state = self.SPOOLING_UP

    def tick(self, dt: float) -> None:
        if self.state == self.SPOOLING_UP:
            self.current_output = min(
                self.max_output, self.current_output + self.ramp_rate * dt
            )
            if self.current_output >= self.max_output:
                self.state = self.READY
        elif self.state == self.READY:
            self.current_output = self.max_output


@dataclass
class Battery:
    capacity: float
    charge_rate: float
    current_charge: float = 0.0

    def charge(self, amount: float) -> None:
        self.current_charge = min(self.capacity, self.current_charge + amount)

    def discharge(self, amount: float) -> float:
        draw = min(self.current_charge, amount)
        self.current_charge -= draw
        return draw


@dataclass
class ShipSystem:
    name: str
    power_draw: float
    enabled: bool = True

    def toggle(self, state: bool) -> None:
        self.enabled = state


@dataclass
class PowerBus:
    name: str
    systems: List[ShipSystem] = field(default_factory=list)

    def calculate_demand(self) -> float:
        return sum(s.power_draw for s in self.systems if s.enabled)

    def distribute_power(self, available: float) -> float:
        """Return unused power after distribution."""
        demand = self.calculate_demand()
        used = min(demand, available)
        return available - used


class PowerManagementSystem:
    """Holds reactor, battery and power buses."""

    def __init__(self, config: Dict):
        self.reactor = Reactor(config.get("reactor_output_max", 1000))
        self.battery = Battery(
            config.get("battery_capacity", 500),
            config.get("battery_charge_rate", 50),
            config.get("battery_capacity", 500),
        )
        self.buses: Dict[str, PowerBus] = {
            "primary": PowerBus("primary"),
            "secondary": PowerBus("secondary"),
            "tertiary": PowerBus("tertiary"),
        }
        self.allocation = {
            "primary": 0.6,
            "secondary": 0.3,
            "tertiary": 0.1,
        }

    def set_allocation(self, primary: float, secondary: float, tertiary: float) -> None:
        total = max(primary + secondary + tertiary, 1.0)
        self.allocation = {
            "primary": primary / total,
            "secondary": secondary / total,
            "tertiary": tertiary / total,
        }

    def add_system(self, bus: str, system: ShipSystem) -> None:
        if bus in self.buses:
            self.buses[bus].systems.append(system)

    def toggle_system(self, name: str, state: bool) -> None:
        for bus in self.buses.values():
            for sys in bus.systems:
                if sys.name == name:
                    sys.toggle(state)

    def tick(self, dt: float) -> None:
        self.reactor.tick(dt)
        reactor_power = self.reactor.current_output
        remaining = reactor_power

        # Allocate power to each bus, battery supplements secondary if needed
        for bus_name, bus in self.buses.items():
            allocation = reactor_power * self.allocation[bus_name]
            if bus_name == "secondary" and allocation < bus.calculate_demand():
                deficit = bus.calculate_demand() - allocation
                drawn = self.battery.discharge(deficit)
                allocation += drawn
            remaining -= allocation
        # Excess power charges battery
        if remaining > 0:
            self.battery.charge(min(remaining, self.battery.charge_rate * dt))

    def get_status(self) -> Dict:
        return {
            "reactor_output": self.reactor.current_output,
            "reactor_state": self.reactor.state,
            "battery_charge": self.battery.current_charge,
            "allocation": self.allocation,
            "bus_demand": {b: self.buses[b].calculate_demand() for b in self.buses},
        }
