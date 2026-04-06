# tests/systems/sensors/test_ghost_contacts.py
"""Tests for ghost contact data masking and LOST state persistence."""

from types import SimpleNamespace
from hybrid.systems.sensors.contact import ContactData, ContactState, compute_contact_state
from hybrid.telemetry import get_sensor_contacts, _mask_contact_by_state, _coarsen_classification


# --- ContactState computation ---

def test_compute_contact_state_ghost():
    assert compute_contact_state(0.1) == "ghost"
    assert compute_contact_state(0.29) == "ghost"


def test_compute_contact_state_unconfirmed():
    assert compute_contact_state(0.3) == "unconfirmed"
    assert compute_contact_state(0.59) == "unconfirmed"


def test_compute_contact_state_confirmed():
    assert compute_contact_state(0.6) == "confirmed"
    assert compute_contact_state(0.95) == "confirmed"


# --- Telemetry masking ---

def test_ghost_mask_nulls_velocity_and_classification():
    """Ghost contacts should only expose bearing, rough distance, id, state, detection_method."""
    contact_dict = {
        "id": "C001",
        "position": {"x": 100.0, "y": 0.0, "z": 0.0},
        "velocity": {"x": 50.0, "y": 0.0, "z": 0.0},
        "distance": 10000.0,
        "bearing": {"azimuth": 45.0, "elevation": 0.0},
        "confidence": 0.2,
        "contact_state": "ghost",
        "last_update": 1.0,
        "detection_method": "ir",
        "name": "MCRN Donnager",
        "classification": "Battleship",
        "faction": "MCRN",
        "diplomatic_state": "hostile",
    }

    result = _mask_contact_by_state(contact_dict)

    # Nulled fields
    assert result["position"] is None
    assert result["velocity"] is None
    assert result["classification"] is None
    assert result["name"] is None
    assert result["faction"] is None
    assert result["diplomatic_state"] == "unknown"

    # Preserved fields
    assert result["id"] == "C001"
    assert result["bearing"] == {"azimuth": 45.0, "elevation": 0.0}
    assert result["contact_state"] == "ghost"
    assert result["detection_method"] == "ir"

    # Distance should be noised (+/- 30%) but still positive
    assert result["distance"] > 0
    assert 7000.0 <= result["distance"] <= 13000.0


def test_unconfirmed_mask_nulls_name_coarsens_classification():
    """Unconfirmed contacts get size-class classification and no name."""
    contact_dict = {
        "id": "C002",
        "position": {"x": 5000.0, "y": 0.0, "z": 0.0},
        "velocity": {"x": 100.0, "y": 50.0, "z": 0.0},
        "distance": 5000.0,
        "bearing": {"azimuth": 90.0, "elevation": 0.0},
        "confidence": 0.45,
        "contact_state": "unconfirmed",
        "last_update": 2.0,
        "detection_method": "ir",
        "name": "UNN Agatha King",
        "classification": "Cruiser",
        "faction": "UNN",
        "diplomatic_state": "allied",
    }

    result = _mask_contact_by_state(contact_dict)

    # Name nulled at unconfirmed
    assert result["name"] is None

    # Classification coarsened to size bucket
    assert result["classification"] in ("Small", "Medium", "Large")

    # Position preserved
    assert result["position"] == {"x": 5000.0, "y": 0.0, "z": 0.0}

    # Velocity preserved but noised (hard to assert exact values,
    # just verify it's still a dict with x/y/z)
    assert isinstance(result["velocity"], dict)
    assert "x" in result["velocity"]


def test_unconfirmed_preserves_size_class_classification():
    """If classification is already a size class, don't change it."""
    contact_dict = {
        "id": "C003",
        "position": {"x": 0.0, "y": 0.0, "z": 0.0},
        "velocity": {"x": 0.0, "y": 0.0, "z": 0.0},
        "distance": 1000.0,
        "bearing": {"azimuth": 0.0, "elevation": 0.0},
        "confidence": 0.4,
        "contact_state": "unconfirmed",
        "last_update": 1.0,
        "detection_method": "ir",
        "name": None,
        "classification": "Large",
        "faction": None,
        "diplomatic_state": "unknown",
    }

    result = _mask_contact_by_state(contact_dict)
    assert result["classification"] == "Large"


