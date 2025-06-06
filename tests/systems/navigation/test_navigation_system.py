import types
from hybrid.core.event_bus import EventBus
from hybrid.systems.navigation.navigation import NavigationSystem


def test_navigation_tick_publishes_event():
    eb = EventBus.get_instance()
    eb.listeners.clear()
    events = []
    eb.subscribe("navigation_tick", lambda payload: events.append(payload))

    nav = NavigationSystem({})
    dummy_ship = types.SimpleNamespace(id="ship1")
    nav.tick(0.5, dummy_ship, eb)

    assert events == [{"dt": 0.5, "ship_id": "ship1"}]
