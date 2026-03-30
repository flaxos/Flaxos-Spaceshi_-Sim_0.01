# tests/systems/combat/test_weapon_customization.py
"""Tests for weapon customization: slug types, warhead types, and guidance modes.

Validates that:
- Enums and spec tables exist with correct values
- Slug type modifiers scale railgun damage/penetration correctly
- Warhead types change detonation behaviour (damage, blast radius, EMP)
- Guidance modes change flight behaviour (dumb/guided/smart)
- All defaults are backward compatible (no params = current behaviour)
"""

import pytest
import math


# ---------------------------------------------------------------------------
# Slug Type Tests (Railgun)
# ---------------------------------------------------------------------------

class TestSlugTypeEnums:
    """Verify SlugType enum and modifier tables."""

    def test_slug_type_values(self):
        from hybrid.systems.weapons.truth_weapons import SlugType
        assert SlugType.STANDARD.value == "standard"
        assert SlugType.SABOT.value == "sabot"
        assert SlugType.FRAGMENTATION.value == "fragmentation"

    def test_slug_modifier_table_complete(self):
        """Every slug type must have an entry in the modifier table."""
        from hybrid.systems.weapons.truth_weapons import SlugType, SLUG_TYPE_MODIFIERS
        for st in SlugType:
            assert st.value in SLUG_TYPE_MODIFIERS, f"Missing modifier for {st}"
            mods = SLUG_TYPE_MODIFIERS[st.value]
            assert "armor_penetration_mult" in mods
            assert "subsystem_damage_mult" in mods
            assert "extra_subsystem_hits" in mods

    def test_standard_slug_is_identity(self):
        """STANDARD slug should not modify any stats (all multipliers = 1.0)."""
        from hybrid.systems.weapons.truth_weapons import SLUG_TYPE_MODIFIERS
        std = SLUG_TYPE_MODIFIERS["standard"]
        assert std["armor_penetration_mult"] == 1.0
        assert std["subsystem_damage_mult"] == 1.0
        assert std["extra_subsystem_hits"] == 0

    def test_sabot_slug_trades_subsystem_for_pen(self):
        """SABOT: higher armor pen, lower subsystem damage."""
        from hybrid.systems.weapons.truth_weapons import SLUG_TYPE_MODIFIERS
        sabot = SLUG_TYPE_MODIFIERS["sabot"]
        assert sabot["armor_penetration_mult"] > 1.0
        assert sabot["subsystem_damage_mult"] < 1.0
        assert sabot["extra_subsystem_hits"] == 0

    def test_frag_slug_trades_pen_for_subsystem(self):
        """FRAGMENTATION: lower armor pen, higher subsystem damage, extra hits."""
        from hybrid.systems.weapons.truth_weapons import SLUG_TYPE_MODIFIERS
        frag = SLUG_TYPE_MODIFIERS["fragmentation"]
        assert frag["armor_penetration_mult"] < 1.0
        assert frag["subsystem_damage_mult"] > 1.0
        assert frag["extra_subsystem_hits"] >= 1


class TestSlugTypeInFiring:
    """Verify slug type flows through fire() and _fire_ballistic()."""

    def test_fire_accepts_slug_type_param(self):
        """TruthWeapon.fire() must accept slug_type without error."""
        from hybrid.systems.weapons.truth_weapons import create_railgun
        railgun = create_railgun("rg_test")
        # fire() will fail at power/solution checks, but it should not
        # raise TypeError on the slug_type kwarg.
        result = railgun.fire(
            sim_time=10.0,
            power_manager=None,
            slug_type="sabot",
        )
        # Expected: fails because no firing solution, but no TypeError
        assert result.get("ok") is False

    def test_default_slug_type_is_standard(self):
        """Omitting slug_type should default to standard."""
        from hybrid.systems.weapons.truth_weapons import create_railgun
        railgun = create_railgun("rg_test")
        result = railgun.fire(sim_time=10.0, power_manager=None)
        # Should fail gracefully without slug_type kwarg
        assert result.get("ok") is False


