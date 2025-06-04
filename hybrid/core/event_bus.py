# hybrid/core/event_bus.py
class EventBus:
    _instance = None

    @staticmethod
    def get_instance():
        if EventBus._instance is None:
            EventBus._instance = EventBus()
        return EventBus._instance

    def __init__(self):
        self.listeners = {}

    def subscribe(self, event_name, callback):
        self.listeners.setdefault(event_name, []).append(callback)

    def publish(self, event_name, payload=None, source=None):
        """Publish an event to all subscribers.

        Older callbacks expect a single ``payload`` argument while some newer
        calls include a ``source`` parameter.  To remain backward compatible we
        try calling the subscriber with just the payload first and fall back to
        passing the optional source if required.
        """
        for callback in self.listeners.get(event_name, []):
            try:
                callback(payload)
            except TypeError:
                callback(payload, source)
