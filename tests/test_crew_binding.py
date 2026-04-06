"""
Tests for crew-station binding system.

Covers: assignment, transfer, unassignment, performance multipliers,
experience gain, crew injury from subsystem damage, and AI backup fallback.
"""

import pytest
import random

from server.stations.crew_system import (
    CrewManager, CrewMember, CrewSkills, StationSkill, SkillLevel,
)
from server.stations.crew_binding import (
    CrewStationBinder, AI_BACKUP_COMPETENCE, STATION_SKILL_MAP,
    StationSlot, PerformanceReport, XP_PER_ACTION,
)
from server.stations.station_types import StationType


@pytest.fixture
def crew_manager() -> CrewManager:
    return CrewManager()


@pytest.fixture
def binder(crew_manager: CrewManager) -> CrewStationBinder:
    return CrewStationBinder(crew_manager)


@pytest.fixture
def ship_with_crew(crew_manager: CrewManager, binder: CrewStationBinder):
    """Create a ship with two crew members and registered slots."""
    ship_id = "test_ship"
    binder.register_ship(ship_id)

    # Expert gunner
    gunner_skills = CrewSkills(gunnery=5, targeting=5)
    gunner = crew_manager.create_crew_member(ship_id, "Amos Burton", skills=gunner_skills)

    # Competent pilot
    pilot_skills = CrewSkills(piloting=3, navigation=4)
    pilot = crew_manager.create_crew_member(ship_id, "Alex Kamal", skills=pilot_skills)

    return ship_id, gunner, pilot


class TestAssignment:
    """Test crew assignment to stations."""

    def test_assign_crew_to_station(self, binder, ship_with_crew):
        ship_id, gunner, pilot = ship_with_crew

        ok, msg = binder.assign_crew(ship_id, gunner.crew_id, StationType.TACTICAL)
        assert ok is True
        assert gunner.name in msg

    def test_assign_to_occupied_station_fails(self, binder, ship_with_crew):
        ship_id, gunner, pilot = ship_with_crew

        binder.assign_crew(ship_id, gunner.crew_id, StationType.TACTICAL)
        ok, msg = binder.assign_crew(ship_id, pilot.crew_id, StationType.TACTICAL)
        assert ok is False
        assert "already has" in msg

    def test_assign_already_assigned_crew_fails(self, binder, ship_with_crew):
        ship_id, gunner, pilot = ship_with_crew

        binder.assign_crew(ship_id, gunner.crew_id, StationType.TACTICAL)
        ok, msg = binder.assign_crew(ship_id, gunner.crew_id, StationType.HELM)
        assert ok is False
        assert "already assigned" in msg

    def test_assign_dead_crew_fails(self, binder, ship_with_crew):
        ship_id, gunner, pilot = ship_with_crew
        gunner.health = 0.0

        ok, msg = binder.assign_crew(ship_id, gunner.crew_id, StationType.TACTICAL)
        assert ok is False
        assert "dead" in msg

    def test_assign_nonexistent_crew_fails(self, binder, ship_with_crew):
        ship_id, _, _ = ship_with_crew

        ok, msg = binder.assign_crew(ship_id, "crew_999", StationType.TACTICAL)
        assert ok is False
        assert "not found" in msg

    def test_assign_unregistered_ship_fails(self, binder, crew_manager):
        crew = crew_manager.create_crew_member("other_ship", "Nobody")
        ok, msg = binder.assign_crew("other_ship", crew.crew_id, StationType.HELM)
        assert ok is False


