'use strict';

// ════════════════════════════════════════════════════════════
// Konstanten  (identisch mit pap_editor.py)
// ════════════════════════════════════════════════════════════
const CANVAS_BG      = '#f8fafc';
const SIDEBAR_BG     = '#0f172a';
const PALETTE_CARD_C = '#1e293b';
const PALETTE_MUTED  = '#94a3b8';
const GRID_COLOR     = '#e6ebf2';
const ACCENT         = '#2563eb';
const ARROW_COLOR    = '#111111';
const NODE_BORDER    = '#111111';
const TEXT_COLOR     = '#111111';

const NODE_STYLE = {
  'Start':          ['#b3b3b3', NODE_BORDER],
  'Stop':           ['#b3b3b3', NODE_BORDER],
  'Funktion':       ['#ec4f71', NODE_BORDER],
  'Anweisung':      ['#ec4f71', NODE_BORDER],
  'Entscheidung':   ['#5ecf87', NODE_BORDER],
  'Verzweigung zu': ['#ffffff', NODE_BORDER],
  'Schleife':       ['#fdcb4a', NODE_BORDER],
  'Schleife zu':    ['#fdcb4a', NODE_BORDER],
};
const DEFAULT_STYLE = ['#ffffff', NODE_BORDER];

const NODE_SHAPE = {
  'Start':          'terminator',
  'Stop':           'terminator',
  'Funktion':       'subroutine',
  'Anweisung':      'rect',
  'Entscheidung':   'diamond',
  'Verzweigung zu': 'connector',
  'Schleife':       'loop_start',
  'Schleife zu':    'loop_end',
};

const NODE_TYPES = [
  { label: 'Start',          kind: 'terminator', rel: 'Bilder/Start.png'          },
  { label: 'Stop',           kind: 'terminator', rel: 'Bilder/Stop.png'           },
  { label: 'Funktion',       kind: 'subroutine', rel: 'Bilder/Funktion.png'       },
  { label: 'Anweisung',      kind: 'rect',       rel: 'Bilder/Anweisung.png'      },
  { label: 'Entscheidung',   kind: 'diamond',    rel: 'Bilder/Verzweigung_auf.png'},
  { label: 'Verzweigung zu', kind: 'connector',  rel: 'Bilder/Verzweigung_zu.png' },
  { label: 'Schleife',       kind: 'loop_start', rel: 'Bilder/Schleife_auf.png'   },
  { label: 'Schleife zu',    kind: 'loop_end',   rel: 'Bilder/Schleife_zu.png'    },
];

const UNLABELED = new Set(['connector', 'loop_end']);

const NODE_W = 104;
const NODE_H = 44;
const PORT_R = 6;
const SEL_MARGIN = 8;

const NODE_FONT  = 'bold 11px Helvetica,Arial,sans-serif';
const LINE_H     = 14;      // Zeilenhöhe im Blocktext
const MIN_NODE_W = 60;      // kleinste manuell einstellbare Blockbreite
const GRIP       = 6;       // halbe Kantenlänge des Breiten-Anfassers
const BEND_R     = 5;       // Radius der Knickpunkt-Anfasser
const APPROACH   = 24;      // Mindestlänge der Einmündung in einen Port

// ════════════════════════════════════════════════════════════
// Globaler State
// ════════════════════════════════════════════════════════════
let nodes   = {};   // id → node
let arrows  = {};   // id → arrow
let nextNid = 1;
let nextAid = 1;
let selNodes  = new Set();
let selArrow  = null;
let curFile   = null;
let gridSize  = 40;
let showGrid  = true;

// Undo/Redo
let undoStack = [];
let redoStack = [];

// Sub-Diagramm (Kontext-Stack)
let ctxStack = [];
let ctxTitle = 'Hauptprogramm';

// Zwischenablage
let clipboard = null;

// Viewport-Verschiebung
let panX = 0;
let panY = 0;

// Interaktions-State
let dragState    = null;   // { type, … }
let connSrc      = null;   // { nodeId, port }
let tempTarget   = null;   // [wx, wy] – Endpunkt des Temp-Pfeils
let dragSnap     = null;
let dragMoved    = false;
let lastBend     = null;   // zuletzt per Klick gesetzter Knickpunkt (für Doppelklick-Korrektur)

// Palette Drag
let palDragItem    = null;
let palDragPreview = null;  // [wx, wy]

// Touch
let touchPan   = null;   // { cx, cy, panX, panY }
let lastTapT   = 0;
let lastTapX   = 0;
let lastTapY   = 0;

// Canvas
let canvas, ctx;
const DPR = window.devicePixelRatio || 1;

// ════════════════════════════════════════════════════════════
// Geometrie-Hilfsfunktionen
// ════════════════════════════════════════════════════════════
function shapeOf(n) { return NODE_SHAPE[n.templateLabel] || n.kind || 'rect'; }
function snap(v)    { return Math.round(v / gridSize) * gridSize; }

function bbox(n) {
  return [n.x - n.width/2, n.y - n.height/2, n.x + n.width/2, n.y + n.height/2];
}

function ports(n) {
  const [x1,y1,x2,y2] = bbox(n);
  return {
    top:    [(x1+x2)/2, y1],
    bottom: [(x1+x2)/2, y2],
    left:   [x1, (y1+y2)/2],
    right:  [x2, (y1+y2)/2],
  };
}

function allowedPorts(n) {
  const sh = shapeOf(n);
  let ps = (sh === 'diamond' || sh === 'connector') ? ['top','bottom','right'] : ['top','bottom'];
  if (n.templateLabel === 'Start') ps = ps.filter(p => p !== 'top');
  if (n.templateLabel === 'Stop')  ps = ps.filter(p => p !== 'bottom');
  return ps;
}

// Pfad-Funktionen – nehmen explizit einen Kontext
function rrPath(c, x1,y1,x2,y2,r) {
  r = Math.max(0, Math.min(r, (x2-x1)/2, (y2-y1)/2));
  c.beginPath();
  c.moveTo(x1+r, y1); c.lineTo(x2-r, y1);
  c.arcTo(x2,y1, x2,y1+r, r); c.lineTo(x2, y2-r);
  c.arcTo(x2,y2, x2-r,y2, r); c.lineTo(x1+r, y2);
  c.arcTo(x1,y2, x1,y2-r, r); c.lineTo(x1, y1+r);
  c.arcTo(x1,y1, x1+r,y1, r); c.closePath();
}

function diamondPath(c, x,y,w,h) {
  c.beginPath();
  c.moveTo(x, y-h/2); c.lineTo(x+w/2, y);
  c.lineTo(x, y+h/2); c.lineTo(x-w/2, y);
  c.closePath();
}

function chamfer(w,h) { return Math.min(w*0.14, h*0.5, 16); }

function loopStartPath(c, x,y,w,h) {
  const [x1,y1,x2,y2] = [x-w/2, y-h/2, x+w/2, y+h/2];
  const cf = chamfer(w,h);
  c.beginPath();
  c.moveTo(x1+cf,y1); c.lineTo(x2-cf,y1); c.lineTo(x2,y1+cf);
  c.lineTo(x2,y2);    c.lineTo(x1,y2);    c.lineTo(x1,y1+cf);
  c.closePath();
}

function loopEndPath(c, x,y,w,h) {
  const [x1,y1,x2,y2] = [x-w/2, y-h/2, x+w/2, y+h/2];
  const cf = chamfer(w,h);
  c.beginPath();
  c.moveTo(x1,y1);    c.lineTo(x2,y1);    c.lineTo(x2,y2-cf);
  c.lineTo(x2-cf,y2); c.lineTo(x1+cf,y2); c.lineTo(x1,y2-cf);
  c.closePath();
}

// ════════════════════════════════════════════════════════════
// Orthogonales Routing (portiert aus Python)
// ════════════════════════════════════════════════════════════
function orthoPts(start, srcPort, waypoints, end, tgtPort) {
  const sAx = (srcPort === 'top' || srcPort === 'bottom') ? 'v' : 'h';
  const tAx = (tgtPort === 'top' || tgtPort === 'bottom') ? 'v' : 'h';
  const pts  = [start];

  function connect(a, b, lead, arrive) {
    const [ax,ay] = a, [bx,by] = b;
    if (Math.abs(ax-bx) < 1 || Math.abs(ay-by) < 1) return [[bx,by]];
    const axis = arrive !== undefined ? arrive : lead;
    return axis === 'v' ? [[bx,ay],[bx,by]] : [[ax,by],[bx,by]];
  }

  if (!waypoints || waypoints.length === 0) {
    const [ax,ay] = start, [bx,by] = end;
    if (Math.abs(ax-bx) < 1 || Math.abs(ay-by) < 1) {
      pts.push(end);
    } else if (sAx === tAx) {
      if (sAx === 'v') { const m=(ay+by)/2; pts.push([ax,m],[bx,m],end); }
      else              { const m=(ax+bx)/2; pts.push([m,ay],[m,by],end); }
    } else if (sAx === 'v') {
      pts.push([ax,by], end);
    } else {
      pts.push([bx,ay], end);
    }
  } else {
    const anchors = [...waypoints, end];
    let lead = sAx;
    for (let i = 0; i < anchors.length; i++) {
      const arrive = i === anchors.length-1 ? tAx : undefined;
      pts.push(...connect(pts[pts.length-1], anchors[i], lead, arrive));
      const p = pts[pts.length-2], q = pts[pts.length-1];
      lead = Math.abs(p[0]-q[0]) < 1 ? 'v' : 'h';
    }
  }

  const out = [pts[0]];
  for (let i = 1; i < pts.length; i++) {
    const [px,py] = out[out.length-1], [qx,qy] = pts[i];
    if (Math.abs(qx-px) > 0.5 || Math.abs(qy-py) > 0.5) out.push(pts[i]);
  }
  return out;
}

function arrowRoute(a) {
  const s = nodes[a.sourceId], t = nodes[a.targetId];
  if (!s || !t) return null;
  const start = ports(s)[a.sourcePort], end = ports(t)[a.targetPort];
  const wps = approachPoints(start, a.waypoints || [], end, a.targetPort);
  return orthoPts(start, a.sourcePort, wps, end, a.targetPort);
}

/**
 * Sorgt dafür, dass der Pfeil immer aus der zum Ziel-Port passenden Richtung
 * einmündet: oben von oben nach unten, unten von unten nach oben, rechts von
 * rechts nach links. Liegt der letzte Knickpunkt auf der falschen Seite, wird
 * ein zusätzlicher (nicht gespeicherter) Umlenkpunkt eingefügt.
 */
function approachPoints(start, waypoints, end, tgtPort) {
  const wps = waypoints.map(p => [p[0], p[1]]);
  const last = wps.length ? wps[wps.length-1] : start;
  const [ex,ey] = end;
  if (tgtPort === 'top'    && last[1] <= ey - 1) return wps;
  if (tgtPort === 'bottom' && last[1] >= ey + 1) return wps;
  if (tgtPort === 'right'  && last[0] >= ex + 1) return wps;
  if (tgtPort === 'left'   && last[0] <= ex - 1) return wps;

  if (tgtPort === 'top' || tgtPort === 'bottom') {
    const dir = tgtPort === 'top' ? -1 : 1;
    let cx = last[0];
    if (Math.abs(cx - ex) < 1) cx = ex + APPROACH*2;   // sonst liefe der Pfeil auf sich selbst zurück
    wps.push([cx, ey + dir*APPROACH]);
  } else {
    const dir = tgtPort === 'right' ? 1 : -1;
    let cy = last[1];
    if (Math.abs(cy - ey) < 1) cy = ey + APPROACH*2;
    wps.push([ex + dir*APPROACH, cy]);
  }
  return wps;
}

function labelPos(route) {
  let bestLen = -1, best = route[Math.floor(route.length/2)];
  for (let i = 0; i < route.length-1; i++) {
    const [ax,ay] = route[i], [bx,by] = route[i+1];
    const seg = Math.abs(bx-ax) + Math.abs(by-ay);
    if (seg > bestLen) { bestLen = seg; best = [(ax+bx)/2, (ay+by)/2]; }
  }
  return best;
}

// ════════════════════════════════════════════════════════════
// Canvas-Setup
// ════════════════════════════════════════════════════════════
function setupCanvas() {
  canvas = document.getElementById('main-canvas');
  ctx    = canvas.getContext('2d');
  resizeCanvas();
  window.addEventListener('resize', resizeCanvas);
}

function resizeCanvas() {
  const cont = document.getElementById('canvas-container');
  const w = cont.clientWidth, h = cont.clientHeight;
  canvas.width  = w * DPR;
  canvas.height = h * DPR;
  canvas.style.width  = w + 'px';
  canvas.style.height = h + 'px';
  redraw();
}

/** Transformations-Ursprung auf Welt-Koordinaten setzen */
function applyTransform(c) {
  c.setTransform(DPR, 0, 0, DPR, -panX * DPR, -panY * DPR);
}

function worldPt(clientX, clientY) {
  const r = canvas.getBoundingClientRect();
  return [clientX - r.left + panX, clientY - r.top + panY];
}

