"""
Extracts a feature vector from a parsed Beatmap.
All distance units are osu! pixels (playfield is 512x384).
"""
from __future__ import annotations
import math
import statistics
from typing import Any

from osu_parser import Beatmap, HitObject


# ── helpers ──────────────────────────────────────────────────────────────────

def _dist(a: HitObject, b: HitObject) -> float:
    return math.hypot(b.x - a.x, b.y - a.y)


def _angle_between(a: HitObject, b: HitObject, c: HitObject) -> float:
    """Angle (degrees) at vertex b formed by a→b→c."""
    dx1, dy1 = a.x - b.x, a.y - b.y
    dx2, dy2 = c.x - b.x, c.y - b.y
    mag1 = math.hypot(dx1, dy1)
    mag2 = math.hypot(dx2, dy2)
    if mag1 == 0 or mag2 == 0:
        return 0.0
    cos_a = max(-1.0, min(1.0, (dx1*dx2 + dy1*dy2) / (mag1 * mag2)))
    return math.degrees(math.acos(cos_a))


def _direction_change(a: HitObject, b: HitObject, c: HitObject) -> float:
    """Signed turn angle in degrees (positive = left, negative = right)."""
    dx1, dy1 = b.x - a.x, b.y - a.y
    dx2, dy2 = c.x - b.x, c.y - b.y
    cross = dx1 * dy2 - dy1 * dx2           # z-component of cross product
    dot   = dx1 * dx2 + dy1 * dy2
    return math.degrees(math.atan2(cross, dot))


def _safe_stdev(data: list[float]) -> float:
    if len(data) < 2:
        return 0.0
    return statistics.stdev(data)


def _safe_mean(data: list[float]) -> float:
    return statistics.mean(data) if data else 0.0


# ── BPM helpers ───────────────────────────────────────────────────────────────

def _dominant_bpm(bm: Beatmap, hit_objects: list[HitObject]) -> float:
    """
    Return the BPM active for the longest time span during the map's
    note-active region (first note → last note).
    """
    uninherited = [tp for tp in bm.timing_points if tp.uninherited and tp.bpm > 0]
    if not uninherited:
        return 0.0
    if not hit_objects:
        return uninherited[0].bpm

    start_t = hit_objects[0].time
    end_t   = hit_objects[-1].time

    # collect (time, bpm) breakpoints within the map range
    bps: list[tuple[int, float]] = []
    for tp in sorted(uninherited, key=lambda t: t.time):
        bps.append((tp.time, tp.bpm))

    # find bpm active at start_t
    active_bpm = bps[0][1]
    for t, b in bps:
        if t <= start_t:
            active_bpm = b

    # accumulate durations
    durations: dict[float, float] = {}
    prev_t = start_t
    prev_b = active_bpm

    for tp_t, tp_b in bps:
        if tp_t <= start_t:
            prev_b = tp_b
            continue
        if tp_t >= end_t:
            break
        durations[prev_b] = durations.get(prev_b, 0) + (tp_t - prev_t)
        prev_t, prev_b = tp_t, tp_b

    durations[prev_b] = durations.get(prev_b, 0) + (end_t - prev_t)
    return max(durations, key=lambda k: durations[k])


# ── stream detection ──────────────────────────────────────────────────────────

_STREAM_MIN_BPM    = 170          # minimum BPM to count as a stream note
_STREAM_MIN_LENGTH = 4            # consecutive notes to qualify as a stream


def _detect_streams(
    objs: list[HitObject],
    dom_bpm: float,
) -> dict[str, Any]:
    """
    Detect runs of ≥4 consecutive circles spaced close enough to be
    170+ BPM equivalent (i.e. gap ≤ 60000 / (2 * bpm_threshold) ms).

    We use a dynamic threshold: max_gap = 60000 / (2 * max(dom_bpm, 170)).
    This adapts the detector to the map's actual tempo.
    """
    threshold_bpm = max(dom_bpm * 0.9, _STREAM_MIN_BPM)
    max_gap = 60_000 / (2 * threshold_bpm)   # ms between 1/4 notes at that BPM

    circles = [o for o in objs if not o.is_slider and not o.is_spinner]

    runs: list[int] = []   # lengths of detected stream runs
    i = 0
    while i < len(circles) - 1:
        run_len = 1
        j = i
        while j < len(circles) - 1:
            gap = circles[j + 1].time - circles[j].time
            if gap <= max_gap:
                run_len += 1
                j += 1
            else:
                break
        if run_len >= _STREAM_MIN_LENGTH:
            runs.append(run_len)
            i = j + 1
        else:
            i += 1

    total_stream_notes = sum(runs)
    total_circles      = len(circles)

    return {
        "stream_run_count":          len(runs),
        "stream_total_notes":        total_stream_notes,
        "stream_avg_run_length":     _safe_mean([float(r) for r in runs]),
        "stream_max_run_length":     max(runs) if runs else 0,
        "stream_note_ratio":         total_stream_notes / total_circles if total_circles else 0.0,
        "stream_threshold_bpm":      round(threshold_bpm, 2),
    }


