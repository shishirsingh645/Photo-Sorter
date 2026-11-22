"""GET /api/events: the job's events as Server-Sent Events, so the page subscribes instead of polling."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

router = APIRouter()

HEARTBEAT_SECONDS = 15  # a comment frame, so an idle proxy or a sleeping laptop does not kill the stream


@router.get("/api/events")
def get_events(request: Request) -> StreamingResponse:
    runner = request.app.state.runner
    if runner is None:
        raise HTTPException(503, "There is no job runner attached to this server, so there are no events to stream.")

    async def frames() -> AsyncIterator[str]:
        with runner.subscribe() as sub:  # __exit__ unsubscribes, including when the client vanishes
            yield ": connected\n\n"  # flushes the headers, so a client knows at once that it is attached
            beat = time.monotonic()
            # The loop ends when the runner drops this subscription (it stopped being drained), so the
            # response ends too and the browser's EventSource reconnects instead of sitting on a frozen bar.
            async for event in sub:
                if event is not None:
                    yield f"data: {event.model_dump_json()}\n\n"
                    beat = time.monotonic()
                elif time.monotonic() - beat >= HEARTBEAT_SECONDS:
                    beat = time.monotonic()
                    yield ": ping\n\n"
                elif await request.is_disconnected():
                    return

    return StreamingResponse(
        frames(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
