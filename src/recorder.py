"""RTSP video capture via VLC + FFmpeg remux for CamKinescope.

VLC captures the RTSP stream to .ts (transport stream) file.
FFmpeg remuxes .ts to .mp4 (stream copy, no re-encoding).
This two-step approach is needed because FFmpeg cannot connect
to this camera's non-standard RTSP implementation directly.
"""

import os
import signal
import subprocess
from datetime import datetime
from pathlib import Path

import yaml

from logger_setup import setup_logger

logger = setup_logger(__name__)


def load_config(config_path: str) -> dict:
    path = Path(config_path)
    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    logger.info("Config loaded from %s", path.resolve())
    return config


def record_segment(config: dict, duration_override: int = None) -> str:
    """Record a video segment: VLC captures RTSP to .ts, FFmpeg remuxes to .mp4.

    Returns:
        Full path to the created MP4 file on success, or None on failure.
    """
    rtsp_url = config["camera"]["rtsp_url"]
    duration = duration_override or config["recording"]["duration_seconds"]
    output_dir = Path(config["recording"]["output_dir"])
    vlc_path = config.get("vlc", {}).get("path", "C:\\Program Files\\VideoLAN\\VLC\\vlc.exe")
    ffmpeg_path = config.get("ffmpeg", {}).get("path", "ffmpeg")

    output_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    base_name = now.strftime("%d.%m.%Y %H_%M")
    ts_path = output_dir / (base_name + ".ts")
    mp4_path = output_dir / (base_name + ".mp4")

    # Step 1: VLC captures RTSP → .ts
    vlc_cmd = [
        vlc_path,
        "-I", "dummy",
        "--play-and-exit",
        rtsp_url,
        f"--sout=#file{{dst={ts_path}}}",
    ]

    logger.info(
        "VLC recording started: url=%s duration=%ds output=%s",
        rtsp_url, duration, ts_path,
    )

    try:
        process = subprocess.Popen(
            vlc_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # Wait for the recording duration, then terminate VLC
        process.wait(timeout=duration)
        logger.warning("VLC exited early (code %d) before duration elapsed", process.returncode)
    except subprocess.TimeoutExpired:
        # Expected: VLC records until we kill it
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        logger.info("VLC recording stopped after %ds", duration)

    # Check .ts file was created
    if not ts_path.exists() or ts_path.stat().st_size == 0:
        logger.error("VLC produced no output file: %s", ts_path)
        if ts_path.exists():
            ts_path.unlink()
        return None

    ts_size_mb = ts_path.stat().st_size / (1024 * 1024)
    logger.info("VLC recording saved: %s (%.1f MB)", ts_path, ts_size_mb)

    # Step 2: FFmpeg remuxes .ts → .mp4 (stream copy, no re-encoding)
    remux_cmd = [
        ffmpeg_path, "-y",
        "-i", str(ts_path),
        "-c", "copy",
        "-an",
        "-movflags", "+faststart",
        str(mp4_path),
    ]

    logger.info("Remuxing to MP4: %s → %s", ts_path.name, mp4_path.name)

    remux_timeout = 60  # remux is near-instant

    try:
        result = subprocess.run(remux_cmd, capture_output=True, text=True, timeout=remux_timeout)
    except subprocess.TimeoutExpired:
        logger.error("Remux timed out after %ds", remux_timeout)
        return str(ts_path)

    if result.returncode != 0:
        logger.error("Remux failed (exit code %d): %s", result.returncode,
                      result.stderr[-500:] if result.stderr else "no stderr")
        return str(ts_path)

    # Remove .ts after successful remux
    ts_path.unlink()
    mp4_size_mb = mp4_path.stat().st_size / (1024 * 1024)
    logger.info("Remux complete: %s (%.1f MB)", mp4_path, mp4_size_mb)

    return str(mp4_path)


def get_kinescope_title(filepath: str) -> str:
    stem = Path(filepath).stem
    title = stem.replace("_", ":")
    return title


def cleanup_old_recordings(config: dict, skip_files: set = None) -> None:
    """Delete oldest recordings when file count exceeds max_local_files.

    Args:
        config: Application config dict.
        skip_files: Set of absolute file path strings to skip (e.g. files being uploaded).
    """
    output_dir = Path(config["recording"]["output_dir"])
    max_files = config["recording"]["max_local_files"]

    if not output_dir.exists():
        return

    # Clean both .mp4 and .ts files
    media_files = sorted(
        list(output_dir.glob("*.mp4")) + list(output_dir.glob("*.ts")),
        key=lambda p: p.stat().st_mtime,
    )

    files_to_delete = len(media_files) - max_files
    if files_to_delete <= 0:
        return

    skip = skip_files or set()
    deleted = 0
    for old_file in media_files[:files_to_delete]:
        if str(old_file.resolve()) in skip or str(old_file) in skip:
            logger.info("Skipping file in use: %s", old_file)
            continue
        try:
            old_file.unlink()
            deleted += 1
            logger.info("Deleted old recording: %s", old_file)
        except PermissionError:
            logger.warning("Cannot delete (file in use): %s", old_file)

    if deleted:
        logger.info("Cleanup complete: removed %d file(s)", deleted)


if __name__ == "__main__":
    config_path = Path(__file__).parent.parent / "config.yaml"
    cfg = load_config(str(config_path))

    result_path = record_segment(cfg, duration_override=30)
    if result_path:
        title = get_kinescope_title(result_path)
        print(f"Recorded: {result_path}")
        print(f"Kinescope title: {title}")
    else:
        print("Recording failed. Check logs for details.")
