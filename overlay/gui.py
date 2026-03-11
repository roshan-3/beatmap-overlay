"""
Always-on-top tkinter overlay window.

Layout (top → bottom):
  ┌ accent bar ──────────────────────────────┐
  │ title / artist / difficulty              │
  ├──────────────────────────────────────────┤
  │ feature rows (key stats)                 │
  ├──────────────────────────────────────────┤
  │ INTENSITY MAP  (line graph)              │
  │ legend: ■ stream  ■ jump  ■ tech             │
  ├──────────────────────────────────────────┤
  │ right-click to close  •  drag to move    │
  └──────────────────────────────────────────┘

Controls:
  Drag  – reposition
  Right-click – close
"""
from __future__ import annotations

import queue
import tkinter as tk
from tkinter import font as tkfont
from typing import Optional

# ── palette ───────────────────────────────────────────────────────────────────
BG        = "#0f0f1a"
PANEL     = "#1a1a2e"
ACCENT    = "#e040fb"
TEXT_MAIN = "#e8e8f0"
TEXT_DIM  = "#7a7a9a"
TEXT_VAL  = "#ffffff"
BORDER    = "#2e2e4e"
GRAPH_BG  = "#0a0a15"

COL_STREAM = "#ff6b6b"
COL_JUMP   = "#4fc3f7"
COL_TECH   = "#ffd54f"
COL_FLOW   = "#81c784"

_LEGEND = [("stream", COL_STREAM), ("jump", COL_JUMP),
           ("tech",   COL_TECH),   ("flow", COL_FLOW)]

# ── feature rows: (label, feature_key, format_string) ────────────────────────
_ROWS: list[tuple[str, str, str]] = [
    ("BPM",          "dominant_bpm",         "{:.0f}"),
    ("Notes / s",    "note_density_per_s",   "{:.2f}"),
    ("Avg distance", "avg_distance",         "{:.1f} px"),
    ("Max distance", "max_distance",         "{:.1f} px"),
    ("Dir changes",  "dir_change_freq",      "{:.1%}"),
    ("Streams",      "stream_run_count",     "{:.0f} runs"),
    ("Stream notes", "stream_note_ratio",    "{:.1%}"),
    ("Stream max",   "stream_max_run_length","{:.0f} notes"),
    ("Complex sldr", "slider_complex_ratio", "{:.1%}"),
]

_W, _H    = 272, 470
_GRAPH_H  = 100   # canvas pixel height
_GRAPH_W  = 252   # canvas pixel width (matches inner width at padx=10)


