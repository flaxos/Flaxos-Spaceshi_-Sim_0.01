# tests/test_armor_penetration.py
"""Tests for the armor thickness and penetration model.

Validates:
- Armor section initialization from ship class config
- Railgun penetration at various angles
- PDC ablation mechanics (repeated hits degrade armor)
- Ricochet behaviour at oblique angles
- Stripped armor → full penetration
- Telemetry status output
- Integration with projectile manager hit pipeline
"""

import math
import pytest
from typing import Dict

from hybrid.combat.armor import (
    ArmorModel,
    ArmorSection,
    PenetrationResult,
    ARMOR_SECTIONS,
    RICOCHET_ANGLE_DEG,
    MATERIAL_RESISTANCE,
    ABLATION_RATE,
)


# --- Helpers ---

def _corvette_armor() -> Dict:
    """Armor config matching the corvette ship class."""
    return {
        "fore":      {"thickness_cm": 3.0, "material": "composite_cermet"},
        "aft":       {"thickness_cm": 1.5, "material": "composite_cermet"},
        "port":      {"thickness_cm": 2.0, "material": "composite_cermet"},
        "starboard": {"thickness_cm": 2.0, "material": "composite_cermet"},
        "dorsal":    {"thickness_cm": 2.0, "material": "composite_cermet"},
        "ventral":   {"thickness_cm": 2.0, "material": "composite_cermet"},
    }


def _freighter_armor() -> Dict:
    """Armor config matching the freighter ship class."""
    return {
        "fore":      {"thickness_cm": 5.0, "material": "steel_composite"},
        "aft":       {"thickness_cm": 3.0, "material": "steel_composite"},
        "port":      {"thickness_cm": 4.0, "material": "steel_composite"},
        "starboard": {"thickness_cm": 4.0, "material": "steel_composite"},
        "dorsal":    {"thickness_cm": 3.0, "material": "steel_composite"},
        "ventral":   {"thickness_cm": 3.0, "material": "steel_composite"},
    }


def _railgun_velocity(angle_deg: float = 0.0) -> Dict[str, float]:
    """Railgun slug velocity at 20 km/s approaching along X axis.

    angle_deg: angle off the X axis (0 = head-on perpendicular to fore)
    """
    speed = 20_000.0  # m/s
    rad = math.radians(angle_deg)
    return {
        "x": -speed * math.cos(rad),
        "y": speed * math.sin(rad),
        "z": 0.0,
    }


def _pdc_velocity(angle_deg: float = 0.0) -> Dict[str, float]:
    """PDC round velocity at 3 km/s approaching along X axis."""
    speed = 3_000.0
    rad = math.radians(angle_deg)
    return {
        "x": -speed * math.cos(rad),
        "y": speed * math.sin(rad),
        "z": 0.0,
    }


RAILGUN_MASS = 5.0         # kg
RAILGUN_PEN_RATING = 1.5
PDC_MASS = 0.05            # kg (50g)
PDC_PEN_RATING = 0.5


# --- Initialization tests ---

class TestArmorModelInit:
    """Test armor model construction from config."""

    def test_init_from_corvette_config(self):
        model = ArmorModel(_corvette_armor())
        assert len(model.sections) == 6
        assert model.sections["fore"].thickness_cm == 3.0
        assert model.sections["fore"].material == "composite_cermet"
        assert model.sections["aft"].thickness_cm == 1.5

    def test_init_empty_config(self):
        """Ships without armor config get zero-thickness sections."""
        model = ArmorModel(None)
        for section in ARMOR_SECTIONS:
            assert model.sections[section].thickness_cm == 0.0

    def test_init_partial_config(self):
        """Missing sections default to zero armor."""
        model = ArmorModel({"fore": {"thickness_cm": 5.0, "material": "steel"}})
        assert model.sections["fore"].thickness_cm == 5.0
        assert model.sections["aft"].thickness_cm == 0.0

    def test_original_thickness_preserved(self):
        model = ArmorModel(_corvette_armor())
        assert model.sections["fore"].original_thickness_cm == 3.0

    def test_integrity_starts_at_100(self):
        model = ArmorModel(_corvette_armor())
        for section in ARMOR_SECTIONS:
            assert model.sections[section].integrity_percent() == 100.0