// ════════════════════════════════════════════════════════════
// Zeichnen
// ════════════════════════════════════════════════════════════
function redraw(c) {
  if (!c) c = ctx;
  const isMain = (c === ctx);

  if (isMain) {
    c.save();
    applyTransform(c);
  }

  // Hintergrund (sichtbarer Bereich + Rand)
  c.fillStyle = CANVAS_BG;
  if (isMain) {
    c.fillRect(panX-50, panY-50,
               canvas.width/DPR + 100, canvas.height/DPR + 100);
  }

  if (showGrid && isMain) drawGrid(c);

  for (const a of Object.values(arrows)) drawArrow(c, a, false);
  for (const n of Object.values(nodes))  drawNode(c, n);
  drawTempArrow(c);

  // Rubber-Band-Auswahl
  if (dragState && dragState.type === 'rubberband') {
    const {x0,y0,x1,y1} = dragState;
    c.strokeStyle = ACCENT; c.lineWidth = 1;
    c.setLineDash([3,3]);
    c.strokeRect(x0, y0, x1-x0, y1-y0);
    c.setLineDash([]);
  }

  // Palette-Drag-Preview
  if (palDragPreview && isMain) {
    const [wx,wy] = palDragPreview;
    c.strokeStyle = '#60a5fa'; c.lineWidth = 2;
    c.setLineDash([4,3]);
    c.strokeRect(wx-56, wy-24, 112, 48);
    c.setLineDash([]);
  }

  if (isMain) { c.restore(); updateStatus(); updateDeleteButton(); }
}

function drawGrid(c) {
  const step = gridSize;
  const x1 = panX - (panX % step) - step;
  const y1 = panY - (panY % step) - step;
  const x2 = panX + canvas.width/DPR + step;
  const y2 = panY + canvas.height/DPR + step;
  c.strokeStyle = GRID_COLOR; c.lineWidth = 1;
  c.beginPath();
  for (let x = x1; x <= x2; x += step) { c.moveTo(x,y1); c.lineTo(x,y2); }
  for (let y = y1; y <= y2; y += step) { c.moveTo(x1,y); c.lineTo(x2,y); }
  c.stroke();
}

function drawNode(c, n) {
  const sh = shapeOf(n);
  const [fill, border] = NODE_STYLE[n.templateLabel] || DEFAULT_STYLE;
  const sel = selNodes.has(n.id);
  const outline = sel ? ACCENT : border;
  const lw = sel ? 3 : 2;
  const {x,y} = n, w = n.width, h = n.height;
  const [x1,y1,x2,y2] = bbox(n);

  if (sel) {
    c.strokeStyle = ACCENT; c.lineWidth = 1; c.setLineDash([3,3]);
    c.strokeRect(x1-6, y1-6, w+12, h+12);
    c.setLineDash([]);
  }

  c.strokeStyle = outline; c.lineWidth = lw; c.fillStyle = fill;

  if (sh === 'terminator') {
    rrPath(c, x1,y1,x2,y2, h/2); c.fill(); c.stroke();
  } else if (sh === 'diamond') {
    diamondPath(c, x,y,w,h); c.fill(); c.stroke();
  } else if (sh === 'connector') {
    const d = Math.min(w,h)/2;
    c.fillStyle = CANVAS_BG; c.beginPath();
    c.arc(x,y, d, 0, Math.PI*2); c.fill(); c.stroke();
  } else if (sh === 'loop_start') {
    loopStartPath(c,x,y,w,h); c.fill(); c.stroke();
  } else if (sh === 'loop_end') {
    loopEndPath(c,x,y,w,h); c.fill(); c.stroke();
  } else if (sh === 'subroutine') {
    c.fillRect(x1,y1,w,h); c.strokeRect(x1,y1,w,h);
    c.beginPath();
    c.moveTo(x1+10,y1); c.lineTo(x1+10,y2);
    c.moveTo(x2-10,y1); c.lineTo(x2-10,y2);
    c.stroke();
  } else {
    c.fillRect(x1,y1,w,h); c.strokeRect(x1,y1,w,h);
  }

  if (!UNLABELED.has(sh) && n.label) {
    c.fillStyle = TEXT_COLOR;
    c.font = NODE_FONT;
    c.textAlign = 'center'; c.textBaseline = 'middle';
    wrapText(c, n.label, x, y, w-18);
  }

  drawPorts(c, n);
  if (sel && selNodes.size === 1) drawWidthGrip(c, n);
}

/** Anfasser rechts unten an der Auswahl – zieht die Blockbreite auf. */
function widthGrip(n) {
  const [,, x2, y2] = bbox(n);
  return [x2 + GRIP, y2 + GRIP];
}

function drawWidthGrip(c, n) {
  if (!isResizable(n)) return;
  const [gx,gy] = widthGrip(n);
  c.fillStyle = '#ffffff'; c.strokeStyle = ACCENT; c.lineWidth = 2;
  c.beginPath(); c.rect(gx-GRIP, gy-GRIP, GRIP*2, GRIP*2);
  c.fill(); c.stroke();
  c.strokeStyle = ACCENT; c.lineWidth = 1;
  c.beginPath();
  c.moveTo(gx-3, gy-1); c.lineTo(gx+3, gy-1);
  c.moveTo(gx-3, gy+2); c.lineTo(gx+3, gy+2);
  c.stroke();
}

/**
 * Text in Zeilen zerlegen: zuerst an harten Umbrüchen (\n, per Strg/⌘+Enter
 * eingegeben), danach zusätzlich an Wortgrenzen, wenn die Breite nicht reicht.
 */
function wrapLines(c, text, maxW) {
  const lines = [];
  for (const para of String(text == null ? '' : text).split('\n')) {
    let cur = '';
    for (const w of para.split(' ')) {
      const test = cur ? cur+' '+w : w;
      if (c.measureText(test).width <= maxW || !cur) { cur = test; }
      else { lines.push(cur); cur = w; }
    }
    lines.push(cur);
  }
  return lines;
}

/** Messkontext ohne Bildschirmbezug – auch vor dem ersten redraw() nutzbar. */
let measCanvas = null;
function measureCtx() {
  if (!measCanvas) measCanvas = document.createElement('canvas');
  const c = measCanvas.getContext('2d');
  c.font = NODE_FONT;
  return c;
}

function wrapText(c, text, cx, cy, maxW) {
  const lines = wrapLines(c, text, maxW);
  const startY = cy - (lines.length * LINE_H)/2 + LINE_H/2;
  for (let i = 0; i < lines.length; i++) c.fillText(lines[i], cx, startY + i*LINE_H);
}

function drawPorts(c, n) {
  const occ = occupiedPorts();
  const ps  = ports(n);
  for (const nm of allowedPorts(n)) {
    if (occ.has(`${n.id}:${nm}`)) continue;
    const [px,py] = ps[nm];
    c.fillStyle = '#ffffff'; c.strokeStyle = ACCENT; c.lineWidth = 1;
    c.beginPath(); c.arc(px,py, PORT_R, 0, Math.PI*2); c.fill(); c.stroke();
  }
}

function occupiedPorts() {
  const s = new Set();
  for (const a of Object.values(arrows)) {
    s.add(`${a.sourceId}:${a.sourcePort}`);
    s.add(`${a.targetId}:${a.targetPort}`);
  }
  return s;
}

function drawArrow(c, a, dashed) {
  const route = arrowRoute(a);
  if (!route || route.length < 2) return;
  const color = a.id === selArrow ? ACCENT : ARROW_COLOR;
  c.strokeStyle = color; c.fillStyle = color; c.lineWidth = 2;
  if (dashed) c.setLineDash([5,4]);
  c.beginPath();
  c.moveTo(route[0][0], route[0][1]);
  for (let i = 1; i < route.length; i++) c.lineTo(route[i][0], route[i][1]);
  c.stroke();
  c.setLineDash([]);
  const n = route.length;
  arrowHead(c, route[n-2][0], route[n-2][1], route[n-1][0], route[n-1][1], color);
  if (a.label) {
    const [mx,my] = labelPos(route);
    c.fillStyle = CANVAS_BG;
    c.fillRect(mx-3, my-9, 13 + 7*a.label.length, 18);
    c.fillStyle = TEXT_COLOR;
    c.font = 'bold 10px Helvetica,Arial,sans-serif';
    c.textAlign = 'left'; c.textBaseline = 'middle';
    c.fillText(a.label, mx, my);
  }
  if (a.id === selArrow) drawBends(c, a);
}

/** Knickpunkte des markierten Pfeils als verschiebbare Griffe zeichnen. */
function drawBends(c, a) {
  for (const [wx,wy] of (a.waypoints || [])) {
    c.fillStyle = '#ffffff'; c.strokeStyle = ACCENT; c.lineWidth = 2;
    c.beginPath(); c.arc(wx, wy, BEND_R, 0, Math.PI*2);
    c.fill(); c.stroke();
  }
}

function arrowHead(c, x1,y1,x2,y2, color) {
  const ang = Math.atan2(y2-y1, x2-x1), L = 10, sp = 0.45;
  c.fillStyle = color; c.beginPath();
  c.moveTo(x2, y2);
  c.lineTo(x2 - L*Math.cos(ang-sp), y2 - L*Math.sin(ang-sp));
  c.lineTo(x2 - L*Math.cos(ang+sp), y2 - L*Math.sin(ang+sp));
  c.closePath(); c.fill();
}

function drawTempArrow(c) {
  if (!connSrc || !tempTarget) return;
  const src = nodes[connSrc.nodeId]; if (!src) return;
  const start = ports(src)[connSrc.port];
  const route = orthoPts(start, connSrc.port,
                         approachPoints(start, [], tempTarget, 'top'), tempTarget, 'top');
  c.strokeStyle = '#7c3aed'; c.fillStyle = '#7c3aed';
  c.lineWidth = 2; c.setLineDash([4,4]);
  c.beginPath();
  c.moveTo(route[0][0], route[0][1]);
  for (let i = 1; i < route.length; i++) c.lineTo(route[i][0], route[i][1]);
  c.stroke(); c.setLineDash([]);
  const n = route.length;
  arrowHead(c, route[n-2][0], route[n-2][1], route[n-1][0], route[n-1][1], '#7c3aed');
}

// ════════════════════════════════════════════════════════════
// Hit-Testing
// ════════════════════════════════════════════════════════════
function hitNode(wx, wy) {
  const list = Object.values(nodes);
  for (let i = list.length-1; i >= 0; i--) {
    const [x1,y1,x2,y2] = bbox(list[i]);
    if (wx >= x1-SEL_MARGIN && wx <= x2+SEL_MARGIN &&
        wy >= y1-SEL_MARGIN && wy <= y2+SEL_MARGIN) return list[i].id;
  }
  return null;
}

function hitPort(n, wx, wy) {
  const ps = ports(n);
  for (const nm of allowedPorts(n)) {
    const [px,py] = ps[nm];
    if (Math.hypot(px-wx, py-wy) <= 14) return nm;
  }
  return null;
}

/** Breiten-Anfasser des einzeln markierten Blocks treffen? */
function hitWidthGrip(wx, wy) {
  if (selNodes.size !== 1) return null;
  const n = nodes[[...selNodes][0]];
  if (!n) return null;
  if (!isResizable(n)) return null;
  const [gx,gy] = widthGrip(n);
  return (Math.abs(wx-gx) <= GRIP+4 && Math.abs(wy-gy) <= GRIP+4) ? n.id : null;
}

/** Knickpunkt des markierten Pfeils treffen? → Index oder null */
function hitBend(wx, wy) {
  if (selArrow === null) return null;
  const a = arrows[selArrow];
  if (!a) return null;
  const wps = a.waypoints || [];
  for (let i = wps.length-1; i >= 0; i--)
    if (Math.hypot(wps[i][0]-wx, wps[i][1]-wy) <= BEND_R+6) return i;
  return null;
}

function hitArrow(wx, wy) {
  const list = Object.values(arrows);
  for (let i = list.length-1; i >= 0; i--) {
    if (distToArrow(list[i], wx, wy) <= 8) return list[i].id;
  }
  return null;
}

function distToArrow(a, wx, wy) {
  const r = arrowRoute(a); if (!r) return Infinity;
  let best = Infinity;
  for (let i = 0; i < r.length-1; i++)
    best = Math.min(best, distSeg(wx,wy, r[i][0],r[i][1], r[i+1][0],r[i+1][1]));
  return best;
}

function distSeg(px,py, x1,y1,x2,y2) {
  const dx = x2-x1, dy = y2-y1;
  if (!dx && !dy) return Math.hypot(px-x1, py-y1);
  const t = Math.max(0, Math.min(1, ((px-x1)*dx+(py-y1)*dy)/(dx*dx+dy*dy)));
  return Math.hypot(px-(x1+t*dx), py-(y1+t*dy));
}

function nodesInRect(x0,y0,x1,y1) {
  const L = Math.min(x0,x1), R = Math.max(x0,x1);
  const T = Math.min(y0,y1), B = Math.max(y0,y1);
  const res = new Set();
  for (const n of Object.values(nodes)) {
    const [nx1,ny1,nx2,ny2] = bbox(n);
    if (L < nx2 && R > nx1 && T < ny2 && B > ny1) res.add(n.id);
  }
  return res;
}

