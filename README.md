# herdrnema

**asciinema for agent fleets.** Record a live [herdr](https://herdr.dev) session —
every pane's terminal, the workspace layout, and each agent's lifecycle
(`working` / `blocked` / `done`) — and replay it as a single self-contained
HTML page that reproduces the herdr screen, with a scrubbable agent timeline.

Asciinema records one terminal. herdrnema records the *orchestration*: watch
several agents work in parallel, see one go blocked, scrub to the moment
everything lands.

## Usage

```sh
# record everything in the current herdr session (Ctrl-C or SIGTERM to stop)
herdrnema rec ./my-recording

# limit to one workspace, stop after 60s, custom frame rate
herdrnema rec ./my-recording -w wG --duration 60 --fps 10

# what's inside
herdrnema info ./my-recording

# replay one pane in the terminal
herdrnema play ./my-recording --pane wG:p1 --speed 2

# render the shareable replay page
herdrnema html ./my-recording        # -> my-recording/replay.html
```

No dependencies — Python 3.9+ stdlib only. Run as `python3 -m herdrnema …`
from the repo, or `pip install -e .` for the `herdrnema` command.

See `examples/claude-code/replay.html` for a real recording: a Claude Code
agent answering a prompt beside a build pane, with its `idle → working → done`
arc on the timeline.

## The replay page

`herdrnema html` produces one self-contained file (no external assets, no
player library) that reconstructs the herdr client screen from the recorded
character-cell geometry:

- sidebar with the *spaces* list and *agents* section — status dots update
  live during playback, like the real UI
- tab bar, pane border boxes (focus-colored), panes at their exact recorded
  rects, ANSI-styled content
- herdr's Catppuccin Mocha palette, extracted from a real herdr TUI capture
- asciinema-style controls: play/pause (space), seek, speed, plus a per-pane
  agent-lifecycle timeline with click-to-seek

## Recording format

A recording is a directory:

- `pane-<id>.cast` — one [asciicast v2](https://docs.asciinema.org/manual/asciicast/v2/)
  file per pane, playable by any asciinema tooling (`asciinema play …`).
  Frames are full-screen ANSI repaints; agent status changes are embedded as
  `m` (marker) events.
- `session.json` — topology (workspaces / tabs / panes), per-tab layouts with
  character-cell rects, and a timeline of events: `pane_started`,
  `agent_status`, `agent_detected`, `layout`, `pane_closed`.
- `replay.html` (after `herdrnema html`).

## Recording at full resolution

herdr lays workspaces out at the attached client's viewport size. Two
consequences:

- a recording of your live session mirrors your actual herdr window — run
  herdr fullscreen for roomy recordings;
- a workspace that has never been displayed gets a bare 80×24 default.

For staged demo recordings at any resolution regardless of your terminal,
attach a hidden client at the size you want in a throwaway session and drive
it over that session's socket (see `docs/full-res-recipe.md`).
`scripts/record_full_res_demo.py` implements the whole flow — the
`examples/claude-code` recording was produced by it.

## How it captures (herdr 0.8, protocol 19)

Findings the implementation is built on:

- The herdr socket (`~/.config/herdr/herdr.sock`) speaks newline-delimited
  JSON and is **one-shot per connection** — every request opens a fresh
  connection. Only `events.subscribe` keeps the connection open (and it
  replays a historical backlog on subscribe).
- There is **no raw output stream**: pane `revision` does not track output,
  `pane.updated` events don't fire on output or agent-status changes, and
  `pane.output_matched` fires once then goes silent. So herdrnema **polls**:
  one `session.snapshot` per tick (statuses, layouts, pane add/remove) plus
  one `pane.read` (visible screen, ANSI) per pane, diffing frames. Default
  8 fps — a rapid flipbook of real screens, not a byte-perfect PTY tape.
- A pane's terminal grid is *not* shrunk when splits make its rect smaller;
  the client clips the view inside the border box. The replay renders the
  same way (border on the rect's outer ring, content inset one cell,
  clipped).
- `pane.read` ANSI already uses `\r\n` and full SGR; layout rects are in
  character cells, so geometry maps 1:1 to the replay grid.
- The `herdr` CLI does not honor a socket override — to talk to a named
  session, connect to `~/.config/herdr/sessions/<name>/herdr.sock` directly.

## Status / roadmap

- [x] `rec` (poll + diff, lifecycle timeline, mid-recording pane add/close,
      graceful SIGTERM/SIGINT stop)
- [x] `play`, `info`
- [x] `html` — herdr-faithful self-contained replay page
- [ ] layout changes *during* playback (recorded in `session.json`; the
      player renders the final layout per tab)
- [ ] workspace/tab switcher for multi-workspace recordings
- [ ] `herdrnema share` — publish the replay page somewhere linkable
- [ ] smoother playback (higher fps + appended-line interpolation)
