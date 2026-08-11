"""Render a recording into one self-contained HTML replay page that
reproduces the herdr client screen: sidebar (spaces + agents with live
status dots), tab bar, box-drawing pane borders, panes at their recorded
character-cell rects — in an asciinema-style player window.

Chrome geometry and palette were extracted from a real herdr 0.8 TUI
capture (Catppuccin Mocha)."""

import json
import os

TEMPLATE = r"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
  :root {
    --crust: #11111b; --mantle: #181825; --base: #1e1e2e;
    --surface: #313244; --overlay: #6c7086; --subtext: #a6adc8;
    --text: #cdd6f4; --blue: #89b4fa;
    --st-working: #f9e2af; --st-blocked: #f38ba8; --st-done: #a6e3a1;
    --st-idle: #94b9a8; --st-unknown: #6c7086;
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--crust); color: var(--text);
         font: 13px/1.5 -apple-system, "Segoe UI", sans-serif;
         display: flex; flex-direction: column; align-items: center;
         padding: 28px 16px 40px; }
  #titlebar { color: var(--overlay); font-size: 12px; margin-bottom: 10px; }
  #player { position: relative; background: var(--mantle);
            border: 1px solid #26263a; border-radius: 8px;
            box-shadow: 0 16px 48px rgba(0,0,0,.5); overflow: hidden;
            max-width: 100%; }
  #term { position: relative;
          font-family: "SF Mono", Menlo, Consolas, monospace; }
  #term pre { margin: 0; position: absolute; font: inherit;
              line-height: inherit; white-space: pre; color: var(--text); }
  /* big center play button, asciinema-style */
  #bigplay { position: absolute; inset: 0; display: flex; align-items: center;
             justify-content: center; cursor: pointer; background: rgba(17,17,27,.35); }
  #bigplay div { width: 74px; height: 74px; border-radius: 50%;
                 background: rgba(30,30,46,.9); border: 2px solid var(--blue);
                 display: flex; align-items: center; justify-content: center; }
  #bigplay svg { margin-left: 6px; }
  #bigplay.hidden { display: none; }
  /* control bar */
  #bar { display: flex; align-items: center; gap: 10px;
         background: var(--mantle); border-top: 1px solid #26263a;
         padding: 7px 12px; font-size: 12px; }
  #bar button { background: none; border: 0; color: var(--text);
                cursor: pointer; padding: 2px; display: flex; }
  #progress { flex: 1; height: 5px; border-radius: 3px; background: var(--surface);
              cursor: pointer; position: relative; }
  #progress .fill { position: absolute; left: 0; top: 0; bottom: 0;
                    background: var(--blue); border-radius: 3px; }
  #clock { font-family: "SF Mono", Menlo, monospace; color: var(--subtext);
           font-size: 11px; }
  #speed { background: var(--base); color: var(--subtext); border: 0;
           border-radius: 4px; padding: 2px 4px; font-size: 11px; }
  /* lifecycle timeline */
  #timeline { margin-top: 16px; background: var(--mantle);
              border: 1px solid #26263a; border-radius: 8px;
              padding: 10px 14px; }
  #timeline h2 { margin: 0 0 8px; font-size: 11px; font-weight: 600;
                 color: var(--overlay); text-transform: uppercase;
                 letter-spacing: .06em; }
  .tl-row { display: flex; align-items: center; gap: 10px; margin: 4px 0; }
  .tl-label { width: 140px; flex: none; font-size: 11px; color: var(--overlay);
              white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
              text-align: right; font-family: "SF Mono", Menlo, monospace; }
  .tl-track { position: relative; flex: 1; height: 12px; border-radius: 3px;
              background: var(--crust); overflow: hidden; cursor: pointer; }
  .tl-seg { position: absolute; top: 0; bottom: 0; }
  #tl-body { position: relative; }
  #cursorline { position: absolute; top: -2px; bottom: -2px; width: 1.5px;
                background: var(--text); opacity: .9; pointer-events: none; }
  #legend { display: flex; gap: 12px; margin-top: 8px; margin-left: 150px;
            font-size: 10px; color: var(--overlay); }
  #legend span::before { content: ""; display: inline-block; width: 8px;
            height: 8px; border-radius: 50%; margin-right: 4px; }
  #legend .working::before { background: var(--st-working); }
  #legend .blocked::before { background: var(--st-blocked); }
  #legend .done::before { background: var(--st-done); }
  #legend .idle::before { background: var(--st-idle); }
  #legend .unknown::before { background: var(--st-unknown); }
