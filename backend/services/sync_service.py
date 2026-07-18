# backend/services/sync_service.py
# ProspectLens — Real-Time State Synchronization Broadcast Service

import asyncio
import json
from typing import Set
from fastapi.responses import StreamingResponse

class SyncBroadcaster:
    """
    Centralized event broadcast layer for real-time clients.
    Popup Home, Dashboard, and Data Capsules subscribe to this stream to receive instant updates.
    """
    _subscribers: Set[asyncio.Queue] = set()

    @classmethod
    def subscribe(cls) -> asyncio.Queue:
        """
        Subscribe a new client event listener queue.
        """
        queue = asyncio.Queue()
        cls._subscribers.add(queue)
        print(f"[Sync] Client subscribed. Active listeners: {len(cls._subscribers)}")
        return queue

    @classmethod
    def unsubscribe(cls, queue: asyncio.Queue):
        """
        Unsubscribe a client queue.
        """
        if queue in cls._subscribers:
            cls._subscribers.remove(queue)
            print(f"[Sync] Client unsubscribed. Active listeners: {len(cls._subscribers)}")

    @classmethod
    def broadcast(cls, event_type: str, data: dict = None):
        """
        Thread-safe broadcast method to publish events to all listening clients.
        Formats events as standard Server-Sent Events (SSE).
        """
        if not cls._subscribers:
            return

        payload = {
            "type": event_type,
            "data": data or {}
        }
        sse_event = f"data: {json.dumps(payload)}\n\n"

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # Thread-safe dispatch to all listening queues
        for queue in list(cls._subscribers):
            if loop.is_running():
                loop.call_soon_threadsafe(queue.put_nowait, sse_event)
            else:
                queue.put_nowait(sse_event)


async def sse_event_generator(queue: asyncio.Queue):
    """
    Asynchronous event loop yielding Server-Sent Events to the client stream.
    Automatically handles disconnect cleanups.
    """
    try:
        while True:
            # Wait for next broadcast event
            event = await queue.get()
            yield event
    except asyncio.CancelledError:
        # Client disconnected
        SyncBroadcaster.unsubscribe(queue)
        raise
