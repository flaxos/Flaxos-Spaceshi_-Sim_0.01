"""Persistent campaign state that carries forward between missions.

Reputation is per-faction (-100 hostile to +100 allied). Ship state carries
hull, subsystem health, ammo, and fuel -- not the full physics snapshot
(position/velocity reset each scenario).
"""

from __future__ import annotations

import copy
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from hybrid.campaign.defaults import (
    CREDIT_REWARDS,
    DEFAULT_FACTIONS,
    STARTING_CREDITS,
    make_starter_crew,
    make_starter_ship,
)
from hybrid.campaign.snapshot import apply_crew_snapshot, apply_ship_snapshot

logger = logging.getLogger(__name__)


@dataclass
class CampaignState:
    """Persistent state across campaign missions.

    All fields are plain JSON-serialisable types so the entire object can
    be round-tripped through save/load without custom encoders.
    """

    # Ship state carried from last mission
    ship_state: Dict[str, Any] = field(default_factory=dict)

    # Crew roster -- list of crew member dicts (mirrors CrewMember.to_dict())
    crew_roster: List[Dict[str, Any]] = field(default_factory=list)

    # Per-faction reputation (-100 to +100)
    reputation: Dict[str, int] = field(default_factory=dict)

    # Currency for repairs/resupply/upgrades
    credits: int = 0

    # Completed mission history
    mission_history: List[Dict[str, Any]] = field(default_factory=list)

    # Scenario IDs available for the next mission selection
    unlocked_scenarios: List[str] = field(default_factory=list)

    # Current chapter in the campaign arc (0-indexed)
    current_chapter: int = 0

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, filepath: str) -> None:
        """Save campaign state to a JSON file.

        Args:
            filepath: Destination path. Parent directories are created
                      automatically if they don't exist.
        """
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = self._to_dict()
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.info("Campaign saved to %s", filepath)

    @classmethod
    def load(cls, filepath: str) -> "CampaignState":
        """Load campaign state from a JSON file.

        Args:
            filepath: Path to a previously saved campaign JSON file.

        Returns:
            Reconstructed CampaignState.

        Raises:
            FileNotFoundError: If the file does not exist.
            json.JSONDecodeError: If the file is not valid JSON.
        """
        path = Path(filepath)
        data = json.loads(path.read_text(encoding="utf-8"))
        state = cls._from_dict(data)
        logger.info("Campaign loaded from %s", filepath)
        return state

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def new_campaign(cls, ship_class: str = "corvette") -> "CampaignState":
        """Create a fresh campaign state with a starter ship and crew.

        The starter ship is a lightly-armed corvette with full fuel and
        a standard ammo loadout. Two crew members are generated with
        competent-level skills.

        Args:
            ship_class: Ship class for the player's starting vessel.

        Returns:
            A new CampaignState ready for the first mission.
        """
        return cls(
            ship_state=make_starter_ship(ship_class),
            crew_roster=make_starter_crew(),
            reputation=dict(DEFAULT_FACTIONS),
            credits=STARTING_CREDITS,
            mission_history=[],
            unlocked_scenarios=["01_tutorial_intercept"],
            current_chapter=0,
        )

    # ------------------------------------------------------------------
    # Mission lifecycle
    # ------------------------------------------------------------------

    def apply_mission_result(self, mission_result: dict) -> None:
        """Update campaign state after a mission completes.

        Carries forward ship state, crew XP, reputation, credits, and
        unlocks the next scenario(s). See defaults.py for credit tiers.
        """
        outcome = mission_result.get("outcome", "failure")
        scenario_id = mission_result.get("scenario_id", "unknown")
        score = mission_result.get("score", 0)

        # 1. Carry forward ship damage/ammo/fuel
        ship_snapshot = mission_result.get("ship_snapshot")
        if ship_snapshot:
            apply_ship_snapshot(self.ship_state, ship_snapshot)

        # 2. Update crew fatigue/injury/XP
        # Always call even with empty snapshot -- XP awards happen regardless
        crew_snapshot = mission_result.get("crew_snapshot", [])
        apply_crew_snapshot(self.crew_roster, crew_snapshot, outcome)

        # 3. Adjust reputation based on choices
        rep_changes = mission_result.get("reputation_changes", {})
        for faction, delta in rep_changes.items():
            current = self.reputation.get(faction, 0)
            self.reputation[faction] = max(-100, min(100, current + delta))

        # 4. Award credits based on outcome and score
        base_reward = CREDIT_REWARDS.get(outcome, 0)
        # Score bonus: up to +50% of base reward for perfect score
        score_bonus = int(base_reward * (score / 100.0) * 0.5)
        self.credits += base_reward + score_bonus

        # 5. Unlock next scenarios
        next_scenarios = mission_result.get("next_scenarios", [])
        for sid in next_scenarios:
            if sid not in self.unlocked_scenarios:
                self.unlocked_scenarios.append(sid)

        # 6. Record in history
        self.mission_history.append({
            "scenario_id": scenario_id,
            "outcome": outcome,
            "score": score,
            "choices": mission_result.get("choices", []),
            "credits_earned": base_reward + score_bonus,
        })

        # 7. Advance chapter on success
        if outcome == "success":
            self.current_chapter += 1

        logger.info(
            "Campaign updated: scenario=%s outcome=%s credits=%d chapter=%d",
            scenario_id, outcome, self.credits, self.current_chapter,
        )

    def inject_into_scenario(self, scenario_data: dict) -> dict:
        """Overlay campaign ship state onto a scenario's player ship definition.

        Returns a deep copy with hull, subsystems, ammo, fuel, and crew
        injected. Non-player ships and scenario structure are untouched.
        """
        result = copy.deepcopy(scenario_data)
        ships = result.get("ships", [])

        for ship_def in ships:
            if not ship_def.get("player_controlled"):
                continue

            # Overlay hull integrity
            hull_pct = self.ship_state.get("hull_percent", 100.0)
            if "mass" in ship_def:
                max_hull = ship_def.get("max_hull_integrity", ship_def["mass"] / 10.0)
                ship_def["hull_integrity"] = max_hull * (hull_pct / 100.0)

            # Overlay subsystem health into the systems block
            systems = ship_def.get("systems", {})
            subsys_health = self.ship_state.get("subsystems", {})
            for sys_name, health_pct in subsys_health.items():
                if sys_name in systems:
                    if isinstance(systems[sys_name], dict):
                        systems[sys_name]["health"] = health_pct / 100.0
                    else:
                        systems[sys_name] = {"health": health_pct / 100.0}

            # Overlay ammo counts
            campaign_ammo = self.ship_state.get("ammo", {})
            if campaign_ammo and "weapons" in systems:
                weapons_cfg = systems["weapons"]
                if isinstance(weapons_cfg, dict):
                    weapons_cfg["ammo"] = dict(campaign_ammo)

            # Overlay fuel
            campaign_fuel = self.ship_state.get("fuel")
            if campaign_fuel is not None and "propulsion" in systems:
                prop_cfg = systems["propulsion"]
                if isinstance(prop_cfg, dict):
                    prop_cfg["fuel_level"] = campaign_fuel

            # Overlay crew roster (attach to ship def for the crew system)
            if self.crew_roster:
                ship_def["crew_roster"] = copy.deepcopy(self.crew_roster)

            # Only inject into the first player ship
            break

        return result

    # ------------------------------------------------------------------
    # Query helpers (for GUI / telemetry)
    # ------------------------------------------------------------------

    def get_summary(self) -> dict:
        """Return a JSON-friendly summary for the campaign hub GUI.

        Returns:
            Dict with credits, reputation, chapter, ship overview, crew
            count, and mission history length.
        """
        return {
            "credits": self.credits,
            "reputation": dict(self.reputation),
            "current_chapter": self.current_chapter,
            "ship_class": self.ship_state.get("class", "unknown"),
            "hull_percent": self.ship_state.get("hull_percent", 0),
            "subsystems": self.ship_state.get("subsystems", {}),
            "ammo": self.ship_state.get("ammo", {}),
            "fuel": self.ship_state.get("fuel", 0),
            "max_fuel": self.ship_state.get("max_fuel", 0),
            "crew_count": len(self.crew_roster),
            "crew_roster": list(self.crew_roster),
            "missions_completed": len(self.mission_history),
            "mission_history": list(self.mission_history),
            "unlocked_scenarios": list(self.unlocked_scenarios),
        }

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def _to_dict(self) -> dict:
        """Serialise to a plain dict for JSON persistence."""
        return {
            "version": 1,
            "ship_state": self.ship_state,
            "crew_roster": self.crew_roster,
            "reputation": self.reputation,
            "credits": self.credits,
            "mission_history": self.mission_history,
            "unlocked_scenarios": self.unlocked_scenarios,
            "current_chapter": self.current_chapter,
        }

    @classmethod
    def _from_dict(cls, data: dict) -> "CampaignState":
        """Reconstruct from a plain dict (loaded from JSON)."""
        return cls(
            ship_state=data.get("ship_state", {}),
            crew_roster=data.get("crew_roster", []),
            reputation=data.get("reputation", {}),
            credits=data.get("credits", 0),
            mission_history=data.get("mission_history", []),
            unlocked_scenarios=data.get("unlocked_scenarios", []),
            current_chapter=data.get("current_chapter", 0),
        )