def test_confirmed_mask_no_changes():
    """Confirmed contacts should pass through unmodified."""
    contact_dict = {
        "id": "C004",
        "position": {"x": 200.0, "y": 0.0, "z": 0.0},
        "velocity": {"x": 30.0, "y": 0.0, "z": 0.0},
        "distance": 200.0,
        "bearing": {"azimuth": 0.0, "elevation": 0.0},
        "confidence": 0.8,
        "contact_state": "confirmed",
        "last_update": 3.0,
        "detection_method": "ir",
        "name": "Canterbury",
        "classification": "Freighter",
        "faction": "Pur'n'Kleen",
        "diplomatic_state": "neutral",
    }

    # Take a snapshot before masking
    original_name = contact_dict["name"]
    original_vel = dict(contact_dict["velocity"])
    original_class = contact_dict["classification"]

    result = _mask_contact_by_state(contact_dict)

    assert result["name"] == original_name
    assert result["velocity"] == original_vel
    assert result["classification"] == original_class
    assert result["position"] is not None


def test_lost_mask_nulls_velocity_and_name():
    """LOST contacts preserve position but null velocity and identity."""
    contact_dict = {
        "id": "C005",
        "position": {"x": 8000.0, "y": 1000.0, "z": 0.0},
        "velocity": {"x": 200.0, "y": 0.0, "z": 0.0},
        "distance": 8062.0,
        "bearing": {"azimuth": 7.0, "elevation": 0.0},
        "confidence": 0.15,
        "contact_state": "lost",
        "last_update": 5.0,
        "detection_method": "ir",
        "name": "Scopuli",
        "classification": "Medium",
        "faction": "OPA",
        "diplomatic_state": "hostile",
    }

    result = _mask_contact_by_state(contact_dict)

    # LOST: position preserved (last-known), velocity and name nulled
    assert result["position"] == {"x": 8000.0, "y": 1000.0, "z": 0.0}
    assert result["velocity"] is None
    assert result["name"] is None
    # Classification preserved — we knew what it was before we lost it
    assert result["classification"] == "Medium"


# --- Classification coarsening ---

def test_coarsen_classification_large():
    assert _coarsen_classification("Battleship") == "Large"
    assert _coarsen_classification("Carrier") == "Large"
    assert _coarsen_classification("Freighter") == "Large"
    assert _coarsen_classification("Station") == "Large"


def test_coarsen_classification_medium():
    assert _coarsen_classification("Corvette") == "Medium"
    assert _coarsen_classification("Destroyer") == "Medium"
    assert _coarsen_classification("Frigate") == "Medium"


def test_coarsen_classification_small():
    assert _coarsen_classification("Shuttle") == "Small"
    assert _coarsen_classification("Fighter") == "Small"
    assert _coarsen_classification("Unknown") == "Small"


# --- Integration: get_sensor_contacts with ContactTracker ---

def _make_ship_with_tracker(contacts_dict: dict, sim_time: float = 10.0):
    """Helper: build a minimal ship with a ContactTracker carrying the given contacts."""
    from hybrid.systems.sensors.contact import ContactTracker

    tracker = ContactTracker()
    for stable_id, contact in contacts_dict.items():
        contact.id = stable_id
        tracker.contacts[stable_id] = contact

    sensors = SimpleNamespace(
        contact_tracker=tracker,
        sim_time=sim_time,
    )
    return SimpleNamespace(
        position={"x": 0.0, "y": 0.0, "z": 0.0},
        systems={"sensors": sensors},
        faction="UNN",
    )