# ---------------------------------------------------------------------------
# Warhead Type Tests (Torpedo/Missile)
# ---------------------------------------------------------------------------

class TestWarheadTypeEnums:
    """Verify WarheadType enum and spec tables."""

    def test_warhead_type_values(self):
        from hybrid.systems.combat.torpedo_manager import WarheadType
        assert WarheadType.FRAGMENTATION.value == "fragmentation"
        assert WarheadType.SHAPED_CHARGE.value == "shaped_charge"
        assert WarheadType.EMP.value == "emp"

    def test_torpedo_warhead_specs_complete(self):
        """Every warhead type must have torpedo specs."""
        from hybrid.systems.combat.torpedo_manager import (
            WarheadType, TORPEDO_WARHEAD_SPECS,
        )
        for wt in WarheadType:
            assert wt.value in TORPEDO_WARHEAD_SPECS, f"Missing torpedo specs for {wt}"
            specs = TORPEDO_WARHEAD_SPECS[wt.value]
            assert "hull_damage" in specs
            assert "subsystem_damage" in specs
            assert "lethal_radius" in specs
            assert "blast_radius" in specs

    def test_missile_warhead_specs_complete(self):
        """Every warhead type must have missile specs."""
        from hybrid.systems.combat.torpedo_manager import (
            WarheadType, MISSILE_WARHEAD_SPECS,
        )
        for wt in WarheadType:
            assert wt.value in MISSILE_WARHEAD_SPECS, f"Missing missile specs for {wt}"
            specs = MISSILE_WARHEAD_SPECS[wt.value]
            assert "hull_damage" in specs
            assert "subsystem_damage" in specs
            assert "lethal_radius" in specs
            assert "blast_radius" in specs

    def test_fragmentation_is_default_baseline(self):
        """FRAGMENTATION torpedo specs should match the original hardcoded values."""
        from hybrid.systems.combat.torpedo_manager import TORPEDO_WARHEAD_SPECS
        frag = TORPEDO_WARHEAD_SPECS["fragmentation"]
        assert frag["hull_damage"] == 60.0
        assert frag["lethal_radius"] == 30.0
        assert frag["blast_radius"] == 100.0

    def test_shaped_charge_torpedo_higher_damage(self):
        """SHAPED_CHARGE torpedo should deal more hull damage than fragmentation."""
        from hybrid.systems.combat.torpedo_manager import TORPEDO_WARHEAD_SPECS
        frag = TORPEDO_WARHEAD_SPECS["fragmentation"]
        shaped = TORPEDO_WARHEAD_SPECS["shaped_charge"]
        assert shaped["hull_damage"] > frag["hull_damage"]

    def test_shaped_charge_torpedo_smaller_blast(self):
        """SHAPED_CHARGE torpedo should have tighter blast/lethal radii."""
        from hybrid.systems.combat.torpedo_manager import TORPEDO_WARHEAD_SPECS
        frag = TORPEDO_WARHEAD_SPECS["fragmentation"]
        shaped = TORPEDO_WARHEAD_SPECS["shaped_charge"]
        assert shaped["blast_radius"] < frag["blast_radius"]
        assert shaped["lethal_radius"] < frag["lethal_radius"]

    def test_emp_torpedo_low_hull_damage(self):
        """EMP torpedo should deal much less hull damage."""
        from hybrid.systems.combat.torpedo_manager import TORPEDO_WARHEAD_SPECS
        frag = TORPEDO_WARHEAD_SPECS["fragmentation"]
        emp = TORPEDO_WARHEAD_SPECS["emp"]
        assert emp["hull_damage"] < frag["hull_damage"]

    def test_emp_torpedo_has_disable_duration(self):
        """EMP torpedo must specify subsystem disable duration and count."""
        from hybrid.systems.combat.torpedo_manager import TORPEDO_WARHEAD_SPECS
        emp = TORPEDO_WARHEAD_SPECS["emp"]
        assert emp["subsystem_disable_duration"] == 30.0
        assert emp["max_subsystems_disabled"] == 2

    def test_emp_missile_has_disable_duration(self):
        """EMP missile must specify subsystem disable duration and count."""
        from hybrid.systems.combat.torpedo_manager import MISSILE_WARHEAD_SPECS
        emp = MISSILE_WARHEAD_SPECS["emp"]
        assert emp["subsystem_disable_duration"] == 20.0
        assert emp["max_subsystems_disabled"] == 1

    def test_missile_fragmentation_matches_baseline(self):
        """Missile FRAGMENTATION should match the original hardcoded values."""
        from hybrid.systems.combat.torpedo_manager import MISSILE_WARHEAD_SPECS
        frag = MISSILE_WARHEAD_SPECS["fragmentation"]
        assert frag["hull_damage"] == 25.0
        assert frag["lethal_radius"] == 10.0
        assert frag["blast_radius"] == 30.0


