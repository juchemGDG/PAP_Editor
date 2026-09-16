import json
import math
import os
import re
import sys
import time
import tkinter as tk
from xml.sax.saxutils import escape
from dataclasses import dataclass, field
from tkinter import filedialog, font as tkfont, messagebox, simpledialog, ttk
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
    "Funktion":       ("#ec4f71", NODE_BORDER),
    "Anweisung":      ("#ec4f71", NODE_BORDER),
    "Entscheidung":   ("#5ecf87", NODE_BORDER),
    "Verzweigung zu": ("#ffffff", NODE_BORDER),
    "Schleife":       ("#fdcb4a", NODE_BORDER),
    "Schleife zu":    ("#fdcb4a", NODE_BORDER),
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


def _is_resizable(node) -> bool:
    """Runde Konnektoren behalten ihre Form – alle anderen Bloecke sind breitenverstellbar."""
    return node is not None and shape_of(node) != "connector"


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

NODE_FONT = ("Helvetica", 11, "bold")
LINE_H = 14           # Zeilenhöhe im Blocktext
MIN_NODE_W = 60       # kleinste manuell einstellbare Blockbreite
GRIP = 6              # halbe Kantenlänge des Breiten-Anfassers
BEND_RADIUS = 5       # Radius der Knickpunkt-Anfasser
APPROACH = 24         # Mindestlänge der Einmündung in einen Port
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


def wrap_lines(measure, text: str, max_w: float) -> List[str]:
    """Text in Zeilen zerlegen: erst harte Umbrueche (\\n, per Strg/Cmd+Enter
    eingegeben), dann zusaetzlich an Wortgrenzen, wenn die Breite nicht reicht.
    Identisch zu wrapLines() in web/static/pap.js."""
    lines: List[str] = []
    for para in str(text or "").split("\n"):
        current = ""
        for word in para.split(" "):
            candidate = f"{current} {word}" if current else word
            if measure(candidate) <= max_w or not current:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def approach_points(start: Tuple[float, float], waypoints: List[Tuple[float, float]],
                    end: Tuple[float, float], target_port: str) -> List[Tuple[float, float]]:
    """Sorgt dafuer, dass der Pfeil immer aus der zum Ziel-Port passenden
    Richtung einmuendet: oben von oben nach unten, unten von unten nach oben,
    rechts von rechts nach links. Liegt der letzte Knickpunkt auf der falschen
    Seite, wird ein zusaetzlicher (nicht gespeicherter) Umlenkpunkt ergaenzt.
    Identisch zu approachPoints() in web/static/pap.js."""
    points = [(float(px), float(py)) for px, py in waypoints]
    last = points[-1] if points else start
    ex, ey = end
    if target_port == "top" and last[1] <= ey - 1:
        return points
    if target_port == "bottom" and last[1] >= ey + 1:
        return points
    if target_port == "right" and last[0] >= ex + 1:
        return points
    if target_port == "left" and last[0] <= ex - 1:
        return points

    if target_port in ("top", "bottom"):
        direction = -1 if target_port == "top" else 1
        cx = last[0]
        if abs(cx - ex) < 1:                 # sonst liefe der Pfeil auf sich selbst zurueck
            cx = ex + APPROACH * 2
        points.append((cx, ey + direction * APPROACH))
    else:
        direction = 1 if target_port == "right" else -1
        cy = last[1]
        if abs(cy - ey) < 1:
            cy = ey + APPROACH * 2
        points.append((ex + direction * APPROACH, cy))
    return points


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
        # Tk bricht selbst an \n und – dank width – zusaetzlich an Wortgrenzen um
        canvas.create_text(x, y, text=node.label, fill=TEXT_COLOR, font=NODE_FONT, width=w - 18)


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
    manual_width: bool = False      # True: Breite wurde von Hand gesetzt und waechst nicht mehr mit

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


# ════════════════════════════════════════════════════════════════════════
# Plausibilitätsprüfung (Regelwerk für PAP / DIN 66001)
# ════════════════════════════════════════════════════════════════════════
#
# Jede Regel hat eine ID ("R01" …), einen Schweregrad ("error"/"warning") und
# erzeugt kurze, an die Schülerin/den Schüler gerichtete Meldungen auf
# Deutsch. Die Regeln orientieren sich am allgemeinen PAP-Regelkatalog,
# wurden aber an das Datenmodell dieses Editors angepasst. Folgende Regeln
# des allgemeinen Katalogs entfallen bewusst, weil es im Editor kein
# entsprechendes Konzept gibt:
#   R07  Block-IDs sind über das dict[id]-Modell technisch immer eindeutig.
#   R13  Es gibt keinen eigenständigen Seitenverweis-Konnektor; "Verzweigung
#        zu" übernimmt ausschließlich die Rolle des Verzweigungsendes.
#   (R16 ist umgesetzt: ein von Hand gezeichneter Rücksprung von einem
#    Schleife-zu-Block an einen weiter oben liegenden Schleifenanfang ist
#    erlaubt und wird nur als Hinweis gemeldet – siehe check_geometry_ports.)
#   R21  SESE wird nicht als eigene Prüfung umgesetzt, sondern ergibt sich
#        als Nebenprodukt der Verschachtelungsprüfung (R20/R22/R23): eine
#        Verletzung führt dort zu einer Meldung über nicht passende
#        Verschachtelung.
#   R32  Es gibt keinen eigenen Eingabe/Ausgabe-Blocktyp.
#   R33  Ein-Anweisung-pro-Block (Atomicity) wird bewusst nicht geprüft.
#   R34  Datenfluss-Analyse ("Variable vor Gebrauch zugewiesen") wird bewusst
#        nicht geprüft – zu viele Fehlalarme bei kurzen Schul-Beispielen.
#   R35  Ausgabe-auf-jedem-Pfad wird bewusst nicht geprüft.
#
# Zum Hinzufügen einer neuen Regel: eine Funktion `check_rXX_...(...)`
# schreiben, die eine `List[Finding]` zurückgibt, und den Aufruf in
# `evaluate_chart` ergänzen. Siehe README für Details.

ROLE_BY_TEMPLATE = {
    "Start": "start",
    "Stop": "stop",
    "Anweisung": "process",
    "Funktion": "subprocess",
    "Entscheidung": "decision",
    "Verzweigung zu": "branchEnd",
    "Schleife": "loopStart",
    "Schleife zu": "loopEnd",
}

ROLE_NAMES_DE = {
    "process": "Anweisungs",
    "loopStart": "Schleifen",
    "loopEnd": "Schleife-zu",
    "subprocess": "Funktions",
}

COMPARISON_OPS = ("==", "!=", "<=", ">=", "<", ">")
BOOL_WORDS = ("und", "oder", "nicht", "and", "or", "not", "&&", "||")
YES_WORDS = {"ja", "yes", "j", "y", "true", "wahr"}
NO_WORDS = {"nein", "no", "n", "false", "falsch"}
IDENT_RE = re.compile(r"[A-Za-z_]\w*")
ASSIGN_RE = re.compile(r":=|<-|(?<![=!<>])=(?!=)")
_STRING_LITERAL_RE = re.compile(r"'[^']*'|\"[^\"]*\"")
_STOPWORDS = {
    "und", "oder", "nicht", "and", "or", "not", "true", "false", "wahr", "falsch",
    "then", "dann", "if", "wenn", "sonst", "else", "ausgabe", "eingabe", "print",
    "input", "cout", "system", "out", "write", "gib", "aus", "schreibe", "lies",
    "einlesen",
}


def role_of(node: "Node") -> str:
    return ROLE_BY_TEMPLATE.get(node.template_label, "process")


_UNLABELED_ROLE_NAMES = {"branchEnd": "Verzweigung zu", "loopEnd": "Schleife zu"}


def _display_label(node: "Node") -> str:
    """Label for messages; falls back to a role name for intentionally unlabelled shapes."""
    if node.label and node.label.strip():
        # Zeilenumbrueche im Blocktext fuer Meldungen zu einer Zeile zusammenziehen
        return re.sub(r"\s*\n\s*", " ", node.label)
    return _UNLABELED_ROLE_NAMES.get(role_of(node), node.label or "?")


