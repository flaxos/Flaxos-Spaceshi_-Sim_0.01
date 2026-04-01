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
        self._sim_time = 0.0
        self._event_bus = EventBus.get_instance()
        self._subscribe()

    def update_time(self, sim_time: float) -> None:
        """Update the current simulation time reference.

        Called each tick by the simulator so that event handlers
        can stamp entries with the correct sim_time without
        requiring every event publisher to include it.

        Args:
            sim_time: Current simulation time in seconds.
        """
        self._sim_time = sim_time

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
        # Railgun projectile lifecycle events (projectile_manager publishes these
        # separately from the instant-hit weapon_fired path used by PDCs)
        self._event_bus.subscribe("projectile_spawned", self._on_projectile_spawned)
        self._event_bus.subscribe("projectile_impact", self._on_projectile_impact)
        self._event_bus.subscribe("projectile_expired", self._on_projectile_expired)
        # Missile lifecycle events (separate from torpedo — lighter munitions)
        self._event_bus.subscribe("missile_launched", self._on_missile_launched)
        self._event_bus.subscribe("missile_detonation", self._on_missile_detonation)
        # PDC point-defense intercepts (simulator fires PDCs at incoming torpedoes)
        self._event_bus.subscribe("pdc_torpedo_engage", self._on_pdc_torpedo_engage)
        # Ship-level damage and destruction
        self._event_bus.subscribe("ship_damaged", self._on_ship_damaged)
        self._event_bus.subscribe("ship_destroyed", self._on_ship_destroyed)

    def _add_entry(self, entry: CombatLogEntry):
        """Add entry, assign an ID, and stamp current sim_time."""
        entry.id = self._next_id
        entry.sim_time = self._sim_time
        self._next_id += 1
        self._entries.append(entry)

    def get_entries(self, limit: int = 50, since_id: int = 0,
                    event_type: str = None, weapon: str = None,
                    target: str = None) -> List[Dict[str, Any]]:
        """Get combat log entries with optional filtering.

        Args:
            limit: Max entries to return
            since_id: Only return entries with id > since_id
            event_type: Filter by event type or comma-separated prefixes.
                Supports prefix matching so "torpedo" matches torpedo_launch,
                torpedo_hit, etc.  Multiple prefixes can be joined with commas
                (e.g. "hit,projectile_hit,torpedo_hit,missile_hit") so that
                cross-cutting category filters work correctly.
            weapon: Filter by weapon name
            target: Filter by target ship ID

        Returns:
            List of serialized combat log entries
        """
        # Pre-split comma-separated prefixes once for the loop
        type_prefixes: Optional[List[str]] = None
        if event_type:
            type_prefixes = [t.strip() for t in event_type.split(",") if t.strip()]

        result = []
        for entry in reversed(self._entries):
            if entry.id <= since_id:
                break
            if type_prefixes:
                # Match if entry.event_type starts with ANY of the prefixes
                if not any(entry.event_type.startswith(p) or entry.event_type == p
                           for p in type_prefixes):
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

    # ── Missile Event Handlers ──────────────────────────────────

    def _on_missile_launched(self, payload: dict):
        """Handle missile launch event."""
        torpedo_id = payload.get("torpedo_id", "unknown")
        shooter = payload.get("shooter", "unknown")
        target = payload.get("target", "unknown")
        profile = payload.get("profile", "direct")

        profile_labels = {
            "direct": "DIRECT",
            "evasive": "EVASIVE",
            "terminal_pop": "TERMINAL POP",
            "bracket": "BRACKET",
        }
        profile_label = profile_labels.get(profile, profile.upper())

        summary = f"Missile launched at {target} ({profile_label})"
        chain = [
            f"Missile {torpedo_id} launched",
            f"Shooter: {shooter}",
            f"Target: {target}",
            f"Flight profile: {profile_label}",
            "Missile motor ignited -- tracking target",
        ]

        self._add_entry(CombatLogEntry(
            id=0,
            sim_time=0.0,
            timestamp=time.time(),
            event_type="missile_launch",
            ship_id=shooter,
            target_id=target,
            summary=summary,
            chain=chain,
            details={
                "torpedo_id": torpedo_id,
                "profile": profile,
            },
            weapon="Missile",
            severity="info",
        ))

    def _on_missile_detonation(self, payload: dict):
        """Handle missile detonation/impact event."""
        torpedo_id = payload.get("torpedo_id", "unknown")
        shooter = payload.get("shooter", "unknown")
        target = payload.get("target", "unknown")
        impact_distance = payload.get("impact_distance", 0.0)
        flight_time = payload.get("flight_time", 0.0)
        damage_results = payload.get("damage_results", [])
        feedback = payload.get("feedback", "")

        summary = feedback or f"Missile impact on {target} at {impact_distance:.0f}m"

        chain = [
            f"Missile {torpedo_id} detonated",
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
            event_type="missile_hit" if total_hull_dmg > 0 or subsystems_hit else "missile_miss",
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
            weapon="Missile",
            severity=severity,
        ))

    # ── Projectile Event Handlers (Railgun slugs) ─────────────

    def _on_projectile_spawned(self, payload: dict):
        """Handle railgun projectile launch.

        projectile_manager publishes this when a slug leaves the barrel.
        The slug is now in-flight and unguided -- hit/miss is determined
        by the firing solution quality computed at launch time.
        """
        weapon_name = payload.get("weapon", "Unknown weapon")
        shooter = payload.get("shooter", "unknown")
        target = payload.get("target", "unknown")
        proj_id = payload.get("projectile_id", "unknown")

        summary = f"{weapon_name} fired at {target}"
        chain = [
            f"Projectile {proj_id} launched",
            f"Weapon: {weapon_name}",
            f"Shooter: {shooter}",
            f"Target: {target}",
            "Slug in flight -- unguided Newtonian trajectory",
        ]

        self._add_entry(CombatLogEntry(
            id=0,
            sim_time=0.0,
            timestamp=time.time(),
            event_type="projectile_fired",
            ship_id=shooter,
            target_id=target,
            summary=summary,
            chain=chain,
            details={"projectile_id": proj_id},
            weapon=weapon_name,
            severity="info",
        ))

    def _on_projectile_impact(self, payload: dict):
        """Handle railgun slug intercept (hit or near-miss).

        projectile_manager publishes this when a slug passes within
        hit_radius of a ship. The pre-rolled hit_probability from the
        firing solution determines whether it actually connects.
        The feedback string explains WHY it hit or missed.
        """
        weapon_name = payload.get("weapon", "Unknown weapon")
        shooter = payload.get("shooter", "unknown")
        target = payload.get("target", "unknown")
        proj_id = payload.get("projectile_id", "unknown")
        hit = payload.get("hit", False)
        damage = payload.get("damage", 0.0)
        subsystem_hit = payload.get("subsystem_hit")
        subsystem_damage = payload.get("subsystem_damage", 0.0)
        flight_time = payload.get("flight_time", 0.0)
        confidence = payload.get("confidence_at_fire", 0.0)
        feedback = payload.get("feedback", "")
        hit_loc = payload.get("hit_location") or {}
        armor_info = payload.get("armor_ablation") or {}

        chain = [
            f"Projectile {proj_id} intercepted target",
            f"Weapon: {weapon_name}",
            f"Flight time: {flight_time:.1f}s",
            f"Solution confidence at fire: {confidence:.0%}",
        ]

        if hit:
            chain.append("IMPACT CONFIRMED")
            if damage > 0:
                chain.append(f"Hull damage: {damage:.1f}")
            if subsystem_hit:
                chain.append(f"Subsystem hit: {subsystem_hit} ({subsystem_damage:.1f} damage)")
            # Hit-location physics details give the player insight into
            # WHY that subsystem was hit (angle, armor section, ricochet)
            if hit_loc.get("armor_section"):
                chain.append(f"Impact section: {hit_loc['armor_section']}")
                chain.append(f"Angle of incidence: {hit_loc.get('angle_of_incidence', 0):.1f} deg")
            if armor_info.get("description"):
                chain.append(f"Armor: {armor_info['description']}")
            severity = "hit"
            summary = feedback or (
                f"{weapon_name} hit {target} -- "
                f"{damage:.1f} damage"
                f"{f' [{subsystem_hit}]' if subsystem_hit else ''}"
            )
        else:
            chain.append("No impact -- miss")
            severity = "miss"
            summary = feedback or (
                f"{weapon_name} missed {target} "
                f"(confidence {confidence:.0%}, {flight_time:.1f}s flight)"
            )
            if hit_loc.get("is_ricochet"):
                chain.append("Slug ricocheted off armor")
                severity = "miss"

        self._add_entry(CombatLogEntry(
            id=0,
            sim_time=0.0,
            timestamp=time.time(),
            event_type="projectile_hit" if hit else "projectile_miss",
            ship_id=shooter,
            target_id=target,
            summary=summary,
            chain=chain,
            details={
                "projectile_id": proj_id,
                "hit": hit,
                "damage": damage,
                "subsystem_hit": subsystem_hit,
                "subsystem_damage": subsystem_damage,
                "flight_time": flight_time,
                "confidence_at_fire": confidence,
                "hit_location": hit_loc,
                "armor_ablation": armor_info,
            },
            weapon=weapon_name,
            severity=severity,
        ))

    def _on_projectile_expired(self, payload: dict):
        """Handle railgun slug expiry (flew past target or lifetime exceeded).

        This is the definitive miss case: the slug never came close enough
        to the target for an intercept check. Common at long range where
        even small errors in the firing solution grow over flight time.
        """
        weapon_name = payload.get("weapon", "Unknown weapon")
        shooter = payload.get("shooter", "unknown")
        target = payload.get("target", "unknown")
        proj_id = payload.get("projectile_id", "unknown")
        flight_time = payload.get("flight_time", 0.0)
        confidence = payload.get("confidence_at_fire", 0.0)
        feedback = payload.get("feedback", "")

        summary = feedback or (
            f"{weapon_name} slug expired after {flight_time:.1f}s -- "
            f"missed {target} (confidence {confidence:.0%})"
        )
        chain = [
            f"Projectile {proj_id} expired",
            f"Weapon: {weapon_name}",
            f"Target: {target}",
            f"Flight time: {flight_time:.1f}s",
            f"Solution confidence at fire: {confidence:.0%}",
            "Slug lifetime exceeded without intercept",
        ]

        self._add_entry(CombatLogEntry(
            id=0,
            sim_time=0.0,
            timestamp=time.time(),
            event_type="projectile_miss",
            ship_id=shooter,
            target_id=target,
            summary=summary,
            chain=chain,
            details={
                "projectile_id": proj_id,
                "flight_time": flight_time,
                "confidence_at_fire": confidence,
            },
            weapon=weapon_name,
            severity="miss",
        ))

    # ── PDC Point-Defense Intercept Handler ────────────────────

    def _on_pdc_torpedo_engage(self, payload: dict):
        """Handle PDC auto-engagement of incoming torpedoes.

        Each PDC fires a burst of rounds (burst_count per trigger pull).
        The payload includes per-burst stats: rounds_fired, burst_hits,
        and whether the torpedo was destroyed. This gives the player
        detailed feedback on point-defense effectiveness.
        """
        ship_id = payload.get("ship_id", "unknown")
        pdc_mount = payload.get("pdc_mount", "unknown")
        torpedo_id = payload.get("torpedo_id", "unknown")
        distance = payload.get("distance", 0.0)
        hit = payload.get("hit", False)
        destroyed = payload.get("destroyed", False)
        rounds_fired = payload.get("rounds_fired", 0)
        burst_hits = payload.get("burst_hits", 0)
        range_str = _format_range(distance)

        # Build a summary that shows burst-level detail and range:
        # "PDC (pdc_1): burst 10 rounds at torpedo T001 at 1.5km, 3 hits -- torpedo destroyed"
        if destroyed:
            summary = (
                f"PDC ({pdc_mount}): burst {rounds_fired} rounds at {torpedo_id} "
                f"at {range_str}, {burst_hits} hits -- torpedo destroyed"
            )
            severity = "hit"
        elif hit:
            summary = (
                f"PDC ({pdc_mount}): burst {rounds_fired} rounds at {torpedo_id} "
                f"at {range_str}, {burst_hits} hits -- torpedo damaged"
            )
            severity = "hit"
        else:
            summary = (
                f"PDC ({pdc_mount}): burst {rounds_fired} rounds at {torpedo_id} "
                f"at {range_str}, 0 hits -- torpedo survived"
            )
            severity = "miss"

        chain = [
            f"PDC mount: {pdc_mount}",
            f"Target: {torpedo_id}",
            f"Engagement range: {range_str}",
            f"Burst: {rounds_fired} rounds fired, {burst_hits} hits",
        ]
        if destroyed:
            chain.append("Torpedo DESTROYED -- threat neutralized")
        elif hit:
            chain.append("Torpedo damaged but still tracking")

        self._add_entry(CombatLogEntry(
            id=0,
            sim_time=0.0,
            timestamp=time.time(),
            event_type="pdc_intercept",
            ship_id=ship_id,
            target_id=torpedo_id,
            summary=summary,
            chain=chain,
            details={
                "pdc_mount": pdc_mount,
                "torpedo_id": torpedo_id,
                "distance": distance,
                "hit": hit,
                "destroyed": destroyed,
                "rounds_fired": rounds_fired,
                "burst_hits": burst_hits,
            },
            weapon="Narwhal-III PDC",
            severity=severity,
        ))

    # ── Ship Damage / Destruction Handlers ─────────────────────

    def _on_ship_damaged(self, payload: dict):
        """Handle ship taking damage from any source.

        ship.py publishes this whenever take_damage() is called. Provides
        the player with hull status updates and shows which subsystems
        were affected so they can prioritize repairs.
        """
        ship_id = payload.get("ship_id", "unknown")
        damage = payload.get("damage", 0.0)
        hull_before = payload.get("hull_before", 0.0)
        hull_after = payload.get("hull_after", 0.0)
        source = payload.get("source", "unknown")
        target_subsystem = payload.get("target_subsystem")
        subsystem_result = payload.get("subsystem_result") or {}

        # Calculate hull percentage from absolute values
        # (the payload doesn't include max_hull, so derive % from the change)
        hull_pct = hull_after / hull_before * 100 if hull_before > 0 else 0.0

        severity = "damage"
        if hull_after <= 0:
            severity = "critical"
        elif hull_pct < 25:
            severity = "critical"

        chain = [
            f"Ship: {ship_id}",
            f"Source: {source}",
            f"Damage taken: {damage:.1f}",
            f"Hull: {hull_before:.1f} -> {hull_after:.1f}",
        ]

        if target_subsystem:
            chain.append(f"Targeted subsystem: {target_subsystem}")
        if subsystem_result and subsystem_result.get("subsystem"):
            sub_name = subsystem_result.get("subsystem", "unknown")
            sub_status = subsystem_result.get("status", "unknown")
            chain.append(f"Subsystem affected: {sub_name} ({sub_status})")

        summary = (
            f"{ship_id} took {damage:.1f} damage from {source} "
            f"-- hull at {hull_after:.1f}"
        )

        self._add_entry(CombatLogEntry(
            id=0,
            sim_time=0.0,
            timestamp=time.time(),
            event_type="ship_damage",
            ship_id=ship_id,
            target_id=None,
            summary=summary,
            chain=chain,
            details={
                "damage": damage,
                "hull_before": hull_before,
                "hull_after": hull_after,
                "source": source,
                "target_subsystem": target_subsystem,
                "subsystem_result": subsystem_result,
            },
            severity=severity,
        ))

    def _on_ship_destroyed(self, payload: dict):
        """Handle ship destruction -- the kill confirmation.

        This is the most important combat log entry. When a ship is
        destroyed, the player needs unambiguous confirmation.
        """
        ship_id = payload.get("ship_id", "unknown")
        source = payload.get("source", "unknown")

        summary = f"TARGET DESTROYED: {ship_id}"
        chain = [
            f"Ship {ship_id} destroyed",
            f"Killing blow from: {source}",
            "Hull integrity: 0%",
            "All systems offline",
        ]

        self._add_entry(CombatLogEntry(
            id=0,
            sim_time=0.0,
            timestamp=time.time(),
            event_type="ship_destroyed",
            ship_id=ship_id,
            target_id=None,
            summary=summary,
            chain=chain,
            details={
                "source": source,
            },
            severity="critical",
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
