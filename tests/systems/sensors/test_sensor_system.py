import types
from hybrid.core.event_bus import EventBus
from hybrid.systems.sensors.sensor_system import SensorSystem


def test_sensor_tick_publishes_event():
    eb = EventBus.get_instance()
    eb.listeners.clear()
    events = []
    eb.subscribe("sensor_tick", lambda payload: events.append(payload))

    sensors = SensorSystem({})
    dummy_ship = types.SimpleNamespace(id="ship1")
    sensors.tick(0.25, dummy_ship, eb)

    assert events == [{"dt": 0.25, "ship_id": "ship1", "contacts": 0}]
