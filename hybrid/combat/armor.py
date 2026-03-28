# hybrid/combat/armor.py
"""Armor thickness and penetration model.

Tracks per-section armor state that degrades under fire. Armor is not HP —
it is a physical barrier with thickness (cm) and material properties.
Penetration depends on projectile KE vs armor resistance at the impact angle.

Key physics:
- Railgun slugs (20 km/s, 5 kg) have enormous KE (~1 GJ). They punch through
  most armor at perpendicular angles but ricochet at oblique angles (>60deg
  from normal). One slug, one subsystem.
- PDC rounds (3 km/s, 50 g) have modest KE (~225 kJ). They bounce off heavy
  armor but ablate it — each hit removes a fraction of a cm. Enough sustained
  fire on one section will eventually punch through.
- Armor ablation is section-specific. Concentrating fire on one facing is a
  valid tactic; spreading fire is wasteful.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# --- Material properties ---

# Resistance factor per cm of armor thickness.
# Higher = harder to penetrate per cm.
MATERIAL_RESISTANCE: Dict[str, float] = {
    "composite_cermet": 1.0,    # Standard military armor
    "steel": 0.6,               # Basic steel plating
    "steel_composite": 0.7,     # Reinforced steel (freighter standard)
    "titanium": 0.8,            # Lighter but weaker
    "depleted_uranium": 1.4,    # Heavy, very resistant
}

# How much thickness (cm) is ablated per joule of impact energy.
# PDC round at 3 km/s = ~225 kJ → ablates ~0.009 cm of composite_cermet.
# 2 cm of cermet needs ~220 rounds to fully strip (about 22 seconds of PDC fire).
ABLATION_RATE: Dict[str, float] = {
    "composite_cermet": 4e-8,   # cm per joule — military grade, slow to ablate
    "steel": 6e-8,              # cheaper steel ablates faster
    "steel_composite": 5e-8,    # between steel and cermet
    "titanium": 5e-8,           # similar to steel composite
    "depleted_uranium": 3e-8,   # very hard, slowest ablation
}

# Angle thresholds (degrees from surface normal).
# 0 = head-on perpendicular hit, 90 = perfectly tangent.
RICOCHET_ANGLE_DEG = 70.0       # Beyond this: full ricochet
GRAZE_ANGLE_DEG = 60.0          # Beyond this: reduced penetration + reduced ablation

# Minimum penetration factor even on ricochet (energy transfer from glancing blow)
MIN_RICOCHET_PEN = 0.05

# Valid armor section names
ARMOR_SECTIONS = ("fore", "aft", "port", "starboard", "dorsal", "ventral")


@dataclass
class ArmorSection:
    """State of one armor facing.

    Thickness decreases as the section takes hits (ablation).
    When thickness reaches 0, the section is stripped — all
    subsequent hits penetrate fully.
    """
    section: str
    original_thickness_cm: float
    thickness_cm: float
    material: str

    def integrity_percent(self) -> float:
        """Remaining armor as a percentage of original thickness."""
        if self.original_thickness_cm <= 0:
            return 0.0
        return max(0.0, min(100.0,
            (self.thickness_cm / self.original_thickness_cm) * 100.0))

    def is_stripped(self) -> bool:
        """True if armor on this section is completely gone."""
        return self.thickness_cm <= 0.0


@dataclass
class PenetrationResult:
    """Outcome of a single projectile-vs-armor interaction.

    Returned by ArmorModel.resolve_hit() so the caller (projectile_manager)
    knows how much damage reaches the subsystem behind the armor.
    """
    # Impact geometry
    armor_section: str
    angle_of_incidence: float       # degrees from surface normal
    is_ricochet: bool

    # Armor state at impact
    armor_thickness_cm: float       # thickness BEFORE this hit
    armor_material: str

    # Penetration outcome
    penetration_factor: float       # 0.0 (stopped) to 1.0+ (clean through)
    ablation_cm: float              # how much armor was removed by this hit

    # Feedback
    description: str

    # Armor state after impact
    remaining_thickness_cm: float   # thickness AFTER ablation


class ArmorModel:
    """Per-ship armor state model.

    Initialised from the ship class definition's ``armor`` dict.
    Tracks ablation over time as the ship takes hits. Provides the
    penetration factor that scales subsystem damage.
    """

    def __init__(self, armor_config: Optional[Dict] = None):
        """Create armor model from ship class armor definition.

        Args:
            armor_config: Dict mapping section name to
                ``{"thickness_cm": float, "material": str}``.
                Missing sections get zero armor (exposed hull).
        """
        self.sections: Dict[str, ArmorSection] = {}
        armor_config = armor_config or {}

        for section_name in ARMOR_SECTIONS:
            section_data = armor_config.get(section_name, {})
            if isinstance(section_data, dict):
                thickness = float(section_data.get("thickness_cm", 0.0))
                material = section_data.get("material", "steel")
            else:
                thickness = 0.0
                material = "steel"

            self.sections[section_name] = ArmorSection(
                section=section_name,
                original_thickness_cm=thickness,
                thickness_cm=thickness,
                material=material,
            )

        # Running totals for telemetry
        self._total_ablation_cm = 0.0
        self._hits_absorbed = 0
        self._ricochets = 0

    def resolve_hit(
        self,
        section: str,
        projectile_velocity: Dict[str, float],
        projectile_mass: float,
        armor_penetration_rating: float,
        angle_of_incidence: float,
    ) -> PenetrationResult:
        """Resolve a projectile impact against a specific armor section.

        Computes penetration factor and ablation. The caller multiplies
        subsystem damage by penetration_factor.

        Physics:
        - KE = 0.5 * m * v^2
        - Effective KE reduced by oblique angle (cos component)
        - Penetration = weapon_pen * KE_factor * oblique / (pen + armor_resistance)
        - Ablation = KE_normal * material_ablation_rate

        Args:
            section: Which armor section was hit (fore/aft/port/starboard/dorsal/ventral)
            projectile_velocity: Velocity vector {x, y, z} in m/s
            projectile_mass: Mass in kg
            armor_penetration_rating: Weapon's base armor pen multiplier
            angle_of_incidence: Degrees from surface normal (0 = perpendicular)

        Returns:
            PenetrationResult with all outcome data
        """
        armor = self.sections.get(section)
        if armor is None:
            # Unknown section — treat as unarmored
            armor = ArmorSection(
                section=section,
                original_thickness_cm=0.0,
                thickness_cm=0.0,
                material="steel",
            )

        self._hits_absorbed += 1

        # --- Ricochet check ---
        is_ricochet = angle_of_incidence > RICOCHET_ANGLE_DEG

        # --- Projectile kinetic energy ---
        speed = math.sqrt(
            projectile_velocity["x"] ** 2
            + projectile_velocity["y"] ** 2
            + projectile_velocity["z"] ** 2
        )
        ke_joules = 0.5 * projectile_mass * speed * speed

        # --- Oblique angle factor ---
        # cos(0) = 1.0 (perpendicular, full effect)
        # cos(60) = 0.5 (grazing, half effect)
        # cos(70+) = ricochet territory
        angle_rad = math.radians(min(angle_of_incidence, 89.0))
        oblique_factor = math.cos(angle_rad)

        # Normal component of KE (energy actually delivered into armor)
        ke_normal = ke_joules * oblique_factor

        # --- Armor resistance ---
        material_factor = MATERIAL_RESISTANCE.get(armor.material, 1.0)
        armor_resistance = armor.thickness_cm * material_factor * 0.1

        # --- Penetration factor ---
        if is_ricochet:
            penetration = MIN_RICOCHET_PEN
            self._ricochets += 1
        elif armor.thickness_cm <= 0:
            # No armor left — full penetration
            penetration = 1.0
        else:
            # KE factor normalised to railgun baseline (1 GJ)
            ke_factor = min(2.0, ke_joules / 1e9)
            effective_pen = armor_penetration_rating * ke_factor * oblique_factor
            if armor_resistance > 0:
                penetration = effective_pen / (effective_pen + armor_resistance)
            else:
                penetration = 1.0
            penetration = max(0.0, min(1.5, penetration))

        # --- Ablation ---
        # Even ricochets ablate a tiny amount (surface scoring).
        # Normal hits ablate proportional to the energy delivered into the plate.
        ablation_rate = ABLATION_RATE.get(armor.material, 5e-8)
        if is_ricochet:
            # Ricochets barely scratch the surface
            ablation = ke_normal * ablation_rate * 0.1
        elif angle_of_incidence > GRAZE_ANGLE_DEG:
            # Grazing hits: reduced ablation
            ablation = ke_normal * ablation_rate * 0.5
        else:
            ablation = ke_normal * ablation_rate

        # Apply ablation
        pre_thickness = armor.thickness_cm
        armor.thickness_cm = max(0.0, armor.thickness_cm - ablation)
        actual_ablation = pre_thickness - armor.thickness_cm
        self._total_ablation_cm += actual_ablation

        # --- Description ---
        description = _describe_impact(
            section, angle_of_incidence, is_ricochet,
            penetration, pre_thickness, armor.material, actual_ablation,
        )

        if actual_ablation > 0.01:
            logger.debug(
                "Armor hit: %s section, %.2f cm ablated (%.2f -> %.2f cm), pen=%.2f",
                section, actual_ablation, pre_thickness, armor.thickness_cm, penetration,
            )

        return PenetrationResult(
            armor_section=section,
            angle_of_incidence=angle_of_incidence,
            is_ricochet=is_ricochet,
            armor_thickness_cm=pre_thickness,
            armor_material=armor.material,
            penetration_factor=penetration,
            ablation_cm=actual_ablation,
            description=description,
            remaining_thickness_cm=armor.thickness_cm,
        )

    def repair_section(self, section: str, amount_cm: float) -> float:
        """Repair armor on a section (e.g. during docking resupply).

        Cannot exceed original thickness — you cannot add armor in the field.

        Args:
            section: Armor section to repair
            amount_cm: Centimeters of armor to restore

        Returns:
            Actual amount repaired
        """
        armor = self.sections.get(section)
        if armor is None or amount_cm <= 0:
            return 0.0
        pre = armor.thickness_cm
        armor.thickness_cm = min(
            armor.original_thickness_cm,
            armor.thickness_cm + amount_cm,
        )
        return armor.thickness_cm - pre

    def get_section_status(self, section: str) -> Optional[Dict]:
        """Get status dict for a single armor section.

        Returns:
            Dict with thickness, material, integrity, or None if unknown section
        """
        armor = self.sections.get(section)
        if armor is None:
            return None
        return {
            "section": armor.section,
            "thickness_cm": round(armor.thickness_cm, 3),
            "original_thickness_cm": armor.original_thickness_cm,
            "material": armor.material,
            "integrity_percent": round(armor.integrity_percent(), 1),
            "stripped": armor.is_stripped(),
        }

    def get_status(self) -> Dict:
        """Full armor status for telemetry.

        Returns:
            Dict with per-section status and aggregate stats
        """
        sections = {}
        total_original = 0.0
        total_current = 0.0

        for name in ARMOR_SECTIONS:
            armor = self.sections[name]
            sections[name] = self.get_section_status(name)
            total_original += armor.original_thickness_cm
            total_current += armor.thickness_cm

        overall_integrity = (
            (total_current / total_original * 100.0)
            if total_original > 0 else 0.0
        )

        return {
            "sections": sections,
            "overall_integrity_percent": round(overall_integrity, 1),
            "total_ablation_cm": round(self._total_ablation_cm, 3),
            "hits_absorbed": self._hits_absorbed,
            "ricochets": self._ricochets,
        }


def _describe_impact(
    section: str,
    angle: float,
    is_ricochet: bool,
    penetration: float,
    thickness_cm: float,
    material: str,
    ablation_cm: float,
) -> str:
    """Generate human-readable description of an armor interaction."""
    section_label = {
        "fore": "forward hull",
        "aft": "aft hull",
        "port": "port side",
        "starboard": "starboard side",
        "dorsal": "dorsal plating",
        "ventral": "ventral plating",
    }.get(section, section)

    if is_ricochet:
        return (
            f"Ricochet off {section_label} — {angle:.0f} deg incidence, "
            f"{thickness_cm:.1f}cm {material} deflected the round"
        )

    if thickness_cm <= 0:
        return (
            f"Unarmored hit on {section_label} — armor stripped, "
            f"full penetration"
        )

    if penetration < 0.2:
        return (
            f"Stopped by {section_label} armor — {thickness_cm:.1f}cm {material} "
            f"absorbed the impact ({angle:.0f} deg), "
            f"{ablation_cm:.3f}cm ablated"
        )

    if penetration < 0.6:
        return (
            f"Partial penetration of {section_label} — "
            f"{thickness_cm:.1f}cm {material} at {angle:.0f} deg, "
            f"pen factor {penetration:.0%}, {ablation_cm:.3f}cm ablated"
        )

    return (
        f"Penetration through {section_label} — "
        f"{thickness_cm:.1f}cm {material} at {angle:.0f} deg, "
        f"pen factor {penetration:.0%}, {ablation_cm:.3f}cm ablated"
    )