def split_assignment(text: str) -> Optional[Tuple[str, str]]:
    """Split a block label at its assignment operator (=, :=, <-), ignoring ==, !=, <=, >=."""
    match = ASSIGN_RE.search(text or "")
    if not match:
        return None
    return text[: match.start()], text[match.end() :]


def extract_identifiers(text: str) -> Set[str]:
    """Identifiers referenced in a label; text inside quotes is a literal, not a variable."""
    cleaned = _STRING_LITERAL_RE.sub(" ", text or "")
    return {ident for ident in IDENT_RE.findall(cleaned) if ident.lower() not in _STOPWORDS}


@dataclass
class Finding:
    rule: str
    severity: str  # "error" | "warning"
    message: str
    node_ids: List[int] = field(default_factory=list)
    arrow_ids: List[int] = field(default_factory=list)


def _build_edge_maps(nodes: Dict[int, "Node"], arrows: Dict[int, "Arrow"]) -> Tuple[Dict[int, List["Arrow"]], Dict[int, List["Arrow"]]]:
    outgoing: Dict[int, List[Arrow]] = {}
    incoming: Dict[int, List[Arrow]] = {}
    for arrow in arrows.values():
        if arrow.source_id in nodes and arrow.target_id in nodes:
            outgoing.setdefault(arrow.source_id, []).append(arrow)
            incoming.setdefault(arrow.target_id, []).append(arrow)
    return outgoing, incoming


# ---- A. Globale Struktur --------------------------------------------------

def check_r01_start(nodes: Dict[int, "Node"]) -> List[Finding]:
    starts = [n for n in nodes.values() if role_of(n) == "start"]
    if not starts:
        return [Finding("R01", "error", "Es gibt keinen Start-Block – jeder Ablauf braucht genau einen.", [], [])]
    if len(starts) > 1:
        return [Finding("R01", "error", f"Es gibt {len(starts)} Start-Blöcke – es darf nur genau einen geben.", [n.id for n in starts], [])]
    return []


def check_r02_stop_exists(nodes: Dict[int, "Node"]) -> List[Finding]:
    if not any(role_of(n) == "stop" for n in nodes.values()):
        return [Finding("R02", "error", "Es gibt keinen Stop-Block – jeder Ablauf muss enden.", [], [])]
    return []


def check_r03_multiple_stops(nodes: Dict[int, "Node"]) -> List[Finding]:
    stops = [n for n in nodes.values() if role_of(n) == "stop"]
    if len(stops) > 1:
        return [Finding(
            "R03", "warning",
            f"Es gibt {len(stops)} Stop-Blöcke – meist ist genau ein Stop-Block übersichtlicher.",
            [n.id for n in stops], [],
        )]
    return []


def check_r04_reachable_from_start(nodes: Dict[int, "Node"], outgoing: Dict[int, List["Arrow"]]) -> List[Finding]:
    starts = [n for n in nodes.values() if role_of(n) == "start"]
    if len(starts) != 1:
        return []
    reachable: Set[int] = set()
    stack = [starts[0].id]
    while stack:
        current = stack.pop()
        if current in reachable:
            continue
        reachable.add(current)
        for arrow in outgoing.get(current, []):
            stack.append(arrow.target_id)
    return [
        Finding("R04", "error", f"Der Block »{_display_label(n)}« ist vom Start aus nicht erreichbar.", [n.id], [])
        for n in nodes.values() if n.id not in reachable
    ]


def check_r05_reach_stop(nodes: Dict[int, "Node"], incoming: Dict[int, List["Arrow"]]) -> List[Finding]:
    stops = [n for n in nodes.values() if role_of(n) == "stop"]
    if not stops:
        return []
    can_reach_stop: Set[int] = set()
    stack = [s.id for s in stops]
    while stack:
        current = stack.pop()
        if current in can_reach_stop:
            continue
        can_reach_stop.add(current)
        for arrow in incoming.get(current, []):
            stack.append(arrow.source_id)
    return [
        Finding("R05", "error", f"Vom Block »{_display_label(n)}« aus wird kein Stop-Block mehr erreicht (Sackgasse).", [n.id], [])
        for n in nodes.values() if n.id not in can_reach_stop
    ]


def check_r06_connected(nodes: Dict[int, "Node"], arrows: Dict[int, "Arrow"]) -> List[Finding]:
    if not nodes:
        return []
    adjacency: Dict[int, Set[int]] = {}
    for arrow in arrows.values():
        if arrow.source_id in nodes and arrow.target_id in nodes:
            adjacency.setdefault(arrow.source_id, set()).add(arrow.target_id)
            adjacency.setdefault(arrow.target_id, set()).add(arrow.source_id)
    seen: Set[int] = set()
    stack = [next(iter(nodes))]
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        stack.extend(adjacency.get(current, ()))
    missing = [n for n in nodes.values() if n.id not in seen]
    return [
        Finding("R06", "error", f"Der Block »{_display_label(n)}« gehört zu einem vom restlichen Ablaufplan getrennten Teil.", [n.id], [])
        for n in missing
    ]


# ---- B. Verbindungen und Knotengrade --------------------------------------

def check_r08_dangling_edges(nodes: Dict[int, "Node"], arrows: Dict[int, "Arrow"]) -> List[Finding]:
    findings = []
    for arrow in arrows.values():
        if arrow.source_id not in nodes or arrow.target_id not in nodes:
            findings.append(Finding(
                "R08", "error",
                "Ein Pfeil verweist auf einen nicht (mehr) vorhandenen Block – die Datei scheint beschädigt zu sein.",
                [], [arrow.id],
            ))
    return findings


def check_node_degrees(nodes: Dict[int, "Node"], incoming: Dict[int, List["Arrow"]], outgoing: Dict[int, List["Arrow"]]) -> List[Finding]:
    """R10: Ein- und Ausgangsgrad muss zum Blocktyp passen."""
    findings = []
    for node in nodes.values():
        role = role_of(node)
        label = _display_label(node) or role
        in_count = len(incoming.get(node.id, []))
        out_count = len(outgoing.get(node.id, []))
        if role == "start":
            if in_count > 0:
                findings.append(Finding("R10", "error", f"Der Start-Block »{label}« darf keinen eingehenden Pfeil haben.", [node.id], []))
            if out_count == 0:
                findings.append(Finding("R10", "error", f"Der Start-Block »{label}« hat keinen ausgehenden Pfeil.", [node.id], []))
            elif out_count > 1:
                findings.append(Finding("R10", "error", f"Der Start-Block »{label}« hat {out_count} ausgehende Pfeile – erlaubt ist genau einer.", [node.id], []))
        elif role == "stop":
            if in_count == 0:
                findings.append(Finding("R10", "error", f"Der Stop-Block »{label}« hat keinen eingehenden Pfeil.", [node.id], []))
            if out_count > 0:
                findings.append(Finding("R10", "error", f"Der Stop-Block »{label}« darf keinen ausgehenden Pfeil haben.", [node.id], []))
        elif role == "decision":
            if in_count == 0:
                findings.append(Finding("R10", "error", f"Die Verzweigung »{label}« hat keinen eingehenden Pfeil.", [node.id], []))
            if out_count != 2:
                findings.append(Finding(
                    "R10", "error",
                    f"Die Verzweigung »{label}« hat {out_count} ausgehende Pfeile. Eine Verzweigung braucht genau zwei: Ja und Nein.",
                    [node.id], [],
                ))
        elif role == "branchEnd":
            if in_count != 2:
                findings.append(Finding(
                    "R10", "error",
                    f"Der Verzweigung-zu-Block »{label}« hat {in_count} eingehende Pfeile statt der geforderten zwei (je einer pro Zweig).",
                    [node.id], [],
                ))
            if out_count != 1:
                findings.append(Finding("R10", "error", f"Der Verzweigung-zu-Block »{label}« hat {out_count} ausgehende Pfeile statt genau einem.", [node.id], []))
        else:
            kind = ROLE_NAMES_DE.get(role, role)
            if in_count == 0:
                findings.append(Finding("R10", "error", f"Der {kind}-Block »{label}« ist nicht erreichbar (kein eingehender Pfeil).", [node.id], []))
            if out_count == 0:
                findings.append(Finding("R10", "error", f"Der {kind}-Block »{label}« hat keinen ausgehenden Pfeil.", [node.id], []))
            elif out_count > 1:
                findings.append(Finding("R10", "error", f"Der {kind}-Block »{label}« hat {out_count} ausgehende Pfeile, ist aber kein Verzweigungsblock.", [node.id], []))
    return findings