class TestTransfer:
    """Test crew transfers between stations."""

    def test_transfer_crew(self, binder, ship_with_crew):
        ship_id, gunner, pilot = ship_with_crew

        binder.assign_crew(ship_id, gunner.crew_id, StationType.TACTICAL)
        ok, msg = binder.transfer_crew(ship_id, gunner.crew_id, StationType.HELM)
        assert ok is True
        assert "transferred" in msg

        # Old station should be AI backup now
        mult = binder.get_station_multiplier(ship_id, StationType.TACTICAL)
        assert mult == AI_BACKUP_COMPETENCE

        # New station should use gunner's skills
        mult = binder.get_station_multiplier(ship_id, StationType.HELM)
        assert mult > AI_BACKUP_COMPETENCE

    def test_transfer_to_occupied_station_fails(self, binder, ship_with_crew):
        ship_id, gunner, pilot = ship_with_crew

        binder.assign_crew(ship_id, gunner.crew_id, StationType.TACTICAL)
        binder.assign_crew(ship_id, pilot.crew_id, StationType.HELM)

        ok, msg = binder.transfer_crew(ship_id, gunner.crew_id, StationType.HELM)
        assert ok is False

    def test_transfer_unassigned_crew_fails(self, binder, ship_with_crew):
        ship_id, gunner, _ = ship_with_crew

        ok, msg = binder.transfer_crew(ship_id, gunner.crew_id, StationType.HELM)
        assert ok is False
        assert "not currently assigned" in msg

    def test_transfer_to_same_station_fails(self, binder, ship_with_crew):
        ship_id, gunner, _ = ship_with_crew

        binder.assign_crew(ship_id, gunner.crew_id, StationType.TACTICAL)
        ok, msg = binder.transfer_crew(ship_id, gunner.crew_id, StationType.TACTICAL)
        assert ok is False
        assert "already at" in msg


class TestUnassign:
    """Test crew removal from stations."""

    def test_unassign_crew(self, binder, ship_with_crew):
        ship_id, gunner, _ = ship_with_crew

        binder.assign_crew(ship_id, gunner.crew_id, StationType.TACTICAL)
        ok, msg = binder.unassign_crew(ship_id, StationType.TACTICAL)
        assert ok is True
        assert "AI backup" in msg

    def test_unassign_empty_station_fails(self, binder, ship_with_crew):
        ship_id, _, _ = ship_with_crew

        ok, msg = binder.unassign_crew(ship_id, StationType.TACTICAL)
        assert ok is False


class TestPerformance:
    """Test performance multiplier calculations."""

    def test_unmanned_station_returns_ai_backup(self, binder, ship_with_crew):
        ship_id, _, _ = ship_with_crew

        mult = binder.get_station_multiplier(ship_id, StationType.TACTICAL)
        assert mult == AI_BACKUP_COMPETENCE

    def test_expert_crew_has_high_multiplier(self, binder, ship_with_crew):
        """Expert gunner at tactical should produce ~0.9 efficiency."""
        ship_id, gunner, _ = ship_with_crew

        binder.assign_crew(ship_id, gunner.crew_id, StationType.TACTICAL)
        mult = binder.get_station_multiplier(ship_id, StationType.TACTICAL)
        # Expert (level 5) has 0.90 base efficiency
        assert mult >= 0.85
        assert mult <= 1.0

    def test_fatigued_crew_has_lower_multiplier(self, binder, ship_with_crew):
        ship_id, gunner, _ = ship_with_crew

        binder.assign_crew(ship_id, gunner.crew_id, StationType.TACTICAL)
        fresh_mult = binder.get_station_multiplier(ship_id, StationType.TACTICAL)

        # Exhaust the crew member
        gunner.fatigue = 0.9
        gunner.stress = 0.5

        tired_mult = binder.get_station_multiplier(ship_id, StationType.TACTICAL)
        assert tired_mult < fresh_mult

    def test_injured_crew_has_lower_multiplier(self, binder, ship_with_crew):
        ship_id, gunner, _ = ship_with_crew

        binder.assign_crew(ship_id, gunner.crew_id, StationType.TACTICAL)
        healthy_mult = binder.get_station_multiplier(ship_id, StationType.TACTICAL)

        gunner.health = 0.3
        injured_mult = binder.get_station_multiplier(ship_id, StationType.TACTICAL)
        assert injured_mult < healthy_mult

    def test_unregistered_ship_returns_ai_backup(self, binder):
        mult = binder.get_station_multiplier("ghost_ship", StationType.HELM)
        assert mult == AI_BACKUP_COMPETENCE


