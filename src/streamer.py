"""VLC-based RTSP → RTMP live streaming for CamKinescope.

Captures the camera RTSP stream via VLC and pushes it to
Kinescope RTMP endpoint. Does NOT record to disk.
"""

import subprocess
from pathlib import Path

from logger_setup import setup_logger

logger = setup_logger(__name__)

# Global VLC streaming process
_stream_process: subprocess.Popen | None = None


def start_stream(config: dict) -> bool:
    """Start VLC: RTSP camera → RTMP Kinescope (no local recording).

    Returns True if the stream process started successfully.
    """
    global _stream_process

    if _stream_process is not None and _stream_process.poll() is None:
        logger.warning("Stream already running (pid %d)", _stream_process.pid)
        return False

    rtsp_url = config["camera"]["rtsp_url"]
    vlc_path = config.get("vlc", {}).get("path", "C:\\Program Files\\VideoLAN\\VLC\\vlc.exe")
    rtmp_url = config["streaming"]["rtmp_url"]
    stream_key = config["streaming"]["stream_key"]

    rtmp_dest = f"{rtmp_url}/{stream_key}"

    vlc_cmd = [
        vlc_path,
        "-I", "dummy",
        rtsp_url,
        f"--sout=#std{{access=rtmp,mux=flv,dst={rtmp_dest}}}",
        "--no-sout-all",
    ]

    logger.info("Starting stream: %s → %s", rtsp_url, rtmp_dest)

    try:
        _stream_process = subprocess.Popen(
            vlc_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logger.info("Stream started (pid %d)", _stream_process.pid)
        return True
    except Exception as exc:
        logger.error("Failed to start stream: %s", exc)
        _stream_process = None
        return False


def stop_stream() -> bool:
    """Stop the VLC streaming process.

    Returns True if the process was stopped.
    """
    global _stream_process

    if _stream_process is None or _stream_process.poll() is not None:
        logger.info("No active stream to stop")
        _stream_process = None
        return False

    pid = _stream_process.pid
    logger.info("Stopping stream (pid %d)", pid)

    _stream_process.terminate()
    try:
        _stream_process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        _stream_process.kill()
        _stream_process.wait(timeout=5)

    _stream_process = None
    logger.info("Stream stopped (pid %d)", pid)
    return True


def is_streaming() -> bool:
    """Check if the stream process is currently running."""
    return _stream_process is not None and _stream_process.poll() is None
