"""Main orchestrator for CamKinescope.

Runs an infinite loop: record RTSP segment -> upload in background -> repeat.
Upload runs in a separate thread so recording continues without gaps.
"""

import sys
import time
import shutil
import threading
import traceback
from datetime import datetime
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


def check_disk_space(config: dict, min_free_gb: float = 2.0) -> bool:
    output_dir = Path(config["recording"]["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(str(output_dir))
    free_gb = usage.free / (1024 ** 3)

    if free_gb < min_free_gb:
        logger.warning("Low disk space: %.2f GB free (min %.2f GB)", free_gb, min_free_gb)
        notify_disk_space(free_gb, config)
        return False
    return True


def upload_in_background(filepath: str, title: str, config: dict) -> None:
    """Upload a file to Kinescope in a background thread.

    On success: sends notification with play_link and deletes local file.
    On failure: sends error notification and keeps local file.
    """
    try:
        logger.info("Background upload started: %s", filepath)
        result = upload_to_kinescope(filepath, title, config)
        play_link = result.get("play_link") if result else None
        notify_upload_complete(title, config, play_link=play_link)
        Path(filepath).unlink()
        logger.info("Local file deleted after successful upload: %s", filepath)
    except Exception:
        error_details = traceback.format_exc()
        logger.error("Background upload failed:\n%s", error_details)
        notify_error("загрузка", error_details, config)

    # Cleanup after upload
    try:
        cleanup_old_recordings(config)
    except Exception:
        logger.error("Cleanup failed: %s", traceback.format_exc())


def main() -> None:
    config_path = Path(__file__).parent.parent / "config.yaml"
    config = load_config(str(config_path))

    send_telegram("\U0001f680 CamKinescope запущен", config)
    logger.info("CamKinescope started, entering main loop")

    while True:
        try:
            # Disk space check
            if not check_disk_space(config):
                logger.info("Disk space low, running cleanup")
                cleanup_old_recordings(config)
                if not check_disk_space(config):
                    logger.error("Disk space still insufficient, waiting 60s")
                    time.sleep(60)
                    continue

            # Notify recording start
            filename = datetime.now().strftime("%d.%m.%Y %H_%M") + ".mp4"
            notify_recording_started(filename, config)

            # Record segment (blocks for duration_seconds)
            filepath = record_segment(config)

            if filepath is None:
                notify_error("запись", "VLC recording returned no file", config)
                time.sleep(10)
                continue

            # Start upload in background thread — next recording starts immediately
            title = get_kinescope_title(filepath)
            upload_thread = threading.Thread(
                target=upload_in_background,
                args=(filepath, title, config),
                daemon=True,
            )
            upload_thread.start()
            logger.info("Upload thread started for %s, beginning next recording", filepath)

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