// ════════════════════════════════════════════════════════════
// Node- / Arrow-Operationen
// ════════════════════════════════════════════════════════════
function addNode(templateLabel, kind, text, x, y, imageRel) {
  x = snap(x); y = snap(y);
  const n = {
    id: nextNid++, kind, label: text || templateLabel,
    x, y, width: NODE_W, height: NODE_H,
    imageRel: imageRel || '', templateLabel,
    subdiagram: '', textAnchor: 'center',
  };
  fitSize(n);
  nodes[n.id] = n;
  return n;
}

/** Blöcke mit manuell gesetzter Breite wachsen nicht mehr automatisch mit. */
function fitSize(n) {
  const sh = shapeOf(n);
  if (sh === 'connector')    { n.width = n.height = 26; return; }
  if (UNLABELED.has(sh))     return;
  const c = measureCtx();
  const label = n.label || '';

  if (!n.manualWidth) {
    let tw = 0;
    for (const para of label.split('\n')) tw = Math.max(tw, c.measureText(para).width);
    tw += 24;
    if (sh === 'diamond') n.width = Math.max(n.width, snap(tw*1.7));
    else                  n.width = Math.max(n.width, snap(tw));
  }
  n.width = Math.max(MIN_NODE_W, n.width);

  const lines = wrapLines(c, label, Math.max(20, n.width - 18)).length;
  const needH = lines*LINE_H + (sh === 'diamond' ? 40 : 22);
  n.height = Math.max(sh === 'diamond' ? 88 : NODE_H, needH);
}

/** Breite manuell festlegen (rastet aufs Raster, Höhe folgt dem Text). */
function setNodeWidth(n, w) {
  if (!isResizable(n)) return;
  n.width = Math.max(MIN_NODE_W, snap(w));
  n.manualWidth = true;
  fitSize(n);
}

/** Runde Konnektoren behalten ihre Form – alle anderen Blöcke sind breitenverstellbar. */
function isResizable(n) { return !!n && shapeOf(n) !== 'connector'; }

function resizableNodes(ids) {
  return [...ids].map(id => nodes[id]).filter(isResizable);
}

/** Alle markierten Blöcke auf die Breite des breitesten bringen. */
function equalizeWidth() {
  const list = resizableNodes(selNodes);
  if (list.length < 2) { setStatus('Mindestens zwei Blöcke markieren, um die Breite anzugleichen.'); return; }
  const w = Math.max(...list.map(n => n.width));
  pushUndo();
  for (const n of list) setNodeWidth(n, w);
  redraw();
  setStatus(`${list.length} Blöcke auf ${Math.round(w)} px Breite gebracht`);
}

/** Automatische Breite wiederherstellen. */
function resetWidth() {
  const list = resizableNodes(selNodes);
  if (!list.length) return;
  pushUndo();
  for (const n of list) { n.manualWidth = false; n.width = NODE_W; fitSize(n); }
  redraw();
  setStatus(`${list.length} Block/Blöcke auf automatische Breite zurückgesetzt`);
}

function hasPath(startId, targetId) {
  const seen = new Set(), stk = [startId];
  while (stk.length) {
    const c = stk.pop();
    if (c === targetId) return true;
    if (seen.has(c)) continue; seen.add(c);
    for (const a of Object.values(arrows))
      if (a.sourceId === c) stk.push(a.targetId);
  }
  return false;
}

function addArrow(srcId, srcPort, tgtId, tgtPort) {
  if (srcId === tgtId) return null;
  const s = nodes[srcId], t = nodes[tgtId];
  if (!s || !t) return null;
  if (srcPort === 'top' || tgtPort === 'bottom') return null;
  if (hasPath(tgtId, srcId)) return null;
  const a = { id: nextAid++, sourceId: srcId, sourcePort: srcPort,
              targetId: tgtId, targetPort: tgtPort, waypoints: [], label: '' };
  // Liegt das Ziel weiter oben, wird ein Weg außen herum vorbelegt; die
  // Knickpunkte lassen sich anschließend am Raster verschieben.
  if (t.y < s.y) a.waypoints = backJumpWaypoints(s, srcPort, t, tgtPort);
  arrows[a.id] = a; return a;
}

/** Vorschlag für den Umweg eines Pfeils, der zu einem höher liegenden Block führt. */
function backJumpWaypoints(s, srcPort, t, tgtPort) {
  if (srcPort !== 'bottom' || tgtPort !== 'top') return [];
  const lane = snap(Math.max(s.x + s.width/2, t.x + t.width/2) + gridSize);
  const below = snap(s.y + s.height/2 + gridSize);
  const above = snap(t.y - t.height/2 - gridSize);
  return [[snap(s.x), below], [lane, below], [lane, above]];
}

function bestTgtPort(src, tgt) {
  const sh = shapeOf(tgt);
  if (sh !== 'diamond' && sh !== 'connector') return 'top';
  if (src.x - tgt.x > tgt.width/2 + 4) return 'right';
  return 'top';
}

function removeNode(id) {
  delete nodes[id];
  for (const [aid, a] of Object.entries(arrows))
    if (a.sourceId === id || a.targetId === id) delete arrows[aid];
}

function deleteSelected() {
  if (!selNodes.size && selArrow === null) return;
  pushUndo();
  for (const id of selNodes) removeNode(id);
  selNodes = new Set();
  if (selArrow !== null) { delete arrows[selArrow]; selArrow = null; }
  redraw();
}

function selectAll() {
  selNodes = new Set(Object.keys(nodes).map(Number));
  selArrow = null; redraw();
}

function overlapsAny(x, y, w, h, m) {
  m = m || 10;
  const [ax1,ay1,ax2,ay2] = [x-w/2-m, y-h/2-m, x+w/2+m, y+h/2+m];
  for (const n of Object.values(nodes)) {
    const [nx1,ny1,nx2,ny2] = bbox(n);
    if (ax1 < nx2 && ax2 > nx1 && ay1 < ny2 && ay2 > ny1) return true;
  }
  return false;
}

function freeSpot(x, y, w, h) {
  x = snap(x); y = snap(y);
  const sx = x; let row = 0, col = 0;
  while (overlapsAny(x, y, w, h)) {
    row++;
    y += Math.max(gridSize*2, 80);
    if (row % 8 === 0) { col++; row = 0; x = snap(sx + col*(w+gridSize*2)); }
  }
  return [x, y];
}

// ════════════════════════════════════════════════════════════
// Undo / Redo
// ════════════════════════════════════════════════════════════
function statePayload() {
  return {
    nodes:        Object.values(nodes).map(n => ({...n})),
    arrows:       Object.values(arrows).filter(a => a.id !== -1)
                        .map(a => ({...a, waypoints: a.waypoints.map(p => [...p])})),
    next_node_id:  nextNid,
    next_arrow_id: nextAid,
  };
}

function loadPayload(p) {
  nodes = {}; arrows = {};
  for (const item of (p.nodes || [])) {
    const n = {...item};
    // Kompatibilität desktop ↔ web (snake_case → camelCase)
    for (const [snake, camel] of [['image_rel','imageRel'], ['template_label','templateLabel'],
                                  ['text_anchor','textAnchor'], ['manual_width','manualWidth']]) {
      if (n[snake] !== undefined) { n[camel] = n[snake]; delete n[snake]; }
    }
    nodes[n.id] = n;
  }
  for (const item of (p.arrows || [])) {
    const a = {...item};
    // Kompatibilität desktop ↔ web (camelCase ↔ snake_case)
    if (a.source_id !== undefined) {
      a.sourceId = a.source_id; a.sourcePort = a.source_port;
      a.targetId = a.target_id; a.targetPort = a.target_port;
      delete a.source_id; delete a.source_port;
      delete a.target_id; delete a.target_port;
    }
    if (!Array.isArray(a.waypoints)) a.waypoints = [];
    arrows[a.id] = a;
  }
  nextNid = p.next_node_id  || p.nextNodeId  || Math.max(0, ...Object.keys(nodes).map(Number))  + 1;
  nextAid = p.next_arrow_id || p.nextArrowId || Math.max(0, ...Object.keys(arrows).map(Number)) + 1;
}

function serialize()     { return JSON.stringify(statePayload()); }
function restoreSnap(s)  {
  loadPayload(JSON.parse(s));
  selNodes = new Set([...selNodes].filter(id => nodes[id]));
  selArrow = null; redraw();
}

function pushUndo() {
  undoStack.push(serialize());
  if (undoStack.length > 100) undoStack.shift();
  redoStack = [];
}

function undo() {
  if (!undoStack.length) return;
  redoStack.push(serialize()); restoreSnap(undoStack.pop());
}

function redo() {
  if (!redoStack.length) return;
  undoStack.push(serialize()); restoreSnap(redoStack.pop());
}

// ════════════════════════════════════════════════════════════
// Kopieren / Einfügen
// ════════════════════════════════════════════════════════════
function copySelection() {
  if (!selNodes.size) return;
  clipboard = {
    nodes:  [...selNodes].filter(id => nodes[id]).map(id => ({...nodes[id]})),
    arrows: Object.values(arrows)
              .filter(a => selNodes.has(a.sourceId) && selNodes.has(a.targetId))
              .map(a => ({...a, waypoints: a.waypoints.map(p=>[...p])})),
  };
  setStatus(`${clipboard.nodes.length} Baustein(e) kopiert`);
}

function pasteSelection() {
  if (!clipboard || !clipboard.nodes.length) return;
  pushUndo();
  const off = gridSize, idMap = {}, newIds = new Set();
  for (const item of clipboard.nodes) {
    const n = {...item, id: nextNid++, x: snap(item.x+off), y: snap(item.y+off)};
    nodes[n.id] = n; idMap[item.id] = n.id; newIds.add(n.id);
  }
  for (const item of clipboard.arrows) {
    const src = idMap[item.sourceId], tgt = idMap[item.targetId];
    if (src === undefined || tgt === undefined) continue;
    const a = {...item, id: nextAid++, sourceId: src, targetId: tgt,
               waypoints: (item.waypoints||[]).map(([wx,wy]) => [snap(wx+off),snap(wy+off)])};
    arrows[a.id] = a;
  }
  selNodes = newIds; selArrow = null; redraw();
}

// ════════════════════════════════════════════════════════════
// Sub-Diagramme (Funktionen)
// ════════════════════════════════════════════════════════════
function openFunction(n) {
  ctxStack.push({nodes, arrows, nextNid, nextAid, node: n, title: ctxTitle});
  nodes = {}; arrows = {}; nextNid = 1; nextAid = 1;
  if (n.subdiagram) { try { loadPayload(JSON.parse(n.subdiagram)); } catch(e){} }
  if (!Object.keys(nodes).length) createFunctionScene();
  ctxTitle = `Funktion: ${n.label || 'unbenannt'}`;
  selNodes = new Set(); selArrow = null;
  undoStack = []; redoStack = [];
  updateCtxUI(); redraw();
}

function closeFunction() {
  if (!ctxStack.length) return;
  const par = ctxStack.pop();
  par.node.subdiagram = JSON.stringify(statePayload());
  nodes = par.nodes; arrows = par.arrows;
  nextNid = par.nextNid; nextAid = par.nextAid;
  ctxTitle = par.title;
  selNodes = new Set(); selArrow = null;
  undoStack = []; redoStack = [];
  updateCtxUI(); redraw();
}

function returnToRoot() { while (ctxStack.length) closeFunction(); }

function createStartScene() {
  const s  = addNode('Start',    'terminator', 'Start',    350, 120, 'Bilder/Start.png');
  const m  = addNode('Funktion', 'subroutine', 'Schritt 1',350, 280, 'Bilder/Funktion.png');
  const st = addNode('Stop',     'terminator', 'Stop',     350, 440, 'Bilder/Stop.png');
  addArrow(s.id,'bottom',m.id,'top'); addArrow(m.id,'bottom',st.id,'top');
}

function createFunctionScene() {
  const s  = addNode('Start','terminator','Start',360,120,'');
  const st = addNode('Stop', 'terminator','Stop', 360,320,'');
  addArrow(s.id,'bottom',st.id,'top');
}

function updateCtxUI() {
  const crumbs = [...ctxStack.map(c=>c.title), ctxTitle];
  document.getElementById('breadcrumb').textContent = crumbs.join(' › ');
  document.getElementById('back-btn').style.display = ctxStack.length ? 'inline-block' : 'none';
}

// ════════════════════════════════════════════════════════════
// Diagramm-Validierung (Regelwerk für PAP / DIN 66001)
// ════════════════════════════════════════════════════════════
//
// Entspricht der Logik in pap_editor.py (siehe dort für Details zu den
// bewusst nicht umgesetzten Regeln R07/R13/R16/R21/R32-R35 und wie man eine
// neue Regel ergänzt).

const ROLE_BY_TEMPLATE = {
  'Start': 'start', 'Stop': 'stop', 'Anweisung': 'process', 'Funktion': 'subprocess',
  'Entscheidung': 'decision', 'Verzweigung zu': 'branchEnd', 'Schleife': 'loopStart', 'Schleife zu': 'loopEnd',
};
function roleOf(n) { return ROLE_BY_TEMPLATE[n.templateLabel] || 'process'; }

const ROLE_NAMES_DE = { process: 'Anweisungs', loopStart: 'Schleifen', loopEnd: 'Schleife-zu', subprocess: 'Funktions' };
const UNLABELED_ROLE_NAMES = { branchEnd: 'Verzweigung zu', loopEnd: 'Schleife zu' };
function displayLabel(n) {
  // Zeilenumbrüche im Blocktext für Meldungen zu einer Zeile zusammenziehen
  if (n.label && n.label.trim()) return n.label.replace(/\s*\n\s*/g, ' ');
  return UNLABELED_ROLE_NAMES[roleOf(n)] || n.label || '?';
}

