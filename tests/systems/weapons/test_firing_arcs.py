# tests/systems/weapons/test_firing_arcs.py
"""Tests for weapon firing arc enforcement.

Firing arcs are defined in ship-relative coordinates (0 azimuth = ship nose).
The arc check must convert world-space aim direction into ship-relative
bearing before comparing against the arc limits. Without this conversion,
a ship facing any direction other than +X would have incorrect arc results.
"""

import pytest
import math

from hybrid.systems.weapons.truth_weapons import create_railgun, create_pdc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _corvette_railgun_arc() -> dict:
    """Corvette railgun arc from ship_classes/corvette.json."""
    return {
        "azimuth_min": -30,
        "azimuth_max": 30,
        "elevation_min": -20,
        "elevation_max": 20,
    }


def _compute_solution(weapon, target_pos, shooter_heading, shooter_pos=None):
    """Compute a firing solution with the given geometry.

    Returns the FiringSolution for inspection.
    """
    if shooter_pos is None:
        shooter_pos = {"x": 0, "y": 0, "z": 0}
    return weapon.calculate_solution(
        shooter_pos=shooter_pos,
        shooter_vel={"x": 0, "y": 0, "z": 0},
        target_pos=target_pos,
        target_vel={"x": 0, "y": 0, "z": 0},
        target_id="target_1",
        sim_time=10.0,
        shooter_heading=shooter_heading,
    )


# ---------------------------------------------------------------------------
# Tests: railgun with +/-30 degree azimuth arc
# ---------------------------------------------------------------------------