def check_r11_self_loop(nodes: Dict[int, "Node"], arrows: Dict[int, "Arrow"]) -> List[Finding]:
    findings = []
    for arrow in arrows.values():
        if arrow.source_id == arrow.target_id and arrow.source_id in nodes:
            node = nodes[arrow.source_id]
            findings.append(Finding("R11", "error", f"Der Block »{_display_label(node)}« ist über einen Pfeil mit sich selbst verbunden.", [node.id], [arrow.id]))
    return findings


def check_r12_duplicate_edges(nodes: Dict[int, "Node"], arrows: Dict[int, "Arrow"]) -> List[Finding]:
    findings = []
    seen: Dict[Tuple[int, str, int, str], int] = {}
    for arrow in arrows.values():
        key = (arrow.source_id, arrow.source_port, arrow.target_id, arrow.target_port)
        if key in seen:
            source = nodes.get(arrow.source_id)
            target = nodes.get(arrow.target_id)
            findings.append(Finding(
                "R12", "warning",
                f"Zwischen »{_display_label(source) if source else '?'}« und »{_display_label(target) if target else '?'}« gibt es doppelte Pfeile.",
                [i for i in (arrow.source_id, arrow.target_id) if i in nodes], [seen[key], arrow.id],
            ))
        else:
            seen[key] = arrow.id
    return findings


# ---- C. Geometrie und Zeichenkonventionen ---------------------------------

def check_geometry_ports(nodes: Dict[int, "Node"], arrows: Dict[int, "Arrow"]) -> List[Finding]:
    """R14, R15, R17: Pfeile verlassen unten (Verzweigung zusätzlich rechts) und enden oben (bzw. rechts)."""
    findings = []
    for arrow in arrows.values():
        source = nodes.get(arrow.source_id)
        target = nodes.get(arrow.target_id)
        if not source or not target:
            continue
        is_branch_edge = role_of(source) == "decision" and arrow.source_port == "right"
        if arrow.source_port == "top" or arrow.target_port == "bottom":
            findings.append(Finding(
                "R14", "error",
                f"Der Pfeil von »{_display_label(source)}« nach »{_display_label(target)}« beginnt oder endet an der falschen Seite – "
                f"Pfeile müssen unten beginnen und oben am nächsten Block enden.",
                [source.id, target.id], [arrow.id],
            ))
            continue
        if arrow.source_port == "right" and not is_branch_edge:
            findings.append(Finding(
                "R14", "error",
                f"Der Pfeil von »{_display_label(source)}« verlässt den Block seitlich, obwohl es kein Verzweigungsblock ist – Pfeile müssen unten beginnen.",
                [source.id], [arrow.id],
            ))
        if is_branch_edge and arrow.target_port not in ("right", "top"):
            findings.append(Finding(
                "R15", "error",
                f"Der seitliche Zweig der Verzweigung »{_display_label(source)}« muss rechts oder oben in den nächsten Block münden.",
                [source.id, target.id], [arrow.id],
            ))
        if arrow.source_port != "right" and target.y < source.y:
            # Rücksprung von einem Schleifenende an einen weiter oben liegenden
            # Schleifenanfang ist zulässig – er wird nur als Hinweis gemeldet (R16).
            if role_of(source) == "loopEnd" and role_of(target) == "loopStart" and arrow.target_port == "top":
                findings.append(Finding(
                    "R16", "warning",
                    f"Der Pfeil von »{_display_label(source)}« nach »{_display_label(target)}« ist ein Rücksprung nach oben. "
                    f"Das ist erlaubt – prüfe, ob die Wiederholung so gewollt ist und der Pfeil von oben in die Schleife mündet.",
                    [source.id, target.id], [arrow.id],
                ))
            else:
                findings.append(Finding(
                    "R17", "warning",
                    f"Der Pfeil von »{_display_label(source)}« nach »{_display_label(target)}« führt nach oben statt nach unten.",
                    [source.id, target.id], [arrow.id],
                ))
    for node in nodes.values():
        if role_of(node) != "decision":
            continue
        ports_used = [a.source_port for a in arrows.values() if a.source_id == node.id]
        if len(ports_used) == 2 and ports_used[0] == ports_used[1]:
            findings.append(Finding(
                "R15", "error",
                f"Beide Zweige der Verzweigung »{_display_label(node)}« verlassen den Block an derselben Seite – Ja und Nein sollten unten und rechts herausgeführt werden.",
                [node.id], [],
            ))
    return findings


def check_r19_overlaps(nodes: Dict[int, "Node"]) -> List[Finding]:
    findings = []
    items = list(nodes.values())
    if len(items) > 500:
        return findings
    for i in range(len(items)):
        ax1, ay1, ax2, ay2 = items[i].bbox()
        for j in range(i + 1, len(items)):
            bx1, by1, bx2, by2 = items[j].bbox()
            if ax1 < bx2 and ax2 > bx1 and ay1 < by2 and ay2 > by1:
                findings.append(Finding(
                    "R19", "warning",
                    f"Die Blöcke »{_display_label(items[i])}« und »{_display_label(items[j])}« überlappen sich.",
                    [items[i].id, items[j].id], [],
                ))
    return findings


def _segments_intersect(p1: Tuple[float, float], p2: Tuple[float, float], p3: Tuple[float, float], p4: Tuple[float, float]) -> bool:
    def ccw(a: Tuple[float, float], b: Tuple[float, float], c: Tuple[float, float]) -> bool:
        return (c[1] - a[1]) * (b[0] - a[0]) > (b[1] - a[1]) * (c[0] - a[0])
    return ccw(p1, p3, p4) != ccw(p2, p3, p4) and ccw(p1, p2, p3) != ccw(p1, p2, p4)


def _arrow_polyline(nodes: Dict[int, "Node"], arrow: "Arrow") -> Optional[List[Tuple[float, float]]]:
    source = nodes.get(arrow.source_id)
    target = nodes.get(arrow.target_id)
    if not source or not target:
        return None
    return [source.ports()[arrow.source_port]] + list(arrow.waypoints) + [target.ports()[arrow.target_port]]


def check_r18_crossings(nodes: Dict[int, "Node"], arrows: Dict[int, "Arrow"]) -> List[Finding]:
    """R18: sich kreuzende Pfeile (O(n²), daher bei sehr großen Plänen übersprungen)."""
    if len(nodes) > 500:
        return []
    findings = []
    polylines = {aid: _arrow_polyline(nodes, a) for aid, a in arrows.items()}
    ids = list(arrows.keys())
    for i in range(len(ids)):
        a1 = arrows[ids[i]]
        p1 = polylines[ids[i]]
        if not p1:
            continue
        for j in range(i + 1, len(ids)):
            a2 = arrows[ids[j]]
            if {a1.source_id, a1.target_id} & {a2.source_id, a2.target_id}:
                continue  # gemeinsamer Block ist kein "Kreuzen"
            p2 = polylines[ids[j]]
            if not p2:
                continue
            crossed = False
            for k in range(len(p1) - 1):
                for l in range(len(p2) - 1):
                    if _segments_intersect(p1[k], p1[k + 1], p2[l], p2[l + 1]):
                        crossed = True
                        break
                if crossed:
                    break
            if crossed:
                findings.append(Finding("R18", "warning", "Zwei Pfeile kreuzen sich – das lässt sich meist durch Umsortieren der Blöcke vermeiden.", [], [a1.id, a2.id]))
    return findings


# ---- D. Kontrollstrukturen -------------------------------------------------