const COMPARISON_OPS = ['==', '!=', '<=', '>=', '<', '>'];
const BOOL_WORDS = ['und', 'oder', 'nicht', 'and', 'or', 'not', '&&', '||'];
const YES_WORDS = new Set(['ja', 'yes', 'j', 'y', 'true', 'wahr']);
const NO_WORDS = new Set(['nein', 'no', 'n', 'false', 'falsch']);
const IDENT_RE = /[A-Za-z_]\w*/g;
const ASSIGN_RE = /:=|<-|(?<![=!<>])=(?!=)/;
const STRING_LITERAL_RE = /'[^']*'|"[^"]*"/g;
const STOPWORDS = new Set([
  'und', 'oder', 'nicht', 'and', 'or', 'not', 'true', 'false', 'wahr', 'falsch',
  'then', 'dann', 'if', 'wenn', 'sonst', 'else', 'ausgabe', 'eingabe', 'print',
  'input', 'cout', 'system', 'out', 'write', 'gib', 'aus', 'schreibe', 'lies', 'einlesen',
]);

function F(rule, severity, message, nodeIds, arrowIds) {
  return { rule, severity, message, nodeIds: nodeIds || [], arrowIds: arrowIds || [] };
}

function splitAssignment(text) {
  const m = ASSIGN_RE.exec(text || '');
  if (!m) return null;
  return [text.slice(0, m.index), text.slice(m.index + m[0].length)];
}

function extractIdentifiers(text) {
  const out = new Set();
  const cleaned = (text || '').replace(STRING_LITERAL_RE, ' ');
  for (const m of cleaned.matchAll(IDENT_RE)) {
    if (!STOPWORDS.has(m[0].toLowerCase())) out.add(m[0]);
  }
  return out;
}

function buildEdgeMaps(nodesObj, arrowsObj) {
  const outgoing = {}, incoming = {};
  for (const a of Object.values(arrowsObj)) {
    if (nodesObj[a.sourceId] && nodesObj[a.targetId]) {
      (outgoing[a.sourceId] = outgoing[a.sourceId] || []).push(a);
      (incoming[a.targetId] = incoming[a.targetId] || []).push(a);
    }
  }
  return { outgoing, incoming };
}

// ---- A. Globale Struktur ----

function checkR01Start(nodesObj) {
  const starts = Object.values(nodesObj).filter(n => roleOf(n) === 'start');
  if (starts.length === 0) return [F('R01', 'error', 'Es gibt keinen Start-Block – jeder Ablauf braucht genau einen.')];
  if (starts.length > 1) return [F('R01', 'error', `Es gibt ${starts.length} Start-Blöcke – es darf nur genau einen geben.`, starts.map(n => n.id))];
  return [];
}

function checkR02StopExists(nodesObj) {
  if (!Object.values(nodesObj).some(n => roleOf(n) === 'stop')) {
    return [F('R02', 'error', 'Es gibt keinen Stop-Block – jeder Ablauf muss enden.')];
  }
  return [];
}

function checkR03MultipleStops(nodesObj) {
  const stops = Object.values(nodesObj).filter(n => roleOf(n) === 'stop');
  if (stops.length > 1) {
    return [F('R03', 'warning', `Es gibt ${stops.length} Stop-Blöcke – meist ist genau ein Stop-Block übersichtlicher.`, stops.map(n => n.id))];
  }
  return [];
}

function checkR04ReachableFromStart(nodesObj, outgoing) {
  const starts = Object.values(nodesObj).filter(n => roleOf(n) === 'start');
  if (starts.length !== 1) return [];
  const reachable = new Set();
  const stack = [starts[0].id];
  while (stack.length) {
    const cur = stack.pop();
    if (reachable.has(cur)) continue;
    reachable.add(cur);
    for (const a of (outgoing[cur] || [])) stack.push(a.targetId);
  }
  return Object.values(nodesObj)
    .filter(n => !reachable.has(n.id))
    .map(n => F('R04', 'error', `Der Block »${displayLabel(n)}« ist vom Start aus nicht erreichbar.`, [n.id]));
}

function checkR05ReachStop(nodesObj, incoming) {
  const stops = Object.values(nodesObj).filter(n => roleOf(n) === 'stop');
  if (!stops.length) return [];
  const canReachStop = new Set();
  const stack = stops.map(s => s.id);
  while (stack.length) {
    const cur = stack.pop();
    if (canReachStop.has(cur)) continue;
    canReachStop.add(cur);
    for (const a of (incoming[cur] || [])) stack.push(a.sourceId);
  }
  return Object.values(nodesObj)
    .filter(n => !canReachStop.has(n.id))
    .map(n => F('R05', 'error', `Vom Block »${displayLabel(n)}« aus wird kein Stop-Block mehr erreicht (Sackgasse).`, [n.id]));
}

function checkR06Connected(nodesObj, arrowsObj) {
  const ids = Object.values(nodesObj).map(n => n.id);
  if (!ids.length) return [];
  const adjacency = {};
  for (const a of Object.values(arrowsObj)) {
    if (nodesObj[a.sourceId] && nodesObj[a.targetId]) {
      (adjacency[a.sourceId] = adjacency[a.sourceId] || new Set()).add(a.targetId);
      (adjacency[a.targetId] = adjacency[a.targetId] || new Set()).add(a.sourceId);
    }
  }
  const seen = new Set();
  const stack = [ids[0]];
  while (stack.length) {
    const cur = stack.pop();
    if (seen.has(cur)) continue;
    seen.add(cur);
    for (const nb of (adjacency[cur] || [])) stack.push(nb);
  }
  return Object.values(nodesObj)
    .filter(n => !seen.has(n.id))
    .map(n => F('R06', 'error', `Der Block »${displayLabel(n)}« gehört zu einem vom restlichen Ablaufplan getrennten Teil.`, [n.id]));
}

// ---- B. Verbindungen und Knotengrade ----

function checkR08DanglingEdges(nodesObj, arrowsObj) {
  const findings = [];
  for (const a of Object.values(arrowsObj)) {
    if (!nodesObj[a.sourceId] || !nodesObj[a.targetId]) {
      findings.push(F('R08', 'error', 'Ein Pfeil verweist auf einen nicht (mehr) vorhandenen Block – die Datei scheint beschädigt zu sein.', [], [a.id]));
    }
  }
  return findings;
}

function checkNodeDegrees(nodesObj, incoming, outgoing) {
  const findings = [];
  for (const node of Object.values(nodesObj)) {
    const role = roleOf(node);
    const label = displayLabel(node);
    const inCount = (incoming[node.id] || []).length;
    const outCount = (outgoing[node.id] || []).length;
    if (role === 'start') {
      if (inCount > 0) findings.push(F('R10', 'error', `Der Start-Block »${label}« darf keinen eingehenden Pfeil haben.`, [node.id]));
      if (outCount === 0) findings.push(F('R10', 'error', `Der Start-Block »${label}« hat keinen ausgehenden Pfeil.`, [node.id]));
      else if (outCount > 1) findings.push(F('R10', 'error', `Der Start-Block »${label}« hat ${outCount} ausgehende Pfeile – erlaubt ist genau einer.`, [node.id]));
    } else if (role === 'stop') {
      if (inCount === 0) findings.push(F('R10', 'error', `Der Stop-Block »${label}« hat keinen eingehenden Pfeil.`, [node.id]));
      if (outCount > 0) findings.push(F('R10', 'error', `Der Stop-Block »${label}« darf keinen ausgehenden Pfeil haben.`, [node.id]));
    } else if (role === 'decision') {
      if (inCount === 0) findings.push(F('R10', 'error', `Die Verzweigung »${label}« hat keinen eingehenden Pfeil.`, [node.id]));
      if (outCount !== 2) findings.push(F('R10', 'error', `Die Verzweigung »${label}« hat ${outCount} ausgehende Pfeile. Eine Verzweigung braucht genau zwei: Ja und Nein.`, [node.id]));
    } else if (role === 'branchEnd') {
      if (inCount !== 2) findings.push(F('R10', 'error', `Der Verzweigung-zu-Block »${label}« hat ${inCount} eingehende Pfeile statt der geforderten zwei (je einer pro Zweig).`, [node.id]));
      if (outCount !== 1) findings.push(F('R10', 'error', `Der Verzweigung-zu-Block »${label}« hat ${outCount} ausgehende Pfeile statt genau einem.`, [node.id]));
    } else {
      const kind = ROLE_NAMES_DE[role] || role;
      if (inCount === 0) findings.push(F('R10', 'error', `Der ${kind}-Block »${label}« ist nicht erreichbar (kein eingehender Pfeil).`, [node.id]));
      if (outCount === 0) findings.push(F('R10', 'error', `Der ${kind}-Block »${label}« hat keinen ausgehenden Pfeil.`, [node.id]));
      else if (outCount > 1) findings.push(F('R10', 'error', `Der ${kind}-Block »${label}« hat ${outCount} ausgehende Pfeile, ist aber kein Verzweigungsblock.`, [node.id]));
    }
  }
  return findings;
}

function checkR11SelfLoop(nodesObj, arrowsObj) {
  const findings = [];
  for (const a of Object.values(arrowsObj)) {
    if (a.sourceId === a.targetId && nodesObj[a.sourceId]) {
      findings.push(F('R11', 'error', `Der Block »${displayLabel(nodesObj[a.sourceId])}« ist über einen Pfeil mit sich selbst verbunden.`, [a.sourceId], [a.id]));
    }
  }
  return findings;
}

function checkR12DuplicateEdges(nodesObj, arrowsObj) {
  const findings = [];
  const seen = new Map();
  for (const a of Object.values(arrowsObj)) {
    const key = `${a.sourceId}|${a.sourcePort}|${a.targetId}|${a.targetPort}`;
    if (seen.has(key)) {
      const s = nodesObj[a.sourceId], t = nodesObj[a.targetId];
      findings.push(F('R12', 'warning',
        `Zwischen »${s ? displayLabel(s) : '?'}« und »${t ? displayLabel(t) : '?'}« gibt es doppelte Pfeile.`,
        [a.sourceId, a.targetId].filter(id => nodesObj[id]), [seen.get(key), a.id]));
    } else {
      seen.set(key, a.id);
    }
  }
  return findings;
}

// ---- C. Geometrie ----

function checkGeometryPorts(nodesObj, arrowsObj) {
  const findings = [];
  for (const a of Object.values(arrowsObj)) {
    const source = nodesObj[a.sourceId], target = nodesObj[a.targetId];
    if (!source || !target) continue;
    const isBranchEdge = roleOf(source) === 'decision' && a.sourcePort === 'right';
    if (a.sourcePort === 'top' || a.targetPort === 'bottom') {
      findings.push(F('R14', 'error',
        `Der Pfeil von »${displayLabel(source)}« nach »${displayLabel(target)}« beginnt oder endet an der falschen Seite – Pfeile müssen unten beginnen und oben am nächsten Block enden.`,
        [source.id, target.id], [a.id]));
      continue;
    }
    if (a.sourcePort === 'right' && !isBranchEdge) {
      findings.push(F('R14', 'error',
        `Der Pfeil von »${displayLabel(source)}« verlässt den Block seitlich, obwohl es kein Verzweigungsblock ist – Pfeile müssen unten beginnen.`,
        [source.id], [a.id]));
    }
    if (isBranchEdge && a.targetPort !== 'right' && a.targetPort !== 'top') {
      findings.push(F('R15', 'error',
        `Der seitliche Zweig der Verzweigung »${displayLabel(source)}« muss rechts oder oben in den nächsten Block münden.`,
        [source.id, target.id], [a.id]));
    }
    if (a.sourcePort !== 'right' && target.y < source.y) {
      // Rücksprung von einem Schleifenende an einen weiter oben liegenden
      // Schleifenanfang ist zulässig – er wird nur als Hinweis gemeldet (R16).
      if (roleOf(source) === 'loopEnd' && roleOf(target) === 'loopStart' && a.targetPort === 'top') {
        findings.push(F('R16', 'warning',
          `Der Pfeil von »${displayLabel(source)}« nach »${displayLabel(target)}« ist ein Rücksprung nach oben. Das ist erlaubt – prüfe, ob die Wiederholung so gewollt ist und der Pfeil von oben in die Schleife mündet.`,
          [source.id, target.id], [a.id]));
      } else {
        findings.push(F('R17', 'warning',
          `Der Pfeil von »${displayLabel(source)}« nach »${displayLabel(target)}« führt nach oben statt nach unten.`,
          [source.id, target.id], [a.id]));
      }
    }
  }
  for (const node of Object.values(nodesObj)) {
    if (roleOf(node) !== 'decision') continue;
    const portsUsed = Object.values(arrowsObj).filter(a => a.sourceId === node.id).map(a => a.sourcePort);
    if (portsUsed.length === 2 && portsUsed[0] === portsUsed[1]) {
      findings.push(F('R15', 'error',
        `Beide Zweige der Verzweigung »${displayLabel(node)}« verlassen den Block an derselben Seite – Ja und Nein sollten unten und rechts herausgeführt werden.`,
        [node.id]));
    }
  }
  return findings;
}

