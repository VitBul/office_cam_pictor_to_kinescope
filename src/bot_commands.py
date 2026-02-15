"""Telegram Bot command listener for CamKinescope.

Long-polls getUpdates to handle /stream, /stopstream, /status commands.
Runs in a daemon thread alongside recording and uploading.
"""

import threading
import time
import traceback

import requests

from logger_setup import setup_logger
from notifier import send_telegram, pin_message, unpin_message, get_api_base_url
from streamer import start_stream, stop_stream, is_streaming

logger = setup_logger(__name__)

# Message ID of the pinned stream link (to unpin on stop)
_pinned_message_id: int | None = None


def _get_updates(config: dict, offset: int, timeout: int = 30) -> list:
    """Call Telegram getUpdates with long polling."""
    bot_token = config["telegram"]["bot_token"]
    base = get_api_base_url(config)
    url = f"{base}/bot{bot_token}/getUpdates"

    try:
        response = requests.get(
            url,
            params={"offset": offset, "timeout": timeout, "allowed_updates": '["message"]'},
            timeout=timeout + 10,
        )
        if response.ok:
            return response.json().get("result", [])
        logger.error("getUpdates failed (status %s): %s", response.status_code, response.text[:200])
        return []
    except requests.RequestException as exc:
        logger.error("getUpdates request failed: %s", exc)
        return []


def _handle_stream(config: dict) -> None:
    """Handle /stream command: start VLC stream, send and pin play link."""
    global _pinned_message_id

    if is_streaming():
        play_link = config["streaming"]["play_link"]
        send_telegram(f"\u26a0\ufe0f Трансляция уже идёт:\n\U0001f517 {play_link}", config)
        return

    ok = start_stream(config)
    if not ok:
        send_telegram("\u274c Не удалось запустить трансляцию", config)
        return

    play_link = config["streaming"]["play_link"]
    msg_id = send_telegram(f"\U0001f534 Трансляция запущена:\n\U0001f517 {play_link}", config)

    if msg_id:
        pin_message(msg_id, config)
        _pinned_message_id = msg_id


def _handle_stopstream(config: dict) -> None:
    """Handle /stopstream command: stop VLC stream, unpin message."""
    global _pinned_message_id

    if not is_streaming():
        send_telegram("\u2139\ufe0f Трансляция не запущена", config)
        return

    stop_stream()

    if _pinned_message_id:
        unpin_message(_pinned_message_id, config)
        _pinned_message_id = None

    send_telegram("\u23f9 Трансляция остановлена", config)


def _handle_status(config: dict, upload_queue_size: int = 0) -> None:
    """Handle /status command: show system status."""
    streaming = "\U0001f534 Стрим: активен" if is_streaming() else "\u26aa Стрим: не активен"

    lines = [
        "\U0001f4ca Статус CamKinescope:",
        streaming,
        f"\U0001f4e4 В очереди на загрузку: {upload_queue_size}",
    ]
    send_telegram("\n".join(lines), config)


def start_command_listener(config: dict, stop_event: threading.Event, upload_queue=None) -> None:
    """Long-poll Telegram getUpdates and handle bot commands.

    Args:
        config: Application config dict.
        stop_event: Event to signal shutdown.
        upload_queue: Optional queue.Queue to report queue size in /status.
    """
    chat_id = str(config["telegram"]["chat_id"])
    offset = 0

    logger.info("Command listener started")

    while not stop_event.is_set():
        try:
            updates = _get_updates(config, offset, timeout=30)

            for update in updates:
                offset = update["update_id"] + 1

                message = update.get("message", {})
                text = message.get("text", "")
                msg_chat_id = str(message.get("chat", {}).get("id", ""))

                # Only process commands from the configured chat
                if msg_chat_id != chat_id:
                    continue

                if text.startswith("/stream") and not text.startswith("/stopstream"):
                    logger.info("Command received: /stream")
                    _handle_stream(config)
                elif text.startswith("/stopstream"):
                    logger.info("Command received: /stopstream")
                    _handle_stopstream(config)
                elif text.startswith("/status"):
                    logger.info("Command received: /status")
                    queue_size = upload_queue.qsize() if upload_queue else 0
                    _handle_status(config, queue_size)

        except Exception:
            logger.error("Command listener error:\n%s", traceback.format_exc())
            # Wait before retrying to avoid tight loop on persistent errors
            for _ in range(6):
                if stop_event.is_set():
                    return
                time.sleep(5)

    logger.info("Command listener stopped")