class TestPerformanceReport:
    """Test detailed performance reports."""

    def test_report_for_manned_station(self, binder, ship_with_crew):
        ship_id, gunner, _ = ship_with_crew

        binder.assign_crew(ship_id, gunner.crew_id, StationType.TACTICAL)
        report = binder.get_performance_report(ship_id, StationType.TACTICAL)

        assert report is not None
        assert report.crew_name == gunner.name
        assert report.is_ai is False
        assert "gunnery" in report.skill_breakdown
        assert "targeting" in report.skill_breakdown

    def test_report_for_unmanned_station(self, binder, ship_with_crew):
        ship_id, _, _ = ship_with_crew

        report = binder.get_performance_report(ship_id, StationType.TACTICAL)
        assert report is not None
        assert report.is_ai is True
        assert report.efficiency == AI_BACKUP_COMPETENCE


class TestExperience:
    """Test learning-by-doing experience gain."""

    def test_action_records_command(self, binder, ship_with_crew):
        ship_id, gunner, _ = ship_with_crew

        binder.assign_crew(ship_id, gunner.crew_id, StationType.TACTICAL)

        assert gunner.commands_executed == 0
        binder.record_action(ship_id, StationType.TACTICAL, success=True)
        assert gunner.commands_executed == 1
        assert gunner.successful_commands == 1

    def test_failed_action_increases_stress(self, binder, ship_with_crew):
        ship_id, gunner, _ = ship_with_crew

        binder.assign_crew(ship_id, gunner.crew_id, StationType.TACTICAL)
        initial_stress = gunner.stress

        binder.record_action(ship_id, StationType.TACTICAL, success=False)
        assert gunner.stress > initial_stress

    def test_action_on_unmanned_station_is_noop(self, binder, ship_with_crew):
        """Recording actions on an unmanned station should not crash."""
        ship_id, _, _ = ship_with_crew
        # Should not raise
        binder.record_action(ship_id, StationType.TACTICAL, success=True)


class TestCrewInjury:
    """Test crew injury from subsystem damage.

    The injury model uses an InjuryState escalation ladder:
    HEALTHY -> WOUNDED (30% * severity) -> CRITICAL (50%) -> DEAD (30%).
    Tests use deterministic seeds chosen for the new probabilities.
    """

    def test_severe_damage_can_injure_crew(self, binder, ship_with_crew):
        """Catastrophic damage (severity=1.0) can wound healthy crew."""
        ship_id, gunner, _ = ship_with_crew
        binder.assign_crew(ship_id, gunner.crew_id, StationType.TACTICAL)

        # seed=1 gives random() ~ 0.134, below the 0.3 injury threshold
        random.seed(1)
        result = binder.apply_damage_to_station(ship_id, StationType.TACTICAL, severity=1.0)

        assert result is not None
        assert result["injured"] is True
        assert result["new_state"] == "wounded"

    def test_light_damage_may_not_injure(self, binder, ship_with_crew):
        """Light damage (severity=0.1) should rarely injure."""
        ship_id, gunner, _ = ship_with_crew
        binder.assign_crew(ship_id, gunner.crew_id, StationType.TACTICAL)

        random.seed(0)  # deterministic
        # With severity=0.1, injury chance is 0.03 -- very unlikely
        from server.stations.crew_system import InjuryState
        injuries = 0
        for _ in range(20):
            # Reset state for each attempt
            gunner.health = 1.0
            gunner.injury_state = InjuryState.HEALTHY
            result = binder.apply_damage_to_station(
                ship_id, StationType.TACTICAL, severity=0.1,
            )
            if result and result["injured"]:
                injuries += 1

        # Should be rare (0-3 out of 20 attempts)
        assert injuries < 10

    def test_killed_crew_reverts_to_ai(self, binder, ship_with_crew):
        """Killing a crew member should activate AI backup."""
        from server.stations.crew_system import InjuryState
        ship_id, gunner, _ = ship_with_crew
        binder.assign_crew(ship_id, gunner.crew_id, StationType.TACTICAL)

        # Set to CRITICAL state so next hit has 30% kill chance
        gunner.injury_state = InjuryState.CRITICAL
        gunner.health = 0.1
        # Re-assign since critical would normally remove from station
        slots = binder._slots[ship_id]
        slots[StationType.TACTICAL].crew_id = gunner.crew_id
        slots[StationType.TACTICAL].is_ai_backup = False

        # seed=1 gives random() ~ 0.134, below the 0.3 kill threshold
        random.seed(1)
        result = binder.apply_damage_to_station(
            ship_id, StationType.TACTICAL, severity=1.0,
        )

        assert result is not None
        assert result["killed"] is True

        # Station should now use AI backup
        mult = binder.get_station_multiplier(ship_id, StationType.TACTICAL)
        assert mult == AI_BACKUP_COMPETENCE

    def test_damage_on_unmanned_station_returns_none(self, binder, ship_with_crew):
        ship_id, _, _ = ship_with_crew
        result = binder.apply_damage_to_station(
            ship_id, StationType.TACTICAL, severity=1.0,
        )
        assert result is None


