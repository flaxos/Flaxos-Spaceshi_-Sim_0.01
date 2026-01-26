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
            # D6: Support "output" as alias for "capacity" for backward compatibility
            capacity = params.get("capacity") or params.get("output", base.capacity)
            self.reactors[layer_name] = Reactor(
                name=layer_name,
                capacity=capacity,
                output_rate=params.get("output_rate", base.output_rate),
                thermal_limit=params.get("thermal_limit", base.thermal_limit)
            )
        self.event_bus = EventBus.get_instance()
        self._last_reactor_status = {}

    def tick(self, dt, ship=None, event_bus=None):
        for reactor in self.reactors.values():
            reactor.tick(dt)
            if reactor.status == "overheated":
                self.event_bus.publish("power_overheat", {"reactor": reactor.name})
            previous_status = self._last_reactor_status.get(reactor.name)
            if previous_status != reactor.status:
                self.event_bus.publish("reactor_status", {
                    "ship_id": getattr(ship, "id", None),
                    "reactor": reactor.name,
                    "status": reactor.status,
                    "available": reactor.available,
                    "capacity": reactor.capacity,
                })
                self._last_reactor_status[reactor.name] = reactor.status

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

    def reroute_power(self, amount, from_layer, to_layer):
        """
        Reroute power between layers.
        
        Args:
            amount (float): Amount of power to transfer
            from_layer (str): Source layer name
            to_layer (str): Destination layer name
            
        Returns:
            float: Amount of power actually transferred
        """
        source = self.reactors.get(from_layer)
        target = self.reactors.get(to_layer)
        
        if not source or not target:
            return 0.0
        
        # Calculate how much we can actually transfer
        available = getattr(source, 'available', source.capacity)
        transferable = min(amount, available)
        
        if transferable <= 0:
            return 0.0
        
        # Perform the transfer
        if self.transfer_output(from_layer, to_layer, transferable):
            return transferable
        return 0.0

    def get_state(self):
        """
        Get the current state of the power management system.
        
        Returns:
            dict: Power system state including all reactors
        """
        state = {
            "reactors": {},
            "total_capacity": 0.0,
            "total_available": 0.0,
        }
        
        for name, reactor in self.reactors.items():
            reactor_state = {
                "name": name,
                "capacity": reactor.capacity,
                "available": getattr(reactor, 'available', reactor.capacity),
                "output_rate": reactor.output_rate,
                "thermal_limit": reactor.thermal_limit,
                "status": getattr(reactor, 'status', 'nominal'),
            }
            state["reactors"][name] = reactor_state
            state["total_capacity"] += reactor.capacity
            state["total_available"] += reactor_state["available"]
        
        return state