class TestFiringArcEnforcement:
    """Verify that weapon firing arcs reject targets outside the arc."""

    def test_target_dead_ahead_in_arc(self):
        """Target directly ahead of the ship — well within +/-30 deg arc."""
        railgun = create_railgun("railgun_1")
        railgun.firing_arc = _corvette_railgun_arc()

        # Ship faces +X (yaw=0), target at +X
        solution = _compute_solution(
            railgun,
            target_pos={"x": 50000, "y": 0, "z": 0},
            shooter_heading={"pitch": 0, "yaw": 0, "roll": 0},
        )
        assert solution.in_arc is True, (
            f"Target dead ahead should be in arc, got in_arc={solution.in_arc}"
        )

    def test_target_90_degrees_off_bow_out_of_arc(self):
        """Target at 90 deg off the bow — clearly outside +/-30 deg arc."""
        railgun = create_railgun("railgun_1")
        railgun.firing_arc = _corvette_railgun_arc()

        # Ship faces +X (yaw=0), target at +Y (90 deg off bow)
        solution = _compute_solution(
            railgun,
            target_pos={"x": 0, "y": 50000, "z": 0},
            shooter_heading={"pitch": 0, "yaw": 0, "roll": 0},
        )
        assert solution.in_arc is False, (
            f"Target 90 deg off bow should be outside arc, "
            f"got in_arc={solution.in_arc}"
        )

    def test_target_behind_ship_out_of_arc(self):
        """Target directly behind the ship — outside forward arc."""
        railgun = create_railgun("railgun_1")
        railgun.firing_arc = _corvette_railgun_arc()

        # Ship faces +X, target at -X (180 deg off bow)
        solution = _compute_solution(
            railgun,
            target_pos={"x": -50000, "y": 0, "z": 0},
            shooter_heading={"pitch": 0, "yaw": 0, "roll": 0},
        )
        assert solution.in_arc is False

    def test_target_at_arc_edge_inside(self):
        """Target at ~25 degrees off bow — inside the 30 deg limit."""
        railgun = create_railgun("railgun_1")
        railgun.firing_arc = _corvette_railgun_arc()

        # Place target at ~25 deg off-axis: atan2(y, x) ~ 25 deg
        # tan(25 deg) ~ 0.466 => y = 0.466 * x
        solution = _compute_solution(
            railgun,
            target_pos={"x": 50000, "y": 23300, "z": 0},
            shooter_heading={"pitch": 0, "yaw": 0, "roll": 0},
        )
        assert solution.in_arc is True, (
            f"Target ~25 deg off bow should be inside +/-30 arc"
        )

    def test_target_at_arc_edge_outside(self):
        """Target at ~35 degrees off bow — just outside the 30 deg limit."""
        railgun = create_railgun("railgun_1")
        railgun.firing_arc = _corvette_railgun_arc()

        # tan(35 deg) ~ 0.700 => y = 0.700 * x
        solution = _compute_solution(
            railgun,
            target_pos={"x": 50000, "y": 35000, "z": 0},
            shooter_heading={"pitch": 0, "yaw": 0, "roll": 0},
        )
        assert solution.in_arc is False, (
            f"Target ~35 deg off bow should be outside +/-30 arc"
        )

    def test_arc_respects_ship_heading(self):
        """Arc check must use ship-relative bearing, not world-space angles.

        This is the core regression test: if the ship faces +Y (yaw=90)
        and the target is directly ahead at +Y, the target should be in
        arc even though its world-space azimuth is 90 degrees.
        """
        railgun = create_railgun("railgun_1")
        railgun.firing_arc = _corvette_railgun_arc()

        # Ship faces +Y (yaw=90), target directly ahead at +Y
        solution = _compute_solution(
            railgun,
            target_pos={"x": 0, "y": 50000, "z": 0},
            shooter_heading={"pitch": 0, "yaw": 90, "roll": 0},
        )
        assert solution.in_arc is True, (
            f"Target dead ahead of a yaw=90 ship should be in arc. "
            f"Arc check must use ship-relative bearing, not world-space."
        )

    def test_arc_rejects_when_ship_turns_away(self):
        """If the ship turns so the target is off-axis, arc should reject.

        Ship faces -X (yaw=180), target at +X => 180 deg off bow => out of arc.
        """
        railgun = create_railgun("railgun_1")
        railgun.firing_arc = _corvette_railgun_arc()

        solution = _compute_solution(
            railgun,
            target_pos={"x": 50000, "y": 0, "z": 0},
            shooter_heading={"pitch": 0, "yaw": 180, "roll": 0},
        )
        assert solution.in_arc is False

    def test_elevation_arc_enforcement(self):
        """Target above the elevation limit should be out of arc."""
        railgun = create_railgun("railgun_1")
        railgun.firing_arc = _corvette_railgun_arc()  # elevation: +/-20 deg

        # Target high above: z >> x => elevation > 20 deg
        # atan2(30000, 50000) ~ 31 deg elevation
        solution = _compute_solution(
            railgun,
            target_pos={"x": 50000, "y": 0, "z": 30000},
            shooter_heading={"pitch": 0, "yaw": 0, "roll": 0},
        )
        assert solution.in_arc is False, (
            f"Target at ~31 deg elevation should be outside +/-20 deg limit"
        )

    def test_elevation_within_limits(self):
        """Target slightly above — within the elevation limit."""
        railgun = create_railgun("railgun_1")
        railgun.firing_arc = _corvette_railgun_arc()

        # atan2(10000, 50000) ~ 11.3 deg elevation — inside +/-20
        solution = _compute_solution(
            railgun,
            target_pos={"x": 50000, "y": 0, "z": 10000},
            shooter_heading={"pitch": 0, "yaw": 0, "roll": 0},
        )
        assert solution.in_arc is True

    def test_no_arc_constraint_always_in_arc(self):
        """Weapon with no firing_arc should always report in_arc=True."""
        railgun = create_railgun("railgun_1")
        # firing_arc defaults to None

        solution = _compute_solution(
            railgun,
            target_pos={"x": 0, "y": 50000, "z": 0},
            shooter_heading={"pitch": 0, "yaw": 0, "roll": 0},
        )
        assert solution.in_arc is True

    def test_ready_to_fire_blocked_by_arc(self):
        """When target is outside arc, ready_to_fire must be False."""
        railgun = create_railgun("railgun_1")
        railgun.firing_arc = _corvette_railgun_arc()

        solution = _compute_solution(
            railgun,
            target_pos={"x": 0, "y": 50000, "z": 0},
            shooter_heading={"pitch": 0, "yaw": 0, "roll": 0},
        )
        assert solution.in_arc is False
        assert solution.ready_to_fire is False
        assert "arc" in solution.reason.lower()

    def test_fire_returns_error_when_out_of_arc(self):
        """Calling fire() when out of arc should return an error."""
        railgun = create_railgun("railgun_1")
        railgun.firing_arc = _corvette_railgun_arc()

        # Compute solution with target outside arc
        _compute_solution(
            railgun,
            target_pos={"x": 0, "y": 50000, "z": 0},
            shooter_heading={"pitch": 0, "yaw": 0, "roll": 0},
        )

        # Charge the railgun fully so the charge gate doesn't mask the arc error
        if hasattr(railgun, '_charge_state'):
            from hybrid.systems.weapons.truth_weapons import ChargeState
            railgun._charge_state = ChargeState.READY
            railgun._charge_progress = 1.0

        result = railgun.fire(sim_time=10.0, power_manager=None)
        assert not result.get("ok")
        # The reason should mention the arc or not-ready (arc blocks ready_to_fire)
        reason = result.get("reason", "")
        assert "arc" in reason.lower() or "not ready" in reason.lower() or "Target outside" in reason


