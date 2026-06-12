#!/usr/bin/env python3
"""gui.py – line_gl pipeline GUI (tkinter, no external dependencies).

Tabs:
  1. Render   – pick scene, tweak hatching params, run bin/line_gl.exe, view SVG
  2. GCode    – run svg_to_gcode.py on the rendered SVG, configure paper/pen
  3. Paint    – run gcode_to_paint.py on a gcode file, configure paint-pot settings
"""

import json
import math
import os
import re
import subprocess
import sys
import threading
import tkinter as tk
import xml.etree.ElementTree as ET
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

# ---------------------------------------------------------------------------
# Paths (relative to repo root — gui.py lives in scripts/)
# ---------------------------------------------------------------------------
REPO = Path(__file__).resolve().parent.parent
SCENES_DIR  = REPO / "scenes"
SVG_DIR     = REPO / "svg"
GCODE_DIR   = REPO / "gcode"
BIN         = REPO / "bin" / "line_gl.exe"
SVG_TO_GCODE  = REPO / "scripts" / "svg_to_gcode.py"
GCODE_TO_PAINT = REPO / "scripts" / "gcode_to_paint.py"
GCODE_CONFIG  = REPO / "gcode_config.json"
PAINT_CONFIG  = REPO / "gcode_paint.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def load_json_safe(path) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def save_json(path, data: dict):
    with open(path, "w") as f:
        json.dump(data, f, indent=4)


def scene_list() -> list[str]:
    return sorted(p.name for p in SCENES_DIR.glob("*.json"))


def svg_for_scene(scene_name: str) -> Path:
    stem = Path(scene_name).stem
    return SVG_DIR / f"{stem}.svg"


def gcode_files() -> list[str]:
    return sorted(p.name for p in GCODE_DIR.glob("*.gcode"))


# ---------------------------------------------------------------------------
# SVG canvas renderer (draws <line> and simple <path> M/L elements)
# ---------------------------------------------------------------------------
class SvgCanvas(tk.Canvas):
    def __init__(self, master, **kw):
        super().__init__(master, bg="#f8f8f0", **kw)
        self._svg_path = None
        self.bind("<Configure>", lambda e: self._redraw())

    def load(self, svg_path):
        self._svg_path = svg_path
        self._redraw()

    def _redraw(self):
        self.delete("all")
        if not self._svg_path or not Path(self._svg_path).exists():
            self.create_text(self.winfo_width() // 2 or 200,
                             self.winfo_height() // 2 or 150,
                             text="No SVG", fill="#aaa", font=("Arial", 14))
            return
        try:
            self._render(self._svg_path)
        except Exception as exc:
            self.create_text(10, 10, anchor="nw", text=f"SVG error: {exc}",
                             fill="red", font=("Arial", 9))

    def _render(self, path):
        tree = ET.parse(path)
        root = tree.getroot()

        # parse SVG viewport
        w_attr = root.attrib.get("width",  "800")
        h_attr = root.attrib.get("height", "600")
        svg_w = float(re.sub(r"[^\d.]", "", w_attr))
        svg_h = float(re.sub(r"[^\d.]", "", h_attr))

        cw = max(self.winfo_width(),  100)
        ch = max(self.winfo_height(), 100)
        scale = min(cw / svg_w, ch / svg_h) * 0.97
        off_x = (cw - svg_w * scale) / 2
        off_y = (ch - svg_h * scale) / 2

        def sx(x): return off_x + x * scale
        def sy(y): return off_y + y * scale

        def rgb_str(stroke):
            if not stroke or stroke == "none":
                return "#000"
            m = re.match(r'rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)', stroke)
            if m:
                return "#{:02x}{:02x}{:02x}".format(int(m.group(1)),
                                                     int(m.group(2)),
                                                     int(m.group(3)))
            if re.match(r'#[0-9a-fA-F]{3,6}', stroke):
                return stroke
            return "#000"

        _PATH_TOKEN = re.compile(
            r'([MmLlHhVvZz])|'
            r'([-+]?(?:[0-9]*\.[0-9]+|[0-9]+)(?:[eE][-+]?[0-9]+)?)'
        )

        def draw_path(d, color, width):
            tokens = [m.group() for m in _PATH_TOKEN.finditer(d)]
            cx = cy = 0.0
            i = 0
            while i < len(tokens):
                cmd = tokens[i]
                if cmd in ('M', 'm'):
                    i += 1
                    x = float(tokens[i]); i += 1
                    y = float(tokens[i]); i += 1
                    cx, cy = (x, y) if cmd == 'M' else (cx + x, cy + y)
                elif cmd in ('L', 'l'):
                    i += 1
                    x = float(tokens[i]); i += 1
                    y = float(tokens[i]); i += 1
                    nx, ny = (x, y) if cmd == 'L' else (cx + x, cy + y)
                    self.create_line(sx(cx), sy(cy), sx(nx), sy(ny),
                                     fill=color, width=width)
                    cx, cy = nx, ny
                elif cmd in ('H', 'h'):
                    i += 1
                    x = float(tokens[i]); i += 1
                    nx = x if cmd == 'H' else cx + x
                    self.create_line(sx(cx), sy(cy), sx(nx), sy(cy),
                                     fill=color, width=width)
                    cx = nx
                elif cmd in ('V', 'v'):
                    i += 1
                    y = float(tokens[i]); i += 1
                    ny = y if cmd == 'V' else cy + y
                    self.create_line(sx(cx), sy(cy), sx(cx), sy(ny),
                                     fill=color, width=width)
                    cy = ny
                elif cmd in ('Z', 'z'):
                    i += 1
                else:
                    i += 1

        for elem in root.iter():
            tag = elem.tag.split("}")[-1]
            stroke = elem.attrib.get("stroke", "#000")
            try:
                sw = float(elem.attrib.get("stroke-width", "0.5"))
            except ValueError:
                sw = 0.5
            color = rgb_str(stroke)
            draw_w = max(0.5, sw * scale)

            if tag == "line":
                x1 = float(elem.attrib.get("x1", 0))
                y1 = float(elem.attrib.get("y1", 0))
                x2 = float(elem.attrib.get("x2", 0))
                y2 = float(elem.attrib.get("y2", 0))
                self.create_line(sx(x1), sy(y1), sx(x2), sy(y2),
                                 fill=color, width=draw_w)
            elif tag == "path":
                d = elem.attrib.get("d", "").strip()
                if d:
                    draw_path(d, color, draw_w)


