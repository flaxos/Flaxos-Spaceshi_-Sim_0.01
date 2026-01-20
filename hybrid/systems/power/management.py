# hybrid/systems/power/management.py

from hybrid.core.constants import POWER_LAYER_PRIORITIES
from hybrid.systems.power.reactor import Reactor
from hybrid.core.event_bus import EventBus

class PowerManagementSystem:
    def __init__(self, config):
        # config is a dict mapping layer_name → {capacity, output_rate, thermal_limit}
        # May also contain other keys like alert_threshold, system_map (ignored for now)
        self.reactors = {}
        for layer_name, params in config.items():
            # Skip non-reactor configuration items (must be dicts)
            if not isinstance(params, dict):
                continue
            # Skip configuration metadata that isn't reactor params
            if layer_name in ('system_map',):
                continue
            base = Reactor(layer_name)
            self.reactors[layer_name] = Reactor(
                name=layer_name,
                capacity=params.get("capacity", base.capacity),
                output_rate=params.get("output_rate", base.output_rate),
                thermal_limit=params.get("thermal_limit", base.thermal_limit)
            )
        self.event_bus = EventBus.get_instance()

    def tick(self, dt, ship=None, event_bus=None):
        for reactor in self.reactors.values():
            reactor.tick(dt)
            if reactor.status == "overheated":
                self.event_bus.publish("power_overheat", {"reactor": reactor.name})

    def request_power(self, amount, consumer):
        for layer in POWER_LAYER_PRIORITIES:
            reactor = self.reactors.get(layer)
            if reactor and reactor.draw_power(amount):
                return True
        self.event_bus.publish("power_insufficient", {"consumer": consumer, "amount": amount})
        return False

    def transfer_output(self, src, dest, amount):
        source = self.reactors.get(src)
        target = self.reactors.get(dest)
        if source and target and source.available >= amount:
            source.available -= amount
            target.available = min(target.capacity, target.available + amount)
            return True
        return False