def check_r25_empty_bodies(nodes: Dict[int, "Node"], outgoing: Dict[int, List["Arrow"]]) -> List[Finding]:
    findings = []
    for node in nodes.values():
        role = role_of(node)
        if role == "decision":
            for arrow in outgoing.get(node.id, []):
                target = nodes.get(arrow.target_id)
                if target and role_of(target) == "branchEnd":
                    findings.append(Finding(
                        "R25", "warning",
                        f"Ein Zweig der Verzweigung »{_display_label(node)}« ist leer (der Pfeil geht direkt zum Verzweigung-zu-Block).",
                        [node.id, target.id], [arrow.id],
                    ))
        elif role == "loopStart":
            for arrow in outgoing.get(node.id, []):
                target = nodes.get(arrow.target_id)
                if target and role_of(target) == "loopEnd":
                    findings.append(Finding(
                        "R25", "warning",
                        f"Der Rumpf der Schleife »{_display_label(node)}« ist leer (der Pfeil geht direkt zum Schleife-zu-Block).",
                        [node.id, target.id], [arrow.id],
                    ))
    return findings


def analyze_control_structure_nesting(
    nodes: Dict[int, "Node"], outgoing: Dict[int, List["Arrow"]],
) -> Tuple[List[Finding], Dict[int, Set[int]]]:
    """R20, R22, R23: Verzweigung/Schleife müssen passend und geschachtelt geschlossen werden.

    Realisiert als einziger, gedächtnisbasierter Pfad-Durchlauf mit einem Stack aus
    ("DEC", id)/("LOOP", id)-Markierungen: Öffnende Blöcke legen eine Markierung ab,
    schließende Blöcke müssen die oberste Markierung des passenden Typs entfernen.
    Ein nicht passender Zustand (z. B. "Schleife zu" während eine Verzweigung offen
    ist) verletzt die Verschachtelung (R22); ein am Pfadende nicht abgebauter Stack
    verletzt R20; wenn die beiden Zweige einer Verzweigung an unterschiedlichen
    Verzweigung-zu-Blöcken schließen, verletzt das R23.
    """
    findings: List[Finding] = []
    starts = [n for n in nodes.values() if role_of(n) == "start"]
    if not starts:
        return findings, {}

    decision_merges: Dict[int, Set[int]] = {}
    loop_body_nodes: Dict[int, Set[int]] = {}
    reported: Set[Tuple[str, int]] = set()
    seen_states: Set[Tuple[int, Tuple[Tuple[str, int], ...]]] = set()
    MAX_STATES = 50000

    def walk(node_id: int, stack: Tuple[Tuple[str, int], ...]) -> None:
        if len(seen_states) > MAX_STATES:
            return
        key = (node_id, stack)
        if key in seen_states:
            return
        seen_states.add(key)
        node = nodes.get(node_id)
        if node is None:
            return
        for kind, marker_id in stack:
            if kind == "LOOP":
                loop_body_nodes.setdefault(marker_id, set()).add(node_id)

        role = role_of(node)
        new_stack = stack
        if role == "decision":
            new_stack = stack + (("DEC", node_id),)
        elif role == "loopStart":
            new_stack = stack + (("LOOP", node_id),)
        elif role == "branchEnd":
            if stack and stack[-1][0] == "DEC":
                dec_id = stack[-1][1]
                decision_merges.setdefault(dec_id, set()).add(node_id)
                new_stack = stack[:-1]
            elif ("branchEnd", node_id) not in reported:
                reported.add(("branchEnd", node_id))
                findings.append(Finding(
                    "R22", "error",
                    f"Der Verzweigung-zu-Block »{_display_label(node) or node.id}« schließt keine offene Verzweigung an dieser Stelle – "
                    f"Verzweigung und Schleife müssen sauber ineinander verschachtelt sein.",
                    [node_id], [],
                ))
        elif role == "loopEnd":
            if stack and stack[-1][0] == "LOOP":
                new_stack = stack[:-1]
            elif ("loopEnd", node_id) not in reported:
                reported.add(("loopEnd", node_id))
                findings.append(Finding(
                    "R22", "error",
                    f"Der Schleife-zu-Block »{_display_label(node) or node.id}« schließt keine offene Schleife an dieser Stelle – "
                    f"Verzweigung und Schleife müssen sauber ineinander verschachtelt sein.",
                    [node_id], [],
                ))

        outs = outgoing.get(node_id, [])
        if not outs and role == "stop" and new_stack:
            for kind, marker_id in new_stack:
                if (kind, marker_id) in reported:
                    continue
                reported.add((kind, marker_id))
                marker_node = nodes.get(marker_id)
                marker_label = marker_node.label if marker_node else "?"
                if kind == "DEC":
                    findings.append(Finding("R20", "error", f"Die Verzweigung »{marker_label}« wird auf diesem Pfad nie durch einen Verzweigung-zu-Block geschlossen.", [marker_id], []))
                else:
                    findings.append(Finding("R20", "error", f"Die Schleife »{marker_label}« wird auf diesem Pfad nie durch einen Schleife-zu-Block geschlossen.", [marker_id], []))
        for arrow in outs:
            walk(arrow.target_id, new_stack)

    walk(starts[0].id, tuple())

    for dec_id, merges in decision_merges.items():
        if len(merges) > 1:
            dec = nodes.get(dec_id)
            findings.append(Finding(
                "R23", "error",
                f"Die beiden Zweige der Verzweigung »{dec.label if dec else dec_id}« münden an unterschiedlichen "
                f"Verzweigung-zu-Blöcken – beide Zweige müssen im selben Block zusammengeführt werden.",
                [dec_id, *merges], [],
            ))

    return findings, loop_body_nodes


def check_r26_loop_condition(nodes: Dict[int, "Node"], loop_body_nodes: Dict[int, Set[int]]) -> List[Finding]:
    findings = []
    for node in nodes.values():
        if role_of(node) != "loopStart":
            continue
        body = loop_body_nodes.get(node.id, set()) - {node.id}
        condition_vars = extract_identifiers(_display_label(node))
        if not condition_vars:
            continue
        modified: Set[str] = set()
        for body_id in body:
            body_node = nodes.get(body_id)
            if body_node and role_of(body_node) == "process":
                assignment = split_assignment(body_node.label)
                if assignment:
                    modified |= extract_identifiers(assignment[0])
        if not (condition_vars & modified):
            findings.append(Finding(
                "R26", "warning",
                f"Die Bedingung der Schleife »{_display_label(node)}« verwendet nur Variablen, die im Schleifenrumpf nie verändert werden – möglicherweise eine Endlosschleife.",
                [node.id], [],
            ))
    return findings


# ---- E. Kantenbeschriftungen ----------------------------------------------

def check_r27_r28_branch_labels(nodes: Dict[int, "Node"], arrows: Dict[int, "Arrow"], outgoing: Dict[int, List["Arrow"]]) -> List[Finding]:
    findings = []
    for node in nodes.values():
        if role_of(node) != "decision":
            continue
        outs = outgoing.get(node.id, [])
        if len(outs) != 2:
            continue  # bereits durch R10 gemeldet
        labelled = [(a, (a.label or "").strip().lower()) for a in outs]
        kinds = ["yes" if lbl in YES_WORDS else "no" if lbl in NO_WORDS else None for _, lbl in labelled]
        if None in kinds:
            findings.append(Finding(
                "R27", "error",
                f"Beide Pfeile der Verzweigung »{_display_label(node)}« müssen mit »Ja« bzw. »Nein« beschriftet sein.",
                [node.id], [a.id for a, _ in labelled],
            ))
        elif kinds[0] == kinds[1]:
            findings.append(Finding(
                "R27", "error",
                f"Die beiden Pfeile der Verzweigung »{_display_label(node)}« sind beide mit »{labelled[0][1]}« beschriftet – sie müssen sich unterscheiden (Ja/Nein).",
                [node.id], [a.id for a, _ in labelled],
            ))
    for arrow in arrows.values():
        source = nodes.get(arrow.source_id)
        if source and role_of(source) == "decision":
            continue
        label = (arrow.label or "").strip().lower()
        if label in YES_WORDS or label in NO_WORDS:
            findings.append(Finding(
                "R28", "error",
                f"Der Pfeil von »{_display_label(source) if source else '?'}« trägt die Beschriftung »{arrow.label}«, stammt aber nicht von einer Verzweigung.",
                [source.id] if source else [], [arrow.id],
            ))
    return findings


