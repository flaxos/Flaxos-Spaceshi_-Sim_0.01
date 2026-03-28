# tests/systems/sensors/test_eccm.py
"""Tests for the ECCM (Electronic Counter-Countermeasures) system."""

import math
import types
import pytest

from hybrid.systems.sensors.eccm import ECCMState, ECCMMode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_ecm_ship(jammer_enabled: bool = False, jammer_power: float = 50000.0,
                  chaff_active: bool = False, flare_active: bool = False,
                  emcon_active: bool = False):
    """Create a minimal mock ship with ECM system for testing.

    Args:
        jammer_enabled: Whether the radar jammer is on.
        jammer_power: Jammer radiated power in watts.
        chaff_active: Whether chaff cloud is deployed.
        flare_active: Whether IR flare is burning.
        emcon_active: Whether EMCON mode is active.

    Returns:
        SimpleNamespace ship with ECM system.
    """
    ecm = types.SimpleNamespace(
        jammer_enabled=jammer_enabled,
        jammer_power=jammer_power,
        _ecm_factor=1.0,
        emcon_active=emcon_active,
    )

    # ECM query methods
    ecm.is_chaff_active = lambda: chaff_active
    ecm.is_flare_active = lambda: flare_active
    ecm.get_chaff_rcs_multiplier = lambda: 5.0 if chaff_active else 1.0
    ecm.get_chaff_noise_radius = lambda: 2000.0 if chaff_active else 0.0
    ecm.get_flare_ir_power = lambda: 5.0e6 if flare_active else 0.0
    ecm.get_emcon_ir_modifier = lambda: 0.3 if emcon_active else 1.0
    ecm.get_emcon_rcs_modifier = lambda: 0.7 if emcon_active else 1.0

    def get_jammer_effect_at_range(distance):
        if not jammer_enabled or distance <= 0:
            return 1.0
        flux = jammer_power / (4.0 * math.pi * distance * distance)
        noise_floor = 1.0e-12
        jam_ratio = flux / noise_floor
        if jam_ratio <= 1.0:
            return 1.0
        deg = 1.0 / (1.0 + math.log10(jam_ratio))
        return max(0.05, min(1.0, deg))

    ecm.get_jammer_effect_at_range = get_jammer_effect_at_range

    ship = types.SimpleNamespace(
        id="target_1",
        position={"x": 100000, "y": 0, "z": 0},
        velocity={"x": 0, "y": 0, "z": 0},
        systems={"ecm": ecm},
        mass=5000,
        class_type="corvette",
    )
    return ship


# ---------------------------------------------------------------------------
# ECCMState unit tests
# ---------------------------------------------------------------------------

class TestECCMStateInit:
    """Test ECCMState initialisation and defaults."""

    def test_default_state(self):
        eccm = ECCMState()
        assert eccm.mode == ECCMMode.OFF
        assert eccm.multispectral_active is False
        assert eccm.hoj_active is False
        assert eccm._sensor_health == 1.0

    def test_custom_config(self):
        eccm = ECCMState({"freq_hop_jam_reduction": 0.5})
        assert eccm.freq_hop_jam_reduction == 0.5


