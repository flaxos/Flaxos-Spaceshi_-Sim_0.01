"""
Fleet Formation System
Manages formation types, position calculations, and station-keeping for fleet coordination.
"""

import math
from enum import Enum
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import numpy as np


class FormationType(Enum):
    """Available formation types for fleet operations"""
    LINE = "line"           # Ships arranged in a horizontal line
    COLUMN = "column"       # Ships arranged in a vertical column
    WALL = "wall"           # Ships arranged in a 2D wall/grid
    SPHERE = "sphere"       # Ships arranged in a defensive sphere
    WEDGE = "wedge"         # Ships arranged in a wedge/V formation
    ECHELON = "echelon"     # Ships arranged in diagonal echelon
    DIAMOND = "diamond"     # Ships arranged in diamond formation
    FREE = "free"           # No formation, ships move independently


@dataclass
class FormationPosition:
    """Calculated position for a ship in formation"""
    ship_id: str
    slot_index: int
    relative_position: np.ndarray  # Position relative to flagship [x, y, z] in meters
    relative_velocity: np.ndarray  # Velocity relative to flagship [vx, vy, vz] in m/s
    priority: int  # Priority in formation (0 = flagship)


@dataclass
class FormationConfig:
    """Configuration for a specific formation"""
    formation_type: FormationType
    spacing: float  # Distance between ships in meters
    flagship_id: str
    orientation: np.ndarray  # Forward direction vector [x, y, z]
    up_vector: np.ndarray  # Up direction vector [x, y, z]
    echelon_angle: float = 30.0  # Angle for echelon formation in degrees
    wall_columns: int = 3  # Number of columns for wall formation
    sphere_radius: float = 5000.0  # Radius for sphere formation in meters