# ---- F. Blockinhalte und Semantik -----------------------------------------

def check_r29_labels(nodes: Dict[int, "Node"]) -> List[Finding]:
    findings = []
    for node in nodes.values():
        role = role_of(node)
        if shape_of(node) in UNLABELED_SHAPES:
            continue  # Verzweigung-zu / Schleife-zu tragen bewusst keinen Text
        label = (_display_label(node) or "").strip()
        if not label:
            findings.append(Finding("R29", "error", "Ein Block ohne Beschriftung wurde gefunden.", [node.id], []))
            continue
        if role == "start" and label.lower() != "start":
            findings.append(Finding("R29", "error", "Der Start-Block muss den Text »Start« tragen.", [node.id], []))
        if role == "stop" and label.lower() != "stop":
            findings.append(Finding("R29", "error", "Der Stop-Block muss den Text »Stop« tragen.", [node.id], []))
    return findings


def check_r30_decision_content(nodes: Dict[int, "Node"]) -> List[Finding]:
    findings = []
    for node in nodes.values():
        if role_of(node) != "decision":
            continue
        label = _display_label(node) or ""
        assignment = split_assignment(label)
        has_comparison = any(op in label for op in COMPARISON_OPS)
        has_bool_word = any(w in label.lower() for w in BOOL_WORDS)
        if assignment:
            findings.append(Finding("R30", "error", f"Die Verzweigung »{label}« enthält eine Zuweisung – eine Verzweigung darf nur eine Ja/Nein-Bedingung enthalten.", [node.id], []))
        elif not has_comparison and not has_bool_word:
            findings.append(Finding("R30", "error", f"Die Verzweigung »{label}« enthält keine erkennbare Ja/Nein-Bedingung (z. B. mit ==, <, >, und, oder).", [node.id], []))
    return findings


def check_r31_process_content(nodes: Dict[int, "Node"]) -> List[Finding]:
    findings = []
    for node in nodes.values():
        if role_of(node) != "process":
            continue
        label = _display_label(node) or ""
        assignment = split_assignment(label)
        has_comparison = any(op in label for op in COMPARISON_OPS)
        if has_comparison and not assignment:
            findings.append(Finding(
                "R31", "error",
                f"Die Anweisung »{label}« enthält einen Vergleich, aber keine Zuweisung – gehört das nicht in einen Verzweigungsblock?",
                [node.id], [],
            ))
    return findings


def check_r36_subprocess(nodes: Dict[int, "Node"]) -> List[Finding]:
    findings = []
    for node in nodes.values():
        if role_of(node) != "subprocess":
            continue
        if not (_display_label(node) or "").strip() or not node.subdiagram:
            continue  # fehlende Beschriftung meldet bereits R29; leeres/unbenutztes subdiagram ist ok
        try:
            payload = json.loads(node.subdiagram)
            sub_nodes = {item["id"]: Node(**item) for item in payload.get("nodes", [])}
            sub_arrows = {item["id"]: Arrow(**item) for item in payload.get("arrows", [])}
        except (ValueError, TypeError, KeyError):
            findings.append(Finding("R36", "error", f"Die Funktion »{_display_label(node)}« enthält einen beschädigten Unterablaufplan.", [node.id], []))
            continue
        if sum(1 for n in sub_nodes.values() if role_of(n) == "start") != 1:
            findings.append(Finding("R36", "error", f"Die Funktion »{_display_label(node)}« hat keinen eindeutigen Start-Block im Unterablaufplan.", [node.id], []))
        for nested in evaluate_chart(sub_nodes, sub_arrows):
            findings.append(Finding(nested.rule, nested.severity, f"In Funktion »{_display_label(node)}«: {nested.message}", [node.id], []))
    return findings


# ---- Zusammenführung -------------------------------------------------------

def evaluate_chart(nodes: Dict[int, "Node"], arrows: Dict[int, "Arrow"], disabled_rules: Optional[Set[str]] = None) -> List[Finding]:
    """Run the full rule catalogue against a chart and return all findings.

    Pure function: does not modify `nodes`/`arrows`, has no side effects, and
    never raises on malformed input.
    """
    disabled_rules = disabled_rules or set()
    outgoing, incoming = _build_edge_maps(nodes, arrows)

    findings: List[Finding] = []
    findings += check_r01_start(nodes)
    findings += check_r02_stop_exists(nodes)
    findings += check_r03_multiple_stops(nodes)
    findings += check_r04_reachable_from_start(nodes, outgoing)
    findings += check_r05_reach_stop(nodes, incoming)
    findings += check_r06_connected(nodes, arrows)
    findings += check_r08_dangling_edges(nodes, arrows)
    findings += check_node_degrees(nodes, incoming, outgoing)
    findings += check_r11_self_loop(nodes, arrows)
    findings += check_r12_duplicate_edges(nodes, arrows)
    findings += check_geometry_ports(nodes, arrows)
    findings += check_r19_overlaps(nodes)
    findings += check_r18_crossings(nodes, arrows)
    findings += check_r25_empty_bodies(nodes, outgoing)
    nesting_findings, loop_body_nodes = analyze_control_structure_nesting(nodes, outgoing)
    findings += nesting_findings
    findings += check_r26_loop_condition(nodes, loop_body_nodes)
    findings += check_r27_r28_branch_labels(nodes, arrows, outgoing)
    findings += check_r29_labels(nodes)
    findings += check_r30_decision_content(nodes)
    findings += check_r31_process_content(nodes)
    findings += check_r36_subprocess(nodes)

    if disabled_rules:
        findings = [f for f in findings if f.rule not in disabled_rules]
    findings.sort(key=lambda f: (0 if f.severity == "error" else 1, f.rule))
    return findings


# Metadata for a future rule-settings UI: id -> (severity, short German title).
RULES: Dict[str, Tuple[str, str]] = {
    "R01": ("error", "Genau ein Start-Block"),
    "R02": ("error", "Mindestens ein Stop-Block"),
    "R03": ("warning", "Mehrere Stop-Blöcke"),
    "R04": ("error", "Erreichbarkeit vom Start"),
    "R05": ("error", "Jeder Block erreicht ein Stop"),
    "R06": ("error", "Ablaufplan zusammenhängend"),
    "R08": ("error", "Keine hängenden Pfeile"),
    "R10": ("error", "Ein-/Ausgangsgrad passt zum Blocktyp"),
    "R11": ("error", "Kein Selbstbezug"),
    "R12": ("warning", "Keine doppelten Pfeile"),
    "R14": ("error", "Pfeile unten raus, oben rein"),
    "R15": ("error", "Verzweigungszweige sauber getrennt"),
    "R16": ("warning", "Rücksprung zu einer Schleife nur als Hinweis"),
    "R17": ("warning", "Fluss von oben nach unten"),
    "R18": ("warning", "Keine Pfeilkreuzungen"),
    "R19": ("warning", "Keine überlappenden Blöcke"),
    "R20": ("error", "Kontrollstrukturen werden geschlossen"),
    "R22": ("error", "Saubere Verschachtelung"),
    "R23": ("error", "Beide Zweige treffen sich im selben Block"),
    "R25": ("warning", "Kein leerer Zweig/Rumpf"),
    "R26": ("warning", "Schleifenbedingung wird verändert"),
    "R27": ("error", "Ja/Nein-Beschriftung an Verzweigungen"),
    "R28": ("error", "Ja/Nein nur an Verzweigungen"),
    "R29": ("error", "Jeder Block ist beschriftet"),
    "R30": ("error", "Verzweigung enthält eine Bedingung"),
    "R31": ("error", "Anweisung enthält keinen Vergleich"),
    "R36": ("error", "Funktion referenziert gültigen Unterablaufplan"),
}