class TestFrequencyHopping:
    """Test frequency hopping ECCM mode."""

    def test_activate(self):
        eccm = ECCMState()
        result = eccm.activate_frequency_hop()
        assert result["ok"] is True
        assert eccm.mode == ECCMMode.FREQUENCY_HOP

    def test_jam_reduction_full_health(self):
        eccm = ECCMState()
        eccm.activate_frequency_hop()

        # A raw jam factor of 0.2 means 80% degradation from jamming.
        # Freq hop should remove 60-80% of that penalty.
        modified = eccm.get_jam_factor_modifier(0.2)
        # With full health: 80% reduction of 0.8 penalty = 0.64 removed
        # New penalty = 0.16, factor = 0.84
        assert modified > 0.7, f"Expected >0.7, got {modified}"
        assert modified < 1.0

    def test_jam_reduction_degraded_health(self):
        eccm = ECCMState()
        eccm.set_sensor_health(0.5)
        eccm.activate_frequency_hop()

        modified = eccm.get_jam_factor_modifier(0.2)
        # Reduced effectiveness at 50% health
        # But still better than raw 0.2
        assert modified > 0.2
        # Worse than full health
        full_health = ECCMState()
        full_health.activate_frequency_hop()
        full_mod = full_health.get_jam_factor_modifier(0.2)
        assert modified < full_mod

    def test_no_effect_when_off(self):
        eccm = ECCMState()
        raw = 0.3
        assert eccm.get_jam_factor_modifier(raw) == raw

    def test_cannot_activate_during_burn_through(self):
        eccm = ECCMState()
        eccm.activate_burn_through()
        result = eccm.activate_frequency_hop()
        assert result["ok"] is False
        assert eccm.mode == ECCMMode.BURN_THROUGH


class TestBurnThrough:
    """Test burn-through ECCM mode."""

    def test_activate(self):
        eccm = ECCMState()
        result = eccm.activate_burn_through()
        assert result["ok"] is True
        assert eccm.mode == ECCMMode.BURN_THROUGH

    def test_radar_power_multiplier(self):
        eccm = ECCMState()
        eccm.activate_burn_through()
        mult = eccm.get_burn_through_radar_multiplier()
        # Should be close to 4x at full health
        assert mult > 3.5
        assert mult <= 4.0

    def test_radar_multiplier_degraded(self):
        eccm = ECCMState()
        eccm.set_sensor_health(0.0)
        eccm.activate_burn_through()
        mult = eccm.get_burn_through_radar_multiplier()
        # Even at 0 health, should still get partial boost (brute force)
        assert mult > 1.0
        assert mult < 4.0

    def test_no_multiplier_when_off(self):
        eccm = ECCMState()
        assert eccm.get_burn_through_radar_multiplier() == 1.0

    def test_emission_multiplier(self):
        eccm = ECCMState()
        eccm.activate_burn_through()
        mult = eccm.get_burn_through_emission_multiplier()
        assert mult == 6.0  # Default config

    def test_no_emission_multiplier_when_off(self):
        eccm = ECCMState()
        assert eccm.get_burn_through_emission_multiplier() == 1.0

    def test_cannot_activate_during_freq_hop(self):
        eccm = ECCMState()
        eccm.activate_frequency_hop()
        result = eccm.activate_burn_through()
        assert result["ok"] is False
        assert eccm.mode == ECCMMode.FREQUENCY_HOP

    def test_jam_reduction_via_burn_through(self):
        eccm = ECCMState()
        eccm.activate_burn_through()
        # Burn-through also provides ~40% jam reduction via improved SNR
        modified = eccm.get_jam_factor_modifier(0.2)
        assert modified > 0.2
        assert modified < 1.0


class TestDeactivateMode:
    """Test ECCM mode deactivation."""

    def test_deactivate_freq_hop(self):
        eccm = ECCMState()
        eccm.activate_frequency_hop()
        result = eccm.deactivate_eccm_mode()
        assert result["ok"] is True
        assert eccm.mode == ECCMMode.OFF

    def test_deactivate_burn_through(self):
        eccm = ECCMState()
        eccm.activate_burn_through()
        result = eccm.deactivate_eccm_mode()
        assert result["ok"] is True
        assert eccm.mode == ECCMMode.OFF

    def test_deactivate_when_already_off(self):
        eccm = ECCMState()
        result = eccm.deactivate_eccm_mode()
        assert result["ok"] is True
        assert eccm.mode == ECCMMode.OFF


