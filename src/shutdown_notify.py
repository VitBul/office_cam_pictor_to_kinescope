"""Send a Telegram notification when the PC is shutting down.

Self-contained script (no project imports) for maximum reliability
during the limited shutdown window.
"""

from pathlib import Path

import requests
import yaml


def main():
    try:
        config_path = Path(__file__).parent.parent / "config.yaml"
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        bot_token = config["telegram"]["bot_token"]
        chat_id = config["telegram"]["chat_id"]

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        requests.post(
            url,
            json={"chat_id": chat_id, "text": "⏹ Компьютер выключается..."},
            timeout=10,
        )
    except Exception:
        pass


if __name__ == "__main__":
    main()