class OverlayWindow:
    def __init__(self, data_queue: "queue.Queue[Optional[dict]]"):
        self._queue  = data_queue
        self._drag_x = 0
        self._drag_y = 0

        self._root = tk.Tk()
        self._setup_window()
        self._build_ui()
        self._root.after(150, self._poll)

    # ── window setup ──────────────────────────────────────────────────────────

    def _setup_window(self) -> None:
        r = self._root
        r.title("MapClassifier")
        r.overrideredirect(True)
        r.wm_attributes("-topmost", True)
        r.wm_attributes("-alpha", 0.92)
        r.configure(bg=BG)
        r.resizable(False, False)

        sw = r.winfo_screenwidth()
        r.geometry(f"{_W}x{_H}+{sw - _W - 16}+16")

        r.bind("<Button-1>",  self._drag_start)
        r.bind("<B1-Motion>", self._drag_move)
        r.bind("<Button-3>",  lambda _e: r.destroy())

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        r = self._root

        bold_md = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        bold_sm = tkfont.Font(family="Segoe UI", size=8,  weight="bold")
        reg_sm  = tkfont.Font(family="Segoe UI", size=8)
        reg_xs  = tkfont.Font(family="Segoe UI", size=7)

        # ── top accent bar ────────────────────────────────────────────────────
        hdr = tk.Frame(r, bg=ACCENT, height=3)
        hdr.pack(fill="x")
        self._bind_drag(hdr)

        # ── song info panel ───────────────────────────────────────────────────
        top = tk.Frame(r, bg=PANEL, padx=10, pady=8)
        top.pack(fill="x")
        self._bind_drag(top)

        self._lbl_title   = tk.Label(top, text="— no map detected —",
                                     fg=TEXT_MAIN, bg=PANEL,
                                     font=bold_md, wraplength=248, justify="left")
        self._lbl_title.pack(anchor="w")

        self._lbl_artist  = tk.Label(top, text="", fg=TEXT_DIM, bg=PANEL,
                                     font=reg_sm, wraplength=248, justify="left")
        self._lbl_artist.pack(anchor="w")

        self._lbl_version = tk.Label(top, text="", fg=ACCENT, bg=PANEL,
                                     font=bold_sm)
        self._lbl_version.pack(anchor="w", pady=(2, 0))

        tk.Frame(r, bg=BORDER, height=1).pack(fill="x")

        # ── feature rows ──────────────────────────────────────────────────────
        body = tk.Frame(r, bg=BG, padx=10, pady=6)
        body.pack(fill="x")
        self._bind_drag(body)

        self._val_labels: dict[str, tk.Label] = {}

        for _label, key, _fmt in _ROWS:
            row = tk.Frame(body, bg=BG)
            row.pack(fill="x", pady=1)
            self._bind_drag(row)

            tk.Label(row, text=_label, fg=TEXT_DIM, bg=BG,
                     font=reg_sm, width=13, anchor="w").pack(side="left")

            val_lbl = tk.Label(row, text="—", fg=TEXT_VAL, bg=BG,
                               font=bold_sm, anchor="e")
            val_lbl.pack(side="right")
            self._val_labels[key] = val_lbl

        tk.Frame(r, bg=BORDER, height=1).pack(fill="x")

        # ── intensity graph ───────────────────────────────────────────────────
        graph_outer = tk.Frame(r, bg=BG, padx=10, pady=5)
        graph_outer.pack(fill="x")
        self._bind_drag(graph_outer)

        tk.Label(graph_outer, text="INTENSITY MAP", fg=TEXT_DIM, bg=BG,
                 font=reg_xs).pack(anchor="w", pady=(0, 3))

        self._graph_canvas = tk.Canvas(graph_outer,
                                       width=_GRAPH_W, height=_GRAPH_H,
                                       bg=GRAPH_BG, highlightthickness=0)
        self._graph_canvas.pack()

        # legend
        legend = tk.Frame(graph_outer, bg=BG)
        legend.pack(anchor="w", pady=(4, 0))
        for name, col in _LEGEND:
            tk.Label(legend, text="■", fg=col,      bg=BG, font=reg_xs).pack(side="left")
            tk.Label(legend, text=f" {name}  ",     fg=TEXT_DIM, bg=BG, font=reg_xs).pack(side="left")

        # ── footer ────────────────────────────────────────────────────────────
        tk.Frame(r, bg=BORDER, height=1).pack(fill="x")
        foot = tk.Label(r, text="right-click to close  •  drag to move",
                        fg=TEXT_DIM, bg=BG, font=reg_xs)
        foot.pack(pady=3)
        self._bind_drag(foot)

    # ── queue polling ─────────────────────────────────────────────────────────

    def _poll(self) -> None:
        try:
            while True:
                data = self._queue.get_nowait()
                self._refresh(data)
        except queue.Empty:
            pass
        self._root.after(150, self._poll)

    # ── display update ────────────────────────────────────────────────────────

    def _refresh(self, data: Optional[dict]) -> None:
        if data is None:
            self._lbl_title.config(text="— osu! not detected —")
            self._lbl_artist.config(text="")
            self._lbl_version.config(text="")
            for lbl in self._val_labels.values():
                lbl.config(text="—", fg=TEXT_VAL)
            self._graph_canvas.delete("all")
            return

        self._lbl_title.config(text=data.get("title",   "Unknown"))
        self._lbl_artist.config(text=data.get("artist",  ""))
        self._lbl_version.config(text=data.get("version", ""))

        for _label, key, fmt in _ROWS:
            lbl = self._val_labels[key]
            val = data.get(key)
            if val is None:
                lbl.config(text="—", fg=TEXT_VAL)
                continue
            try:
                text = fmt.format(val)
            except (ValueError, TypeError):
                text = str(val)

            color = TEXT_VAL
            if key == "stream_note_ratio" and isinstance(val, float) and val > 0.3:
                color = COL_STREAM
            elif key == "slider_complex_ratio" and isinstance(val, float) and val > 0.4:
                color = COL_JUMP

            lbl.config(text=text, fg=color)

        self._draw_graph(data.get("_sections") or [])

    # ── graph helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _bin_sections(sections: list[dict], bin_ms: float = 2000.0) -> list[dict]:
        """Merge raw 400 ms rosu sections into larger display bins."""
        if not sections:
            return []
        raw_ms   = sections[0]["t_end"] - sections[0]["t_start"]
        bin_size = max(1, round(bin_ms / raw_ms))
        result   = []
        for i in range(0, len(sections), bin_size):
            batch = sections[i : i + bin_size]
            peak  = max(batch, key=lambda s: s["star_rating"])
            result.append({
                "t_start":     batch[0]["t_start"],
                "t_end":       batch[-1]["t_end"],
                "t_mid":       (batch[0]["t_start"] + batch[-1]["t_end"]) / 2.0,
                "star_rating": peak["star_rating"],
                "pattern":     peak["pattern"],
                "color":       peak["color"],
            })
        return result

    @staticmethod
    def _moving_avg(values: list[float], window: int = 3) -> list[float]:
        """Apply a symmetric moving average to smooth the line."""
        n = len(values)
        return [
            sum(values[max(0, i - window) : min(n, i + window + 1)])
            / len(values[max(0, i - window) : min(n, i + window + 1)])
            for i in range(n)
        ]

    # ── graph drawing ─────────────────────────────────────────────────────────

    def _draw_graph(self, sections: list[dict]) -> None:
        c = self._graph_canvas
        c.delete("all")
        if not sections:
            return

        # Canvas dimensions — use configured values before window is fully mapped
        W = c.winfo_width()
        H = c.winfo_height()
        if W <= 1:
            W = _GRAPH_W
        if H <= 1:
            H = _GRAPH_H

        # Left padding wide enough for "99.9" label; right/top/bottom minimal
        PAD_L, PAD_R, PAD_T, PAD_B = 28, 4, 6, 6
        gw = W - PAD_L - PAD_R   # drawable width
        gh = H - PAD_T - PAD_B   # drawable height
        baseline = PAD_T + gh

        # Bin into 2 s windows, compute Y-axis ceiling from raw peak,
        # then smooth the curve so it isn't cluttered
        sections  = self._bin_sections(sections, bin_ms=2000.0)
        stars_raw = [s["star_rating"] for s in sections]
        max_stars = max(stars_raw, default=1.0) or 1.0   # true peak for Y-axis
        stars_sm  = self._moving_avg(stars_raw, window=3)
        for s, v in zip(sections, stars_sm):
            s["star_rating"] = v
        t_start   = sections[0]["t_start"]
        t_end     = sections[-1]["t_end"]
        total_dur = (t_end - t_start) or 1

        def tx(t: float) -> float:
            return PAD_L + (t - t_start) / total_dur * gw

        def dy(d: float) -> float:
            return baseline - d / max_stars * gh

        # ── Y-axis: 4 evenly-spaced ticks with ★ labels ───────────────────────
        axis_font = ("Segoe UI", 6)
        n_ticks   = 4
        for i in range(n_ticks + 1):
            frac  = i / n_ticks
            val   = frac * max_stars
            y_pos = dy(val)
            label = f"{val:.1f}"

            # horizontal grid line (dim)
            c.create_line(PAD_L, y_pos, W - PAD_R, y_pos,
                          fill="#1e1e30", width=1)

            # tick mark on the Y axis
            c.create_line(PAD_L - 3, y_pos, PAD_L, y_pos,
                          fill=TEXT_DIM, width=1)

            # label (right-aligned against the axis)
            c.create_text(PAD_L - 5, y_pos,
                          text=label, anchor="e",
                          fill=TEXT_DIM, font=axis_font)

        # Y-axis spine
        c.create_line(PAD_L, PAD_T, PAD_L, baseline,
                      fill=BORDER, width=1)

        # baseline rule
        c.create_line(PAD_L, baseline, W - PAD_R, baseline,
                      fill=BORDER, width=1)

        pts = [(tx(s["t_mid"]), dy(s["star_rating"]), s["color"])
               for s in sections]

        for i in range(len(pts) - 1):
            x1, y1, col1 = pts[i]
            x2, y2, _    = pts[i + 1]
            # Thin filled trapezoid under this segment (subtle shading)
            c.create_polygon(x1, baseline, x1, y1, x2, y2, x2, baseline,
                             fill=col1, outline="", stipple="gray12")
            # Line with Bezier smoothing
            c.create_line(x1, y1, x2, y2,
                          fill=col1, width=2, smooth=True)

    # ── drag helpers ──────────────────────────────────────────────────────────

    def _bind_drag(self, widget: tk.Widget) -> None:
        widget.bind("<Button-1>",  self._drag_start)
        widget.bind("<B1-Motion>", self._drag_move)

    def _drag_start(self, event: tk.Event) -> None:
        self._drag_x = event.x_root - self._root.winfo_x()
        self._drag_y = event.y_root - self._root.winfo_y()

    def _drag_move(self, event: tk.Event) -> None:
        self._root.geometry(f"+{event.x_root - self._drag_x}+{event.y_root - self._drag_y}")

    # ── run ───────────────────────────────────────────────────────────────────

    def run(self) -> None:
        self._root.mainloop()