function checkR19Overlaps(nodesObj) {
  const findings = [];
  const items = Object.values(nodesObj);
  if (items.length > 500) return findings;
  for (let i = 0; i < items.length; i++) {
    const [ax1, ay1, ax2, ay2] = bbox(items[i]);
    for (let j = i + 1; j < items.length; j++) {
      const [bx1, by1, bx2, by2] = bbox(items[j]);
      if (ax1 < bx2 && ax2 > bx1 && ay1 < by2 && ay2 > by1) {
        findings.push(F('R19', 'warning', `Die Blöcke »${displayLabel(items[i])}« und »${displayLabel(items[j])}« überlappen sich.`, [items[i].id, items[j].id]));
      }
    }
  }
  return findings;
}

function segmentsIntersect(p1, p2, p3, p4) {
  const ccw = (a, b, c) => (c[1] - a[1]) * (b[0] - a[0]) > (b[1] - a[1]) * (c[0] - a[0]);
  return ccw(p1, p3, p4) !== ccw(p2, p3, p4) && ccw(p1, p2, p3) !== ccw(p1, p2, p4);
}

function arrowPolyline(nodesObj, a) {
  const source = nodesObj[a.sourceId], target = nodesObj[a.targetId];
  if (!source || !target) return null;
  return [ports(source)[a.sourcePort], ...(a.waypoints || []), ports(target)[a.targetPort]];
}

function checkR18Crossings(nodesObj, arrowsObj) {
  if (Object.keys(nodesObj).length > 500) return [];
  const findings = [];
  const ids = Object.keys(arrowsObj);
  const polylines = {};
  for (const id of ids) polylines[id] = arrowPolyline(nodesObj, arrowsObj[id]);
  for (let i = 0; i < ids.length; i++) {
    const a1 = arrowsObj[ids[i]];
    const p1 = polylines[ids[i]];
    if (!p1) continue;
    for (let j = i + 1; j < ids.length; j++) {
      const a2 = arrowsObj[ids[j]];
      if (a1.sourceId === a2.sourceId || a1.sourceId === a2.targetId ||
          a1.targetId === a2.sourceId || a1.targetId === a2.targetId) continue;
      const p2 = polylines[ids[j]];
      if (!p2) continue;
      let crossed = false;
      for (let k = 0; k < p1.length - 1 && !crossed; k++) {
        for (let l = 0; l < p2.length - 1; l++) {
          if (segmentsIntersect(p1[k], p1[k + 1], p2[l], p2[l + 1])) { crossed = true; break; }
        }
      }
      if (crossed) {
        findings.push(F('R18', 'warning', 'Zwei Pfeile kreuzen sich – das lässt sich meist durch Umsortieren der Blöcke vermeiden.', [], [a1.id, a2.id]));
      }
    }
  }
  return findings;
}

// ---- D. Kontrollstrukturen ----

function checkR25EmptyBodies(nodesObj, outgoing) {
  const findings = [];
  for (const node of Object.values(nodesObj)) {
    const role = roleOf(node);
    if (role === 'decision') {
      for (const a of (outgoing[node.id] || [])) {
        const target = nodesObj[a.targetId];
        if (target && roleOf(target) === 'branchEnd') {
          findings.push(F('R25', 'warning', `Ein Zweig der Verzweigung »${displayLabel(node)}« ist leer (der Pfeil geht direkt zum Verzweigung-zu-Block).`, [node.id, target.id], [a.id]));
        }
      }
    } else if (role === 'loopStart') {
      for (const a of (outgoing[node.id] || [])) {
        const target = nodesObj[a.targetId];
        if (target && roleOf(target) === 'loopEnd') {
          findings.push(F('R25', 'warning', `Der Rumpf der Schleife »${displayLabel(node)}« ist leer (der Pfeil geht direkt zum Schleife-zu-Block).`, [node.id, target.id], [a.id]));
        }
      }
    }
  }
  return findings;
}

function analyzeControlStructureNesting(nodesObj, outgoing) {
  const findings = [];
  const starts = Object.values(nodesObj).filter(n => roleOf(n) === 'start');
  if (!starts.length) return { findings, loopBodyNodes: {} };

  const decisionMerges = {};
  const loopBodyNodes = {};
  const reported = new Set();
  const seenStates = new Set();
  const MAX_STATES = 50000;

  function walk(nodeId, stack) {
    if (seenStates.size > MAX_STATES) return;
    const key = nodeId + '|' + stack.map(m => m[0] + ':' + m[1]).join(',');
    if (seenStates.has(key)) return;
    seenStates.add(key);
    const node = nodesObj[nodeId];
    if (!node) return;

    for (const [kind, markerId] of stack) {
      if (kind === 'LOOP') (loopBodyNodes[markerId] = loopBodyNodes[markerId] || new Set()).add(nodeId);
    }

    const role = roleOf(node);
    let newStack = stack;
    if (role === 'decision') {
      newStack = [...stack, ['DEC', nodeId]];
    } else if (role === 'loopStart') {
      newStack = [...stack, ['LOOP', nodeId]];
    } else if (role === 'branchEnd') {
      if (stack.length && stack[stack.length - 1][0] === 'DEC') {
        const decId = stack[stack.length - 1][1];
        (decisionMerges[decId] = decisionMerges[decId] || new Set()).add(nodeId);
        newStack = stack.slice(0, -1);
      } else if (!reported.has('branchEnd|' + nodeId)) {
        reported.add('branchEnd|' + nodeId);
        findings.push(F('R22', 'error',
          `Der Verzweigung-zu-Block »${displayLabel(node)}« schließt keine offene Verzweigung an dieser Stelle – Verzweigung und Schleife müssen sauber ineinander verschachtelt sein.`,
          [nodeId]));
      }
    } else if (role === 'loopEnd') {
      if (stack.length && stack[stack.length - 1][0] === 'LOOP') {
        newStack = stack.slice(0, -1);
      } else if (!reported.has('loopEnd|' + nodeId)) {
        reported.add('loopEnd|' + nodeId);
        findings.push(F('R22', 'error',
          `Der Schleife-zu-Block »${displayLabel(node)}« schließt keine offene Schleife an dieser Stelle – Verzweigung und Schleife müssen sauber ineinander verschachtelt sein.`,
          [nodeId]));
      }
    }

    const outs = outgoing[nodeId] || [];
    if (!outs.length && role === 'stop' && newStack.length) {
      for (const [kind, markerId] of newStack) {
        const rkey = kind + '|' + markerId;
        if (reported.has(rkey)) continue;
        reported.add(rkey);
        const markerNode = nodesObj[markerId];
        const markerLabel = markerNode ? displayLabel(markerNode) : '?';
        if (kind === 'DEC') {
          findings.push(F('R20', 'error', `Die Verzweigung »${markerLabel}« wird auf diesem Pfad nie durch einen Verzweigung-zu-Block geschlossen.`, [markerId]));
        } else {
          findings.push(F('R20', 'error', `Die Schleife »${markerLabel}« wird auf diesem Pfad nie durch einen Schleife-zu-Block geschlossen.`, [markerId]));
        }
      }
    }
    for (const a of outs) walk(a.targetId, newStack);
  }

  walk(starts[0].id, []);

  for (const [decId, merges] of Object.entries(decisionMerges)) {
    if (merges.size > 1) {
      const dec = nodesObj[decId];
      findings.push(F('R23', 'error',
        `Die beiden Zweige der Verzweigung »${dec ? displayLabel(dec) : decId}« münden an unterschiedlichen Verzweigung-zu-Blöcken – beide Zweige müssen im selben Block zusammengeführt werden.`,
        [Number(decId), ...merges]));
    }
  }

  return { findings, loopBodyNodes };
}

function checkR26LoopCondition(nodesObj, loopBodyNodes) {
  const findings = [];
  for (const node of Object.values(nodesObj)) {
    if (roleOf(node) !== 'loopStart') continue;
    const body = new Set(loopBodyNodes[node.id] || []);
    body.delete(node.id);
    const conditionVars = extractIdentifiers(node.label);
    if (!conditionVars.size) continue;
    const modified = new Set();
    for (const bodyId of body) {
      const bodyNode = nodesObj[bodyId];
      if (bodyNode && roleOf(bodyNode) === 'process') {
        const assignment = splitAssignment(bodyNode.label);
        if (assignment) {
          for (const v of extractIdentifiers(assignment[0])) modified.add(v);
        }
      }
    }
    const overlap = [...conditionVars].some(v => modified.has(v));
    if (!overlap) {
      findings.push(F('R26', 'warning',
        `Die Bedingung der Schleife »${displayLabel(node)}« verwendet nur Variablen, die im Schleifenrumpf nie verändert werden – möglicherweise eine Endlosschleife.`,
        [node.id]));
    }
  }
  return findings;
}

// ---- E. Kantenbeschriftungen ----

function checkR27R28BranchLabels(nodesObj, arrowsObj, outgoing) {
  const findings = [];
  for (const node of Object.values(nodesObj)) {
    if (roleOf(node) !== 'decision') continue;
    const outs = outgoing[node.id] || [];
    if (outs.length !== 2) continue;
    const labelled = outs.map(a => [a, (a.label || '').trim().toLowerCase()]);
    const kinds = labelled.map(([, lbl]) => (YES_WORDS.has(lbl) ? 'yes' : NO_WORDS.has(lbl) ? 'no' : null));
    if (kinds.includes(null)) {
      findings.push(F('R27', 'error', `Beide Pfeile der Verzweigung »${displayLabel(node)}« müssen mit »Ja« bzw. »Nein« beschriftet sein.`, [node.id], labelled.map(([a]) => a.id)));
    } else if (kinds[0] === kinds[1]) {
      findings.push(F('R27', 'error', `Die beiden Pfeile der Verzweigung »${displayLabel(node)}« sind beide mit »${labelled[0][1]}« beschriftet – sie müssen sich unterscheiden (Ja/Nein).`, [node.id], labelled.map(([a]) => a.id)));
    }
  }
  for (const a of Object.values(arrowsObj)) {
    const source = nodesObj[a.sourceId];
    if (source && roleOf(source) === 'decision') continue;
    const label = (a.label || '').trim().toLowerCase();
    if (YES_WORDS.has(label) || NO_WORDS.has(label)) {
      findings.push(F('R28', 'error', `Der Pfeil von »${source ? displayLabel(source) : '?'}« trägt die Beschriftung »${a.label}«, stammt aber nicht von einer Verzweigung.`, source ? [source.id] : [], [a.id]));
    }
  }
  return findings;
}

// ---- F. Blockinhalte und Semantik ----

function checkR29Labels(nodesObj) {
  const findings = [];
  for (const node of Object.values(nodesObj)) {
    const role = roleOf(node);
    if (UNLABELED.has(shapeOf(node))) continue;
    const label = (node.label || '').trim();
    if (!label) {
      findings.push(F('R29', 'error', 'Ein Block ohne Beschriftung wurde gefunden.', [node.id]));
      continue;
    }
    if (role === 'start' && label.toLowerCase() !== 'start') {
      findings.push(F('R29', 'error', 'Der Start-Block muss den Text »Start« tragen.', [node.id]));
    }
    if (role === 'stop' && label.toLowerCase() !== 'stop') {
      findings.push(F('R29', 'error', 'Der Stop-Block muss den Text »Stop« tragen.', [node.id]));
    }
  }
  return findings;
}

function checkR30DecisionContent(nodesObj) {
  const findings = [];
  for (const node of Object.values(nodesObj)) {
    if (roleOf(node) !== 'decision') continue;
    const label = node.label || '';
    const assignment = splitAssignment(label);
    const hasComparison = COMPARISON_OPS.some(op => label.includes(op));
    const hasBoolWord = BOOL_WORDS.some(w => label.toLowerCase().includes(w));
    if (assignment) {
      findings.push(F('R30', 'error', `Die Verzweigung »${label}« enthält eine Zuweisung – eine Verzweigung darf nur eine Ja/Nein-Bedingung enthalten.`, [node.id]));
    } else if (!hasComparison && !hasBoolWord) {
      findings.push(F('R30', 'error', `Die Verzweigung »${label}« enthält keine erkennbare Ja/Nein-Bedingung (z. B. mit ==, <, >, und, oder).`, [node.id]));
    }
  }
  return findings;
}

function checkR31ProcessContent(nodesObj) {
  const findings = [];
  for (const node of Object.values(nodesObj)) {
    if (roleOf(node) !== 'process') continue;
    const label = node.label || '';
    const assignment = splitAssignment(label);
    const hasComparison = COMPARISON_OPS.some(op => label.includes(op));
    if (hasComparison && !assignment) {
      findings.push(F('R31', 'error', `Die Anweisung »${label}« enthält einen Vergleich, aber keine Zuweisung – gehört das nicht in einen Verzweigungsblock?`, [node.id]));
    }
  }
  return findings;
}

