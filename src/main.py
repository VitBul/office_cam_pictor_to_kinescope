"""Main orchestrator for CamKinescope.

Runs an infinite loop: record RTSP segment -> upload in background -> repeat.
Upload runs in a separate thread so recording continues without gaps.
On startup, uploads any leftover .mp4 files from previous sessions.
Before uploading, checks network for extra devices — pauses if busy.
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
from network_monitor import check_extra_devices
from notifier import (
    notify_recording_started,
    notify_upload_complete,
    notify_error,
    notify_disk_space,
    send_telegram,
)
from logger_setup import setup_logger

logger = setup_logger("main")

# Track files currently being uploaded to avoid double-uploads
_uploading_files = set()
_uploading_lock = threading.Lock()


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


def wait_for_free_network(config: dict) -> None:
    """Block until no extra devices are detected on the network.

    Checks every check_interval_seconds (default 5 min).
    Sends Telegram notification when pausing and resuming.
    """
    if not config.get("network", {}).get("known_devices"):
        return  # Network monitoring not configured, skip

    check_interval = config.get("network", {}).get("check_interval_seconds", 300)
    notified_paused = False

    while True:
        extra = check_extra_devices(config)

        if not extra:
            if notified_paused:
                send_telegram("\u25b6\ufe0f Сеть свободна, загрузка возобновлена", config)
                logger.info("Network clear, resuming upload")
            return

        if not notified_paused:
            devices_str = ", ".join(extra)
            send_telegram(
                f"\u23f8 Загрузка на паузе: обнаружены доп. устройства в сети ({len(extra)}): {devices_str}",
                config,
            )
            notified_paused = True

        logger.info("Extra devices on network (%d), waiting %ds: %s", len(extra), check_interval, extra)
        time.sleep(check_interval)


def upload_in_background(filepath: str, title: str, config: dict) -> None:
    """Upload a file to Kinescope in a background thread.

    Waits for network to be free before uploading.
    On success: sends notification with play_link and deletes local file.
    On failure: sends error notification and keeps local file for retry.
    """
    try:
        # Wait until extra devices leave the network
        wait_for_free_network(config)

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
    finally:
        with _uploading_lock:
            _uploading_files.discard(filepath)

    try:
        cleanup_old_recordings(config)
    except Exception:
        logger.error("Cleanup failed: %s", traceback.format_exc())


def start_upload(filepath: str, config: dict) -> None:
    """Start a background upload thread for a file, if not already uploading."""
    with _uploading_lock:
        if filepath in _uploading_files:
            logger.info("Already uploading, skipping: %s", filepath)
            return
        _uploading_files.add(filepath)

    title = get_kinescope_title(filepath)
    upload_thread = threading.Thread(
        target=upload_in_background,
        args=(filepath, title, config),
        daemon=True,
    )
    upload_thread.start()
    logger.info("Upload thread started for: %s", filepath)


def upload_pending_files(config: dict) -> None:
    """Upload any .mp4 files left in recordings from previous sessions."""
    output_dir = Path(config["recording"]["output_dir"])
    if not output_dir.exists():
        return

    pending = sorted(output_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime)
    if not pending:
        return

    logger.info("Found %d pending file(s) to upload", len(pending))
    send_telegram(f"\U0001f4e4 Найдено {len(pending)} незагруженных файлов, начинаю загрузку", config)

    for mp4_file in pending:
        start_upload(str(mp4_file), config)


def main() -> None:
    config_path = Path(__file__).parent.parent / "config.yaml"
    config = load_config(str(config_path))

    send_telegram("\U0001f680 CamKinescope запущен", config)
    logger.info("CamKinescope started, entering main loop")

    # Upload leftover files from previous sessions
    upload_pending_files(config)

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

            # Start upload in background — next recording starts immediately
            start_upload(filepath, config)

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