# ---------------------------------------------------------------------------
# GCode canvas renderer  (G0 = dashed gray rapid, G1 = solid draw stroke)
# ---------------------------------------------------------------------------
_COORD_RE = re.compile(r'([XYZE])([-+]?[0-9]*\.?[0-9]+)', re.IGNORECASE)


def _parse_gcode_moves(path: str):
    """Return (draw_lines, rapid_lines) each as list of (x1,y1,x2,y2) in mm."""
    draw, rapid = [], []
    cx = cy = 0.0
    pen_down = False
    with open(path, encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.split(';')[0].strip().upper()
            if not line:
                continue
            # Detect pen up/down via M commands (M3/M5 style)
            if line.startswith('M5') or (line.startswith('M3') and 'S' in line):
                # M5 = pen up; M3 Sxx = pen down (S > 0 means down for most configs)
                # We'll track pen state by G0/G1 instead — simpler and reliable
                pass
            coords = {m.group(1): float(m.group(2)) for m in _COORD_RE.finditer(line)}
            nx = coords.get('X', cx)
            ny = coords.get('Y', cy)
            if line.startswith('G0'):
                if (cx, cy) != (nx, ny):
                    rapid.append((cx, cy, nx, ny))
                pen_down = False
                cx, cy = nx, ny
            elif line.startswith('G1'):
                if (cx, cy) != (nx, ny):
                    draw.append((cx, cy, nx, ny))
                pen_down = True
                cx, cy = nx, ny
    return draw, rapid


class GcodeCanvas(tk.Canvas):
    """Renders G0/G1 plotter gcode onto a tk.Canvas.

    - G1 draw moves: solid dark lines
    - G0 rapid moves: thin dashed gray lines
    Fit-to-view on every resize.
    """

    def __init__(self, master, **kw):
        super().__init__(master, bg="#fafaf5", **kw)
        self._gcode_path = None
        self._draw  = []   # list of (x1,y1,x2,y2)
        self._rapid = []
        self.bind("<Configure>", lambda e: self._redraw())

    def load(self, gcode_path: str):
        self._gcode_path = gcode_path
        self._draw, self._rapid = [], []
        if gcode_path and Path(gcode_path).exists():
            try:
                self._draw, self._rapid = _parse_gcode_moves(gcode_path)
            except Exception as exc:
                print(f"GcodeCanvas parse error: {exc}", file=sys.stderr)
        self._redraw()

    def _redraw(self):
        self.delete("all")
        all_lines = self._draw + self._rapid
        if not all_lines:
            self.create_text(max(self.winfo_width(), 100) // 2,
                             max(self.winfo_height(), 100) // 2,
                             text="No GCode", fill="#aaa", font=("Arial", 14))
            return

        xs = [x for x1, y1, x2, y2 in all_lines for x in (x1, x2)]
        ys = [y for x1, y1, x2, y2 in all_lines for y in (y1, y2)]
        bx0, bx1 = min(xs), max(xs)
        by0, by1 = min(ys), max(ys)
        bw = bx1 - bx0 or 1
        bh = by1 - by0 or 1

        cw = max(self.winfo_width(),  100)
        ch = max(self.winfo_height(), 100)
        RULER = 28
        scale = min((cw - RULER) / bw, (ch - RULER) / bh) * 0.95
        off_x = ((cw - RULER) - bw * scale) / 2 - bx0 * scale
        off_y = (ch - RULER - bh * scale) / 2 + RULER - by0 * scale

        def sx(x): return RULER + off_x + x * scale
        def sy(y): return off_y + (by0 + by1 - y) * scale  # flip Y: plotter Y-up → screen Y-down

        # ---- rulers ----
        rc = "#888888"
        font_small = ("Arial", 7)

        # horizontal ruler (X axis, top strip)
        self.create_rectangle(RULER, 0, cw, RULER, fill="#eeeeee", outline="")
        self.create_line(RULER, RULER, cw, RULER, fill=rc, width=1)

        # vertical ruler (Y axis, left strip)
        self.create_rectangle(0, 0, RULER, ch, fill="#eeeeee", outline="")
        self.create_line(RULER, 0, RULER, ch, fill=rc, width=1)

        # corner square
        self.create_rectangle(0, 0, RULER, RULER, fill="#dddddd", outline="")
        self.create_text(RULER // 2, RULER // 2, text="cm", fill=rc, font=font_small)

        # determine a sensible cm step so ticks aren't too dense
        px_per_cm = scale * 10.0  # 10 mm = 1 cm
        cm_step = 1
        for step in (2, 5, 10, 20, 50):
            if px_per_cm * step >= 30:
                cm_step = step
                break

        # X ticks: from floor(bx0/10)*10 up to bx1+extra, every cm_step cm
        x_start = int(bx0 / 10) * 10
        x_end   = int(bx1 / 10 + 2) * 10
        for x_mm in range(x_start, x_end, cm_step * 10):
            px = sx(x_mm)
            if px < RULER or px > cw:
                continue
            is_major = (x_mm % (cm_step * 10 * 5) == 0) or cm_step >= 5
            tick_h = 8 if is_major else 4
            self.create_line(px, RULER - tick_h, px, RULER, fill=rc, width=1)
            if is_major:
                self.create_text(px, RULER // 2, text=str(x_mm // 10),
                                 fill=rc, font=font_small, anchor="center")

        # Y ticks: from floor(by0/10)*10 up, drawn in screen-flipped position
        y_start = int(by0 / 10) * 10
        y_end   = int(by1 / 10 + 2) * 10
        for y_mm in range(y_start, y_end, cm_step * 10):
            py = sy(y_mm)
            if py < RULER or py > ch:
                continue
            is_major = (y_mm % (cm_step * 10 * 5) == 0) or cm_step >= 5
            tick_w = 8 if is_major else 4
            self.create_line(RULER - tick_w, py, RULER, py, fill=rc, width=1)
            if is_major:
                self.create_text(RULER // 2, py, text=str(y_mm // 10),
                                 fill=rc, font=font_small, anchor="center")

        # ---- toolpaths ----
        # Rapids first (behind draw strokes)
        for x1, y1, x2, y2 in self._rapid:
            self.create_line(sx(x1), sy(y1), sx(x2), sy(y2),
                             fill="#cccccc", width=0.5, dash=(3, 4))

        # Draw strokes
        for x1, y1, x2, y2 in self._draw:
            self.create_line(sx(x1), sy(y1), sx(x2), sy(y2),
                             fill="#1a1a1a", width=1.0)


# ---------------------------------------------------------------------------
# Reusable labelled entry / spinbox / checkbox helpers
# ---------------------------------------------------------------------------
def _label(parent, text, row, col=0, **kw):
    tk.Label(parent, text=text, anchor="w", **kw).grid(
        row=row, column=col, sticky="w", padx=(4, 2), pady=1)


def _entry(parent, var, row, col=1, width=9):
    e = tk.Entry(parent, textvariable=var, width=width)
    e.grid(row=row, column=col, sticky="ew", padx=4, pady=1)
    return e


def _check(parent, var, text, row, col=0):
    tk.Checkbutton(parent, text=text, variable=var).grid(
        row=row, column=col, columnspan=2, sticky="w", padx=4, pady=1)


# ---------------------------------------------------------------------------
# Tab 1 – Render
# ---------------------------------------------------------------------------
class RenderTab(ttk.Frame):
    def __init__(self, notebook):
        super().__init__(notebook)
        self._svg_path = None
        self._build_ui()

    def _build_ui(self):
        # ---- top-level paned layout: left panel | svg viewer ----
        paned = tk.PanedWindow(self, orient=tk.HORIZONTAL, sashwidth=5,
                               sashrelief=tk.RAISED)
        paned.pack(fill=tk.BOTH, expand=True)

        # ---- LEFT PANEL ----
        left = ttk.Frame(paned, width=230)
        paned.add(left, minsize=200)

        # Scene list
        ttk.Label(left, text="Scenes", font=("Arial", 10, "bold")).pack(
            pady=(8, 2), padx=6, anchor="w")

        list_frame = ttk.Frame(left)
        list_frame.pack(fill=tk.BOTH, padx=6, pady=2)
        sb = ttk.Scrollbar(list_frame, orient=tk.VERTICAL)
        self.scene_list = tk.Listbox(list_frame, yscrollcommand=sb.set,
                                     selectmode=tk.SINGLE, height=10,
                                     exportselection=False)
        sb.config(command=self.scene_list.yview)
        self.scene_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.scene_list.bind("<<ListboxSelect>>", self._on_scene_select)
        self._refresh_scene_list()

        # Hatching params
        ttk.Separator(left, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=6, pady=4)
        ttk.Label(left, text="Hatching", font=("Arial", 9, "bold")).pack(
            padx=6, anchor="w")

        hf = ttk.Frame(left)
        hf.pack(fill=tk.X, padx=6, pady=2)
        hf.columnconfigure(1, weight=1)

        self.v_max_spacing  = tk.StringVar(value="0.2")
        self.v_min_spacing  = tk.StringVar(value="0.05")
        self.v_shade_cutoff = tk.StringVar(value="0.95")
        self.v_epsilon      = tk.StringVar(value="0.001")
        self.v_min_col      = tk.StringVar(value="180,180,180")
        self.v_max_col      = tk.StringVar(value="60,60,60")

        rows = [
            ("max spacing",  self.v_max_spacing),
            ("min spacing",  self.v_min_spacing),
            ("shade cutoff", self.v_shade_cutoff),
            ("epsilon",      self.v_epsilon),
            ("min color",    self.v_min_col),
            ("max color",    self.v_max_col),
        ]
        for i, (lbl, var) in enumerate(rows):
            _label(hf, lbl, i)
            _entry(hf, var, i)

        ttk.Button(left, text="Apply to scene JSON",
                   command=self._apply_hatch).pack(fill=tk.X, padx=6, pady=(6, 2))
        self.gen_btn = ttk.Button(left, text="▶ Generate", command=self._run_generate)
        self.gen_btn.pack(fill=tk.X, padx=6, pady=(0, 4))

        # Log output
        ttk.Separator(left, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=6, pady=4)
        ttk.Label(left, text="Log", font=("Arial", 9, "bold")).pack(
            padx=6, anchor="w")
        self.log = scrolledtext.ScrolledText(left, height=6, font=("Consolas", 8),
                                             state=tk.DISABLED)
        self.log.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 6))

        # ---- RIGHT PANEL – SVG viewer ----
        right = ttk.Frame(paned)
        paned.add(right, minsize=400)

        self.svg_canvas = SvgCanvas(right)
        self.svg_canvas.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

    # -- helpers --
    def _refresh_scene_list(self):
        self.scene_list.delete(0, tk.END)
        for name in scene_list():
            self.scene_list.insert(tk.END, name)

    def _log(self, msg):
        self.log.config(state=tk.NORMAL)
        self.log.insert(tk.END, msg + "\n")
        self.log.see(tk.END)
        self.log.config(state=tk.DISABLED)

    def _selected_scene(self) -> str | None:
        sel = self.scene_list.curselection()
        if not sel:
            return None
        return self.scene_list.get(sel[0])

    def _on_scene_select(self, _event=None):
        name = self._selected_scene()
        if not name:
            return
        # Load hatch params from scene JSON into the left panel
        data = load_json_safe(SCENES_DIR / name)
        h = data.get("hatching", {})
        self.v_max_spacing .set(str(h.get("max_spacing",  0.2)))
        self.v_min_spacing .set(str(h.get("min_spacing",  0.05)))
        self.v_shade_cutoff.set(str(h.get("shade_cutoff", 0.95)))
        self.v_epsilon     .set(str(h.get("epsilon",      0.001)))
        mc = h.get("min_color", [180, 180, 180])
        xc = h.get("max_color", [60,  60,  60])
        self.v_min_col.set(",".join(str(v) for v in mc))
        self.v_max_col.set(",".join(str(v) for v in xc))
        # Show existing SVG if available
        svg = svg_for_scene(name)
        if svg.exists():
            self.svg_canvas.load(str(svg))
            self._svg_path = str(svg)

    def _apply_hatch(self):
        name = self._selected_scene()
        if not name:
            messagebox.showwarning("No scene", "Select a scene first.")
            return
        path = SCENES_DIR / name
        data = load_json_safe(path)

        def parse_col(s):
            parts = [int(x.strip()) for x in s.split(",")]
            return parts if len(parts) == 3 else [0, 0, 0]

        data["hatching"] = {
            "max_spacing":  float(self.v_max_spacing.get()),
            "min_spacing":  float(self.v_min_spacing.get()),
            "shade_cutoff": float(self.v_shade_cutoff.get()),
            "epsilon":      float(self.v_epsilon.get()),
            "min_color":    parse_col(self.v_min_col.get()),
            "max_color":    parse_col(self.v_max_col.get()),
        }
        save_json(path, data)
        self._log(f"Saved hatching to {name}")

    def _run_generate(self):
        name = self._selected_scene()
        if not name:
            messagebox.showwarning("No scene", "Select a scene first.")
            return
        if not BIN.exists():
            messagebox.showerror("Build missing",
                                 f"Executable not found:\n{BIN}\n\nRun 'make' first.")
            return
        self.gen_btn.config(state=tk.DISABLED)
        self._log(f"Generating {name} ...")

        def worker():
            try:
                result = subprocess.run(
                    [str(BIN), str(SCENES_DIR / name)],
                    capture_output=True, text=True, cwd=str(REPO)
                )
                out = (result.stdout + result.stderr).strip()
                self.after(0, lambda: self._log(out or "Done."))
                svg = svg_for_scene(name)
                if svg.exists():
                    self.after(0, lambda: self._load_svg(str(svg)))
            except Exception as exc:
                self.after(0, lambda: self._log(f"Error: {exc}"))
            finally:
                self.after(0, lambda: self.gen_btn.config(state=tk.NORMAL))

        threading.Thread(target=worker, daemon=True).start()

    def _load_svg(self, path):
        self._svg_path = path
        self.svg_canvas.load(path)

    def get_svg_path(self) -> str | None:
        return self._svg_path


