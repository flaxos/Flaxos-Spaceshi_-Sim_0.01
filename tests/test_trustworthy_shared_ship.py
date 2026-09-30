"""Runtime boundaries for one physical ship and independent crew stations."""

from datetime import datetime, timedelta
import json
import socket
import threading
import time

import pytest

from hybrid.core.event_bus import EventBus
from hybrid.systems.crew_binding_system import CrewBindingSystem
from hybrid.systems.combat.torpedo_manager import MunitionType
from hybrid.systems.thermal_system import ThermalSystem
from hybrid.telemetry import get_ship_telemetry
from hybrid_runner import HybridRunner
from server.config import ServerConfig, ServerMode
from server.main import UnifiedServer
from server.stations.station_types import StationType, get_station_commands


@pytest.fixture(autouse=True)
def isolated_shared_managers():
    old_bus = EventBus._instance
    old_crew = CrewBindingSystem._shared_crew_manager
    old_binder = CrewBindingSystem._shared_binder
    EventBus._instance = None
    yield
    EventBus._instance = old_bus
    CrewBindingSystem._shared_crew_manager = old_crew
    CrewBindingSystem._shared_binder = old_binder


@pytest.fixture
def station_server():
    server = UnifiedServer(ServerConfig(tcp_port=0, rcon_password="test-admin"))
    server.initialize()
    server.runner.stop()
    yield server
    server.stop()


def join(server, client, station, ship="player"):
    manager = server.station_manager
    manager.register_client(client, client)
    assert manager.assign_to_ship(client, ship)
    assert manager.claim_station(client, ship, station)[0]


