"""Rate-limited observer helper.

Provides a thin wrapper around an existing Pipecat `BaseObserver` instance and
ensures that `on_push_frame` is forwarded at most once every `min_interval` 
seconds. This is useful to avoid log floods when using verbose observers like
`DebugLogObserver` that may emit a message for every frame in a high-throughput
segment such as audio streaming.

Example
-------
>>> debug_observer = DebugLogObserver(frame_types=(TTSStartedFrame, TTSStoppedFrame))
>>> rate_limited = RateLimitedObserver(debug_observer, min_interval=1.0)
>>> task.add_observer(rate_limited)
"""

from pipecat.observers.base_observer import BaseObserver, FramePushed


class RateLimitedObserver(BaseObserver):
    """Observer that forwards events to a delegate observer at a limited rate.

    Parameters
    ----------
    delegate : BaseObserver
        The underlying observer that will handle the forwarded events.
    min_interval : float, default 1.0
        Minimum interval between two forwarded events in **seconds**. Events
        arriving sooner than this threshold are silently ignored.
    """

    def __init__(self, delegate: BaseObserver, min_interval: float = 1.0, **kwargs):
        super().__init__(**kwargs)
        self._delegate = delegate
        # Convert to nanoseconds because `FramePushed.timestamp` is in ns
        self._min_interval_ns = int(min_interval * 1_000_000_000)
        # Allow the first event immediately
        self._last_forward_ts: int = 0

    async def on_push_frame(self, data: FramePushed):  # noqa: D401
        """Forward the frame to the delegate if rate limit allows.

        If `data.timestamp` is `None` (shouldn’t normally happen), fall back to
        Python’s `time.monotonic_ns()` so we never raise `TypeError` and still
        get rate-limited behaviour.
        """
        import time

        ts = data.timestamp if data.timestamp is not None else time.monotonic_ns()

        if ts - self._last_forward_ts >= self._min_interval_ns:
            self._last_forward_ts = ts
            await self._delegate.on_push_frame(data)
