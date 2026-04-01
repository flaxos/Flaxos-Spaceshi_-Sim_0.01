# hybrid/scenarios/skirmish_generator.py
"""Quick-play skirmish scenario generator.

Generates valid scenario dicts from simple parameters, same structure
as ScenarioLoader.load() so the runner can consume them directly.
"""

import math
import random
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Fallback stats per ship class (mass kg, thrust N, fuel kg)
_CLASS_DEFAULTS = {
    "fighter":        {"mass": 800,    "thrust": 30000,  "fuel": 300},
    "corvette":       {"mass": 5000,   "thrust": 50000,  "fuel": 10000},
    "gunship":        {"mass": 6000,   "thrust": 45000,  "fuel": 8000},
    "frigate":        {"mass": 8000,   "thrust": 40000,  "fuel": 8000},
    "destroyer":      {"mass": 15000,  "thrust": 60000,  "fuel": 15000},
    "cruiser":        {"mass": 30000,  "thrust": 80000,  "fuel": 25000},
    "battleship":     {"mass": 80000,  "thrust": 120000, "fuel": 50000},
    "carrier":        {"mass": 100000, "thrust": 100000, "fuel": 60000},
    "freighter":      {"mass": 50000,  "thrust": 20000,  "fuel": 20000},
    "science_vessel": {"mass": 12000,  "thrust": 25000,  "fuel": 12000},
    "station":        {"mass": 200000, "thrust": 0,      "fuel": 0},
}

VALID_MODES = {"deathmatch", "team", "defend", "escort"}

_AI_PRESETS = {
    "combat":    {"behavior": "combat", "params": {"engagement_range": 50000, "flee_threshold": 0.2}},
    "capital":   {"behavior": "combat", "params": {"engagement_range": 80000, "flee_threshold": 0.15}},
    "freighter": {"behavior": "evade",  "params": {"flee_threshold": 0.9}},
}


def generate_skirmish(params: dict) -> dict:
    """Generate a skirmish scenario from parameters.

    Args:
        params: mode, player_ships, enemy_ships, start_range_km,
                time_limit_seconds, randomize_positions, seed

    Returns:
        Scenario dict compatible with hybrid_runner.load_scenario_dict().
    """
    mode = params.get("mode", "deathmatch")
    if mode not in VALID_MODES:
        raise ValueError(f"Invalid mode '{mode}'. Choose from: {sorted(VALID_MODES)}")

    player_defs = params.get("player_ships") or [{"class": "corvette"}]
    enemy_defs = params.get("enemy_ships") or [{"class": "frigate"}]
    range_km = float(params.get("start_range_km", 50))
    time_limit = params.get("time_limit_seconds")
    randomize = params.get("randomize_positions", True)
    rng = random.Random(params.get("seed"))

    ships: List[dict] = []
    player_ids: List[str] = []
    enemy_ids: List[str] = []

    # Player ships clustered near origin
    for idx, pdef in enumerate(player_defs):
        sid = f"player_{idx}" if idx > 0 else "player"
        cls = pdef.get("class", "corvette")
        ship = _build_ship(
            sid, pdef.get("name") or f"Player {cls.title()}", cls,
            pdef.get("faction", "unsa"),
            _cluster_pos(rng, 0, 0, 5000, randomize),
            player_controlled=(idx == 0),
            facing={"x": range_km * 1000, "y": 0, "z": 0},
        )
        ships.append(ship)
        player_ids.append(sid)

    # Enemy ships at range, random bearings
    eidx = 0
    for edef in enemy_defs:
        count = int(edef.get("count", 1))
        cls = edef.get("class", "frigate")
        faction = edef.get("faction", "pirates")
        for _ in range(count):
            bearing = rng.uniform(0, 2 * math.pi)
            r = range_km * 1000 * (rng.uniform(0.8, 1.2) if randomize else 1.0)
            cx, cy = r * math.cos(bearing), r * math.sin(bearing)
            ai_role = _classify_ai_role(cls)
            ai = {"behavior": _AI_PRESETS[ai_role]["behavior"],
                  "params": dict(_AI_PRESETS[ai_role]["params"])}
            ship = _build_ship(
                f"enemy_{eidx}",
                edef.get("name") or f"Hostile {cls.title()} {eidx + 1}",
                cls, faction, _cluster_pos(rng, cx, cy, 3000, randomize),
                ai=ai, facing={"x": 0, "y": 0, "z": 0},
            )
            ships.append(ship)
            enemy_ids.append(f"enemy_{eidx}")
            eidx += 1

    # Mode-specific assets
    asset_id = None
    if mode == "defend":
        asset_id = "defended_asset"
        ships.append(_build_ship(
            asset_id, "Station Alpha", "station", "unsa",
            {"x": 0, "y": 0, "z": 0},
        ))
    elif mode == "escort":
        asset_id = "escort_freighter"
        ai = {"behavior": "evade", "params": {"flee_threshold": 0.9}}
        ships.append(_build_ship(
            asset_id, "MV Fortunate Son", "freighter", "unsa",
            _cluster_pos(rng, 0, 0, 2000, randomize), ai=ai,
        ))

    objectives = _build_objectives(mode, player_ids, enemy_ids, asset_id, time_limit)
    label = {"deathmatch": "Deathmatch", "team": "Team Battle",
             "defend": "Defense", "escort": "Escort"}.get(mode, mode.title())
    name = f"Skirmish: {label}"

    scenario = {
        "name": name,
        "description": f"Quick-play {mode} skirmish -- {len(player_ids)} vs {len(enemy_ids)}",
        "dt": 0.1,
        "ships": ships,
        "mission": {
            "name": name,
            "description": f"{mode.title()} skirmish engagement",
            "briefing": _briefing(mode, len(player_ids), len(enemy_ids), range_km),
            "objectives": objectives,
            "time_limit": time_limit,
            "success_message": "Skirmish won! All objectives completed.",
            "failure_message": "Skirmish lost.",
            "hints": [],
        },
        "config": {},
        "fleets": [],
    }
    logger.info(f"Generated skirmish: mode={mode}, {len(player_ids)}v{len(enemy_ids)}, {range_km}km")
    return scenario