# ---------------------------------------------------------------------------
# Tab 2 – SVG → GCode
# ---------------------------------------------------------------------------
class GcodeTab(ttk.Frame):
    def __init__(self, notebook, render_tab: RenderTab):
        super().__init__(notebook)
        self._render_tab = render_tab
        self._cfg = load_json_safe(GCODE_CONFIG)
        self._build_ui()

    def _build_ui(self):
        paned = tk.PanedWindow(self, orient=tk.HORIZONTAL, sashwidth=5,
                               sashrelief=tk.RAISED)
        paned.pack(fill=tk.BOTH, expand=True)

        # ---- LEFT ----
        left = ttk.Frame(paned, width=230)
        paned.add(left, minsize=200)

        ttk.Label(left, text="SVG → GCode", font=("Arial", 10, "bold")).pack(
            pady=(8, 2), padx=6, anchor="w")

        # SVG file selector
        sf = ttk.Frame(left)
        sf.pack(fill=tk.X, padx=6, pady=2)
        self.v_svg = tk.StringVar()
        ttk.Entry(sf, textvariable=self.v_svg, width=18).pack(
            side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(sf, text="…", width=2,
                   command=self._pick_svg).pack(side=tk.LEFT, padx=2)

        # Run button
        self.run_btn = ttk.Button(left, text="▶ Run svg_to_gcode",
                                  command=self._run)
        self.run_btn.pack(fill=tk.X, padx=6, pady=6)

        ttk.Separator(left, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=6, pady=4)
        ttk.Label(left, text="Paper & pen", font=("Arial", 9, "bold")).pack(
            padx=6, anchor="w")

        cf = ttk.Frame(left)
        cf.pack(fill=tk.X, padx=6, pady=2)
        cf.columnconfigure(1, weight=1)

        self.v_feed       = tk.StringVar(value=str(self._cfg.get("feed_rate",       3000)))
        self.v_rapid      = tk.StringVar(value=str(self._cfg.get("rapid_rate",      6000)))
        self.v_paper_w    = tk.StringVar(value=str(self._cfg.get("paper_width_mm",  105.0)))
        self.v_paper_h    = tk.StringVar(value=str(self._cfg.get("paper_height_mm", 148.0)))
        self.v_margin     = tk.StringVar(value=str(self._cfg.get("margin_mm",       10.0)))
        self.v_pen_cmd    = tk.StringVar(value=str(self._cfg.get("pen_up_cmd",      "M5")))
        self.v_pd_steps   = tk.StringVar(value=str(self._cfg.get("pen_down_steps",  5)))
        self.v_pd_start   = tk.StringVar(value=str(self._cfg.get("pen_down_start",  10)))
        self.v_pd_end     = tk.StringVar(value=str(self._cfg.get("pen_down_end",    30)))
        self.v_pd_dwell   = tk.StringVar(value=str(self._cfg.get("pen_down_dwell",  0.1)))
        self.v_min_seg    = tk.StringVar(value=str(self._cfg.get("min_segment_mm",  0.1)))
        self.v_flip_y     = tk.BooleanVar(value=bool(self._cfg.get("flip_y",        True)))
        self.v_opt_sort   = tk.BooleanVar(value=bool(self._cfg.get("optimize_sort", True)))
        self.v_opt_conn   = tk.BooleanVar(value=bool(self._cfg.get("optimize_connect", True)))
        self.v_opt_rev    = tk.BooleanVar(value=bool(self._cfg.get("optimize_reverse", True)))

        num_rows = [
            ("feed rate",     self.v_feed),
            ("rapid rate",    self.v_rapid),
            ("paper W (mm)",  self.v_paper_w),
            ("paper H (mm)",  self.v_paper_h),
            ("margin (mm)",   self.v_margin),
            ("pen up cmd",    self.v_pen_cmd),
            ("pen dn steps",  self.v_pd_steps),
            ("pen dn start",  self.v_pd_start),
            ("pen dn end",    self.v_pd_end),
            ("pen dn dwell",  self.v_pd_dwell),
            ("min seg (mm)",  self.v_min_seg),
        ]
        for i, (lbl, var) in enumerate(num_rows):
            _label(cf, lbl, i)
            _entry(cf, var, i)

        r = len(num_rows)
        _check(cf, self.v_flip_y,   "flip Y",    r);     r += 1
        _check(cf, self.v_opt_sort, "opt sort",  r);     r += 1
        _check(cf, self.v_opt_conn, "opt connect", r);   r += 1
        _check(cf, self.v_opt_rev,  "opt reverse", r)

        ttk.Button(left, text="Save config", command=self._save_cfg).pack(
            fill=tk.X, padx=6, pady=(6, 2))

        ttk.Separator(left, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=6, pady=4)
        ttk.Label(left, text="Log", font=("Arial", 9, "bold")).pack(
            padx=6, anchor="w")
        self.log = scrolledtext.ScrolledText(left, height=8, font=("Consolas", 8),
                                             state=tk.DISABLED)
        self.log.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 6))

        # ---- RIGHT – SVG preview + GCode preview tabs ----
        right = ttk.Frame(paned)
        paned.add(right, minsize=400)

        right_nb = ttk.Notebook(right)
        right_nb.pack(fill=tk.BOTH, expand=True)

        svg_frame = ttk.Frame(right_nb)
        self.svg_canvas = SvgCanvas(svg_frame)
        self.svg_canvas.pack(fill=tk.BOTH, expand=True)
        right_nb.add(svg_frame, text="SVG")

        gc_frame = ttk.Frame(right_nb)
        self.gcode_canvas = GcodeCanvas(gc_frame)
        self.gcode_canvas.pack(fill=tk.BOTH, expand=True)
        right_nb.add(gc_frame, text="GCode")

        self._right_nb = right_nb

    def on_tab_raised(self):
        """Called when this tab becomes visible — sync SVG from Render tab."""
        svg = self._render_tab.get_svg_path()
        if svg:
            self.v_svg.set(svg)
            self.svg_canvas.load(svg)

    def _pick_svg(self):
        p = filedialog.askopenfilename(initialdir=str(SVG_DIR),
                                       filetypes=[("SVG", "*.svg"), ("All", "*.*")])
        if p:
            self.v_svg.set(p)
            self.svg_canvas.load(p)

    def _log(self, msg):
        self.log.config(state=tk.NORMAL)
        self.log.insert(tk.END, msg + "\n")
        self.log.see(tk.END)
        self.log.config(state=tk.DISABLED)

    def _save_cfg(self):
        cfg = self._build_cfg()
        save_json(GCODE_CONFIG, cfg)
        self._log(f"Saved {GCODE_CONFIG.name}")

    def _build_cfg(self) -> dict:
        return {
            "feed_rate":        int(self.v_feed.get()),
            "rapid_rate":       int(self.v_rapid.get()),
            "paper_width_mm":   float(self.v_paper_w.get()),
            "paper_height_mm":  float(self.v_paper_h.get()),
            "margin_mm":        float(self.v_margin.get()),
            "pen_up_cmd":       self.v_pen_cmd.get(),
            "pen_down_steps":   int(self.v_pd_steps.get()),
            "pen_down_start":   int(self.v_pd_start.get()),
            "pen_down_end":     int(self.v_pd_end.get()),
            "pen_down_dwell":   float(self.v_pd_dwell.get()),
            "min_segment_mm":   float(self.v_min_seg.get()),
            "flip_y":           self.v_flip_y.get(),
            "optimize_sort":    self.v_opt_sort.get(),
            "optimize_connect": self.v_opt_conn.get(),
            "optimize_reverse": self.v_opt_rev.get(),
        }

    def _run(self):
        svg = self.v_svg.get()
        if not svg or not Path(svg).exists():
            messagebox.showwarning("No SVG", "Select a valid SVG file first.")
            return
        # write a temp config
        tmp_cfg = REPO / "_gui_gcode_cfg.json"
        save_json(tmp_cfg, self._build_cfg())

        self.run_btn.config(state=tk.DISABLED)
        self._log(f"Running svg_to_gcode on {Path(svg).name} ...")

        # Predict output gcode path (mirrors svg_to_gcode.py naming)
        svg_stem = Path(svg).stem
        expected_gcode = GCODE_DIR / f"{svg_stem}.gcode"

        def worker():
            try:
                result = subprocess.run(
                    [sys.executable, str(SVG_TO_GCODE), svg,
                     "--config", str(tmp_cfg)],
                    capture_output=True, text=True, cwd=str(REPO)
                )
                out = (result.stdout + result.stderr).strip()
                self.after(0, lambda: self._log(out or "Done."))
                if expected_gcode.exists():
                    self.after(0, lambda: self.gcode_canvas.load(str(expected_gcode)))
                    self.after(0, lambda: self._right_nb.select(1))  # switch to GCode tab
            except Exception as exc:
                self.after(0, lambda: self._log(f"Error: {exc}"))
            finally:
                self.after(0, lambda: self.run_btn.config(state=tk.NORMAL))

        threading.Thread(target=worker, daemon=True).start()


