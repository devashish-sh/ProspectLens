# backend/services/event_bus.py
# ProspectLens — Internal Pub/Sub Event Bus

import asyncio
import inspect
from typing import Callable, Dict, List, Any

# Standard Event Constant Types
LEAD_ADDED = "Lead Added"
LEAD_UPDATED = "Lead Updated"
LEAD_ENRICHED = "Lead Enriched"
LEAD_APPROVED = "Lead Approved"
LEAD_DELETED = "Lead Deleted"
LEAD_MOVED = "Lead Moved"
COLLECTION_STARTED = "Collection Started"
COLLECTION_FINISHED = "Collection Finished"

class EventBus:
    """
    Centralized, thread-safe Pub/Sub event bus.
    Enables decoupled communication between backend subsystems.
    Future modules can subscribe to events without modifying the source code.
    """
    _listeners: Dict[str, List[Callable[..., Any]]] = {}
    _lock = asyncio.Lock()

    @classmethod
    def subscribe(cls, event_type: str, callback: Callable[..., Any]):
        """
        Subscribe a callback function to a specific event type.
        """
        if event_type not in cls._listeners:
            cls._listeners[event_type] = []
        if callback not in cls._listeners[event_type]:
            cls._listeners[event_type].append(callback)
            print(f"[EventBus] Subscribed callback '{callback.__name__}' to event '{event_type}'")

    @classmethod
    def unsubscribe(cls, event_type: str, callback: Callable[..., Any]):
        """
        Unsubscribe a callback function from a specific event type.
        """
        if event_type in cls._listeners and callback in cls._listeners[event_type]:
            cls._listeners[event_type].remove(callback)
            print(f"[EventBus] Unsubscribed callback '{callback.__name__}' from event '{event_type}'")

    @classmethod
    def publish(cls, event_type: str, *args, **kwargs):
        """
        Publish an event synchronously to all registered listeners.
        Spawns async tasks for coroutine listeners to keep execution non-blocking.
        """
        if event_type not in cls._listeners:
            return

        listeners = list(cls._listeners[event_type])
        for callback in listeners:
            try:
                if inspect.iscoroutinefunction(callback):
                    # Safely schedule coroutine callbacks on the event loop
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                    
                    if loop.is_running():
                        loop.create_task(callback(*args, **kwargs))
                    else:
                        loop.run_until_complete(callback(*args, **kwargs))
                else:
                    # Synchronous callback
                    callback(*args, **kwargs)
            except Exception as e:
                print(f"[EventBus] Error executing listener callback for event '{event_type}': {e}")
