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
        self.global_listeners = []

    def subscribe(self, event_name, callback):
        self.listeners.setdefault(event_name, []).append(callback)

    def subscribe_all(self, callback):
        self.global_listeners.append(callback)

    def publish(self, event_name, payload):
        for callback in self.listeners.get(event_name, []):
            callback(payload)
        for callback in self.listeners.get("*", []):
            callback(payload)
        for callback in self.global_listeners:
            callback(event_name, payload)