# ── Internal helpers ─────────────────────────────────────────────────

def _build_ship(
    ship_id: str, name: str, ship_class: str, faction: str,
    position: dict, velocity: dict = None, player_controlled: bool = False,
    ai: Optional[dict] = None, facing: Optional[dict] = None,
) -> dict:
    """Build a ship definition dict with ship_class for registry resolution."""
    vel = velocity or {"x": 0, "y": 0, "z": 0}
    d = _CLASS_DEFAULTS.get(ship_class, _CLASS_DEFAULTS["corvette"])

    yaw = 0.0
    if facing:
        dx = facing["x"] - position["x"]
        dy = facing["y"] - position["y"]
        if abs(dx) > 0.1 or abs(dy) > 0.1:
            yaw = math.degrees(math.atan2(dy, dx))

    ship = {
        "id": ship_id, "name": name, "ship_class": ship_class,
        "class": ship_class, "faction": faction,
        "player_controlled": player_controlled,
        "position": position, "velocity": vel,
        "orientation": {"pitch": 0, "yaw": yaw, "roll": 0},
        "mass": d["mass"], "ai_enabled": not player_controlled,
        "systems": {
            "propulsion": {"max_thrust": d["thrust"], "fuel_level": d["fuel"], "max_fuel": d["fuel"]},
            "sensors": {"passive": {"range": 200000}, "active": {"scan_range": 500000}},
            "navigation": {},
            "targeting": {"lock_range": 500000.0},
            "combat": {"railguns": 1, "pdcs": 2},
        },
    }
    if ai:
        ship["ai"] = ai
    return ship


def _cluster_pos(rng: random.Random, cx: float, cy: float,
                 spread: float, randomize: bool) -> dict:
    """Position clustered around (cx, cy) with optional jitter."""
    if randomize:
        return {"x": round(cx + rng.uniform(-spread, spread), 1),
                "y": round(cy + rng.uniform(-spread, spread), 1),
                "z": round(rng.uniform(-spread * 0.3, spread * 0.3), 1)}
    return {"x": cx, "y": cy, "z": 0.0}


def _classify_ai_role(ship_class: str) -> str:
    if ship_class in ("freighter", "science_vessel"):
        return "freighter"
    if ship_class in ("destroyer", "cruiser", "battleship", "carrier"):
        return "capital"
    return "combat"


def _obj(oid: str, otype: str, desc: str, required: bool, **params) -> dict:
    """Shorthand for building an objective dict."""
    return {"id": oid, "type": otype, "description": desc,
            "required": required, "params": params}


def _build_objectives(
    mode: str, player_ids: List[str], enemy_ids: List[str],
    asset_id: Optional[str], time_limit: Optional[float],
) -> List[dict]:
    """Build objective list for the given mode."""
    objs: List[dict] = []

    if mode in ("deathmatch", "team"):
        for eid in enemy_ids:
            objs.append(_obj(f"destroy_{eid}", "destroy_target", f"Destroy {eid}", True, target=eid))
        objs.append(_obj("player_survive", "avoid_mission_kill",
                         "Keep your ship operational", True, target=player_ids[0]))

    elif mode == "defend":
        for eid in enemy_ids:
            objs.append(_obj(f"destroy_{eid}", "destroy_target", f"Destroy {eid}", True, target=eid))
        if asset_id:
            objs.append(_obj("protect_asset", "protect_ship",
                             "Protect the station", True, target=asset_id, time=time_limit or 300))

    elif mode == "escort":
        if asset_id:
            objs.append(_obj("protect_freighter", "protect_ship",
                             "Keep the freighter alive", True, target=asset_id, time=time_limit or 600))
            objs.append(_obj("reach_destination", "reach_range",
                             "Escort freighter to destination", True, target=asset_id, range=5000))
        for eid in enemy_ids:
            objs.append(_obj(f"destroy_{eid}", "destroy_target", f"Destroy {eid}", False, target=eid))

    return objs


def _briefing(mode: str, n_friendly: int, n_hostile: int, range_km: float) -> str:
    descs = {
        "deathmatch": "Destroy all enemy ships. Last team standing wins.",
        "team": "Team engagement. Eliminate all hostile ships.",
        "defend": "Defend Station Alpha from incoming hostiles.\nThe station cannot move.",
        "escort": "Escort the freighter to the destination waypoint.\nProtect it en route.",
    }
    return (f"SKIRMISH BRIEFING -- {mode.upper()}\n\n"
            f"Engagement range: {range_km:.0f} km\n"
            f"Friendly ships: {n_friendly}\n"
            f"Hostile contacts: {n_hostile}\n\n"
            f"{descs.get(mode, '')}\n\nGood hunting.")
