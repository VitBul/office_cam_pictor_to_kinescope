"""System tray entry point for CamKinescope.

Creates a tray icon using pystray + Pillow.
Runs main() in a background daemon thread.
Context menu: Open logs, Exit.
"""

import os
import sys
import threading
from pathlib import Path

from PIL import Image, ImageDraw
import pystray

# Add src directory to path so imports resolve correctly
sys.path.insert(0, str(Path(__file__).parent))

from main import main
from logger_setup import setup_logger

logger = setup_logger("tray")

# Shared stop event — signals main loop and upload worker to shut down
_stop_event = threading.Event()


def create_camera_icon(size: int = 64) -> Image.Image:
    """Draw a simple camera icon using Pillow."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Camera body (rounded rectangle)
    body_l = int(size * 0.08)
    body_t = int(size * 0.25)
    body_r = int(size * 0.68)
    body_b = int(size * 0.78)
    draw.rounded_rectangle(
        [body_l, body_t, body_r, body_b],
        radius=5,
        fill="#2196F3",
        outline="#1565C0",
        width=2,
    )

    # Lens circle
    cx = (body_l + body_r) // 2
    cy = (body_t + body_b) // 2
    r = int(size * 0.11)
    draw.ellipse(
        [cx - r, cy - r, cx + r, cy + r],
        fill="#BBDEFB",
        outline="#1565C0",
        width=2,
    )

    # Viewfinder triangle (right side)
    tri_l = int(size * 0.68)
    tri_r = int(size * 0.92)
    tri_t = int(size * 0.33)
    tri_b = int(size * 0.70)
    draw.polygon(
        [(tri_l, tri_t), (tri_r, (tri_t + tri_b) // 2), (tri_l, tri_b)],
        fill="#2196F3",
        outline="#1565C0",
    )

    # Recording indicator (red dot)
    dot_r = int(size * 0.06)
    dot_x = int(size * 0.85)
    dot_y = int(size * 0.18)
    draw.ellipse(
        [dot_x - dot_r, dot_y - dot_r, dot_x + dot_r, dot_y + dot_r],
        fill="#F44336",
    )

    return img


def open_logs():
    """Open the logs directory in the default file manager."""
    log_dir = Path(__file__).parent.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    if sys.platform == "win32":
        os.startfile(str(log_dir))
    elif sys.platform == "darwin":
        import subprocess
        subprocess.Popen(["open", str(log_dir)])


def on_exit(icon):
    """Handle Exit menu click: stop main loop, remove tray icon."""
    logger.info("Exit requested from tray menu")
    _stop_event.set()
    icon.stop()


def run_tray():
    """Create and run the system tray icon."""
    icon_image = create_camera_icon()

    menu = pystray.Menu(
        pystray.MenuItem("Открыть логи", lambda: open_logs()),
        pystray.MenuItem("Выход", on_exit),
    )

    icon = pystray.Icon(
        name="CamKinescope",
        icon=icon_image,
        title="CamKinescope",
        menu=menu,
    )

    # Run main() in a background daemon thread
    main_thread = threading.Thread(target=main, args=(_stop_event,), daemon=True)
    main_thread.start()
    logger.info("Main loop started in background thread")

    # pystray.run() blocks — runs the tray event loop on the main thread
    icon.run()

    # After icon.stop(), ensure main loop exits
    _stop_event.set()
    main_thread.join(timeout=15)
    logger.info("CamKinescope shut down")


if __name__ == "__main__":
    run_tray()