# ── slider complexity ─────────────────────────────────────────────────────────

def _slider_features(objs: list[HitObject]) -> dict[str, Any]:
    sliders = [o for o in objs if o.is_slider]
    if not sliders:
        return {
            "slider_count":           0,
            "slider_avg_length":      0.0,
            "slider_length_variance": 0.0,
            "slider_avg_curve_pts":   0.0,
            "slider_avg_velocity":    0.0,
            "slider_velocity_variance": 0.0,
            "slider_complex_ratio":   0.0,   # fraction with ≥3 curve points
        }

    lengths    = [s.length for s in sliders]
    velocities = [s.slider_velocity for s in sliders]
    curve_pts  = [len(s.curve_points) for s in sliders]
    complex_count = sum(1 for c in curve_pts if c >= 3)

    return {
        "slider_count":             len(sliders),
        "slider_avg_length":        _safe_mean(lengths),
        "slider_length_variance":   _safe_stdev(lengths),
        "slider_avg_curve_pts":     _safe_mean([float(c) for c in curve_pts]),
        "slider_avg_velocity":      _safe_mean(velocities),
        "slider_velocity_variance": _safe_stdev(velocities),
        "slider_complex_ratio":     complex_count / len(sliders),
    }


# ── main extractor ────────────────────────────────────────────────────────────

def extract_features(bm: Beatmap) -> dict[str, Any]:
    objs = bm.hit_objects
    if not objs:
        return {"error": "no hit objects"}

    # ── filter spinners for most calculations ────────────────────────────────
    active = [o for o in objs if not o.is_spinner]
    if len(active) < 2:
        return {"error": "too few non-spinner objects"}

    # ── timing ───────────────────────────────────────────────────────────────
    map_start = active[0].time
    map_end   = active[-1].time
    map_dur_s = (map_end - map_start) / 1000.0

    dom_bpm = _dominant_bpm(bm, active)

    intervals = [active[i+1].time - active[i].time for i in range(len(active)-1)]
    pos_intervals = [iv for iv in intervals if iv > 0]

    note_density   = len(active) / map_dur_s if map_dur_s > 0 else 0.0
    rhythm_variance = _safe_stdev([float(iv) for iv in pos_intervals])

    # rhythm irregularity: coefficient of variation of intervals
    mean_iv = _safe_mean([float(iv) for iv in pos_intervals])
    rhythm_cv = (rhythm_variance / mean_iv) if mean_iv > 0 else 0.0

    # ── distances ────────────────────────────────────────────────────────────
    dists = [_dist(active[i], active[i+1]) for i in range(len(active)-1)]
    avg_dist = _safe_mean(dists)
    max_dist = max(dists) if dists else 0.0
    dist_variance = _safe_stdev(dists)

    # ── directional change ───────────────────────────────────────────────────
    angles: list[float] = []
    turn_angles: list[float] = []
    dir_change_count = 0

    for i in range(1, len(active) - 1):
        ang = _angle_between(active[i-1], active[i], active[i+1])
        turn = _direction_change(active[i-1], active[i], active[i+1])
        angles.append(ang)
        turn_angles.append(turn)
        # a "direction change" is any turn > 45°
        if abs(turn) > 45:
            dir_change_count += 1

    dir_change_freq      = dir_change_count / len(active) if active else 0.0
    angle_variance       = _safe_stdev(angles)
    avg_angle            = _safe_mean(angles)
    avg_abs_turn         = _safe_mean([abs(t) for t in turn_angles])

    # ── streams ──────────────────────────────────────────────────────────────
    stream_feats = _detect_streams(active, dom_bpm)

    # ── sliders ──────────────────────────────────────────────────────────────
    slider_feats = _slider_features(active)

    # ── assemble ─────────────────────────────────────────────────────────────
    features: dict[str, Any] = {
        # identity
        "title":   bm.title,
        "artist":  bm.artist,
        "version": bm.version,
        # global stats
        "map_duration_s":      round(map_dur_s, 3),
        "total_objects":       len(objs),
        "circle_count":        sum(1 for o in active if not o.is_slider),
        "slider_count":        sum(1 for o in active if o.is_slider),
        "spinner_count":       len(objs) - len(active),
        # BPM / density
        "dominant_bpm":        round(dom_bpm, 2),
        "note_density_per_s":  round(note_density, 4),
        # distance
        "avg_distance":        round(avg_dist, 4),
        "max_distance":        round(max_dist, 4),
        "distance_variance":   round(dist_variance, 4),
        # rhythm
        "avg_interval_ms":     round(mean_iv, 4),
        "rhythm_variance_ms":  round(rhythm_variance, 4),
        "rhythm_cv":           round(rhythm_cv, 6),
        # direction
        "dir_change_freq":     round(dir_change_freq, 6),
        "avg_angle_deg":       round(avg_angle, 4),
        "angle_variance_deg":  round(angle_variance, 4),
        "avg_abs_turn_deg":    round(avg_abs_turn, 4),
    }

    # merge stream and slider sub-dicts
    features.update(stream_feats)
    features.update(slider_feats)

    return features


