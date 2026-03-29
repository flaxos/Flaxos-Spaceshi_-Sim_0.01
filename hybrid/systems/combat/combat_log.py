# hybrid/systems/combat/combat_log.py
"""Combat feedback log with causal chain tracking.

Records every combat event with full cause-to-effect chains so the player
understands WHY things happen. Each entry links cause to effect:

  'Railgun fired -> slug travel time 18.3s -> target maneuvered 1.2g ->
   slug passed 340m behind target -> miss.'

This is the primary tool for player learning.
"""

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from hybrid.core.event_bus import EventBus


@dataclass
class CombatLogEntry:
    """A single combat log entry with causal chain."""
    id: int
    sim_time: float
    timestamp: float
    event_type: str        # weapon_fired, hit, miss, damage, cascade, reload
    ship_id: Optional[str]
    target_id: Optional[str]
    summary: str           # Human-readable one-liner
    chain: List[str]       # Ordered causal chain steps
    details: Dict[str, Any] = field(default_factory=dict)
    weapon: Optional[str] = None
    severity: str = "info"  # info, hit, miss, damage, critical

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for telemetry transport."""
        return {
            "id": self.id,
            "sim_time": round(self.sim_time, 2),
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "ship_id": self.ship_id,
            "target_id": self.target_id,
            "summary": self.summary,
            "chain": self.chain,
            "details": self.details,
            "weapon": self.weapon,
            "severity": self.severity,
        }


class CombatLog:
    """Persistent combat event log with causal chain construction.

    Subscribes to EventBus combat events and builds narrative entries
    that explain the full cause-to-effect chain for each engagement.
    """

    def __init__(self, maxlen: int = 200):
        self._entries: deque = deque(maxlen=maxlen)
        self._next_id = 1
        self._event_bus = EventBus.get_instance()
        self._subscribe()

    def _subscribe(self):
        """Subscribe to combat-relevant events."""
        self._event_bus.subscribe("weapon_fired", self._on_weapon_fired)
        self._event_bus.subscribe("weapon_reloading", self._on_weapon_reloading)
        self._event_bus.subscribe("weapon_reloaded", self._on_weapon_reloaded)
        self._event_bus.subscribe("subsystem_damaged", self._on_subsystem_damaged)
        self._event_bus.subscribe("cascade_effect", self._on_cascade_effect)
        self._event_bus.subscribe("cascade_cleared", self._on_cascade_cleared)
        self._event_bus.subscribe("target_locked", self._on_target_locked)
        self._event_bus.subscribe("target_lost", self._on_target_lost)
        # Torpedo lifecycle events
        self._event_bus.subscribe("torpedo_launched", self._on_torpedo_launched)
        self._event_bus.subscribe("torpedo_detonation", self._on_torpedo_detonation)
        self._event_bus.subscribe("torpedo_expired", self._on_torpedo_expired)
        self._event_bus.subscribe("torpedo_intercepted", self._on_torpedo_intercepted)

    def _add_entry(self, entry: CombatLogEntry):
        """Add entry and assign an ID."""
        entry.id = self._next_id
        self._next_id += 1
        self._entries.append(entry)

    def get_entries(self, limit: int = 50, since_id: int = 0,
                    event_type: str = None, weapon: str = None,
                    target: str = None) -> List[Dict[str, Any]]:
        """Get combat log entries with optional filtering.

        Args:
            limit: Max entries to return
            since_id: Only return entries with id > since_id
            event_type: Filter by event type
            weapon: Filter by weapon name
            target: Filter by target ship ID

        Returns:
            List of serialized combat log entries
        """
        result = []
        for entry in reversed(self._entries):
            if entry.id <= since_id:
                break
            if event_type:
                # Support prefix matching for grouped event types
                # (e.g. "torpedo" matches torpedo_launch, torpedo_hit, torpedo_miss)
                if not entry.event_type.startswith(event_type) and entry.event_type != event_type:
                    continue
            if weapon and entry.weapon != weapon:
                continue
            if target and entry.target_id != target:
                continue
            result.append(entry.to_dict())
            if len(result) >= limit:
                break
        result.reverse()
        return result

    def get_latest_id(self) -> int:
        """Get the ID of the most recent entry."""
        if self._entries:
            return self._entries[-1].id
        return 0

    # ── Event Handlers ──────────────────────────────────────

    def _on_weapon_fired(self, payload: dict):
        """Handle weapon_fired event — the core combat narrative."""
        weapon_name = payload.get("weapon", "Unknown weapon")
        ship_id = payload.get("ship_id")
        target_id = payload.get("target", "unknown")
        hit = payload.get("hit", False)
        hit_prob = payload.get("hit_probability", 0.0)
        rng = payload.get("range", 0.0)
        damage = payload.get("damage", 0.0)
        damage_result = payload.get("damage_result") or {}
        sim_time = payload.get("sim_time", 0.0)

        # Format range for readability
        range_str = _format_range(rng)

        # Calculate time of flight from range and weapon
        tof = _estimate_tof(weapon_name, rng)
        tof_str = f"{tof:.1f}s" if tof > 0 else "instant"

        # Build causal chain
        chain = []
        chain.append(f"{weapon_name} fired at {target_id}")
        chain.append(f"Range: {range_str}")

        if tof > 0.5:
            chain.append(f"Slug travel time: {tof_str}")

        chain.append(f"Hit probability: {hit_prob * 100:.0f}%")

        if hit:
            chain.append(f"Impact confirmed")
            if damage > 0:
                chain.append(f"Hull damage: {damage:.1f}")

            subsystem_hit = damage_result.get("subsystem_hit")
            subsystem_dmg = damage_result.get("subsystem_damage", 0)
            if subsystem_hit:
                chain.append(f"Subsystem hit: {subsystem_hit} ({subsystem_dmg:.1f} damage)")

            severity = "hit"
            summary = (
                f"{weapon_name} hit {target_id} at {range_str} "
                f"({hit_prob * 100:.0f}% prob) - {damage:.1f} damage"
            )
            if subsystem_hit:
                summary += f" [{subsystem_hit}]"
        else:
            chain.append("No impact - miss")
            if hit_prob < 0.3:
                chain.append(f"Low hit probability ({hit_prob * 100:.0f}%) at this range")
            elif hit_prob > 0.7:
                chain.append(f"Unlucky miss despite {hit_prob * 100:.0f}% probability")

            severity = "miss"
            summary = (
                f"{weapon_name} missed {target_id} at {range_str} "
                f"({hit_prob * 100:.0f}% prob, ToF {tof_str})"
            )

        self._add_entry(CombatLogEntry(
            id=0,
            sim_time=sim_time,
            timestamp=time.time(),
            event_type="hit" if hit else "miss",
            ship_id=ship_id,
            target_id=target_id,
            summary=summary,
            chain=chain,
            details={
                "hit": hit,
                "hit_probability": hit_prob,
                "range": rng,
                "damage": damage,
                "time_of_flight": tof,
                "subsystem_hit": damage_result.get("subsystem_hit"),
                "subsystem_damage": damage_result.get("subsystem_damage", 0),
            },
            weapon=weapon_name,
            severity=severity,
        ))

    def _on_weapon_reloading(self, payload: dict):
        """Handle magazine reload start."""
        weapon_name = payload.get("weapon", "Unknown")
        mount_id = payload.get("mount_id", "")
        reload_time = payload.get("reload_time", 0)
        ship_id = payload.get("ship_id")

        summary = f"{weapon_name} reloading ({reload_time:.1f}s)"
        chain = [
            f"{weapon_name} ({mount_id}) magazine depleted",
            f"Reload initiated: {reload_time:.1f}s",
            "Weapon offline during reload",
        ]

        self._add_entry(CombatLogEntry(
            id=0,
            sim_time=0.0,
            timestamp=time.time(),
            event_type="reload",
            ship_id=ship_id,
            target_id=None,
            summary=summary,
            chain=chain,
            weapon=weapon_name,
            severity="info",
        ))

    def _on_weapon_reloaded(self, payload: dict):
        """Handle magazine reload complete."""
        weapon_name = payload.get("weapon", "Unknown")
        mount_id = payload.get("mount_id", "")
        ship_id = payload.get("ship_id")

        summary = f"{weapon_name} reload complete - weapon ready"
        chain = [
            f"{weapon_name} ({mount_id}) magazine loaded",
            "Weapon back online",
        ]

        self._add_entry(CombatLogEntry(
            id=0,
            sim_time=0.0,
            timestamp=time.time(),
            event_type="reload",
            ship_id=ship_id,
            target_id=None,
            summary=summary,
            chain=chain,
            weapon=weapon_name,
            severity="info",
        ))

    def _on_subsystem_damaged(self, payload: dict):
        """Handle subsystem damage event."""
        subsystem = payload.get("subsystem", "unknown")
        health = payload.get("health", 0)
        status = payload.get("status", "unknown")
        ship_id = payload.get("ship_id")
        source = payload.get("source", "unknown")

        severity = "critical" if status in ("destroyed", "offline") else "damage"

        status_label = {
            "online": "ONLINE",
            "impaired": "IMPAIRED",
            "damaged": "DAMAGED",
            "offline": "OFFLINE",
            "destroyed": "DESTROYED",
        }.get(status, status.upper())

        chain = [
            f"Subsystem: {subsystem}",
            f"Source: {source}",
            f"Health: {health:.0f}%",
            f"Status: {status_label}",
        ]

        if status in ("destroyed", "offline"):
            chain.append(f"WARNING: {subsystem} is {status_label}")

        summary = f"{subsystem} {status_label} ({health:.0f}%) - hit by {source}"

        self._add_entry(CombatLogEntry(
            id=0,
            sim_time=0.0,
            timestamp=time.time(),
            event_type="damage",
            ship_id=ship_id,
            target_id=None,
            summary=summary,
            chain=chain,
            details={"subsystem": subsystem, "health": health, "status": status},
            severity=severity,
        ))

    def _on_cascade_effect(self, payload: dict):
        """Handle cascade damage effect."""
        source = payload.get("source", "unknown")
        dependent = payload.get("dependent", "unknown")
        penalty = payload.get("penalty", 0.0)
        reason = payload.get("reason", "")
        ship_id = payload.get("ship_id")
        description = payload.get("description", "")

        chain = [
            f"Cascade: {source} failure",
            f"Affected: {dependent}",
            f"Penalty: {(1.0 - penalty) * 100:.0f}% degradation",
        ]
        if description:
            chain.append(description)

        summary = (
            f"CASCADE: {source} -> {dependent} "
            f"({(1.0 - penalty) * 100:.0f}% degraded)"
        )

        self._add_entry(CombatLogEntry(
            id=0,
            sim_time=0.0,
            timestamp=time.time(),
            event_type="cascade",
            ship_id=ship_id,
            target_id=None,
            summary=summary,
            chain=chain,
            details={"source": source, "dependent": dependent, "penalty": penalty},
            severity="critical",
        ))

    def _on_cascade_cleared(self, payload: dict):
        """Handle cascade effect cleared."""
        source = payload.get("source", "unknown")
        dependent = payload.get("dependent", "unknown")
        ship_id = payload.get("ship_id")

        summary = f"Cascade cleared: {source} -> {dependent} restored"
        chain = [
            f"Cascade cleared: {source} restored",
            f"{dependent} back to nominal",
        ]

        self._add_entry(CombatLogEntry(
            id=0,
            sim_time=0.0,
            timestamp=time.time(),
            event_type="cascade_cleared",
            ship_id=ship_id,
            target_id=None,
            summary=summary,
            chain=chain,
            severity="info",
        ))

    def _on_target_locked(self, payload: dict):
        """Handle target lock acquired."""
        ship_id = payload.get("ship_id")
        target_id = payload.get("target_id", "unknown")
        rng = payload.get("range", 0.0)
        range_str = _format_range(rng)

        summary = f"Target lock acquired: {target_id} at {range_str}"
        chain = [
            f"Targeting: lock acquired on {target_id}",
            f"Range: {range_str}",
            "Weapons can now engage",
        ]

        self._add_entry(CombatLogEntry(
            id=0,
            sim_time=0.0,
            timestamp=time.time(),
            event_type="lock",
            ship_id=ship_id,
            target_id=target_id,
            summary=summary,
            chain=chain,
            severity="info",
        ))

    def _on_target_lost(self, payload: dict):
        """Handle target lock lost."""
        ship_id = payload.get("ship_id")
        target_id = payload.get("target_id", "unknown")
        reason = payload.get("reason", "unknown")

        summary = f"Target lock lost: {target_id} ({reason})"
        chain = [
            f"Targeting: lock lost on {target_id}",
            f"Reason: {reason}",
            "Weapons cannot engage",
        ]

        self._add_entry(CombatLogEntry(
            id=0,
            sim_time=0.0,
            timestamp=time.time(),
            event_type="lock_lost",
            ship_id=ship_id,
            target_id=target_id,
            summary=summary,
            chain=chain,
            severity="info",
        ))

    # ── Torpedo Event Handlers ─────────────────────────────────

    def _on_torpedo_launched(self, payload: dict):
        """Handle torpedo launch event."""
        torpedo_id = payload.get("torpedo_id", "unknown")
        shooter = payload.get("shooter", "unknown")
        target = payload.get("target", "unknown")
        profile = payload.get("profile", "direct")

        summary = f"Torpedo launched at {target} ({profile})"
        chain = [
            f"Torpedo {torpedo_id} launched",
            f"Shooter: {shooter}",
            f"Target: {target}",
            f"Profile: {profile}",
            "Torpedo drive ignited — tracking target",
        ]

        self._add_entry(CombatLogEntry(
            id=0,
            sim_time=0.0,
            timestamp=time.time(),
            event_type="torpedo_launch",
            ship_id=shooter,
            target_id=target,
            summary=summary,
            chain=chain,
            details={
                "torpedo_id": torpedo_id,
                "profile": profile,
            },
            weapon="Torpedo",
            severity="info",
        ))

    def _on_torpedo_detonation(self, payload: dict):
        """Handle torpedo detonation/impact event."""
        torpedo_id = payload.get("torpedo_id", "unknown")
        shooter = payload.get("shooter", "unknown")
        target = payload.get("target", "unknown")
        impact_distance = payload.get("impact_distance", 0.0)
        flight_time = payload.get("flight_time", 0.0)
        damage_results = payload.get("damage_results", [])
        feedback = payload.get("feedback", "")

        # Use the pre-built feedback string if available, otherwise construct
        summary = feedback or f"Torpedo impact on {target} at {impact_distance:.0f}m"

        # Build detailed causal chain
        chain = [
            f"Torpedo {torpedo_id} detonated",
            f"Target: {target}",
            f"Impact distance: {impact_distance:.0f}m",
            f"Flight time: {flight_time:.1f}s",
        ]

        total_hull_dmg = 0.0
        subsystems_hit = []
        for result in damage_results:
            ship_hit = result.get("ship_id", "unknown")
            hull_dmg = result.get("hull_damage", 0)
            total_hull_dmg += hull_dmg
            if hull_dmg > 0:
                chain.append(f"Hull damage to {ship_hit}: {hull_dmg:.1f}")
            for sub in result.get("subsystems_hit", []):
                name = sub.get("subsystem", "unknown")
                dmg = sub.get("damage", 0)
                subsystems_hit.append(name)
                chain.append(f"Subsystem hit: {name} ({dmg:.1f} damage)")

        if not damage_results:
            chain.append("No ships in blast radius")

        severity = "hit" if total_hull_dmg > 0 else "miss"
        if subsystems_hit:
            severity = "damage"

        self._add_entry(CombatLogEntry(
            id=0,
            sim_time=0.0,
            timestamp=time.time(),
            event_type="torpedo_hit",
            ship_id=shooter,
            target_id=target,
            summary=summary,
            chain=chain,
            details={
                "torpedo_id": torpedo_id,
                "impact_distance": impact_distance,
                "flight_time": flight_time,
                "hull_damage": total_hull_dmg,
                "subsystems_hit": subsystems_hit,
            },
            weapon="Torpedo",
            severity=severity,
        ))

    def _on_torpedo_expired(self, payload: dict):
        """Handle torpedo expiry (fuel exhausted or lifetime exceeded)."""
        torpedo_id = payload.get("torpedo_id", "unknown")
        shooter = payload.get("shooter", "unknown")
        target = payload.get("target", "unknown")
        flight_time = payload.get("flight_time", 0.0)
        reason = payload.get("reason", "lifetime_exceeded")

        reason_label = {
            "fuel_exhausted_past_target": "fuel exhausted past target",
            "lifetime_exceeded": "guidance timeout",
        }.get(reason, reason)

        summary = f"Torpedo expired — {reason_label} (target: {target})"
        chain = [
            f"Torpedo {torpedo_id} lost",
            f"Target: {target}",
            f"Reason: {reason_label}",
            f"Flight time: {flight_time:.1f}s",
            "No impact — torpedo failed to reach target",
        ]

        self._add_entry(CombatLogEntry(
            id=0,
            sim_time=0.0,
            timestamp=time.time(),
            event_type="torpedo_miss",
            ship_id=shooter,
            target_id=target,
            summary=summary,
            chain=chain,
            details={
                "torpedo_id": torpedo_id,
                "flight_time": flight_time,
                "reason": reason,
            },
            weapon="Torpedo",
            severity="miss",
        ))

    def _on_torpedo_intercepted(self, payload: dict):
        """Handle torpedo interception by PDC fire."""
        torpedo_id = payload.get("torpedo_id", "unknown")
        shooter = payload.get("shooter", "unknown")
        target = payload.get("target", "unknown")
        intercepted_by = payload.get("intercepted_by", "PDC")

        summary = f"Torpedo intercepted by {intercepted_by} (target: {target})"
        chain = [
            f"Torpedo {torpedo_id} destroyed",
            f"Launched by: {shooter}",
            f"Targeting: {target}",
            f"Intercepted by: {intercepted_by}",
            "PDC point defense successful — torpedo neutralized",
        ]

        self._add_entry(CombatLogEntry(
            id=0,
            sim_time=0.0,
            timestamp=time.time(),
            event_type="torpedo_miss",
            ship_id=shooter,
            target_id=target,
            summary=summary,
            chain=chain,
            details={
                "torpedo_id": torpedo_id,
                "intercepted_by": intercepted_by,
            },
            weapon="Torpedo",
            severity="info",
        ))


# ── Helpers ─────────────────────────────────────────────────

def _format_range(range_m: float) -> str:
    """Format range in meters to human-readable string."""
    if range_m >= 1_000_000:
        return f"{range_m / 1_000:.0f}km"
    elif range_m >= 1_000:
        return f"{range_m / 1_000:.1f}km"
    else:
        return f"{range_m:.0f}m"


def _estimate_tof(weapon_name: str, range_m: float) -> float:
    """Estimate time of flight based on weapon type and range."""
    # Muzzle velocities from weapon specs
    if "railgun" in weapon_name.lower() or "une-440" in weapon_name.lower():
        muzzle_vel = 20_000.0  # 20 km/s
    elif "pdc" in weapon_name.lower() or "narwhal" in weapon_name.lower():
        muzzle_vel = 3_000.0   # 3 km/s
    else:
        muzzle_vel = 10_000.0  # generic

    if muzzle_vel <= 0:
        return 0.0
    return range_m / muzzle_vel


# ── Singleton ───────────────────────────────────────────────

_combat_log_instance: Optional[CombatLog] = None


def get_combat_log() -> CombatLog:
    """Get or create the singleton CombatLog instance."""
    global _combat_log_instance
    if _combat_log_instance is None:
        _combat_log_instance = CombatLog()
    return _combat_log_instance