class TestWarheadInSpawn:
    """Verify warhead_type and guidance_mode flow through TorpedoManager.spawn()."""

    def test_spawn_torpedo_default_warhead(self):
        """Spawning torpedo without warhead_type defaults to fragmentation."""
        from hybrid.systems.combat.torpedo_manager import TorpedoManager, WarheadType
        mgr = TorpedoManager()
        t = mgr.spawn(
            shooter_id="s1", target_id="t1",
            position={"x": 0, "y": 0, "z": 0},
            velocity={"x": 100, "y": 0, "z": 0},
            sim_time=0.0,
            target_pos={"x": 10000, "y": 0, "z": 0},
            target_vel={"x": 0, "y": 0, "z": 0},
        )
        assert t.warhead_type == WarheadType.FRAGMENTATION.value

    def test_spawn_torpedo_shaped_charge(self):
        """Spawning torpedo with shaped_charge stores the type correctly."""
        from hybrid.systems.combat.torpedo_manager import TorpedoManager
        mgr = TorpedoManager()
        t = mgr.spawn(
            shooter_id="s1", target_id="t1",
            position={"x": 0, "y": 0, "z": 0},
            velocity={"x": 100, "y": 0, "z": 0},
            sim_time=0.0,
            target_pos={"x": 10000, "y": 0, "z": 0},
            target_vel={"x": 0, "y": 0, "z": 0},
            warhead_type="shaped_charge",
        )
        assert t.warhead_type == "shaped_charge"

    def test_spawn_torpedo_emp(self):
        from hybrid.systems.combat.torpedo_manager import TorpedoManager
        mgr = TorpedoManager()
        t = mgr.spawn(
            shooter_id="s1", target_id="t1",
            position={"x": 0, "y": 0, "z": 0},
            velocity={"x": 100, "y": 0, "z": 0},
            sim_time=0.0,
            target_pos={"x": 10000, "y": 0, "z": 0},
            target_vel={"x": 0, "y": 0, "z": 0},
            warhead_type="emp",
        )
        assert t.warhead_type == "emp"

    def test_spawn_missile_default_warhead(self):
        """Spawning missile without warhead_type defaults to fragmentation."""
        from hybrid.systems.combat.torpedo_manager import (
            TorpedoManager, MunitionType, WarheadType,
        )
        mgr = TorpedoManager()
        m = mgr.spawn(
            shooter_id="s1", target_id="t1",
            position={"x": 0, "y": 0, "z": 0},
            velocity={"x": 100, "y": 0, "z": 0},
            sim_time=0.0,
            target_pos={"x": 10000, "y": 0, "z": 0},
            target_vel={"x": 0, "y": 0, "z": 0},
            munition_type=MunitionType.MISSILE,
        )
        assert m.warhead_type == WarheadType.FRAGMENTATION.value

    def test_spawn_missile_with_warhead_and_guidance(self):
        from hybrid.systems.combat.torpedo_manager import (
            TorpedoManager, MunitionType,
        )
        mgr = TorpedoManager()
        m = mgr.spawn(
            shooter_id="s1", target_id="t1",
            position={"x": 0, "y": 0, "z": 0},
            velocity={"x": 100, "y": 0, "z": 0},
            sim_time=0.0,
            target_pos={"x": 10000, "y": 0, "z": 0},
            target_vel={"x": 0, "y": 0, "z": 0},
            munition_type=MunitionType.MISSILE,
            warhead_type="emp",
            guidance_mode="smart",
        )
        assert m.warhead_type == "emp"
        assert m.guidance_mode == "smart"