# ── osu! standard difficulty sections via rosu-pp ─────────────────────────────
#
# Uses rosu-pp-py (the same Rust library osu! uses internally) for accurate
# per-section aim + speed strain values.
#
# star_rating per section is scaled so:
#   peak section  ≈  overall star rating reported by osu!
#   quiet sections (breaks/intro) approach 0★
#
# Pattern classification uses the per-section aim/speed ratio:
#   speed >> aim  →  stream  (red)
#   aim   >> speed →  jump   (blue)
#   both high     →  tech   (yellow)
#   otherwise     →  flow   (green)


def compute_strain_sections(path: str) -> list[dict]:
    """
    Return per-section difficulty using rosu-pp-py.

    Each dict:
        t_start, t_end, t_mid  – ms (relative to map audio start)
        star_rating            – osu! ★ scaled to match official rating
        pattern                – "stream" | "jump" | "tech" | "flow"
        color                  – hex colour for the pattern
    """
    if not path:
        return []
    try:
        import rosu_pp_py as rosu

        rosu_map = rosu.Beatmap(path=path)
        diff     = rosu.Difficulty()

        # Overall star rating — used as the Y-axis ceiling
        overall = diff.calculate(rosu_map).stars
        if overall == 0:
            return []

        # Per-section strain arrays (one value per `section_length` ms window)
        strains  = diff.strains(rosu_map)
        aim_arr  = strains.aim
        spd_arr  = strains.speed
        sec_ms   = strains.section_length   # typically 400 ms

        n = min(len(aim_arr), len(spd_arr))
        if n == 0:
            return []

        combined   = [aim_arr[i] + spd_arr[i] for i in range(n)]
        max_comb   = max(combined) or 1.0
        # Scale so the hardest section equals the map's true star rating
        star_scale = overall / max_comb

        sections: list[dict] = []
        for i in range(n):
            aim  = aim_arr[i]
            spd  = spd_arr[i]
            comb = combined[i]
            star = comb * star_scale

            # Pattern from aim/speed ratio
            if comb < max_comb * 0.04:
                pattern, color = "flow",   "#81c784"   # break / silent
            elif spd > 0 and aim / (spd + 1e-9) < 0.45:
                pattern, color = "stream", "#ff6b6b"   # speed dominant
            elif aim > 0 and spd / (aim + 1e-9) < 0.45:
                pattern, color = "jump",   "#4fc3f7"   # aim dominant
            elif comb > max_comb * 0.65:
                pattern, color = "tech",   "#ffd54f"   # both high
            else:
                pattern, color = "flow",   "#81c784"

            sections.append({
                "t_start":     float(i * sec_ms),
                "t_end":       float((i + 1) * sec_ms),
                "t_mid":       float(i * sec_ms + sec_ms / 2),
                "star_rating": round(star, 2),
                "pattern":     pattern,
                "color":       color,
            })

        return sections

    except Exception:
        return []
