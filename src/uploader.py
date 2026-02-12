"""Kinescope video upload module for the CamKinescope project.

Uploads local MP4 recordings to the Kinescope API and provides a
standalone CLI entry point for manual uploads.
"""

import sys
from pathlib import Path

import requests
import yaml

from logger_setup import setup_logger

logger = setup_logger(__name__)


def upload_to_kinescope(filepath: str, title: str, config: dict) -> dict:
    """Upload an MP4 video file to the Kinescope platform.

    Args:
        filepath: Absolute or relative path to the MP4 file.
        title: Title that will appear in Kinescope.
        config: Parsed config dictionary (from config.yaml).

    Returns:
        Parsed JSON response from the Kinescope API.

    Raises:
        requests.HTTPError: If the API returns a non-2xx status code.
        FileNotFoundError: If the specified file does not exist.
    """
    api_key = config["kinescope"]["api_key"]
    upload_url = config["kinescope"].get(
        "upload_url", "https://upload.new.video"
    )

    path = Path(filepath)
    filename = path.name
    file_size_mb = path.stat().st_size / (1024 * 1024)

    logger.info(
        "Upload started: file=%s size=%.2f MB title=%s",
        filepath,
        file_size_mb,
        title,
    )

    with open(path, "rb") as file_handle:
        response = requests.post(
            upload_url,
            auth=(api_key, ""),
            files={"video": (filename, file_handle, "video/mp4")},
            data={"title": title},
            timeout=7200,  # 2 hours max for large files
        )

    response.raise_for_status()

    result = response.json()
    logger.info(
        "Upload succeeded: status=%d response=%s",
        response.status_code,
        str(result)[:200],
    )
    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python uploader.py <path_to_mp4>")
        sys.exit(1)

    video_path = sys.argv[1]
    config_path = Path(__file__).parent.parent / "config.yaml"

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    video_title = Path(video_path).stem.replace("_", ":")
    result = upload_to_kinescope(video_path, video_title, cfg)
    print("Upload result:", result)
