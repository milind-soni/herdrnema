import argparse
import json
import os
import sys


def main():
    ap = argparse.ArgumentParser(
        prog="herdrnema",
        description="Record and replay herdr sessions — asciinema for agent fleets.",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    rec = sub.add_parser("rec", help="record the current herdr session")
    rec.add_argument("out", help="output directory for the recording")
    rec.add_argument("--workspace", "-w", action="append",
                     help="limit to workspace id(s), e.g. -w wG (repeatable)")
    rec.add_argument("--fps", type=float, default=8.0,
                     help="frame poll rate per pane (default 8)")
    rec.add_argument("--duration", "-d", type=float, default=None,
                     help="stop after N seconds (default: run until Ctrl-C)")
    rec.add_argument("--socket", default=None, help="herdr socket path")
    rec.add_argument("--quiet", "-q", action="store_true")

    play = sub.add_parser("play", help="replay one pane's cast in the terminal")
    play.add_argument("recording", help="recording dir or .cast file")
    play.add_argument("--pane", help="pane id to play (default: first)")
    play.add_argument("--speed", type=float, default=1.0)

    info = sub.add_parser("info", help="describe a recording")
    info.add_argument("recording")

    html = sub.add_parser("html", help="render a self-contained HTML replay")
    html.add_argument("recording")
    html.add_argument("-o", "--output", default=None,
                      help="output html path (default <recording>/replay.html)")

    args = ap.parse_args()

    if args.cmd == "rec":
        from .rec import Recorder
        r = Recorder(args.out, workspaces=args.workspace, fps=args.fps,
                     socket_path=args.socket, quiet=args.quiet)
        r.run(duration=args.duration)

    elif args.cmd == "play":
        from .play import play as play_cast
        path = args.recording
        if os.path.isdir(path):
            session = json.load(open(os.path.join(path, "session.json")))
            panes = session["panes"]
            pane_id = args.pane or sorted(panes)[0]
            if pane_id not in panes:
                sys.exit(f"pane {pane_id} not in recording; have: {', '.join(sorted(panes))}")
            path = os.path.join(args.recording, panes[pane_id]["cast"])
        play_cast(path, speed=args.speed)

    elif args.cmd == "info":
        session = json.load(open(os.path.join(args.recording, "session.json")))
        print(f"herdr {session['herdr_version']}  duration {session['duration']:.1f}s")
        for pid, p in sorted(session["panes"].items()):
            print(f"  {pid}  {p['cols']}x{p['rows']}  {p['frames']} frames  "
                  f"agent={p['agent'] or '-'}  {p['title']}")
        statuses = [e for e in session["events"] if e["type"] == "agent_status"]
        print(f"  {len(session['events'])} timeline events "
              f"({len(statuses)} agent status changes)")

    elif args.cmd == "html":
        from .html import render
        out = args.output or os.path.join(args.recording, "replay.html")
        render(args.recording, out)
        print(f"wrote {out}")


if __name__ == "__main__":
    main()