def test_get_sensor_contacts_masks_ghost():
    """Integration: ghost contact through get_sensor_contacts has nulled fields."""
    ghost = ContactData(
        id="C001",
        position={"x": 50000.0, "y": 0.0, "z": 0.0},
        velocity={"x": 100.0, "y": 0.0, "z": 0.0},
        confidence=0.15,
        last_update=10.0,
        detection_method="ir",
        name="Secret Ship",
        classification="Corvette",
        contact_state="ghost",
    )

    ship = _make_ship_with_tracker({"C001": ghost})
    result = get_sensor_contacts(ship)

    assert result["count"] == 1
    c = result["contacts"][0]
    assert c["contact_state"] == "ghost"
    assert c["position"] is None
    assert c["velocity"] is None
    assert c["name"] is None
    assert c["classification"] is None


def test_get_sensor_contacts_masks_unconfirmed():
    """Integration: unconfirmed contact has no name and coarsened class."""
    unconf = ContactData(
        id="C002",
        position={"x": 10000.0, "y": 0.0, "z": 0.0},
        velocity={"x": 50.0, "y": 0.0, "z": 0.0},
        confidence=0.45,
        last_update=10.0,
        detection_method="ir",
        name="Should Be Nulled",
        classification="Destroyer",
        contact_state="unconfirmed",
    )

    ship = _make_ship_with_tracker({"C002": unconf})
    result = get_sensor_contacts(ship)

    assert result["count"] == 1
    c = result["contacts"][0]
    assert c["contact_state"] == "unconfirmed"
    assert c["name"] is None
    assert c["classification"] in ("Small", "Medium", "Large")


def test_get_sensor_contacts_confirmed_full_data():
    """Integration: confirmed contact passes through fully."""
    confirmed = ContactData(
        id="C003",
        position={"x": 1000.0, "y": 0.0, "z": 0.0},
        velocity={"x": 20.0, "y": 0.0, "z": 0.0},
        confidence=0.85,
        last_update=10.0,
        detection_method="ir",
        name="Rocinante",
        classification="Corvette",
        contact_state="confirmed",
    )

    ship = _make_ship_with_tracker({"C003": confirmed})
    result = get_sensor_contacts(ship)

    assert result["count"] == 1
    c = result["contacts"][0]
    assert c["contact_state"] == "confirmed"
    assert c["name"] == "Rocinante"
    assert c["classification"] == "Corvette"
    assert c["velocity"] is not None


# --- LOST state persistence in PassiveSensor ---

def test_passive_sensor_lost_state_transition():
    """Contact that fails re-detection should transition to LOST, not vanish."""
    from hybrid.systems.sensors.passive import PassiveSensor

    sensor = PassiveSensor({"range": 100000, "update_interval": 1})

    # Seed an existing contact as if previously detected
    existing = ContactData(
        id="target_1",
        position={"x": 50000.0, "y": 0.0, "z": 0.0},
        velocity={"x": 0.0, "y": 0.0, "z": 0.0},
        confidence=0.7,
        last_update=100.0,
        detection_method="ir",
        contact_state="confirmed",
    )
    sensor.contacts["target_1"] = existing

    # Create an observer that can't see the target (target out of range)
    observer = SimpleNamespace(
        id="player",
        position={"x": 0.0, "y": 0.0, "z": 0.0},
        velocity={"x": 0.0, "y": 0.0, "z": 0.0},
        systems={},
    )

    # All ships list with target far away (beyond detection)
    far_target = SimpleNamespace(
        id="target_1",
        position={"x": 9999999.0, "y": 0.0, "z": 0.0},
        velocity={"x": 0.0, "y": 0.0, "z": 0.0},
        systems={},
        mass=50000,
        class_type="Corvette",
        faction="MCRN",
        name="Tachi",
        thrust=0.0,
        heading={"x": 1.0, "y": 0.0, "z": 0.0},
    )

    # Run update — target should NOT be detected, existing contact -> LOST
    sensor.update(
        current_tick=20,
        dt=0.25,
        observer_ship=observer,
        all_ships=[observer, far_target],
        sim_time=105.0,
    )

    assert "target_1" in sensor.contacts
    lost_contact = sensor.contacts["target_1"]
    assert lost_contact.contact_state == "lost"
    assert lost_contact.lost_since == 105.0
    assert lost_contact.last_known_position == {"x": 50000.0, "y": 0.0, "z": 0.0}


