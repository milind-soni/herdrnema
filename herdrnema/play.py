"""Terminal playback of a recorded pane's asciicast."""

import json
import sys
import time


def load_cast(path):
    with open(path) as f:
        header = json.loads(f.readline())
        events = [json.loads(line) for line in f if line.strip()]
    return header, events


def play(path, speed=1.0, idle_limit=2.0):
    header, events = load_cast(path)
    sys.stdout.write("\x1b[2J\x1b[H")
    sys.stdout.flush()
    last_t = 0.0
    try:
        for t, kind, data in events:
            if kind != "o":
                continue
            delay = min((t - last_t) / speed, idle_limit)
            if delay > 0:
                time.sleep(delay)
            last_t = t
            sys.stdout.write(data)
            sys.stdout.flush()
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write("\x1b[0m\n")
        sys.stdout.flush()
    return header, len(events)
