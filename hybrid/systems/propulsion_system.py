# hybrid/systems/propulsion_system.py
"""Propulsion system providing thrust and fuel management."""

from hybrid.core.base_system import BaseSystem
import math
import logging

logger = logging.getLogger(__name__)

class PropulsionSystem(BaseSystem):
    """Manages ship propulsion and thrust."""

    def __init__(self, config=None):
        super().__init__(config)
        config = config or {}

        # Power usage
        self.power_draw = config.get("power_draw", 10.0)
        self.power_draw_per_thrust = config.get("power_draw_per_thrust", 0.5)

        # Main drive configuration
        self.max_thrust = float(config.get("max_thrust", 100.0))
        self.main_drive = {
            "thrust": {"x": 0.0, "y": 0.0, "z": 0.0},
            "max_thrust": self.max_thrust,
        }

        # Fuel and efficiency
        self.efficiency = float(config.get("efficiency", 0.9))
        self.fuel_consumption = float(config.get("fuel_consumption", 0.1))
        self.max_fuel = float(config.get("max_fuel", 1000.0))
        self.fuel_level = float(config.get("fuel_level", self.max_fuel))

        # Tracking
        self.current_thrust = {"x": 0.0, "y": 0.0, "z": 0.0}
        self.power_status = True
        self.status = "idle"

    def tick(self, dt, ship, event_bus):
        if not self.enabled:
            ship.thrust = {"x": 0.0, "y": 0.0, "z": 0.0}
            ship.acceleration = {"x": 0.0, "y": 0.0, "z": 0.0}
            self.main_drive["thrust"] = {"x": 0.0, "y": 0.0, "z": 0.0}
            self.status = "offline"
            return

        thrust = self.main_drive["thrust"]
        magnitude = math.sqrt(thrust["x"]**2 + thrust["y"]**2 + thrust["z"]**2)
        total_power = self.power_draw + (self.power_draw_per_thrust * magnitude * dt)
        power_system = ship.systems.get("power")
        if power_system and not power_system.request_power(total_power, "propulsion"):
            logger.warning(f"Propulsion on {ship.id} reduced due to power shortage")
            self.main_drive["thrust"] = {"x": 0.0, "y": 0.0, "z": 0.0}
            if self.power_status:
                self.power_status = False
                event_bus.publish("propulsion_power_loss", None, "propulsion")
        elif not self.power_status:
            self.power_status = True
            event_bus.publish("propulsion_power_restored", None, "propulsion")

        thrust_mag = math.sqrt(ship.thrust["x"]**2 + ship.thrust["y"]**2 + ship.thrust["z"]**2)
        if thrust_mag > 0:
            consumption = (thrust_mag / self.max_thrust) * self.fuel_consumption * dt
            if self.fuel_level >= consumption:
                self.fuel_level -= consumption
                ship.acceleration = {
                    "x": ship.thrust["x"] / ship.mass,
                    "y": ship.thrust["y"] / ship.mass,
                    "z": ship.thrust["z"] / ship.mass,
                }
                self.status = "active"
            else:
                ship.thrust = {"x": 0.0, "y": 0.0, "z": 0.0}
                ship.acceleration = {"x": 0.0, "y": 0.0, "z": 0.0}
                self.fuel_level = 0.0
                self.status = "no_fuel"
                event_bus.publish("propulsion_status_change", {"system": "propulsion", "status": "no_fuel"})
        else:
            ship.acceleration = {"x": 0.0, "y": 0.0, "z": 0.0}
            self.status = "idle"

        if magnitude > 10.0:
            event_bus.publish("signature_spike", {"duration": 3.0, "magnitude": magnitude}, "propulsion")

    # ----- Commands -----
    def command(self, action, params):
        if action == "set_thrust":
            return self.set_thrust(params)
        if action == "refuel":
            return self.refuel(params)
        if action == "emergency_stop":
            return self.emergency_stop()
        if action == "status":
            return self.get_state()
        if action == "power_on":
            return self.power_on()
        if action == "power_off":
            return self.power_off()
        return super().command(action, params)

    def set_thrust(self, params):
        if not self.enabled:
            return {"error": "Propulsion system is disabled"}
        x = float(params.get("x", self.main_drive["thrust"]["x"]))
        y = float(params.get("y", self.main_drive["thrust"]["y"]))
        z = float(params.get("z", self.main_drive["thrust"]["z"]))
        magnitude = math.sqrt(x**2 + y**2 + z**2)
        if magnitude > self.max_thrust:
            scale = self.max_thrust / magnitude
            x *= scale
            y *= scale
            z *= scale
        self.main_drive["thrust"] = {"x": x, "y": y, "z": z}
        self.current_thrust = dict(self.main_drive["thrust"])
        return {"status": "Thrust updated", "thrust": self.main_drive["thrust"]}

    def refuel(self, params):
        amount = float(params.get("amount", self.max_fuel - self.fuel_level))
        self.fuel_level = min(self.max_fuel, self.fuel_level + amount)
        return {
            "status": "Refueled",
            "amount": amount,
            "current_level": self.fuel_level,
            "max_fuel": self.max_fuel,
        }

    def emergency_stop(self):
        self.main_drive["thrust"] = {"x": 0.0, "y": 0.0, "z": 0.0}
        self.current_thrust = {"x": 0.0, "y": 0.0, "z": 0.0}
        return {"status": "Emergency stop activated", "thrust": self.main_drive["thrust"]}

    def get_thrust(self):
        return self.main_drive["thrust"]

    def get_state(self):
        state = super().get_state()
        state.update({
            "status": self.status,
            "main_drive": self.main_drive,
            "max_thrust": self.max_thrust,
            "current_thrust": self.current_thrust,
            "fuel_level": self.fuel_level,
            "fuel_percent": (self.fuel_level / self.max_fuel * 100) if self.max_fuel > 0 else 0,
            "max_fuel": self.max_fuel,
            "power_status": self.power_status,
        })
        return state