# --- Railgun penetration tests ---

class TestRailgunPenetration:
    """Railgun at 20 km/s should penetrate most armor at good angles."""

    def test_perpendicular_hit_penetrates(self):
        """Head-on railgun slug should achieve high penetration."""
        model = ArmorModel(_corvette_armor())
        result = model.resolve_hit(
            section="fore",
            projectile_velocity=_railgun_velocity(0),
            projectile_mass=RAILGUN_MASS,
            armor_penetration_rating=RAILGUN_PEN_RATING,
            angle_of_incidence=0.0,
        )
        assert not result.is_ricochet
        # 20 km/s slug vs 3 cm cermet should get high penetration
        assert result.penetration_factor > 0.7
        assert result.ablation_cm > 0

    def test_oblique_hit_reduced_penetration(self):
        """45-degree hit should have reduced but nonzero penetration."""
        model = ArmorModel(_corvette_armor())
        perp = model.resolve_hit(
            section="fore",
            projectile_velocity=_railgun_velocity(0),
            projectile_mass=RAILGUN_MASS,
            armor_penetration_rating=RAILGUN_PEN_RATING,
            angle_of_incidence=0.0,
        )
        model2 = ArmorModel(_corvette_armor())
        oblique = model2.resolve_hit(
            section="fore",
            projectile_velocity=_railgun_velocity(45),
            projectile_mass=RAILGUN_MASS,
            armor_penetration_rating=RAILGUN_PEN_RATING,
            angle_of_incidence=45.0,
        )
        assert oblique.penetration_factor < perp.penetration_factor
        assert oblique.penetration_factor > 0.0

    def test_ricochet_at_extreme_angle(self):
        """Beyond 70 degrees: ricochet with minimal penetration."""
        model = ArmorModel(_corvette_armor())
        result = model.resolve_hit(
            section="fore",
            projectile_velocity=_railgun_velocity(75),
            projectile_mass=RAILGUN_MASS,
            armor_penetration_rating=RAILGUN_PEN_RATING,
            angle_of_incidence=75.0,
        )
        assert result.is_ricochet
        assert result.penetration_factor < 0.1

    def test_railgun_vs_heavy_armor(self):
        """Railgun against destroyer's 8cm cermet should still penetrate."""
        heavy_armor = {"fore": {"thickness_cm": 8.0, "material": "composite_cermet"}}
        model = ArmorModel(heavy_armor)
        result = model.resolve_hit(
            section="fore",
            projectile_velocity=_railgun_velocity(0),
            projectile_mass=RAILGUN_MASS,
            armor_penetration_rating=RAILGUN_PEN_RATING,
            angle_of_incidence=0.0,
        )
        # Should still penetrate, but less than light armor
        assert result.penetration_factor > 0.4


# --- PDC ablation tests ---

