"""Main orchestrator for CamKinescope.

Runs an infinite loop: record RTSP segment -> queue for upload -> repeat.
A single upload worker thread processes files one at a time (sequential).
On startup, queues any leftover .mp4 files from previous sessions.
Before each upload, checks internet connectivity and network for extra devices.

Recording and remuxing work without internet (local LAN only).
Uploads start automatically when internet becomes available.
If Kinescope upload fails after max retries, falls back to Telegram upload.
"""

import sys
import time
import queue
import shutil
import threading
import traceback
from datetime import datetime
from pathlib import Path

import requests

from recorder import load_config, record_segment, get_kinescope_title, cleanup_old_recordings
from uploader import upload_to_kinescope
from network_monitor import check_extra_devices
from notifier import (
    notify_recording_started,
    notify_upload_complete,
    notify_error,
    notify_disk_space,
    send_telegram,
    send_video_to_telegram,
    delete_telegram_message,
)
from logger_setup import setup_logger

logger = setup_logger("main")

# Upload queue: files processed one at a time by upload_worker
_upload_queue = queue.Queue()

# Track file currently being uploaded — used by cleanup to skip it
_uploading_files = set()
_uploading_lock = threading.Lock()

# Track all files sitting in the upload queue — cleanup must skip these too
_queued_files = set()
_queued_lock = threading.Lock()


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


def wait_for_internet(stop_event: threading.Event = None) -> bool:
    """Block until internet is reachable (Kinescope endpoint responds).

    Returns True when connected, False if stop_event is set.
    """
    while True:
        if stop_event and stop_event.is_set():
            return False
        try:
            requests.head("https://uploader.kinescope.io", timeout=10)
            return True
        except (requests.ConnectionError, requests.Timeout, requests.RequestException):
            logger.info("No internet connection, retrying in 60s")
            for _ in range(12):  # 60s in 5s increments to respond to stop_event
                if stop_event and stop_event.is_set():
                    return False
                time.sleep(5)


