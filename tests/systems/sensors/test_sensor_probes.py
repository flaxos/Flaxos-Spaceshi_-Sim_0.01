# tests/systems/sensors/test_sensor_probes.py
"""Tests for deployable sensor probes."""

import types
import math
import pytest

from hybrid.core.event_bus import EventBus
from hybrid.systems.sensors.sensor_probe import (
    SensorProbe,
    bearing_to_unit_vector,
    MAX_PROBES_PER_SHIP,
    PROBE_LIFESPAN_S,
    PROBE_DELTA_V,
    PROBE_SENSOR_RANGE_M,
    _next_probe_id,
)
from hybrid.systems.sensors.sensor_system import SensorSystem


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ship(ship_id: str, pos: dict = None, vel: dict = None,
               mass: float = 10000.0, class_type: str = "corvette",
               faction: str = "UNE", thrust: float = 0.0) -> types.SimpleNamespace:
    """Build a minimal ship-like namespace for sensor tests."""
    if pos is None:
        pos = {"x": 0.0, "y": 0.0, "z": 0.0}
    if vel is None:
        vel = {"x": 0.0, "y": 0.0, "z": 0.0}
    ship = types.SimpleNamespace(
        id=ship_id,
        name=ship_id,
        position=dict(pos),
        velocity=dict(vel),
        acceleration={"x": 0.0, "y": 0.0, "z": 0.0},
        mass=mass,
        class_type=class_type,
        faction=faction,
        systems={},
        event_bus=EventBus.get_instance(),
        orientation={"pitch": 0, "yaw": 0, "roll": 0},
        angular_velocity={"pitch": 0, "yaw": 0, "roll": 0},
        hull_integrity=100.0,
        max_hull_integrity=100.0,
    )
    # Propulsion stub so emission model can read thrust state
    ship.systems["propulsion"] = types.SimpleNamespace(
        get_state=lambda: {"fuel_level": 1000, "max_fuel": 1000,
                           "fuel_percent": 100, "fuel_burn_rate": 0,
                           "fuel_time_remaining": None},
        current_thrust=thrust,
        max_thrust=50000.0,
        enabled=True,
    )
    # Radiator stub for emission model
    ship.systems["thermal"] = types.SimpleNamespace(
        get_state=lambda: {"radiator_temperature": 300.0, "radiator_area": 10.0},
        enabled=True,
    )
    return ship


def _make_sensor_system() -> SensorSystem:
    """Build a SensorSystem with default config."""
    return SensorSystem({
        "passive": {"passive_range": 300000, "sensor_tick_interval": 1},
        "active": {},
    })


# ---------------------------------------------------------------------------
# bearing_to_unit_vector
# ---------------------------------------------------------------------------

