# hybrid/systems/power/management.py

from hybrid.core.constants import POWER_LAYER_PRIORITIES
from hybrid.systems.power.reactor import Reactor
from hybrid.core.event_bus import EventBus

DEFAULT_POWER_ALLOCATION = {
    "primary": 0.5,
    "secondary": 0.3,
    "tertiary": 0.2,
}

DEFAULT_ENGINEERING_PROFILES = {
    "offensive": {
        "power_allocation": {
            "primary": 0.6,
            "secondary": 0.25,
            "tertiary": 0.15,
        },
        "overdrive_limits": {
            "primary": 1.2,
            "secondary": 1.0,
            "tertiary": 1.0,
        },
        "systems": {
            "railgun": {"enabled": True, "power_draw": 60.0},
            "pdc": {"enabled": True, "power_draw": 18.0},
            "ecm": {"enabled": False, "power_draw": 0.0},
            "eccm": {"enabled": False, "power_draw": 0.0},
        },
    },
    "defensive": {
        "power_allocation": {
            "primary": 0.4,
            "secondary": 0.4,
            "tertiary": 0.2,
        },
        "overdrive_limits": {
            "primary": 1.0,
            "secondary": 1.2,
            "tertiary": 1.0,
        },
        "systems": {
            "railgun": {"enabled": False, "power_draw": 40.0},
            "pdc": {"enabled": True, "power_draw": 22.0},
            "ecm": {"enabled": True, "power_draw": 12.0},
            "eccm": {"enabled": True, "power_draw": 10.0},
        },
    },
}

