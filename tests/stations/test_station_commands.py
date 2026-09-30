"""Tests for station management commands."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from server.stations.station_dispatch import StationAwareDispatcher
from server.stations.station_manager import StationManager
from server.stations.station_commands import register_station_commands
from server.stations.station_types import StationType, get_station_commands
from server.stations.crew_system import CrewManager


def test_list_ships_returns_metadata():
    """List ships should return available ship metadata when provided."""
    manager = StationManager()
    dispatcher = StationAwareDispatcher(manager)

    ships = {
        "ship_alpha": SimpleNamespace(
            id="ship_alpha",
            name="Alpha",
            class_type="frigate",
            faction="neutral",
        ),
        "ship_bravo": SimpleNamespace(
            id="ship_bravo",
            name="Bravo",
            class_type="corvette",
        ),
    }

    register_station_commands(dispatcher, manager, ship_provider=lambda: ships)

    result = dispatcher.dispatch("client_1", "", "list_ships", {})

    assert result.success is True
    assert result.data is not None

    ship_entries = result.data["ships"]
    ship_ids = {entry["id"] for entry in ship_entries}

    assert ship_ids == {"ship_alpha", "ship_bravo"}
    assert any(entry.get("name") == "Alpha" for entry in ship_entries)
    assert any(entry.get("class") == "frigate" for entry in ship_entries)


def test_transfer_station_requires_officer_permission():
    """Crew members cannot transfer stations without officer permissions."""
    manager = StationManager()
    dispatcher = StationAwareDispatcher(manager)
    register_station_commands(dispatcher, manager)

    manager.register_client("client_1", "Alpha")
    manager.register_client("client_2", "Bravo")

    manager.assign_to_ship("client_1", "ship_alpha")
    manager.assign_to_ship("client_2", "ship_alpha")
    manager.claim_station("client_1", "ship_alpha", StationType.HELM)

    result = dispatcher.dispatch(
        "client_1",
        "ship_alpha",
        "transfer_station",
        {"target_client": "client_2"},
    )

    assert result.success is False
    assert result.message == "Only OFFICER or CAPTAIN can transfer station control"
    assert manager.get_station_owner("ship_alpha", StationType.HELM) == "client_1"


# ---------------------------------------------------------------------------
# assign_ship — ship-existence validation (Fix 1)
# ---------------------------------------------------------------------------

def test_assign_ship_rejects_unknown_ship_id():
    """assign_ship must return ok=False when the ship ID does not exist."""
    manager = StationManager()
    dispatcher = StationAwareDispatcher(manager)

    # Only one known ship in the simulation
    ships = {
        "real_ship": SimpleNamespace(id="real_ship", name="Real", class_type="corvette"),
    }
    register_station_commands(dispatcher, manager, ship_provider=lambda: ships)
    manager.register_client("client_1", "Pilot")

    result = dispatcher.dispatch("client_1", "", "assign_ship", {"ship": "ghost_ship"})

    assert result.success is False
    assert "ghost_ship" in result.message
    # Session must not have been mutated
    session = manager.get_session("client_1")
    assert session.ship_id is None


def test_assign_ship_accepts_known_ship_id():
    """assign_ship must succeed when the ship ID exists in the simulation."""
    manager = StationManager()
    dispatcher = StationAwareDispatcher(manager)

    ships = {
        "real_ship": SimpleNamespace(id="real_ship", name="Real", class_type="corvette"),
    }
    register_station_commands(dispatcher, manager, ship_provider=lambda: ships)
    manager.register_client("client_1", "Pilot")

    result = dispatcher.dispatch("client_1", "", "assign_ship", {"ship": "real_ship"})

    assert result.success is True
    session = manager.get_session("client_1")
    assert session.ship_id == "real_ship"


def test_assign_ship_without_ship_provider_still_assigns():
    """
    When no ship_provider is registered, the existence check is skipped and
    assign_ship falls back to its original behaviour (station_manager decides).
    """
    manager = StationManager()
    dispatcher = StationAwareDispatcher(manager)
    # No ship_provider — existence validation must be skipped
    register_station_commands(dispatcher, manager, ship_provider=None)
    manager.register_client("client_1", "Pilot")

    result = dispatcher.dispatch("client_1", "", "assign_ship", {"ship": "any_ship"})

    # station_manager.assign_to_ship creates the ship slot on-demand, so this
    # should succeed without a provider.
    assert result.success is True


def test_assign_ship_missing_ship_id_returns_error():
    """assign_ship with no ship argument must return a descriptive error."""
    manager = StationManager()
    dispatcher = StationAwareDispatcher(manager)
    ships = {"ship_a": SimpleNamespace(id="ship_a")}
    register_station_commands(dispatcher, manager, ship_provider=lambda: ships)
    manager.register_client("client_1", "Pilot")

    # No 'ship' arg and no implicit ship_id
    result = dispatcher.dispatch("client_1", "", "assign_ship", {})

    assert result.success is False


def test_assign_ship_empty_string_ship_id_returns_error():
    """assign_ship with an empty string ship ID must return an error."""
    manager = StationManager()
    dispatcher = StationAwareDispatcher(manager)
    ships = {"ship_a": SimpleNamespace(id="ship_a")}
    register_station_commands(dispatcher, manager, ship_provider=lambda: ships)
    manager.register_client("client_1", "Pilot")

    result = dispatcher.dispatch("client_1", "", "assign_ship", {"ship": ""})

    assert result.success is False


@pytest.mark.parametrize("with_crew_manager", [False, True])
@pytest.mark.parametrize("assigned", [False, True])
def test_crew_status_capability_matches_existing_read_contract(with_crew_manager, assigned):
    """Only an assigned session with the registered crew read advertises it."""
    manager = StationManager()
    dispatcher = StationAwareDispatcher(manager)
    crew = CrewManager() if with_crew_manager else None
    register_station_commands(dispatcher, manager, crew_manager=crew)
    manager.register_client("client_1", "Pilot")
    if crew is not None:
        crew.create_crew_member("ship_alpha", "Alpha engineer")
        crew.create_crew_member("ship_other", "Other ship engineer")
    if assigned:
        assert dispatcher.dispatch("client_1", "", "assign_ship", {"ship": "ship_alpha"}).success

    status = dispatcher.dispatch("client_1", "", "my_status", {}).to_dict()
    expected = ["crew_status"] if with_crew_manager and assigned else []
    assert status["ok"] is True
    assert status["response"]["station"] is None
    assert status["response"]["available_commands"] == expected
    # Explicit command ship arguments cannot change the roster's assigned-ship scope.
    result = dispatcher.dispatch("client_1", "ship_other", "crew_status", {}).to_dict()
    assert result["ok"] is (with_crew_manager and assigned)
    if result["ok"]:
        assert result["response"]["ship_id"] == "ship_alpha"
        assert [member["name"] for member in result["response"]["crew"]] == ["Alpha engineer"]
    else:
        assert "response" not in result


@pytest.mark.parametrize("with_crew_manager", [False, True])
@pytest.mark.parametrize("station", list(StationType))
def test_claim_and_my_status_advertise_only_station_commands_plus_available_crew_read(with_crew_manager, station):
    """Every real role, including Captain, gets the same narrow read contract."""
    manager = StationManager()
    dispatcher = StationAwareDispatcher(manager)
    crew = CrewManager() if with_crew_manager else None
    register_station_commands(dispatcher, manager, crew_manager=crew)
    manager.register_client("client_1", "Pilot")
    dispatcher.dispatch("client_1", "", "assign_ship", {"ship": "ship_alpha"})
    if crew is not None:
        crew.create_crew_member("ship_alpha", "Alpha engineer")

    claimed = dispatcher.dispatch("client_1", "ship_alpha", "claim_station", {"station": station.value}).to_dict()
    assert claimed["ok"] is True
    status = dispatcher.dispatch("client_1", "ship_alpha", "my_status", {}).to_dict()
    expected = set(get_station_commands(station))
    if with_crew_manager:
        expected.add("crew_status")
    assert set(claimed["response"]["available_commands"]) == expected
    assert claimed["response"]["available_commands"] == status["response"]["available_commands"]
    result = dispatcher.dispatch("client_1", "ship_alpha", "crew_status", {}).to_dict()
    assert result["ok"] is with_crew_manager
    if result["ok"]:
        assert result["response"]["crew_count"] == 1
        assert result["response"]["crew"][0]["name"] == "Alpha engineer"


def _crew_contract_case(with_crew_manager, assigned, claimed):
    """Produce a small real-dispatcher projection shared with the Node-only UI job."""
    manager = StationManager()
    dispatcher = StationAwareDispatcher(manager)
    crew = CrewManager() if with_crew_manager else None
    register_station_commands(dispatcher, manager, crew_manager=crew)
    manager.register_client("client_test", "Pilot")
    if crew is not None:
        member = crew.create_crew_member("ship_A", "Verified Engineer")
        member.fatigue, member.stress = 0.25, 0.1
    if assigned:
        dispatcher.dispatch("client_test", "", "assign_ship", {"ship": "ship_A"})
    if claimed:
        dispatcher.dispatch("client_test", "ship_A", "claim_station", {"station": "ops"})
    status = dispatcher.dispatch("client_test", "ship_A", "my_status", {}).to_dict()
    # This fixture asserts the crew read capability, not an unrelated station snapshot.
    status["response"] = {key: status["response"][key] for key in ("ship_id", "station", "available_commands")}
    status["response"]["available_commands"] = [cmd for cmd in status["response"]["available_commands"] if cmd == "crew_status"]
    result = dispatcher.dispatch("client_test", "ship_A", "crew_status", {}).to_dict()
    if result["ok"]:
        result["response"]["crew"] = [{
            key: member[key] for key in ("crew_id", "name", "fatigue", "stress", "injury_state", "skills")
        } for member in result["response"]["crew"]]
        for member in result["response"]["crew"]:
            member["skills"] = {"engineering": member["skills"]["engineering"]}
    return {"status": status, "crew": result}


def test_frontend_crew_contract_fixture_matches_actual_dispatcher():
    """The frontend fixture must track actual eligibility and nested read envelopes."""
    fixture = json.loads((Path(__file__).resolve().parents[2] / "gui-svelte/tests/fixtures/crew-contract.json").read_text())
    expected = {
        "assigned_ops": _crew_contract_case(True, True, True),
        "assigned_unclaimed": _crew_contract_case(True, True, False),
        "unassigned": _crew_contract_case(True, False, False),
        "manager_unavailable": _crew_contract_case(False, True, True),
    }
    assert fixture == expected
