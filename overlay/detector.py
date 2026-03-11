"""
Background thread that detects which .osu file osu! currently has highlighted.

Strategy:
  1. Find osu!.exe via psutil.
  2. Scan its open file handles for a preview audio file (.mp3/.ogg/.wav)
     inside the Songs directory — osu! keeps this open while previewing.
  3. Collect all .osu files in that audio file's folder.
  4. Try to match the active difficulty from the osu! window title
     (format during gameplay: "osu!  - Artist - Title [Diff]").
  5. Fall back to the alphabetically first .osu if no title match.
  6. Cache parse+extract results by file path — never re-processes the same file.
  7. Push to result_queue only when the detected file actually changes.
"""
from __future__ import annotations

import queue
import re
import sys
import threading
import time
from pathlib import Path
from typing import Optional

import psutil

# Add parent directory so we can import osu_parser / feature_extractor
# (skipped when running as a PyInstaller bundle — modules are already bundled)
if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from feature_extractor import extract_features, compute_strain_sections
from osu_parser import parse_osu_file

POLL_INTERVAL = 0.25          # seconds between osu! process scans
AUDIO_EXTENSIONS = {".mp3", ".ogg", ".wav", ".flac"}
_TITLE_RE = re.compile(r"osu!\s*-\s*.+?\[(.+?)\]$")   # captures [Difficulty]


def _osu_window_title() -> str:
    """Return the osu! window title, or '' if not found."""
    try:
        import ctypes
        import ctypes.wintypes

        EnumWindows        = ctypes.windll.user32.EnumWindows
        GetWindowTextW     = ctypes.windll.user32.GetWindowTextW
        GetWindowTextLengthW = ctypes.windll.user32.GetWindowTextLengthW
        IsWindowVisible    = ctypes.windll.user32.IsWindowVisible
        GetWindowThreadProcessId = ctypes.windll.user32.GetWindowThreadProcessId

        result: list[str] = []

        def _callback(hwnd, _):
            if not IsWindowVisible(hwnd):
                return True
            length = GetWindowTextLengthW(hwnd)
            if length == 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value
            if title.startswith("osu!"):
                result.append(title)
                return False   # stop enumeration
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
        EnumWindows(WNDENUMPROC(_callback), 0)
        return result[0] if result else ""
    except Exception:
        return ""


def _pick_osu_file(folder: Path, window_title: str) -> Optional[Path]:
    """
    Choose the best .osu file from *folder*, in priority order:

    1. [Difficulty] name in the osu! window title (accurate during gameplay).
    2. Most recently accessed .osu file (atime) — osu! reads the file when
       you click a difficulty in song select, bumping its access time.
       Only trusted when the atime is within the last 10 seconds.
    3. Alphabetical first as a last resort.
    """
    candidates = sorted(folder.glob("*.osu"))
    if not candidates:
        return None

    # 1. Window title match
    m = _TITLE_RE.search(window_title)
    if m:
        diff_name = m.group(1).lower()
        for c in candidates:
            if diff_name in c.stem.lower():
                return c

    # 2. Most-recently-accessed file (works when Windows atime updates are on)
    try:
        now = time.time()
        by_atime = max(candidates, key=lambda p: p.stat().st_atime)
        if now - by_atime.stat().st_atime < 10.0:
            return by_atime
    except OSError:
        pass

    # 3. Fallback
    return candidates[0]


class MapDetector(threading.Thread):
    """
    Daemon thread that continuously monitors osu! and pushes feature dicts
    into *result_queue* whenever the active beatmap changes.
    Also pushes None when osu! is not found / no map is active.
    """

    def __init__(self, result_queue: "queue.Queue[Optional[dict]]"):
        super().__init__(daemon=True, name="MapDetector")
        self._queue = result_queue
        self._cache: dict[str, dict] = {}   # path str → feature dict
        self._last_path: Optional[str] = None

    # ── public ────────────────────────────────────────────────────────────────

    def run(self) -> None:
        while True:
            try:
                self._tick()
            except Exception:
                pass
            time.sleep(POLL_INTERVAL)

    # ── internals ─────────────────────────────────────────────────────────────

    def _tick(self) -> None:
        path = self._detect()
        path_str = str(path) if path else None

        if path_str == self._last_path:
            return   # nothing changed

        self._last_path = path_str

        if path is None:
            self._queue.put(None)
            return

        features = self._get_features(path)
        self._queue.put(features)

    def _detect(self) -> Optional[Path]:
        """Return the .osu file osu! currently has active, or None."""
        proc = self._find_osu_process()
        if proc is None:
            return None

        try:
            open_files = proc.open_files()
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            return None

        title = _osu_window_title()

        # FIRST: directly open .osu file — most precise (happens during gameplay
        # and sometimes in song select when a difficulty is loaded)
        for f in open_files:
            if f.path.lower().endswith(".osu"):
                return Path(f.path)

        # SECOND: audio file open for preview — osu! streams this while
        # hovering in song select; use the folder + window title to pick a diff
        for f in open_files:
            p = Path(f.path)
            if p.suffix.lower() in AUDIO_EXTENSIONS:
                result = _pick_osu_file(p.parent, title)
                if result:
                    return result

        return None

    @staticmethod
    def _find_osu_process() -> Optional[psutil.Process]:
        for proc in psutil.process_iter(["name"]):
            try:
                if proc.info["name"] and proc.info["name"].lower() == "osu!.exe":
                    return proc
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return None

    def _get_features(self, path: Path) -> dict:
        key = str(path)
        if key not in self._cache:
            bm = parse_osu_file(path)
            feats = extract_features(bm)
            feats["_file"]     = key
            feats["_sections"] = compute_strain_sections(path=key)
            self._cache[key]  = feats
        return self._cache[key]
