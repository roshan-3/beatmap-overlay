"""
Entry point for the osu! MapClassifier overlay.

Usage:
    python overlay/main.py

The overlay window appears in the top-right corner.
- Drag to reposition.
- Right-click to close.
"""
from __future__ import annotations

import queue

from detector import MapDetector
from gui import OverlayWindow


def main() -> None:
    data_queue: queue.Queue = queue.Queue()

    detector = MapDetector(data_queue)
    detector.start()

    overlay = OverlayWindow(data_queue)
    overlay.run()   # blocks on tkinter mainloop


if __name__ == "__main__":
    main()
