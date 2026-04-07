"""Grid-based spatial index for efficient neighbor queries.

Passive sensor detection iterates ALL ships for EACH ship -- O(n^2).
This spatial grid bins ships into cells so that each ship only checks
nearby cells, reducing sensor checks to O(n * k) where k is the
average number of ships per cell neighborhood.

Cell size is tuned to typical sensor detection ranges (~100km).
Ships far beyond sensor range are never even considered.
"""

from typing import Dict, List, Any
import math


class SpatialGrid:
    """Fixed-size grid for spatial neighbor lookups.

    Ships are binned into cells based on position. Queries return
    only ships in nearby cells, reducing O(n^2) sensor checks to
    O(n * k) where k is the average number of ships per cell neighborhood.
    """

    def __init__(self, cell_size: float = 100_000.0):
        """Initialize grid.

        Args:
            cell_size: Grid cell size in meters. Default 100km matches
                typical passive sensor ranges -- a cold drifter is only
                visible at short range, while a thrusting ship's IR plume
                can reach ~300km. 100km cells mean we check a 3x3x3 cube
                of cells for short-range contacts and scale up for longer
                range queries.
        """
        self.cell_size = cell_size
        self._cells: Dict[tuple, List[Any]] = {}

    def _cell_key(self, position: dict) -> tuple:
        """Compute grid cell for a position.

        Args:
            position: Dict with x, y, z keys (meters).

        Returns:
            Tuple of integer cell coordinates.
        """
        x = position.get("x", 0.0)
        y = position.get("y", 0.0)
        z = position.get("z", 0.0)
        return (
            math.floor(x / self.cell_size),
            math.floor(y / self.cell_size),
            math.floor(z / self.cell_size),
        )

    def clear(self) -> None:
        """Clear all entries. Called once per tick before re-insertion."""
        self._cells.clear()

    def insert(self, entity: Any, position: dict) -> None:
        """Insert an entity at a position.

        Args:
            entity: Any object (typically a Ship).
            position: Dict with x, y, z keys (meters).
        """
        key = self._cell_key(position)
        if key not in self._cells:
            self._cells[key] = []
        self._cells[key].append(entity)

    def query_radius(self, position: dict, radius: float) -> List[Any]:
        """Return all entities within radius of position.

        Checks all cells that could contain entities within the given
        radius. This is a coarse filter -- callers should still do
        exact distance checks on the returned candidates.

        Args:
            position: Center of query sphere (dict with x, y, z).
            radius: Query radius in meters.

        Returns:
            List of entities in cells overlapping the query sphere.
        """
        center = self._cell_key(position)
        # Number of cells to check in each direction. ceil ensures we
        # never miss a cell that partially overlaps the query sphere.
        cell_radius = math.ceil(radius / self.cell_size)

        results: List[Any] = []
        for dx in range(-cell_radius, cell_radius + 1):
            for dy in range(-cell_radius, cell_radius + 1):
                for dz in range(-cell_radius, cell_radius + 1):
                    key = (center[0] + dx, center[1] + dy, center[2] + dz)
                    if key in self._cells:
                        results.extend(self._cells[key])
        return results
