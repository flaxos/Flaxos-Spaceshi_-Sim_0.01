"""
Fleet Manager
Manages fleet coordination, formations, and fleet-level operations.
"""

import time
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
import numpy as np

from .formation import FleetFormation, FormationType, FormationPosition


class FleetStatus(Enum):
    """Fleet operational status"""
    FORMING = "forming"           # Fleet assembling into formation
    IN_FORMATION = "in_formation" # Fleet maintaining formation
    MANEUVERING = "maneuvering"   # Fleet executing maneuver
    ENGAGING = "engaging"         # Fleet in combat
    SCATTERED = "scattered"       # Fleet broken/disorganized
    DISBANDED = "disbanded"       # Fleet dissolved


class ThreatLevel(Enum):
    """Threat assessment levels"""
    NONE = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class FleetMessage:
    """Inter-ship message"""
    timestamp: float
    from_ship: str
    to_ship: Optional[str]  # None for broadcast
    message_type: str  # "command", "status", "contact", "target", "tactical"
    content: Dict
    priority: int = 1  # 1-5, 5 being highest


@dataclass
class FleetGroup:
    """A group/squadron of ships within a fleet"""
    group_id: str
    name: str
    flagship_id: str
    ship_ids: Set[str] = field(default_factory=set)
    formation_id: Optional[str] = None
    status: FleetStatus = FleetStatus.FORMING
    target_contact: Optional[str] = None
    assigned_sector: Optional[str] = None


@dataclass
class SharedContact:
    """Sensor contact shared across fleet via tactical data link"""
    contact_id: str
    reporting_ship: str
    timestamp: float
    position: np.ndarray
    velocity: np.ndarray
    classification: str
    confidence: float
    threat_level: ThreatLevel
    is_hostile: bool
    last_update: float


