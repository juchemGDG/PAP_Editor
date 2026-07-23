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
  'Funktion':       ['#e60132af', NODE_BORDER],
  'Anweisung':      ['#e60132af', NODE_BORDER],
  'Entscheidung':   ['#00b43f9e', NODE_BORDER],
  'Verzweigung zu': ['#ffffff', NODE_BORDER],
  'Schleife':       ['#ffb700b4', NODE_BORDER],
  'Schleife zu':    ['#ffb700b4', NODE_BORDER],
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
  return orthoPts(ports(s)[a.sourcePort], a.sourcePort,
                  a.waypoints || [], ports(t)[a.targetPort], a.targetPort);
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
    c.font = 'bold 11px Helvetica,Arial,sans-serif';
    c.textAlign = 'center'; c.textBaseline = 'middle';
    wrapText(c, n.label, x, y, w-18);
  }

  drawPorts(c, n);
}

function wrapText(c, text, cx, cy, maxW) {
  const words = text.split(' ');
  const lines = [];
  let cur = '';
  for (const w of words) {
    const test = cur ? cur+' '+w : w;
    if (c.measureText(test).width <= maxW || !cur) { cur = test; }
    else { lines.push(cur); cur = w; }
  }
  if (cur) lines.push(cur);
  const LH = 14;
  const startY = cy - (lines.length * LH)/2 + LH/2;
  for (let i = 0; i < lines.length; i++) c.fillText(lines[i], cx, startY + i*LH);
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
  const route = orthoPts(start, connSrc.port, [], tempTarget, 'top');
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

function fitSize(n) {
  const sh = shapeOf(n);
  if (sh === 'connector')    { n.width = n.height = 26; return; }
  if (UNLABELED.has(sh))     return;
  const tw = n.label.length * 8 + 24;
  if (sh === 'diamond') { n.width = Math.max(n.width, snap(tw*1.7)); n.height = Math.max(n.height, 88); }
  else                  { n.width = Math.max(n.width, snap(tw)); }
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
  if (t.y <= s.y - 20) return null;
  if (srcPort === 'top' || tgtPort === 'bottom') return null;
  if (hasPath(tgtId, srcId)) return null;
  if (srcPort === 'bottom' && tgtPort === 'top' && t.y < s.y) return null;
  const a = { id: nextAid++, sourceId: srcId, sourcePort: srcPort,
              targetId: tgtId, targetPort: tgtPort, waypoints: [], label: '' };
  arrows[a.id] = a; return a;
}

function bestTgtPort(srcPort, src, tgt) {
  const sh = shapeOf(tgt);
  if (sh !== 'diamond' && sh !== 'connector') return tgt.y >= src.y ? 'top' : 'bottom';
  if (src.x - tgt.x > tgt.width/2 + 4) return 'right';
  return tgt.y >= src.y ? 'top' : 'bottom';
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
  for (const item of (p.nodes || [])) { const n = {...item}; nodes[n.id] = n; }
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
// Diagramm-Validierung
// ════════════════════════════════════════════════════════════
function checkDiagram() {
  const issues = [];
  const starts = Object.values(nodes).filter(n => n.templateLabel === 'Start');
  const stops  = Object.values(nodes).filter(n => n.templateLabel === 'Stop');
  if (starts.length !== 1) issues.push(`Es muss genau einen Start-Block geben (gefunden: ${starts.length}).`);
  if (!stops.length)       issues.push('Es muss mindestens einen Stop-Block geben.');

  const out = {}, inc = {};
  for (const a of Object.values(arrows)) {
    (out[a.sourceId] = out[a.sourceId]||[]).push(a);
    (inc[a.targetId] = inc[a.targetId]||[]).push(a);
  }
  for (const n of Object.values(nodes)) {
    const o = (out[n.id]||[]).length, i = (inc[n.id]||[]).length;
    if (n.templateLabel === 'Start') {
      if (o===0) issues.push(`Start '${n.label}' hat keine ausgehende Verbindung.`);
      if (i> 0) issues.push(`Start '${n.label}' darf keine eingehende Verbindung haben.`);
    } else if (n.templateLabel === 'Stop') {
      if (i===0) issues.push(`Stop '${n.label}' hat keine eingehende Verbindung.`);
      if (o> 0) issues.push(`Stop '${n.label}' darf keine ausgehende Verbindung haben.`);
    } else if (n.templateLabel === 'Entscheidung') {
      if (o < 2) issues.push(`Verzweigung '${n.label}' benötigt mindestens zwei Ausgänge (gefunden: ${o}).`);
      if (i===0) issues.push(`Verzweigung '${n.label}' hat keine eingehende Verbindung.`);
    } else {
      if (i===0) issues.push(`Block '${n.label}' ist nicht erreichbar.`);
      if (o===0) issues.push(`Block '${n.label}' hat keinen Ausgang.`);
    }
  }
  if (starts.length) {
    const reach = new Set(), stk = [starts[0].id];
    while(stk.length){ const c=stk.pop(); if(reach.has(c))continue; reach.add(c); for(const a of(out[c]||[]))stk.push(a.targetId); }
    for (const n of Object.values(nodes))
      if (!reach.has(n.id)) issues.push(`Block '${n.label}' vom Start nicht erreichbar.`);
  }
  showModal('Plausibilitätsprüfung',
    issues.length ? 'Gefundene Probleme:\n\n' + issues.map(i=>'• '+i).join('\n')
                  : 'Keine Probleme gefunden.\nDer Algorithmus scheint plausibel. ✓');
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
  if (!UNLABELED.has(sh) && n.label)
    parts.push(`<text x="${cx}" y="${cy}" font-family="Helvetica" font-size="12" font-weight="bold" text-anchor="middle" dominant-baseline="central" fill="${TEXT_COLOR}">${xmlEsc(n.label)}</text>`);
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
    selArrow = hitArrow(wx,wy);
    connSrc = null;
    if (selArrow === null)
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
    else if (dragState.type === 'node' && dragMoved && dragSnap) {
      undoStack.push(dragSnap); if(undoStack.length>100)undoStack.shift(); redoStack=[];
    }
    dragState=null; dragSnap=null;
  }

  if (connSrc) {
    const {nodeId:srcId, port:srcPort} = connSrc;
    const tgtId = hitNode(wx,wy);
    if (tgtId !== null && tgtId !== srcId) {
      const tgtPort = bestTgtPort(srcPort, nodes[srcId], nodes[tgtId]);
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
  const nid = hitNode(wx,wy);
  if (nid !== null) {
    const n = nodes[nid];
    if (n.templateLabel === 'Funktion') { openFunction(n); return; }
    if (UNLABELED.has(shapeOf(n))) return;
    showPrompt('Symbol bearbeiten','Inhalt des Symbols:', n.label, v => {
      if (v !== null) { pushUndo(); n.label = v.trim() || n.label; fitSize(n); redraw(); }
    });
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
  const nid = hitNode(wx,wy);
  if (nid !== null) { pushUndo(); removeNode(nid); selNodes.delete(nid); redraw(); return; }
  const aid = hitArrow(wx,wy);
  if (aid !== null) insertBend(aid,wx,wy);
}

function insertBend(aid,wx,wy) {
  const a = arrows[aid]; if (!a) return;
  pushUndo(); a.waypoints.push([snap(wx),snap(wy)]);
  selArrow=aid; redraw();
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

function showModal(title, msg) {
  document.getElementById('modal-title').textContent = title;
  document.getElementById('modal-body').textContent  = msg;
  document.getElementById('modal').style.display     = 'flex';
}

let promptCb = null;
function showPrompt(title, lbl, def, cb) {
  document.getElementById('prompt-title').textContent = title;
  document.getElementById('prompt-label').textContent = lbl;
  const inp = document.getElementById('prompt-input');
  inp.value = def;
  document.getElementById('prompt-modal').style.display = 'flex';
  setTimeout(() => { inp.focus(); inp.select(); }, 80);
  promptCb = cb;
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
  document.getElementById('btn-new')  .addEventListener('click', newDiagram);
  document.getElementById('btn-load') .addEventListener('click', loadDiagram);
  document.getElementById('btn-save') .addEventListener('click', saveDiagram);
  document.getElementById('btn-png')  .addEventListener('click', exportPNG);
  document.getElementById('btn-jpg')  .addEventListener('click', exportJPG);
  document.getElementById('btn-svg')  .addEventListener('click', exportSVG);
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

  document.getElementById('prompt-ok').addEventListener('click', () => {
    document.getElementById('prompt-modal').style.display='none';
    if (promptCb) { const v=document.getElementById('prompt-input').value; promptCb(v); promptCb=null; }
  });
  document.getElementById('prompt-cancel').addEventListener('click', () => {
    document.getElementById('prompt-modal').style.display='none';
    if (promptCb) { promptCb(null); promptCb=null; }
  });
  document.getElementById('prompt-modal').addEventListener('click', e => {
    if (e.target===document.getElementById('prompt-modal')) {
      document.getElementById('prompt-modal').style.display='none';
      if (promptCb) { promptCb(null); promptCb=null; }
    }
  });
  document.getElementById('prompt-input').addEventListener('keydown', e => {
    if (e.key==='Enter') document.getElementById('prompt-ok').click();
    if (e.key==='Escape') document.getElementById('prompt-cancel').click();
  });

  // Sidebar overlay (iPad: Klick außerhalb schließt Sidebar)
  const ov = document.createElement('div');
  ov.id='sidebar-overlay';
  document.getElementById('app').appendChild(ov);
  ov.addEventListener('click', () => document.getElementById('sidebar').classList.remove('open'));

  redraw();
}

window.addEventListener('DOMContentLoaded', init);
