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
            response = json.loads(message) # Parse the JSON message
            current_time = time.time()

            # Handle partial transcript
            if "partial" in response:
                partial_text = response.get("partial", "").strip() # Get partial text, strip whitespace

                # Check if partial transcript has changed
                if partial_text != self.last_partial_transcript:
                    self.last_partial_transcript = partial_text
                    self.last_partial_timestamp = current_time
                    self.partial_unchanged_duration = 0.0

                    if partial_text: # Log non-empty partials
                        logging.info(f"{self.session_id}Partial transcript: \"{partial_text}\"")
                    if self.on_partial_transcript and partial_text: # Trigger callback if set and text exists
                        await self.on_partial_transcript(partial_text)
                else:
                    # Partial hasn't changed, update duration
                    self.partial_unchanged_duration = current_time - self.last_partial_timestamp

            # Handle final transcript
            if "text" in response:
                final_text = response.get("text", "").strip() # Get final text, strip whitespace
                if final_text: # Process only if final text is non-empty
                    self.last_final_transcript = final_text
                    # Reset partial tracking since we got a final
                    self.last_partial_timestamp = 0.0
                    self.partial_unchanged_duration = 0.0

                    # It's common for final results to also update the last partial,
                    # ensuring consistency if no further partials arrive.
                    if final_text != self.last_partial_transcript:
                        self.last_partial_transcript = final_text

                    logging.info(f"{self.session_id}Final transcript: \"{final_text}\"")
                    if self.on_final_transcript: # Trigger callback if set
                        # Run final transcript callback as a separate task to avoid blocking
                        # the message handling loop if the callback is slow.
                        asyncio.create_task(self.on_final_transcript(final_text))

            return True # Message processed successfully

        except json.JSONDecodeError:
            logging.error(f"{self.session_id}Invalid JSON response from STT: {message[:100]}...")
            return False
        except Exception as e:
            logging.error(f"{self.session_id}Error processing STT transcript message: {str(e)}", exc_info=True)
            return False

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

    def get_final_transcript(self) -> str:
        """
        Retrieves the most definitive transcript available.

        It prioritizes the last final transcript. If no final transcript is
        available, it falls back to the last partial transcript. If neither is
        available, it returns an empty string.

        Returns:
            The most definitive transcript string.
        """
        if self.last_final_transcript:
            if self.debug_logging_enabled():
                 logging.debug(f"{self.session_id}Returning final transcript: \"{self.last_final_transcript[:70]}...\"")
            return self.last_final_transcript
        elif self.last_partial_transcript:
            if self.debug_logging_enabled():
                logging.debug(f"{self.session_id}No final transcript, returning partial: \"{self.last_partial_transcript[:70]}...\"")
            return self.last_partial_transcript
        else:
            if self.debug_logging_enabled():
                logging.debug(f"{self.session_id}No transcript (final or partial) available, returning empty string.")
            return ""

    def debug_logging_enabled(self) -> bool:
        """Helper to check if DEBUG level logging is enabled for the current logger."""
        # This assumes a global logger. If TranscriptHandler uses a dedicated logger,
        # this method should refer to that specific logger instance.
        return logging.getLogger().isEnabledFor(logging.DEBUG)
