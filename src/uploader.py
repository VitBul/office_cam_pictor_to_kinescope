"""Kinescope video upload module for CamKinescope.

Uses Kinescope Uploader API v2 (Method 2: Single Request Upload).
Endpoint: POST https://uploader.kinescope.io/v2/video
Auth: Bearer token in header.
"""

import sys
from pathlib import Path

import requests
import yaml

from logger_setup import setup_logger

logger = setup_logger(__name__)

KINESCOPE_UPLOAD_URL = "https://uploader.kinescope.io/v2/video"


def upload_to_kinescope(filepath: str, title: str, config: dict) -> dict:
    """Upload an MP4 video file to Kinescope.

    Uses single-request upload: sends the raw video binary in the request body
    with metadata in headers.

    Returns:
        Parsed JSON response from the Kinescope API.
    Raises:
        requests.HTTPError: If the API returns a non-2xx status code.
    """
    api_key = config["kinescope"]["api_key"]
    parent_id = config["kinescope"]["parent_id"]

    path = Path(filepath)
    file_size_mb = path.stat().st_size / (1024 * 1024)

    logger.info(
        "Upload started: file=%s size=%.2f MB title=%s",
        filepath, file_size_mb, title,
    )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "X-Parent-ID": parent_id,
        "X-Video-Title": title,
        "Content-Type": "video/mp4",
    }

    with open(path, "rb") as f:
        response = requests.post(
            KINESCOPE_UPLOAD_URL,
            headers=headers,
            data=f,
            timeout=7200,
        )

    response.raise_for_status()

    result = response.json()
    logger.info(
        "Upload succeeded: status=%d response=%s",
        response.status_code, str(result)[:200],
    )
    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python uploader.py <path_to_mp4>")
        sys.exit(1)

    video_path = sys.argv[1]
    config_path = Path(__file__).parent.parent / "config.yaml"

    with open(config_path, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)

    video_title = Path(video_path).stem.replace("_", ":")
    result = upload_to_kinescope(video_path, video_title, cfg)
    print("Upload result:", result)