</style>
</head>
<body>
<div id="titlebar">__TITLE__ · herdr __HVER__ · recorded with herdrnema</div>
<div id="player">
  <div id="term"></div>
  <div id="bigplay"><div>
    <svg width="26" height="30" viewBox="0 0 26 30"><path d="M0 0 L26 15 L0 30 Z" fill="#cdd6f4"/></svg>
  </div></div>
  <div id="bar">
    <button id="playbtn" title="play/pause">
      <svg id="ic-play" width="12" height="14" viewBox="0 0 12 14"><path d="M0 0 L12 7 L0 14 Z" fill="#cdd6f4"/></svg>
      <svg id="ic-pause" width="12" height="14" viewBox="0 0 12 14" style="display:none"><rect width="4" height="14" fill="#cdd6f4"/><rect x="8" width="4" height="14" fill="#cdd6f4"/></svg>
    </button>
    <span id="clock">00:00 / 00:00</span>
    <div id="progress"><div class="fill" style="width:0%"></div></div>
    <select id="speed">
      <option value="1">1×</option><option value="2" selected>2×</option>
      <option value="4">4×</option><option value="8">8×</option>
    </select>
  </div>
</div>
<div id="timeline">
  <h2>Agent timeline</h2>
  <div id="tl-body"><div id="cursorline" style="left:150px"></div></div>
  <div id="legend">
    <span class="working">working</span><span class="blocked">blocked</span>
    <span class="done">done</span><span class="idle">idle</span>
    <span class="unknown">unknown</span>
  </div>
</div>
<script id="hnema-data" type="application/json">__DATA__</script>
<script>
const DATA = JSON.parse(document.getElementById('hnema-data').textContent);
const S = DATA.session, CASTS = DATA.casts;
const DUR = S.duration;
const C = {
  crust:'#11111b', mantle:'#181825', base:'#1e1e2e', surface:'#313244',
  overlay:'#6c7086', subtext:'#a6adc8', text:'#cdd6f4', blue:'#89b4fa',
  working:'#f9e2af', blocked:'#f38ba8', done:'#a6e3a1',
  idle:'#94b9a8', unknown:'#6c7086'
};
const stColor = s => C[s] || C.unknown;

/* ---------- pick the tab to render (first workspace's tab with panes) --- */
const tabPanes = {};
for (const [pid, p] of Object.entries(S.panes))
  (tabPanes[p.tab_id] = tabPanes[p.tab_id] || []).push(pid);
const tabIds = Object.keys(tabPanes).sort(
  (a,b) => tabPanes[b].length - tabPanes[a].length);
const TAB = tabIds[0];
const PIDS = tabPanes[TAB];
const layout = S.layouts[TAB] || {area:{x:26,y:1,width:160,height:46},
                                  panes:[], focused_pane_id:null};
const area = layout.area;
const SIDEBAR = Math.min(25, Math.max(16, area.x - 1));
const COLS = SIDEBAR + 1 + area.width;
const ROWS = 1 + area.height + 1;
const rectOf = pid => {
  for (const lp of (layout.panes||[])) if (lp.pane_id === pid) return lp.rect;
  return area;
};
const BORDERS = PIDS.length > 1;

