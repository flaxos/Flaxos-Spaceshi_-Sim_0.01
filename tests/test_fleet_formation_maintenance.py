"""Tests for fleet formation maintenance wiring.

Verifies that FleetManager._maintain_formation() actually engages
formation autopilots on member ships, skips the flagship, and
re-uses existing autopilots instead of recreating them each tick.
"""

import numpy as np
import pytest

from hybrid.fleet.fleet_manager import FleetManager, FleetStatus
from hybrid.fleet.formation import FormationType


# ---------------------------------------------------------------------------
# Lightweight fakes -- just enough interface to satisfy FleetManager
# ---------------------------------------------------------------------------

class FakeNavController:
    """Mimics NavController with autopilot and program_name slots."""

    def __init__(self):
        self.autopilot = None
        self.autopilot_program_name = None


class FakeNavSystem:
    """Mimics NavigationSystem with set_autopilot and controller."""

    def __init__(self):
        self.controller = FakeNavController()
        self._last_params = None

    def set_autopilot(self, params: dict):
        """Record the call and fake-engage a formation autopilot."""
        self._last_params = params
        # Simulate what the real NavController.engage_autopilot does:
        # store program name and create a stub autopilot with flagship_id.
        self.controller.autopilot_program_name = params.get("program")
        self.controller.autopilot = _StubFormationAP(
            flagship_id=params.get("flagship_id"),
            relative_position=np.array(params.get("formation_position", [0, 0, 0]), dtype=float),
        )


class _StubFormationAP:
    """Minimal stand-in for FormationAutopilot."""

    def __init__(self, flagship_id: str, relative_position: np.ndarray):
        self.flagship_id = flagship_id
        self.relative_position = relative_position
        self.update_count = 0

    def update_formation_position(self, new_pos: np.ndarray):
        self.relative_position = np.array(new_pos, dtype=float)
        self.update_count += 1


class FakeShip:
    """Minimal ship with position/velocity dicts and systems."""

    def __init__(self, ship_id: str, x: float = 0, y: float = 0, z: float = 0,
                 vx: float = 0, vy: float = 0, vz: float = 0,
                 has_nav: bool = True):
        self.id = ship_id
        self.position = {"x": x, "y": y, "z": z}
        self.velocity = {"x": vx, "y": vy, "z": vz}
        self.orientation = {"yaw": 0.0, "pitch": 0.0, "roll": 0.0}
        self.systems = {}
        if has_nav:
            self.systems["navigation"] = FakeNavSystem()


class FakeSimulator:
    """Minimal simulator holding a ships dict."""

    def __init__(self, ships: dict):
        self.ships = ships


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_fleet(n_members: int = 2):
    """Create a FleetManager with a flagship and n_members wingmen.

    Returns (FleetManager, flagship, [wingmen]).
    """
    flagship = FakeShip("flagship", x=0, y=0, z=0)
    wingmen = [
        FakeShip(f"wing_{i}", x=1000 * (i + 1), y=0, z=0)
        for i in range(n_members)
    ]

    all_ships = {flagship.id: flagship}
    for w in wingmen:
        all_ships[w.id] = w

    sim = FakeSimulator(all_ships)
    fm = FleetManager(simulator=sim)
    fm.create_fleet(
        "alpha", "Alpha Squadron", "flagship",
        ship_ids=[w.id for w in wingmen],
    )
    fm.form_fleet("alpha", FormationType.LINE, spacing=2000.0)

    return fm, flagship, wingmen


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestMaintainFormationEngagesAutopilot:
    """Formation maintenance should engage autopilots on member ships."""

    def test_autopilot_engaged_on_wingmen(self):
        fm, flagship, wingmen = _build_fleet(2)

        # Ensure fleet is in FORMING so update triggers _maintain_formation
        fleet = fm.fleets["alpha"]
        assert fleet.status == FleetStatus.FORMING

        fm.update(dt=1.0)

        for w in wingmen:
            nav = w.systems["navigation"]
            assert nav._last_params is not None, (
                f"set_autopilot never called on {w.id}"
            )
            assert nav._last_params["program"] == "formation"
            assert nav._last_params["flagship_id"] == "flagship"

    def test_flagship_not_given_formation_autopilot(self):
        fm, flagship, wingmen = _build_fleet(2)
        fm.update(dt=1.0)

        nav = flagship.systems["navigation"]
        assert nav._last_params is None, (
            "Flagship should not receive a formation autopilot"
        )

    def test_reengagement_guard_updates_position(self):
        """If autopilot already running for this fleet, update position only."""
        fm, flagship, wingmen = _build_fleet(1)
        wing = wingmen[0]

        # First tick -- engage
        fm.update(dt=1.0)
        nav = wing.systems["navigation"]
        ap = nav.controller.autopilot
        assert ap is not None
        assert ap.update_count == 0

        # Move flagship so calculated positions change
        flagship.position["x"] = 5000.0
        first_params = nav._last_params

        # Second tick -- should update position, not recreate
        fm.update(dt=1.0)
        # Same autopilot object (not replaced)
        assert nav.controller.autopilot is ap
        # update_formation_position was called
        assert ap.update_count == 1


