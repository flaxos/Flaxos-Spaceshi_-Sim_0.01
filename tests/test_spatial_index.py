"""Tests for hybrid.spatial_index.SpatialGrid.

Verifies grid insertion, radius queries, cross-cell boundaries,
and empty-grid edge cases.
"""

import pytest
from hybrid.spatial_index import SpatialGrid


class TestSpatialGridBasic:
    """Basic insert/query operations."""

    def test_empty_grid_returns_empty(self):
        grid = SpatialGrid(cell_size=100.0)
        result = grid.query_radius({"x": 0, "y": 0, "z": 0}, radius=500.0)
        assert result == []

    def test_insert_and_query_single_entity(self):
        grid = SpatialGrid(cell_size=100.0)
        grid.insert("ship_a", {"x": 50, "y": 50, "z": 0})
        result = grid.query_radius({"x": 50, "y": 50, "z": 0}, radius=10.0)
        assert result == ["ship_a"]

    def test_entity_outside_radius_not_returned(self):
        """Entity in a far-away cell should not appear in a local query."""
        grid = SpatialGrid(cell_size=100.0)
        grid.insert("nearby", {"x": 50, "y": 0, "z": 0})
        grid.insert("far_away", {"x": 50000, "y": 0, "z": 0})

        result = grid.query_radius({"x": 0, "y": 0, "z": 0}, radius=200.0)
        assert "nearby" in result
        assert "far_away" not in result

    def test_multiple_entities_same_cell(self):
        """Multiple entities landing in the same cell are all returned."""
        grid = SpatialGrid(cell_size=1000.0)
        grid.insert("a", {"x": 10, "y": 10, "z": 10})
        grid.insert("b", {"x": 20, "y": 20, "z": 20})
        grid.insert("c", {"x": 30, "y": 30, "z": 30})

        result = grid.query_radius({"x": 0, "y": 0, "z": 0}, radius=50.0)
        assert set(result) == {"a", "b", "c"}


class TestSpatialGridCrossBoundary:
    """Queries that span cell boundaries."""

    def test_cross_cell_boundary_query(self):
        """Entity just across a cell boundary should be found."""
        grid = SpatialGrid(cell_size=100.0)
        # Entity at x=101 is in cell (1,0,0), query from x=99 is in cell (0,0,0)
        grid.insert("across_boundary", {"x": 101, "y": 0, "z": 0})

        result = grid.query_radius({"x": 99, "y": 0, "z": 0}, radius=10.0)
        assert "across_boundary" in result

    def test_3d_cross_boundary(self):
        """Entity across boundaries in all three axes."""
        grid = SpatialGrid(cell_size=100.0)
        grid.insert("corner", {"x": 101, "y": 101, "z": 101})

        result = grid.query_radius({"x": 99, "y": 99, "z": 99}, radius=10.0)
        assert "corner" in result

    def test_negative_coordinates(self):
        """Grid handles negative coordinates correctly."""
        grid = SpatialGrid(cell_size=100.0)
        grid.insert("neg", {"x": -50, "y": -50, "z": -50})

        result = grid.query_radius({"x": -60, "y": -60, "z": -60}, radius=50.0)
        assert "neg" in result


class TestSpatialGridClear:
    """Clearing the grid between ticks."""

    def test_clear_removes_all_entities(self):
        grid = SpatialGrid(cell_size=100.0)
        grid.insert("a", {"x": 0, "y": 0, "z": 0})
        grid.insert("b", {"x": 500, "y": 0, "z": 0})

        grid.clear()

        result = grid.query_radius({"x": 0, "y": 0, "z": 0}, radius=10000.0)
        assert result == []

    def test_insert_after_clear(self):
        """Grid is usable after clearing."""
        grid = SpatialGrid(cell_size=100.0)
        grid.insert("old", {"x": 0, "y": 0, "z": 0})
        grid.clear()
        grid.insert("new", {"x": 10, "y": 10, "z": 0})

        result = grid.query_radius({"x": 0, "y": 0, "z": 0}, radius=50.0)
        assert result == ["new"]


class TestSpatialGridRealisticScales:
    """Sensor-range scale tests matching game distances."""

    def test_100km_cell_300km_query(self):
        """Typical passive sensor range: 300km query with 100km cells.

        Should check a 7x7x7 cube of cells (ceil(300000/100000) = 3
        cells in each direction).
        """
        grid = SpatialGrid(cell_size=100_000.0)
        # Ship at 250km away
        grid.insert("distant_ship", {"x": 250_000, "y": 0, "z": 0})
        # Ship at 350km away -- outside 300km range
        grid.insert("too_far", {"x": 350_000, "y": 0, "z": 0})

        result = grid.query_radius({"x": 0, "y": 0, "z": 0}, radius=300_000.0)
        assert "distant_ship" in result
        # too_far is in cell (3,0,0), query checks cells -3 to +3, so
        # cell (3,0,0) IS included in the coarse filter. The spatial grid
        # is a coarse filter -- callers do exact distance checks.
        # This verifies the grid returns candidates, not exact results.
        assert "too_far" in result  # coarse filter includes it

    def test_default_cell_size(self):
        """Default cell size is 100km."""
        grid = SpatialGrid()
        assert grid.cell_size == 100_000.0

    def test_missing_coordinates_default_to_zero(self):
        """Position dicts with missing keys default to 0."""
        grid = SpatialGrid(cell_size=100.0)
        grid.insert("partial", {"x": 5})  # y and z missing

        result = grid.query_radius({"x": 0}, radius=50.0)
        assert "partial" in result