class TestSubsystemDamageMapping:
    """Test mapping from subsystem damage to crew injuries."""

    def test_weapons_damage_hits_tactical(self, binder, ship_with_crew):
        ship_id, gunner, _ = ship_with_crew
        binder.assign_crew(ship_id, gunner.crew_id, StationType.TACTICAL)

        # seed=1 triggers injury at 30% chance
        random.seed(1)
        results = binder.on_subsystem_damaged(ship_id, "weapons", severity=1.0)
        assert len(results) > 0
        assert results[0]["crew_name"] == gunner.name

    def test_propulsion_damage_hits_helm(self, binder, ship_with_crew):
        ship_id, _, pilot = ship_with_crew
        binder.assign_crew(ship_id, pilot.crew_id, StationType.HELM)

        random.seed(1)
        results = binder.on_subsystem_damaged(ship_id, "propulsion", severity=1.0)
        assert len(results) > 0
        assert results[0]["crew_name"] == pilot.name

    def test_unknown_subsystem_returns_empty(self, binder, ship_with_crew):
        ship_id, _, _ = ship_with_crew
        results = binder.on_subsystem_damaged(ship_id, "warp_drive", severity=1.0)
        assert results == []


class TestShipCrewStatus:
    """Test full crew status serialization."""

    def test_status_includes_all_stations(self, binder, ship_with_crew):
        ship_id, _, _ = ship_with_crew
        status = binder.get_ship_crew_status(ship_id)

        station_names = {entry["station"] for entry in status}
        for st in StationType:
            assert st.value in station_names

    def test_status_shows_assigned_crew(self, binder, ship_with_crew):
        ship_id, gunner, _ = ship_with_crew
        binder.assign_crew(ship_id, gunner.crew_id, StationType.TACTICAL)

        status = binder.get_ship_crew_status(ship_id)
        tactical_entry = next(
            e for e in status if e["station"] == "tactical"
        )
        assert tactical_entry["crew_id"] == gunner.crew_id
        assert tactical_entry["is_ai_backup"] is False
        assert tactical_entry["performance"]["crew_name"] == gunner.name


class TestStationSkillMapping:
    """Verify that every station has a skill mapping defined."""

    def test_all_stations_have_skill_map(self):
        for station in StationType:
            assert station in STATION_SKILL_MAP, (
                f"Station {station.value} missing from STATION_SKILL_MAP"
            )
