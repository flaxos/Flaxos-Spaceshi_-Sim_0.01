"""Power management system with layered reactors."""
from dataclasses import dataclass
from hybrid.core.base_system import BaseSystem

@dataclass
class PowerLayer:
    name: str
    output: float
    available: float
    status: str = "online"

    def reset(self):
        self.available = self.output
        self.status = "online"

class PowerManagementSystem(BaseSystem):
    """Manages power generation and distribution across three reactors."""

    DEFAULT_MAP = {
        "propulsion": "primary",
        "weapons": "primary",
        "sensors": "secondary",
        "defense": "secondary",
        "rcs": "secondary",
        "life_support": "tertiary",
        "bio_monitor": "tertiary",
    }

    def __init__(self, config=None):
        super().__init__(config)
        config = config or {}
        self.layers = {
            "primary": PowerLayer("primary", config.get("primary", {}).get("output", 100.0), 0.0),
            "secondary": PowerLayer("secondary", config.get("secondary", {}).get("output", 50.0), 0.0),
            "tertiary": PowerLayer("tertiary", config.get("tertiary", {}).get("output", 25.0), 0.0),
        }
        self.system_map = {**self.DEFAULT_MAP, **config.get("system_map", {})}
        self.alert_threshold = float(config.get("alert_threshold", 0.1))
        for layer in self.layers.values():
            layer.reset()

    def tick(self, dt, ship, event_bus):
        for layer in self.layers.values():
            layer.reset()
            if layer.available / layer.output < self.alert_threshold:
                if event_bus:
                    event_bus.publish("power_low", {"layer": layer.name, "available": layer.available})

    def request_power(self, amount, system_name, layer_name=None, event_bus=None):
        layer_name = layer_name or self.system_map.get(system_name, "tertiary")
        order = ["primary", "secondary", "tertiary"]
        start = order.index(layer_name)
        remaining = amount
        for lname in order[start:]:
            layer = self.layers[lname]
            if layer.available <= 0:
                continue
            if remaining <= layer.available:
                layer.available -= remaining
                return True
            else:
                remaining -= layer.available
                layer.available = 0
                layer.status = "overload"
                if event_bus:
                    event_bus.publish("power_overload", {"layer": lname, "request": amount})
        return False

    def reroute_power(self, amount, from_layer, to_layer):
        src = self.layers.get(from_layer)
        dest = self.layers.get(to_layer)
        if not src or not dest:
            return False
        moved = min(amount, src.available)
        src.available -= moved
        dest.available += moved
        return moved

    def get_state(self):
        state = super().get_state()
        state.update({lname: {"output": layer.output, "available": layer.available, "status": layer.status}
                      for lname, layer in self.layers.items()})
        return state

    def command(self, action, params):
        """Handle commands for the power manager."""
        if action in ("status", "get_state"):
            return self.get_state()
        elif action == "request_power":
            amount = float(params.get("amount", 0))
            system = params.get("system", "")
            layer = params.get("layer")
            success = self.request_power(amount, system, layer)
            return {"success": success, "state": self.get_state()}
        elif action == "reroute_power":
            amount = float(params.get("amount", 0))
            from_layer = params.get("from_layer", "primary")
            to_layer = params.get("to_layer", "secondary")
            moved = self.reroute_power(amount, from_layer, to_layer)
            return {"moved": moved, "state": self.get_state()}
        return super().command(action, params)
