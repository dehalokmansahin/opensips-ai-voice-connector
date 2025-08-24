#!/usr/bin/env python3
"""
Prometheus metrics for OpenSIPS AI Voice Connector
"""

from typing import Optional
from prometheus_client import Counter, Gauge, start_http_server


# RTP ingest metrics (label by call_id)
RTP_PACKETS_RECEIVED = Counter(
    "rtp_packets_received_total",
    "Total RTP packets received",
    labelnames=("call_id",),
)

RTP_FRAMES_ENQUEUED = Counter(
    "rtp_frames_enqueued_total",
    "Total frames enqueued from RTP receiver",
    labelnames=("call_id",),
)

RTP_FRAMES_PROCESSED = Counter(
    "rtp_frames_processed_total",
    "Total frames processed from RTP queue",
    labelnames=("call_id",),
)

RTP_INPUT_QUEUE_DEPTH = Gauge(
    "rtp_input_queue_depth",
    "Current depth of RTP input queue",
    labelnames=("call_id",),
)


_metrics_server_started: bool = False


def start_metrics_server(port: int = 9000) -> None:
    global _metrics_server_started
    if _metrics_server_started:
        return
    start_http_server(port)
    _metrics_server_started = True