# ---------------------------------------------------------------------------
# Guidance Mode Tests
# ---------------------------------------------------------------------------

class TestGuidanceModeEnums:
    """Verify GuidanceMode enum."""

    def test_guidance_mode_values(self):
        from hybrid.systems.combat.torpedo_manager import GuidanceMode
        assert GuidanceMode.DUMB.value == "dumb"
        assert GuidanceMode.GUIDED.value == "guided"
        assert GuidanceMode.SMART.value == "smart"


class TestGuidanceModeBehaviour:
    """Verify guidance mode affects torpedo flight."""

    def test_dumb_torpedo_stops_correcting_after_boost(self):
        """DUMB torpedo should coast with zero acceleration after boost phase."""
        from hybrid.systems.combat.torpedo_manager import (
            TorpedoManager, TorpedoState,
        )
        mgr = TorpedoManager()
        t = mgr.spawn(
            shooter_id="s1", target_id="t1",
            position={"x": 0, "y": 0, "z": 0},
            velocity={"x": 500, "y": 0, "z": 0},
            sim_time=0.0,
            target_pos={"x": 50000, "y": 0, "z": 0},
            target_vel={"x": 0, "y": 0, "z": 0},
            guidance_mode="dumb",
        )

        # Simulate past boost phase (8s for torpedoes)
        # Advance time far enough that boost ends
        for tick in range(100):
            sim_time = 0.1 * (tick + 1)
            mgr._update_guidance(t, None, 0.1, sim_time)

        # After boost, dumb torpedo should be coasting (zero accel)
        assert t.state == TorpedoState.MIDCOURSE
        assert t.acceleration == {"x": 0, "y": 0, "z": 0}

    def test_guided_torpedo_default(self):
        """GUIDED is the default — omitting guidance_mode should produce GUIDED."""
        from hybrid.systems.combat.torpedo_manager import (
            TorpedoManager, GuidanceMode,
        )
        mgr = TorpedoManager()
        t = mgr.spawn(
            shooter_id="s1", target_id="t1",
            position={"x": 0, "y": 0, "z": 0},
            velocity={"x": 500, "y": 0, "z": 0},
            sim_time=0.0,
            target_pos={"x": 50000, "y": 0, "z": 0},
            target_vel={"x": 0, "y": 0, "z": 0},
        )
        assert t.guidance_mode == GuidanceMode.GUIDED.value

    def test_smart_torpedo_has_higher_pn_gain(self):
        """SMART guidance should use higher PN gain than GUIDED.

        We verify this indirectly: a SMART torpedo should produce
        larger course corrections than a GUIDED torpedo against the
        same laterally-moving target.
        """
        from hybrid.systems.combat.torpedo_manager import TorpedoManager
        from hybrid.utils.math_utils import magnitude

        # Target moving perpendicular to torpedo heading
        target_pos = {"x": 10000, "y": 5000, "z": 0}
        target_vel = {"x": 0, "y": 100, "z": 0}

        # Fake target ship with position/velocity attributes
        class FakeShip:
            def __init__(self):
                self.position = dict(target_pos)
                self.velocity = dict(target_vel)

        target = FakeShip()

        mgr = TorpedoManager()

        # Spawn GUIDED torpedo
        guided = mgr.spawn(
            shooter_id="s1", target_id="t1",
            position={"x": 0, "y": 0, "z": 0},
            velocity={"x": 1000, "y": 0, "z": 0},
            sim_time=0.0,
            target_pos=dict(target_pos),
            target_vel=dict(target_vel),
            guidance_mode="guided",
        )

        # Spawn SMART torpedo (identical start conditions)
        smart = mgr.spawn(
            shooter_id="s1", target_id="t1",
            position={"x": 0, "y": 0, "z": 0},
            velocity={"x": 1000, "y": 0, "z": 0},
            sim_time=0.0,
            target_pos=dict(target_pos),
            target_vel=dict(target_vel),
            guidance_mode="smart",
        )

        # One tick of guidance
        mgr._update_guidance(guided, target, 0.1, 0.1)
        mgr._update_guidance(smart, target, 0.1, 0.1)

        # SMART should have a larger lateral acceleration component
        # (higher PN gain produces stronger course corrections)
        guided_lat = abs(guided.acceleration.get("y", 0))
        smart_lat = abs(smart.acceleration.get("y", 0))
        assert smart_lat >= guided_lat, (
            f"SMART lateral accel ({smart_lat:.1f}) should >= GUIDED ({guided_lat:.1f})"
        )