# ---------------------------------------------------------------------------
# Tab 3 – GCode → Paint
# ---------------------------------------------------------------------------
class PaintTab(ttk.Frame):
    def __init__(self, notebook):
        super().__init__(notebook)
        self._cfg = load_json_safe(PAINT_CONFIG)
        self._build_ui()

    def _build_ui(self):
        paned = tk.PanedWindow(self, orient=tk.HORIZONTAL, sashwidth=5,
                               sashrelief=tk.RAISED)
        paned.pack(fill=tk.BOTH, expand=True)

        # ---- LEFT ----
        left = ttk.Frame(paned, width=230)
        paned.add(left, minsize=200)

        ttk.Label(left, text="GCode → Paint", font=("Arial", 10, "bold")).pack(
            pady=(8, 2), padx=6, anchor="w")

        # GCode file list
        ttk.Label(left, text="GCode files", font=("Arial", 9)).pack(
            padx=6, anchor="w")
        lf = ttk.Frame(left)
        lf.pack(fill=tk.X, padx=6, pady=2)
        sb = ttk.Scrollbar(lf, orient=tk.VERTICAL)
        self.gcode_list = tk.Listbox(lf, yscrollcommand=sb.set,
                                     selectmode=tk.SINGLE, height=8,
                                     exportselection=False)
        sb.config(command=self.gcode_list.yview)
        self.gcode_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._refresh_gcode_list()

        self.run_btn = ttk.Button(left, text="▶ Run gcode_to_paint",
                                  command=self._run)
        self.run_btn.pack(fill=tk.X, padx=6, pady=6)

        ttk.Separator(left, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=6, pady=4)
        ttk.Label(left, text="Paint pot", font=("Arial", 9, "bold")).pack(
            padx=6, anchor="w")

        pf = ttk.Frame(left)
        pf.pack(fill=tk.X, padx=6, pady=2)
        pf.columnconfigure(1, weight=1)

        self.v_paint_x    = tk.StringVar(value=str(self._cfg.get("paint_x",           250.0)))
        self.v_paint_y    = tk.StringVar(value=str(self._cfg.get("paint_y",            10.0)))
        self.v_paint_r    = tk.StringVar(value=str(self._cfg.get("paint_radius",        5.0)))
        self.v_paint_dist = tk.StringVar(value=str(self._cfg.get("paint_distance_mm", 500.0)))
        self.v_paint_feed = tk.StringVar(value=str(self._cfg.get("paint_feed",        1000)))
        self.v_paint_spd  = tk.StringVar(value=str(self._cfg.get("paint_speed",       1000)))
        self.v_rapid      = tk.StringVar(value=str(self._cfg.get("rapid_rate",        6000)))
        self.v_in_up      = tk.StringVar(value=str(self._cfg.get("input_pen_up_cmd",  "M5")))
        self.v_pt_up      = tk.StringVar(value=str(self._cfg.get("paint_pen_up_cmd",  "M5")))
        self.v_dip_steps  = tk.StringVar(value=str(self._cfg.get("paint_dip_steps",    3)))
        self.v_dip_start  = tk.StringVar(value=str(self._cfg.get("paint_dip_start",   25)))
        self.v_dip_end    = tk.StringVar(value=str(self._cfg.get("paint_dip_end",     35)))
        self.v_dip_dwell  = tk.StringVar(value=str(self._cfg.get("paint_dip_dwell",  0.1)))

        paint_rows = [
            ("paint X (mm)",   self.v_paint_x),
            ("paint Y (mm)",   self.v_paint_y),
            ("paint radius",   self.v_paint_r),
            ("reload dist mm", self.v_paint_dist),
            ("paint feed",     self.v_paint_feed),
            ("paint speed",    self.v_paint_spd),
            ("rapid rate",     self.v_rapid),
            ("in pen-up cmd",  self.v_in_up),
            ("paint pen-up",   self.v_pt_up),
            ("dip steps",      self.v_dip_steps),
            ("dip start",      self.v_dip_start),
            ("dip end",        self.v_dip_end),
            ("dip dwell",      self.v_dip_dwell),
        ]
        for i, (lbl, var) in enumerate(paint_rows):
            _label(pf, lbl, i)
            _entry(pf, var, i)

        ttk.Button(left, text="Save config", command=self._save_cfg).pack(
            fill=tk.X, padx=6, pady=(6, 2))

        ttk.Separator(left, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=6, pady=4)
        ttk.Label(left, text="Log", font=("Arial", 9, "bold")).pack(
            padx=6, anchor="w")
        self.log = scrolledtext.ScrolledText(left, height=8, font=("Consolas", 8),
                                             state=tk.DISABLED)
        self.log.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 6))

        # ---- RIGHT – gcode canvas viewer ----
        right = ttk.Frame(paned)
        paned.add(right, minsize=400)

        ttk.Label(right, text="GCode preview", foreground="#888").pack(
            anchor="nw", padx=4, pady=2)
        self.gcode_canvas = GcodeCanvas(right)
        self.gcode_canvas.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self.gcode_list.bind("<<ListboxSelect>>", self._on_gcode_select)

    def _refresh_gcode_list(self):
        self.gcode_list.delete(0, tk.END)
        for name in gcode_files():
            self.gcode_list.insert(tk.END, name)

    def _on_gcode_select(self, _event=None):
        sel = self.gcode_list.curselection()
        if not sel:
            return
        name = self.gcode_list.get(sel[0])
        self.gcode_canvas.load(str(GCODE_DIR / name))

    def _log(self, msg):
        self.log.config(state=tk.NORMAL)
        self.log.insert(tk.END, msg + "\n")
        self.log.see(tk.END)
        self.log.config(state=tk.DISABLED)

    def _save_cfg(self):
        cfg = self._build_cfg()
        save_json(PAINT_CONFIG, cfg)
        self._log(f"Saved {PAINT_CONFIG.name}")

    def _build_cfg(self) -> dict:
        return {
            "paint_x":            float(self.v_paint_x.get()),
            "paint_y":            float(self.v_paint_y.get()),
            "paint_radius":       float(self.v_paint_r.get()),
            "paint_distance_mm":  float(self.v_paint_dist.get()),
            "paint_feed":         int(self.v_paint_feed.get()),
            "paint_speed":        int(self.v_paint_spd.get()),
            "rapid_rate":         int(self.v_rapid.get()),
            "input_pen_up_cmd":   self.v_in_up.get(),
            "paint_pen_up_cmd":   self.v_pt_up.get(),
            "paint_dip_steps":    int(self.v_dip_steps.get()),
            "paint_dip_start":    int(self.v_dip_start.get()),
            "paint_dip_end":      int(self.v_dip_end.get()),
            "paint_dip_dwell":    float(self.v_dip_dwell.get()),
        }

    def _run(self):
        sel = self.gcode_list.curselection()
        if not sel:
            messagebox.showwarning("No file", "Select a gcode file first.")
            return
        name = self.gcode_list.get(sel[0])
        in_path = GCODE_DIR / name
        stem = Path(name).stem
        out_path = GCODE_DIR / f"{stem}_paint.gcode"

        tmp_cfg = REPO / "_gui_paint_cfg.json"
        save_json(tmp_cfg, self._build_cfg())

        self.run_btn.config(state=tk.DISABLED)
        self._log(f"Running gcode_to_paint on {name} ...")

        def worker():
            try:
                result = subprocess.run(
                    [sys.executable, str(GCODE_TO_PAINT), str(in_path),
                     "--config", str(tmp_cfg), "-o", str(out_path)],
                    capture_output=True, text=True, cwd=str(REPO)
                )
                out = (result.stdout + result.stderr).strip()
                self.after(0, lambda: self._log(out or "Done."))
                self.after(0, self._refresh_gcode_list)
                if out_path.exists():
                    self.after(0, lambda: self.gcode_canvas.load(str(out_path)))
            except Exception as exc:
                self.after(0, lambda: self._log(f"Error: {exc}"))
            finally:
                self.after(0, lambda: self.run_btn.config(state=tk.NORMAL))

        threading.Thread(target=worker, daemon=True).start()


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("line_gl pipeline")
        self.geometry("1100x700")
        self.minsize(800, 500)

        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        self.render_tab = RenderTab(notebook)
        self.gcode_tab  = GcodeTab(notebook, self.render_tab)
        self.paint_tab  = PaintTab(notebook)

        notebook.add(self.render_tab, text="  Render  ")
        notebook.add(self.gcode_tab,  text="  SVG → GCode  ")
        notebook.add(self.paint_tab,  text="  GCode → Paint  ")

        notebook.bind("<<NotebookTabChanged>>", self._on_tab_change)

    def _on_tab_change(self, event):
        tab = event.widget.tab(event.widget.select(), "text").strip()
        if tab == "SVG → GCode":
            self.gcode_tab.on_tab_raised()


if __name__ == "__main__":
    app = App()
    app.mainloop()
