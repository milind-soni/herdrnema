# Full-resolution staged recordings

herdr computes workspace layouts against the attached client's viewport, so a
recording can never be roomier than the client that laid it out. To stage a
demo at any resolution regardless of your terminal size:

1. **Attach a hidden client at the size you want, in a throwaway session.**
   Fork a PTY, exec `herdr --session <name>`, and set the window size with
   `TIOCSWINSZ` (e.g. 200×55). Keep this process alive for the whole
   recording — it is what gives the layout engine its viewport.
2. **Drive everything over that session's socket**
   (`~/.config/herdr/sessions/<name>/herdr.sock`). The `herdr` CLI always
   talks to the default session, so use the socket API directly:
   `pane.split`, `pane.send_text`, `agent.start`, `agent.prompt`.
   Target agents by **pane id**, not name — names can survive a session
   restore in a taken-but-unresolvable state.
3. **Record with `herdrnema rec --socket <that socket>`**, run your scenario,
   then stop the recorder with SIGTERM (it finalizes gracefully).
4. **Tear down completely:** kill the hidden client, then
   `herdr session stop <name>`, `herdr session delete <name>`, and remove
   `~/.config/herdr/sessions/<name>` — persistent sessions restore panes
   *and running agents* on relaunch otherwise.

`scripts/record_full_res_demo.py` implements the whole flow: a 200×55 hidden
client, a Claude Code agent answering a prompt beside a scripted build pane,
recorded at 10 fps. The `examples/claude-code` recording was produced by it.
