"""Telegram bot notifications for CamKinescope.

Sends formatted messages to a configured Telegram chat via the Bot API.
All notification functions are fire-and-forget: they catch network errors
internally so a failed notification never crashes the main process.
"""

from pathlib import Path

import requests
import yaml

from logger_setup import setup_logger

logger = setup_logger(__name__)


# ---------------------------------------------------------------------------
# Core send function
# ---------------------------------------------------------------------------

def send_telegram(message: str, config: dict) -> bool:
    """Send a message to Telegram using the Bot API.

    Args:
        message: Text to send (HTML parse mode is used).
        config:  Application config dict that must contain
                 ``config["telegram"]["bot_token"]`` and
                 ``config["telegram"]["chat_id"]``.

    Returns:
        ``True`` if the message was delivered, ``False`` otherwise.
    """
    bot_token = config["telegram"]["bot_token"]
    chat_id = config["telegram"]["chat_id"]
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    try:
        response = requests.post(
            url,
            json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
            timeout=30,
        )
        if response.ok:
            logger.info("Telegram notification sent successfully")
            return True
        logger.error(
            "Telegram API returned status %s: %s",
            response.status_code,
            response.text,
        )
        return False
    except requests.RequestException as exc:
        logger.error("Failed to send Telegram notification: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Convenience notification helpers
# ---------------------------------------------------------------------------

def notify_recording_started(filename: str, config: dict) -> bool:
    """Notify that a new recording has started."""
    return send_telegram(f"\U0001f3a5 Запись начата: {filename}", config)


def notify_upload_complete(filename: str, config: dict) -> bool:
    """Notify that a file has been uploaded to Kinescope."""
    return send_telegram(f"\u2705 Загружено в Kinescope: {filename}", config)


def notify_error(error_type: str, details: str, config: dict) -> bool:
    """Notify about an error."""
    return send_telegram(f"\u274c Ошибка ({error_type}): {details}", config)


def notify_disk_space(free_gb: float, config: dict) -> bool:
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

    ok = send_telegram("\U0001f527 CamKinescope: тестовое уведомление", cfg)
    if ok:
        print("Test notification sent successfully")
    else:
        print("Failed to send test notification")
