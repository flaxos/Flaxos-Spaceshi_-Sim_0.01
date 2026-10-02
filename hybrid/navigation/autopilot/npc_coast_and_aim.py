"""NPC combat coast phase: sensor line of sight, zero main-drive thrust."""

import math

from hybrid.navigation.autopilot.base import BaseAutopilot


def operator_controls_ship(ship):
    """Manual Helm input and queued commands take precedence over NPC aim."""
    nav = ship.systems.get("navigation")
    controller = getattr(nav, "controller", None)
    helm = ship.systems.get("helm")
    return (
        getattr(controller, "mode", None) == "manual_override"
        or bool(getattr(helm, "manual_override", False))
        or getattr(helm, "mode", None) == "manual"
        or bool(getattr(helm, "active_command", None))
        or bool(getattr(helm, "command_queue", None))
    )


class NPCCoastAndAimAutopilot(BaseAutopilot):
    """Face a live sensor contact while coasting inside the NPC weapon range.

    This phase changes only heading priority. Navigation and Helm apply the
    returned attitude through physical RCS; the existing weapon pipeline still
    solves ballistic lead and enforces every firing gate. Cached weapon leads
    and ship-truth fallbacks are deliberately not used for navigation aim.
    """

    def compute(self, dt, sim_time):
        nav = self.ship.systems.get("navigation")
        controller = getattr(nav, "controller", None)
        if controller and controller.autopilot is not self:
            return None
        if operator_controls_ship(self.ship):
            return None

        ai = getattr(self.ship, "ai_controller", None)
        target = getattr(ai, "current_target", None)
        behavior = getattr(getattr(ai, "behavior", None), "value", None)
        if (not getattr(self.ship, "ai_enabled", False)
                or behavior != "attack" or not target
                or target[0] != self.target_id):
            command = self._coast_hold("phase_ended")
            # A behavior change must release only this phase's own slot.
            if controller and controller.autopilot is self:
                cache_key = f"npc_coast_and_aim:{self.target_id}"
                if ai and ai._autopilot_set_for_target == cache_key:
                    ai._autopilot_set_for_target = None
                controller.disengage_autopilot(reason="NPC coast-and-aim phase ended")
            return command

        sensors = self.ship.systems.get("sensors")
        contact = sensors.get_contact(self.target_id) if sensors else None
        tracker = getattr(sensors, "contact_tracker", None)
        stale_threshold = getattr(tracker, "stale_threshold", 60.0)
        if (not contact or not getattr(sensors, "enabled", True)
                or getattr(contact.contact_state, "value", contact.contact_state) == "lost"
                or contact.is_stale(sim_time, stale_threshold)):
            return self._coast_hold("contact_lost")

        try:
            direction = [float(contact.position[axis]) - float(self.ship.position[axis])
                         for axis in ("x", "y", "z")]
        except (KeyError, TypeError, ValueError):
            return self._coast_hold("invalid_contact")
        if not all(math.isfinite(value) for value in direction):
            return self._coast_hold("invalid_contact")

        distance = math.hypot(*direction)
        if (distance > min(ai.weapon_range, ai.engagement_range)
                or distance < ai.profile.min_engagement_range
                or (ai._disengage_until is not None and sim_time < ai._disengage_until)):
            return self._coast_hold("repositioning")
        if distance < 1e-10:
            return self._coast_hold("coincident_contact")

        x, y, z = direction
        self.status = "aiming"
        return {
            "thrust": 0.0,
            "heading": {
                # Physical Quaternion.from_euler rotates +X toward -Z
                # for positive pitch. Keep the actual nose on the contact.
                "pitch": -math.degrees(math.atan2(z, math.hypot(x, y))),
                "yaw": math.degrees(math.atan2(y, x)),
                "roll": self.ship.orientation.get("roll", 0.0),
            },
        }

    def _coast_hold(self, status):
        self.status = status
        # Explicitly clear a latched thrust/attitude request while we own
        # navigation. Returning None would leave those requests in effect.
        return {"thrust": 0.0, "heading": dict(self.ship.orientation)}

    def get_state(self):
        state = super().get_state()
        state["phase"] = "coast_and_aim"
        return state