class TestMultiSpectralCorrelation:
    """Test multi-spectral correlation for chaff/flare filtering."""

    def test_chaff_reduction_all_sensors(self):
        eccm = ECCMState()
        eccm.set_multispectral(True)
        reduction = eccm.get_chaff_reduction(has_ir=True, has_radar=True, has_lidar=True)
        assert reduction > 0.8  # ~85% at full health

    def test_chaff_reduction_two_sensors(self):
        eccm = ECCMState()
        eccm.set_multispectral(True)
        reduction = eccm.get_chaff_reduction(has_ir=True, has_radar=True, has_lidar=False)
        # Two sensors give ~50% of full reduction
        assert 0.3 < reduction < 0.6

    def test_chaff_reduction_one_sensor(self):
        eccm = ECCMState()
        eccm.set_multispectral(True)
        reduction = eccm.get_chaff_reduction(has_ir=True, has_radar=False, has_lidar=False)
        # Cannot correlate with only one sensor
        assert reduction == 0.0

    def test_chaff_reduction_inactive(self):
        eccm = ECCMState()
        # Multi-spectral not enabled
        reduction = eccm.get_chaff_reduction(has_ir=True, has_radar=True, has_lidar=True)
        assert reduction == 0.0

    def test_flare_reduction_all_sensors(self):
        eccm = ECCMState()
        eccm.set_multispectral(True)
        reduction = eccm.get_flare_reduction(has_ir=True, has_radar=True, has_lidar=True)
        assert reduction > 0.7  # ~80% at full health

    def test_flare_reduction_degraded_health(self):
        eccm = ECCMState()
        eccm.set_multispectral(True)
        eccm.set_sensor_health(0.5)
        full = eccm.get_flare_reduction(has_ir=True, has_radar=True, has_lidar=True)
        eccm.set_sensor_health(1.0)
        healthy = eccm.get_flare_reduction(has_ir=True, has_radar=True, has_lidar=True)
        assert full < healthy

    def test_toggle(self):
        eccm = ECCMState()
        result = eccm.set_multispectral(True)
        assert result["ok"] is True
        assert eccm.multispectral_active is True
        result = eccm.set_multispectral(False)
        assert eccm.multispectral_active is False


class TestHomeOnJam:
    """Test home-on-jam capability."""

    def test_detect_active_jammer(self):
        eccm = ECCMState()
        eccm.set_home_on_jam(True)

        target = make_ecm_ship(jammer_enabled=True, jammer_power=50000)
        observer_pos = {"x": 0, "y": 0, "z": 0}
        distance = 100000  # 100km

        result = eccm.check_home_on_jam(target, observer_pos, distance)
        assert result is not None
        assert result["detection_method"] == "home_on_jam"
        assert result["has_range"] is False  # Bearing only
        assert "bearing" in result

    def test_no_detect_inactive_jammer(self):
        eccm = ECCMState()
        eccm.set_home_on_jam(True)

        target = make_ecm_ship(jammer_enabled=False)
        observer_pos = {"x": 0, "y": 0, "z": 0}
        result = eccm.check_home_on_jam(target, observer_pos, 100000)
        assert result is None

    def test_no_detect_when_hoj_disabled(self):
        eccm = ECCMState()
        # HoJ not enabled
        target = make_ecm_ship(jammer_enabled=True)
        observer_pos = {"x": 0, "y": 0, "z": 0}
        result = eccm.check_home_on_jam(target, observer_pos, 100000)
        assert result is None

    def test_toggle(self):
        eccm = ECCMState()
        result = eccm.set_home_on_jam(True)
        assert result["ok"] is True
        assert eccm.hoj_active is True


