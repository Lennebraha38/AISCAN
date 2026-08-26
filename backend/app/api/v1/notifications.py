"""SSE (Server-Sent Events) bildirim akisi — canli analiz/karar bildirimleri.

Demo tek-islem oldugu icin basit in-memory broadcast kullanir.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from ...core.deps import get_current_user
from ...models import User

router = APIRouter(prefix="/v1/notifications", tags=["system"])

# In-memory broadcast queue (demo tek-process)
_queues: list[asyncio.Queue] = []
_MAX_QUEUES = 32


async def broadcast(event: dict) -> None:
    """Yeni bir bildirimi tum bagli istemcilere gonderir."""
    dead: list[asyncio.Queue] = []
    for q in _queues:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        _queues.remove(q)


async def _event_stream(queue: asyncio.Queue) -> AsyncGenerator[str, None]:
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30)
                data = json.dumps(event, ensure_ascii=False, default=str)
                yield f"data: {data}\n\n"
            except asyncio.TimeoutError:
                # keepalive
                yield f": keepalive {int(time.time())}\n\n"
    except asyncio.CancelledError:
        pass
    finally:
        if queue in _queues:
            _queues.remove(queue)


@router.get("")
async def stream(
    request: Request,
    user: User = Depends(get_current_user),
):
    """SSE bildirim kanali — tum analiz ve karar olaylarini canli olarak aktarir."""
    if len(_queues) >= _MAX_QUEUES:
        from fastapi import HTTPException
        raise HTTPException(429, "Cok fazla baglanti acildi; daha sonra tekrar deneyin")

    queue: asyncio.Queue = asyncio.Queue(maxsize=64)
    _queues.append(queue)

    async def gen():
        # Ilk olarak baglanti basari mesaji gonder
        hello = json.dumps({"type": "connected", "user": user.role, "ts": int(time.time())})
        yield f"data: {hello}\n\n"
        async for chunk in _event_stream(queue):
            yield chunk

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