class PapEditor(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1400x900")
        self.minsize(1180, 760)

        self._node_font = tkfont.Font(family=NODE_FONT[0], size=NODE_FONT[1], weight=NODE_FONT[2])

        self.nodes: Dict[int, Node] = {}
        self.arrows: Dict[int, Arrow] = {}
        self.selected_node_ids: Set[int] = set()
        self.selected_arrow_id: Optional[int] = None
        self.drag_node_id: Optional[int] = None
        self.drag_bend: Optional[Tuple[int, int]] = None    # (arrow_id, index) beim Verschieben eines Knickpunkts
        self.drag_width_node: Optional[int] = None          # Block, dessen Breite gerade gezogen wird
        self.last_bend: Optional[Tuple[int, int, float]] = None  # zuletzt per Klick gesetzter Knickpunkt (+ Zeitpunkt)
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
        self._context_menu: Optional[tk.Menu] = None    # Kontextmenue eines Funktionsblocks
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

        hint = tk.Label(
            self.left,
            text="Mehrfachauswahl: Rahmen ziehen · Shift-Klick\n"
                 "Kopieren ⌘/Strg+C · Einfügen ⌘/Strg+V\n"
                 "SVG kopieren ⌘/Strg+Shift+C · Undo ⌘/Strg+Z\n"
                 "Text ändern: Doppelklick · Löschen: Entf\n"
                 "Funktion öffnen: Rechtsklick · Zurück: Esc\n"
                 "Breite: Griff rechts unten · angleichen ⌘/Strg+B\n"
                 "Text: ⌘/Strg+Enter = Zeilenumbruch\n"
                 "Pfeil-Knick: markierten Pfeil anklicken · Doppelklick löscht",
            bg=SIDEBAR_BG, fg=PALETTE_MUTED, justify="left", font=("Helvetica", 8),
        )
        hint.pack(anchor="w", padx=16, pady=(0, 12))

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Sidebar.TButton", padding=(9, 6), font=("Helvetica", 10), relief="flat",
                        background="#334155", foreground=PALETTE_FG, borderwidth=0)
        style.map("Sidebar.TButton", background=[("active", "#475569")])
        style.configure("Accent.TButton", padding=(9, 6), font=("Helvetica", 10, "bold"), relief="flat",
                        background=ACCENT, foreground="#ffffff", borderwidth=0)
        style.map("Accent.TButton", background=[("active", "#4f46e5")])

        # Kopfleiste: Zurück-Button · Breadcrumb (wächst) · Aktionen-Menüleiste · Status
        topbar = tk.Frame(self.right, bg=STATUS_BG)
        topbar.grid(row=0, column=0, columnspan=2, sticky="ew")
        topbar.columnconfigure(1, weight=1)

        self.back_button = ttk.Button(topbar, text="← Zurück", command=self.close_function, style="Sidebar.TButton")
        self.breadcrumb = tk.StringVar(value=self.context_title)
        tk.Label(topbar, textvariable=self.breadcrumb, bg=STATUS_BG, fg="#0f172a",
                 padx=12, pady=5, font=("Helvetica", 11, "bold")).grid(row=0, column=1, sticky="w")

        menubar = tk.Frame(topbar, bg=STATUS_BG)
        menubar.grid(row=0, column=2, sticky="e", padx=(6, 0))
        for text, command, kind in [
            ("Diagramm prüfen", self.check_diagram, "Accent.TButton"),
            ("Breite angleichen", self.equalize_width, "Sidebar.TButton"),
            ("Neu", self.new_diagram, "Sidebar.TButton"),
            ("Laden", self.load_diagram, "Sidebar.TButton"),
            ("Speichern", self.save_diagram, "Sidebar.TButton"),
            ("PNG export", self.export_png, "Sidebar.TButton"),
            ("JPG export", self.export_jpg, "Sidebar.TButton"),
            ("SVG kopieren", self.copy_svg, "Sidebar.TButton"),
            ("SVG export", self.export_svg, "Sidebar.TButton"),
        ]:
            ttk.Button(menubar, text=text, command=command, style=kind).pack(side="left", padx=(0, 4), pady=4)

        self.status = tk.StringVar(value="Bereit")
        tk.Label(topbar, textvariable=self.status, anchor="e", bg=STATUS_BG, fg="#475569",
                 padx=12, pady=5, font=("Helvetica", 10)).grid(row=0, column=3, sticky="e")

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
        if sys.platform == "darwin":                 # Sekundaerklick auf dem Mac
            self.canvas.bind("<Button-2>", self.on_canvas_right_click)
            self.canvas.bind("<Control-Button-1>", self.on_canvas_right_click)
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
        for seq in ("<Control-b>", "<Command-b>"):
            self.bind_all(seq, self.equalize_width)
        for seq in ("<Control-Shift-B>", "<Command-Shift-B>"):
            self.bind_all(seq, self.reset_width)
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
        if selected and len(self.selected_node_ids) == 1:
            self._draw_width_grip(node)

    def _width_grip_pos(self, node: Node) -> Tuple[float, float]:
        _, _, x2, y2 = node.bbox()
        return x2 + GRIP, y2 + GRIP

    def _draw_width_grip(self, node: Node) -> None:
        """Anfasser rechts unten an der Auswahl – zieht die Blockbreite auf."""
        if not _is_resizable(node):
            return
        gx, gy = self._width_grip_pos(node)
        self.canvas.create_rectangle(gx - GRIP, gy - GRIP, gx + GRIP, gy + GRIP,
                                     fill="#ffffff", outline=ACCENT, width=2)
        self.canvas.create_line(gx - 3, gy - 1, gx + 3, gy - 1, fill=ACCENT)
        self.canvas.create_line(gx - 3, gy + 2, gx + 3, gy + 2, fill=ACCENT)

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
        points = approach_points(start, list(arrow.waypoints), end, arrow.target_port)
        return orthogonal_points(start, arrow.source_port, points, end, arrow.target_port)

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
        if arrow.id == self.selected_arrow_id:
            self._draw_bends(arrow)

    def _draw_bends(self, arrow: Arrow) -> None:
        """Knickpunkte des markierten Pfeils als verschiebbare Griffe zeichnen."""
        for wx, wy in arrow.waypoints:
            self.canvas.create_oval(wx - BEND_RADIUS, wy - BEND_RADIUS, wx + BEND_RADIUS, wy + BEND_RADIUS,
                                    fill="#ffffff", outline=ACCENT, width=2)

    def _draw_temp_arrow(self) -> None:
        if not self.connection_source or not self.temp_arrow_target:
            return
        source_id, source_port = self.connection_source
        source = self.nodes.get(source_id)
        if not source:
            return
        start = source.ports()[source_port]
        points = approach_points(start, [], self.temp_arrow_target, "top")
        route = orthogonal_points(start, source_port, points, self.temp_arrow_target, "top")
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

    def _measure(self, text: str) -> float:
        return self._node_font.measure(text)

    def _fit_node_size(self, node: Node) -> None:
        """Grow the block so its label fits the shape (diamonds taper, connectors are round).

        Bloecke mit manuell gesetzter Breite wachsen nicht mehr in die Breite –
        der Text bricht dann um und die Hoehe waechst."""
        shape = shape_of(node)
        if shape == "connector":
            node.width = node.height = 26
            return
        if shape in UNLABELED_SHAPES:
            return
        label = node.label or ""
        if not node.manual_width:
            text_w = max((self._measure(para) for para in label.split("\n")), default=0) + 24
            if shape == "diamond":
                node.width = max(node.width, self.snap(text_w * 1.7))
            else:
                node.width = max(node.width, self.snap(text_w))
        node.width = max(MIN_NODE_W, node.width)
        lines = len(wrap_lines(self._measure, label, max(20, node.width - 18)))
        need_h = lines * LINE_H + (40 if shape == "diamond" else 22)
        node.height = max(88 if shape == "diamond" else NODE_H, need_h)

    def set_node_width(self, node: Node, width: float) -> None:
        """Breite von Hand festlegen (rastet aufs Raster, Hoehe folgt dem Text)."""
        if not _is_resizable(node):
            return
        node.width = max(MIN_NODE_W, self.snap(width))
        node.manual_width = True
        self._fit_node_size(node)

    def _resizable_nodes(self) -> List[Node]:
        return [node for node in (self.nodes.get(nid) for nid in self.selected_node_ids)
                if _is_resizable(node)]

    def _is_typing(self) -> bool:
        """Waehrend einer Texteingabe duerfen die Tastenkuerzel nicht zuschlagen."""
        try:
            return isinstance(self.focus_get(), (tk.Text, tk.Entry, ttk.Entry))
        except KeyError:
            return False

    def equalize_width(self, event: Optional[tk.Event] = None) -> str:
        """Alle markierten Bloecke auf die Breite des breitesten bringen."""
        if event is not None and self._is_typing():
            return ""
        selection = self._resizable_nodes()
        if len(selection) < 2:
            self.status.set("Mindestens zwei Bloecke markieren, um die Breite anzugleichen.")
            return "break"
        width = max(node.width for node in selection)
        self._push_undo()
        for node in selection:
            self.set_node_width(node, width)
        self._redraw()
        self.status.set(f"{len(selection)} Bloecke auf {int(width)} px Breite gebracht")
        return "break"

    def reset_width(self, event: Optional[tk.Event] = None) -> str:
        """Automatische Breite wiederherstellen."""
        if event is not None and self._is_typing():
            return ""
        selection = self._resizable_nodes()
        if not selection:
            return "break"
        self._push_undo()
        for node in selection:
            node.manual_width = False
            node.width = NODE_W
            self._fit_node_size(node)
        self._redraw()
        self.status.set(f"{len(selection)} Block/Bloecke auf automatische Breite zurueckgesetzt")
        return "break"

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
        if source_port == "top" or target_port == "bottom":
            return None
        if self._has_path(target_id, source_id):
            return None
        arrow = Arrow(self.next_arrow_id, source_id, source_port, target_id, target_port)
        # Liegt das Ziel weiter oben, wird ein Weg aussen herum vorbelegt; die
        # Knickpunkte lassen sich anschliessend am Raster verschieben.
        if target.y < source.y:
            arrow.waypoints = self._back_jump_waypoints(source, source_port, target, target_port)
        self.arrows[arrow.id] = arrow
        self.next_arrow_id += 1
        return arrow

    def _back_jump_waypoints(self, source: Node, source_port: str,
                             target: Node, target_port: str) -> List[Tuple[float, float]]:
        """Vorschlag fuer den Umweg eines Pfeils, der zu einem hoeher liegenden Block fuehrt."""
        if source_port != "bottom" or target_port != "top":
            return []
        lane = self.snap(max(source.x + source.width / 2, target.x + target.width / 2) + self.grid_size)
        below = self.snap(source.y + source.height / 2 + self.grid_size)
        above = self.snap(target.y - target.height / 2 - self.grid_size)
        return [(self.snap(source.x), below), (lane, below), (lane, above)]

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

        # Knickpunkt des markierten Pfeils verschieben
        bend = self._hit_test_bend(x, y)
        if bend is not None:
            self.drag_bend = (self.selected_arrow_id, bend)
            self.drag_snapshot = self._serialize()
            self.drag_moved = False
            return

        # Breiten-Anfasser des markierten Blocks ziehen
        grip_id = self._hit_test_width_grip(x, y)
        if grip_id is not None:
            self.drag_width_node = grip_id
            self.drag_snapshot = self._serialize()
            self.drag_moved = False
            return

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
            arrow_id = self._hit_test_arrow(x, y)
            self.connection_source = None
            # Zweiter Klick auf denselben Pfeil setzt einen Knickpunkt
            if arrow_id is not None and arrow_id == self.selected_arrow_id:
                self._insert_bend_point(arrow_id, x, y)
            self.selected_arrow_id = arrow_id
            if arrow_id is None:
                self.rubber_band = (x, y, x, y)
            self._redraw()

    def on_canvas_drag(self, event: tk.Event) -> None:
        x, y = self._canvas_coords(event)
        if self.drag_bend is not None:
            arrow_id, index = self.drag_bend
            arrow = self.arrows.get(arrow_id)
            if not arrow or index >= len(arrow.waypoints):
                self.drag_bend = None
                return
            nx, ny = self.snap(x), self.snap(y)
            if (nx, ny) != tuple(arrow.waypoints[index]):
                arrow.waypoints[index] = (nx, ny)
                self.drag_moved = True
            self._redraw()
        elif self.drag_width_node is not None:
            node = self.nodes.get(self.drag_width_node)
            if not node:
                self.drag_width_node = None
                return
            new_width = max(MIN_NODE_W, self.snap(2 * (x - node.x - GRIP)))
            if new_width != node.width:
                self.set_node_width(node, new_width)
                self.drag_moved = True
            self._redraw()
        elif self.drag_node_id and self.drag_node_id in self.nodes:
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
        if self.drag_bend is not None or self.drag_width_node is not None:
            if self.drag_moved and self.drag_snapshot is not None:
                self.undo_stack.append(self.drag_snapshot)
                if len(self.undo_stack) > 100:
                    self.undo_stack.pop(0)
                self.redo_stack.clear()
            self.drag_bend = None
            self.drag_width_node = None
            self.drag_snapshot = None
            self.drag_moved = False
            self._redraw()
            return
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

        # Doppelklick auf einen Knickpunkt entfernt ihn
        bend = self._hit_test_bend(x, y)
        if bend is not None:
            self._remove_bend_point(self.selected_arrow_id, bend)
            return

        # Der erste Klick eines Doppelklicks auf einen markierten Pfeil hat
        # gerade einen Knickpunkt gesetzt – der war nicht gemeint.
        if (self.last_bend is not None and time.monotonic() - self.last_bend[2] < 0.6
                and self._hit_test_arrow(x, y) == self.last_bend[0]):
            arrow_id, index, _ = self.last_bend
            arrow = self.arrows.get(arrow_id)
            if arrow and index < len(arrow.waypoints):
                arrow.waypoints.pop(index)
                if self.undo_stack:
                    self.undo_stack.pop()
            self.last_bend = None

        node_id = self._hit_test_node(x, y)
        if node_id:
            node = self.nodes[node_id]
            if shape_of(node) in UNLABELED_SHAPES:
                return
            new_label = self._ask_multiline("Symbol bearbeiten", "Inhalt des Symbols:", node.label)
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

    def _ask_multiline(self, title: str, prompt: str, initial: str) -> Optional[str]:
        """Mehrzeiliger Eingabedialog.

        Enter schliesst den Dialog, Strg/Cmd+Enter bzw. Shift+Enter fuegen einen
        Zeilenumbruch in den Blocktext ein."""
        dialog = tk.Toplevel(self)
        dialog.title(title)
        dialog.transient(self)
        dialog.resizable(False, False)
        result: Dict[str, Optional[str]] = {"value": None}

        tk.Label(dialog, text=prompt, anchor="w", font=("Helvetica", 11)).pack(fill="x", padx=14, pady=(14, 6))
        text = tk.Text(dialog, width=46, height=4, font=("Helvetica", 12), wrap="word",
                       relief="solid", borderwidth=1, highlightthickness=0)
        text.pack(fill="both", expand=True, padx=14)
        text.insert("1.0", initial or "")
        tk.Label(dialog, text="Strg/⌘+Enter oder Shift+Enter = Zeilenumbruch · Enter = OK",
                 fg="#64748b", font=("Helvetica", 9)).pack(anchor="w", padx=14, pady=(6, 0))

        def confirm(event: Optional[tk.Event] = None) -> str:
            result["value"] = text.get("1.0", "end-1c")
            dialog.destroy()
            return "break"

        def cancel(event: Optional[tk.Event] = None) -> str:
            dialog.destroy()
            return "break"

        def newline(event: Optional[tk.Event] = None) -> str:
            text.insert("insert", "\n")
            return "break"

        buttons = tk.Frame(dialog)
        buttons.pack(fill="x", padx=14, pady=12)
        ttk.Button(buttons, text="OK", command=confirm).pack(side="right")
        ttk.Button(buttons, text="Abbrechen", command=cancel).pack(side="right", padx=(0, 6))

        for seq in ("<Control-Return>", "<Command-Return>", "<Shift-Return>"):
            text.bind(seq, newline)
        text.bind("<Return>", confirm)          # muss nach den Kombinationen kommen
        dialog.bind("<Escape>", cancel)
        dialog.protocol("WM_DELETE_WINDOW", cancel)

        text.focus_set()
        text.mark_set("insert", "end-1c")
        dialog.grab_set()
        self.wait_window(dialog)
        return result["value"]

    def on_canvas_right_click(self, event: tk.Event) -> None:
        x, y = self._canvas_coords(event)
        bend = self._hit_test_bend(x, y)
        if bend is not None:
            self._remove_bend_point(self.selected_arrow_id, bend)
            return
        node_id = self._hit_test_node(x, y)
        if node_id:
            node = self.nodes[node_id]
            if node.template_label == "Funktion":
                self._show_function_menu(node, event)
                return
            self.delete_node(node_id)
            return
        arrow_id = self._hit_test_arrow(x, y)
        if arrow_id is not None:
            self._edit_arrow_waypoints(arrow_id, x, y)

    def _show_function_menu(self, node: Node, event: tk.Event) -> None:
        """Kontextmenue eines Funktionsblocks.

        Der Doppelklick bearbeitet wie bei allen anderen Bloecken den Text,
        deshalb fuehrt nur noch dieses Menue in den Unterablaufplan."""
        self.selected_node_ids = {node.id}
        self.selected_arrow_id = None
        self._redraw()

        if getattr(self, "_context_menu", None) is not None:
            self._context_menu.destroy()
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Funktion öffnen …", command=lambda: self.open_function(node))
        menu.add_separator()
        menu.add_command(label="Löschen", command=lambda: self.delete_node(node.id))
        self._context_menu = menu
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

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
            return "top"
        if source.x - target.x > target.width / 2 + 4:   # source clearly to the right
            return "right"
        return "top"

    def _insert_bend_point(self, arrow_id: int, x: float, y: float) -> None:
        arrow = self.arrows.get(arrow_id)
        if not arrow:
            return
        index = self._bend_insert_index(arrow, x, y)
        self._push_undo()
        arrow.waypoints.insert(index, (self.snap(x), self.snap(y)))
        self.last_bend = (arrow_id, index, time.monotonic())
        self.selected_arrow_id = arrow_id
        self._redraw()

    def _bend_insert_index(self, arrow: Arrow, x: float, y: float) -> int:
        """An welcher Stelle der Knickpunkt-Liste liegt der angeklickte Abschnitt?"""
        route = self._arrow_route(arrow)
        if not route:
            return len(arrow.waypoints)
        best, segment = float("inf"), 0
        for i, ((ax, ay), (bx, by)) in enumerate(zip(route, route[1:])):
            distance = self._distance_to_segment(x, y, ax, ay, bx, by)
            if distance < best:
                best, segment = distance, i
        index, ri = 0, 0
        for k, (wx, wy) in enumerate(arrow.waypoints):
            while ri < len(route) and not (abs(route[ri][0] - wx) < 0.5 and abs(route[ri][1] - wy) < 0.5):
                ri += 1
            if ri > segment:
                break
            index, ri = k + 1, ri + 1
        return index

    def _remove_bend_point(self, arrow_id: int, index: int) -> None:
        arrow = self.arrows.get(arrow_id)
        if not arrow or index >= len(arrow.waypoints):
            return
        self._push_undo()
        arrow.waypoints.pop(index)
        self.last_bend = None
        self._redraw()

    def _hit_test_bend(self, x: float, y: float) -> Optional[int]:
        """Knickpunkt des markierten Pfeils treffen? -> Index oder None"""
        if self.selected_arrow_id is None:
            return None
        arrow = self.arrows.get(self.selected_arrow_id)
        if not arrow:
            return None
        for index in range(len(arrow.waypoints) - 1, -1, -1):
            wx, wy = arrow.waypoints[index]
            if math.hypot(wx - x, wy - y) <= BEND_RADIUS + 6:
                return index
        return None

    def _hit_test_width_grip(self, x: float, y: float) -> Optional[int]:
        """Breiten-Anfasser des einzeln markierten Blocks treffen?"""
        if len(self.selected_node_ids) != 1:
            return None
        node = self.nodes.get(next(iter(self.selected_node_ids)))
        if not node:
            return None
        if not _is_resizable(node):
            return None
        gx, gy = self._width_grip_pos(node)
        if abs(x - gx) <= GRIP + 4 and abs(y - gy) <= GRIP + 4:
            return node.id
        return None

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

    @staticmethod
    def _normalize_item(item: dict, mapping: Dict[str, str], allowed: Set[str]) -> dict:
        """Dateien der Web-Version nutzen camelCase-Schluessel – hier umschreiben
        und unbekannte Felder verwerfen, damit neue Felder abwaertskompatibel bleiben."""
        data = {mapping.get(key, key): value for key, value in item.items()}
        return {key: value for key, value in data.items() if key in allowed}

    NODE_KEY_MAP = {"imageRel": "image_rel", "templateLabel": "template_label",
                    "textAnchor": "text_anchor", "manualWidth": "manual_width"}
    ARROW_KEY_MAP = {"sourceId": "source_id", "sourcePort": "source_port",
                     "targetId": "target_id", "targetPort": "target_port"}

    def _load_payload(self, payload: dict) -> None:
        self.nodes.clear()
        self.arrows.clear()
        node_fields = set(Node.__dataclass_fields__)
        arrow_fields = set(Arrow.__dataclass_fields__)
        for item in payload.get("nodes", []):
            node = Node(**self._normalize_item(item, self.NODE_KEY_MAP, node_fields))
            self.nodes[node.id] = node
        for item in payload.get("arrows", []):
            arrow = Arrow(**self._normalize_item(item, self.ARROW_KEY_MAP, arrow_fields))
            arrow.waypoints = [(float(wx), float(wy)) for wx, wy in arrow.waypoints]
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
        findings = evaluate_chart(self.nodes, self.arrows)

        # betroffene Blöcke/Pfeile zur Orientierung markieren
        self.selected_node_ids = {nid for f in findings for nid in f.node_ids if nid in self.nodes}
        arrow_hits = [aid for f in findings for aid in f.arrow_ids if aid in self.arrows]
        self.selected_arrow_id = arrow_hits[0] if arrow_hits else None
        self._redraw()

        if not findings:
            messagebox.showinfo("Plausibilitätsprüfung", "Keine Probleme gefunden. Der Algorithmus scheint plausibel.")
            return

        errors = [f for f in findings if f.severity == "error"]
        warnings = [f for f in findings if f.severity == "warning"]

        def fmt(f: Finding) -> str:
            return f"[{f.rule}] {f.message}"

        parts = []
        if errors:
            parts.append(f"Fehler ({len(errors)}):\n" + "\n".join(f"- {fmt(f)}" for f in errors))
        if warnings:
            parts.append(f"Hinweise ({len(warnings)}):\n" + "\n".join(f"- {fmt(f)}" for f in warnings))
        body = "\n\n".join(parts)
        if errors:
            messagebox.showwarning("Plausibilitätsprüfung", body)
        else:
            messagebox.showinfo("Plausibilitätsprüfung", body)

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
            lines = wrap_lines(self._measure, node.label, max(20, w - 18))
            start_y = cy - (len(lines) - 1) * LINE_H / 2
            spans = "".join(
                f'<tspan x="{cx}" y="{start_y + i * LINE_H:.1f}">{escape(line)}</tspan>'
                for i, line in enumerate(lines)
            )
            s.append('<text font-family="Helvetica" font-size="12" font-weight="bold" '
                     f'text-anchor="middle" dominant-baseline="central" fill="{TEXT_COLOR}">{spans}</text>')
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
            route = self._arrow_route(arrow)
            if not route:
                continue
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
                # gleiche Zeilenaufteilung wie auf der Zeichenflaeche
                label = "\n".join(wrap_lines(self._measure, node.label, max(20, node.width - 18)))
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
