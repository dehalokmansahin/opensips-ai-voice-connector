import g711  # Assuming 'pip install g711' provides this
import numpy as np
import logging

class PCMUDecoder:
    @staticmethod
    def decode(ulaw_bytes: bytes) -> np.ndarray:
        """Decodes PCMU (G.711 u-law) bytes to 16-bit linear PCM samples
           represented as a float32 NumPy array using g711 library."""
        if not isinstance(ulaw_bytes, bytes):
            logging.error(f"PCMUDecoder received non-bytes input: {type(ulaw_bytes)}")
            # Return an empty float32 array on error
            return np.array([], dtype=np.float32)

        if len(ulaw_bytes) == 0:
            return np.array([], dtype=np.float32)

        try:
            # g711.decode_ulaw directly returns a float32 numpy array
            # representing linear PCM samples (typically in range -1.0 to 1.0)
            pcm_float32_samples = g711.decode_ulaw(ulaw_bytes)
            logging.debug(f"Decoded {len(ulaw_bytes)} u-law bytes to {len(pcm_float32_samples)} float32 PCM samples (g711)")
            return pcm_float32_samples

        except Exception as e:
            logging.error(f"Error decoding u-law with g711 library: {e}", exc_info=True)
            return np.array([], dtype=np.float32)
