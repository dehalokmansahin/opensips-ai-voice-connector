from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

class STTEngineBase(ABC):
    """
    Abstract Base Class for Speech-to-Text (STT) engines.

    Defines the common interface that all STT engine implementations should adhere to.
    This allows for interchangeable STT backends within the speech processing system.
    """

    @abstractmethod
    async def connect(self) -> bool:
        """
        Establishes a connection to the STT service.

        Returns:
            bool: True if connection was successful, False otherwise.
        """
        pass

    @abstractmethod
    async def send_config(self, config: Dict[str, Any]) -> bool:
        """
        Sends configuration parameters to the STT service.
        This might include sample rate, number of channels, language model, etc.

        Args:
            config (Dict[str, Any]): A dictionary containing configuration parameters.
                                     The specific structure depends on the STT engine.

        Returns:
            bool: True if configuration was sent and accepted successfully, False otherwise.
        """
        pass

    @abstractmethod
    async def send_audio(self, audio_bytes: bytes) -> bool:
        """
        Sends a chunk of audio data to the STT service for transcription.

        Args:
            audio_bytes (bytes): The raw audio data chunk.

        Returns:
            bool: True if audio was sent successfully, False otherwise.
        """
        pass

    @abstractmethod
    async def send_eof(self) -> bool:
        """
        Signals the end of the audio stream to the STT service.
        This is often used to finalize the transcription process for the current utterance.

        Returns:
            bool: True if EOF was sent successfully, False otherwise.
        """
        pass

    @abstractmethod
    async def receive_result(self) -> Optional[str]:
        """
        Receives transcription results (partial or final) from the STT service.
        This method should handle blocking or non-blocking receives as appropriate
        for the underlying communication protocol (e.g., WebSockets).

        Returns:
            Optional[str]: A string containing the transcription result (e.g., JSON formatted),
                           or None if no result is available (e.g., timeout, connection issue).
        """
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """
        Closes the connection to the STT service and cleans up resources.
        """
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """
        Checks the current connection status to the STT service.

        Returns:
            bool: True if currently connected, False otherwise.
        """
        pass