class FleetManager:
    """
    Manages fleet operations, formations, and coordination.
    Integrates with Simulator to provide fleet-level command and control.
    """

    def __init__(self, simulator=None):
        """
        Initialize fleet manager.

        Args:
            simulator: Reference to the main Simulator instance
        """
        self.simulator = simulator
        self.formation_manager = FleetFormation()

        # Fleet organization
        self.fleets: Dict[str, FleetGroup] = {}
        self.ship_to_fleet: Dict[str, str] = {}  # ship_id -> fleet_id

        # Fleet messaging
        self.message_queue: List[FleetMessage] = []
        self.message_history: List[FleetMessage] = []
        self.max_history = 1000

        # Tactical data link - shared sensor contacts
        self.shared_contacts: Dict[str, SharedContact] = {}  # contact_id -> SharedContact
        self.contact_timeout = 60.0  # Contacts expire after 60s

        # Fleet coordination
        self.fleet_targets: Dict[str, str] = {}  # fleet_id -> contact_id
        self.engagement_range = 50000.0  # 50km default engagement range

        # AI ship control
        self.ai_controlled_ships: Set[str] = set()

    def create_fleet(
        self,
        fleet_id: str,
        name: str,
        flagship_id: str,
        ship_ids: Optional[List[str]] = None
    ) -> bool:
        """
        Create a new fleet/squadron.

        Args:
            fleet_id: Unique identifier for the fleet
            name: Human-readable fleet name
            flagship_id: ID of the flagship
            ship_ids: List of ship IDs to add to fleet

        Returns:
            True if fleet created successfully
        """
        if fleet_id in self.fleets:
            return False

        # Verify ships exist in simulator
        if self.simulator:
            if flagship_id not in self.simulator.ships:
                return False
            if ship_ids:
                for ship_id in ship_ids:
                    if ship_id not in self.simulator.ships:
                        return False

        fleet = FleetGroup(
            group_id=fleet_id,
            name=name,
            flagship_id=flagship_id,
            ship_ids={flagship_id} if ship_ids is None else set(ship_ids + [flagship_id])
        )

        self.fleets[fleet_id] = fleet

        # Update ship-to-fleet mapping
        for ship_id in fleet.ship_ids:
            self.ship_to_fleet[ship_id] = fleet_id

        return True

    def add_ship_to_fleet(self, ship_id: str, fleet_id: str) -> bool:
        """Add a ship to an existing fleet."""
        if fleet_id not in self.fleets:
            return False

        if self.simulator and ship_id not in self.simulator.ships:
            return False

        # Remove from current fleet if assigned
        if ship_id in self.ship_to_fleet:
            old_fleet_id = self.ship_to_fleet[ship_id]
            if old_fleet_id in self.fleets:
                self.fleets[old_fleet_id].ship_ids.discard(ship_id)

        # Add to new fleet
        self.fleets[fleet_id].ship_ids.add(ship_id)
        self.ship_to_fleet[ship_id] = fleet_id

        return True

    def remove_ship_from_fleet(self, ship_id: str) -> bool:
        """Remove a ship from its fleet."""
        if ship_id not in self.ship_to_fleet:
            return False

        fleet_id = self.ship_to_fleet[ship_id]
        if fleet_id in self.fleets:
            self.fleets[fleet_id].ship_ids.discard(ship_id)

        del self.ship_to_fleet[ship_id]
        return True

    def form_fleet(
        self,
        fleet_id: str,
        formation_type: FormationType,
        spacing: float = 2000.0,
        **kwargs
    ) -> bool:
        """
        Put a fleet into formation.

        Args:
            fleet_id: ID of the fleet to form
            formation_type: Type of formation to use
            spacing: Distance between ships in meters
            **kwargs: Additional formation parameters

        Returns:
            True if formation initiated successfully
        """
        if fleet_id not in self.fleets:
            return False

        fleet = self.fleets[fleet_id]
        formation_id = f"{fleet_id}_formation"

        # Get flagship position and orientation
        flagship = self._get_ship(fleet.flagship_id)
        if not flagship:
            return False

        # Determine orientation from flagship velocity or heading
        orientation = self._get_ship_orientation(flagship)
        up_vector = np.array([0.0, 0.0, 1.0])

        # Create formation
        success = self.formation_manager.create_formation(
            formation_id=formation_id,
            formation_type=formation_type,
            flagship_id=fleet.flagship_id,
            spacing=spacing,
            orientation=orientation,
            up_vector=up_vector,
            **kwargs
        )

        if not success:
            return False

        # Assign all ships to formation
        for ship_id in fleet.ship_ids:
            self.formation_manager.assign_ship(ship_id, formation_id)

        fleet.formation_id = formation_id
        fleet.status = FleetStatus.FORMING

        # Send formation commands to all ships
        self._broadcast_to_fleet(fleet_id, "command", {
            "type": "form_up",
            "formation": formation_type.value,
            "spacing": spacing
        })

        return True

    def break_formation(self, fleet_id: str) -> bool:
        """Break fleet formation and return to free movement."""
        if fleet_id not in self.fleets:
            return False

        fleet = self.fleets[fleet_id]
        if fleet.formation_id:
            self.formation_manager.dissolve_formation(fleet.formation_id)
            fleet.formation_id = None

        fleet.status = FleetStatus.SCATTERED

        self._broadcast_to_fleet(fleet_id, "command", {
            "type": "break_formation"
        })

        return True

    def get_formation_positions(self, fleet_id: str) -> List[FormationPosition]:
        """Get calculated formation positions for all ships in fleet."""
        if fleet_id not in self.fleets:
            return []

        fleet = self.fleets[fleet_id]
        if not fleet.formation_id:
            return []

        flagship = self._get_ship(fleet.flagship_id)
        if not flagship:
            return []

        flagship_pos = np.array([flagship.x, flagship.y, flagship.z])
        flagship_vel = np.array([flagship.vx, flagship.vy, flagship.vz])

        return self.formation_manager.calculate_positions(
            fleet.formation_id,
            flagship_pos,
            flagship_vel
        )

    def set_fleet_target(self, fleet_id: str, contact_id: str) -> bool:
        """Designate a target for the entire fleet."""
        if fleet_id not in self.fleets:
            return False

        self.fleet_targets[fleet_id] = contact_id
        self.fleets[fleet_id].target_contact = contact_id
        self.fleets[fleet_id].status = FleetStatus.ENGAGING

        # Broadcast target to all ships
        self._broadcast_to_fleet(fleet_id, "target", {
            "contact_id": contact_id,
            "action": "designate"
        })

        return True

    def fleet_fire(self, fleet_id: str, volley: bool = False) -> Dict:
        """
        Order fleet to fire on designated target.

        Args:
            fleet_id: ID of the fleet
            volley: If True, coordinate simultaneous fire

        Returns:
            Dictionary with firing results per ship
        """
        if fleet_id not in self.fleets:
            return {"success": False, "error": "Fleet not found"}

        fleet = self.fleets[fleet_id]
        if not fleet.target_contact:
            return {"success": False, "error": "No target designated"}

        results = {}

        if volley:
            # Coordinated volley - all ships fire together
            self._broadcast_to_fleet(fleet_id, "command", {
                "type": "fire_volley",
                "target": fleet.target_contact,
                "timestamp": time.time()
            })
            results["volley"] = True
        else:
            # Independent fire - ships engage at will
            self._broadcast_to_fleet(fleet_id, "command", {
                "type": "fire_at_will",
                "target": fleet.target_contact
            })
            results["independent"] = True

        results["success"] = True
        results["target"] = fleet.target_contact
        results["ships"] = len(fleet.ship_ids)

        return results

    def fleet_maneuver(
        self,
        fleet_id: str,
        maneuver_type: str,
        target_position: Optional[np.ndarray] = None,
        target_velocity: Optional[np.ndarray] = None
    ) -> bool:
        """
        Execute a coordinated fleet maneuver.

        Args:
            fleet_id: ID of the fleet
            maneuver_type: Type of maneuver ("intercept", "match_velocity", "hold", "evasive")
            target_position: Target position for maneuver
            target_velocity: Target velocity for maneuver

        Returns:
            True if maneuver initiated
        """
        if fleet_id not in self.fleets:
            return False

        fleet = self.fleets[fleet_id]
        fleet.status = FleetStatus.MANEUVERING

        maneuver_data = {
            "type": maneuver_type,
        }

        if target_position is not None:
            maneuver_data["position"] = target_position.tolist()
        if target_velocity is not None:
            maneuver_data["velocity"] = target_velocity.tolist()

        self._broadcast_to_fleet(fleet_id, "command", {
            "type": "maneuver",
            "maneuver": maneuver_data
        })

        return True

    def share_contact(
        self,
        contact_id: str,
        reporting_ship: str,
        position: np.ndarray,
        velocity: np.ndarray,
        classification: str,
        confidence: float,
        is_hostile: bool = False
    ) -> bool:
        """
        Share a sensor contact via tactical data link.

        Args:
            contact_id: Contact identifier
            reporting_ship: ID of ship reporting the contact
            position: Contact position [x, y, z]
            velocity: Contact velocity [vx, vy, vz]
            classification: Contact classification
            confidence: Detection confidence (0-1)
            is_hostile: Whether contact is hostile

        Returns:
            True if contact shared
        """
        # Determine threat level based on classification and hostility
        threat_level = ThreatLevel.NONE
        if is_hostile:
            if "fighter" in classification.lower():
                threat_level = ThreatLevel.MEDIUM
            elif "cruiser" in classification.lower() or "frigate" in classification.lower():
                threat_level = ThreatLevel.HIGH
            elif "battleship" in classification.lower() or "carrier" in classification.lower():
                threat_level = ThreatLevel.CRITICAL

        contact = SharedContact(
            contact_id=contact_id,
            reporting_ship=reporting_ship,
            timestamp=time.time(),
            position=position,
            velocity=velocity,
            classification=classification,
            confidence=confidence,
            threat_level=threat_level,
            is_hostile=is_hostile,
            last_update=time.time()
        )

        self.shared_contacts[contact_id] = contact

        # Broadcast to fleet
        if reporting_ship in self.ship_to_fleet:
            fleet_id = self.ship_to_fleet[reporting_ship]
            self._broadcast_to_fleet(fleet_id, "contact", {
                "contact_id": contact_id,
                "position": position.tolist(),
                "velocity": velocity.tolist(),
                "classification": classification,
                "confidence": confidence,
                "threat_level": threat_level.name,
                "is_hostile": is_hostile,
                "reporting_ship": reporting_ship
            })

        return True

    def get_shared_contacts(self, fleet_id: str) -> List[SharedContact]:
        """Get all shared contacts visible to a fleet."""
        # Clean up expired contacts
        current_time = time.time()
        expired = [
            cid for cid, contact in self.shared_contacts.items()
            if current_time - contact.last_update > self.contact_timeout
        ]
        for cid in expired:
            del self.shared_contacts[cid]

        # Return all active contacts
        return list(self.shared_contacts.values())

    def send_message(
        self,
        from_ship: str,
        to_ship: Optional[str],
        message_type: str,
        content: Dict,
        priority: int = 1
    ) -> bool:
        """
        Send a message between ships.

        Args:
            from_ship: Sending ship ID
            to_ship: Receiving ship ID (None for broadcast)
            message_type: Type of message
            content: Message content
            priority: Message priority (1-5)

        Returns:
            True if message queued
        """
        message = FleetMessage(
            timestamp=time.time(),
            from_ship=from_ship,
            to_ship=to_ship,
            message_type=message_type,
            content=content,
            priority=priority
        )

        self.message_queue.append(message)
        self.message_history.append(message)

        # Trim history if needed
        if len(self.message_history) > self.max_history:
            self.message_history = self.message_history[-self.max_history:]

        return True

    def get_messages_for_ship(self, ship_id: str, since: Optional[float] = None) -> List[FleetMessage]:
        """
        Get all messages for a specific ship.

        Args:
            ship_id: Ship to get messages for
            since: Only return messages after this timestamp

        Returns:
            List of messages for the ship
        """
        messages = [
            msg for msg in self.message_queue
            if msg.to_ship is None or msg.to_ship == ship_id
        ]

        if since is not None:
            messages = [msg for msg in messages if msg.timestamp > since]

        # Sort by priority then timestamp
        messages.sort(key=lambda m: (-m.priority, m.timestamp))

        return messages

    def clear_ship_messages(self, ship_id: str):
        """Clear messages that have been delivered to a ship."""
        self.message_queue = [
            msg for msg in self.message_queue
            if msg.to_ship != ship_id and msg.to_ship is not None
        ]

    def get_fleet_status(self, fleet_id: str) -> Optional[Dict]:
        """Get comprehensive status of a fleet."""
        if fleet_id not in self.fleets:
            return None

        fleet = self.fleets[fleet_id]

        # Get ship statuses
        ships_status = []
        for ship_id in fleet.ship_ids:
            ship = self._get_ship(ship_id)
            if ship:
                ships_status.append({
                    "ship_id": ship_id,
                    "position": [ship.x, ship.y, ship.z],
                    "velocity": [ship.vx, ship.vy, ship.vz],
                    "systems_online": self._get_ship_systems_status(ship),
                    "is_flagship": ship_id == fleet.flagship_id,
                    "is_ai_controlled": ship_id in self.ai_controlled_ships
                })

        # Get formation info
        formation_info = None
        if fleet.formation_id:
            formation_info = self.formation_manager.get_formation_status(fleet.formation_id)

        # Get current target
        target_info = None
        if fleet.target_contact and fleet.target_contact in self.shared_contacts:
            contact = self.shared_contacts[fleet.target_contact]
            target_info = {
                "contact_id": contact.contact_id,
                "classification": contact.classification,
                "threat_level": contact.threat_level.name,
                "is_hostile": contact.is_hostile
            }

        return {
            "fleet_id": fleet_id,
            "name": fleet.name,
            "status": fleet.status.value,
            "flagship": fleet.flagship_id,
            "ship_count": len(fleet.ship_ids),
            "ships": ships_status,
            "formation": formation_info,
            "target": target_info,
            "shared_contacts": len(self.get_shared_contacts(fleet_id))
        }

    def get_fleet_tactical_summary(self, fleet_id: str) -> Optional[Dict]:
        """Get tactical summary for fleet commander."""
        if fleet_id not in self.fleets:
            return None

        fleet = self.fleets[fleet_id]

        # Aggregate fleet firepower
        total_weapons = 0
        total_ammo = 0
        ships_in_range = 0

        for ship_id in fleet.ship_ids:
            ship = self._get_ship(ship_id)
            if ship and hasattr(ship, 'systems'):
                weapon_sys = ship.systems.get('weapons')
                if weapon_sys:
                    total_weapons += len(weapon_sys.weapons) if hasattr(weapon_sys, 'weapons') else 0

        # Get threat assessment
        hostile_contacts = [
            c for c in self.shared_contacts.values()
            if c.is_hostile
        ]

        threat_summary = {
            "total_hostiles": len(hostile_contacts),
            "critical_threats": len([c for c in hostile_contacts if c.threat_level == ThreatLevel.CRITICAL]),
            "high_threats": len([c for c in hostile_contacts if c.threat_level == ThreatLevel.HIGH]),
            "medium_threats": len([c for c in hostile_contacts if c.threat_level == ThreatLevel.MEDIUM]),
        }

        return {
            "fleet_id": fleet_id,
            "combat_ready": len(fleet.ship_ids),
            "total_weapons": total_weapons,
            "formation_status": fleet.status.value,
            "target_locked": fleet.target_contact is not None,
            "threat_summary": threat_summary,
            "contacts_tracked": len(self.shared_contacts)
        }

    def _broadcast_to_fleet(self, fleet_id: str, message_type: str, content: Dict):
        """Broadcast a message to all ships in a fleet."""
        if fleet_id not in self.fleets:
            return

        fleet = self.fleets[fleet_id]
        for ship_id in fleet.ship_ids:
            self.send_message(
                from_ship=fleet.flagship_id,
                to_ship=ship_id,
                message_type=message_type,
                content=content,
                priority=3
            )

    def _get_ship(self, ship_id: str):
        """Get ship object from simulator."""
        if self.simulator and ship_id in self.simulator.ships:
            return self.simulator.ships[ship_id]
        return None

    def _get_ship_orientation(self, ship) -> np.ndarray:
        """Get ship's orientation vector."""
        # If ship has velocity, use velocity direction
        velocity = np.array([ship.vx, ship.vy, ship.vz])
        speed = np.linalg.norm(velocity)

        if speed > 1.0:  # Moving significantly
            return velocity / speed

        # Default to X-axis if stationary
        return np.array([1.0, 0.0, 0.0])

    def _get_ship_systems_status(self, ship) -> Dict[str, bool]:
        """Get status of ship's critical systems."""
        if not hasattr(ship, 'systems'):
            return {}

        return {
            system_name: system.is_online if hasattr(system, 'is_online') else True
            for system_name, system in ship.systems.items()
        }

    def update(self, dt: float):
        """
        Update fleet manager state. Call this each simulation tick.

        Args:
            dt: Time delta in seconds
        """
        # Clean up old messages (keep last 10 minutes)
        current_time = time.time()
        cutoff_time = current_time - 600
        self.message_history = [
            msg for msg in self.message_history
            if msg.timestamp > cutoff_time
        ]

        # Update fleet statuses based on formation adherence
        for fleet_id, fleet in self.fleets.items():
            if fleet.formation_id and fleet.status == FleetStatus.FORMING:
                # Check if ships are in position (simplified check)
                if self._check_formation_adherence(fleet_id):
                    fleet.status = FleetStatus.IN_FORMATION

    def _check_formation_adherence(self, fleet_id: str) -> bool:
        """Check if fleet is adhering to formation (simplified)."""
        # This would check actual ship positions vs formation positions
        # For now, just return True after a delay
        fleet = self.fleets[fleet_id]
        return fleet.status == FleetStatus.FORMING
