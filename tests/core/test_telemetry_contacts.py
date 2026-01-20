from types import SimpleNamespace

from hybrid.systems.sensors.contact import ContactData
from hybrid.telemetry import get_sensor_contacts


def test_sensor_contacts_support_dataclass_entries():
    passive_contact = ContactData(
        id="C001",
        position={"x": 100.0, "y": 0.0, "z": 0.0},
        velocity={"x": 0.0, "y": 0.0, "z": 0.0},
        confidence=0.7,
        last_update=1.0,
        detection_method="passive",
    )
    active_contact = ContactData(
        id="C002",
        position={"x": 200.0, "y": 0.0, "z": 0.0},
        velocity={"x": 0.0, "y": 0.0, "z": 0.0},
        confidence=0.9,
        last_update=2.0,
        detection_method="active",
    )

    sensors = SimpleNamespace(
        passive=SimpleNamespace(contacts={"C001": passive_contact}),
        active=SimpleNamespace(contacts={"C002": active_contact}),
    )
    ship = SimpleNamespace(position={"x": 0.0, "y": 0.0, "z": 0.0}, systems={"sensors": sensors})

    result = get_sensor_contacts(ship)

    assert result["available"] is True
    assert result["count"] == 2
    contact_map = {contact["id"]: contact for contact in result["contacts"]}
    assert contact_map["C001"]["last_update"] == 1.0
    assert contact_map["C002"]["last_update"] == 2.0
