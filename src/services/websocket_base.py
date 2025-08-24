#!/usr/bin/env python3
"""
Shared WebSocket client mixin to reduce duplication across STT/LLM/TTS services.
"""

import asyncio
from typing import Optional


class WebsocketClientMixin:
    def __init__(self) -> None:
        self._websocket: Optional[object] = None
        self._listener_task: Optional[asyncio.Task] = None
        self._is_connected: bool = False

    async def start_ws_listener(self, listener_coro) -> None:
        if not self._listener_task:
            self._listener_task = asyncio.create_task(listener_coro)
            self._is_connected = True

    async def stop_ws(self) -> None:
        # Stop listener task
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            self._listener_task = None

        # Close websocket if available
        try:
            if self._websocket:
                await getattr(self._websocket, "close", (lambda: None))()
        except Exception:
            pass
        finally:
            self._websocket = None
            self._is_connected = False