class TestPdcFiringArc:
    """PDC arcs are wider (hemisphere coverage) but should still enforce."""

    def test_dorsal_pdc_rejects_below(self):
        """Dorsal PDC (elevation 0-90) should reject targets below the ship."""
        pdc = create_pdc("pdc_1")
        pdc.firing_arc = {
            "azimuth_min": -120,
            "azimuth_max": 120,
            "elevation_min": 0,
            "elevation_max": 90,
        }

        # Target below: z = -5000, elevation ~ -5.7 deg (below 0)
        solution = _compute_solution(
            pdc,
            target_pos={"x": 500, "y": 0, "z": -500},
            shooter_heading={"pitch": 0, "yaw": 0, "roll": 0},
        )
        assert solution.in_arc is False, (
            "Dorsal PDC should reject targets below the ship (negative elevation)"
        )

    def test_dorsal_pdc_accepts_above(self):
        """Dorsal PDC should accept targets above the ship."""
        pdc = create_pdc("pdc_1")
        pdc.firing_arc = {
            "azimuth_min": -120,
            "azimuth_max": 120,
            "elevation_min": 0,
            "elevation_max": 90,
        }

        # Target above: z = +500, within azimuth and elevation
        solution = _compute_solution(
            pdc,
            target_pos={"x": 500, "y": 0, "z": 500},
            shooter_heading={"pitch": 0, "yaw": 0, "roll": 0},
        )
        assert solution.in_arc is True


class TestArcTelemetry:
    """Verify in_arc appears in weapon state telemetry."""

    def test_in_arc_in_get_state(self):
        """get_state() should include in_arc in the solution dict."""
        railgun = create_railgun("railgun_1")
        railgun.firing_arc = _corvette_railgun_arc()

        _compute_solution(
            railgun,
            target_pos={"x": 50000, "y": 0, "z": 0},
            shooter_heading={"pitch": 0, "yaw": 0, "roll": 0},
        )

        state = railgun.get_state()
        assert "solution" in state
        assert "in_arc" in state["solution"]
        assert state["solution"]["in_arc"] is True

    def test_out_of_arc_in_get_state(self):
        """get_state() should report in_arc=False when outside arc."""
        railgun = create_railgun("railgun_1")
        railgun.firing_arc = _corvette_railgun_arc()

        _compute_solution(
            railgun,
            target_pos={"x": 0, "y": 50000, "z": 0},
            shooter_heading={"pitch": 0, "yaw": 0, "roll": 0},
        )

        state = railgun.get_state()
        assert state["solution"]["in_arc"] is False
        assert "arc" in state["solution"]["reason"].lower()