function checkR36Subprocess(nodesObj) {
  const findings = [];
  for (const node of Object.values(nodesObj)) {
    if (roleOf(node) !== 'subprocess') continue;
    if (!(node.label || '').trim() || !node.subdiagram) continue;
    let payload;
    try {
      payload = JSON.parse(node.subdiagram);
    } catch (e) {
      findings.push(F('R36', 'error', `Die Funktion »${node.label}« enthält einen beschädigten Unterablaufplan.`, [node.id]));
      continue;
    }
    const subNodes = {};
    for (const item of (payload.nodes || [])) subNodes[item.id] = item;
    const subArrows = {};
    for (const item of (payload.arrows || [])) subArrows[item.id] = item;
    if (Object.values(subNodes).filter(n => roleOf(n) === 'start').length !== 1) {
      findings.push(F('R36', 'error', `Die Funktion »${node.label}« hat keinen eindeutigen Start-Block im Unterablaufplan.`, [node.id]));
    }
    for (const nested of evaluateChart(subNodes, subArrows)) {
      findings.push(F(nested.rule, nested.severity, `In Funktion »${node.label}«: ${nested.message}`, [node.id]));
    }
  }
  return findings;
}

// ---- Zusammenführung ----

function evaluateChart(nodesObj, arrowsObj) {
  const { outgoing, incoming } = buildEdgeMaps(nodesObj, arrowsObj);
  let findings = [];
  findings = findings.concat(checkR01Start(nodesObj));
  findings = findings.concat(checkR02StopExists(nodesObj));
  findings = findings.concat(checkR03MultipleStops(nodesObj));
  findings = findings.concat(checkR04ReachableFromStart(nodesObj, outgoing));
  findings = findings.concat(checkR05ReachStop(nodesObj, incoming));
  findings = findings.concat(checkR06Connected(nodesObj, arrowsObj));
  findings = findings.concat(checkR08DanglingEdges(nodesObj, arrowsObj));
  findings = findings.concat(checkNodeDegrees(nodesObj, incoming, outgoing));
  findings = findings.concat(checkR11SelfLoop(nodesObj, arrowsObj));
  findings = findings.concat(checkR12DuplicateEdges(nodesObj, arrowsObj));
  findings = findings.concat(checkGeometryPorts(nodesObj, arrowsObj));
  findings = findings.concat(checkR19Overlaps(nodesObj));
  findings = findings.concat(checkR18Crossings(nodesObj, arrowsObj));
  findings = findings.concat(checkR25EmptyBodies(nodesObj, outgoing));
  const { findings: nestingFindings, loopBodyNodes } = analyzeControlStructureNesting(nodesObj, outgoing);
  findings = findings.concat(nestingFindings);
  findings = findings.concat(checkR26LoopCondition(nodesObj, loopBodyNodes));
  findings = findings.concat(checkR27R28BranchLabels(nodesObj, arrowsObj, outgoing));
  findings = findings.concat(checkR29Labels(nodesObj));
  findings = findings.concat(checkR30DecisionContent(nodesObj));
  findings = findings.concat(checkR31ProcessContent(nodesObj));
  findings = findings.concat(checkR36Subprocess(nodesObj));
  findings.sort((a, b) => {
    const sa = a.severity === 'error' ? 0 : 1, sb = b.severity === 'error' ? 0 : 1;
    if (sa !== sb) return sa - sb;
    return a.rule.localeCompare(b.rule);
  });
  return findings;
}

function checkDiagram() {
  const findings = evaluateChart(nodes, arrows);

  selNodes = new Set(findings.flatMap(f => f.nodeIds).filter(id => nodes[id]));
  const arrowHit = findings.flatMap(f => f.arrowIds).find(id => arrows[id]);
  selArrow = (arrowHit !== undefined) ? arrowHit : null;
  redraw();

  if (!findings.length) {
    showModal('Plausibilitätsprüfung', 'Keine Probleme gefunden.\nDer Algorithmus scheint plausibel. ✓');
    return;
  }
  const errors = findings.filter(f => f.severity === 'error');
  const warns = findings.filter(f => f.severity === 'warning');
  const fmt = f => `[${f.rule}] ${f.message}`;
  const parts = [];
  if (errors.length) parts.push(`Fehler (${errors.length}):\n` + errors.map(f => '- ' + fmt(f)).join('\n'));
  if (warns.length) parts.push(`Hinweise (${warns.length}):\n` + warns.map(f => '- ' + fmt(f)).join('\n'));
  showModal('Plausibilitätsprüfung', parts.join('\n\n'));
}

// ════════════════════════════════════════════════════════════
// Dateioperationen (alles client-seitig)
// ════════════════════════════════════════════════════════════
function newDiagram() {
  returnToRoot();
  if (!confirmDiscard()) return;
  nodes={}; arrows={}; nextNid=1; nextAid=1;
  curFile=null; selNodes=new Set(); selArrow=null;
  undoStack=[]; redoStack=[];
  ctxStack=[]; ctxTitle='Hauptprogramm';
  updateCtxUI(); redraw();
}

function confirmDiscard() {
  if (!Object.keys(nodes).length && !Object.keys(arrows).length) return true;
  return confirm('Das aktuelle Diagramm wird überschrieben. Fortfahren?');
}

function saveDiagram() {
  returnToRoot();
  const json = JSON.stringify(statePayload(), null, 2);
  downloadBlob(new Blob([json],{type:'application/json'}),
               curFile || 'diagramm.json');
}

function loadDiagram() {
  const inp = document.createElement('input');
  inp.type='file'; inp.accept='.json';
  inp.onchange = e => {
    const f = e.target.files[0]; if(!f) return;
    if(!confirmDiscard()) return;
    const r = new FileReader();
    r.onload = ev => {
      try {
        const p = JSON.parse(ev.target.result);
        returnToRoot();
        nodes={}; arrows={};
        ctxStack=[]; ctxTitle='Hauptprogramm';
        loadPayload(p);
        curFile = f.name;
        selNodes=new Set(); selArrow=null;
        undoStack=[]; redoStack=[];
        updateCtxUI(); redraw();
      } catch(err) { alert('Fehler beim Laden: '+err.message); }
    };
    r.readAsText(f);
  };
  inp.click();
}

// ────── PNG / JPG export (offscreen canvas) ──────────────
function exportPNG() { renderOffscreen(oc => oc.toBlob(b => downloadBlob(b,'diagramm.png'),'image/png')); }
function exportJPG() { renderOffscreen(oc => oc.toBlob(b => downloadBlob(b,'diagramm.jpg'),'image/jpeg',0.95),'image/jpeg'); }

function renderOffscreen(cb) {
  const ns = Object.values(nodes);
  if (!ns.length) { alert('Keine Elemente zum Exportieren.'); return; }
  const pad = 48;
  const minX = Math.min(...ns.map(n=>n.x-n.width/2))  - pad;
  const minY = Math.min(...ns.map(n=>n.y-n.height/2)) - pad;
  const maxX = Math.max(...ns.map(n=>n.x+n.width/2))  + pad;
  const maxY = Math.max(...ns.map(n=>n.y+n.height/2)) + pad;
  const W = maxX-minX, H = maxY-minY;
  const sc = 2;   // 2× für scharfe Ausgabe
  const oc = document.createElement('canvas');
  oc.width = W*sc; oc.height = H*sc;
  const oc2 = oc.getContext('2d');
  oc2.scale(sc, sc);
  oc2.fillStyle = '#ffffff'; oc2.fillRect(0,0,W,H);
  oc2.translate(-minX, -minY);

  // Zeichne mit temporärem ctx-Swap
  const savedCtx = ctx, savedSel = selNodes, savedArrow = selArrow;
  ctx = oc2; selNodes = new Set(); selArrow = null;
  for (const a of Object.values(arrows)) drawArrow(oc2, a, false);
  for (const n of Object.values(nodes))  drawNode(oc2, n);
  ctx = savedCtx; selNodes = savedSel; selArrow = savedArrow;
  cb(oc);
}

// ────── SVG export ──────────────────────────────────────
function exportSVG() {
  const svg = buildSVG(new Set(Object.keys(nodes).map(Number)));
  if (!svg) { alert('Keine Elemente zum Exportieren.'); return; }
  downloadBlob(new Blob([svg],{type:'image/svg+xml'}),'diagramm.svg');
}

function buildSVG(nodeIds) {
  const ns = [...nodeIds].map(id=>nodes[id]).filter(Boolean);
  if (!ns.length) return null;
  const as = Object.values(arrows).filter(a=>nodeIds.has(a.sourceId)&&nodeIds.has(a.targetId));
  let xs = ns.flatMap(n=>[n.x-n.width/2, n.x+n.width/2]);
  let ys = ns.flatMap(n=>[n.y-n.height/2, n.y+n.height/2]);
  const routes = {};
  for (const a of as) {
    routes[a.id] = arrowRoute(a);
    if (routes[a.id]) { xs.push(...routes[a.id].map(p=>p[0])); ys.push(...routes[a.id].map(p=>p[1])); }
  }
  const pad=24, mnx=Math.min(...xs)-pad, mny=Math.min(...ys)-pad;
  const W=Math.max(...xs)-mnx+pad, H=Math.max(...ys)-mny+pad;
  const tx = v=>(v-mnx).toFixed(1), ty = v=>(v-mny).toFixed(1);

  const out = [
    `<svg xmlns="http://www.w3.org/2000/svg" width="${W.toFixed(0)}" height="${H.toFixed(0)}" viewBox="0 0 ${W.toFixed(0)} ${H.toFixed(0)}">`,
    '<defs><marker id="arr" markerWidth="10" markerHeight="8" refX="8" refY="3" orient="auto" markerUnits="strokeWidth">'+
    '<path d="M0,0 L8,3 L0,6 z" fill="#111111"/></marker></defs>',
  ];
  for (const a of as) {
    const r = routes[a.id]; if (!r) continue;
    out.push(`<polyline points="${r.map(([x,y])=>`${tx(x)},${ty(y)}`).join(' ')}" fill="none" stroke="#111111" stroke-width="2" marker-end="url(#arr)"/>`);
    if (a.label) {
      const [mx,my] = labelPos(r);
      out.push(`<text x="${(+tx(mx)+4).toFixed(1)}" y="${(+ty(my)-4).toFixed(1)}" font-family="Helvetica" font-size="12" fill="#111111">${xmlEsc(a.label)}</text>`);
    }
  }
  for (const n of ns) out.push(svgNode(n,tx,ty));
  out.push('</svg>');
  return out.join('\n');
}

function svgNode(n, tx, ty) {
  const [fill,border] = NODE_STYLE[n.templateLabel] || DEFAULT_STYLE;
  const sh = shapeOf(n), {width:w,height:h} = n;
  const x1=+tx(n.x-w/2), y1=+ty(n.y-h/2);
  const cx=+tx(n.x), cy=+ty(n.y);
  const parts = [];
  if (sh==='terminator') {
    parts.push(`<rect x="${x1}" y="${y1}" width="${w}" height="${h}" rx="${h/2}" ry="${h/2}" fill="${fill}" stroke="${border}" stroke-width="2"/>`);
  } else if (sh==='diamond') {
    parts.push(`<polygon points="${tx(n.x)},${ty(n.y-h/2)} ${tx(n.x+w/2)},${ty(n.y)} ${tx(n.x)},${ty(n.y+h/2)} ${tx(n.x-w/2)},${ty(n.y)}" fill="${fill}" stroke="${border}" stroke-width="2"/>`);
  } else if (sh==='connector') {
    parts.push(`<circle cx="${cx}" cy="${cy}" r="${Math.min(w,h)/2}" fill="${CANVAS_BG}" stroke="${border}" stroke-width="2"/>`);
  } else if (sh==='loop_start') {
    const cf=chamfer(w,h);
    parts.push(`<polygon points="${x1+cf},${y1} ${x1+w-cf},${y1} ${x1+w},${y1+cf} ${x1+w},${y1+h} ${x1},${y1+h} ${x1},${y1+cf}" fill="${fill}" stroke="${border}" stroke-width="2"/>`);
  } else if (sh==='loop_end') {
    const cf=chamfer(w,h);
    parts.push(`<polygon points="${x1},${y1} ${x1+w},${y1} ${x1+w},${y1+h-cf} ${x1+w-cf},${y1+h} ${x1+cf},${y1+h} ${x1},${y1+h-cf}" fill="${fill}" stroke="${border}" stroke-width="2"/>`);
  } else if (sh==='subroutine') {
    parts.push(`<rect x="${x1}" y="${y1}" width="${w}" height="${h}" fill="${fill}" stroke="${border}" stroke-width="2"/>`);
    parts.push(`<line x1="${x1+10}" y1="${y1}" x2="${x1+10}" y2="${y1+h}" stroke="${border}" stroke-width="2"/>`);
    parts.push(`<line x1="${x1+w-10}" y1="${y1}" x2="${x1+w-10}" y2="${y1+h}" stroke="${border}" stroke-width="2"/>`);
  } else {
    parts.push(`<rect x="${x1}" y="${y1}" width="${w}" height="${h}" fill="${fill}" stroke="${border}" stroke-width="2"/>`);
  }
  if (!UNLABELED.has(sh) && n.label) {
    const lines  = wrapLines(measureCtx(), n.label, Math.max(20, w-18));
    const startY = cy - (lines.length-1)*LINE_H/2;
    const tspans = lines.map((ln,i) =>
      `<tspan x="${cx}" y="${(startY+i*LINE_H).toFixed(1)}">${xmlEsc(ln)}</tspan>`).join('');
    parts.push(`<text font-family="Helvetica" font-size="12" font-weight="bold" text-anchor="middle" dominant-baseline="central" fill="${TEXT_COLOR}">${tspans}</text>`);
  }
  return parts.join('\n');
}

