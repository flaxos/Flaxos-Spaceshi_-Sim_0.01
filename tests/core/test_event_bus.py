# tests/core/test_event_bus.py

import pytest
from hybrid.core.event_bus import EventBus


def test_event_bus_publish_subscribe():
    eb = EventBus.get_instance()
    events = []

    def callback(payload):
        events.append(payload)

    eb.subscribe("test_event", callback)
    eb.publish("test_event", {"data": 123})
    assert events == [{"data": 123}]
