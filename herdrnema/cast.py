"""asciicast v2 writer. One .cast file per pane, streamed to disk."""

import json
import time


class CastWriter:
    def __init__(self, path, width, height, title=None, t0=None):
        self.path = path
        self.t0 = t0 if t0 is not None else time.time()
        self.f = open(path, "w")
        header = {
            "version": 2,
            "width": width,
            "height": height,
            "timestamp": int(self.t0),
        }
        if title:
            header["title"] = title
        self.f.write(json.dumps(header) + "\n")
        self.events = 0

    def _stamp(self, t):
        return round((t if t is not None else time.time()) - self.t0, 4)

    def output(self, data, t=None):
        self.f.write(json.dumps([self._stamp(t), "o", data]) + "\n")
        self.events += 1
        self.f.flush()

    def marker(self, label, t=None):
        self.f.write(json.dumps([self._stamp(t), "m", label]) + "\n")
        self.f.flush()

    def frame(self, ansi_text, t=None):
        """Write a full-screen frame: home + clear-below, then the screen."""
        self.output("\x1b[H" + ansi_text + "\x1b[0m\x1b[J", t=t)

    def close(self):
        self.f.close()