class TestAnalyzeJamming:
    """Test jamming analysis."""

    def test_detect_noise_jamming(self):
        eccm = ECCMState()
        target = make_ecm_ship(jammer_enabled=True)
        result = eccm.analyze_jamming(target, distance=50000)

        assert result["ok"] is True
        assert result["ecm_detected"] is True
        assert any(t["type"] == "noise_jamming" for t in result["threats"])

    def test_detect_chaff(self):
        eccm = ECCMState()
        target = make_ecm_ship(chaff_active=True)
        result = eccm.analyze_jamming(target, distance=50000)

        assert result["ecm_detected"] is True
        assert any(t["type"] == "chaff" for t in result["threats"])
        assert "multispectral" in result["all_recommendations"]

    def test_detect_flare(self):
        eccm = ECCMState()
        target = make_ecm_ship(flare_active=True)
        result = eccm.analyze_jamming(target, distance=50000)

        assert result["ecm_detected"] is True
        assert any(t["type"] == "flare" for t in result["threats"])

    def test_no_ecm_detected(self):
        eccm = ECCMState()
        target = make_ecm_ship()  # All off
        result = eccm.analyze_jamming(target, distance=50000)

        assert result["ecm_detected"] is False
        assert len(result["threats"]) == 0

    def test_no_ecm_system(self):
        eccm = ECCMState()
        target = types.SimpleNamespace(
            id="bare_ship",
            systems={},
        )
        result = eccm.analyze_jamming(target, distance=50000)
        assert result["ecm_detected"] is False

    def test_recommendation_for_severe_jamming(self):
        eccm = ECCMState()
        # Close range + high power = severe jamming
        target = make_ecm_ship(jammer_enabled=True, jammer_power=100000)
        result = eccm.analyze_jamming(target, distance=5000)

        assert result["ecm_detected"] is True
        # Should recommend burn-through for severe jamming
        assert "burn_through" in result["all_recommendations"]


class TestSensorPowerMultiplier:
    """Test sensor power draw changes from ECCM modes."""

    def test_no_extra_power_when_off(self):
        eccm = ECCMState()
        assert eccm.get_sensor_power_multiplier() == 1.0

    def test_freq_hop_power_increase(self):
        eccm = ECCMState()
        eccm.activate_frequency_hop()
        mult = eccm.get_sensor_power_multiplier()
        assert mult > 1.5  # ~1.8x

    def test_burn_through_power_increase(self):
        eccm = ECCMState()
        eccm.activate_burn_through()
        mult = eccm.get_sensor_power_multiplier()
        assert mult > 2.0  # Significant power draw


class TestECCMState:
    """Test ECCM state/telemetry output."""

    def test_state_output(self):
        eccm = ECCMState()
        eccm.activate_frequency_hop()
        eccm.set_multispectral(True)

        state = eccm.get_state()
        assert state["mode"] == "frequency_hop"
        assert state["multispectral_active"] is True
        assert state["hoj_active"] is False
        assert state["freq_hop_jam_reduction"] is not None
        assert state["burn_through_radar_mult"] is None  # Not in burn-through

    def test_status_string(self):
        eccm = ECCMState()
        assert eccm._get_status_string() == "standby"

        eccm.activate_frequency_hop()
        assert "FREQUENCY-HOP" in eccm._get_status_string()

        eccm.deactivate_eccm_mode()
        eccm.set_multispectral(True)
        assert "MULTI-SPEC" in eccm._get_status_string()

        eccm.set_home_on_jam(True)
        status = eccm._get_status_string()
        assert "MULTI-SPEC" in status
        assert "HOJ" in status


class TestECCMTick:
    """Test ECCM tick behaviour (heat, health tracking)."""

    def test_tick_updates_sensor_health(self):
        eccm = ECCMState()
        ship = types.SimpleNamespace(
            id="ship1",
            damage_model=types.SimpleNamespace(
                get_degradation_factor=lambda sys: 0.6,
                subsystems={},
            ),
        )

        eccm.tick(0.25, ship)
        assert eccm._sensor_health == 0.6

    def test_tick_no_crash_without_ship(self):
        eccm = ECCMState()
        eccm.tick(0.25)  # Should not raise

    def test_tick_with_get_effective_factor(self):
        eccm = ECCMState()
        ship = types.SimpleNamespace(
            id="ship1",
            get_effective_factor=lambda sys: 0.8,
        )

        eccm.tick(0.25, ship)
        assert eccm._sensor_health == 0.8
