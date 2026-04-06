# tests/systems/sensors/test_contact_id_stability.py
"""Tests for stable contact ID mapping after ship destruction.

When a ship is destroyed and pruned from the contact tracker, the
id_mapping (real_ship_id -> stable_contact_id) must be preserved.
Deleting it causes re-detected or new ships to collide with existing
contact IDs, cascading into total contact loss for all surviving ships.
"""

import time
from hybrid.systems.sensors.contact import ContactData, ContactTracker


def _make_contact(ship_id: str, confidence: float = 0.8) -> ContactData:
    """Helper: build a minimal ContactData for testing."""
    return ContactData(
        id=ship_id,
        position={"x": 1000.0, "y": 0.0, "z": 0.0},
        velocity={"x": 0.0, "y": 0.0, "z": 0.0},
        confidence=confidence,
        last_update=0.0,
        detection_method="passive",
        classification="corvette",
        name=f"ship_{ship_id}",
    )


class TestPrunePreservesIdMapping:
    """Pruning a destroyed ship's contact must keep its id_mapping entry."""

    def test_prune_preserves_id_mapping_for_dead_ships(self) -> None:
        """After pruning a dead ship, its id_mapping entry must survive.

        This is the core invariant: the mapping from real ship ID to stable
        contact ID is permanent. Without it, subsequent update_contact()
        calls allocate new IDs that collide with live contacts.
        """
        tracker = ContactTracker(stale_threshold=5.0)
        tracker.update_contact("ship_a", _make_contact("ship_a"), current_time=0.0)

        # Verify initial state
        assert "ship_a" in tracker.id_mapping
        assert tracker.id_mapping["ship_a"] == "C001"
        assert "C001" in tracker.contacts

        # Prune with ship_a absent from existing ships (it was destroyed).
        # Use a time well past the stale threshold so the contact qualifies.
        tracker.prune_stale_contacts(current_time=100.0, existing_ship_ids=set())

        # Contact data should be gone, but the mapping must persist
        assert "C001" not in tracker.contacts
        assert "ship_a" in tracker.id_mapping
        assert tracker.id_mapping["ship_a"] == "C001"

    def test_redetected_ship_keeps_original_id(self) -> None:
        """If a pruned ship reappears, it must get its original stable ID.

        Covers the scenario where a ship is destroyed and removed, then
        a new ship with the same ID spawns (e.g. reinforcement wave).
        The stable contact ID must be C001, not C002.
        """
        tracker = ContactTracker(stale_threshold=5.0)
        tracker.update_contact("ship_a", _make_contact("ship_a"), current_time=0.0)
        assert tracker.id_mapping["ship_a"] == "C001"

        # Prune (ship destroyed)
        tracker.prune_stale_contacts(current_time=100.0, existing_ship_ids=set())

        # Re-detect the same ship ID
        tracker.update_contact("ship_a", _make_contact("ship_a"), current_time=101.0)

        # Must reuse C001, not allocate C002
        assert tracker.id_mapping["ship_a"] == "C001"
        assert "C001" in tracker.contacts
        assert tracker.next_contact_number == 2  # counter unchanged

    def test_destroying_one_contact_preserves_others(self) -> None:
        """Pruning one dead ship must not corrupt surviving contacts.

        Regression test: the old code deleted id_mapping entries on prune,
        which could cause update_contact() for surviving ships to generate
        colliding IDs on the next scan cycle.
        """
        tracker = ContactTracker(stale_threshold=5.0)
        tracker.update_contact("ship_a", _make_contact("ship_a"), current_time=0.0)
        tracker.update_contact("ship_b", _make_contact("ship_b"), current_time=0.0)
        tracker.update_contact("ship_c", _make_contact("ship_c"), current_time=0.0)

        assert tracker.id_mapping["ship_a"] == "C001"
        assert tracker.id_mapping["ship_b"] == "C002"
        assert tracker.id_mapping["ship_c"] == "C003"

        # ship_a destroyed; ship_b and ship_c still alive.
        # Only ship_a's contact data is stale (we update b and c recently).
        tracker.update_contact("ship_b", _make_contact("ship_b"), current_time=50.0)
        tracker.update_contact("ship_c", _make_contact("ship_c"), current_time=50.0)

        tracker.prune_stale_contacts(
            current_time=100.0,
            existing_ship_ids={"ship_b", "ship_c"},
        )

        # ship_a contact data removed, but mapping preserved
        assert "C001" not in tracker.contacts
        assert "ship_a" in tracker.id_mapping

        # ship_b and ship_c fully intact
        assert "C002" in tracker.contacts
        assert "C003" in tracker.contacts
        assert tracker.contacts["C002"].name == "ship_ship_b"
        assert tracker.contacts["C003"].name == "ship_ship_c"
        assert tracker.id_mapping["ship_b"] == "C002"
        assert tracker.id_mapping["ship_c"] == "C003"

    def test_new_ship_after_prune_gets_next_id(self) -> None:
        """A brand-new ship after a prune must get the NEXT counter ID.

        After ship_a (C001) is pruned, a new ship_d must get C004 (if 3
        ships were previously tracked), not C001. The counter is monotonic
        and never recycles IDs -- recycling would cause ambiguous log entries
        and break any system that cached a contact ID.
        """
        tracker = ContactTracker(stale_threshold=5.0)
        tracker.update_contact("ship_a", _make_contact("ship_a"), current_time=0.0)
        tracker.update_contact("ship_b", _make_contact("ship_b"), current_time=0.0)
        tracker.update_contact("ship_c", _make_contact("ship_c"), current_time=0.0)

        # Prune ship_a
        tracker.prune_stale_contacts(current_time=100.0, existing_ship_ids={"ship_b", "ship_c"})

        # Add a completely new ship
        tracker.update_contact("ship_d", _make_contact("ship_d"), current_time=101.0)

        # Must be C004, not C001 (recycled) or C002/C003 (collision)
        assert tracker.id_mapping["ship_d"] == "C004"
        assert "C004" in tracker.contacts
        assert tracker.next_contact_number == 5
