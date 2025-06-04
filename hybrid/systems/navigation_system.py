# hybrid/systems/navigation_system.py
"""Navigation system handling autopilot and course plotting."""

from hybrid.base_system import BaseSystem
import math
import logging

logger = logging.getLogger(__name__)

class NavigationSystem(BaseSystem):
    """Manages ship navigation and autopilot."""

    def __init__(self, config=None):
        super().__init__(config)
        config = config or {}

        # Power requirements
        self.power_draw = config.get("power_draw", 3.0)

        # Autopilot state
        self.autopilot_enabled = config.get("autopilot_enabled", False)
        self.autopilot = config.get("autopilot", self.autopilot_enabled)
        self.auto_avoidance = config.get("auto_avoidance", True)

        # Target and course parameters
        self.target = config.get("target", {
            "x": float(config.get("target_x", 0.0)),
            "y": float(config.get("target_y", 0.0)),
            "z": float(config.get("target_z", 0.0)),
        })
        self.thrust = float(config.get("thrust", 1.0))
        self.arrival_distance = float(config.get("arrival_distance", 1.0))
        self.approach_distance = float(config.get("approach_distance", 10.0))
        self.max_speed = float(config.get("max_speed", 100.0))
        self.braking_distance = float(config.get("braking_distance", 200.0))

        # Waypoint support
        self.waypoints = config.get("waypoints", [])
        self.current_waypoint = 0

        # Runtime state
        self.distance_to_target = 0.0
        self.status = "standby"

    def tick(self, dt, ship, event_bus):
        if not self.enabled:
            if self.autopilot_enabled or self.autopilot:
                self.autopilot_enabled = False
                self.autopilot = False
                event_bus.publish("navigation_autopilot_disengaged", None, "navigation")
            self.status = "offline"
            return

        power_system = ship.systems.get("power")
        if power_system and not power_system.request_power(self.power_draw * dt, "navigation"):
            if self.autopilot_enabled or self.autopilot:
                self.autopilot_enabled = False
                self.autopilot = False
                event_bus.publish("navigation_autopilot_disengaged", {"reason": "power_loss"}, "navigation")
            return

        # Determine active target
        tgt = self.target
        if not tgt and self.waypoints and self.current_waypoint < len(self.waypoints):
            tgt = self.waypoints[self.current_waypoint]
            self.target = tgt

        if not tgt or not (self.autopilot_enabled or self.autopilot):
            return

        # Distance to target
        pos = ship.position
        dx = tgt["x"] - pos["x"]
        dy = tgt["y"] - pos["y"]
        dz = tgt["z"] - pos["z"]
        dist = math.sqrt(dx**2 + dy**2 + dz**2)
        self.distance_to_target = dist

        # Check arrival / waypoint advancement
        if dist < max(self.arrival_distance, self.approach_distance):
            if self.waypoints and self.current_waypoint < len(self.waypoints) - 1:
                self.current_waypoint += 1
                self.target = self.waypoints[self.current_waypoint]
                event_bus.publish("navigation_waypoint_reached", {"waypoint": self.current_waypoint}, "navigation")
            else:
                self.autopilot_enabled = False
                self.autopilot = False
                self.status = "arrived"
                event_bus.publish("navigation_target_reached", None, "navigation")
                return

        self._autopilot_navigate(dt, ship, event_bus, dx, dy, dz, dist)
        self.status = "navigating"

    def _autopilot_navigate(self, dt, ship, event_bus, dx, dy, dz, dist):
        if dist == 0:
            return
        direction = {"x": dx / dist, "y": dy / dist, "z": dz / dist}

        desired_speed = self.max_speed
        if dist < self.braking_distance:
            braking_factor = dist / self.braking_distance
            desired_speed = self.max_speed * braking_factor

        desired_velocity = {axis: direction[axis] * desired_speed for axis in direction}
        velocity_error = {axis: desired_velocity[axis] - ship.velocity[axis] for axis in direction}
        kp = 1.0
        thrust = {axis: velocity_error[axis] * kp for axis in velocity_error}

        thrust_mag = math.sqrt(sum(v*v for v in thrust.values()))
        if thrust_mag > self.thrust:
            scale = self.thrust / thrust_mag
            for axis in thrust:
                thrust[axis] *= scale

        max_thrust = 100.0
        if "propulsion" in ship.systems and hasattr(ship.systems["propulsion"], "get_state"):
            prop_state = ship.systems["propulsion"].get_state()
            max_thrust = prop_state.get("max_thrust", 100.0)
        thrust_mag = math.sqrt(sum(v*v for v in thrust.values()))
        if thrust_mag > max_thrust:
            scale = max_thrust / thrust_mag
            for axis in thrust:
                thrust[axis] *= scale

        ship.thrust = thrust

    # ----- Commands -----
    def command(self, action, params):
        if action == "set_course":
            return self.set_course(params)
        if action == "autopilot":
            return self.set_autopilot(params)
        if action == "add_waypoint":
            return self.add_waypoint(params)
        if action == "clear_waypoints":
            return self.clear_waypoints()
        if action == "set_thrust":
            return self.set_autopilot_thrust(params)
        if action == "abort_course":
            return self.abort_course()
        if action == "status":
            return self.get_state()
        if action == "power_on":
            return self.power_on()
        if action == "power_off":
            return self.power_off()
        return super().command(action, params)

    def set_course(self, params):
        if not self.enabled:
            return {"error": "Navigation system is disabled"}
        target = params.get("target")
        if not target:
            target = {
                "x": float(params.get("x", 0)),
                "y": float(params.get("y", 0)),
                "z": float(params.get("z", 0)),
            }
        self.target = target
        self.autopilot_enabled = True
        self.autopilot = True
        return {"status": "Course set", "target": self.target}

    def set_autopilot(self, params):
        if not self.enabled:
            return {"error": "Navigation system is disabled"}
        if "enabled" in params:
            enabled = bool(params["enabled"])
            self.autopilot_enabled = enabled
            self.autopilot = enabled
        status = "enabled" if self.autopilot_enabled else "disabled"
        return {"status": f"Autopilot {status}", "autopilot": self.autopilot_enabled}

    def add_waypoint(self, params):
        if not self.enabled:
            return {"error": "Navigation system is disabled"}
        waypoint = {
            "x": float(params.get("x", 0)),
            "y": float(params.get("y", 0)),
            "z": float(params.get("z", 0)),
        }
        self.waypoints.append(waypoint)
        if len(self.waypoints) == 1 and not self.target:
            self.target = waypoint
        return {"status": "Waypoint added", "waypoint": waypoint, "waypoint_count": len(self.waypoints)}

    def clear_waypoints(self):
        self.waypoints = []
        self.current_waypoint = 0
        return {"status": "Waypoints cleared"}

    def set_autopilot_thrust(self, params):
        if "thrust" in params:
            self.thrust = float(params["thrust"])
        elif "value" in params:
            self.thrust = float(params["value"])
        return {"status": f"Autopilot thrust set to {self.thrust}", "thrust": self.thrust}

    def abort_course(self):
        self.autopilot_enabled = False
        self.autopilot = False
        self.status = "standby"
        return {"status": "Course aborted", "autopilot": False}

    def get_state(self):
        state = super().get_state()
        state.update({
            "status": self.status,
            "autopilot_enabled": self.autopilot_enabled,
            "target": self.target,
            "distance_to_target": self.distance_to_target,
            "approach_distance": self.approach_distance,
            "max_speed": self.max_speed,
            "braking_distance": self.braking_distance,
            "auto_avoidance": self.auto_avoidance,
            "thrust": self.thrust,
            "waypoints": self.waypoints,
            "current_waypoint": self.current_waypoint,
            "waypoint_count": len(self.waypoints),
        })
        return state
