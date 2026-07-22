import json
import math
import os
import sys
import tkinter as tk
from xml.sax.saxutils import escape
from dataclasses import dataclass, field
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Dict, List, Optional, Set, Tuple

try:
    from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageTk
except ImportError:
    Image = None
    ImageDraw = None
    ImageFont = None
    ImageOps = None
    ImageTk = None

APP_TITLE = "PAP Editor"

# --- Modern flat colour palette ---------------------------------------------
CANVAS_BG = "#f8fafc"          # light slate canvas
SIDEBAR_BG = "#0f172a"         # deep slate sidebar
PALETTE_BG = SIDEBAR_BG        # kept for backwards references
PALETTE_FG = "#f8fafc"
PALETTE_CARD = "#1e293b"
PALETTE_CARD_LINE = "#334155"
PALETTE_MUTED = "#94a3b8"
GRID_COLOR = "#e6ebf2"
ACCENT = "#2563eb"             # selection accent
HIGHLIGHT = ACCENT
ARROW_COLOR = "#111111"
NODE_BORDER = "#111111"
TEXT_COLOR = "#111111"
STATUS_BG = "#e2e8f0"

# fill / border colour per block type (matches the PNGs in /Bilder)
NODE_STYLE = {
    "Start":          ("#b3b3b3", NODE_BORDER),
    "Stop":           ("#b3b3b3", NODE_BORDER),
    "Funktion":       ("#ea0034", NODE_BORDER),
    "Anweisung":      ("#ea0034", NODE_BORDER),
    "Entscheidung":   ("#00b43e", NODE_BORDER),
    "Verzweigung zu": ("#ffffff", NODE_BORDER),
    "Schleife":       ("#ffb700", NODE_BORDER),
    "Schleife zu":    ("#ffb700", NODE_BORDER),
}
DEFAULT_STYLE = ("#ffffff", NODE_BORDER)

# shape/form per block type (keyed by template label)
NODE_SHAPE = {
    "Start":          "terminator",
    "Stop":           "terminator",
    "Funktion":       "subroutine",
    "Anweisung":      "rect",
    "Entscheidung":   "diamond",
    "Verzweigung zu": "connector",
    "Schleife":       "loop_start",
    "Schleife zu":    "loop_end",
}

NODE_TYPES = [
    ("Start", "terminator", "Bilder/Start.png"),
    ("Stop", "terminator", "Bilder/Stop.png"),
    ("Funktion", "subroutine", "Bilder/Funktion.png"),
    ("Anweisung", "rect", "Bilder/Anweisung.png"),
    ("Entscheidung", "diamond", "Bilder/Verzweigung_auf.png"),
    ("Verzweigung zu", "connector", "Bilder/Verzweigung_zu.png"),
    ("Schleife", "loop_start", "Bilder/Schleife_auf.png"),
    ("Schleife zu", "loop_end", "Bilder/Schleife_zu.png"),
]


# shapes that never carry a caption
UNLABELED_SHAPES = {"connector", "loop_end"}


def shape_of(node: "Node") -> str:
    return NODE_SHAPE.get(node.template_label, node.kind or "rect")