def test_passive_sensor_lost_reacquisition():
    """A LOST contact that is re-detected should clear LOST state."""
    from hybrid.systems.sensors.passive import PassiveSensor

    sensor = PassiveSensor({"range": 500000, "update_interval": 1})

    # Seed a LOST contact
    lost = ContactData(
        id="target_1",
        position={"x": 50000.0, "y": 0.0, "z": 0.0},
        velocity={"x": 0.0, "y": 0.0, "z": 0.0},
        confidence=0.3,
        last_update=100.0,
        detection_method="ir",
        contact_state="lost",
        lost_since=95.0,
        last_known_position={"x": 50000.0, "y": 0.0, "z": 0.0},
    )
    sensor.contacts["target_1"] = lost

    observer = SimpleNamespace(
        id="player",
        position={"x": 0.0, "y": 0.0, "z": 0.0},
        velocity={"x": 0.0, "y": 0.0, "z": 0.0},
        systems={},
    )

    # Target is now close and bright (high thrust = high IR)
    close_target = SimpleNamespace(
        id="target_1",
        position={"x": 10000.0, "y": 0.0, "z": 0.0},
        velocity={"x": 100.0, "y": 0.0, "z": 0.0},
        systems={},
        mass=50000,
        class_type="Corvette",
        faction="MCRN",
        name="Tachi",
        thrust=500000.0,  # High thrust = huge IR signature
        heading={"x": 1.0, "y": 0.0, "z": 0.0},
    )

    sensor.update(
        current_tick=20,
        dt=0.25,
        observer_ship=observer,
        all_ships=[observer, close_target],
        sim_time=110.0,
    )

    assert "target_1" in sensor.contacts
    reacquired = sensor.contacts["target_1"]
    # Should no longer be LOST
    assert reacquired.contact_state != "lost"
    assert reacquired.lost_since is None
    assert reacquired.last_known_position is None


def test_passive_sensor_lost_expiry():
    """A LOST contact should be removed after LOST_PERSISTENCE_SECONDS."""
    from hybrid.systems.sensors.passive import PassiveSensor

    sensor = PassiveSensor({"range": 100000, "update_interval": 1})

    # Seed a contact that has been LOST for longer than 30s
    old_lost = ContactData(
        id="target_1",
        position={"x": 50000.0, "y": 0.0, "z": 0.0},
        velocity={"x": 0.0, "y": 0.0, "z": 0.0},
        confidence=0.05,
        last_update=50.0,
        detection_method="ir",
        contact_state="lost",
        lost_since=60.0,  # Lost at t=60
        last_known_position={"x": 50000.0, "y": 0.0, "z": 0.0},
    )
    sensor.contacts["target_1"] = old_lost

    observer = SimpleNamespace(
        id="player",
        position={"x": 0.0, "y": 0.0, "z": 0.0},
        velocity={"x": 0.0, "y": 0.0, "z": 0.0},
        systems={},
    )

    # No ships to detect — target is gone
    sensor.update(
        current_tick=200,
        dt=0.25,
        observer_ship=observer,
        all_ships=[observer],
        sim_time=95.0,  # 35s after lost_since=60 > 30s threshold
    )

    # Contact should be removed
    assert "target_1" not in sensor.contacts


def test_contact_data_lost_fields_default():
    """ContactData lost_since and last_known_position default to None."""
    contact = ContactData(
        id="C001",
        position={"x": 0.0, "y": 0.0, "z": 0.0},
        velocity={"x": 0.0, "y": 0.0, "z": 0.0},
        confidence=0.8,
        last_update=1.0,
        detection_method="ir",
    )
    assert contact.lost_since is None
    assert contact.last_known_position is None