class TestBearingToUnitVector:

    def test_zero_bearing(self):
        v = bearing_to_unit_vector({"azimuth": 0, "elevation": 0})
        assert abs(v["x"] - 1.0) < 1e-9
        assert abs(v["y"]) < 1e-9
        assert abs(v["z"]) < 1e-9

    def test_90_azimuth(self):
        v = bearing_to_unit_vector({"azimuth": 90, "elevation": 0})
        assert abs(v["x"]) < 1e-9
        assert abs(v["y"] - 1.0) < 1e-9
        assert abs(v["z"]) < 1e-9

    def test_90_elevation(self):
        v = bearing_to_unit_vector({"azimuth": 0, "elevation": 90})
        assert abs(v["x"]) < 1e-9
        assert abs(v["y"]) < 1e-9
        assert abs(v["z"] - 1.0) < 1e-9

    def test_unit_length(self):
        v = bearing_to_unit_vector({"azimuth": 45, "elevation": 30})
        length = math.sqrt(v["x"]**2 + v["y"]**2 + v["z"]**2)
        assert abs(length - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# SensorProbe
# ---------------------------------------------------------------------------

class TestSensorProbe:

    def test_initial_state(self):
        probe = SensorProbe(
            probe_id="p1",
            parent_ship_id="ship1",
            position={"x": 0, "y": 0, "z": 0},
            velocity={"x": 100, "y": 0, "z": 0},
            deploy_time=0.0,
        )
        assert probe.active is True
        assert probe.id == "p1"
        assert probe.parent_ship_id == "ship1"
        assert probe.time_remaining == PROBE_LIFESPAN_S
        assert probe.sensor.range == PROBE_SENSOR_RANGE_M

    def test_newtonian_drift(self):
        """Probe moves in a straight line with no thrust."""
        probe = SensorProbe(
            probe_id="p1",
            parent_ship_id="ship1",
            position={"x": 0, "y": 0, "z": 0},
            velocity={"x": 100, "y": 0, "z": 0},
            deploy_time=0.0,
        )
        # 10-second tick, no ships to detect
        probe.update(dt=10.0, all_ships=[], sim_time=10.0)
        assert abs(probe.position["x"] - 1000.0) < 1e-6
        assert abs(probe.position["y"]) < 1e-6

    def test_lifespan_expiry(self):
        """Probe deactivates after PROBE_LIFESPAN_S."""
        probe = SensorProbe(
            probe_id="p1",
            parent_ship_id="ship1",
            position={"x": 0, "y": 0, "z": 0},
            velocity={"x": 0, "y": 0, "z": 0},
            deploy_time=0.0,
        )
        # Advance past lifespan
        contacts = probe.update(
            dt=1.0, all_ships=[], sim_time=PROBE_LIFESPAN_S + 1.0,
        )
        assert probe.active is False
        assert contacts == {}

    def test_deactivate_recall(self):
        probe = SensorProbe(
            probe_id="p1",
            parent_ship_id="ship1",
            position={"x": 0, "y": 0, "z": 0},
            velocity={"x": 0, "y": 0, "z": 0},
            deploy_time=0.0,
        )
        probe.deactivate()
        assert probe.active is False
        # Update after deactivation returns nothing
        contacts = probe.update(dt=1.0, all_ships=[], sim_time=1.0)
        assert contacts == {}

    def test_detects_nearby_ship(self):
        """Probe should detect a thrusting ship within range."""
        probe = SensorProbe(
            probe_id="p1",
            parent_ship_id="ship1",
            position={"x": 0, "y": 0, "z": 0},
            velocity={"x": 0, "y": 0, "z": 0},
            deploy_time=0.0,
        )
        # Target 50 km away, thrusting hard (high IR signature)
        target = _make_ship(
            "target1",
            pos={"x": 50000, "y": 0, "z": 0},
            thrust=50000.0,
        )
        contacts = probe.update(dt=1.0, all_ships=[target], sim_time=1.0)
        # Should have detected the target
        assert len(contacts) > 0

    def test_get_state(self):
        probe = SensorProbe(
            probe_id="p1",
            parent_ship_id="ship1",
            position={"x": 100, "y": 200, "z": 300},
            velocity={"x": 0, "y": 0, "z": 0},
            deploy_time=0.0,
        )
        state = probe.get_state()
        assert state["id"] == "p1"
        assert state["position"] == {"x": 100, "y": 200, "z": 300}
        assert state["active"] is True
        assert isinstance(state["time_remaining"], float)
        assert isinstance(state["contacts"], int)


# ---------------------------------------------------------------------------
# SensorSystem probe integration
# ---------------------------------------------------------------------------

class TestSensorSystemProbes:

    def test_deploy_probe_creates_probe(self):
        ss = _make_sensor_system()
        ship = _make_ship("ship1")
        ship.systems["sensors"] = ss

        result = ss.command("deploy_probe", {
            "ship": ship,
            "bearing": {"azimuth": 0, "elevation": 0},
        })
        assert result.get("ok") is True
        assert "probe_id" in result
        assert len(ss.probes) == 1
        assert ss.probes[0].active is True

    def test_deploy_probe_limit(self):
        """Cannot exceed MAX_PROBES_PER_SHIP active probes."""
        ss = _make_sensor_system()
        ship = _make_ship("ship1")
        ship.systems["sensors"] = ss

        for i in range(MAX_PROBES_PER_SHIP):
            result = ss.command("deploy_probe", {
                "ship": ship,
                "bearing": {"azimuth": i * 90, "elevation": 0},
            })
            assert result.get("ok") is True

        # 5th should fail
        result = ss.command("deploy_probe", {
            "ship": ship,
            "bearing": {"azimuth": 0, "elevation": 0},
        })
        assert result.get("ok") is not True
        assert "PROBE_LIMIT" in result.get("error", "")

    def test_recall_probe(self):
        ss = _make_sensor_system()
        ship = _make_ship("ship1")
        ship.systems["sensors"] = ss

        deploy_result = ss.command("deploy_probe", {
            "ship": ship,
            "bearing": {"azimuth": 0, "elevation": 0},
        })
        probe_id = deploy_result["probe_id"]

        recall_result = ss.command("recall_probe", {"probe_id": probe_id})
        assert recall_result.get("ok") is True
        # Probe still in list but marked inactive
        assert ss.probes[0].active is False

    def test_recall_nonexistent_probe(self):
        ss = _make_sensor_system()
        result = ss.command("recall_probe", {"probe_id": "bogus"})
        assert result.get("ok") is not True
        assert "PROBE_NOT_FOUND" in result.get("error", "")

    def test_probes_pruned_after_expiry(self):
        """Expired probes are removed from the list on tick."""
        ss = _make_sensor_system()
        ship = _make_ship("ship1")
        ship.systems["sensors"] = ss
        ss.sim_time = 0.0

        ss.command("deploy_probe", {
            "ship": ship,
            "bearing": {"azimuth": 0, "elevation": 0},
        })
        assert len(ss.probes) == 1

        # Simulate a tick well past lifespan
        ss.sim_time = PROBE_LIFESPAN_S + 10.0
        ss._tick_probes(dt=1.0, sim_time=ss.sim_time)
        # Probe should have been pruned
        assert len(ss.probes) == 0

    def test_deploy_probe_inherits_ship_velocity(self):
        """Probe velocity = ship velocity + launch impulse."""
        ss = _make_sensor_system()
        ship = _make_ship("ship1", vel={"x": 500, "y": 0, "z": 0})
        ship.systems["sensors"] = ss

        result = ss.command("deploy_probe", {
            "ship": ship,
            "bearing": {"azimuth": 0, "elevation": 0},
        })
        probe = ss.probes[0]
        # Ship moving at 500 m/s +X, probe launched at bearing 0 (also +X),
        # so probe velocity should be ~(500 + 100, 0, 0)
        assert abs(probe.velocity["x"] - (500 + PROBE_DELTA_V)) < 1e-6
        assert abs(probe.velocity["y"]) < 1e-6
        assert abs(probe.velocity["z"]) < 1e-6

    def test_probe_contacts_merge_into_tracker(self):
        """Contacts detected by probes appear in parent ship's tracker."""
        ss = _make_sensor_system()
        ship = _make_ship("ship1")
        ship.systems["sensors"] = ss
        ship._all_ships_ref = []

        # Deploy probe
        ss.command("deploy_probe", {
            "ship": ship,
            "bearing": {"azimuth": 0, "elevation": 0},
        })

        # Place a target near the probe's position (within 50 km)
        target = _make_ship(
            "target1",
            pos={"x": 30000, "y": 0, "z": 0},
            thrust=50000.0,
        )
        ss.all_ships = [ship, target]

        # Tick the probes
        ss.sim_time = 1.0
        ss._tick_probes(dt=1.0, sim_time=1.0)

        # Check that the contact tracker has the target
        all_contacts = ss.contact_tracker.get_all_contacts(ss.sim_time)
        # There should be at least one contact from the probe
        target_found = any(
            c.detection_method == "probe"
            for c in all_contacts.values()
        )
        assert target_found, (
            f"Expected probe-sourced contact in tracker, got: "
            f"{[(c.id, c.detection_method) for c in all_contacts.values()]}"
        )

    def test_get_state_includes_probes(self):
        """SensorSystem.get_state() includes probes list."""
        ss = _make_sensor_system()
        ship = _make_ship("ship1")
        ship.systems["sensors"] = ss

        ss.command("deploy_probe", {
            "ship": ship,
            "bearing": {"azimuth": 45, "elevation": 10},
        })

        state = ss.get_state()
        assert "probes" in state
        assert len(state["probes"]) == 1
        assert state["probes"][0]["active"] is True


# ---------------------------------------------------------------------------
# Command registration (3-place checklist)
# ---------------------------------------------------------------------------

class TestProbeCommandRegistration:

    def test_system_commands_dict(self):
        """deploy_probe and recall_probe are in command_handler.system_commands."""
        from hybrid.command_handler import system_commands
        assert "deploy_probe" in system_commands
        assert system_commands["deploy_probe"] == ("sensors", "deploy_probe")
        assert "recall_probe" in system_commands
        assert system_commands["recall_probe"] == ("sensors", "recall_probe")

    def test_station_permissions(self):
        """Both commands are in SCIENCE and TACTICAL station command sets."""
        from server.stations.station_types import (
            STATION_DEFINITIONS, StationType, can_station_issue_command,
        )
        for cmd in ("deploy_probe", "recall_probe"):
            assert can_station_issue_command(StationType.SCIENCE, cmd), (
                f"{cmd} not in SCIENCE station"
            )
            assert can_station_issue_command(StationType.TACTICAL, cmd), (
                f"{cmd} not in TACTICAL station"
            )

    def test_dispatcher_registration(self):
        """Both commands are registered in the command dispatcher."""
        from hybrid.commands.dispatch import create_default_dispatcher
        dispatcher = create_default_dispatcher()
        assert "deploy_probe" in dispatcher.commands
        assert "recall_probe" in dispatcher.commands
