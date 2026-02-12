"""RTSP video capture via FFmpeg for the CamKinescope project.

Records segments from an RTSP camera stream, generates Kinescope-friendly
titles, and manages local file retention.
"""

import subprocess
from datetime import datetime
from pathlib import Path

import yaml

from logger_setup import setup_logger

logger = setup_logger(__name__)


def load_config(config_path: str) -> dict:
    """Load and return the YAML configuration file.

    Args:
        config_path: Absolute or relative path to config.yaml.

    Returns:
        Parsed configuration dictionary.
    """
    path = Path(config_path)
    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    logger.info("Config loaded from %s", path.resolve())
    return config


def record_segment(config: dict, duration_override: int = None) -> str:
    """Record a single video segment from the RTSP camera via FFmpeg.

    Args:
        config: Parsed config dictionary (from config.yaml).
        duration_override: If provided, overrides duration_seconds from config.

    Returns:
        Full path to the created MP4 file on success, or None on failure.
    """
    rtsp_url = config["camera"]["rtsp_url"]
    rtsp_transport = config["camera"].get("rtsp_transport", "tcp")
    duration = duration_override or config["recording"]["duration_seconds"]
    output_dir = Path(config["recording"]["output_dir"])
    ffmpeg_path = config.get("ffmpeg", {}).get("path", "ffmpeg")

    # Create output directory if it doesn't exist
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate filename from current datetime: dd.mm.yyyy HH_MM.mp4
    now = datetime.now()
    filename = now.strftime("%d.%m.%Y %H_%M") + ".mp4"
    output_path = output_dir / filename

    cmd = [
        ffmpeg_path,
        "-y",
        "-rtsp_transport", rtsp_transport,
        "-i", rtsp_url,
        "-c", "copy",
        "-t", str(duration),
        "-f", "mp4",
        "-movflags", "+faststart",
        str(output_path),
    ]

    logger.info(
        "Recording started: url=%s duration=%ds output=%s",
        rtsp_url,
        duration,
        output_path,
    )

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        logger.info("Recording finished successfully: %s", output_path)
        return str(output_path)

    logger.error(
        "Recording failed (exit code %d): %s",
        result.returncode,
        result.stderr,
    )
    return None


def get_kinescope_title(filepath: str) -> str:
    """Derive a Kinescope upload title from the recording filename.

    Extracts the filename without extension and replaces underscores with
    colons so the timestamp reads naturally.

    Example:
        "13.02.2026 14_00.mp4"  ->  "13.02.2026 14:00"

    Args:
        filepath: Path to the MP4 file.

    Returns:
        Human-readable title string.
    """
    stem = Path(filepath).stem
    title = stem.replace("_", ":")
    return title


def cleanup_old_recordings(config: dict) -> None:
    """Delete the oldest local recordings when count exceeds the limit.

    Args:
        config: Parsed config dictionary (from config.yaml).
    """
    output_dir = Path(config["recording"]["output_dir"])
    max_files = config["recording"]["max_local_files"]

    if not output_dir.exists():
        logger.info("Output directory does not exist, nothing to clean up")
        return

    # List MP4 files sorted by modification time (oldest first)
    mp4_files = sorted(
        output_dir.glob("*.mp4"),
        key=lambda p: p.stat().st_mtime,
    )

    files_to_delete = len(mp4_files) - max_files
    if files_to_delete <= 0:
        logger.info(
            "No cleanup needed: %d files, max %d", len(mp4_files), max_files
        )
        return

    for old_file in mp4_files[:files_to_delete]:
        old_file.unlink()
        logger.info("Deleted old recording: %s", old_file)

    logger.info("Cleanup complete: removed %d file(s)", files_to_delete)


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