/* ---------- minimal ANSI(SGR) -> spans ---------- */
const ESC = /\x1b\[([0-9;]*)([A-Za-z])/g;
const BASE16 = ['#45475a','#f38ba8','#a6e3a1','#f9e2af','#89b4fa','#f5c2e7',
  '#94e2d5','#bac2de','#585b70','#f38ba8','#a6e3a1','#f9e2af','#89b4fa',
  '#f5c2e7','#94e2d5','#a6adc8'];
function xterm256(n){
  n = +n;
  if (n < 16) return BASE16[n];
  if (n < 232) { n -= 16;
    const c = [0,95,135,175,215,255];
    return `rgb(${c[(n/36)|0]},${c[((n/6)|0)%6]},${c[n%6]})`; }
  const v = 8 + (n-232)*10; return `rgb(${v},${v},${v})`;
}
function esc(s){ return s.replace(/&/g,'&amp;').replace(/</g,'&lt;'); }
function renderAnsi(text){
  let st = {b:0,i:0,u:0,rev:0,fg:null,bg:null};
  let out = '', open = false;
  const flushOpen = () => {
    if (open) out += '</span>';
    let css = '';
    if (st.b) css += 'font-weight:700;';
    if (st.i) css += 'font-style:italic;';
    if (st.u) css += 'text-decoration:underline;';
    let fg = st.fg, bg = st.bg;
    if (st.rev) { fg = st.bg || C.base; bg = st.fg || C.text; }
    if (fg) css += 'color:'+fg+';';
    if (bg) css += 'background:'+bg+';';
    out += '<span style="'+css+'">'; open = true;
  };
  flushOpen();
  let last = 0; ESC.lastIndex = 0;
  for (let m; (m = ESC.exec(text)); ) {
    out += esc(text.slice(last, m.index)); last = ESC.lastIndex;
    if (m[2] !== 'm') continue;
    const ps = (m[1]||'0').split(';').map(x => x===''?0:+x);
    for (let i = 0; i < ps.length; i++) {
      const p = ps[i];
      if (p === 0) st = {b:0,i:0,u:0,rev:0,fg:null,bg:null};
      else if (p === 1) st.b = 1; else if (p === 3) st.i = 1;
      else if (p === 4) st.u = 1; else if (p === 7) st.rev = 1;
      else if (p === 22) st.b = 0; else if (p === 23) st.i = 0;
      else if (p === 24) st.u = 0; else if (p === 27) st.rev = 0;
      else if (p >= 30 && p <= 37) st.fg = BASE16[p-30];
      else if (p >= 90 && p <= 97) st.fg = BASE16[p-90+8];
      else if (p === 39) st.fg = null;
      else if (p >= 40 && p <= 47) st.bg = BASE16[p-40];
      else if (p >= 100 && p <= 107) st.bg = BASE16[p-100+8];
      else if (p === 49) st.bg = null;
      else if (p === 38 || p === 48) {
        const isFg = p === 38;
        if (ps[i+1] === 5) { const c = xterm256(ps[i+2]); isFg?st.fg=c:st.bg=c; i += 2; }
        else if (ps[i+1] === 2) { const c = `rgb(${ps[i+2]},${ps[i+3]},${ps[i+4]})`;
          isFg?st.fg=c:st.bg=c; i += 4; }
      }
    }
    flushOpen();
  }
  out += esc(text.slice(last));
  if (open) out += '</span>';
  return out;
}
function frameLines(data, maxCols, maxRows){
  let t = data.replace(/^\x1b\[H/,'').replace(/\x1b\[0m\x1b\[J$/,'');
  return t.split('\r\n').slice(0, maxRows).map(renderAnsi);
}

/* ---------- lifecycle ---------- */
const segs = {};
for (const pid of Object.keys(S.panes)) segs[pid] = [];
for (const ev of S.events) {
  if (ev.type === 'pane_started')
    segs[ev.pane_id].push({t: ev.t, s: ev.agent_status || 'unknown'});
  else if (ev.type === 'agent_status')
    segs[ev.pane_id].push({t: ev.t, s: ev.agent_status});
  else if (ev.type === 'pane_closed')
    segs[ev.pane_id].push({t: ev.t, s: 'closed'});
}
function statusAt(pid, t){
  let s = 'unknown';
  for (const seg of segs[pid]) { if (seg.t <= t) s = seg.s; else break; }
  return s;
}
function wsStatusAt(ws, t){
  const order = ['blocked','working','done','idle'];
  let best = 'unknown';
  for (const [pid, p] of Object.entries(S.panes)) {
    if (p.workspace_id !== ws || !p.agent) continue;
    const s = statusAt(pid, t);
    if (s === 'closed') continue;
    if (best === 'unknown' || order.indexOf(s) < order.indexOf(best) &&
        order.indexOf(s) !== -1) best = s;
  }
  return best;
}

/* ---------- build the herdr screen (character grid) ---------- */
const term = document.getElementById('term');
function addPre(top, left, html, color){
  const el = document.createElement('pre');
  el.style.top = 'calc(' + top + ' * var(--lh))';
  el.style.left = 'calc(' + left + ' * var(--cw))';
  if (color) el.style.color = color;
  el.innerHTML = html;
  term.appendChild(el);
  return el;
}
/* sidebar chrome (static text; dots injected as spans updated live) */
const wsList = S.workspaces.length ? S.workspaces
  : [{workspace_id:'w?', label:'~', focused:true}];
const dotEls = [];   // {el, kind:'ws'|'pane', id}
{
  addPre(0, 1, '<b style="color:'+C.overlay+'">spaces</b>');
  let r = 2;
  for (const ws of wsList) {
    const el = addPre(r, 1,
      '<span class="dot">●</span> <b style="color:'+C.text+'">' +
      esc(ws.label || ws.workspace_id) + '</b>');
    el.style.background = C.base;
    el.style.paddingRight = '1ch';
    dotEls.push({el: el.querySelector('.dot'), kind: 'ws', id: ws.workspace_id});
    r += 1;
  }
  const half = Math.floor(ROWS/2);
  addPre(half - 1, 1, '<span style="color:'+C.overlay+'">new</span>');
  addPre(half - 1, SIDEBAR - 5, '<span style="color:'+C.overlay+'">menu</span>');
  addPre(half, 0, '<span style="color:'+C.surface+'">' +
    '─'.repeat(SIDEBAR) + '</span>');
  addPre(half + 1, 1, '<b style="color:'+C.overlay+'">agents</b>');
  addPre(half + 1, SIDEBAR - 8, '<span style="color:'+C.overlay+'">grouped</span>');
  r = half + 3;
  for (const ws of wsList) {
    const agents = Object.entries(S.panes)
      .filter(([pid,p]) => p.workspace_id === ws.workspace_id && p.agent);
    if (!agents.length) continue;
    const el = addPre(r, 1, '<span class="dot">●</span> <b style="color:' +
      C.subtext + '">' + esc(ws.label || ws.workspace_id) + '</b>');
    dotEls.push({el: el.querySelector('.dot'), kind: 'ws', id: ws.workspace_id});
    r += 1;
    for (const [pid, p] of agents) {
      const ael = addPre(r, 3, '<span class="dot">●</span> <span style="color:' +
        C.overlay + '">' + esc(p.agent) + '</span>');
      dotEls.push({el: ael.querySelector('.dot'), kind: 'pane', id: pid});
      r += 1;
    }
  }
  addPre(ROWS - 1, SIDEBAR - 1, '<span style="color:'+C.overlay+'">«</span>');
  /* sidebar separator column */
  addPre(0, SIDEBAR, '<span style="color:'+C.base+'">' +
    Array(ROWS).fill('│').join('\n') + '</span>');
}
/* tab bar */
{
  let col = SIDEBAR + 1, n = 1;
  for (const tid of Object.keys(tabPanes).sort()) {
    const active = tid === TAB;
    const label = ' ' + n + ' ';
    const el = addPre(0, col, esc(label));
    el.style.background = active ? C.blue : 'transparent';
    el.style.color = active ? C.mantle : C.overlay;
    col += label.length + 1; n += 1;
  }
  const plus = addPre(0, col + 1, ' + ');
  plus.style.background = C.mantle; plus.style.color = '#7f849c';
}
/* pane borders + content layers */
const paneEls = {}, paneFrames = {}, paneIdx = {};
for (const pid of PIDS) {
  paneFrames[pid] = CASTS[pid].filter(e => e[1] === 'o');
  paneIdx[pid] = -1;
  const r = rectOf(pid);
  const top = r.y - area.y + 1, left = SIDEBAR + 1 + (r.x - area.x);
  /* Like the real herdr client: the border box sits on the rect's outer
     ring and the pane's terminal grid renders inside it, clipped. (The grid
     can be larger than the view — herdr doesn't shrink it on splits.) */
  const w = r.width, h = r.height;
  const inset = BORDERS ? 1 : 0;
  if (BORDERS) {
    const bc = layout.focused_pane_id === pid ? C.blue : C.overlay;
    const box = ['┌' + '─'.repeat(w-2) + '┐']
      .concat(Array(h-2).fill('│' + ' '.repeat(w-2) + '│'))
      .concat(['└' + '─'.repeat(w-2) + '┘']);
    addPre(top, left, '<span style="color:'+bc+'">' + box.join('\n') + '</span>');
  }
  paneEls[pid] = addPre(top + inset, left + inset, '');
  const el = paneEls[pid];
  el.dataset.cols = w - 2*inset; el.dataset.rows = h - 2*inset;
  el.style.width = 'calc(' + el.dataset.cols + ' * var(--cw))';
  el.style.height = 'calc(' + el.dataset.rows + ' * var(--lh))';
  el.style.overflow = 'hidden';
}
/* font sizing: fit COLS to container width */
function fit(){
  const avail = Math.min(document.body.clientWidth - 34, 1680);
  let fs = Math.min(16, avail / (COLS * 0.602));
  term.style.setProperty('font-size', fs + 'px');
  const probe = document.createElement('pre');
  probe.textContent = 'X'.repeat(100);
  probe.style.position = 'absolute'; probe.style.visibility = 'hidden';
  term.appendChild(probe);
  const cw = probe.getBoundingClientRect().width / 100;
  term.removeChild(probe);
  const lh = fs * 1.25;
  term.style.setProperty('--cw', cw + 'px');
  term.style.setProperty('--lh', lh + 'px');
  term.style.lineHeight = lh + 'px';
  term.style.width = (cw * COLS) + 'px';
  term.style.height = (lh * ROWS) + 'px';
}
fit();
addEventListener('resize', fit);

/* ---------- timeline ---------- */
const tlBody = document.getElementById('tl-body');
const cursor = document.getElementById('cursorline');
for (const pid of Object.keys(S.panes).sort()) {
  const p = S.panes[pid];
  const row = document.createElement('div');
  row.className = 'tl-row';
  const label = document.createElement('div');
  label.className = 'tl-label';
  label.textContent = pid + (p.agent ? ' · ' + p.agent : '');
  const track = document.createElement('div');
  track.className = 'tl-track';
  const list = segs[pid];
  for (let i = 0; i < list.length; i++) {
    const from = list[i].t, to = (i+1 < list.length) ? list[i+1].t : DUR;
    if (list[i].s === 'closed') break;
    const d = document.createElement('div');
    d.className = 'tl-seg';
    d.style.left = (from / DUR * 100) + '%';
    d.style.width = ((to - from) / DUR * 100) + '%';
    d.style.background = stColor(list[i].s);
    d.title = pid + ': ' + list[i].s + ' @ ' + from.toFixed(1) + 's';
    track.appendChild(d);
  }
  track.addEventListener('click', e => {
    const r = track.getBoundingClientRect();
    seek((e.clientX - r.left) / r.width * DUR);
  });
  row.appendChild(label); row.appendChild(track);
  tlBody.appendChild(row);
}
function sizeTimeline(){
  const player = document.getElementById('player');
  document.getElementById('timeline').style.width =
    player.getBoundingClientRect().width + 'px';
}
sizeTimeline(); addEventListener('resize', sizeTimeline);

/* ---------- playback ---------- */
let t = 0, playing = false, lastTs = null;
const playbtn = document.getElementById('playbtn');
const bigplay = document.getElementById('bigplay');
const speedSel = document.getElementById('speed');
const clock = document.getElementById('clock');
const fill = document.querySelector('#progress .fill');
const icPlay = document.getElementById('ic-play');
const icPause = document.getElementById('ic-pause');
const fmt = s => {
  const m = Math.floor(s/60), ss = Math.floor(s%60);
  return String(m).padStart(2,'0') + ':' + String(ss).padStart(2,'0');
};
function renderAt(time, force){
  for (const [pid, frames] of Object.entries(paneFrames)) {
    let i = paneIdx[pid];
    if (force || i < 0 || (frames[i] && frames[i][0] > time)) i = -1;
    while (i + 1 < frames.length && frames[i+1][0] <= time) i++;
    if (i !== paneIdx[pid] || force) {
      paneIdx[pid] = i;
      const el = paneEls[pid];
      el.innerHTML = i >= 0
        ? frameLines(frames[i][2], +el.dataset.cols, +el.dataset.rows).join('\n')
        : '';
    }
  }
  for (const d of dotEls)
    d.el.style.color = stColor(
      d.kind === 'ws' ? wsStatusAt(d.id, time) : statusAt(d.id, time));
  const tr = tlBody.querySelector('.tl-track');
  if (tr) {
    const r0 = tr.getBoundingClientRect(), rb = tlBody.getBoundingClientRect();
    cursor.style.left = (r0.left - rb.left + time / DUR * r0.width) + 'px';
  }
  clock.textContent = fmt(time) + ' / ' + fmt(DUR);
  fill.style.width = (time / DUR * 100) + '%';
}
function seek(time){ t = Math.max(0, Math.min(DUR, time)); renderAt(t, true); }
function setPlaying(p){
  playing = p;
  bigplay.classList.toggle('hidden', p || t > 0);
  icPlay.style.display = p ? 'none' : '';
  icPause.style.display = p ? '' : 'none';
}
function tick(ts){
  if (!playing) return;
  if (lastTs != null) {
    t += (ts - lastTs) / 1000 * (+speedSel.value);
    if (t >= DUR) { t = DUR; setPlaying(false); }
    renderAt(t, false);
  }
  lastTs = ts;
  if (playing) requestAnimationFrame(tick);
}
function toggle(){
  if (playing) { setPlaying(false); return; }
  if (t >= DUR) t = 0;
  setPlaying(true); lastTs = null;
  requestAnimationFrame(tick);
}
playbtn.addEventListener('click', toggle);
bigplay.addEventListener('click', toggle);
document.getElementById('progress').addEventListener('click', e => {
  const r = e.currentTarget.getBoundingClientRect();
  seek((e.clientX - r.left) / r.width * DUR);
});
addEventListener('keydown', e => {
  if (e.key === ' ') { e.preventDefault(); toggle(); }
});
renderAt(0, true);
</script>
</body>
</html>
"""


def render(recording_dir, out_path, title=None):
    with open(os.path.join(recording_dir, "session.json")) as f:
        session = json.load(f)
    casts = {}
    for pid, p in session["panes"].items():
        path = os.path.join(recording_dir, p["cast"])
        with open(path) as f:
            lines = f.read().splitlines()
        casts[pid] = [json.loads(l) for l in lines[1:] if l.strip()]
    data = json.dumps({"session": session, "casts": casts})
    data = data.replace("</", "<\\/")
    title = title or os.path.basename(os.path.abspath(recording_dir))
    html = (
        TEMPLATE
        .replace("__TITLE__", title)
        .replace("__HVER__", str(session.get("herdr_version", "?")))
        .replace("__DATA__", data)
    )
    with open(out_path, "w") as f:
        f.write(html)
    return out_path
