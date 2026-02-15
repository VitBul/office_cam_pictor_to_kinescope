"""Telegram bot notifications for CamKinescope.

Sends formatted messages to a configured Telegram chat via the Bot API.
Supports Local Bot API Server for large file uploads (up to 2 GB).
All notification functions are fire-and-forget: they catch network errors
internally so a failed notification never crashes the main process.
"""

from pathlib import Path

import requests
import yaml

from logger_setup import setup_logger

logger = setup_logger(__name__)


# ---------------------------------------------------------------------------
# API base URL helper
# ---------------------------------------------------------------------------

def get_api_base_url(config: dict) -> str:
    """Return Telegram Bot API base URL from config, defaulting to public API."""
    return config["telegram"].get("api_base_url", "https://api.telegram.org")


# ---------------------------------------------------------------------------
# Core send functions
# ---------------------------------------------------------------------------

def send_telegram(message: str, config: dict) -> int | None:
    """Send a message to Telegram using the Bot API.

    Args:
        message: Text to send (HTML parse mode is used).
        config:  Application config dict.

    Returns:
        message_id (int) on success, None on failure.
    """
    bot_token = config["telegram"]["bot_token"]
    chat_id = config["telegram"]["chat_id"]
    base = get_api_base_url(config)
    url = f"{base}/bot{bot_token}/sendMessage"

    try:
        response = requests.post(
            url,
            json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
            timeout=30,
        )
        if response.ok:
            logger.info("Telegram notification sent successfully")
            data = response.json()
            return data.get("result", {}).get("message_id")
        logger.error(
            "Telegram API returned status %s: %s",
            response.status_code,
            response.text,
        )
        return None
    except requests.RequestException as exc:
        logger.error("Failed to send Telegram notification: %s", exc)
        return None


