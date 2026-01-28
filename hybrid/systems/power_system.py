# hybrid/systems/power_system.py
"""Power generation, storage and distribution for ships."""

from hybrid.core.base_system import BaseSystem

class PowerSystem(BaseSystem):
    """Handles power generation, storage and distribution."""

    def __init__(self, config=None):
        super().__init__(config)
        config = config or {}

        # Generation and storage
        self.generation_rate = float(config.get("generation", 10.0))
        self.capacity = float(config.get("capacity", 100.0))
        self.stored_power = float(config.get("initial", self.capacity * 0.8))
        self.efficiency = float(config.get("efficiency", 0.95))
        self.allocations = config.get("allocations", {})
        self.base_generation_rate = self.generation_rate
        self.base_capacity = self.capacity
        self.base_efficiency = self.efficiency

        # Additional tracking
        self.generation = config.get("generation", 5.0)  # fallback for old configs
        self.current = config.get("current", self.capacity)
        self.total_draw = 0.0
        self.drawing_systems = {}
        self.status = "online"
        self._last_status = self.status
        self._last_generated = 0.0
        self._last_draw = 0.0

    def tick(self, dt, ship, event_bus):
        damage_factor = 1.0
        if ship is not None and hasattr(ship, "damage_model"):
            damage_factor = ship.damage_model.get_combined_factor("power")

        self.capacity = self.base_capacity * damage_factor
        self.generation_rate = self.base_generation_rate * damage_factor
        self.efficiency = self.base_efficiency * max(0.1, damage_factor)
        self.current = min(self.current, self.capacity)
        self.stored_power = min(self.stored_power, self.capacity)

        if damage_factor <= 0:
            self.status = "failed"
            event_bus.publish("power_failed", {"system": "power"})
            return

        if not self.enabled:
            self.status = "offline"
            event_bus.publish("power_offline", {"source": "power"})
            return

        generated = self.generation_rate * dt * self.efficiency
        self.stored_power = min(self.capacity, self.stored_power + generated)

        self.current = min(self.capacity, self.current + self.generation * dt)
        self._last_generated = generated
        self._last_draw = self.total_draw
        self.total_draw = 0.0
        self.drawing_systems = {}
        event_bus.publish("power_available", {"available": self.current, "capacity": self.capacity, "source": "power"})

        if self.stored_power <= 0:
            self.status = "critical"
            event_bus.publish("power_critical", {"system": "power"})
        elif self.stored_power < (self.capacity * 0.2):
            self.status = "low"
            event_bus.publish("power_low", {"system": "power", "level": self.stored_power / self.capacity, "source": "power"})
        else:
            self.status = "online"

        if self.status != self._last_status:
            event_bus.publish("power_state_change", {
                "ship_id": getattr(ship, "id", None),
                "status": self.status,
                "stored_power": self.stored_power,
                "capacity": self.capacity,
            })
            self._last_status = self.status

    def report_heat(self, ship, event_bus):
        if ship is None or not hasattr(ship, "damage_model"):
            return
        subsystem = ship.damage_model.subsystems.get("power")
        if not subsystem:
            return
        heat_amount = subsystem.heat_generation * (self._last_generated + self._last_draw)
        if heat_amount <= 0:
            return
        ship.damage_model.add_heat("power", heat_amount, event_bus, ship.id)

    def command(self, action, params):
        if action == "power_on":
            return self.power_on()
        if action == "power_off":
            return self.power_off()
        if action == "get_status" or action == "status":
            return self.get_state()
        if action == "boost_generation":
            boost_factor = float(params.get("factor", 1.5))
            self.generation_rate *= boost_factor
            return {"status": "Generation boosted", "factor": boost_factor, "rate": self.generation_rate}
        if action == "add_power":
            amount = float(params.get("amount", 0))
            self.stored_power = min(self.capacity, self.stored_power + amount)
            return {"status": "Power added", "amount": amount, "current": self.stored_power}
        if action == "set_generation":
            if "value" in params:
                self.generation = float(params["value"])
                self.generation_rate = self.generation
                return {"status": f"Power generation set to {self.generation}"}
        return super().command(action, params)

    def request_power(self, amount, system_name):
        if not self.enabled:
            return False
        if amount <= 0:
            return True
        self.drawing_systems[system_name] = amount
        self.total_draw += amount
        if self.current >= amount:
            self.current -= amount
            self.stored_power = max(0, self.stored_power - amount)
            return True
        return False

    def get_state(self):
        state = super().get_state()
        state.update({
            "status": self.status,
            "generation_rate": self.generation_rate,
            "capacity": self.capacity,
            "stored_power": self.stored_power,
            "percent": (self.stored_power / self.capacity * 100) if self.capacity > 0 else 0,
            "allocations": self.allocations,
            "generation": self.generation,
            "current": self.current,
            "total_draw": self.total_draw,
            "drawing_systems": self.drawing_systems,
        })
        return state