class TestFormationAdherence:
    """_check_formation_adherence should use actual position checks."""

    def test_ships_far_from_slot_returns_false(self):
        fm, flagship, wingmen = _build_fleet(1)
        # wingman is 1000m away from origin; formation slot is ~2000m away
        # so the wingman is far from its slot
        assert fm._check_formation_adherence("alpha") is False

    def test_ships_at_correct_position_returns_true(self):
        fm, flagship, wingmen = _build_fleet(1)
        wing = wingmen[0]

        # Calculate where the wingman should be and place it there
        positions = fm.get_formation_positions("alpha")
        for fp in positions:
            if fp.ship_id == wing.id:
                desired = np.array([
                    flagship.position["x"],
                    flagship.position["y"],
                    flagship.position["z"],
                ]) + fp.relative_position
                wing.position["x"] = float(desired[0])
                wing.position["y"] = float(desired[1])
                wing.position["z"] = float(desired[2])
                break

        assert fm._check_formation_adherence("alpha") is True

    def test_status_transitions_to_in_formation(self):
        """Fleet transitions from FORMING to IN_FORMATION when all ships arrive."""
        fm, flagship, wingmen = _build_fleet(1)
        wing = wingmen[0]

        # Place wingman at correct slot
        positions = fm.get_formation_positions("alpha")
        for fp in positions:
            if fp.ship_id == wing.id:
                desired = np.array([
                    flagship.position["x"],
                    flagship.position["y"],
                    flagship.position["z"],
                ]) + fp.relative_position
                wing.position["x"] = float(desired[0])
                wing.position["y"] = float(desired[1])
                wing.position["z"] = float(desired[2])
                break

        fm.update(dt=1.0)
        assert fm.fleets["alpha"].status == FleetStatus.IN_FORMATION


class TestShipInterfaceFixes:
    """Verify get_formation_positions and get_fleet_status use position dicts."""

    def test_get_formation_positions_uses_dict_interface(self):
        fm, flagship, wingmen = _build_fleet(1)
        # Should not raise AttributeError from ship.x / ship.vx
        positions = fm.get_formation_positions("alpha")
        assert len(positions) > 0

    def test_get_fleet_status_uses_dict_interface(self):
        fm, flagship, wingmen = _build_fleet(1)
        # Should not raise AttributeError from ship.x / ship.vx
        status = fm.get_fleet_status("alpha")
        assert status is not None
        assert status["ship_count"] == 2  # flagship + 1 wingman
        # Verify position is a list of numbers, not an error
        for s in status["ships"]:
            assert len(s["position"]) == 3
            assert len(s["velocity"]) == 3