function xmlEsc(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function downloadBlob(blob, name) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// ════════════════════════════════════════════════════════════
// Pointer-Handler (gemeinsam für Maus und Touch)
// ════════════════════════════════════════════════════════════
function pointerDown(clientX, clientY, shift, btn) {
  const [wx,wy] = worldPt(clientX, clientY);

  if (btn === 2) { rightClick(wx,wy); return; }

  // Knickpunkt des markierten Pfeils verschieben
  const bend = hitBend(wx,wy);
  if (bend !== null) {
    dragState = {type:'bend', arrowId:selArrow, index:bend};
    dragSnap = serialize(); dragMoved = false;
    redraw(); return;
  }

  // Breiten-Anfasser des markierten Blocks ziehen
  const gripId = hitWidthGrip(wx,wy);
  if (gripId !== null) {
    dragState = {type:'width', nodeId:gripId};
    dragSnap = serialize(); dragMoved = false;
    redraw(); return;
  }

  if (shift) {
    const aid = hitArrow(wx,wy);
    if (aid !== null) { insertBend(aid,wx,wy); return; }
  }

  const nid = hitNode(wx,wy);
  if (nid !== null) {
    selArrow = null;
    const n = nodes[nid];
    const prt = hitPort(n,wx,wy);
    if (prt && !shift) {
      selNodes = new Set([nid]);
      connSrc = {nodeId:nid, port:prt};
      tempTarget = ports(n)[prt];
      redraw();
    } else {
      if (shift) { if(selNodes.has(nid)) selNodes.delete(nid); else selNodes.add(nid); }
      else if (!selNodes.has(nid)) selNodes = new Set([nid]);
      if (selNodes.has(nid)) {
        dragState = {type:'node', nodeId:nid, offX:wx-n.x, offY:wy-n.y};
        dragSnap = serialize(); dragMoved = false;
      }
      redraw();
    }
  } else {
    if (!shift) selNodes = new Set();
    const aid = hitArrow(wx,wy);
    connSrc = null;
    // Zweiter Klick auf denselben Pfeil setzt einen Knickpunkt
    if (aid !== null && aid === selArrow) insertBend(aid, wx, wy);
    selArrow = aid;
    if (aid === null)
      dragState = {type:'rubberband', x0:wx, y0:wy, x1:wx, y1:wy};
    redraw();
  }
}

function pointerMove(clientX, clientY) {
  const [wx,wy] = worldPt(clientX, clientY);

  if (dragState) {
    if (dragState.type === 'node') {
      const anch = nodes[dragState.nodeId]; if (!anch) { dragState=null; return; }
      const nx=snap(wx-dragState.offX), ny=snap(wy-dragState.offY);
      const dx=nx-anch.x, dy=ny-anch.y;
      if (dx||dy) {
        dragMoved = true;
        for (const id of selNodes) if(nodes[id]) { nodes[id].x+=dx; nodes[id].y+=dy; }
      }
      redraw();
    } else if (dragState.type === 'bend') {
      const a = arrows[dragState.arrowId];
      const p = a && a.waypoints[dragState.index];
      if (!p) { dragState=null; return; }
      const nx = snap(wx), ny = snap(wy);
      if (nx !== p[0] || ny !== p[1]) { p[0]=nx; p[1]=ny; dragMoved = true; }
      redraw();
    } else if (dragState.type === 'width') {
      const n = nodes[dragState.nodeId];
      if (!n) { dragState=null; return; }
      const nw = Math.max(MIN_NODE_W, snap(2*(wx - n.x - GRIP)));
      if (nw !== n.width) { setNodeWidth(n, nw); dragMoved = true; }
      redraw();
    } else if (dragState.type === 'rubberband') {
      dragState.x1=wx; dragState.y1=wy;
      selNodes = nodesInRect(dragState.x0,dragState.y0,wx,wy);
      redraw();
    }
  }

  if (connSrc) { tempTarget=[wx,wy]; redraw(); }

  if (palDragItem) {
    const r = canvas.getBoundingClientRect();
    if (clientX>=r.left && clientX<=r.right && clientY>=r.top && clientY<=r.bottom)
      palDragPreview = [wx,wy];
    else palDragPreview = null;
    redraw();
  }
}

function pointerUp(clientX, clientY) {
  const [wx,wy] = worldPt(clientX, clientY);

  if (dragState) {
    if (dragState.type === 'rubberband')
      selNodes = nodesInRect(dragState.x0,dragState.y0,dragState.x1,dragState.y1);
    else if ((dragState.type === 'node' || dragState.type === 'bend' ||
              dragState.type === 'width') && dragMoved && dragSnap) {
      undoStack.push(dragSnap); if(undoStack.length>100)undoStack.shift(); redoStack=[];
    }
    dragState=null; dragSnap=null;
  }

  if (connSrc) {
    const {nodeId:srcId, port:srcPort} = connSrc;
    const tgtId = hitNode(wx,wy);
    if (tgtId !== null && tgtId !== srcId) {
      const tgtPort = bestTgtPort(nodes[srcId], nodes[tgtId]);
      pushUndo();
      const created = addArrow(srcId,srcPort,tgtId,tgtPort);
      if (!created) { undoStack.pop(); showModal('Verbindung abgelehnt','Diese Verbindung würde die Flussrichtung verletzen oder einen Zyklus erzeugen.'); }
    }
    connSrc=null; tempTarget=null;
  }

  if (palDragItem) {
    const r = canvas.getBoundingClientRect();
    if (clientX>=r.left && clientX<=r.right && clientY>=r.top && clientY<=r.bottom) {
      pushUndo();
      const [fx,fy] = freeSpot(wx,wy, NODE_W, NODE_H);
      const n = addNode(palDragItem.label,palDragItem.kind,palDragItem.label,fx,fy,palDragItem.rel);
      selNodes = new Set([n.id]);
    }
    palDragItem=null; palDragPreview=null;
  }

  redraw();
}

function dblClick(clientX, clientY) {
  const [wx,wy] = worldPt(clientX,clientY);

  // Doppelklick auf einen Knickpunkt entfernt ihn
  const bend = hitBend(wx,wy);
  if (bend !== null) { removeBend(selArrow, bend); lastBend = null; return; }

  // Der erste Klick eines Doppelklicks auf einen markierten Pfeil hat gerade
  // einen Knickpunkt gesetzt – der war nicht gemeint, also zurücknehmen.
  if (lastBend && Date.now() - lastBend.t < 600 && hitArrow(wx,wy) === lastBend.arrowId) {
    const a = arrows[lastBend.arrowId];
    if (a && a.waypoints[lastBend.index]) { a.waypoints.splice(lastBend.index, 1); undoStack.pop(); }
    lastBend = null;
  }

  const nid = hitNode(wx,wy);
  if (nid !== null) {
    const n = nodes[nid];
    if (n.templateLabel === 'Funktion') { openFunction(n); return; }
    if (UNLABELED.has(shapeOf(n))) return;
    showPrompt('Symbol bearbeiten','Inhalt des Symbols:', n.label, v => {
      if (v !== null) {
        pushUndo();
        const txt = v.replace(/\r\n?/g, '\n').replace(/[ \t]+$/gm, '').trim();
        n.label = txt || n.label;
        fitSize(n); redraw();
      }
    }, true);
    return;
  }
  const aid = hitArrow(wx,wy);
  if (aid !== null) {
    showPrompt('Verbindung beschriften','Beschriftung:',arrows[aid].label||'', v => {
      if (v !== null) { pushUndo(); arrows[aid].label = v.trim(); redraw(); }
    });
  }
}

function rightClick(wx,wy) {
  const bend = hitBend(wx,wy);
  if (bend !== null) { removeBend(selArrow, bend); return; }
  const nid = hitNode(wx,wy);
  if (nid !== null) { pushUndo(); removeNode(nid); selNodes.delete(nid); redraw(); return; }
  const aid = hitArrow(wx,wy);
  if (aid !== null) insertBend(aid,wx,wy);
}

function insertBend(aid,wx,wy) {
  const a = arrows[aid]; if (!a) return;
  const idx = bendInsertIndex(a, wx, wy);
  pushUndo();
  a.waypoints.splice(idx, 0, [snap(wx),snap(wy)]);
  lastBend = {arrowId:aid, index:idx, t:Date.now()};
  selArrow=aid; redraw();
}

/** An welcher Stelle der Knickpunkt-Liste liegt der angeklickte Abschnitt? */
function bendInsertIndex(a, wx, wy) {
  const wps  = a.waypoints || [];
  const route = arrowRoute(a);
  if (!route) return wps.length;
  let best = Infinity, seg = 0;
  for (let i = 0; i < route.length-1; i++) {
    const d = distSeg(wx,wy, route[i][0],route[i][1], route[i+1][0],route[i+1][1]);
    if (d < best) { best = d; seg = i; }
  }
  let idx = 0, ri = 0;
  for (let k = 0; k < wps.length; k++) {
    while (ri < route.length &&
           !(Math.abs(route[ri][0]-wps[k][0]) < 0.5 && Math.abs(route[ri][1]-wps[k][1]) < 0.5)) ri++;
    if (ri > seg) break;
    idx = k+1; ri++;
  }
  return idx;
}

/** Knickpunkt entfernen (Doppelklick oder Rechtsklick auf den Griff). */
function removeBend(aid, index) {
  const a = arrows[aid]; if (!a || !a.waypoints[index]) return;
  pushUndo();
  a.waypoints.splice(index, 1);
  redraw();
}

// ════════════════════════════════════════════════════════════
// Event-Binding
// ════════════════════════════════════════════════════════════
function bindEvents() {
  // ── Maus: Canvas ──────────────────────────────────────────
  canvas.addEventListener('mousedown', e => {
    if (e.button===1) return; // Mittelklick ignorieren
    e.preventDefault();
    pointerDown(e.clientX, e.clientY, e.shiftKey, e.button);
  });
  canvas.addEventListener('mousemove', e => pointerMove(e.clientX, e.clientY));
  canvas.addEventListener('mouseup',   e => pointerUp(e.clientX, e.clientY));
  canvas.addEventListener('dblclick',  e => dblClick(e.clientX, e.clientY));
  canvas.addEventListener('contextmenu', e => { e.preventDefault(); });

  // Mousewheel / Trackpad → Panning
  canvas.addEventListener('wheel', e => {
    e.preventDefault();
    panX = Math.max(0, panX + e.deltaX);
    panY = Math.max(0, panY + e.deltaY);
    redraw();
  }, { passive: false });

  // Globale Maus-Events für Palette-Drag
  document.addEventListener('mousemove', e => { if (palDragItem) pointerMove(e.clientX,e.clientY); });
  document.addEventListener('mouseup',   e => { if (palDragItem) pointerUp(e.clientX,e.clientY); });

  // ── Touch: Canvas ─────────────────────────────────────────
  canvas.addEventListener('touchstart', e => {
    if (e.touches.length === 2) {
      // 2-Finger Pan starten
      const cx = (e.touches[0].clientX + e.touches[1].clientX)/2;
      const cy = (e.touches[0].clientY + e.touches[1].clientY)/2;
      touchPan = {cx, cy, panX, panY};
      dragState=null; connSrc=null; tempTarget=null;
      e.preventDefault(); return;
    }
    const t = e.touches[0];
    const now = Date.now();
    // Doppel-Tap erkennen
    if (now-lastTapT < 320 && Math.hypot(t.clientX-lastTapX, t.clientY-lastTapY) < 25) {
      dblClick(t.clientX, t.clientY);
      lastTapT = 0; e.preventDefault(); return;
    }
    lastTapT=now; lastTapX=t.clientX; lastTapY=t.clientY;
    pointerDown(t.clientX, t.clientY, false, 0);
    e.preventDefault();
  }, { passive:false });

  canvas.addEventListener('touchmove', e => {
    if (e.touches.length === 2 && touchPan) {
      const cx = (e.touches[0].clientX + e.touches[1].clientX)/2;
      const cy = (e.touches[0].clientY + e.touches[1].clientY)/2;
      panX = Math.max(0, touchPan.panX - (cx - touchPan.cx));
      panY = Math.max(0, touchPan.panY - (cy - touchPan.cy));
      redraw(); e.preventDefault(); return;
    }
    if (e.touches.length === 1 && !touchPan) {
      pointerMove(e.touches[0].clientX, e.touches[0].clientY);
      e.preventDefault();
    }
  }, { passive:false });

  canvas.addEventListener('touchend', e => {
    if (touchPan && e.touches.length < 2) { touchPan=null; }
    if (e.touches.length === 0) {
      const t = e.changedTouches[0];
      pointerUp(t.clientX, t.clientY);
    }
    e.preventDefault();
  }, { passive:false });

  // ── Touch: Palette-Drag ───────────────────────────────────
  document.getElementById('palette').addEventListener('touchstart', e => {
    if (e.touches.length !== 1) return;
    const t = e.touches[0];
    const item = palHit(t.clientX, t.clientY);
    if (item) { palDragItem=item; e.preventDefault(); }
  }, { passive:false });

  document.addEventListener('touchmove', e => {
    if (palDragItem) { pointerMove(e.touches[0].clientX, e.touches[0].clientY); e.preventDefault(); }
  }, { passive:false });

  document.addEventListener('touchend', e => {
    if (palDragItem) pointerUp(e.changedTouches[0].clientX, e.changedTouches[0].clientY);
  }, { passive:false });

  // ── Tastatur ──────────────────────────────────────────────
  document.addEventListener('keydown', e => {
    if (e.target.tagName==='INPUT'||e.target.tagName==='TEXTAREA') return;
    const cm = e.ctrlKey||e.metaKey;
    if (cm&&e.key==='z')                        { undo();           e.preventDefault(); }
    if (cm&&(e.key==='y'||(e.shiftKey&&e.key==='z'))) { redo();    e.preventDefault(); }
    if (cm&&e.key==='c')                        { copySelection();  e.preventDefault(); }
    if (cm&&e.key==='v')                        { pasteSelection(); e.preventDefault(); }
    if (cm&&e.key==='a')                        { selectAll();      e.preventDefault(); }
    if (cm&&(e.key==='b'||e.key==='B'))         { e.shiftKey ? resetWidth() : equalizeWidth(); e.preventDefault(); }
    if (e.key==='Delete'||e.key==='Backspace')  { deleteSelected(); e.preventDefault(); }
    if (e.key==='Escape')                       { closeFunction();  e.preventDefault(); }
  });
}

// ════════════════════════════════════════════════════════════
// Palette
// ════════════════════════════════════════════════════════════
function buildPalette() {
  const pal = document.getElementById('palette');
  pal.innerHTML = '';
  for (const item of NODE_TYPES) {
    const card = document.createElement('div');
    card.className = 'palette-card';
    // Mini-Canvas mit der Form
    const sc = document.createElement('canvas');
    sc.width=56; sc.height=40; sc.className='palette-shape';
    drawPalShape(sc.getContext('2d'), item.label);
    const txt = document.createElement('div'); txt.className='palette-text';
    const nm  = document.createElement('div'); nm.className='palette-name';  nm.textContent=item.label;
    const ht  = document.createElement('div'); ht.className='palette-hint';  ht.textContent='ziehen · doppelklick';
    txt.appendChild(nm); txt.appendChild(ht);
    card.appendChild(sc); card.appendChild(txt);
    // Maus-Drag
    card.addEventListener('mousedown', e => { if(e.button===0){ palDragItem=item; e.preventDefault(); } });
    // Doppelklick → mittig einfügen
    card.addEventListener('dblclick', e => {
      e.preventDefault();
      const [cx,cy] = [canvas.clientWidth/2+panX, canvas.clientHeight/2+panY];
      const [fx,fy] = freeSpot(cx,cy,NODE_W,NODE_H);
      pushUndo();
      const n = addNode(item.label,item.kind,item.label,fx,fy,item.rel);
      selNodes=new Set([n.id]); redraw();
    });
    pal.appendChild(card);
  }
}

function drawPalShape(c, label) {
  const [fill,border] = NODE_STYLE[label]||DEFAULT_STYLE;
  const sh=NODE_SHAPE[label]||'rect', cx=28,cy=20,w=46,h=24;
  const x1=cx-w/2, y1=cy-h/2, x2=cx+w/2, y2=cy+h/2;
  c.strokeStyle=border; c.fillStyle=fill; c.lineWidth=2;
  if (sh==='terminator')  { rrPath(c,x1,y1,x2,y2,h/2);   c.fill();c.stroke(); }
  else if(sh==='diamond') {
    c.beginPath(); c.moveTo(cx,y1-4); c.lineTo(x2+2,cy); c.lineTo(cx,y2+4); c.lineTo(x1-2,cy); c.closePath();
    c.fill();c.stroke();
  }
  else if(sh==='connector'){ c.fillStyle=PALETTE_CARD_C; c.strokeStyle='#e5e7eb'; c.beginPath(); c.arc(cx,cy,10,0,Math.PI*2); c.fill();c.stroke(); }
  else if(sh==='loop_start'){ loopStartPath(c,cx,cy,w,h); c.fill();c.stroke(); }
  else if(sh==='loop_end')  { loopEndPath(c,cx,cy,w,h);   c.fill();c.stroke(); }
  else if(sh==='subroutine'){
    c.fillRect(x1,y1,w,h); c.strokeRect(x1,y1,w,h);
    c.beginPath(); c.moveTo(x1+6,y1);c.lineTo(x1+6,y2); c.moveTo(x2-6,y1);c.lineTo(x2-6,y2); c.stroke();
  }
  else { c.fillRect(x1,y1,w,h); c.strokeRect(x1,y1,w,h); }
}

function palHit(clientX, clientY) {
  const cards = document.querySelectorAll('.palette-card');
  for (let i=0; i<cards.length; i++) {
    const r = cards[i].getBoundingClientRect();
    if (clientX>=r.left&&clientX<=r.right&&clientY>=r.top&&clientY<=r.bottom) return NODE_TYPES[i];
  }
  return null;
}

// ════════════════════════════════════════════════════════════
// UI-Hilfsfunktionen
// ════════════════════════════════════════════════════════════
function setStatus(msg) { document.getElementById('status').textContent = msg; }

function updateStatus() {
  const fname = curFile ? curFile.split(/[/\\]/).pop() : 'unbenannt';
  setStatus(`Knoten: ${Object.keys(nodes).length}   Verbindungen: ${Object.keys(arrows).length}   Datei: ${fname}`);
}

// ── Download der Desktop-Version ──────────────────────────────
// Die Dateien liegen auf dem Server unter  web/static/downloads/
// und sind damit unter  /downloads/<dateiname>  erreichbar.
const DOWNLOADS = [
  { os: 'macOS',   file: 'PAP-Editor.dmg',                 hint: 'Apple Silicon & Intel · .dmg' },
  { os: 'Windows', file: 'PAP-Editor-Setup.exe',           hint: 'Installer · .exe' },
  { os: 'Linux',   file: 'PAP-Editor-linux-x86_64.tar.gz', hint: 'entpacken & starten · .tar.gz' },
];

function humanSize(bytes) {
  if (!bytes || isNaN(bytes)) return '';
  const mb = bytes / (1024*1024);
  return mb >= 1 ? `${mb.toFixed(0)} MB` : `${Math.max(1, Math.round(bytes/1024))} KB`;
}

function showDownloads() {
  const list = document.getElementById('download-list');
  list.innerHTML = '';
  for (const item of DOWNLOADS) {
    const url = 'downloads/' + item.file;
    const a = document.createElement('a');
    a.className = 'download-item';
    a.href = url;
    a.setAttribute('download', item.file);
    a.innerHTML = `<span class="download-os"></span><span class="download-meta"></span>`;
    a.querySelector('.download-os').textContent   = item.os;
    a.querySelector('.download-meta').textContent = item.hint;
    list.appendChild(a);

    // Fehlende Pakete ausgrauen, vorhandene mit Dateigröße zeigen
    fetch(url, { method: 'HEAD' }).then(r => {
      if (!r.ok) {
        a.classList.add('missing');
        a.querySelector('.download-meta').textContent = 'noch nicht verfügbar';
        return;
      }
      const size = humanSize(Number(r.headers.get('content-length')));
      if (size) a.querySelector('.download-meta').textContent = `${item.hint} · ${size}`;
    }).catch(() => { /* offline o. ä.: Link einfach anbieten */ });
  }
  document.getElementById('download-modal').style.display = 'flex';
}

function showModal(title, msg) {
  document.getElementById('modal-title').textContent = title;
  document.getElementById('modal-body').textContent  = msg;
  document.getElementById('modal').style.display     = 'flex';
}

let promptCb = null;
let promptEl = null;   // aktives Eingabefeld (ein- oder mehrzeilig)

function showPrompt(title, lbl, def, cb, multiline) {
  document.getElementById('prompt-title').textContent = title;
  document.getElementById('prompt-label').textContent = lbl;
  const inp = document.getElementById('prompt-input');
  const ta  = document.getElementById('prompt-textarea');
  promptEl = multiline ? ta : inp;
  inp.style.display = multiline ? 'none'  : 'block';
  ta.style.display  = multiline ? 'block' : 'none';
  document.getElementById('prompt-hint').style.display = multiline ? 'block' : 'none';
  promptEl.value = def;
  document.getElementById('prompt-modal').style.display = 'flex';
  setTimeout(() => { promptEl.focus(); promptEl.select(); }, 80);
  promptCb = cb;
}

/** Zeilenumbruch an der Cursorposition einfügen (Strg/⌘+Enter). */
function insertNewline(el) {
  const s = el.selectionStart, t = el.selectionEnd;
  el.value = el.value.slice(0, s) + '\n' + el.value.slice(t);
  el.selectionStart = el.selectionEnd = s + 1;
  el.scrollTop = el.scrollHeight;
}

function closePrompt(value) {
  document.getElementById('prompt-modal').style.display = 'none';
  if (promptCb) { const cb = promptCb; promptCb = null; cb(value); }
}

function toggleSidebar() {
  const sb = document.getElementById('sidebar');
  sb.classList.toggle('open');
  closeMenu();
}

function toggleMenu() {
  document.getElementById('menubar').classList.toggle('open');
  document.getElementById('sidebar').classList.remove('open');
}

function closeMenu() {
  document.getElementById('menubar').classList.remove('open');
}

function updateDeleteButton() {
  const btn = document.getElementById('btn-delete');
  btn.disabled = !selNodes.size && selArrow === null;
}

// ════════════════════════════════════════════════════════════
// Init
// ════════════════════════════════════════════════════════════
function init() {
  setupCanvas();
  buildPalette();
  bindEvents();
  createStartScene();
  updateCtxUI();

  // Toolbar
  document.getElementById('btn-check').addEventListener('click', checkDiagram);
  document.getElementById('btn-width').addEventListener('click', equalizeWidth);
  document.getElementById('btn-new')  .addEventListener('click', newDiagram);
  document.getElementById('btn-load') .addEventListener('click', loadDiagram);
  document.getElementById('btn-save') .addEventListener('click', saveDiagram);
  document.getElementById('btn-png')  .addEventListener('click', exportPNG);
  document.getElementById('btn-jpg')  .addEventListener('click', exportJPG);
  document.getElementById('btn-svg')  .addEventListener('click', exportSVG);
  document.getElementById('btn-desktop').addEventListener('click', showDownloads);
  document.getElementById('back-btn') .addEventListener('click', closeFunction);
  document.getElementById('sidebar-toggle').addEventListener('click', toggleSidebar);
  document.getElementById('menu-toggle').addEventListener('click', toggleMenu);
  document.getElementById('menu-overlay').addEventListener('click', closeMenu);
  document.getElementById('menubar').addEventListener('click', e => {
    if (e.target.closest('button')) closeMenu();
  });
  document.getElementById('btn-delete').addEventListener('click', deleteSelected);
  updateDeleteButton();

  document.getElementById('toggle-grid').addEventListener('change', e => {
    showGrid = e.target.checked; redraw();
  });
  document.getElementById('grid-size').addEventListener('change', e => {
    const v = parseInt(e.target.value);
    if (v>=10&&v<=200) { gridSize=v; redraw(); }
  });

  // Modals
  document.getElementById('modal-close').addEventListener('click', () => {
    document.getElementById('modal').style.display='none';
  });
  document.getElementById('modal').addEventListener('click', e => {
    if (e.target===document.getElementById('modal')) document.getElementById('modal').style.display='none';
  });

  const dlModal = document.getElementById('download-modal');
  document.getElementById('download-close').addEventListener('click', () => { dlModal.style.display='none'; });
  dlModal.addEventListener('click', e => { if (e.target===dlModal) dlModal.style.display='none'; });

  document.getElementById('prompt-ok').addEventListener('click', () => {
    closePrompt(promptEl ? promptEl.value : '');
  });
  document.getElementById('prompt-cancel').addEventListener('click', () => closePrompt(null));
  document.getElementById('prompt-modal').addEventListener('click', e => {
    if (e.target===document.getElementById('prompt-modal')) closePrompt(null);
  });
  document.getElementById('prompt-input').addEventListener('keydown', e => {
    if (e.key==='Enter')  { e.preventDefault(); closePrompt(promptEl.value); }
    if (e.key==='Escape') { e.preventDefault(); closePrompt(null); }
  });
  // Mehrzeilig: Strg/⌘+Enter bzw. Shift+Enter erzeugt einen Zeilenumbruch,
  // Enter allein schließt den Dialog.
  document.getElementById('prompt-textarea').addEventListener('keydown', e => {
    if (e.key==='Escape') { e.preventDefault(); closePrompt(null); return; }
    if (e.key!=='Enter') return;
    if (e.shiftKey) return;                 // Shift+Enter: Standardverhalten (Umbruch)
    e.preventDefault();
    if (e.ctrlKey || e.metaKey) { insertNewline(e.target); return; }
    closePrompt(promptEl.value);
  });

  // Sidebar overlay (iPad: Klick außerhalb schließt Sidebar)
  const ov = document.createElement('div');
  ov.id='sidebar-overlay';
  document.getElementById('app').appendChild(ov);
  ov.addEventListener('click', () => document.getElementById('sidebar').classList.remove('open'));

  redraw();
}

window.addEventListener('DOMContentLoaded', init);
