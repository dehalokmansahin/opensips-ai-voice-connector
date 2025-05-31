from abc import ABC, abstractmethod
from typing import AsyncGenerator

class TTSEngineBase(ABC):
    """
    Abstract Base Class for Text-to-Speech (TTS) engines.

    Defines the common interface that all TTS engine implementations should adhere to.
    This allows for interchangeable TTS backends within the speech processing system.
    """

    @abstractmethod
    async def connect(self) -> bool:
        """
        Establishes a connection to the TTS service.

        Returns:
            bool: True if connection was successful, False otherwise.
        """
        pass

    @abstractmethod
    async def synthesize_speech(
        self,
        text: str,
        voice: str,
        output_format: str = "pcm_16000" # Example: "pcm_16000", "mp3", "opus"
    ) -> AsyncGenerator[bytes, None]:
        """
        Synthesizes speech from the given text using the specified voice and format.

        This method should be an asynchronous generator, yielding audio chunks (bytes)
        as they become available from the TTS service. This allows for streaming playback.

        Args:
            text (str): The text to be synthesized.
            voice (str): Identifier for the desired voice. Specific to the TTS engine.
            output_format (str): The desired audio output format.
                                 Examples: "pcm_16000" (16kHz PCM), "mp3", "opus".
                                 The engine should try to match this or a compatible format.

        Yields:
            bytes: Chunks of audio data.

        Raises:
            Exception: If synthesis fails or connection issues occur.
        """
        # Ensure the generator is properly defined even in the ABC
        # This line is not strictly necessary for an abstract method but makes it clearer.
        # Actual implementations will provide the real generator logic.
        if False: # pragma: no cover
            yield b"" # This is to make it an async generator type
        pass


    @abstractmethod
    async def disconnect(self) -> None:
        """
        Closes the connection to the TTS service and cleans up resources.
        """
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """
        Checks the current connection status to the TTS service.

        Returns:
            bool: True if currently connected, False otherwise.
        """
        pass
