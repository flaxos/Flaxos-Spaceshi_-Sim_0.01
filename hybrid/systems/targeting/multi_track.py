# hybrid/systems/targeting/multi_track.py
"""Multi-target simultaneous tracking manager.

Extends the targeting pipeline to maintain locks on multiple contacts.
Each lock consumes sensor processing bandwidth, and track quality degrades
when splitting attention across more targets.

Design rationale:
- Max simultaneous locks depends on sensor subsystem health (damaged sensors
  can track fewer targets)
- Each additional track degrades quality on ALL tracks (bandwidth sharing)
- Primary target gets priority bandwidth; secondary tracks are degraded more
- PDC turrets can be individually assigned to different threats
- Split-fire allows engaging multiple targets with different weapon systems

The bandwidth model: sensor processing capacity is a finite resource.
A healthy sensor suite can maintain N tracks at full quality. Each additional
track beyond 1 applies a quality penalty to all tracks, simulating the
computational/bandwidth cost of splitting attention.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from hybrid.utils.errors import success_dict, error_dict

logger = logging.getLogger(__name__)


# Maximum track slots at 100% sensor health. Degrades linearly with damage.
BASE_MAX_TRACKS = 4

# Quality penalty per additional tracked target beyond the primary.
# With 2 targets: primary gets (1 - 0.10) = 90%, secondary gets 80%.
# With 3 targets: primary gets 80%, secondaries get 70%.
QUALITY_PENALTY_PER_TRACK = 0.10

# Secondary tracks get an additional penalty vs the primary target.
SECONDARY_QUALITY_PENALTY = 0.10


@dataclass
class TrackSlot:
    """A single target track maintained by the sensor system.

    Attributes:
        contact_id: Sensor contact identifier for this track.
        priority: Lower number = higher priority. 0 = primary target.
        quality_modifier: Bandwidth-sharing quality modifier (0-1).
        assigned_weapons: Weapon mount IDs assigned to this track.
    """
    contact_id: str
    priority: int = 0
    quality_modifier: float = 1.0
    assigned_weapons: Set[str] = field(default_factory=set)

    def to_dict(self) -> dict:
        """Serialize for telemetry."""
        return {
            "contact_id": self.contact_id,
            "priority": self.priority,
            "quality_modifier": round(self.quality_modifier, 3),
            "assigned_weapons": sorted(self.assigned_weapons),
        }


class MultiTrackManager:
    """Manages multiple simultaneous target tracks.

    Works alongside the existing TargetingSystem. The targeting system
    continues to manage the primary lock (lock state, firing solutions).
    This manager handles the secondary tracks, bandwidth sharing, and
    weapon-to-target assignments.
    """

    def __init__(self, base_max_tracks: int = BASE_MAX_TRACKS):
        """Initialize multi-track manager.

        Args:
            base_max_tracks: Maximum track slots at full sensor health.
        """
        self.base_max_tracks = base_max_tracks

        # Ordered list of tracked contacts. Index 0 = primary target.
        self.tracks: List[TrackSlot] = []

        # PDC-to-target assignments: mount_id -> contact_id
        self.pdc_assignments: Dict[str, str] = {}

        # Weapon-to-target split-fire assignments: mount_id -> contact_id
        self.split_fire_assignments: Dict[str, str] = {}

    @property
    def primary_target(self) -> Optional[str]:
        """Contact ID of the primary (highest priority) target."""
        if self.tracks:
            return self.tracks[0].contact_id
        return None

    @property
    def track_count(self) -> int:
        """Number of currently active tracks."""
        return len(self.tracks)

    def max_tracks(self, sensor_factor: float) -> int:
        """Calculate maximum simultaneous tracks based on sensor health.

        Sensor damage reduces available tracking bandwidth. At 50% sensor
        health, only half the base track slots are available.

        Args:
            sensor_factor: Sensor subsystem health factor (0-1).

        Returns:
            Maximum number of simultaneous tracks.
        """
        return max(1, int(self.base_max_tracks * sensor_factor))

    def get_quality_modifier(self, track_index: int) -> float:
        """Calculate quality modifier for a track based on bandwidth sharing.

        More targets = lower quality per track. Primary target gets
        preferential bandwidth.

        Args:
            track_index: Index in the track list (0 = primary).

        Returns:
            Quality modifier (0-1) to apply to track quality.
        """
        n = len(self.tracks)
        if n <= 1:
            return 1.0

        # Base penalty scales with number of extra tracks
        extra_tracks = n - 1
        base_penalty = extra_tracks * QUALITY_PENALTY_PER_TRACK

        # Primary target gets less penalty than secondaries
        if track_index == 0:
            return max(0.3, 1.0 - base_penalty)
        else:
            return max(0.2, 1.0 - base_penalty - SECONDARY_QUALITY_PENALTY)

    def update_quality_modifiers(self) -> None:
        """Recalculate quality modifiers for all tracks."""
        for i, track in enumerate(self.tracks):
            track.quality_modifier = self.get_quality_modifier(i)

    def add_track(self, contact_id: str, sensor_factor: float) -> dict:
        """Add a new target to the track list.

        Args:
            contact_id: Sensor contact ID to track.
            sensor_factor: Current sensor health factor.

        Returns:
            Success/error dict.
        """
        # Check if already tracking this contact
        for track in self.tracks:
            if track.contact_id == contact_id:
                return error_dict(
                    "ALREADY_TRACKING",
                    f"Contact '{contact_id}' is already in the track list"
                )

        max_t = self.max_tracks(sensor_factor)
        if len(self.tracks) >= max_t:
            return error_dict(
                "TRACK_LIST_FULL",
                f"Cannot track more than {max_t} contacts "
                f"(sensor health: {sensor_factor:.0%})",
                max_tracks=max_t,
                sensor_factor=sensor_factor,
            )

        priority = len(self.tracks)
        slot = TrackSlot(contact_id=contact_id, priority=priority)
        self.tracks.append(slot)
        self.update_quality_modifiers()

        logger.info(
            f"Added track: {contact_id} (priority {priority}, "
            f"{len(self.tracks)}/{max_t} tracks)"
        )

        return success_dict(
            f"Tracking {contact_id} (priority {priority})",
            contact_id=contact_id,
            priority=priority,
            track_count=len(self.tracks),
            max_tracks=max_t,
            quality_modifier=slot.quality_modifier,
        )

    def remove_track(self, contact_id: str) -> dict:
        """Remove a target from the track list.

        Args:
            contact_id: Contact ID to stop tracking.

        Returns:
            Success/error dict.
        """
        for i, track in enumerate(self.tracks):
            if track.contact_id == contact_id:
                self.tracks.pop(i)
                # Clean up assignments referencing this contact
                self.pdc_assignments = {
                    k: v for k, v in self.pdc_assignments.items()
                    if v != contact_id
                }
                self.split_fire_assignments = {
                    k: v for k, v in self.split_fire_assignments.items()
                    if v != contact_id
                }
                # Re-index priorities
                for j, t in enumerate(self.tracks):
                    t.priority = j
                self.update_quality_modifiers()

                logger.info(f"Removed track: {contact_id}")
                return success_dict(
                    f"Stopped tracking {contact_id}",
                    contact_id=contact_id,
                    track_count=len(self.tracks),
                )

        return error_dict(
            "NOT_TRACKING",
            f"Contact '{contact_id}' is not in the track list"
        )

    def cycle_primary(self) -> dict:
        """Cycle the primary target to the next contact in the track list.

        Moves the current primary to the back and promotes the next
        track to primary. This is the tactical officer's quick-switch
        for engaging multiple threats in sequence.

        Returns:
            Success/error dict with new primary target info.
        """
        if len(self.tracks) < 2:
            return error_dict(
                "INSUFFICIENT_TRACKS",
                "Need at least 2 tracked targets to cycle"
            )

        # Rotate: move first element to end
        old_primary = self.tracks.pop(0)
        self.tracks.append(old_primary)

        # Re-index priorities
        for i, track in enumerate(self.tracks):
            track.priority = i
        self.update_quality_modifiers()

        new_primary = self.tracks[0].contact_id
        logger.info(
            f"Cycled primary target: {old_primary.contact_id} -> {new_primary}"
        )

        return success_dict(
            f"Primary target: {new_primary}",
            previous_primary=old_primary.contact_id,
            new_primary=new_primary,
            track_list=[t.to_dict() for t in self.tracks],
        )

    def assign_pdc_target(
        self, mount_id: str, contact_id: str, available_pdcs: List[str]
    ) -> dict:
        """Assign a specific PDC turret to a tracked contact.

        PDCs can be individually directed at different threats. This is
        how you handle multiple incoming torpedoes or missiles -- spread
        your point defense across the threat axis.

        Args:
            mount_id: PDC mount identifier (e.g. "pdc_1").
            contact_id: Contact to assign the PDC to.
            available_pdcs: List of valid PDC mount IDs on this ship.

        Returns:
            Success/error dict.
        """
        if mount_id not in available_pdcs:
            return error_dict(
                "INVALID_PDC",
                f"Mount '{mount_id}' is not a valid PDC "
                f"(available: {', '.join(available_pdcs)})"
            )

        # Verify contact is in track list
        tracked_ids = {t.contact_id for t in self.tracks}
        if contact_id not in tracked_ids:
            return error_dict(
                "NOT_TRACKING",
                f"Contact '{contact_id}' must be in the track list first"
            )

        self.pdc_assignments[mount_id] = contact_id

        # Also update the track slot's assigned weapons
        for track in self.tracks:
            # Remove this mount from any other track
            track.assigned_weapons.discard(mount_id)
            if track.contact_id == contact_id:
                track.assigned_weapons.add(mount_id)

        logger.info(f"Assigned {mount_id} -> {contact_id}")

        return success_dict(
            f"{mount_id} assigned to {contact_id}",
            mount_id=mount_id,
            contact_id=contact_id,
            all_pdc_assignments=dict(self.pdc_assignments),
        )

    def assign_split_fire(
        self, mount_id: str, contact_id: str, available_weapons: List[str]
    ) -> dict:
        """Assign a weapon to engage a specific tracked target (split-fire).

        Split-fire lets you engage multiple targets simultaneously with
        different weapon systems. For example, railgun on the primary
        while PDCs suppress a secondary threat.

        Args:
            mount_id: Weapon mount identifier.
            contact_id: Contact to assign this weapon to.
            available_weapons: List of valid weapon mount IDs.

        Returns:
            Success/error dict.
        """
        if mount_id not in available_weapons:
            return error_dict(
                "INVALID_WEAPON",
                f"Mount '{mount_id}' not found "
                f"(available: {', '.join(available_weapons)})"
            )

        tracked_ids = {t.contact_id for t in self.tracks}
        if contact_id not in tracked_ids:
            return error_dict(
                "NOT_TRACKING",
                f"Contact '{contact_id}' must be in the track list first"
            )

        self.split_fire_assignments[mount_id] = contact_id

        # Update track slot weapon sets
        for track in self.tracks:
            track.assigned_weapons.discard(mount_id)
            if track.contact_id == contact_id:
                track.assigned_weapons.add(mount_id)

        logger.info(f"Split-fire: {mount_id} -> {contact_id}")

        return success_dict(
            f"{mount_id} assigned to engage {contact_id}",
            mount_id=mount_id,
            contact_id=contact_id,
            all_assignments=dict(self.split_fire_assignments),
        )

    def clear_assignments(self) -> dict:
        """Clear all weapon-to-target assignments.

        Returns all weapons to default behavior (engage primary target).

        Returns:
            Success dict.
        """
        self.pdc_assignments.clear()
        self.split_fire_assignments.clear()
        for track in self.tracks:
            track.assigned_weapons.clear()

        logger.info("Cleared all weapon assignments")
        return success_dict("All weapon assignments cleared")

    def clear_all(self) -> None:
        """Clear all tracks and assignments. Used on full target reset."""
        self.tracks.clear()
        self.pdc_assignments.clear()
        self.split_fire_assignments.clear()

    def get_weapon_target(self, mount_id: str) -> Optional[str]:
        """Get the target contact ID for a weapon mount.

        Checks split-fire assignments first, then PDC assignments,
        then falls back to primary target.

        Args:
            mount_id: Weapon mount identifier.

        Returns:
            Contact ID this weapon should engage, or None.
        """
        # Explicit split-fire assignment takes priority
        if mount_id in self.split_fire_assignments:
            return self.split_fire_assignments[mount_id]

        # PDC-specific assignment
        if mount_id in self.pdc_assignments:
            return self.pdc_assignments[mount_id]

        # Default: primary target
        return self.primary_target

    def prune_lost_contacts(self, valid_contact_ids: Set[str]) -> List[str]:
        """Remove tracks for contacts that are no longer detected.

        Called during tick to keep the track list in sync with sensors.

        Args:
            valid_contact_ids: Set of currently valid contact IDs.

        Returns:
            List of contact IDs that were pruned.
        """
        kept = []
        pruned = []
        for track in self.tracks:
            if track.contact_id in valid_contact_ids:
                kept.append(track)
            else:
                pruned.append(track.contact_id)

        if pruned:
            self.tracks = kept
            # Clean up assignments
            for contact_id in pruned:
                self.pdc_assignments = {
                    k: v for k, v in self.pdc_assignments.items()
                    if v != contact_id
                }
                self.split_fire_assignments = {
                    k: v for k, v in self.split_fire_assignments.items()
                    if v != contact_id
                }
            # Re-index
            for i, track in enumerate(self.tracks):
                track.priority = i
            self.update_quality_modifiers()

            logger.info(f"Pruned lost contacts from track list: {pruned}")

        return pruned

    def get_state(self) -> dict:
        """Get serializable state for telemetry.

        Returns:
            Dict with track list, assignments, and bandwidth info.
        """
        return {
            "track_count": len(self.tracks),
            "base_max_tracks": self.base_max_tracks,
            "tracks": [t.to_dict() for t in self.tracks],
            "primary_target": self.primary_target,
            "pdc_assignments": dict(self.pdc_assignments),
            "split_fire_assignments": dict(self.split_fire_assignments),
        }
