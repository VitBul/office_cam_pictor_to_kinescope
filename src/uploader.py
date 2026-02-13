"""Kinescope video upload module for CamKinescope.

Uses Kinescope Uploader API v2 (Method 2: Single Request Upload).
Endpoint: POST https://uploader.kinescope.io/v2/video
Auth: Bearer token in header.

After upload, fetches video details from the main API to get play_link.
"""

import sys
import time
from pathlib import Path

import requests
import yaml

from logger_setup import setup_logger

logger = setup_logger(__name__)

KINESCOPE_UPLOAD_URL = "https://uploader.kinescope.io/v2/video"
KINESCOPE_API_URL = "https://api.kinescope.io/v1"


def upload_to_kinescope(filepath: str, title: str, config: dict) -> dict:
    """Upload an MP4 video file to Kinescope.

    Returns:
        Dict with keys: 'video_id', 'play_link', 'title', 'raw_response'.
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

    upload_result = response.json()
    logger.info(
        "Upload succeeded: status=%d response=%s",
        response.status_code, str(upload_result)[:300],
    )

    # Extract video_id from upload response
    video_id = None
    if isinstance(upload_result, dict):
        video_id = upload_result.get("data", {}).get("id") or upload_result.get("id")

    # Try to get play_link via main API
    play_link = None
    if video_id:
        play_link = get_video_play_link(video_id, api_key)

    return {
        "video_id": video_id,
        "play_link": play_link,
        "title": title,
        "raw_response": upload_result,
    }


def get_video_play_link(video_id: str, api_key: str, retries: int = 3) -> str:
    """Fetch play_link for a video from Kinescope API.

    The video may take a moment to appear after upload, so we retry.
    Returns play_link URL string, or None if not available.
    """
    headers = {"Authorization": f"Bearer {api_key}"}

    for attempt in range(retries):
        try:
            resp = requests.get(
                f"{KINESCOPE_API_URL}/videos/{video_id}",
                headers=headers,
                timeout=30,
            )
            if resp.ok:
                data = resp.json().get("data", {})
                play_link = data.get("play_link")
                if play_link:
                    logger.info("Got play_link: %s", play_link)
                    return play_link
        except requests.RequestException as exc:
            logger.warning("Failed to fetch play_link (attempt %d): %s", attempt + 1, exc)

        if attempt < retries - 1:
            time.sleep(5)

    logger.warning("Could not get play_link for video %s after %d attempts", video_id, retries)
    return None


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
    print(f"Video ID: {result['video_id']}")
    print(f"Play link: {result['play_link']}")
    print(f"Title: {result['title']}")
