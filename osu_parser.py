"""
Parses .osu beatmap files and extracts raw data structures.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class HitObject:
    x: float
    y: float
    time: int          # ms
    type_flags: int
    is_slider: bool
    is_spinner: bool
    # slider-specific
    curve_type: str = ""
    curve_points: list[tuple[float, float]] = field(default_factory=list)
    slides: int = 0
    length: float = 0.0
    slider_velocity: float = 1.0  # filled in post-parse


@dataclass
class TimingPoint:
    time: int
    beat_length: float   # ms per beat (positive) or SV multiplier (negative)
    meter: int
    uninherited: bool

    @property
    def bpm(self) -> float:
        if self.uninherited and self.beat_length > 0:
            return 60_000 / self.beat_length
        return 0.0

    @property
    def sv_multiplier(self) -> float:
        """For inherited points: multiplier = -100 / beat_length."""
        if not self.uninherited and self.beat_length < 0:
            return -100 / self.beat_length
        return 1.0


@dataclass
class Beatmap:
    title: str = ""
    artist: str = ""
    version: str = ""   # difficulty name
    circle_size: float = 4.0
    approach_rate: float = 9.0
    overall_difficulty: float = 8.0
    slider_multiplier: float = 1.0   # base SV (from [Difficulty])
    slider_tick_rate: float = 1.0
    timing_points: list[TimingPoint] = field(default_factory=list)
    hit_objects: list[HitObject] = field(default_factory=list)


def _parse_curve_points(raw: str) -> tuple[str, list[tuple[float, float]]]:
    """Parse 'B|x1:y1|x2:y2|...' into (curve_type, [(x,y), ...])."""
    parts = raw.split("|")
    curve_type = parts[0] if parts else "L"
    points: list[tuple[float, float]] = []
    for p in parts[1:]:
        if ":" in p:
            px, py = p.split(":", 1)
            try:
                points.append((float(px), float(py)))
            except ValueError:
                pass
    return curve_type, points


def parse_osu_file(path: str | Path) -> Beatmap:
    """Parse a .osu file and return a Beatmap object."""
    bm = Beatmap()
    section = ""

    with open(path, encoding="utf-8", errors="replace") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("//"):
                continue

            # Section header
            if line.startswith("[") and line.endswith("]"):
                section = line[1:-1]
                continue

            if section == "Metadata":
                if line.startswith("Title:"):
                    bm.title = line.split(":", 1)[1].strip()
                elif line.startswith("Artist:"):
                    bm.artist = line.split(":", 1)[1].strip()
                elif line.startswith("Version:"):
                    bm.version = line.split(":", 1)[1].strip()

            elif section == "Difficulty":
                if line.startswith("CircleSize:"):
                    bm.circle_size = float(line.split(":")[1])
                elif line.startswith("ApproachRate:"):
                    bm.approach_rate = float(line.split(":")[1])
                elif line.startswith("OverallDifficulty:"):
                    bm.overall_difficulty = float(line.split(":")[1])
                elif line.startswith("SliderMultiplier:"):
                    bm.slider_multiplier = float(line.split(":")[1])
                elif line.startswith("SliderTickRate:"):
                    bm.slider_tick_rate = float(line.split(":")[1])

            elif section == "TimingPoints":
                parts = line.split(",")
                if len(parts) < 2:
                    continue
                try:
                    tp = TimingPoint(
                        time=int(float(parts[0])),
                        beat_length=float(parts[1]),
                        meter=int(parts[3]) if len(parts) > 3 else 4,
                        uninherited=parts[6].strip() == "1" if len(parts) > 6 else True,
                    )
                    bm.timing_points.append(tp)
                except (ValueError, IndexError):
                    pass

            elif section == "HitObjects":
                parts = line.split(",")
                if len(parts) < 5:
                    continue
                try:
                    x, y, time_ms, type_flags = (
                        float(parts[0]), float(parts[1]),
                        int(parts[2]), int(parts[3]),
                    )
                except ValueError:
                    continue

                is_slider = bool(type_flags & 2)
                is_spinner = bool(type_flags & 8)

                ho = HitObject(
                    x=x, y=y, time=time_ms,
                    type_flags=type_flags,
                    is_slider=is_slider,
                    is_spinner=is_spinner,
                )

                if is_slider and len(parts) >= 8:
                    ho.curve_type, ho.curve_points = _parse_curve_points(parts[5])
                    try:
                        ho.slides = int(parts[6])
                        ho.length = float(parts[7])
                    except (ValueError, IndexError):
                        pass

                bm.hit_objects.append(ho)

    # Assign per-object slider velocity using timing points
    _assign_slider_velocities(bm)
    return bm


def _assign_slider_velocities(bm: Beatmap) -> None:
    """Annotate each slider with its effective SV (in osu! pixels per ms)."""
    tps = sorted(bm.timing_points, key=lambda t: t.time)
    if not tps:
        return

    # Walk hit objects in time order (already sorted in valid .osu files)
    tp_idx = 0
    base_beat_ms = 500.0  # default 120 BPM
    sv_mult = 1.0

    for ho in bm.hit_objects:
        # Advance timing-point pointer
        while tp_idx + 1 < len(tps) and tps[tp_idx + 1].time <= ho.time:
            tp_idx += 1

        tp = tps[tp_idx]
        if tp.uninherited:
            base_beat_ms = tp.beat_length if tp.beat_length > 0 else base_beat_ms
            sv_mult = 1.0
        else:
            sv_mult = tp.sv_multiplier

        if ho.is_slider:
            # pixels per ms = (SliderMultiplier * 100 * sv_mult) / beat_length
            ho.slider_velocity = (bm.slider_multiplier * 100 * sv_mult) / base_beat_ms
