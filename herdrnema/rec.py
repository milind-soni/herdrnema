"""Record a herdr session: per-pane asciicast v2 files + session.json
(topology, layouts, agent lifecycle timeline).

Architecture: pure polling. Each tick takes one `session.snapshot` (panes,
agent statuses, layouts — herdr emits no events for status or output
changes, and pane `revision` does not track output) and one `pane.read`
per in-scope pane, diffing the visible ANSI screen into full-screen cast
frames.
"""

import json
import os
import re
import signal
import time

from .cast import CastWriter
from .client import HerdrClient, HerdrError


def safe_name(pane_id):
    return re.sub(r"[^A-Za-z0-9_-]", "-", pane_id)


class PaneRecorder:
    def __init__(self, pane_id, out_dir, cols, rows, title, t0):
        self.pane_id = pane_id
        self.cast_name = f"pane-{safe_name(pane_id)}.cast"
        self.writer = CastWriter(
            os.path.join(out_dir, self.cast_name), cols, rows, title=title, t0=t0
        )
        self.cols = cols
        self.rows = rows
        self.last_text = None
        self.frames = 0
        self.closed = False

    def maybe_frame(self, ansi_text, t):
        if self.closed or ansi_text == self.last_text:
            return False
        self.last_text = ansi_text
        self.writer.frame(ansi_text, t=t)
        self.frames += 1
        return True