def wait_until(predicate, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    assert predicate(), "Runtime condition did not become true"


def test_live_start_runs_crew_and_stale_monitors_and_stop_joins(monkeypatch):
    monkeypatch.setattr("server.main.AI_CREW_TICK_INTERVAL", 0.01)
    monkeypatch.setattr("server.main.STALE_CLAIM_CHECK_INTERVAL", 0.01)
    server = UnifiedServer(ServerConfig(tcp_port=0))
    thread = threading.Thread(target=server.start, daemon=True)
    thread.start()
    try:
        wait_until(lambda: server.running and server._ai_crew_thread is not None
                   and server._stale_claim_thread is not None
                   and server._ai_crew_thread.is_alive()
                   and server._stale_claim_thread.is_alive())
        assert server._ai_crew_thread.is_alive()
        assert server._stale_claim_thread.is_alive()
        # Existing AICrew executor really acts on registered starter ships.
        wait_until(lambda: any(member.last_action_time > 0
                              for crew in server.ai_crew_manager._ai_crew.values()
                              for member in crew.values()))
        ship_id = next(iter(server.runner.simulator.ships))
        join(server, "abandoned", StationType.HELM, ship_id)
        server.station_manager.sessions["abandoned"].last_heartbeat = datetime.now() - timedelta(seconds=901)
        wait_until(lambda: server.station_manager.get_session("abandoned") is None)
        assert StationType.HELM not in server.station_manager.claims[ship_id]
        # Listening is exercised as well as in-process maintenance.
        with socket.create_connection(server.server_socket.getsockname(), timeout=2) as client:
            welcome = json.loads(client.makefile("r").readline())
            assert welcome["ok"] is True
    finally:
        server.stop()
        thread.join(timeout=2)
    assert not thread.is_alive()
    assert not server._ai_crew_thread.is_alive()
    assert not server._stale_claim_thread.is_alive()
    assert not server.runner.running


def test_live_disconnect_and_expiry_restore_existing_ai_preserve_other_crew_and_pause(monkeypatch):
    monkeypatch.setattr("server.main.AI_CREW_TICK_INTERVAL", 0.01)
    monkeypatch.setattr("server.main.STALE_CLAIM_CHECK_INTERVAL", 0.01)
    server = UnifiedServer(ServerConfig(tcp_port=0))
    thread = threading.Thread(target=server.start, daemon=True)
    connections = []
    thread.start()
    def connect():
        connection = socket.create_connection(server.server_socket.getsockname(), timeout=2)
        reader = connection.makefile("r")
        client_id = json.loads(reader.readline())["client_id"]
        connections.append((connection, reader))
        return connection, reader, client_id
    def command(connection, reader, request):
        connection.sendall((json.dumps(request) + "\n").encode())
        response = json.loads(reader.readline())
        assert response["ok"] is True, response
        return response
    try:
        wait_until(lambda: server.running and server._ai_crew_thread is not None
                   and server._stale_claim_thread is not None
                   and server._ai_crew_thread.is_alive() and server._stale_claim_thread.is_alive())
        server.runner.stop()
        observed = threading.Event()
        original_tick = server.ai_crew_manager.tick
        def tick(ships, dt):
            original_tick(ships, dt)
            observed.set()
        monkeypatch.setattr(server.ai_crew_manager, "tick", tick)
        ship_id = next(iter(server.runner.simulator.ships))
        science, science_reader, _ = connect()
        command(science, science_reader, {"cmd": "assign_ship", "ship": ship_id})
        command(science, science_reader, {"cmd": "claim_station", "ship": ship_id, "station": "science"})
        engineer, engineer_reader, engineer_id = connect()
        command(engineer, engineer_reader, {"cmd": "assign_ship", "ship": ship_id})
        command(engineer, engineer_reader, {"cmd": "claim_station", "ship": ship_id, "station": "engineering"})
        crew = server.ai_crew_manager._ai_crew[ship_id]
        assert not crew[StationType.ENGINEERING].active
        assert not crew[StationType.SCIENCE].active
        engineer_reader.close()
        engineer.close()
        wait_until(lambda: server.station_manager.get_session(engineer_id) is None
                   and crew[StationType.ENGINEERING].active)
        assert not crew[StationType.SCIENCE].active
        assert not observed.wait(0.05)

        expired, expired_reader, expired_id = connect()
        command(expired, expired_reader, {"cmd": "assign_ship", "ship": ship_id})
        command(expired, expired_reader, {"cmd": "claim_station", "ship": ship_id, "station": "engineering"})
        assert not crew[StationType.ENGINEERING].active
        server.station_manager.sessions[expired_id].last_heartbeat = datetime.now() - timedelta(seconds=901)
        wait_until(lambda: server.station_manager.get_session(expired_id) is None
                   and crew[StationType.ENGINEERING].active)
        assert not crew[StationType.SCIENCE].active
        assert not observed.wait(0.05)
        assert not server.runner.running
    finally:
        for connection, reader in connections:
            reader.close()
            connection.close()
        server.stop()
        thread.join(timeout=2)
    assert not thread.is_alive()


def test_competing_human_claim_cannot_interleave_ai_restoration(station_server, monkeypatch):
    server = station_server
    manager = server.station_manager
    ship_id = next(iter(server.runner.simulator.ships))
    station = StationType.ENGINEERING
    manager.register_client("new_engineer", "new_engineer")
    assert manager.assign_to_ship("new_engineer", ship_id)
    server.ai_crew_manager.deactivate_station(ship_id, station)
    observed_unowned = threading.Event()
    resume_restore = threading.Event()
    claim_waiting = threading.Event()
    claim_finished = threading.Event()
    original_owner = manager.get_station_owner
    original_lock = manager.ownership_lock
    outcomes = {}
    errors = []

    class ObservedLock:
        def __enter__(self):
            if threading.current_thread().name == "competing-human":
                # Signals the actual attempt to enter the same ownership
                # guard, rather than relying on a worker's scheduling delay.
                claim_waiting.set()
            original_lock.acquire()
            return self

        def __exit__(self, *args):
            original_lock.release()

    monkeypatch.setattr(manager, "ownership_lock", ObservedLock())

    def owner_with_barrier(candidate_ship, candidate_station):
        owner = original_owner(candidate_ship, candidate_station)
        if threading.current_thread().name == "restoring-ai":
            assert owner is None
            observed_unowned.set()
            assert resume_restore.wait(2)
        return owner

    monkeypatch.setattr(manager, "get_station_owner", owner_with_barrier)

    def restore():
        try:
            server._restore_ai_for_released_claims([(ship_id, station)])
        except Exception as error:
            errors.append(error)

    def claim():
        try:
            outcomes["claim"] = server.dispatch("new_engineer", {
                "cmd": "claim_station", "ship": ship_id, "station": station.value,
            })
        except Exception as error:
            errors.append(error)
        finally:
            claim_finished.set()

    restoration = threading.Thread(target=restore, name="restoring-ai", daemon=True)
    human = threading.Thread(target=claim, name="competing-human", daemon=True)
    restoration.start()
    try:
        assert observed_unowned.wait(1)
        human.start()
        assert claim_waiting.wait(1)
        assert not claim_finished.is_set()
    finally:
        resume_restore.set()
        restoration.join(2)
        if human.ident is not None:
            human.join(2)
    assert not restoration.is_alive()
    assert not human.is_alive()
    assert not errors
    assert outcomes["claim"]["ok"] is True
    assert original_owner(ship_id, station) == "new_engineer"
    assert not server.ai_crew_manager._ai_crew[ship_id][station].active


def test_inflight_cpu_action_finishes_before_human_handover(station_server, monkeypatch):
    server = station_server
    manager = server.station_manager
    ship_id = next(iter(server.runner.simulator.ships))
    station = StationType.ENGINEERING
    manager.register_client("incoming_engineer", "incoming_engineer")
    assert manager.assign_to_ship("incoming_engineer", ship_id)
    # Isolate one actual tick-selected station at the active-check/action boundary.
    for crew_ship, crew in server.ai_crew_manager._ai_crew.items():
        for member in crew.values():
            member.active = crew_ship == ship_id and member.station == station
    selected = threading.Event()
    resume_action = threading.Event()
    claim_waiting = threading.Event()
    claim_finished = threading.Event()
    original_lock = manager.ownership_lock
    ordering, errors, outcomes = [], [], {}

    class ObservedLock:
        def __enter__(self):
            if threading.current_thread().name == "incoming-human":
                acquired = original_lock.acquire(blocking=False)
                outcomes.setdefault("claim_blocked", not acquired)
                claim_waiting.set()  # report the actual acquisition result
                if not acquired:
                    original_lock.acquire()
                return self
            original_lock.acquire()
            return self

        def __exit__(self, *args):
            original_lock.release()

    monkeypatch.setattr(manager, "ownership_lock", ObservedLock())

    def action(ship, ai):
        assert ai.station == station
        selected.set()  # tick has already passed ai.active
        assert resume_action.wait(2)
        ordering.append(("cpu_action", manager.get_station_owner(ship_id, station)))
        server._monitor_stop.set()  # one tick only

    monkeypatch.setattr(server.ai_crew_manager, "_run_station_ai", action)

    def tick():
        try:
            server._ai_crew_tick_loop()
        except Exception as error:
            errors.append(error)

    def claim():
        try:
            outcomes["claim"] = server.dispatch("incoming_engineer", {
                "cmd": "claim_station", "ship": ship_id, "station": station.value,
            })
            ordering.append(("human_handover", manager.get_station_owner(ship_id, station)))
        except Exception as error:
            errors.append(error)
        finally:
            claim_finished.set()

    server.running = server.runner.running = True
    server._monitor_stop.clear()
    cpu = threading.Thread(target=tick, name="cpu-action", daemon=True)
    human = threading.Thread(target=claim, name="incoming-human", daemon=True)
    cpu.start()
    try:
        assert selected.wait(1)
        human.start()
        assert claim_waiting.wait(1)
        # CPU either finishes before handover, or must not execute afterwards.
        # The approved serialization boundary chooses the former.
        assert outcomes["claim_blocked"], "Human handover passed an in-flight CPU action"
        assert not claim_finished.is_set()
    finally:
        resume_action.set()
        cpu.join(2)
        if human.ident is not None:
            human.join(2)
        server.running = server.runner.running = False
    assert not cpu.is_alive() and not human.is_alive(), "Ownership serialization deadlocked"
    assert not errors
    assert outcomes["claim"]["ok"] is True
    assert ordering == [("cpu_action", None), ("human_handover", "incoming_engineer")]
    assert not server.ai_crew_manager._ai_crew[ship_id][station].active
    server.ai_crew_manager.tick(dict(server.runner.simulator.ships), server.config.dt)
    assert len(ordering) == 2, "CPU executed again after handover"


def test_ownership_guard_allows_nested_cleanup_and_captain_election(station_server):
    server = station_server
    manager = server.station_manager
    ship_id = next(iter(server.runner.simulator.ships))
    join(server, "departing_captain", StationType.CAPTAIN, ship_id)
    join(server, "successor", StationType.HELM, ship_id)
    finished = threading.Event()
    errors = []
    outcomes = {}

    def elect():
        try:
            with manager.ownership_lock:
                manager.unregister_client("departing_captain")
                outcomes["successor"] = manager.elect_new_captain(ship_id)
        except Exception as error:
            errors.append(error)
        finally:
            finished.set()

    thread = threading.Thread(target=elect, daemon=True)
    thread.start()
    assert finished.wait(1), "Nested cleanup/election deadlocked on the ownership guard"
    thread.join(1)
    assert not thread.is_alive()
    assert not errors
    assert outcomes["successor"] == "successor"
    assert manager.get_station_owner(ship_id, StationType.CAPTAIN) == "successor"
    assert manager.get_station_owner(ship_id, StationType.HELM) is None


def test_station_status_reports_own_ship_cpu_flags_without_changing_command_authority(station_server):
    server = station_server
    manager = server.station_manager
    ship_id = next(iter(server.runner.simulator.ships))
    manager.register_client("helm_reader", "Helm reader")
    assert server.dispatch("helm_reader", {"cmd": "assign_ship", "ship": ship_id})["ok"]
    assert server.dispatch("helm_reader", {"cmd": "claim_station", "ship": ship_id, "station": "helm"})["ok"]
    response = server.dispatch("helm_reader", {"cmd": "station_status", "ship": ship_id})
    assert response["ok"]
    data = response["response"]
    human = next(row for row in data["stations"] if row["station"] == "helm")
    assert human["claimed"] and human["player"] == "Helm reader"
    cpu = data["crew_assistance"]
    assert not cpu["worker_running"] and not cpu["simulation_running"]
    assert cpu["mission_epoch"] == server.runner.mission_epoch
    assert cpu["thermal_available"] == bool(server.runner.simulator.ships[ship_id].systems.get("thermal"))
    helm = next(row for row in cpu["stations"] if row["station"] == "helm")
    assert not helm["active"]
    assert server.dispatch("helm_reader", {"cmd": "set_reactor_output", "ship": ship_id, "output": 0.5})["ok"] is False
    assert manager.get_session("helm_reader").station == StationType.HELM


def test_other_ship_or_removed_ship_station_status_does_not_infer_cpu_coverage(station_server):
    server = station_server
    own, other = list(server.runner.simulator.ships)[:2]
    join(server, "reader", StationType.ENGINEERING, own)
    foreign = server.dispatch("reader", {"cmd": "station_status", "ship": other})
    assert foreign["ok"]
    assert "crew_assistance" not in foreign["response"]
    server.runner.simulator.ships.pop(own)
    removed = server.dispatch("reader", {"cmd": "station_status", "ship": own})
    assert removed["ok"]
    assert "crew_assistance" not in removed["response"]


def test_assistance_snapshot_loading_and_full_ai_ship_do_not_claim_a_running_cpu_worker(station_server):
    server = station_server
    own = next(iter(server.runner.simulator.ships))
    join(server, "reader", StationType.HELM, own)
    server.runner._loading_scenario = True
    data = server.dispatch("reader", {"cmd": "station_status"})["response"]["crew_assistance"]
    assert data["stations"] == [] and not data["worker_running"]
    server.runner._loading_scenario = False
    server.runner.simulator.ships[own].ai_enabled = True
    data = server.dispatch("reader", {"cmd": "station_status"})["response"]["crew_assistance"]
    assert not data["ship_eligible"] and not data["worker_running"]


def test_bootstrap_and_replay_enforce_authority_and_preserve_crew(station_server):
    server = station_server
    for client in ("captain", "science"):
        server.station_manager.register_client(client, client)
    # Starter fleet exists, but no mission has been loaded. Two browsers can
    # bootstrap without first inventing a captain on a default fleet ship.
    first = server.dispatch("captain", {"cmd": "load_scenario", "scenario": "07_docking_test"})
    assert first["ok"] is True
    assert first["station"] == "captain"
    assert server.station_manager.claim_station("science", "player", StationType.SCIENCE)[0]
    denied = server.dispatch("science", {"cmd": "load_scenario", "scenario": "07_docking_test", "force": True})
    assert denied["ok"] is False
    epoch = server.runner.mission_epoch
    replay = server.dispatch("captain", {"cmd": "load_scenario", "scenario": "07_docking_test", "force": True})
    assert replay["ok"] is True
    assert server.runner.mission_epoch == epoch + 1
    assert server.station_manager.get_session("science").station == StationType.SCIENCE
    assert server.station_manager.get_session("science").ship_id == "player"
    science_ai = next(item for item in server.ai_crew_manager.get_status("player") if item["station"] == "science")
    assert science_ai["active"] is False
    # A zero-survivor outcome does not reopen multi-client reload authority.
    server.runner.simulator.ships.clear()
    assert server.dispatch("science", {"cmd": "load_scenario", "scenario": "07_docking_test", "force": True})["ok"] is False


def test_admin_reset_requires_auth_and_preserves_paused_crew(station_server):
    server = station_server
    server.runner.load_scenario("07_docking_test")
    join(server, "helm", StationType.HELM)
    join(server, "science", StationType.SCIENCE)
    assert server.dispatch("science", {"cmd": "rcon_reload"})["ok"] is False
    auth = server.dispatch("science", {"cmd": "rcon_auth", "password": "test-admin"})
    assert auth["ok"] is True
    before = server.runner.mission_epoch
    reset = server.dispatch("science", {"cmd": "rcon_reload", "token": auth["token"]})
    assert reset["ok"] is True
    assert server.runner.mission_epoch == before + 1
    assert not server.runner.running
    assert server.station_manager.get_session("helm").station == StationType.HELM
    assert server.station_manager.get_session("science").station == StationType.SCIENCE


def test_existing_ai_executor_reacts_only_when_running_and_unclaimed(station_server, monkeypatch):
    server = station_server
    server.runner.load_scenario("07_docking_test")
    server._sync_ai_crew()
    player = server.runner.simulator.ships["player"]
    thermal = ThermalSystem({"initial_temperature": 390, "heat_sink_capacity": 100000})
    player.systems["thermal"] = thermal
    # Diagnostic thermal state exercises the existing reactive heat-sink
    # behavior; it is not evidence of a CPU flying or winning this mission.
    thermal.hull_temperature = 390
    thermal.heat_sink_remaining = 100000
    observed = threading.Event()
    original_tick = server.ai_crew_manager.tick
    def tick(ships, dt):
        original_tick(ships, dt)
        observed.set()
    monkeypatch.setattr(server.ai_crew_manager, "tick", tick)
    monkeypatch.setattr("server.main.AI_CREW_TICK_INTERVAL", 0.01)
    server.running = True
    server._start_station_monitors()
    assert not observed.wait(0.05)  # Paused mission must not mutate crew systems.
    server.runner.start()
    assert observed.wait(1)
    assert thermal.heat_sink_active
    server.runner.stop()
    observed.clear()
    assert not observed.wait(0.05)
    server.station_manager.register_client("engineer", "engineer")
    assert server.dispatch("engineer", {"cmd": "assign_ship", "ship": "player"})["ok"] is True
    assert server.dispatch("engineer", {"cmd": "claim_station", "ship": "player", "station": "engineering"})["ok"] is True
    crew = server.ai_crew_manager._ai_crew["player"][StationType.ENGINEERING]
    assert not crew.active
    thermal.heat_sink_active = False
    crew.last_action_time = 0
    original_tick({"player": player}, server.config.dt)
    assert not thermal.heat_sink_active


def test_paused_load_and_reset_initialize_navigation_without_physics(station_server):
    server = station_server
    server.station_manager.register_client("captain", "captain")
    for _ in range(2):
        response = server.dispatch("captain", {"cmd": "load_scenario", "scenario": "07_docking_test", "force": True})
        assert response["ok"] is True
        ship = server.runner.simulator.ships["player"]
        initial = (dict(ship.position), dict(ship.velocity), ship.systems["propulsion"].fuel_level)
        assert ship.systems["navigation"].controller.ship is ship
        result = server.dispatch("captain", {"cmd": "autopilot", "ship": "player", "program": "hold"})
        assert result["ok"] is True, result
        assert not server.runner.running
        assert server.runner.simulator.time == server.runner.simulator.tick_count == 0
        assert (ship.position, ship.velocity, ship.systems["propulsion"].fuel_level) == initial


def test_actual_guided_munitions_are_removed_by_force_reload():
    runner = HybridRunner()
    runner.load_scenario("07_docking_test")
    manager = runner.simulator.torpedo_manager
    for kind in (MunitionType.TORPEDO, MunitionType.MISSILE):
        manager.spawn("player", "target_station", {"x": 0, "y": 0, "z": 0},
                      {"x": 100, "y": 0, "z": 0}, 0,
                      {"x": 200000, "y": 0, "z": 0}, {"x": 0, "y": 0, "z": 0}, munition_type=kind)
    assert manager.active_count == 2
    runner.load_scenario("07_docking_test", force=True)
    assert manager.active_count == 0
    runner.simulator.start()
    runner.simulator.tick()
    runner.simulator.stop()
    assert runner.simulator.torpedo_manager.get_state() == []


@pytest.mark.parametrize("surviving_other_ship", [False, True])
def test_designated_player_loss_fails_and_notifies_without_substitution(tmp_path, surviving_other_ship):
    ships = [{"id": "player", "player_controlled": True, "mass": 1000,
              "position": {"x": 0, "y": 0, "z": 0}, "systems": {}}]
    if surviving_other_ship:
        ships.append({"id": "other", "mass": 1000, "position": {"x": 1000, "y": 0, "z": 0}, "systems": {}})
    path = tmp_path / "loss.json"
    path.write_text(json.dumps({"ships": ships, "mission": {
        "name": "Player reaches destination", "objectives": [{"id": "reach", "type": "reach_position",
        "params": {"position": {"x": 1000, "y": 0, "z": 0}, "tolerance": 1}}]}}))
    runner = HybridRunner()
    runner._load_scenario_file(str(path))
    player = runner.simulator.ships["player"]
    runner._update_mission()
    assert runner.get_mission_status()["mission_status"] == "in_progress"
    player.take_damage(player.max_hull_integrity * 2)
    runner.simulator.start()
    runner.simulator.tick()
    runner.simulator.stop()
    assert "player" not in runner.simulator.ships
    runner._update_mission()
    runner._update_mission()  # No duplicate completion notification.
    status = runner.get_mission_status()
    assert status["mission_status"] == "failure"
    assert status["objectives"]["reach"]["status"] == "failed"
    assert "player" in status["failure_reason"]
    complete = [event for event in runner.simulator.get_recent_events() if event["type"] == "mission_complete"]
    assert len(complete) == 1
    assert complete[0]["ship_id"] == "player"
    assert complete[0]["data"]["mission_status"] == "failure"


def test_common_physics_and_read_only_helm_contacts_preserve_command_roles(station_server):
    server = station_server
    server.runner.load_scenario("07_docking_test")
    join(server, "helm", StationType.HELM)
    join(server, "science", StationType.SCIENCE)
    join(server, "engineering", StationType.ENGINEERING)
    server.runner.simulator.start()
    server.runner.simulator.tick()
    server.runner.simulator.stop()
    assert server.dispatch("helm", {"cmd": "autopilot", "ship": "player", "program": "hold"})["ok"] is True
    helm = server.dispatch("helm", {"cmd": "get_state", "ship": "player", "full": True})["state"]
    science = server.dispatch("science", {"cmd": "get_state", "ship": "player", "full": True})["state"]
    engineering = server.dispatch("engineering", {"cmd": "get_state", "ship": "player", "full": True})["state"]
    for key in ("position", "velocity", "orientation", "throttle", "fuel", "hull_percent", "reactor_output"):
        assert key in helm
        assert helm[key] == science[key] == engineering[key]
    assert helm["sensors"]["contacts"]
    assert {contact["id"] for contact in engineering["sensors"]["contacts"]} == {
        contact["id"] for contact in science["sensors"]["contacts"]}
    assert engineering["target_id"] == science["target_id"] == helm["target_id"]
    for key in ("nav_mode", "autopilot_program", "autopilot_state"):
        assert engineering[key] == science[key] == helm[key]
    assert engineering["autopilot_program"] == "hold"
    assert "targeting" in helm
    assert "weapons" not in helm
    assert "ping_sensors" not in get_station_commands(StationType.HELM)
    assert server.dispatch("helm", {"cmd": "ping_sensors", "ship": "player"})["ok"] is False
    assert server.dispatch("engineering", {"cmd": "ping_sensors", "ship": "player"})["ok"] is False
    assert server.dispatch("science", {"cmd": "set_thrust", "ship": "player", "thrust": 0.2})["ok"] is False
    assert server.dispatch("science", {"cmd": "autopilot", "ship": "player", "program": "hold"})["ok"] is False
    assert server.dispatch("science", {"cmd": "ping_sensors", "ship": "player"})["ok"] is True


@pytest.mark.parametrize("mode", [ServerMode.MINIMAL, ServerMode.STATION])
def test_full_snapshot_request_bypasses_delta_cache(mode):
    server = UnifiedServer(ServerConfig(mode=mode))
    server.runner.load_scenario("07_docking_test")
    if mode == ServerMode.STATION:
        server._init_station_mode()
        join(server, "client", StationType.HELM)
    request = {"cmd": "get_state", "ship": "player"}
    server.dispatch("client", request)
    assert server.dispatch("client", request).get("_delta") is True
    full = server.dispatch("client", {**request, "full": True})
    assert full["ok"] is True and "_delta" not in full
    assert "state" in full and "position" in full["state"]
    assert full["mission_epoch"] == server.runner.mission_epoch


def test_reset_epoch_and_events_identify_same_paused_scenario(station_server):
    server = station_server
    server.station_manager.register_client("captain", "captain")
    server.dispatch("captain", {"cmd": "load_scenario", "scenario": "07_docking_test"})
    before = server.dispatch("captain", {"cmd": "get_mission"})["mission"]
    assert before["current_scenario_id"] == "07_docking_test"
    server.runner.simulator._record_event("mission_complete", {"ship_id": "player", "mission_status": "success"})
    previous_id = server.runner.simulator.get_recent_events()[-1]["id"]
    server.dispatch("captain", {"cmd": "load_scenario", "scenario": "07_docking_test", "force": True})
    after = server.dispatch("captain", {"cmd": "get_mission"})["mission"]
    assert after["mission_epoch"] == before["mission_epoch"] + 1
    assert after["current_scenario_id"] == before["current_scenario_id"]
    assert server.runner.simulator.time == 0
    assert not server.runner.simulator.get_recent_events()
    server.runner.simulator._record_event("new_mission_event", {})
    assert server.runner.simulator.get_recent_events()[-1]["id"] > previous_id


def test_shared_throttle_reports_governed_drive_output(station_server):
    server = station_server
    server.runner.load_scenario("07_docking_test")
    ship = server.runner.simulator.ships["player"]
    ship.systems["helm"].manual_throttle = 0.9
    ship.systems["propulsion"].throttle = 0.9
    ship.systems["engineering"].drive_limit = 0.25
    ship.systems["engineering"]._enforce_drive_limit(ship)
    telemetry = get_ship_telemetry(ship, 0)
    assert telemetry["throttle"] == 0.25
    assert ship.systems["helm"].manual_throttle == 0.9


def test_detected_ui_contact_docks_through_station_commands_and_real_physics(station_server):
    server = station_server
    server.runner.load_scenario("07_docking_test")
    join(server, "helm", StationType.HELM)
    sim = server.runner.simulator
    sim.start()
    sim.tick()
    server.runner._update_mission()
    player = sim.ships["player"]
    contact_id = player.systems["sensors"].contact_tracker.id_mapping["target_station"]
    assert contact_id.startswith("C")
    unknown = server.dispatch("helm", {"cmd": "request_docking", "ship": "player", "target_id": "C999"})
    assert unknown["ok"] is False
    assert player.systems["docking"].target_ship is None
    autopilot = server.dispatch("helm", {"cmd": "autopilot", "ship": "player", "program": "rendezvous", "target": contact_id})
    requested = server.dispatch("helm", {"cmd": "request_docking", "ship": "player", "target_id": contact_id})
    assert autopilot["ok"] is True, autopilot
    assert requested["ok"] is True, requested
    assert player.systems["docking"].get_state()["target"] == contact_id
    for _ in range(12000):
        sim.tick()
        server.runner._update_mission()
        if player.docked_to == "target_station":
            break
    sim.stop()
    assert player.docked_to == "target_station"
    assert server.runner.get_mission_status()["mission_status"] == "success"
