# hybrid/event_bus.py
"""
Event bus implementation for the ship simulation.
Provides a centralized event publishing and subscription mechanism.
"""

import logging

logger = logging.getLogger(__name__)

class EventBus:
    """Simple event bus for loose coupling between systems."""

    def __init__(self):
        """Initialize an empty event bus."""
        self.subscribers = {}
        self.debug_mode = False

    def subscribe(self, event_type, callback):
        """Subscribe a callback to an event type."""
        if event_type not in self.subscribers:
            self.subscribers[event_type] = []
        self.subscribers[event_type].append(callback)
        return callback

    def unsubscribe(self, event_type, callback):
        """Unsubscribe a callback from an event type."""
        if event_type in self.subscribers and callback in self.subscribers[event_type]:
            self.subscribers[event_type].remove(callback)
            return True
        return False

    def publish(self, event_type, data=None, source=None):
        """Publish an event to all subscribers.

        Args:
            event_type (str): The type of event being published.
            data (any, optional): Data associated with the event.
            source (str, optional): Source of the event (e.g., system name).

        Returns:
            int: Number of subscribers that handled the event.
        """
        event_data = {"type": event_type, "data": data, "source": source}

        if self.debug_mode:
            logger.debug(f"Event published: {event_type} from {source or 'unknown'}")

        count = 0
        if event_type in self.subscribers:
            for callback in list(self.subscribers[event_type]):
                try:
                    callback(event_data)
                    count += 1
                except Exception as e:
                    logger.error(f"Error in event handler for {event_type}: {e}")
        return count

    def clear(self):
        """Remove all subscriptions."""
        self.subscribers = {}

    def enable_debug(self, enabled=True):
        """Enable or disable debug logging for events."""
        self.debug_mode = enabled
