import asyncio
from typing import Dict, Coroutine, Any
import structlog


class CallManager:
    """Manage lifecycle of active bot call tasks."""

    def __init__(self):
        self._active_calls: Dict[str, asyncio.Task] = {}
        self._logger = structlog.get_logger()

    def start_call(self, call_id: str, bot_coro: Coroutine, **log_fields: Any) -> asyncio.Task:
        """Create and track a bot task for a call."""
        task = asyncio.create_task(bot_coro)
        self._active_calls[call_id] = task
        self._logger.info("Bot started for call", call_id=call_id, **log_fields)
        return task

    def end_call(self, call_id: str, **log_fields: Any) -> None:
        """Cancel and remove a running bot task if it exists."""
        task = self._active_calls.pop(call_id, None)
        if task:
            task.cancel()
            self._logger.info("Bot task cancelled", call_id=call_id, **log_fields)

    def end_all(self) -> None:
        """Cancel all running bot tasks."""
        for call_id in list(self._active_calls.keys()):
            self.end_call(call_id)