def wait_for_free_network(config: dict, stop_event: threading.Event = None) -> bool:
    """Block until no extra devices are detected on the local network.

    Returns True when network is free, False if stop_event is set.
    """
    if not config.get("network", {}).get("known_devices"):
        return True  # Network monitoring not configured

    check_interval = config.get("network", {}).get("check_interval_seconds", 300)
    notified_paused = False

    while True:
        if stop_event and stop_event.is_set():
            return False

        extra = check_extra_devices(config)

        if not extra:
            if notified_paused:
                send_telegram("▶️ Сеть свободна, загрузка возобновлена", config)
                logger.info("Network clear, resuming upload")
            return True

        if not notified_paused:
            devices_str = ", ".join(extra)
            send_telegram(
                f"⏸ Загрузка на паузе: доп. устройства в сети ({len(extra)}): {devices_str}",
                config,
            )
            notified_paused = True

        logger.info("Extra devices on network (%d), waiting %ds: %s", len(extra), check_interval, extra)
        for _ in range(check_interval // 5):
            if stop_event and stop_event.is_set():
                return False
            time.sleep(5)


def wait_while_paused(pause_event: threading.Event, stop_event: threading.Event, config: dict) -> bool:
    """Block while pause_event is set. Returns False if stop_event fires during pause."""
    if not pause_event.is_set():
        return True

    send_telegram("⏸ Пауза", config)
    logger.info("Paused by user")

    while pause_event.is_set():
        if stop_event and stop_event.is_set():
            return False
        time.sleep(5)

    # Resumed
    send_telegram("▶️ Возобновлено, проверяю очереди...", config)
    logger.info("Resumed by user")
    pending = _upload_queue.qsize()
    if pending:
        send_telegram(f"📤 В очереди на загрузку: {pending} файлов", config)

    return True


def _get_protected_files() -> set:
    """Return set of file paths that must not be deleted by cleanup.

    Includes files currently being uploaded AND files waiting in the upload queue.
    """
    with _uploading_lock:
        uploading = set(_uploading_files)
    with _queued_lock:
        queued = set(_queued_files)
    return uploading | queued


def upload_worker(config: dict, stop_event: threading.Event = None, pause_event: threading.Event = None) -> None:
    """Worker thread: processes upload queue one file at a time.

    After max_upload_retries failed Kinescope uploads, falls back to Telegram upload.
    """
    max_retries = config.get("kinescope", {}).get("max_upload_retries", 3)
    # Per-file retry counter: filepath -> {"count": int, "error_msg_ids": [int]}
    retry_state = {}

    while True:
        if stop_event and stop_event.is_set():
            break

        # Check pause
        if pause_event and not wait_while_paused(pause_event, stop_event, config):
            break

        # Get next file from queue (blocks up to 10s then re-checks stop_event)
        try:
            filepath = _upload_queue.get(timeout=10)
        except queue.Empty:
            continue

        # File is now dequeued — remove from queued set (it moves to uploading set next)
        with _queued_lock:
            _queued_files.discard(filepath)

        # Verify file still exists
        if not Path(filepath).exists():
            logger.warning("File no longer exists, skipping: %s", filepath)
            retry_state.pop(filepath, None)
            continue

        with _uploading_lock:
            _uploading_files.add(filepath)

        title = get_kinescope_title(filepath)

        # Initialize retry state for this file
        if filepath not in retry_state:
            retry_state[filepath] = {"count": 0, "error_msg_ids": []}

        requeued = False
        try:
            # Check pause before upload
            if pause_event and not wait_while_paused(pause_event, stop_event, config):
                with _queued_lock:
                    _queued_files.add(filepath)
                _upload_queue.put(filepath)
                requeued = True
                break

            # 1. Wait for internet connectivity
            if not wait_for_internet(stop_event):
                with _queued_lock:
                    _queued_files.add(filepath)
                _upload_queue.put(filepath)
                requeued = True
                break

            # 2. Wait for free network (no extra devices on 4G)
            if not wait_for_free_network(config, stop_event):
                with _queued_lock:
                    _queued_files.add(filepath)
                _upload_queue.put(filepath)
                requeued = True
                break

            # 3. Upload to Kinescope
            logger.info("Upload started: %s (attempt %d/%d)",
                        filepath, retry_state[filepath]["count"] + 1, max_retries)
            result = upload_to_kinescope(filepath, title, config)
            play_link = result.get("play_link") if result else None
            notify_upload_complete(title, config, play_link=play_link)

            # Success — delete error messages and cleanup
            _delete_error_messages(retry_state[filepath]["error_msg_ids"], config)
            retry_state.pop(filepath, None)
            Path(filepath).unlink()
            logger.info("Upload complete, file deleted: %s", filepath)

        except Exception:
            error_details = traceback.format_exc()
            logger.error("Upload failed: %s\n%s", filepath, error_details)

            retry_state[filepath]["count"] += 1
            current_count = retry_state[filepath]["count"]

            if current_count >= max_retries:
                # Kinescope exhausted — try Telegram fallback
                logger.info("Max retries (%d) reached for %s, trying Telegram fallback",
                            max_retries, filepath)
                _handle_telegram_fallback(filepath, title, retry_state, config)
            else:
                # Notify error and re-queue — keep file protected from cleanup
                error_msg_id = notify_error("загрузка", error_details, config)
                if error_msg_id:
                    retry_state[filepath]["error_msg_ids"].append(error_msg_id)
                with _queued_lock:
                    _queued_files.add(filepath)
                _upload_queue.put(filepath)
                requeued = True
                # Wait 60s before retry
                for _ in range(12):
                    if stop_event and stop_event.is_set():
                        break
                    time.sleep(5)

        finally:
            # Only remove from uploading set if file was NOT re-queued for retry
            if not requeued:
                with _uploading_lock:
                    _uploading_files.discard(filepath)

        # Cleanup old recordings, skip files being uploaded
        try:
            skip = _get_protected_files()
            cleanup_old_recordings(config, skip_files=skip)
        except Exception:
            logger.error("Cleanup failed: %s", traceback.format_exc())


def _handle_telegram_fallback(filepath: str, title: str, retry_state: dict, config: dict) -> None:
    """Try uploading video to Telegram as fallback. Clean up error messages on success."""
    tg_result = send_video_to_telegram(filepath, title, config)

    if tg_result and tg_result.get("message_id"):
        # Telegram upload succeeded
        logger.info("Telegram fallback succeeded for %s", filepath)
        send_telegram(f"📹 Загружено в Telegram (фоллбэк): {title}", config)

        # Delete previous error messages
        _delete_error_messages(retry_state[filepath]["error_msg_ids"], config)
        retry_state.pop(filepath, None)

        # Delete local file
        try:
            Path(filepath).unlink()
            logger.info("File deleted after Telegram upload: %s", filepath)
        except OSError as exc:
            logger.error("Failed to delete file after Telegram upload: %s", exc)
    else:
        # Both Kinescope and Telegram failed
        logger.error("Telegram fallback also failed for %s, keeping file locally", filepath)
        send_telegram(
            f"⚠️ Не удалось загрузить ни в Kinescope, ни в Telegram: {title}\n"
            f"Файл сохранён локально: {filepath}",
            config,
        )
        retry_state.pop(filepath, None)


def _delete_error_messages(msg_ids: list, config: dict) -> None:
    """Delete previously sent error messages from Telegram."""
    for msg_id in msg_ids:
        try:
            delete_telegram_message(msg_id, config)
        except Exception:
            logger.warning("Failed to delete error message %s", msg_id)


def enqueue_pending_files(config: dict) -> None:
    """Find and queue any .mp4 files left from previous sessions."""
    output_dir = Path(config["recording"]["output_dir"])
    if not output_dir.exists():
        return

    pending = sorted(output_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime)
    if not pending:
        return

    logger.info("Found %d pending file(s) to upload", len(pending))
    send_telegram(f"📤 Найдено {len(pending)} незагруженных файлов, начинаю загрузку", config)

    for mp4_file in pending:
        filepath = str(mp4_file)
        with _queued_lock:
            _queued_files.add(filepath)
        _upload_queue.put(filepath)


def enqueue_upload(filepath: str) -> None:
    """Add a file to the upload queue."""
    with _queued_lock:
        _queued_files.add(filepath)
    _upload_queue.put(filepath)
    logger.info("File queued for upload: %s", filepath)


def main(stop_event: threading.Event = None, pause_event: threading.Event = None) -> None:
    config_path = Path(__file__).parent.parent / "config.yaml"
    config = load_config(str(config_path))

    send_telegram("🚀 CamKinescope запущен", config)
    logger.info("CamKinescope started, entering main loop")

    # Start single upload worker thread (sequential uploads)
    worker = threading.Thread(
        target=upload_worker,
        args=(config, stop_event, pause_event),
        daemon=True,
    )
    worker.start()

    # Queue leftover files from previous sessions
    enqueue_pending_files(config)

    while not (stop_event and stop_event.is_set()):
        try:
            # Check pause
            if pause_event and not wait_while_paused(pause_event, stop_event, config):
                break

            # Disk space check
            if not check_disk_space(config):
                logger.info("Disk space low, running cleanup")
                skip = _get_protected_files()
                cleanup_old_recordings(config, skip_files=skip)
                if not check_disk_space(config):
                    logger.error("Disk space still insufficient, waiting 60s")
                    time.sleep(60)
                    continue

            # Notify recording start
            filename = datetime.now().strftime("%d.%m.%Y %H_%M") + ".mp4"
            notify_recording_started(filename, config)

            # Record segment (blocks for duration_seconds)
            # Recording works on local LAN — no internet required
            filepath = record_segment(config)

            if filepath is None:
                notify_error("запись", "VLC recording returned no file", config)
                time.sleep(10)
                continue

            # Queue for upload — next recording starts immediately
            # Upload worker will wait for internet if needed
            enqueue_upload(filepath)

        except KeyboardInterrupt:
            logger.info("Stopped by user (KeyboardInterrupt)")
            send_telegram("⏹ CamKinescope остановлен", config)
            break
        except Exception:
            error_details = traceback.format_exc()
            logger.error("Critical error in main loop:\n%s", error_details)
            notify_error("критическая", error_details, config)
            logger.info("Sleeping 60 seconds before retry")
            time.sleep(60)

    if stop_event and stop_event.is_set():
        logger.info("Stop event received, shutting down")
        send_telegram("⏹ CamKinescope остановлен", config)


if __name__ == "__main__":
    main()
