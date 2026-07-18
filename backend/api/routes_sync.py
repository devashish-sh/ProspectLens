# backend/api/routes_sync.py
# ProspectLens — Real-Time State Synchronization Endpoint

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from services.sync_service import SyncBroadcaster, sse_event_generator

router = APIRouter(tags=["Sync"])

@router.get("/sync/events")
async def get_sync_events(request: Request):
    """
    Establish a Server-Sent Events (SSE) stream for real-time synchronization.
    Popup Home, Dashboard, and Data Capsules listen to this stream to update state instantly.
    """
    queue = SyncBroadcaster.subscribe()
    
    # Return StreamingResponse with SSE headers
    return StreamingResponse(
        sse_event_generator(queue),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