# ---------------------------------------------------------------------------
# Telemetry Tests
# ---------------------------------------------------------------------------

class TestTelemetryIncludesCustomization:
    """Verify warhead/guidance/slug info appears in telemetry and events."""

    def test_torpedo_telemetry_has_warhead_and_guidance(self):
        from hybrid.systems.combat.torpedo_manager import TorpedoManager
        mgr = TorpedoManager()
        mgr.spawn(
            shooter_id="s1", target_id="t1",
            position={"x": 0, "y": 0, "z": 0},
            velocity={"x": 500, "y": 0, "z": 0},
            sim_time=0.0,
            target_pos={"x": 50000, "y": 0, "z": 0},
            target_vel={"x": 0, "y": 0, "z": 0},
            warhead_type="emp",
            guidance_mode="smart",
        )
        state = mgr.get_state()
        assert len(state) == 1
        assert state[0]["warhead_type"] == "emp"
        assert state[0]["guidance_mode"] == "smart"

    def test_torpedo_telemetry_defaults(self):
        from hybrid.systems.combat.torpedo_manager import TorpedoManager
        mgr = TorpedoManager()
        mgr.spawn(
            shooter_id="s1", target_id="t1",
            position={"x": 0, "y": 0, "z": 0},
            velocity={"x": 500, "y": 0, "z": 0},
            sim_time=0.0,
            target_pos={"x": 50000, "y": 0, "z": 0},
            target_vel={"x": 0, "y": 0, "z": 0},
        )
        state = mgr.get_state()
        assert state[0]["warhead_type"] == "fragmentation"
        assert state[0]["guidance_mode"] == "guided"