def rounded_rect_points(x1: float, y1: float, x2: float, y2: float, r: float) -> List[float]:
    r = max(0.0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    return [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]

NODE_W = 104
NODE_H = 44
PALETTE_ITEM_H = 74
PORT_RADIUS = 6
SELECTION_MARGIN = 8
GRID_SIZE = 40
PALETTE_IMAGE_BOUNDS = (96, 38)
CANVAS_IMAGE_BOUNDS = (104, 44)


def center_of_bbox(bbox: Tuple[float, float, float, float]) -> Tuple[float, float]:
    x1, y1, x2, y2 = bbox
    return (x1 + x2) / 2, (y1 + y2) / 2


def rect_points(x: float, y: float, w: float, h: float) -> List[float]:
    return [x - w / 2, y - h / 2, x + w / 2, y + h / 2]


def diamond_points(x: float, y: float, w: float, h: float) -> List[float]:
    return [x, y - h / 2, x + w / 2, y, x, y + h / 2, x - w / 2, y]


def hex_points(x: float, y: float, w: float, h: float) -> List[float]:
    dx = w * 0.18
    return [x - w / 2 + dx, y - h / 2, x + w / 2 - dx, y - h / 2, x + w / 2, y,
            x + w / 2 - dx, y + h / 2, x - w / 2 + dx, y + h / 2, x - w / 2, y]


def _chamfer(w: float, h: float) -> float:
    return min(w * 0.14, h * 0.5, 16)


def loop_start_points(x: float, y: float, w: float, h: float) -> List[float]:
    # rectangle with the two top corners cut off (Schleife auf)
    x1, y1, x2, y2 = x - w / 2, y - h / 2, x + w / 2, y + h / 2
    c = _chamfer(w, h)
    return [x1 + c, y1, x2 - c, y1, x2, y1 + c, x2, y2, x1, y2, x1, y1 + c]


def loop_end_points(x: float, y: float, w: float, h: float) -> List[float]:
    # rectangle with the two bottom corners cut off (Schleife zu)
    x1, y1, x2, y2 = x - w / 2, y - h / 2, x + w / 2, y + h / 2
    c = _chamfer(w, h)
    return [x1, y1, x2, y1, x2, y2 - c, x2 - c, y2, x1 + c, y2, x1, y2 - c]


PORT_NORMAL = {"top": (0, -1), "bottom": (0, 1), "left": (-1, 0), "right": (1, 0)}


def orthogonal_points(start: Tuple[float, float], source_port: str,
                      waypoints: List[Tuple[float, float]],
                      end: Tuple[float, float], target_port: str) -> List[Tuple[float, float]]:
    """Route a connector using only horizontal/vertical segments (90° bends).

    The line leaves the source along its port axis and enters the target along
    its port axis with as few corners as possible: a straight line when the
    ports line up, a single right-angle corner for a side branch, or one Z when
    both ports share the same axis. User waypoints become pass-through corners.
    """
    s_axis = "v" if source_port in ("top", "bottom") else "h"
    t_axis = "v" if target_port in ("top", "bottom") else "h"
    pts: List[Tuple[float, float]] = [start]

    def connect(a: Tuple[float, float], b: Tuple[float, float], lead: str,
                arrive: Optional[str] = None) -> List[Tuple[float, float]]:
        ax, ay = a
        bx, by = b
        if abs(ax - bx) < 1 or abs(ay - by) < 1:
            return [(bx, by)]
        axis = arrive if arrive is not None else lead
        if axis == "v":  # final sub-move vertical → go horizontal first
            return [(bx, ay), (bx, by)]
        return [(ax, by), (bx, by)]  # final sub-move horizontal → go vertical first

    if not waypoints:
        ax, ay = start
        bx, by = end
        if abs(ax - bx) < 1 or abs(ay - by) < 1:
            pts.append(end)
        elif s_axis == t_axis:  # same axis → one Z with a mid line
            if s_axis == "v":
                mid = (ay + by) / 2
                pts += [(ax, mid), (bx, mid), end]
            else:
                mid = (ax + bx) / 2
                pts += [(mid, ay), (mid, by), end]
        elif s_axis == "v":  # leave top/bottom, enter a side port
            pts += [(ax, by), end]
        else:                # leave a side port, enter top/bottom
            pts += [(bx, ay), end]
    else:
        anchors = list(waypoints) + [end]
        lead = s_axis
        for i, b in enumerate(anchors):
            arrive = ("v" if t_axis == "v" else "h") if i == len(anchors) - 1 else None
            pts += connect(pts[-1], b, lead, arrive)
            px, py = pts[-2]
            qx, qy = pts[-1]
            lead = "v" if abs(px - qx) < 1 else "h"

    out: List[Tuple[float, float]] = [pts[0]]
    for p in pts[1:]:
        if abs(p[0] - out[-1][0]) > 0.5 or abs(p[1] - out[-1][1]) > 0.5:
            out.append(p)
    return out


def paint_node(canvas: tk.Canvas, node: "Node", outline: str, width: int, hole_bg: str) -> None:
    """Draw a node's shape (colour + form from the /Bilder look) onto any canvas."""
    fill, _ = NODE_STYLE.get(node.template_label, DEFAULT_STYLE)
    x, y, w, h = node.x, node.y, node.width, node.height
    x1, y1, x2, y2 = x - w / 2, y - h / 2, x + w / 2, y + h / 2
    shape = shape_of(node)
    if shape == "terminator":
        canvas.create_polygon(rounded_rect_points(x1, y1, x2, y2, h / 2), fill=fill, outline=outline, width=width, smooth=True)
    elif shape == "diamond":
        canvas.create_polygon(diamond_points(x, y, w, h), fill=fill, outline=outline, width=width)
    elif shape == "connector":
        d = min(w, h)
        canvas.create_oval(x - d / 2, y - d / 2, x + d / 2, y + d / 2, fill=hole_bg, outline=outline, width=max(2, width))
    elif shape == "loop_start":
        canvas.create_polygon(loop_start_points(x, y, w, h), fill=fill, outline=outline, width=width)
    elif shape == "loop_end":
        canvas.create_polygon(loop_end_points(x, y, w, h), fill=fill, outline=outline, width=width)
    elif shape == "subroutine":
        canvas.create_rectangle(x1, y1, x2, y2, fill=fill, outline=outline, width=width)
        canvas.create_line(x1 + 10, y1, x1 + 10, y2, fill=outline, width=width)
        canvas.create_line(x2 - 10, y1, x2 - 10, y2, fill=outline, width=width)
    else:
        canvas.create_rectangle(x1, y1, x2, y2, fill=fill, outline=outline, width=width)
    if shape not in UNLABELED_SHAPES:
        canvas.create_text(x, y, text=node.label, fill=TEXT_COLOR, font=("Helvetica", 11, "bold"), width=w - 18)


@dataclass
class Node:
    id: int
    kind: str
    label: str
    x: float
    y: float
    width: float = NODE_W
    height: float = NODE_H
    image_rel: str = ""
    template_label: str = ""
    subdiagram: str = ""
    text_anchor: str = "center"

    def bbox(self) -> Tuple[float, float, float, float]:
        return (self.x - self.width / 2, self.y - self.height / 2, self.x + self.width / 2, self.y + self.height / 2)

    def ports(self) -> Dict[str, Tuple[float, float]]:
        x1, y1, x2, y2 = self.bbox()
        return {
            "top": ((x1 + x2) / 2, y1),
            "bottom": ((x1 + x2) / 2, y2),
            "left": (x1, (y1 + y2) / 2),
            "right": (x2, (y1 + y2) / 2),
        }

    def shape_points(self) -> List[float]:
        if self.kind == "rect":
            return rect_points(self.x, self.y, self.width, self.height)
        if self.kind == "diamond":
            return diamond_points(self.x, self.y, self.width, self.height)
        if self.kind == "hex":
            return hex_points(self.x, self.y, self.width, self.height)
        return rect_points(self.x, self.y, self.width, self.height)

    def kind_text(self) -> str:
        return self.label or self.kind.capitalize()


@dataclass
class Arrow:
    id: int
    source_id: int
    source_port: str
    target_id: int
    target_port: str
    waypoints: List[Tuple[float, float]] = field(default_factory=list)
    label: str = ""


class PapEditor(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1400x900")
        self.minsize(1180, 760)

        self.nodes: Dict[int, Node] = {}
        self.arrows: Dict[int, Arrow] = {}
        self.selected_node_ids: Set[int] = set()
        self.selected_arrow_id: Optional[int] = None
        self.drag_node_id: Optional[int] = None
        self.drag_offset: Tuple[float, float] = (0, 0)
        self.drag_snapshot: Optional[str] = None
        self.drag_moved = False
        self.rubber_band: Optional[Tuple[float, float, float, float]] = None
        self.connection_source: Optional[Tuple[int, str]] = None
        self.temp_arrow_id: Optional[int] = None
        self.temp_arrow_target: Optional[Tuple[float, float]] = None
        self.palette_drag_kind: Optional[Tuple[str, str, str]] = None
        self.palette_preview_id: Optional[int] = None
        self.palette_preview_label_id: Optional[int] = None
        self.next_node_id = 1
        self.next_arrow_id = 1
        self.current_file: Optional[str] = None
        self.grid_size = GRID_SIZE
        self.undo_stack: List[str] = []
        self.redo_stack: List[str] = []
        self.context_stack: List[dict] = []      # geöffnete Funktionen (Drill-in)
        self.context_title = "Hauptprogramm"
        self.palette_images: Dict[str, tk.PhotoImage] = {}
        self.canvas_images: Dict[str, tk.PhotoImage] = {}
        self.export_images: Dict[str, object] = {}
        self.image_sizes: Dict[str, Tuple[int, int]] = {}
        # bei einer mit PyInstaller gepackten App liegen die Ressourcen in sys._MEIPASS
        self.base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))

        self._load_images()
        self._build_ui()
        self._bind_events()
        self._redraw()

    def _load_images(self) -> None:
        for label, _, rel in NODE_TYPES:
            path = os.path.join(self.base_dir, rel)
            if os.path.exists(path):
                try:
                    if Image is not None and ImageTk is not None:
                        source = Image.open(path).convert("RGBA")
                        self.export_images[rel] = source
                        palette_image = ImageOps.contain(source.copy(), PALETTE_IMAGE_BOUNDS, method=Image.Resampling.LANCZOS)
                        canvas_image = ImageOps.contain(source.copy(), CANVAS_IMAGE_BOUNDS, method=Image.Resampling.LANCZOS)
                        self.palette_images[label] = ImageTk.PhotoImage(palette_image)
                        self.canvas_images[label] = ImageTk.PhotoImage(canvas_image)
                        self.image_sizes[rel] = canvas_image.size
                    else:
                        self.palette_images[label] = tk.PhotoImage(file=path)
                        self.canvas_images[label] = tk.PhotoImage(file=path)
                        self.image_sizes[rel] = (NODE_W, NODE_H)
                except tk.TclError:
                    pass

    def _build_ui(self) -> None:
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        self.left = tk.Frame(self, bg=SIDEBAR_BG, width=252)
        self.left.grid(row=0, column=0, sticky="nsew")
        self.left.grid_propagate(False)

        self.right = tk.Frame(self, bg=CANVAS_BG)
        self.right.grid(row=0, column=1, sticky="nsew")
        self.right.rowconfigure(1, weight=1)
        self.right.columnconfigure(0, weight=1)

        title = tk.Label(self.left, text="PAP Editor", bg=SIDEBAR_BG, fg=PALETTE_FG, font=("Helvetica", 19, "bold"))
        title.pack(anchor="w", padx=18, pady=(20, 2))
        subtitle = tk.Label(self.left, text="Programmablaufplan-Designer", bg=SIDEBAR_BG, fg=PALETTE_MUTED, font=("Helvetica", 9))
        subtitle.pack(anchor="w", padx=18, pady=(0, 14))

        section = tk.Label(self.left, text="BAUSTEINE", bg=SIDEBAR_BG, fg=PALETTE_MUTED, font=("Helvetica", 9, "bold"))
        section.pack(anchor="w", padx=18, pady=(0, 6))

        palette_frame = tk.Frame(self.left, bg=SIDEBAR_BG)
        palette_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.palette = tk.Canvas(palette_frame, bg=SIDEBAR_BG, highlightthickness=0, width=236)
        palette_scrollbar = tk.Scrollbar(palette_frame, orient="vertical", command=self.palette.yview)
        self.palette.configure(yscrollcommand=palette_scrollbar.set)
        self.palette.pack(side="left", fill="both", expand=True)
        palette_scrollbar.pack(side="right", fill="y")
        self.palette.bind("<MouseWheel>", lambda e: self.palette.yview_scroll(int(-e.delta / 40) or (-1 if e.delta > 0 else 1), "units"))
        self.palette.bind("<Button-4>", lambda e: self.palette.yview_scroll(-1, "units"))
        self.palette.bind("<Button-5>", lambda e: self.palette.yview_scroll(1, "units"))

        grid_frame = tk.Frame(self.left, bg=SIDEBAR_BG)
        grid_frame.pack(fill="x", padx=16, pady=(6, 4))
        self.show_grid = tk.BooleanVar(value=True)
        tk.Checkbutton(
            grid_frame, text="Raster", variable=self.show_grid, command=self._redraw,
            bg=SIDEBAR_BG, fg=PALETTE_FG, selectcolor=SIDEBAR_BG, activebackground=SIDEBAR_BG,
            activeforeground=PALETTE_FG, highlightthickness=0, bd=0, font=("Helvetica", 10, "bold"),
        ).pack(side="left")
        self.grid_size_var = tk.IntVar(value=self.grid_size)
        tk.Spinbox(
            grid_frame, from_=10, to=100, increment=5, width=4, textvariable=self.grid_size_var,
            command=self._on_grid_size_change, justify="center",
        ).pack(side="right")
        tk.Label(grid_frame, text="px", bg=SIDEBAR_BG, fg=PALETTE_MUTED, font=("Helvetica", 9)).pack(side="right", padx=(0, 4))

        button_bar = tk.Frame(self.left, bg=SIDEBAR_BG)
        button_bar.pack(fill="x", padx=12, pady=(4, 14))

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Sidebar.TButton", padding=(10, 9), font=("Helvetica", 11), relief="flat",
                        background="#334155", foreground=PALETTE_FG, borderwidth=0)
        style.map("Sidebar.TButton", background=[("active", "#475569")])
        style.configure("Accent.TButton", padding=(10, 9), font=("Helvetica", 11, "bold"), relief="flat",
                        background=ACCENT, foreground="#ffffff", borderwidth=0)
        style.map("Accent.TButton", background=[("active", "#4f46e5")])

        for text, command, kind in [
            ("Diagramm prüfen", self.check_diagram, "Accent.TButton"),
            ("Neu", self.new_diagram, "Sidebar.TButton"),
            ("Laden", self.load_diagram, "Sidebar.TButton"),
            ("Speichern", self.save_diagram, "Sidebar.TButton"),
            ("PNG export", self.export_png, "Sidebar.TButton"),
            ("JPG export", self.export_jpg, "Sidebar.TButton"),
            ("SVG kopieren", self.copy_svg, "Sidebar.TButton"),
            ("SVG export", self.export_svg, "Sidebar.TButton"),
        ]:
            ttk.Button(button_bar, text=text, command=command, style=kind).pack(fill="x", pady=3)

        hint = tk.Label(
            self.left,
            text="Mehrfachauswahl: Rahmen ziehen · Shift-Klick\n"
                 "Kopieren ⌘/Strg+C · Einfügen ⌘/Strg+V\n"
                 "SVG kopieren ⌘/Strg+Shift+C · Undo ⌘/Strg+Z\n"
                 "Funktion: Doppelklick · Zurück: Esc · Löschen: Entf",
            bg=SIDEBAR_BG, fg=PALETTE_MUTED, justify="left", font=("Helvetica", 8),
        )
        hint.pack(anchor="w", padx=16, pady=(0, 12))

        topbar = tk.Frame(self.right, bg=STATUS_BG)
        topbar.grid(row=0, column=0, columnspan=2, sticky="ew")
        topbar.columnconfigure(2, weight=1)
        self.back_button = ttk.Button(topbar, text="← Zurück", command=self.close_function, style="Sidebar.TButton")
        self.breadcrumb = tk.StringVar(value=self.context_title)
        tk.Label(topbar, textvariable=self.breadcrumb, bg=STATUS_BG, fg="#0f172a",
                 padx=12, pady=5, font=("Helvetica", 11, "bold")).grid(row=0, column=1, sticky="w")
        self.status = tk.StringVar(value="Bereit")
        tk.Label(topbar, textvariable=self.status, anchor="e", bg=STATUS_BG, fg="#475569",
                 padx=12, pady=5, font=("Helvetica", 10)).grid(row=0, column=2, sticky="e")

        self.canvas = tk.Canvas(self.right, bg=CANVAS_BG, highlightthickness=0, scrollregion=(0, 0, 5000, 5000))
        self.canvas.grid(row=1, column=0, sticky="nsew")
        xbar = tk.Scrollbar(self.right, orient="horizontal", command=self.canvas.xview)
        ybar = tk.Scrollbar(self.right, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=xbar.set, yscrollcommand=ybar.set)
        xbar.grid(row=2, column=0, sticky="ew")
        ybar.grid(row=1, column=1, sticky="ns")

        self._draw_palette()

    def _bind_events(self) -> None:
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)
        self.canvas.bind("<Double-Button-1>", self.on_canvas_double_click)
        self.canvas.bind("<Button-3>", self.on_canvas_right_click)
        self.canvas.bind("<Motion>", self.on_canvas_motion)
        self.canvas.bind("<Delete>", self.delete_selected)
        self.canvas.bind("<BackSpace>", self.delete_selected)
        self.canvas.focus_set()
        self.bind_all("<B1-Motion>", self.on_global_drag, add="+")
        self.bind_all("<ButtonRelease-1>", self.on_global_release, add="+")

        for seq in ("<Control-c>", "<Command-c>"):
            self.bind_all(seq, self.copy_selection)
        for seq in ("<Control-v>", "<Command-v>"):
            self.bind_all(seq, self.paste_selection)
        for seq in ("<Control-z>", "<Command-z>"):
            self.bind_all(seq, self.undo)
        for seq in ("<Control-y>", "<Command-y>", "<Control-Shift-z>", "<Command-Shift-z>"):
            self.bind_all(seq, self.redo)
        for seq in ("<Control-a>", "<Command-a>"):
            self.bind_all(seq, self.select_all)
        for seq in ("<Control-Shift-C>", "<Command-Shift-C>"):
            self.bind_all(seq, self.copy_svg)
        self.bind_all("<Escape>", self.close_function)

        self.palette.bind("<Button-1>", self.on_palette_click)
        self.palette.bind("<B1-Motion>", self.on_palette_drag)
        self.palette.bind("<ButtonRelease-1>", self.on_palette_release)
        self.palette.bind("<Double-Button-1>", self.on_palette_double_click)

    def _create_start_scene(self) -> None:
        start = self.add_node("Start", "terminator", "Start", 350, 120, image_rel="Bilder/Start.png")
        middle = self.add_node("Funktion", "subroutine", "Schritt 1", 350, 280, image_rel="Bilder/Funktion.png")
        stop = self.add_node("Stop", "terminator", "Stop", 350, 440, image_rel="Bilder/Stop.png")
        self.add_arrow_between(start.id, "bottom", middle.id, "top")
        self.add_arrow_between(middle.id, "bottom", stop.id, "top")

    def _draw_palette(self) -> None:
        self.palette.delete("all")
        y = 12
        card_h = 62
        self.palette_items: List[Tuple[float, float, float, float, Tuple[str, str, str]]] = []
        for label, kind, rel in NODE_TYPES:
            x1, y1, x2, y2 = 12, y, 224, y + card_h
            self.palette.create_polygon(rounded_rect_points(x1, y1, x2, y2, 10), fill=PALETTE_CARD, outline=PALETTE_CARD_LINE, width=1, smooth=True)
            self._draw_palette_shape(kind, label, 44, (y1 + y2) / 2)
            self.palette.create_text(84, (y1 + y2) / 2 - 8, anchor="w", fill=PALETTE_FG, font=("Helvetica", 11, "bold"), text=label)
            self.palette.create_text(84, (y1 + y2) / 2 + 10, anchor="w", fill=PALETTE_MUTED, font=("Helvetica", 8), text="ziehen · doppelklick")
            self.palette_items.append((x1, y1, x2, y2, (label, kind, rel)))
            y += card_h + 8
        self.palette.config(scrollregion=(0, 0, 236, max(y, 500)))

    def _draw_palette_shape(self, kind: str, label: str, cx: float, cy: float) -> None:
        fill, border = NODE_STYLE.get(label, DEFAULT_STYLE)
        shape = NODE_SHAPE.get(label, kind)
        w, h = 48, 26
        x1, y1, x2, y2 = cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
        if shape == "terminator":
            self.palette.create_polygon(rounded_rect_points(x1, y1, x2, y2, h / 2), fill=fill, outline=border, width=2, smooth=True)
        elif shape == "diamond":
            self.palette.create_polygon(diamond_points(cx, cy, w, h + 8), fill=fill, outline=border, width=2)
        elif shape == "connector":
            d = 20
            self.palette.create_oval(cx - d / 2, cy - d / 2, cx + d / 2, cy + d / 2, fill=PALETTE_CARD, outline="#e5e7eb", width=2)
        elif shape == "loop_start":
            self.palette.create_polygon(loop_start_points(cx, cy, w, h), fill=fill, outline=border, width=2)
        elif shape == "loop_end":
            self.palette.create_polygon(loop_end_points(cx, cy, w, h), fill=fill, outline=border, width=2)
        elif shape == "subroutine":
            self.palette.create_rectangle(x1, y1, x2, y2, fill=fill, outline=border, width=2)
            self.palette.create_line(x1 + 6, y1, x1 + 6, y2, fill=border, width=2)
            self.palette.create_line(x2 - 6, y1, x2 - 6, y2, fill=border, width=2)
        else:
            self.palette.create_rectangle(x1, y1, x2, y2, fill=fill, outline=border, width=2)

    def _redraw(self) -> None:
        self.canvas.delete("all")
        self._occupied = self._occupied_ports()
        self._draw_grid()
        for arrow in self.arrows.values():
            if arrow.id == -1:
                continue
            self._draw_arrow(arrow)
        for node in self.nodes.values():
            self._draw_node(node)
        self._draw_temp_arrow()
        if self.rubber_band:
            x1, y1, x2, y2 = self.rubber_band
            self.canvas.create_rectangle(x1, y1, x2, y2, outline=ACCENT, width=1, dash=(3, 3), fill="")
        self._update_status()

    def _update_status(self) -> None:
        self.status.set(f"Knoten: {len(self.nodes)}   Verbindungen: {len(self.arrows)}   Datei: {os.path.basename(self.current_file) if self.current_file else 'unbenannt'}")

    def _draw_node(self, node: Node) -> None:
        _, border = NODE_STYLE.get(node.template_label, DEFAULT_STYLE)
        selected = node.id in self.selected_node_ids
        outline = ACCENT if selected else border
        width = 3 if selected else 2
        if selected:
            x1, y1, x2, y2 = node.bbox()
            self.canvas.create_rectangle(x1 - 6, y1 - 6, x2 + 6, y2 + 6, outline=ACCENT, width=1, dash=(3, 3))
        paint_node(self.canvas, node, outline, width, CANVAS_BG)
        self._draw_ports(node)

    def _allowed_ports(self, node: Node) -> List[str]:
        # Verzweigung auf/zu verzweigen bzw. führen nur nach rechts zusammen
        if shape_of(node) in ("diamond", "connector"):
            ports = ["top", "bottom", "right"]
        else:
            ports = ["top", "bottom"]
        if node.template_label == "Start":          # Programmstart: kein Eingang oben
            ports = [p for p in ports if p != "top"]
        elif node.template_label == "Stop":         # Programmende: kein Ausgang unten
            ports = [p for p in ports if p != "bottom"]
        return ports

    def _occupied_ports(self) -> Set[Tuple[int, str]]:
        occ: Set[Tuple[int, str]] = set()
        for arrow in self.arrows.values():
            occ.add((arrow.source_id, arrow.source_port))
            occ.add((arrow.target_id, arrow.target_port))
        return occ

    def _draw_grid(self) -> None:
        if not self.show_grid.get():
            return
        step = self.grid_size
        x1 = int(self.canvas.canvasx(0))
        y1 = int(self.canvas.canvasy(0))
        x2 = int(self.canvas.canvasx(self.canvas.winfo_width()))
        y2 = int(self.canvas.canvasy(self.canvas.winfo_height()))
        start_x = x1 - (x1 % step)
        start_y = y1 - (y1 % step)
        for x in range(start_x, x2 + step, step):
            self.canvas.create_line(x, y1, x, y2, fill=GRID_COLOR)
        for y in range(start_y, y2 + step, step):
            self.canvas.create_line(x1, y, x2, y, fill=GRID_COLOR)

    def _draw_ports(self, node: Node) -> None:
        ports = node.ports()
        occupied = getattr(self, "_occupied", set())
        for name in self._allowed_ports(node):
            if (node.id, name) in occupied:      # verbundene Ports ausblenden
                continue
            px, py = ports[name]
            self.canvas.create_oval(px - PORT_RADIUS, py - PORT_RADIUS, px + PORT_RADIUS, py + PORT_RADIUS, fill="#ffffff", outline=ACCENT, width=1)

    def _arrow_route(self, arrow: Arrow) -> Optional[List[Tuple[float, float]]]:
        source = self.nodes.get(arrow.source_id)
        target = self.nodes.get(arrow.target_id)
        if not source or not target:
            return None
        start = source.ports()[arrow.source_port]
        end = target.ports()[arrow.target_port]
        return orthogonal_points(start, arrow.source_port, list(arrow.waypoints), end, arrow.target_port)

    def _arrow_label_pos(self, route: List[Tuple[float, float]]) -> Tuple[float, float]:
        # midpoint of the longest segment reads best for a right-angled path
        best_len, best = -1.0, route[len(route) // 2]
        for (ax, ay), (bx, by) in zip(route, route[1:]):
            seg = abs(bx - ax) + abs(by - ay)
            if seg > best_len:
                best_len, best = seg, ((ax + bx) / 2, (ay + by) / 2)
        return best

    def _draw_arrow(self, arrow: Arrow, dashed: bool = False) -> None:
        route = self._arrow_route(arrow)
        if not route:
            return
        color = HIGHLIGHT if arrow.id == self.selected_arrow_id else ARROW_COLOR
        flat = [coord for point in route for coord in point]
        self.canvas.create_line(*flat, fill=color, width=2, arrow="last", smooth=False, dash=(5, 4) if dashed else None)
        if arrow.label:
            mx, my = self._arrow_label_pos(route)
            self.canvas.create_rectangle(mx - 3, my - 9, mx + 6 + 7 * len(arrow.label), my + 9, fill=CANVAS_BG, outline="")
            self.canvas.create_text(mx, my, text=arrow.label, fill=TEXT_COLOR, font=("Helvetica", 10, "bold"), anchor="w")

    def _draw_temp_arrow(self) -> None:
        if not self.connection_source or not self.temp_arrow_target:
            return
        source_id, source_port = self.connection_source
        source = self.nodes.get(source_id)
        if not source:
            return
        start = source.ports()[source_port]
        route = orthogonal_points(start, source_port, [], self.temp_arrow_target, "top")
        flat = [coord for point in route for coord in point]
        self.canvas.create_line(*flat, fill="#7c3aed", width=2, arrow="last", dash=(4, 4))

    def add_node(self, label: str, kind: str, text: str, x: float, y: float, image_rel: str = "") -> Node:
        x = self.snap(x)
        y = self.snap(y)
        width, height = self._image_size_for_rel(image_rel)
        node = Node(self.next_node_id, kind, text or label, x, y, width=width, height=height, image_rel=image_rel, template_label=label)
        self._fit_node_size(node)
        self.nodes[node.id] = node
        self.next_node_id += 1
        return node

    def _fit_node_size(self, node: Node) -> None:
        """Grow the block so its label fits the shape (diamonds taper, connectors are round)."""
        shape = shape_of(node)
        if shape == "connector":
            node.width = node.height = 26
            return
        if shape in UNLABELED_SHAPES:
            return
        text_w = len(node.label) * 8 + 24
        if shape == "diamond":
            node.width = max(node.width, self.snap(text_w * 1.7))
            node.height = max(node.height, 88)
        else:
            node.width = max(node.width, self.snap(text_w))

    def _node_image_key(self, node: Node) -> str:
        for label, _, rel in NODE_TYPES:
            if rel == node.image_rel:
                return label
        return ""

    def _image_size_for_rel(self, image_rel: str) -> Tuple[float, float]:
        return NODE_W, NODE_H

    def add_arrow_between(self, source_id: int, source_port: str, target_id: int, target_port: str) -> Optional[Arrow]:
        if source_id == target_id:
            return None
        source = self.nodes.get(source_id)
        target = self.nodes.get(target_id)
        if not source or not target:
            return None
        if target.y <= source.y - 20:
            return None
        if source_port == "top" or target_port == "bottom":
            return None
        if self._has_path(target_id, source_id):
            return None
        if source_port == "bottom" and target_port == "top" and target.y < source.y:
            return None
        arrow = Arrow(self.next_arrow_id, source_id, source_port, target_id, target_port)
        self.arrows[arrow.id] = arrow
        self.next_arrow_id += 1
        return arrow

    def _has_path(self, start_id: int, target_id: int) -> bool:
        seen = set()
        stack = [start_id]
        while stack:
            current = stack.pop()
            if current == target_id:
                return True
            if current in seen:
                continue
            seen.add(current)
            for arrow in self.arrows.values():
                if arrow.source_id == current:
                    stack.append(arrow.target_id)
        return False

    def _canvas_coords(self, event: tk.Event) -> Tuple[float, float]:
        return self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)

    def _on_grid_size_change(self) -> None:
        try:
            value = int(self.grid_size_var.get())
        except (tk.TclError, ValueError):
            return
        self.grid_size = max(5, min(200, value))
        for node in self.nodes.values():
            node.x = self.snap(node.x)
            node.y = self.snap(node.y)
        self._redraw()

    def snap(self, value: float) -> float:
        return round(value / self.grid_size) * self.grid_size

    def _overlaps_any(self, x: float, y: float, width: float, height: float, margin: float = 10) -> bool:
        x1, y1, x2, y2 = x - width / 2 - margin, y - height / 2 - margin, x + width / 2 + margin, y + height / 2 + margin
        for node in self.nodes.values():
            nx1, ny1, nx2, ny2 = node.bbox()
            if x1 < nx2 and x2 > nx1 and y1 < ny2 and y2 > ny1:
                return True
        return False

    def _find_free_spot(self, x: float, y: float, width: float, height: float) -> Tuple[float, float]:
        x, y = self.snap(x), self.snap(y)
        start_x = x
        row, col = 0, 0
        while self._overlaps_any(x, y, width, height):
            row += 1
            y += max(self.grid_size * 2, 80)
            if row % 8 == 0:
                col += 1
                row = 0
                x = self.snap(start_x + col * (width + self.grid_size * 2))
        return x, y

    def _hit_test_node(self, x: float, y: float) -> Optional[int]:
        for node in reversed(list(self.nodes.values())):
            x1, y1, x2, y2 = node.bbox()
            if x1 - SELECTION_MARGIN <= x <= x2 + SELECTION_MARGIN and y1 - SELECTION_MARGIN <= y <= y2 + SELECTION_MARGIN:
                return node.id
        return None

    def _nodes_in_rect(self, x0: float, y0: float, x1: float, y1: float) -> Set[int]:
        left, right = min(x0, x1), max(x0, x1)
        top, bottom = min(y0, y1), max(y0, y1)
        found: Set[int] = set()
        for node in self.nodes.values():
            nx1, ny1, nx2, ny2 = node.bbox()
            if left < nx2 and right > nx1 and top < ny2 and bottom > ny1:
                found.add(node.id)
        return found

    def _hit_test_port(self, node: Node, x: float, y: float) -> Optional[str]:
        ports = node.ports()
        for name in self._allowed_ports(node):
            px, py = ports[name]
            if math.hypot(px - x, py - y) <= 14:
                return name
        return None

    def _hit_test_arrow(self, x: float, y: float) -> Optional[int]:
        for arrow in reversed(list(self.arrows.values())):
            if self._distance_to_arrow(arrow, x, y) <= 8:
                return arrow.id
        return None

    def _distance_to_arrow(self, arrow: Arrow, x: float, y: float) -> float:
        route = self._arrow_route(arrow)
        if not route:
            return float("inf")
        best = float("inf")
        for (ax, ay), (bx, by) in zip(route, route[1:]):
            best = min(best, self._distance_to_segment(x, y, ax, ay, bx, by))
        return best

    def _distance_to_segment(self, px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
        dx = x2 - x1
        dy = y2 - y1
        if dx == 0 and dy == 0:
            return math.hypot(px - x1, py - y1)
        projection = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
        projection = max(0.0, min(1.0, projection))
        closest_x = x1 + projection * dx
        closest_y = y1 + projection * dy
        return math.hypot(px - closest_x, py - closest_y)

    def on_canvas_click(self, event: tk.Event) -> None:
        x, y = self._canvas_coords(event)
        shift = bool(event.state & 0x0001)
        if shift:
            arrow_id = self._hit_test_arrow(x, y)
            if arrow_id is not None:
                self._insert_bend_point(arrow_id, x, y)
                return
        node_id = self._hit_test_node(x, y)
        if node_id:
            self.selected_arrow_id = None
            node = self.nodes[node_id]
            port = self._hit_test_port(node, x, y)
            if port and not shift:
                self.selected_node_ids = {node_id}
                self.connection_source = (node_id, port)
                self._ensure_temp_arrow(node_id, port)
            else:
                if shift:
                    self.selected_node_ids ^= {node_id}
                elif node_id not in self.selected_node_ids:
                    self.selected_node_ids = {node_id}
                if node_id in self.selected_node_ids:
                    self.drag_node_id = node_id
                    self.drag_offset = (x - node.x, y - node.y)
                    self.drag_snapshot = self._serialize()
                    self.drag_moved = False
            self._redraw()
        else:
            if not shift:
                self.selected_node_ids = set()
            self.selected_arrow_id = self._hit_test_arrow(x, y)
            self.connection_source = None
            if self.selected_arrow_id is None:
                self.rubber_band = (x, y, x, y)
            self._redraw()

    def on_canvas_drag(self, event: tk.Event) -> None:
        x, y = self._canvas_coords(event)
        if self.drag_node_id and self.drag_node_id in self.nodes:
            node = self.nodes[self.drag_node_id]
            nx = self.snap(x - self.drag_offset[0])
            ny = self.snap(y - self.drag_offset[1])
            dx, dy = nx - node.x, ny - node.y
            if dx or dy:
                self.drag_moved = True
                for nid in self.selected_node_ids:
                    if nid in self.nodes:
                        self.nodes[nid].x += dx
                        self.nodes[nid].y += dy
            self._redraw()
        elif self.connection_source:
            self._update_temp_arrow(event)
        elif self.rubber_band:
            x0, y0, _, _ = self.rubber_band
            self.rubber_band = (x0, y0, x, y)
            self.selected_node_ids = self._nodes_in_rect(x0, y0, x, y)
            self._redraw()

    def on_canvas_release(self, event: tk.Event) -> None:
        if self.rubber_band:
            x0, y0, x1, y1 = self.rubber_band
            self.selected_node_ids = self._nodes_in_rect(x0, y0, x1, y1)
            self.rubber_band = None
            self._redraw()
        if self.drag_node_id:
            if self.drag_moved and self.drag_snapshot is not None:
                self.undo_stack.append(self.drag_snapshot)
                if len(self.undo_stack) > 100:
                    self.undo_stack.pop(0)
                self.redo_stack.clear()
            self.drag_node_id = None
            self.drag_snapshot = None
        if self.connection_source:
            x, y = self._canvas_coords(event)
            source_id, source_port = self.connection_source
            target_id = self._hit_test_node(x, y)
            if target_id and target_id != source_id:
                target = self.nodes[target_id]
                target_port = self._best_target_port(source_port, self.nodes[source_id], target)
                self._push_undo()
                created = self.add_arrow_between(source_id, source_port, target_id, target_port)
                if created is None:
                    self.undo_stack.pop()
                    messagebox.showwarning("Verbindung abgelehnt", "Diese Verbindung würde die Flussrichtung verletzen oder einen Zyklus erzeugen.")
            self.connection_source = None
            self.temp_arrow_id = None
            self.temp_arrow_target = None
            self._redraw()

    # ---- Funktionen als Unter-PAP (Drill-in im selben Editor) ----------
    def _update_context_ui(self) -> None:
        if not hasattr(self, "breadcrumb"):
            return
        crumbs = " › ".join([c["title"] for c in self.context_stack] + [self.context_title])
        self.breadcrumb.set(crumbs)
        if self.context_stack:
            self.back_button.grid(row=0, column=0, padx=(8, 0), pady=4)
        else:
            self.back_button.grid_remove()

    def _create_function_scene(self) -> None:
        start = self.add_node("Start", "terminator", "Start", 360, 120, image_rel="")
        stop = self.add_node("Stop", "terminator", "Stop", 360, 320, image_rel="")
        self.add_arrow_between(start.id, "bottom", stop.id, "top")

    def open_function(self, node: Node) -> None:
        self.context_stack.append({
            "nodes": self.nodes, "arrows": self.arrows,
            "next_node_id": self.next_node_id, "next_arrow_id": self.next_arrow_id,
            "node": node, "title": self.context_title,
        })
        self.nodes = {}
        self.arrows = {}
        self.next_node_id = 1
        self.next_arrow_id = 1
        if node.subdiagram:
            try:
                self._load_payload(json.loads(node.subdiagram))
            except (ValueError, TypeError):
                pass
        if not self.nodes:
            self._create_function_scene()
        self.context_title = f"Funktion: {node.label or 'unbenannt'}"
        self.selected_node_ids = set()
        self.selected_arrow_id = None
        self.undo_stack.clear()
        self.redo_stack.clear()
        self._update_context_ui()
        self._redraw()

    def close_function(self, event: Optional[tk.Event] = None) -> str:
        if not self.context_stack:
            return "break"
        parent = self.context_stack.pop()
        parent["node"].subdiagram = json.dumps(self._state_payload(), ensure_ascii=False)
        self.nodes = parent["nodes"]
        self.arrows = parent["arrows"]
        self.next_node_id = parent["next_node_id"]
        self.next_arrow_id = parent["next_arrow_id"]
        self.context_title = parent["title"]
        self.selected_node_ids = set()
        self.selected_arrow_id = None
        self.undo_stack.clear()
        self.redo_stack.clear()
        self._update_context_ui()
        self._redraw()
        return "break"

    def _return_to_root(self) -> None:
        while self.context_stack:
            self.close_function()

    def on_canvas_double_click(self, event: tk.Event) -> None:
        x, y = self._canvas_coords(event)
        node_id = self._hit_test_node(x, y)
        if node_id:
            node = self.nodes[node_id]
            if node.template_label == "Funktion":
                self.open_function(node)
                return
            if shape_of(node) in UNLABELED_SHAPES:
                return
            new_label = simpledialog.askstring("Symbol bearbeiten", "Inhalt des Symbols:", initialvalue=node.label, parent=self)
            if new_label is not None:
                self._push_undo()
                node.label = new_label.strip() or node.label
                self._fit_node_size(node)
                self._redraw()
            return
        arrow_id = self._hit_test_arrow(x, y)
        if arrow_id is not None:
            arrow = self.arrows[arrow_id]
            new_label = simpledialog.askstring("Verbindung beschriften", "Beschriftung der Verbindung:", initialvalue=arrow.label, parent=self)
            if new_label is not None:
                self._push_undo()
                arrow.label = new_label.strip()
                self._redraw()

    def on_canvas_right_click(self, event: tk.Event) -> None:
        x, y = self._canvas_coords(event)
        node_id = self._hit_test_node(x, y)
        if node_id:
            self.delete_node(node_id)
            return
        arrow_id = self._hit_test_arrow(x, y)
        if arrow_id is not None:
            self._edit_arrow_waypoints(arrow_id, x, y)

    def on_canvas_motion(self, event: tk.Event) -> None:
        if self.connection_source:
            self._update_temp_arrow(event)

    def _ensure_temp_arrow(self, node_id: int, port: str) -> None:
        self.temp_arrow_id = -1
        self.temp_arrow_target = self.nodes[node_id].ports()[port]
        self._redraw()

    def _update_temp_arrow(self, event: tk.Event) -> None:
        if not self.connection_source:
            return
        x, y = self._canvas_coords(event)
        self.temp_arrow_target = (x, y)
        self._redraw()

    def _best_target_port(self, source_port: str, source: Node, target: Node) -> str:
        # diamonds and the merge connector may also be entered from the right side
        if shape_of(target) not in ("diamond", "connector"):
            return "top" if target.y >= source.y else "bottom"
        if source.x - target.x > target.width / 2 + 4:   # source clearly to the right
            return "right"
        return "top" if target.y >= source.y else "bottom"

    def _insert_bend_point(self, arrow_id: int, x: float, y: float) -> None:
        arrow = self.arrows.get(arrow_id)
        if not arrow:
            return
        self._push_undo()
        arrow.waypoints.append((self.snap(x), self.snap(y)))
        self.selected_arrow_id = arrow_id
        self._redraw()

    def _edit_arrow_waypoints(self, arrow_id: int, default_x: float, default_y: float) -> None:
        arrow = self.arrows.get(arrow_id)
        if not arrow:
            return
        editor = tk.Toplevel(self)
        editor.title("Pfeil bearbeiten")
        editor.transient(self)
        editor.grab_set()
        editor.geometry("320x260")
        tk.Label(editor, text="Knickpunkte", font=("Helvetica", 12, "bold")).pack(anchor="w", padx=12, pady=(12, 6))
        listbox = tk.Listbox(editor)
        listbox.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        def refresh() -> None:
            listbox.delete(0, tk.END)
            for index, waypoint in enumerate(arrow.waypoints, start=1):
                listbox.insert(tk.END, f"{index}: {int(waypoint[0])}, {int(waypoint[1])}")

        def remove_selected() -> None:
            selection = listbox.curselection()
            if not selection:
                return
            arrow.waypoints.pop(selection[0])
            refresh()
            self._redraw()

        def add_here() -> None:
            arrow.waypoints.append((self.snap(default_x), self.snap(default_y)))
            refresh()
            self._redraw()

        button_bar = tk.Frame(editor)
        button_bar.pack(fill="x", padx=12, pady=(0, 12))
        tk.Button(button_bar, text="Punkt hinzufügen", command=add_here).pack(side="left", expand=True, fill="x", padx=(0, 6))
        tk.Button(button_bar, text="Punkt entfernen", command=remove_selected).pack(side="left", expand=True, fill="x")
        refresh()

    def on_global_drag(self, event: tk.Event) -> None:
        if not self.palette_drag_kind:
            return
        widget = self.winfo_containing(event.x_root, event.y_root)
        if widget is not self.canvas:
            return
        canvas_x = self.canvas.canvasx(event.x_root - self.canvas.winfo_rootx())
        canvas_y = self.canvas.canvasy(event.y_root - self.canvas.winfo_rooty())
        self.canvas.delete("drop_preview")
        self.canvas.create_rectangle(canvas_x - 60, canvas_y - 30, canvas_x + 60, canvas_y + 30, outline="#60a5fa", width=2, dash=(4, 3), tags=("drop_preview",))

    def on_global_release(self, event: tk.Event) -> None:
        if not self.palette_drag_kind:
            return
        widget = self.winfo_containing(event.x_root, event.y_root)
        if widget is self.canvas:
            canvas_x = self.canvas.canvasx(event.x_root - self.canvas.winfo_rootx())
            canvas_y = self.canvas.canvasy(event.y_root - self.canvas.winfo_rooty())
            width, height = self._image_size_for_rel(self.palette_drag_kind[2])
            x, y = self._find_free_spot(canvas_x, canvas_y, width, height)
            self._push_undo()
            node = self.add_node(self.palette_drag_kind[0], self.palette_drag_kind[1], self.palette_drag_kind[0], x, y, image_rel=self.palette_drag_kind[2])
            self.selected_node_ids = {node.id}
            self._redraw()
        self.palette_drag_kind = None
        self._clear_palette_preview()

    def _find_palette_item(self, x: float, y: float) -> Optional[Tuple[str, str, str]]:
        for x1, y1, x2, y2, data in getattr(self, "palette_items", []):
            if x1 <= x <= x2 and y1 <= y <= y2:
                return data
        return None

    def _palette_coords(self, event: tk.Event) -> Tuple[float, float]:
        return self.palette.canvasx(event.x), self.palette.canvasy(event.y)

    def on_palette_click(self, event: tk.Event) -> None:
        px, py = self._palette_coords(event)
        item = self._find_palette_item(px, py)
        if item:
            self.palette_drag_kind = item
            self._draw_palette_preview(px, py)

    def on_palette_drag(self, event: tk.Event) -> None:
        if self.palette_drag_kind:
            px, py = self._palette_coords(event)
            self._draw_palette_preview(px, py)

    def on_palette_release(self, event: tk.Event) -> None:
        self._clear_palette_preview()

    def on_palette_double_click(self, event: tk.Event) -> None:
        px, py = self._palette_coords(event)
        item = self._find_palette_item(px, py)
        if item:
            width, height = self._image_size_for_rel(item[2])
            visible_x = self.canvas.canvasx(self.canvas.winfo_width() / 2) or 500
            visible_y = self.canvas.canvasy(self.canvas.winfo_height() / 2) or 200
            x, y = self._find_free_spot(visible_x, visible_y, width, height)
            self._push_undo()
            node = self.add_node(item[0], item[1], item[0], x, y, image_rel=item[2])
            self.selected_node_ids = {node.id}
            self._redraw()

    def _draw_palette_preview(self, x: float, y: float) -> None:
        self._clear_palette_preview()
        self.palette_preview_id = self.palette.create_rectangle(x - 45, y - 20, x + 45, y + 20, outline="#93c5fd", width=2, dash=(4, 3))
        self.palette_preview_label_id = self.palette.create_text(x, y, text="Ziehe", fill="#bfdbfe", font=("Helvetica", 10, "bold"))

    def _clear_palette_preview(self) -> None:
        for item_id in [self.palette_preview_id, self.palette_preview_label_id]:
            if item_id:
                self.palette.delete(item_id)
        self.palette_preview_id = None
        self.palette_preview_label_id = None

    def delete_selected(self, event: Optional[tk.Event] = None) -> str:
        if not self.selected_node_ids and self.selected_arrow_id is None:
            return "break"
        self._push_undo()
        for node_id in list(self.selected_node_ids):
            self._remove_node(node_id)
        self.selected_node_ids = set()
        if self.selected_arrow_id is not None:
            self.arrows.pop(self.selected_arrow_id, None)
            self.selected_arrow_id = None
        self._redraw()
        return "break"

    def select_all(self, event: Optional[tk.Event] = None) -> str:
        self.selected_node_ids = set(self.nodes.keys())
        self.selected_arrow_id = None
        self._redraw()
        return "break"

    def _remove_node(self, node_id: int) -> None:
        self.nodes.pop(node_id, None)
        for arrow_id in [aid for aid, a in self.arrows.items() if a.source_id == node_id or a.target_id == node_id]:
            self.arrows.pop(arrow_id, None)

    def delete_node(self, node_id: int) -> None:
        self._push_undo()
        self._remove_node(node_id)
        self.selected_node_ids.discard(node_id)
        self._redraw()

    def new_diagram(self) -> None:
        self._return_to_root()
        if not self._confirm_discard():
            return
        self.context_stack = []
        self.context_title = "Hauptprogramm"
        self.nodes = {}
        self.arrows = {}
        self.next_node_id = 1
        self.next_arrow_id = 1
        self.current_file = None
        self.selected_node_ids = set()
        self.selected_arrow_id = None
        self.undo_stack.clear()
        self.redo_stack.clear()
        self._update_context_ui()
        self._redraw()

    def _confirm_discard(self) -> bool:
        if not self.nodes and not self.arrows:
            return True
        return messagebox.askyesno("Änderungen verwerfen?", "Das aktuelle Diagramm wird überschrieben.")

    def save_diagram(self) -> None:
        self._return_to_root()   # gesamte Hierarchie inkl. Funktionen sichern
        if self.current_file is None:
            path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("PAP Datei", "*.json")], title="Diagramm speichern")
            if not path:
                return
            self.current_file = path
        self._write_json(self.current_file)
        self._update_status()

    def load_diagram(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("PAP Datei", "*.json")], title="Diagramm laden")
        if not path:
            return
        self._return_to_root()
        if not self._confirm_discard():
            return
        self.context_stack = []
        self.context_title = "Hauptprogramm"
        self._read_json(path)
        self.selected_node_ids = set()
        self.selected_arrow_id = None
        self.current_file = path
        self.undo_stack.clear()
        self.redo_stack.clear()
        self._update_context_ui()
        self._redraw()

    def _state_payload(self) -> dict:
        return {
            "nodes": [dict(node.__dict__) for node in self.nodes.values()],
            "arrows": [dict(arrow.__dict__) for arrow in self.arrows.values() if arrow.id != -1],
            "next_node_id": self.next_node_id,
            "next_arrow_id": self.next_arrow_id,
        }

    def _load_payload(self, payload: dict) -> None:
        self.nodes.clear()
        self.arrows.clear()
        for item in payload.get("nodes", []):
            node = Node(**item)
            self.nodes[node.id] = node
        for item in payload.get("arrows", []):
            arrow = Arrow(**item)
            self.arrows[arrow.id] = arrow
        self.next_node_id = payload.get("next_node_id", max(self.nodes.keys(), default=0) + 1)
        self.next_arrow_id = payload.get("next_arrow_id", max(self.arrows.keys(), default=0) + 1)

    def _write_json(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(self._state_payload(), handle, ensure_ascii=False, indent=2)

    def _read_json(self, path: str) -> None:
        with open(path, "r", encoding="utf-8") as handle:
            self._load_payload(json.load(handle))

    # ---- undo / redo ---------------------------------------------------
    def _serialize(self) -> str:
        return json.dumps(self._state_payload(), ensure_ascii=False)

    def _push_undo(self) -> None:
        self.undo_stack.append(self._serialize())
        if len(self.undo_stack) > 100:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def _restore(self, snapshot: str) -> None:
        self._load_payload(json.loads(snapshot))
        self.selected_node_ids = {nid for nid in self.selected_node_ids if nid in self.nodes}
        self.selected_arrow_id = None
        self._redraw()

    def undo(self, event: Optional[tk.Event] = None) -> str:
        if not self.undo_stack:
            self.status.set("Nichts zum Rückgängigmachen")
            return "break"
        self.redo_stack.append(self._serialize())
        self._restore(self.undo_stack.pop())
        return "break"

    def redo(self, event: Optional[tk.Event] = None) -> str:
        if not self.redo_stack:
            return "break"
        self.undo_stack.append(self._serialize())
        self._restore(self.redo_stack.pop())
        return "break"

    # ---- copy / paste --------------------------------------------------
    def copy_selection(self, event: Optional[tk.Event] = None) -> str:
        if not self.selected_node_ids:
            return "break"
        ids = self.selected_node_ids
        payload = {
            "pap_clipboard": True,
            "nodes": [dict(self.nodes[nid].__dict__) for nid in ids if nid in self.nodes],
            "arrows": [dict(a.__dict__) for a in self.arrows.values()
                       if a.source_id in ids and a.target_id in ids],
        }
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status.set(f"{len(payload['nodes'])} Baustein(e) kopiert")
        return "break"

    def paste_selection(self, event: Optional[tk.Event] = None) -> str:
        try:
            text = self.clipboard_get()
            payload = json.loads(text)
        except (tk.TclError, ValueError):
            return "break"
        if not isinstance(payload, dict) or not payload.get("nodes"):
            return "break"
        self._push_undo()
        offset = self.grid_size if self.grid_size else 40
        id_map: Dict[int, int] = {}
        new_ids: Set[int] = set()
        for item in payload.get("nodes", []):
            item = dict(item)
            old_id = item.get("id")
            item["id"] = self.next_node_id
            item["x"] = self.snap(item.get("x", 0) + offset)
            item["y"] = self.snap(item.get("y", 0) + offset)
            try:
                node = Node(**item)
            except TypeError:
                continue
            self.nodes[node.id] = node
            id_map[old_id] = node.id
            new_ids.add(node.id)
            self.next_node_id += 1
        for item in payload.get("arrows", []):
            item = dict(item)
            src = id_map.get(item.get("source_id"))
            tgt = id_map.get(item.get("target_id"))
            if src is None or tgt is None:
                continue
            item["id"] = self.next_arrow_id
            item["source_id"] = src
            item["target_id"] = tgt
            item["waypoints"] = [(self.snap(wx + offset), self.snap(wy + offset)) for wx, wy in item.get("waypoints", [])]
            try:
                arrow = Arrow(**item)
            except TypeError:
                continue
            self.arrows[arrow.id] = arrow
            self.next_arrow_id += 1
        if new_ids:
            self.selected_node_ids = new_ids
            self.selected_arrow_id = None
            self.status.set(f"{len(new_ids)} Baustein(e) eingefügt")
            self._redraw()
        return "break"

    def check_diagram(self) -> None:
        issues: List[str] = []
        starts = [n for n in self.nodes.values() if n.template_label == "Start"]
        stops = [n for n in self.nodes.values() if n.template_label == "Stop"]
        if len(starts) != 1:
            issues.append(f"Es muss genau einen Start-Block geben (gefunden: {len(starts)}).")
        if not stops:
            issues.append("Es muss mindestens einen Stop-Block geben.")

        outgoing: Dict[int, List[Arrow]] = {}
        incoming: Dict[int, List[Arrow]] = {}
        for arrow in self.arrows.values():
            outgoing.setdefault(arrow.source_id, []).append(arrow)
            incoming.setdefault(arrow.target_id, []).append(arrow)

        for node in self.nodes.values():
            out_count = len(outgoing.get(node.id, []))
            in_count = len(incoming.get(node.id, []))
            if node.template_label == "Start":
                if out_count == 0:
                    issues.append(f"Start-Block '{node.label}' hat keine ausgehende Verbindung.")
                if in_count > 0:
                    issues.append(f"Start-Block '{node.label}' darf keine eingehende Verbindung haben.")
            elif node.template_label == "Stop":
                if in_count == 0:
                    issues.append(f"Stop-Block '{node.label}' hat keine eingehende Verbindung.")
                if out_count > 0:
                    issues.append(f"Stop-Block '{node.label}' darf keine ausgehende Verbindung haben.")
            elif node.template_label == "Entscheidung":
                if out_count < 2:
                    issues.append(f"Verzweigung '{node.label}' benötigt mindestens zwei Ausgänge (gefunden: {out_count}).")
                if in_count == 0:
                    issues.append(f"Verzweigung '{node.label}' hat keine eingehende Verbindung.")
            else:
                if in_count == 0:
                    issues.append(f"Block '{node.label}' ({node.template_label}) ist nicht erreichbar (keine eingehende Verbindung).")
                if out_count == 0:
                    issues.append(f"Block '{node.label}' ({node.template_label}) hat keinen Ausgang.")

        if starts:
            reachable = set()
            stack = [starts[0].id]
            while stack:
                current = stack.pop()
                if current in reachable:
                    continue
                reachable.add(current)
                for arrow in outgoing.get(current, []):
                    stack.append(arrow.target_id)
            for node in self.nodes.values():
                if node.id not in reachable:
                    issues.append(f"Block '{node.label}' ist vom Start aus nicht erreichbar.")
            for stop in stops:
                if stop.id not in reachable:
                    issues.append(f"Stop-Block '{stop.label}' wird nie erreicht.")

        if issues:
            messagebox.showwarning("Plausibilitätsprüfung", "Gefundene Probleme:\n\n" + "\n".join(f"- {i}" for i in issues))
        else:
            messagebox.showinfo("Plausibilitätsprüfung", "Keine Probleme gefunden. Der Algorithmus scheint plausibel.")

    def export_png(self) -> None:
        self._export_image("png")

    def export_jpg(self) -> None:
        self._export_image("jpeg")

    def _export_image(self, fmt: str) -> None:
        if Image is None:
            messagebox.showerror("Pillow fehlt", "Für den Export wird das Paket pillow benötigt.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=f".{fmt if fmt != 'jpeg' else 'jpg'}",
            filetypes=[("Bild", "*.png *.jpg *.jpeg")],
            title="Diagramm exportieren",
        )
        if not path:
            return
        image = self.render_to_image()
        if fmt == "jpeg":
            image = image.convert("RGB")
            image.save(path, quality=95)
        else:
            image.save(path)

    # ---- SVG (Vektor) für Affinity & Co. -------------------------------
    def copy_svg(self, event: Optional[tk.Event] = None) -> str:
        ids = self.selected_node_ids or set(self.nodes.keys())
        svg = self.render_to_svg(ids)
        if not svg:
            self.status.set("Nichts zum Kopieren")
            return "break"
        self.clipboard_clear()
        self.clipboard_append(svg)
        self.status.set(f"{len(ids)} Baustein(e) als SVG kopiert")
        return "break"

    def export_svg(self) -> None:
        svg = self.render_to_svg(set(self.nodes.keys()))
        if not svg:
            return
        path = filedialog.asksaveasfilename(defaultextension=".svg", filetypes=[("SVG", "*.svg")], title="Als SVG exportieren")
        if not path:
            return
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(svg)
        self._update_status()

    def render_to_svg(self, node_ids: Set[int]) -> Optional[str]:
        nodes = [self.nodes[i] for i in node_ids if i in self.nodes]
        if not nodes:
            return None
        arrows = [a for a in self.arrows.values() if a.source_id in node_ids and a.target_id in node_ids]
        xs = [n.x - n.width / 2 for n in nodes] + [n.x + n.width / 2 for n in nodes]
        ys = [n.y - n.height / 2 for n in nodes] + [n.y + n.height / 2 for n in nodes]
        routes = {a.id: self._arrow_route(a) for a in arrows}
        for route in routes.values():
            if route:
                xs += [p[0] for p in route]
                ys += [p[1] for p in route]
        pad = 24
        minx, miny = min(xs) - pad, min(ys) - pad
        w, h = max(xs) - minx + pad, max(ys) - miny + pad

        def tx(v: float) -> float:
            return round(v - minx, 1)

        def ty(v: float) -> float:
            return round(v - miny, 1)

        def poly(flat: List[float]) -> str:
            return " ".join(f"{tx(flat[i])},{ty(flat[i + 1])}" for i in range(0, len(flat), 2))

        out: List[str] = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" height="{h:.0f}" viewBox="0 0 {w:.0f} {h:.0f}">',
            '<defs><marker id="arrow" markerWidth="10" markerHeight="8" refX="8" refY="3" '
            'orient="auto" markerUnits="strokeWidth"><path d="M0,0 L8,3 L0,6 z" fill="#111111"/></marker></defs>',
        ]
        for a in arrows:
            route = routes.get(a.id)
            if not route:
                continue
            pts = " ".join(f"{tx(x)},{ty(y)}" for x, y in route)
            out.append(f'<polyline points="{pts}" fill="none" stroke="#111111" stroke-width="2" marker-end="url(#arrow)"/>')
            if a.label:
                mx, my = self._arrow_label_pos(route)
                out.append(f'<text x="{tx(mx) + 4}" y="{ty(my) - 4}" font-family="Helvetica" font-size="12" fill="#111111">{escape(a.label)}</text>')
        for node in nodes:
            out.append(self._svg_node(node, tx, ty, poly))
        out.append("</svg>")
        return "\n".join(out)

    def _svg_node(self, node: Node, tx, ty, poly) -> str:
        fill, border = NODE_STYLE.get(node.template_label, DEFAULT_STYLE)
        shape = shape_of(node)
        w, h = node.width, node.height
        x1, y1 = tx(node.x - w / 2), ty(node.y - h / 2)
        cx, cy = tx(node.x), ty(node.y)
        s: List[str] = []
        if shape == "terminator":
            s.append(f'<rect x="{x1}" y="{y1}" width="{w:.0f}" height="{h:.0f}" rx="{h / 2:.0f}" ry="{h / 2:.0f}" fill="{fill}" stroke="{border}" stroke-width="2"/>')
        elif shape == "diamond":
            s.append(f'<polygon points="{poly(diamond_points(node.x, node.y, w, h))}" fill="{fill}" stroke="{border}" stroke-width="2"/>')
        elif shape == "hex":
            s.append(f'<polygon points="{poly(hex_points(node.x, node.y, w, h))}" fill="{fill}" stroke="{border}" stroke-width="2"/>')
        elif shape == "loop_start":
            s.append(f'<polygon points="{poly(loop_start_points(node.x, node.y, w, h))}" fill="{fill}" stroke="{border}" stroke-width="2"/>')
        elif shape == "loop_end":
            s.append(f'<polygon points="{poly(loop_end_points(node.x, node.y, w, h))}" fill="{fill}" stroke="{border}" stroke-width="2"/>')
        elif shape == "connector":
            d = min(w, h)
            s.append(f'<circle cx="{cx}" cy="{cy}" r="{d / 2:.0f}" fill="#f8fafc" stroke="{border}" stroke-width="2"/>')
        elif shape == "subroutine":
            s.append(f'<rect x="{x1}" y="{y1}" width="{w:.0f}" height="{h:.0f}" fill="{fill}" stroke="{border}" stroke-width="2"/>')
            s.append(f'<line x1="{x1 + 10}" y1="{y1}" x2="{x1 + 10}" y2="{y1 + h}" stroke="{border}" stroke-width="2"/>')
            s.append(f'<line x1="{x1 + w - 10}" y1="{y1}" x2="{x1 + w - 10}" y2="{y1 + h}" stroke="{border}" stroke-width="2"/>')
        else:
            s.append(f'<rect x="{x1}" y="{y1}" width="{w:.0f}" height="{h:.0f}" fill="{fill}" stroke="{border}" stroke-width="2"/>')
        if shape not in UNLABELED_SHAPES and node.label:
            s.append(f'<text x="{cx}" y="{cy}" font-family="Helvetica" font-size="12" font-weight="bold" '
                     f'text-anchor="middle" dominant-baseline="central" fill="{TEXT_COLOR}">{escape(node.label)}</text>')
        return "\n".join(s)

    def render_to_image(self):
        width = max(1600, int(max((node.x + node.width for node in self.nodes.values()), default=1200) + 120))
        height = max(1200, int(max((node.y + node.height for node in self.nodes.values()), default=900) + 120))
        image = Image.new("RGBA", (width, height), (248, 250, 252, 255))
        draw = ImageDraw.Draw(image)
        font = self._load_font(15)
        small_font = self._load_font(12)
        draw.rectangle([0, 0, width, height], fill="#f8fafc")
        for arrow in self.arrows.values():
            source = self.nodes.get(arrow.source_id)
            target = self.nodes.get(arrow.target_id)
            if not source or not target:
                continue
            start = source.ports()[arrow.source_port]
            end = target.ports()[arrow.target_port]
            route = orthogonal_points(start, arrow.source_port, list(arrow.waypoints), end, arrow.target_port)
            flat = [coord for point in route for coord in point]
            draw.line(flat, fill="#111111", width=3, joint="curve")
            self._draw_arrow_head(draw, flat[-4], flat[-3], flat[-2], flat[-1])
            if arrow.label:
                mx, my = self._arrow_label_pos(route)
                draw.text((mx + 4, my - 9), arrow.label, fill="#111111", font=small_font)
        for node in self.nodes.values():
            fill, border = NODE_STYLE.get(node.template_label, DEFAULT_STYLE)
            x1, y1, x2, y2 = node.bbox()
            shape = shape_of(node)
            if shape == "terminator":
                draw.rounded_rectangle([x1, y1, x2, y2], radius=node.height / 2, fill=fill, outline=border, width=3)
            elif shape == "diamond":
                draw.polygon(diamond_points(node.x, node.y, node.width, node.height), fill=fill, outline=border, width=3)
            elif shape == "connector":
                d = min(node.width, node.height)
                draw.ellipse([node.x - d / 2, node.y - d / 2, node.x + d / 2, node.y + d / 2], fill="#f8fafc", outline=border, width=3)
            elif shape == "loop_start":
                draw.polygon(loop_start_points(node.x, node.y, node.width, node.height), fill=fill, outline=border, width=3)
            elif shape == "loop_end":
                draw.polygon(loop_end_points(node.x, node.y, node.width, node.height), fill=fill, outline=border, width=3)
            elif shape == "subroutine":
                draw.rectangle([x1, y1, x2, y2], fill=fill, outline=border, width=3)
                draw.line([x1 + 11, y1, x1 + 11, y2], fill=border, width=2)
                draw.line([x2 - 11, y1, x2 - 11, y2], fill=border, width=2)
            else:
                draw.rectangle([x1, y1, x2, y2], fill=fill, outline=border, width=3)
            if shape not in UNLABELED_SHAPES:
                label = node.label
                text_bbox = draw.multiline_textbbox((0, 0), label, font=font, align="center")
                tw = text_bbox[2] - text_bbox[0]
                th = text_bbox[3] - text_bbox[1]
                draw.multiline_text((node.x - tw / 2, node.y - th / 2), label, fill="#111111", font=font, align="center")
        return image

    def _draw_arrow_head(self, draw, x1, y1, x2, y2):
        angle = math.atan2(y2 - y1, x2 - x1)
        length = 12
        spread = 0.45
        p1 = (x2, y2)
        p2 = (x2 - length * math.cos(angle - spread), y2 - length * math.sin(angle - spread))
        p3 = (x2 - length * math.cos(angle + spread), y2 - length * math.sin(angle + spread))
        draw.polygon([p1, p2, p3], fill="#111111")

    def _load_font(self, size: int):
        if ImageFont is None:
            return None
        for candidate in ["DejaVuSans.ttf", "/System/Library/Fonts/Supplemental/Arial Unicode.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf"]:
            try:
                return ImageFont.truetype(candidate, size=size)
            except Exception:
                continue
        return ImageFont.load_default()


def main() -> None:
    app = PapEditor()
    app.mainloop()


if __name__ == "__main__":
    main()