class PowerManagementSystem:
    def __init__(self, config):
        # config is a dict mapping layer_name → {capacity, output_rate, thermal_limit}
        # May also contain other keys like alert_threshold, system_map (ignored for now)
        self.reactors = {}
        self.system_map = config.get("system_map", {})
        self.power_allocation = self._normalize_allocation(
            config.get("power_allocation", DEFAULT_POWER_ALLOCATION)
        )
        self.overdrive_limits = {
            layer: float(limit)
            for layer, limit in config.get("overdrive_limits", {}).items()
        }
        self.engineering_profiles = config.get("engineering_profiles", DEFAULT_ENGINEERING_PROFILES)
        self.active_profile = None
        self._base_system_state = {}
        self._base_weapon_state = {}
        for layer_name, params in config.items():
            # Skip non-reactor configuration items (must be dicts)
            if not isinstance(params, dict):
                continue
            # Skip configuration metadata that isn't reactor params
            if layer_name in ('system_map', 'power_allocation', 'overdrive_limits', 'engineering_profiles'):
                continue
            base = Reactor(layer_name)
            # D6: Support "output" as alias for "capacity" for backward compatibility
            capacity = params.get("capacity") or params.get("output", base.capacity)
            self.reactors[layer_name] = Reactor(
                name=layer_name,
                capacity=capacity,
                output_rate=params.get("output_rate", base.output_rate),
                thermal_limit=params.get("thermal_limit", base.thermal_limit),
                fuel_capacity=params.get("fuel_capacity"),
                fuel_level=params.get("fuel_level"),
                fuel_consumption_rate=params.get("fuel_consumption_rate", 0.0),
                cooling_rate=params.get("cooling_rate", 1.5),
                heat_rate=params.get("heat_rate", 0.05),
                heat_per_kw=params.get("heat_per_kw", 0.1),
                overheat_output_factor=params.get("overheat_output_factor", 0.5),
            )
        self._base_reactors = {
            name: {
                "capacity": reactor.capacity,
                "output_rate": reactor.output_rate,
                "thermal_limit": reactor.thermal_limit,
            }
            for name, reactor in self.reactors.items()
        }
        self.event_bus = EventBus.get_instance()
        self._last_reactor_status = {}

    def tick(self, dt, ship=None, event_bus=None):
        damage_factor = 1.0
        if ship is not None and hasattr(ship, "damage_model"):
            damage_factor = ship.damage_model.get_degradation_factor("power")

        for reactor in self.reactors.values():
            base = self._base_reactors.get(reactor.name, {})
            if base:
                overdrive = self.overdrive_limits.get(reactor.name, 1.0)
                reactor.capacity = base["capacity"] * damage_factor * overdrive
                reactor.output_rate = base["output_rate"] * damage_factor * overdrive
                reactor.thermal_limit = base["thermal_limit"]
                reactor.available = min(reactor.available, reactor.capacity)

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
            "power_allocation": self.power_allocation,
            "overdrive_limits": self.overdrive_limits,
            "active_profile": self.active_profile,
            "profiles": sorted(self.engineering_profiles.keys()),
        }
        
        for name, reactor in self.reactors.items():
            reactor_state = {
                "name": name,
                "capacity": reactor.capacity,
                "available": getattr(reactor, 'available', reactor.capacity),
                "output_rate": reactor.output_rate,
                "thermal_limit": reactor.thermal_limit,
                "temperature": getattr(reactor, "temperature", 0.0),
                "fuel_capacity": getattr(reactor, "fuel_capacity", None),
                "fuel_level": getattr(reactor, "fuel_level", None),
                "status": getattr(reactor, 'status', 'nominal'),
            }
            if reactor_state["fuel_capacity"]:
                reactor_state["fuel_percent"] = (
                    reactor_state["fuel_level"] / reactor_state["fuel_capacity"] * 100
                    if reactor_state["fuel_capacity"] > 0 and reactor_state["fuel_level"] is not None
                    else 0.0
                )
            state["reactors"][name] = reactor_state
            state["total_capacity"] += reactor.capacity
            state["total_available"] += reactor_state["available"]
        
        return state

    def _normalize_allocation(self, allocation):
        if not allocation:
            return {}
        normalized = {key: float(value) for key, value in allocation.items()}
        total = sum(normalized.values())
        if total <= 0:
            return normalized
        return {key: value / total for key, value in normalized.items()}

    def set_power_allocation(self, allocation):
        normalized = self._normalize_allocation(allocation)
        self.power_allocation = normalized
        return {"status": "power_allocation_updated", "power_allocation": normalized}

    def set_overdrive_limits(self, limits):
        for layer, limit in limits.items():
            self.overdrive_limits[layer] = float(limit)
        return {"status": "overdrive_limits_updated", "overdrive_limits": self.overdrive_limits}

    def _cache_system_state(self, ship):
        for system_name, system in ship.systems.items():
            if hasattr(system, "enabled") or hasattr(system, "power_draw"):
                if system_name not in self._base_system_state:
                    self._base_system_state[system_name] = {
                        "enabled": getattr(system, "enabled", True),
                        "power_draw": getattr(system, "power_draw", 0.0),
                    }

        weapons_system = ship.systems.get("weapons")
        if weapons_system and hasattr(weapons_system, "weapons"):
            for weapon_name, weapon in weapons_system.weapons.items():
                if weapon_name not in self._base_weapon_state:
                    self._base_weapon_state[weapon_name] = {
                        "enabled": getattr(weapon, "enabled", True),
                        "power_cost": getattr(weapon, "power_cost", 0.0),
                    }

    def _apply_system_profile(self, ship, system_name, settings):
        weapons_system = ship.systems.get("weapons")
        if weapons_system and hasattr(weapons_system, "weapons"):
            weapon = weapons_system.weapons.get(system_name)
            if weapon:
                if "enabled" in settings:
                    weapon.enabled = bool(settings["enabled"])
                power_draw = settings.get("power_draw")
                if power_draw is not None:
                    power_cost = float(power_draw)
                    weapon.power_cost = power_cost
                    if hasattr(weapon, "base_power_cost"):
                        weapon.base_power_cost = power_cost
                return True

        system = ship.systems.get(system_name)
        if system and (hasattr(system, "enabled") or hasattr(system, "power_draw")):
            if "enabled" in settings and hasattr(system, "enabled"):
                system.enabled = bool(settings["enabled"])
            power_draw = settings.get("power_draw")
            if power_draw is not None and hasattr(system, "power_draw"):
                system.power_draw = float(power_draw)
            return True

        return False

    def apply_profile(self, profile_name, ship=None):
        profile = self.engineering_profiles.get(profile_name)
        if not profile:
            return {"error": f"Unknown power profile: {profile_name}"}

        if "power_allocation" in profile:
            self.set_power_allocation(profile["power_allocation"])

        if "overdrive_limits" in profile:
            self.set_overdrive_limits(profile["overdrive_limits"])

        if ship and "systems" in profile:
            self._cache_system_state(ship)
            for system_name, settings in profile["systems"].items():
                self._apply_system_profile(ship, system_name, settings)

        self.active_profile = profile_name
        return {
            "status": "power_profile_applied",
            "profile": profile_name,
            "power_allocation": self.power_allocation,
            "overdrive_limits": self.overdrive_limits,
        }

    def get_profiles(self):
        return {
            "profiles": sorted(self.engineering_profiles.keys()),
            "active_profile": self.active_profile,
            "definitions": self.engineering_profiles,
        }

    def command(self, action, params):
        if action == "set_power_profile":
            profile = params.get("profile") or params.get("mode")
            ship = params.get("ship")
            if not profile:
                return {"error": "Missing profile parameter"}
            return self.apply_profile(profile, ship=ship)
        if action == "get_power_profiles":
            return self.get_profiles()
        if action == "set_power_allocation":
            allocation = params.get("allocation")
            if allocation is None:
                valid_layers = set(self.reactors.keys()) or set(DEFAULT_POWER_ALLOCATION.keys())
                allocation = {key: value for key, value in params.items() if key in valid_layers}
            if not allocation:
                return {"error": "Missing allocation values"}
            return self.set_power_allocation(allocation)
        if action == "set_overdrive_limits":
            limits = params.get("limits", params)
            return self.set_overdrive_limits(limits)
        return {"error": f"Unknown power management command: {action}"}