class Recorder:
    def __init__(self, out_dir, workspaces=None, fps=8.0, socket_path=None,
                 quiet=False):
        self.out_dir = out_dir
        self.scope_ws = set(workspaces) if workspaces else None
        self.interval = 1.0 / fps
        self.client = HerdrClient(socket_path)
        self.quiet = quiet
        self.panes = {}          # pane_id -> PaneRecorder
        self.pane_meta = {}      # pane_id -> latest pane object
        self.agent_status = {}   # pane_id -> last status
        self.layouts = {}        # tab_id -> latest layout
        self.timeline = []
        self.t0 = None
        self.last_snapshot = None

    def log(self, msg):
        if not self.quiet:
            print(msg, flush=True)

    def in_scope(self, workspace_id):
        return self.scope_ws is None or workspace_id in self.scope_ws

    def _rect_for(self, pane_id, tab_id):
        layout = self.layouts.get(tab_id)
        if layout:
            for p in layout.get("panes", []):
                if p["pane_id"] == pane_id:
                    return p["rect"]["width"], p["rect"]["height"]
        return 80, 24

    @staticmethod
    def _title_for(pane):
        return (
            pane.get("terminal_title_stripped")
            or pane.get("terminal_title")
            or pane.get("agent")
            or pane["pane_id"]
        )

    def _mark(self, entry):
        self.timeline.append(entry)

    def _add_pane(self, pane, t):
        pid = pane["pane_id"]
        cols, rows = self._rect_for(pid, pane["tab_id"])
        self.panes[pid] = PaneRecorder(
            pid, self.out_dir, cols, rows, self._title_for(pane), self.t0
        )
        self.pane_meta[pid] = pane
        status = pane.get("agent_status", "unknown")
        self.agent_status[pid] = status
        self._mark(
            {"t": round(t - self.t0, 4), "type": "pane_started", "pane_id": pid,
             "workspace_id": pane["workspace_id"], "tab_id": pane["tab_id"],
             "agent": pane.get("agent"), "agent_status": status,
             "title": self._title_for(pane), "cols": cols, "rows": rows}
        )
        self.log(f"  + pane {pid} ({cols}x{rows}) {self._title_for(pane)}")

    def _apply_snapshot(self, snap, t):
        rel = round(t - self.t0, 4)
        for layout in snap.get("layouts", []):
            tid = layout["tab_id"]
            prev = self.layouts.get(tid)
            self.layouts[tid] = layout
            if prev is not None and prev != layout and self.in_scope(layout["workspace_id"]):
                self._mark({"t": rel, "type": "layout", "tab_id": tid,
                            "workspace_id": layout["workspace_id"],
                            "layout": layout})

        live = set()
        for pane in snap.get("panes", []):
            pid = pane["pane_id"]
            if not self.in_scope(pane["workspace_id"]):
                continue
            live.add(pid)
            if pid not in self.panes:
                self._add_pane(pane, t)
                continue
            self.pane_meta[pid] = pane
            status = pane.get("agent_status", "unknown")
            prev = self.agent_status.get(pid)
            if status != prev:
                self.agent_status[pid] = status
                agent = pane.get("agent")
                self._mark({"t": rel, "type": "agent_status", "pane_id": pid,
                            "agent": agent, "agent_status": status,
                            "title": self._title_for(pane)})
                self.panes[pid].writer.marker(
                    f"{agent or 'agent'}: {status}", t=t)
                self.log(f"  * {pid} {agent or ''} -> {status}")

        for pid, pr in self.panes.items():
            if not pr.closed and pid not in live:
                pr.closed = True
                self._mark({"t": rel, "type": "pane_closed", "pane_id": pid})
                self.log(f"  - pane {pid} closed")

    def _tick(self):
        t = time.time()
        try:
            snap = self.client.snapshot()
        except (HerdrError, ConnectionError, OSError) as e:
            self.log(f"  ! snapshot failed: {e}")
            return
        self.last_snapshot = snap
        self._apply_snapshot(snap, t)
        for pid, pr in self.panes.items():
            if pr.closed:
                continue
            try:
                read = self.client.pane_read(pid)
            except (HerdrError, ConnectionError, OSError):
                continue
            pr.maybe_frame(read.get("text", ""), t=time.time())

    def run(self, duration=None):
        # graceful stop on SIGTERM/SIGINT even when backgrounded (shells
        # start background jobs with SIGINT ignored)
        def _stop(signum, frame):
            raise KeyboardInterrupt
        signal.signal(signal.SIGTERM, _stop)
        signal.signal(signal.SIGINT, _stop)
        os.makedirs(self.out_dir, exist_ok=True)
        self.t0 = time.time()
        snap = self.client.snapshot()
        self.last_snapshot = snap
        for layout in snap.get("layouts", []):
            self.layouts[layout["tab_id"]] = layout
        self._apply_snapshot(snap, self.t0)
        self.log(f"recording {len(self.panes)} pane(s) -> {self.out_dir}  (Ctrl-C to stop)")
        try:
            while True:
                now = time.time()
                if duration is not None and now - self.t0 >= duration:
                    break
                self._tick()
                elapsed = time.time() - now
                if elapsed < self.interval:
                    time.sleep(self.interval - elapsed)
        except KeyboardInterrupt:
            self.log("\nstopping…")
        return self.finish()

    def finish(self):
        t_end = time.time()
        self._tick()  # final pass so the last state is always captured
        for pr in self.panes.values():
            pr.writer.close()
        snap = self.last_snapshot or {}
        session = {
            "format": "herdrnema/1",
            "herdr_version": snap.get("version"),
            "started_at": self.t0,
            "ended_at": t_end,
            "duration": round(t_end - self.t0, 4),
            "workspaces": [w for w in snap.get("workspaces", [])
                           if self.in_scope(w["workspace_id"])],
            "tabs": [t for t in snap.get("tabs", [])
                     if self.in_scope(t["workspace_id"])],
            "layouts": {tid: l for tid, l in self.layouts.items()
                        if self.in_scope(l["workspace_id"])},
            "panes": {
                pid: {
                    "cast": pr.cast_name,
                    "cols": pr.cols,
                    "rows": pr.rows,
                    "frames": pr.frames,
                    "workspace_id": self.pane_meta[pid]["workspace_id"],
                    "tab_id": self.pane_meta[pid]["tab_id"],
                    "agent": self.pane_meta[pid].get("agent"),
                    "title": self._title_for(self.pane_meta[pid]),
                    "final_status": self.agent_status.get(pid),
                }
                for pid, pr in self.panes.items()
            },
            "events": self.timeline,
        }
        path = os.path.join(self.out_dir, "session.json")
        with open(path, "w") as f:
            json.dump(session, f, indent=1)
        total = sum(pr.frames for pr in self.panes.values())
        self.log(
            f"done: {len(self.panes)} pane(s), {total} frames, "
            f"{session['duration']:.1f}s -> {path}"
        )
        return session