def send_telegram_plain(message: str, config: dict) -> int | None:
    """Send a plain-text message (no HTML parsing) to avoid issues with tracebacks.

    Returns:
        message_id (int) on success, None on failure.
    """
    bot_token = config["telegram"]["bot_token"]
    chat_id = config["telegram"]["chat_id"]
    base = get_api_base_url(config)
    url = f"{base}/bot{bot_token}/sendMessage"

    try:
        response = requests.post(
            url,
            json={"chat_id": chat_id, "text": message},
            timeout=30,
        )
        if response.ok:
            logger.info("Telegram notification sent successfully")
            data = response.json()
            return data.get("result", {}).get("message_id")
        logger.error(
            "Telegram API returned status %s: %s",
            response.status_code,
            response.text,
        )
        return None
    except requests.RequestException as exc:
        logger.error("Failed to send Telegram notification: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Video upload to Telegram (fallback for Kinescope failures)
# ---------------------------------------------------------------------------

def send_video_to_telegram(filepath: str, title: str, config: dict) -> dict | None:
    """Upload a video file to Telegram chat via sendVideo (Local Bot API supports up to 2 GB).

    Args:
        filepath: Path to the video file.
        title: Caption/title for the video.
        config: Application config dict.

    Returns:
        dict with 'message_id' on success, None on failure.
    """
    bot_token = config["telegram"]["bot_token"]
    chat_id = config["telegram"]["chat_id"]
    base = get_api_base_url(config)
    url = f"{base}/bot{bot_token}/sendVideo"

    file_path = Path(filepath)
    file_size_mb = file_path.stat().st_size / (1024 * 1024)
    logger.info("Uploading video to Telegram: %s (%.1f MB)", file_path.name, file_size_mb)

    try:
        with open(filepath, "rb") as video_file:
            response = requests.post(
                url,
                data={"chat_id": chat_id, "caption": title},
                files={"video": (file_path.name, video_file, "video/mp4")},
                timeout=600,  # 10 min for large files
            )
        if response.ok:
            data = response.json()
            message_id = data.get("result", {}).get("message_id")
            logger.info("Video uploaded to Telegram: %s (message_id=%s)", file_path.name, message_id)
            return {"message_id": message_id}
        logger.error(
            "Telegram sendVideo failed (status %s): %s",
            response.status_code,
            response.text[:500],
        )
        return None
    except requests.RequestException as exc:
        logger.error("Failed to upload video to Telegram: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Delete message
# ---------------------------------------------------------------------------

def delete_telegram_message(message_id: int, config: dict) -> bool:
    """Delete a message from Telegram chat.

    Args:
        message_id: ID of the message to delete.
        config: Application config dict.

    Returns:
        True if deleted, False otherwise.
    """
    bot_token = config["telegram"]["bot_token"]
    chat_id = config["telegram"]["chat_id"]
    base = get_api_base_url(config)
    url = f"{base}/bot{bot_token}/deleteMessage"

    try:
        response = requests.post(
            url,
            json={"chat_id": chat_id, "message_id": message_id},
            timeout=30,
        )
        if response.ok:
            logger.info("Telegram message deleted: %s", message_id)
            return True
        logger.error(
            "Telegram deleteMessage failed (status %s): %s",
            response.status_code,
            response.text,
        )
        return False
    except requests.RequestException as exc:
        logger.error("Failed to delete Telegram message: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Pin / Unpin messages
# ---------------------------------------------------------------------------

def pin_message(message_id: int, config: dict) -> bool:
    """Pin a message in the Telegram chat.

    Args:
        message_id: ID of the message to pin.
        config: Application config dict.

    Returns:
        True if pinned, False otherwise.
    """
    bot_token = config["telegram"]["bot_token"]
    chat_id = config["telegram"]["chat_id"]
    base = get_api_base_url(config)
    url = f"{base}/bot{bot_token}/pinChatMessage"

    try:
        response = requests.post(
            url,
            json={"chat_id": chat_id, "message_id": message_id, "disable_notification": True},
            timeout=30,
        )
        if response.ok:
            logger.info("Message pinned: %s", message_id)
            return True
        logger.error(
            "Telegram pinChatMessage failed (status %s): %s",
            response.status_code,
            response.text,
        )
        return False
    except requests.RequestException as exc:
        logger.error("Failed to pin message: %s", exc)
        return False


def unpin_message(message_id: int, config: dict) -> bool:
    """Unpin a message in the Telegram chat.

    Args:
        message_id: ID of the message to unpin.
        config: Application config dict.

    Returns:
        True if unpinned, False otherwise.
    """
    bot_token = config["telegram"]["bot_token"]
    chat_id = config["telegram"]["chat_id"]
    base = get_api_base_url(config)
    url = f"{base}/bot{bot_token}/unpinChatMessage"

    try:
        response = requests.post(
            url,
            json={"chat_id": chat_id, "message_id": message_id},
            timeout=30,
        )
        if response.ok:
            logger.info("Message unpinned: %s", message_id)
            return True
        logger.error(
            "Telegram unpinChatMessage failed (status %s): %s",
            response.status_code,
            response.text,
        )
        return False
    except requests.RequestException as exc:
        logger.error("Failed to unpin message: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Convenience notification helpers
# ---------------------------------------------------------------------------

def notify_recording_started(filename: str, config: dict) -> int | None:
    """Notify that a new recording has started."""
    return send_telegram(f"\U0001f3a5 Запись начата: {filename}", config)


def notify_upload_complete(title: str, config: dict, play_link: str = None) -> int | None:
    """Notify that a file has been uploaded to Kinescope, with play link if available."""
    msg = f"\u2705 Загружено в Kinescope: {title}"
    if play_link:
        msg += f"\n\U0001f517 {play_link}"
    return send_telegram(msg, config)


def notify_error(error_type: str, details: str, config: dict) -> int | None:
    """Notify about an error (plain text, no HTML to avoid parse issues with tracebacks).

    Returns:
        message_id (int) on success, None on failure.
    """
    # Truncate long tracebacks to fit Telegram message limit
    if len(details) > 500:
        details = details[:500] + "..."
    msg = f"\u274c Ошибка ({error_type}): {details}"
    return send_telegram_plain(msg, config)


def notify_disk_space(free_gb: float, config: dict) -> int | None:
    """Notify about low disk space."""
    return send_telegram(
        f"\u26a0\ufe0f Мало места на диске: {free_gb:.1f} ГБ свободно", config
    )


# ---------------------------------------------------------------------------
# Manual / smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    config_path = Path(__file__).parent.parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)

    msg_id = send_telegram("\U0001f527 CamKinescope: тестовое уведомление", cfg)
    if msg_id:
        print(f"Test notification sent successfully (message_id={msg_id})")
    else:
        print("Failed to send test notification")