class TestPDCAblation:
    """PDC rounds should ablate armor over sustained fire."""

    def test_single_pdc_round_low_pen(self):
        """One PDC round vs military armor: low penetration."""
        model = ArmorModel(_corvette_armor())
        result = model.resolve_hit(
            section="fore",
            projectile_velocity=_pdc_velocity(0),
            projectile_mass=PDC_MASS,
            armor_penetration_rating=PDC_PEN_RATING,
            angle_of_incidence=0.0,
        )
        # PDC should have very low pen vs 3cm cermet
        assert result.penetration_factor < 0.3
        # But should ablate some armor
        assert result.ablation_cm > 0

    def test_sustained_pdc_fire_ablates_armor(self):
        """Many PDC rounds on the same section should reduce thickness."""
        model = ArmorModel(_corvette_armor())
        initial_thickness = model.sections["fore"].thickness_cm

        # Fire 100 PDC rounds at the fore section
        for _ in range(100):
            model.resolve_hit(
                section="fore",
                projectile_velocity=_pdc_velocity(0),
                projectile_mass=PDC_MASS,
                armor_penetration_rating=PDC_PEN_RATING,
                angle_of_incidence=10.0,
            )

        # Armor should be noticeably thinner
        remaining = model.sections["fore"].thickness_cm
        assert remaining < initial_thickness
        assert remaining >= 0.0

    def test_enough_pdc_rounds_strip_armor(self):
        """Sufficient PDC fire should eventually strip armor completely."""
        # Use thin armor to make the test tractable
        thin_armor = {"fore": {"thickness_cm": 0.5, "material": "steel"}}
        model = ArmorModel(thin_armor)

        rounds = 0
        max_rounds = 5000
        while model.sections["fore"].thickness_cm > 0 and rounds < max_rounds:
            model.resolve_hit(
                section="fore",
                projectile_velocity=_pdc_velocity(0),
                projectile_mass=PDC_MASS,
                armor_penetration_rating=PDC_PEN_RATING,
                angle_of_incidence=5.0,
            )
            rounds += 1

        assert model.sections["fore"].is_stripped(), (
            f"Armor not stripped after {max_rounds} PDC rounds; "
            f"remaining: {model.sections['fore'].thickness_cm:.4f} cm"
        )

    def test_stripped_armor_full_penetration(self):
        """Once armor is stripped, subsequent hits fully penetrate."""
        model = ArmorModel({"fore": {"thickness_cm": 0.0, "material": "steel"}})
        result = model.resolve_hit(
            section="fore",
            projectile_velocity=_pdc_velocity(0),
            projectile_mass=PDC_MASS,
            armor_penetration_rating=PDC_PEN_RATING,
            angle_of_incidence=0.0,
        )
        assert result.penetration_factor == 1.0

    def test_pdc_bounces_off_heavy_armor(self):
        """PDC vs destroyer-class 8cm cermet: very low penetration."""
        heavy = {"fore": {"thickness_cm": 8.0, "material": "composite_cermet"}}
        model = ArmorModel(heavy)
        result = model.resolve_hit(
            section="fore",
            projectile_velocity=_pdc_velocity(0),
            projectile_mass=PDC_MASS,
            armor_penetration_rating=PDC_PEN_RATING,
            angle_of_incidence=0.0,
        )
        assert result.penetration_factor < 0.15

    def test_ablation_is_section_specific(self):
        """Hitting fore should not reduce aft armor."""
        model = ArmorModel(_corvette_armor())
        aft_before = model.sections["aft"].thickness_cm

        for _ in range(50):
            model.resolve_hit(
                section="fore",
                projectile_velocity=_pdc_velocity(0),
                projectile_mass=PDC_MASS,
                armor_penetration_rating=PDC_PEN_RATING,
                angle_of_incidence=10.0,
            )

        assert model.sections["aft"].thickness_cm == aft_before


# --- Ricochet and angle mechanics ---

class TestRicochetMechanics:
    """Test angle-dependent behavior."""

    def test_ricochet_threshold(self):
        model = ArmorModel(_corvette_armor())

        # Just under ricochet threshold: not a ricochet
        result_under = model.resolve_hit(
            section="fore",
            projectile_velocity=_railgun_velocity(69),
            projectile_mass=RAILGUN_MASS,
            armor_penetration_rating=RAILGUN_PEN_RATING,
            angle_of_incidence=69.0,
        )
        model2 = ArmorModel(_corvette_armor())
        # Just over: ricochet
        result_over = model2.resolve_hit(
            section="fore",
            projectile_velocity=_railgun_velocity(71),
            projectile_mass=RAILGUN_MASS,
            armor_penetration_rating=RAILGUN_PEN_RATING,
            angle_of_incidence=71.0,
        )
        assert not result_under.is_ricochet
        assert result_over.is_ricochet

    def test_ricochet_still_ablates_slightly(self):
        """Even ricochets should score the armor surface."""
        model = ArmorModel(_corvette_armor())
        result = model.resolve_hit(
            section="fore",
            projectile_velocity=_railgun_velocity(75),
            projectile_mass=RAILGUN_MASS,
            armor_penetration_rating=RAILGUN_PEN_RATING,
            angle_of_incidence=75.0,
        )
        assert result.is_ricochet
        assert result.ablation_cm > 0  # Some surface scoring


