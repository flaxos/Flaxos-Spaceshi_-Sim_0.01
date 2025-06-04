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

    def publish(self, event_name, payload):
        for callback in self.listeners.get(event_name, []):
            callback(payload)