class FleetFormation:
    """
    Manages fleet formations and calculates ship positions.
    Provides position calculations for various tactical formations.
    """

    def __init__(self):
        self.formations: Dict[str, FormationConfig] = {}
        self.ship_assignments: Dict[str, str] = {}  # ship_id -> formation_id

    def create_formation(
        self,
        formation_id: str,
        formation_type: FormationType,
        flagship_id: str,
        spacing: float = 2000.0,  # Default 2km spacing
        orientation: Optional[np.ndarray] = None,
        up_vector: Optional[np.ndarray] = None,
        **kwargs
    ) -> bool:
        """
        Create a new fleet formation.

        Args:
            formation_id: Unique identifier for this formation
            formation_type: Type of formation to create
            flagship_id: ID of the flagship (formation center/leader)
            spacing: Distance between ships in meters
            orientation: Forward direction vector (default: [1, 0, 0])
            up_vector: Up direction vector (default: [0, 0, 1])
            **kwargs: Additional formation-specific parameters

        Returns:
            True if formation created successfully
        """
        if orientation is None:
            orientation = np.array([1.0, 0.0, 0.0])
        if up_vector is None:
            up_vector = np.array([0.0, 0.0, 1.0])

        # Normalize vectors
        orientation = orientation / np.linalg.norm(orientation)
        up_vector = up_vector / np.linalg.norm(up_vector)

        config = FormationConfig(
            formation_type=formation_type,
            spacing=spacing,
            flagship_id=flagship_id,
            orientation=orientation,
            up_vector=up_vector,
            echelon_angle=kwargs.get('echelon_angle', 30.0),
            wall_columns=kwargs.get('wall_columns', 3),
            sphere_radius=kwargs.get('sphere_radius', spacing * 2)
        )

        self.formations[formation_id] = config
        return True

    def assign_ship(self, ship_id: str, formation_id: str) -> bool:
        """Assign a ship to a formation."""
        if formation_id not in self.formations:
            return False
        self.ship_assignments[ship_id] = formation_id
        return True

    def remove_ship(self, ship_id: str) -> bool:
        """Remove a ship from its formation."""
        if ship_id in self.ship_assignments:
            del self.ship_assignments[ship_id]
            return True
        return False

    def get_formation_ships(self, formation_id: str) -> List[str]:
        """Get all ships assigned to a formation."""
        return [ship_id for ship_id, fid in self.ship_assignments.items() if fid == formation_id]

    def calculate_positions(
        self,
        formation_id: str,
        flagship_pos: np.ndarray,
        flagship_vel: np.ndarray
    ) -> List[FormationPosition]:
        """
        Calculate positions for all ships in formation.

        Args:
            formation_id: ID of the formation
            flagship_pos: Flagship's current position [x, y, z]
            flagship_vel: Flagship's current velocity [vx, vy, vz]

        Returns:
            List of FormationPosition objects for each ship
        """
        if formation_id not in self.formations:
            return []

        config = self.formations[formation_id]
        ships = self.get_formation_ships(formation_id)

        # Remove flagship from ship list and sort for consistent ordering
        ships = [s for s in ships if s != config.flagship_id]
        ships.sort()

        # Calculate positions based on formation type
        if config.formation_type == FormationType.LINE:
            return self._calculate_line_formation(ships, config, flagship_pos, flagship_vel)
        elif config.formation_type == FormationType.COLUMN:
            return self._calculate_column_formation(ships, config, flagship_pos, flagship_vel)
        elif config.formation_type == FormationType.WALL:
            return self._calculate_wall_formation(ships, config, flagship_pos, flagship_vel)
        elif config.formation_type == FormationType.SPHERE:
            return self._calculate_sphere_formation(ships, config, flagship_pos, flagship_vel)
        elif config.formation_type == FormationType.WEDGE:
            return self._calculate_wedge_formation(ships, config, flagship_pos, flagship_vel)
        elif config.formation_type == FormationType.ECHELON:
            return self._calculate_echelon_formation(ships, config, flagship_pos, flagship_vel)
        elif config.formation_type == FormationType.DIAMOND:
            return self._calculate_diamond_formation(ships, config, flagship_pos, flagship_vel)
        else:  # FREE
            return []

    def _calculate_line_formation(
        self,
        ships: List[str],
        config: FormationConfig,
        flagship_pos: np.ndarray,
        flagship_vel: np.ndarray
    ) -> List[FormationPosition]:
        """Calculate positions for line formation (ships side-by-side)."""
        positions = []

        # Get right vector (perpendicular to forward and up)
        right = np.cross(config.orientation, config.up_vector)
        right = right / np.linalg.norm(right)

        # Place flagship at center
        positions.append(FormationPosition(
            ship_id=config.flagship_id,
            slot_index=0,
            relative_position=np.array([0.0, 0.0, 0.0]),
            relative_velocity=np.array([0.0, 0.0, 0.0]),
            priority=0
        ))

        # Place other ships alternating left/right
        for i, ship_id in enumerate(ships):
            slot = i + 1
            side = 1 if i % 2 == 0 else -1  # Alternate sides
            offset = (i // 2 + 1) * config.spacing

            rel_pos = right * side * offset

            positions.append(FormationPosition(
                ship_id=ship_id,
                slot_index=slot,
                relative_position=rel_pos,
                relative_velocity=np.array([0.0, 0.0, 0.0]),
                priority=slot
            ))

        return positions

    def _calculate_column_formation(
        self,
        ships: List[str],
        config: FormationConfig,
        flagship_pos: np.ndarray,
        flagship_vel: np.ndarray
    ) -> List[FormationPosition]:
        """Calculate positions for column formation (ships in single file)."""
        positions = []

        # Flagship at front
        positions.append(FormationPosition(
            ship_id=config.flagship_id,
            slot_index=0,
            relative_position=np.array([0.0, 0.0, 0.0]),
            relative_velocity=np.array([0.0, 0.0, 0.0]),
            priority=0
        ))

        # Other ships behind flagship
        for i, ship_id in enumerate(ships):
            slot = i + 1
            # Position behind flagship along negative forward vector
            rel_pos = -config.orientation * slot * config.spacing

            positions.append(FormationPosition(
                ship_id=ship_id,
                slot_index=slot,
                relative_position=rel_pos,
                relative_velocity=np.array([0.0, 0.0, 0.0]),
                priority=slot
            ))

        return positions

    def _calculate_wall_formation(
        self,
        ships: List[str],
        config: FormationConfig,
        flagship_pos: np.ndarray,
        flagship_vel: np.ndarray
    ) -> List[FormationPosition]:
        """Calculate positions for wall formation (2D grid)."""
        positions = []

        # Get right and up vectors
        right = np.cross(config.orientation, config.up_vector)
        right = right / np.linalg.norm(right)

        # Flagship at center
        positions.append(FormationPosition(
            ship_id=config.flagship_id,
            slot_index=0,
            relative_position=np.array([0.0, 0.0, 0.0]),
            relative_velocity=np.array([0.0, 0.0, 0.0]),
            priority=0
        ))

        # Arrange ships in grid
        cols = config.wall_columns
        for i, ship_id in enumerate(ships):
            slot = i + 1
            row = i // cols
            col = i % cols

            # Center the grid
            col_offset = (col - (cols - 1) / 2) * config.spacing
            row_offset = row * config.spacing

            rel_pos = right * col_offset + config.up_vector * row_offset

            positions.append(FormationPosition(
                ship_id=ship_id,
                slot_index=slot,
                relative_position=rel_pos,
                relative_velocity=np.array([0.0, 0.0, 0.0]),
                priority=slot
            ))

        return positions

    def _calculate_wedge_formation(
        self,
        ships: List[str],
        config: FormationConfig,
        flagship_pos: np.ndarray,
        flagship_vel: np.ndarray
    ) -> List[FormationPosition]:
        """Calculate positions for wedge formation (V-shape)."""
        positions = []

        # Get right vector
        right = np.cross(config.orientation, config.up_vector)
        right = right / np.linalg.norm(right)

        # Flagship at point of wedge
        positions.append(FormationPosition(
            ship_id=config.flagship_id,
            slot_index=0,
            relative_position=np.array([0.0, 0.0, 0.0]),
            relative_velocity=np.array([0.0, 0.0, 0.0]),
            priority=0
        ))

        # Ships form V behind flagship
        wedge_angle = 30.0  # degrees from center line
        angle_rad = math.radians(wedge_angle)

        for i, ship_id in enumerate(ships):
            slot = i + 1
            side = 1 if i % 2 == 0 else -1
            rank = (i // 2 + 1)  # Distance from flagship

            # Calculate position: back and to the side
            back_offset = rank * config.spacing * math.cos(angle_rad)
            side_offset = rank * config.spacing * math.sin(angle_rad) * side

            rel_pos = -config.orientation * back_offset + right * side_offset

            positions.append(FormationPosition(
                ship_id=ship_id,
                slot_index=slot,
                relative_position=rel_pos,
                relative_velocity=np.array([0.0, 0.0, 0.0]),
                priority=slot
            ))

        return positions

    def _calculate_echelon_formation(
        self,
        ships: List[str],
        config: FormationConfig,
        flagship_pos: np.ndarray,
        flagship_vel: np.ndarray
    ) -> List[FormationPosition]:
        """Calculate positions for echelon formation (diagonal line)."""
        positions = []

        # Get right vector
        right = np.cross(config.orientation, config.up_vector)
        right = right / np.linalg.norm(right)

        # Flagship at front
        positions.append(FormationPosition(
            ship_id=config.flagship_id,
            slot_index=0,
            relative_position=np.array([0.0, 0.0, 0.0]),
            relative_velocity=np.array([0.0, 0.0, 0.0]),
            priority=0
        ))

        # Ships form diagonal line
        angle_rad = math.radians(config.echelon_angle)

        for i, ship_id in enumerate(ships):
            slot = i + 1

            # Position: back and to the right (or left for left echelon)
            back_offset = slot * config.spacing * math.cos(angle_rad)
            side_offset = slot * config.spacing * math.sin(angle_rad)

            rel_pos = -config.orientation * back_offset + right * side_offset

            positions.append(FormationPosition(
                ship_id=ship_id,
                slot_index=slot,
                relative_position=rel_pos,
                relative_velocity=np.array([0.0, 0.0, 0.0]),
                priority=slot
            ))

        return positions

    def _calculate_sphere_formation(
        self,
        ships: List[str],
        config: FormationConfig,
        flagship_pos: np.ndarray,
        flagship_vel: np.ndarray
    ) -> List[FormationPosition]:
        """Calculate positions for sphere formation (defensive globe)."""
        positions = []

        # Flagship at center
        positions.append(FormationPosition(
            ship_id=config.flagship_id,
            slot_index=0,
            relative_position=np.array([0.0, 0.0, 0.0]),
            relative_velocity=np.array([0.0, 0.0, 0.0]),
            priority=0
        ))

        # Distribute ships evenly on sphere using Fibonacci sphere algorithm
        num_ships = len(ships)
        golden_ratio = (1 + math.sqrt(5)) / 2

        for i, ship_id in enumerate(ships):
            slot = i + 1

            # Fibonacci sphere distribution
            theta = 2 * math.pi * i / golden_ratio
            phi = math.acos(1 - 2 * (i + 0.5) / num_ships)

            # Convert spherical to Cartesian
            x = config.sphere_radius * math.sin(phi) * math.cos(theta)
            y = config.sphere_radius * math.sin(phi) * math.sin(theta)
            z = config.sphere_radius * math.cos(phi)

            rel_pos = np.array([x, y, z])

            positions.append(FormationPosition(
                ship_id=ship_id,
                slot_index=slot,
                relative_position=rel_pos,
                relative_velocity=np.array([0.0, 0.0, 0.0]),
                priority=slot
            ))

        return positions

    def _calculate_diamond_formation(
        self,
        ships: List[str],
        config: FormationConfig,
        flagship_pos: np.ndarray,
        flagship_vel: np.ndarray
    ) -> List[FormationPosition]:
        """Calculate positions for diamond formation (4-ship basic)."""
        positions = []

        # Get right and up vectors
        right = np.cross(config.orientation, config.up_vector)
        right = right / np.linalg.norm(right)

        # Flagship at center
        positions.append(FormationPosition(
            ship_id=config.flagship_id,
            slot_index=0,
            relative_position=np.array([0.0, 0.0, 0.0]),
            relative_velocity=np.array([0.0, 0.0, 0.0]),
            priority=0
        ))

        # Diamond positions: front, right, back, left (then repeat pattern)
        diamond_offsets = [
            config.orientation,      # Front
            right,                   # Right
            -config.orientation,     # Back
            -right,                  # Left
        ]

        for i, ship_id in enumerate(ships):
            slot = i + 1
            offset_index = i % 4
            ring = (i // 4) + 1  # Which ring of the diamond

            rel_pos = diamond_offsets[offset_index] * config.spacing * ring

            positions.append(FormationPosition(
                ship_id=ship_id,
                slot_index=slot,
                relative_position=rel_pos,
                relative_velocity=np.array([0.0, 0.0, 0.0]),
                priority=slot
            ))

        return positions

    def get_formation_status(self, formation_id: str) -> Optional[Dict]:
        """Get current status of a formation."""
        if formation_id not in self.formations:
            return None

        config = self.formations[formation_id]
        ships = self.get_formation_ships(formation_id)

        return {
            "formation_id": formation_id,
            "type": config.formation_type.value,
            "flagship": config.flagship_id,
            "ship_count": len(ships),
            "ships": ships,
            "spacing": config.spacing,
            "orientation": config.orientation.tolist(),
        }

    def dissolve_formation(self, formation_id: str) -> bool:
        """Dissolve a formation and free all ships."""
        if formation_id not in self.formations:
            return False

        # Remove all ship assignments
        ships = self.get_formation_ships(formation_id)
        for ship_id in ships:
            self.remove_ship(ship_id)

        # Remove formation
        del self.formations[formation_id]
        return True