# --- Status and telemetry ---

class TestArmorStatus:
    """Test status output for telemetry."""

    def test_full_status_structure(self):
        model = ArmorModel(_corvette_armor())
        status = model.get_status()

        assert "sections" in status
        assert "overall_integrity_percent" in status
        assert "total_ablation_cm" in status
        assert "hits_absorbed" in status
        assert "ricochets" in status
        assert len(status["sections"]) == 6

    def test_section_status_fields(self):
        model = ArmorModel(_corvette_armor())
        sec = model.get_section_status("fore")
        assert sec is not None
        assert sec["thickness_cm"] == 3.0
        assert sec["original_thickness_cm"] == 3.0
        assert sec["material"] == "composite_cermet"
        assert sec["integrity_percent"] == 100.0
        assert sec["stripped"] is False

    def test_integrity_decreases_after_hits(self):
        model = ArmorModel(_corvette_armor())

        for _ in range(50):
            model.resolve_hit(
                section="fore",
                projectile_velocity=_pdc_velocity(0),
                projectile_mass=PDC_MASS,
                armor_penetration_rating=PDC_PEN_RATING,
                angle_of_incidence=10.0,
            )

        status = model.get_status()
        assert status["overall_integrity_percent"] < 100.0
        assert status["total_ablation_cm"] > 0
        assert status["hits_absorbed"] == 50

    def test_unknown_section_returns_none(self):
        model = ArmorModel(_corvette_armor())
        assert model.get_section_status("nonexistent") is None


# --- Repair ---

class TestArmorRepair:
    """Test armor repair mechanics."""

    def test_repair_restores_thickness(self):
        model = ArmorModel(_corvette_armor())
        # Ablate some armor
        for _ in range(30):
            model.resolve_hit(
                section="fore",
                projectile_velocity=_pdc_velocity(0),
                projectile_mass=PDC_MASS,
                armor_penetration_rating=PDC_PEN_RATING,
                angle_of_incidence=10.0,
            )
        damaged = model.sections["fore"].thickness_cm
        assert damaged < 3.0

        repaired = model.repair_section("fore", 10.0)
        # Cannot exceed original
        assert model.sections["fore"].thickness_cm == 3.0
        assert repaired == pytest.approx(3.0 - damaged, abs=0.001)

    def test_repair_invalid_section(self):
        model = ArmorModel(_corvette_armor())
        assert model.repair_section("nonexistent", 1.0) == 0.0


# --- Material differences ---

class TestMaterialProperties:
    """Verify different materials behave differently."""

    def test_steel_weaker_than_cermet(self):
        """Steel should be easier to penetrate per cm than cermet."""
        steel_model = ArmorModel({"fore": {"thickness_cm": 3.0, "material": "steel"}})
        cermet_model = ArmorModel({"fore": {"thickness_cm": 3.0, "material": "composite_cermet"}})

        steel_result = steel_model.resolve_hit(
            section="fore",
            projectile_velocity=_pdc_velocity(0),
            projectile_mass=PDC_MASS,
            armor_penetration_rating=PDC_PEN_RATING,
            angle_of_incidence=10.0,
        )
        cermet_result = cermet_model.resolve_hit(
            section="fore",
            projectile_velocity=_pdc_velocity(0),
            projectile_mass=PDC_MASS,
            armor_penetration_rating=PDC_PEN_RATING,
            angle_of_incidence=10.0,
        )

        # Steel should allow higher penetration
        assert steel_result.penetration_factor > cermet_result.penetration_factor

    def test_depleted_uranium_toughest(self):
        """DU armor should be hardest to penetrate."""
        du_model = ArmorModel({"fore": {"thickness_cm": 3.0, "material": "depleted_uranium"}})
        result = du_model.resolve_hit(
            section="fore",
            projectile_velocity=_pdc_velocity(0),
            projectile_mass=PDC_MASS,
            armor_penetration_rating=PDC_PEN_RATING,
            angle_of_incidence=0.0,
        )
        # DU should have lowest PDC penetration
        assert result.penetration_factor < 0.1


