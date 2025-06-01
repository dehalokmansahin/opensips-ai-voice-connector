import asyncio
import json
import logging
import time
from typing import Optional, Callable, Awaitable

class TranscriptHandler:
    """
    Manages STT (Speech-to-Text) transcript data.

    This class stores the last partial and final transcripts received from the
    STT service. It provides callbacks (`on_partial_transcript`, `on_final_transcript`)
    that can be set by other components to react to transcript updates.
    It also offers a method to retrieve the most definitive available transcript.
    """

    def __init__(self, session_id: str = ""):
        """
        Initializes the TranscriptHandler.

        Args:
            session_id: An identifier for the current session, used for contextual logging.
        """
        self.last_partial_transcript: str = ""
        self.last_final_transcript: str = ""
        self.last_partial_timestamp: float = 0.0  # When the last partial was received
        self.partial_unchanged_duration: float = 0.0  # How long the partial has been unchanged
        # Callbacks for transcript updates:
        self.on_partial_transcript: Optional[Callable[[str], Awaitable[None]]] = None
        self.on_final_transcript: Optional[Callable[[str], Awaitable[None]]] = None
        self.session_id: str = session_id
        logging.info(f"{self.session_id}TranscriptHandler initialized.")

    async def handle_message(self, message: str) -> bool:
        """
        Processes an incoming message (JSON string) from the STT service.

        Parses the message, updates `last_partial_transcript` and/or
        `last_final_transcript`, and triggers the respective callbacks if set.

        Args:
            message: The JSON message string from the STT service.
                     Expected to contain 'partial' or 'text' (final) fields.

        Returns:
            True if the message was successfully processed, False otherwise
            (e.g., JSON decode error).
        """
        try:
            response = json.loads(message)
            current_time = time.time()

            # Delegate partial and final processing to helpers
            await self._process_partial(response, current_time)
            await self._process_final(response)

            return True

        except json.JSONDecodeError:
            logging.error(f"{self.session_id}Invalid JSON response from STT: {message[:100]}...")
            return False
        except Exception as e:
            logging.error(f"{self.session_id}Error processing STT transcript message: {str(e)}", exc_info=True)
            return False

    async def _process_partial(self, response: dict, current_time: float) -> None:
        """Handle partial transcript updates and callbacks."""
        partial = response.get("partial", "").strip()
        if partial != self.last_partial_transcript:
            self.last_partial_transcript = partial
            self.last_partial_timestamp = current_time
            self.partial_unchanged_duration = 0.0
            if partial:
                logging.info(f"{self.session_id}Partial transcript: \"{partial}\"")
                if self.on_partial_transcript:
                    await self.on_partial_transcript(partial)
        else:
            self.partial_unchanged_duration = current_time - self.last_partial_timestamp

    async def _process_final(self, response: dict) -> None:
        """Handle final transcript updates and callbacks."""
        final = response.get("text", "").strip()
        if not final:
            return
        self.last_final_transcript = final
        # Reset partial tracking
        self.last_partial_timestamp = 0.0
        self.partial_unchanged_duration = 0.0
        if final != self.last_partial_transcript:
            self.last_partial_transcript = final
        logging.info(f"{self.session_id}Final transcript: \"{final}\"")
        if self.on_final_transcript:
            asyncio.create_task(self.on_final_transcript(final))

    def has_stale_partial(self, max_unchanged_seconds: float = 2.0) -> bool:
        """
        Checks if the current partial transcript has been unchanged for too long.

        Args:
            max_unchanged_seconds: Maximum time (in seconds) a partial can remain unchanged.

        Returns:
            True if there's a stale partial that should be promoted to final.
        """
        if not self.last_partial_transcript or self.last_partial_timestamp == 0.0:
            return False

        return self.partial_unchanged_duration >= max_unchanged_seconds

    def clear_transcripts(self) -> None:
        """Clears all transcript data and resets timing."""
        self.last_partial_transcript = ""
        self.last_final_transcript = ""
        self.last_partial_timestamp = 0.0
        self.partial_unchanged_duration = 0.0

    def _select_best_transcript(self) -> str:
        """Choose the most definitive transcript: final over partial, else empty."""
        if self.last_final_transcript:
            return self.last_final_transcript
        if self.last_partial_transcript:
            return self.last_partial_transcript
        return ""

    def get_final_transcript(self) -> str:
        """
        Retrieves the most definitive transcript available.

        It prioritizes the last final transcript. If no final transcript is
        available, it falls back to the last partial transcript. If neither is
        available, it returns an empty string.

        Returns:
            The most definitive transcript string.
        """
        transcript = self._select_best_transcript()
        if self.debug_logging_enabled():
            if transcript == self.last_final_transcript:
                logging.debug(f"{self.session_id}Returning final transcript: \"{transcript[:70]}...\"")
            elif transcript == self.last_partial_transcript:
                logging.debug(f"{self.session_id}No final transcript, returning partial: \"{transcript[:70]}...\"")
            else:
                logging.debug(f"{self.session_id}No transcript (final or partial) available, returning empty string.")
        return transcript

    def debug_logging_enabled(self) -> bool:
        """Helper to check if DEBUG level logging is enabled for the current logger."""
        # This assumes a global logger. If TranscriptHandler uses a dedicated logger,
        # this method should refer to that specific logger instance.
        return logging.getLogger().isEnabledFor(logging.DEBUG)
