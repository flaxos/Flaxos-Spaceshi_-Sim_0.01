# hybrid/event_bus.py
"""
Event bus implementation for inter-system communication.
Systems can publish events and subscribe to events from other systems.
"""
# hybrid/event_bus.py
"""
Event bus implementation for the ship simulation.
Provides a centralized event publishing and subscription mechanism.
"""

class EventBus:
    """Event bus for publishing and subscribing to events"""
    
    def __init__(self):
        """Initialize the event bus"""
        self.subscribers = {}
    
    def subscribe(self, event_type, callback):
        """
        Subscribe to an event type
        
        Args:
            event_type (str): Type of event to subscribe to
            callback (function): Function to call when event occurs
            
        Returns:
            function: The callback function
        """
        if event_type not in self.subscribers:
            self.subscribers[event_type] = []
        self.subscribers[event_type].append(callback)
        return callback
    
    def unsubscribe(self, event_type, callback):
        """
        Unsubscribe from an event type
        
        Args:
            event_type (str): Type of event to unsubscribe from
            callback (function): Callback function to remove
            
        Returns:
            bool: True if unsubscribed, False if not found
        """
        if event_type in self.subscribers:
            if callback in self.subscribers[event_type]:
                self.subscribers[event_type].remove(callback)
                return True
        return False
    
    def publish(self, event_type, event_data=None):
        """
        Publish an event
        
        Args:
            event_type (str): Type of event to publish
            event_data (dict): Data associated with the event
            
        Returns:
            int: Number of subscribers that received the event
        """
        if event_data is None:
            event_data = {}
            
        # Always include the event type in the data
        if "event_type" not in event_data:
            event_data["event_type"] = event_type
            
        # Dispatch to subscribers
        count = 0
        if event_type in self.subscribers:
            for callback in self.subscribers[event_type]:
                try:
                    callback(event_data)
                    count += 1
                except Exception as e:
                    print(f"Error in event handler for {event_type}: {e}")
        return count
    
    def clear(self):
        """Clear all event subscriptions"""
        self.subscribers = {}
import logging

logger = logging.getLogger(__name__)

class EventBus:
    """
    Simple event bus for loose coupling between systems.
    Systems can publish events and subscribe to events from other systems.
    """
    
    def __init__(self):
        """Initialize an empty event bus"""
        self.subscribers = {}
        self.debug_mode = False
        
    def subscribe(self, event_type, callback):
        """
        Subscribe to an event type
        
        Args:
            event_type (str): The event type to subscribe to
            callback (callable): Function to call when event occurs
        """
        if event_type not in self.subscribers:
            self.subscribers[event_type] = []
        self.subscribers[event_type].append(callback)
        
    def publish(self, event_type, data=None, source=None):
        """
        Publish an event to all subscribers
        
        Args:
            event_type (str): The type of event being published
            data (any, optional): Data associated with the event
            source (str, optional): Source of the event (e.g., system name)
        """
        event_data = {
            "type": event_type,
            "data": data,
            "source": source
        }
        
        if self.debug_mode:
            logger.debug(f"Event published: {event_type} from {source or 'unknown'}")
            
        if event_type in self.subscribers:
            for callback in self.subscribers[event_type]:
                try:
                    callback(event_data)
                except Exception as e:
                    logger.error(f"Error in event handler for {event_type}: {e}")
    
    def enable_debug(self, enabled=True):
        """Enable or disable debug logging for events"""
        self.debug_mode = enabled