# --- Weapon differentiation ---

class TestWeaponDifferentiation:
    """Verify the feature creates meaningful weapon roles."""

    def test_railgun_vs_pdc_same_target(self):
        """Railgun should penetrate where PDC cannot (on same armor)."""
        armor_cfg = {"fore": {"thickness_cm": 4.0, "material": "composite_cermet"}}

        rg_model = ArmorModel(armor_cfg)
        rg_result = rg_model.resolve_hit(
            section="fore",
            projectile_velocity=_railgun_velocity(0),
            projectile_mass=RAILGUN_MASS,
            armor_penetration_rating=RAILGUN_PEN_RATING,
            angle_of_incidence=0.0,
        )

        pdc_model = ArmorModel(armor_cfg)
        pdc_result = pdc_model.resolve_hit(
            section="fore",
            projectile_velocity=_pdc_velocity(0),
            projectile_mass=PDC_MASS,
            armor_penetration_rating=PDC_PEN_RATING,
            angle_of_incidence=0.0,
        )

        # Railgun: high penetration. PDC: low penetration.
        assert rg_result.penetration_factor > 0.5
        assert pdc_result.penetration_factor < 0.3
        # This IS the design intent: railgun = precision penetrator,
        # PDC = ablative suppression weapon.

    def test_pdc_effective_against_stripped_armor(self):
        """PDC should be fully effective once armor is gone."""
        model = ArmorModel({"fore": {"thickness_cm": 0.0, "material": "steel"}})
        result = model.resolve_hit(
            section="fore",
            projectile_velocity=_pdc_velocity(0),
            projectile_mass=PDC_MASS,
            armor_penetration_rating=PDC_PEN_RATING,
            angle_of_incidence=0.0,
        )
        assert result.penetration_factor == 1.0

    def test_pdc_ablates_light_armor_then_penetrates(self):
        """PDC rounds individually bounce off even thin armor, but
        sustained fire ablates it away and then penetrates fully.
        This is the core PDC design: ablative suppression weapon."""
        model = ArmorModel({"fore": {"thickness_cm": 0.5, "material": "steel"}})

        # Single round: blocked
        first = model.resolve_hit(
            section="fore",
            projectile_velocity=_pdc_velocity(0),
            projectile_mass=PDC_MASS,
            armor_penetration_rating=PDC_PEN_RATING,
            angle_of_incidence=0.0,
        )
        assert first.penetration_factor < 0.1
        assert first.ablation_cm > 0

        # Keep firing until armor stripped
        rounds = 1
        while not model.sections["fore"].is_stripped() and rounds < 5000:
            model.resolve_hit(
                section="fore",
                projectile_velocity=_pdc_velocity(0),
                projectile_mass=PDC_MASS,
                armor_penetration_rating=PDC_PEN_RATING,
                angle_of_incidence=0.0,
            )
            rounds += 1

        # Now PDC fully penetrates
        final = model.resolve_hit(
            section="fore",
            projectile_velocity=_pdc_velocity(0),
            projectile_mass=PDC_MASS,
            armor_penetration_rating=PDC_PEN_RATING,
            angle_of_incidence=0.0,
        )
        assert final.penetration_factor == 1.0
