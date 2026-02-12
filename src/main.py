"""Main orchestrator for CamKinescope.

Runs an infinite loop: record RTSP segment -> upload to Kinescope -> notify
via Telegram -> clean up old files -> repeat.
"""

import sys
import time
import shutil
import traceback
from pathlib import Path

from recorder import load_config, record_segment, get_kinescope_title, cleanup_old_recordings
from uploader import upload_to_kinescope
from notifier import (
    notify_recording_started,
    notify_upload_complete,
    notify_error,
    notify_disk_space,
    send_telegram,
)
from logger_setup import setup_logger

logger = setup_logger("main")


# ---------------------------------------------------------------------------
# Disk space check
# ---------------------------------------------------------------------------

def check_disk_space(config: dict, min_free_gb: float = 2.0) -> bool:
    """Check whether the recordings drive has enough free space.

    Args:
        config: Parsed config dictionary (from config.yaml).
        min_free_gb: Minimum required free space in gigabytes.

    Returns:
        True if free space >= min_free_gb, False otherwise.
    """
    output_dir = Path(config["recording"]["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(str(output_dir))
    free_gb = usage.free / (1024 ** 3)

    if free_gb < min_free_gb:
        logger.warning(
            "Low disk space: %.2f GB free (minimum %.2f GB required)",
            free_gb,
            min_free_gb,
        )
        notify_disk_space(free_gb, config)
        return False

    return True


# ---------------------------------------------------------------------------
# Single record-upload-cleanup cycle
# ---------------------------------------------------------------------------

def run_cycle(config: dict) -> None:
    """Execute one full cycle: record -> upload -> cleanup.

    Args:
        config: Parsed config dictionary (from config.yaml).
    """
    # --- Step 1: Disk space check -------------------------------------------
    if not check_disk_space(config):
        logger.info("Disk space low, running cleanup before recording")
        cleanup_old_recordings(config)

        if not check_disk_space(config):
            logger.error("Disk space still insufficient after cleanup, skipping cycle")
            return

    # --- Step 2: Derive expected filename for pre-notification --------------
    from datetime import datetime
    filename = datetime.now().strftime("%d.%m.%Y %H_%M") + ".mp4"

    # --- Step 3: Notify recording start -------------------------------------
    notify_recording_started(filename, config)

    # --- Step 4: Record segment ---------------------------------------------
    filepath = record_segment(config)

    if filepath is None:
        notify_error("запись", "FFmpeg recording returned no file", config)
        return

    # --- Step 5: Upload to Kinescope ----------------------------------------
    title = get_kinescope_title(filepath)

    try:
        upload_to_kinescope(filepath, title, config)
    except Exception:
        error_details = traceback.format_exc()
        logger.error("Upload failed:\n%s", error_details)
        notify_error("загрузка", error_details, config)
        # Keep the local file so it can be retried later
    else:
        # Upload succeeded - notify and remove local copy
        notify_upload_complete(Path(filepath).name, config)
        Path(filepath).unlink()
        logger.info("Local file deleted after successful upload: %s", filepath)

    # --- Step 6: Cleanup old recordings -------------------------------------
    cleanup_old_recordings(config)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Load configuration and run the record-upload loop indefinitely."""
    config_path = Path(__file__).parent.parent / "config.yaml"
    config = load_config(str(config_path))

    send_telegram("\U0001f680 CamKinescope запущен", config)
    logger.info("CamKinescope started, entering main loop")

    while True:
        try:
            run_cycle(config)
        except KeyboardInterrupt:
            logger.info("Stopped by user (KeyboardInterrupt)")
            send_telegram("\u23f9 CamKinescope остановлен", config)
            break
        except Exception:
            error_details = traceback.format_exc()
            logger.error("Critical error in main loop:\n%s", error_details)
            notify_error("критическая", error_details, config)
            logger.info("Sleeping 60 seconds before retry")
            time.sleep(60)


if __name__ == "__main__":
    main()
