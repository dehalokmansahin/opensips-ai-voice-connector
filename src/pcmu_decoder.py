import numpy as np
import logging

class PCMUDecoder:
    @staticmethod
    def decode(ulaw_bytes: bytes) -> np.ndarray:
        logging.debug(f"Decoding {len(ulaw_bytes)} bytes of u-law data")
        MULAW_BIAS = 33
        ulaw_bytes = np.frombuffer(ulaw_bytes, dtype=np.uint8)
        ulaw_bytes = ~ulaw_bytes

        sign = ulaw_bytes & 0x80
        exponent = (ulaw_bytes & 0x70) >> 4
        mantissa = (ulaw_bytes & 0x0F) + MULAW_BIAS

        sample = ((mantissa << (exponent + 3)) - MULAW_BIAS)
        pcm16 = np.where(sign != 0, -sample, sample).astype(np.int16)
        logging.debug(f"Decoded PCM16 samples: {pcm16[:10]}...")
        return pcm16