# ---------------------------------------------------------------------------
# Backward Compatibility Tests
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    """All defaults must match pre-customization behaviour."""

    def test_spawn_without_new_params_unchanged(self):
        """Calling spawn() with no warhead/guidance params should behave
        identically to the pre-feature code."""
        from hybrid.systems.combat.torpedo_manager import (
            TorpedoManager, MunitionType, WarheadType, GuidanceMode,
        )
        mgr = TorpedoManager()

        # Torpedo defaults
        t = mgr.spawn(
            shooter_id="s1", target_id="t1",
            position={"x": 0, "y": 0, "z": 0},
            velocity={"x": 100, "y": 0, "z": 0},
            sim_time=0.0,
            target_pos={"x": 10000, "y": 0, "z": 0},
            target_vel={"x": 0, "y": 0, "z": 0},
        )
        assert t.warhead_type == WarheadType.FRAGMENTATION.value
        assert t.guidance_mode == GuidanceMode.GUIDED.value

        # Missile defaults
        m = mgr.spawn(
            shooter_id="s1", target_id="t1",
            position={"x": 0, "y": 0, "z": 0},
            velocity={"x": 100, "y": 0, "z": 0},
            sim_time=0.0,
            target_pos={"x": 10000, "y": 0, "z": 0},
            target_vel={"x": 0, "y": 0, "z": 0},
            munition_type=MunitionType.MISSILE,
        )
        assert m.warhead_type == WarheadType.FRAGMENTATION.value
        assert m.guidance_mode == GuidanceMode.GUIDED.value

    def test_fire_railgun_without_slug_type_unchanged(self):
        """Calling fire() with no slug_type should use standard (1.0x multipliers)."""
        from hybrid.systems.weapons.truth_weapons import (
            create_railgun, SlugType, SLUG_TYPE_MODIFIERS,
        )
        railgun = create_railgun("rg_compat")
        # The method should accept no slug_type without error
        result = railgun.fire(sim_time=10.0, power_manager=None)
        assert isinstance(result, dict)

    def test_combat_system_fire_weapon_no_slug_type(self):
        """CombatSystem.fire_weapon() should work without slug_type."""
        from hybrid.systems.combat.combat_system import CombatSystem
        cs = CombatSystem({"railguns": 1, "pdcs": 0})
        # Will fail (no ship ref), but should not TypeError on missing slug_type
        result = cs.fire_weapon("railgun_1")
        assert result.get("ok") is False


# ---------------------------------------------------------------------------
# Command Registration Tests
# ---------------------------------------------------------------------------

class TestCommandRegistration:
    """Verify new params are registered in the tactical command specs."""

    def _get_dispatcher(self):
        """Build a fresh command dispatcher."""
        from hybrid.commands.dispatch import CommandDispatcher
        from hybrid.commands.tactical_commands import register_commands
        d = CommandDispatcher()
        register_commands(d)
        return d

    def test_fire_railgun_has_slug_type_arg(self):
        d = self._get_dispatcher()
        spec = d.commands.get("fire_railgun")
        assert spec is not None
        arg_names = [a.name for a in spec.args]
        assert "slug_type" in arg_names

    def test_launch_torpedo_has_warhead_and_guidance_args(self):
        d = self._get_dispatcher()
        spec = d.commands.get("launch_torpedo")
        assert spec is not None
        arg_names = [a.name for a in spec.args]
        assert "warhead_type" in arg_names
        assert "guidance_mode" in arg_names

    def test_launch_missile_has_warhead_and_guidance_args(self):
        d = self._get_dispatcher()
        spec = d.commands.get("launch_missile")
        assert spec is not None
        arg_names = [a.name for a in spec.args]
        assert "warhead_type" in arg_names
        assert "guidance_mode" in arg_names

    def test_slug_type_choices(self):
        d = self._get_dispatcher()
        spec = d.commands.get("fire_railgun")
        slug_arg = None
        for a in spec.args:
            if a.name == "slug_type":
                slug_arg = a
                break
        assert slug_arg is not None
        assert set(slug_arg.choices) == {"standard", "sabot", "fragmentation"}

    def test_warhead_type_choices(self):
        d = self._get_dispatcher()
        spec = d.commands.get("launch_torpedo")
        wh_arg = None
        for a in spec.args:
            if a.name == "warhead_type":
                wh_arg = a
                break
        assert wh_arg is not None
        assert set(wh_arg.choices) == {"fragmentation", "shaped_charge", "emp"}

    def test_guidance_mode_choices(self):
        d = self._get_dispatcher()
        spec = d.commands.get("launch_torpedo")
        gm_arg = None
        for a in spec.args:
            if a.name == "guidance_mode":
                gm_arg = a
                break
        assert gm_arg is not None
        assert set(gm_arg.choices) == {"dumb", "guided", "smart"}
