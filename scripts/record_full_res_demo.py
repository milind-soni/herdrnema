"""Run the claude demo in an isolated big-viewport herdr session and record it."""
import os, pty, time, signal, select, fcntl, termios, struct, sys, subprocess, json

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from herdrnema.client import HerdrClient

SESSION = "hnema-demo-%d" % os.getpid()
SOCK = os.path.expanduser(f"~/.config/herdr/sessions/{SESSION}/herdr.sock")
SCRATCH = "/tmp/herdrnema-demo"
COLS, ROWS = 200, 55
os.makedirs(SCRATCH, exist_ok=True)

# 1. hidden client at a big size — this is what makes the layout roomy
env = dict(os.environ, TERM="xterm-256color")
pid, fd = pty.fork()
if pid == 0:
    os.execvpe("herdr", ["herdr", "--session", SESSION], env)
fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", ROWS, COLS, 0, 0))

def drain(secs):
    t0 = time.time()
    while time.time() - t0 < secs:
        r, _, _ = select.select([fd], [], [], 0.3)
        if r:
            try: os.read(fd, 65536)
            except OSError: return

drain(4)
c = HerdrClient(SOCK)
snap = c.snapshot()
area = snap["layouts"][0]["area"]
print("viewport area:", area, flush=True)
p1 = snap["panes"][0]["pane_id"]

# 2. split for the parallel build pane
r = c.request("pane.split", {"pane_id": p1, "direction": "right",
                             "ratio": 0.62, "focus": False,
                             "cwd": os.path.expanduser("~")})
p2 = r["pane"]["pane_id"]
drain(1)

# 3. start the recorder on this session
rec = subprocess.Popen(
    [sys.executable, "-m", "herdrnema", "rec", f"{SCRATCH}/rec_big",
     "--fps", "10", "--socket", SOCK],
    cwd=REPO,
    stdout=open(f"{SCRATCH}/rec_big.log", "w"), stderr=subprocess.STDOUT)
time.sleep(1.5)

# 4. claude agent + parallel build
c.request("pane.send_text", {"pane_id": p2,
    "text": 'for i in $(seq 1 22); do printf "\\033[2m[build]\\033[0m compiling module %d/22 \\033[32m✓\\033[0m\\n" $i; sleep 1.1; done; printf "\\033[1;32mbuild ok — all modules compiled\\033[0m\\n"\n'})
from herdrnema.client import HerdrError
try:
    c.request("agent.start", {"name": "bd%d" % os.getpid(), "kind": "claude",
                              "pane_id": p1, "timeout_ms": 45000}, timeout=50)
    print("claude started", flush=True)
except HerdrError as e:
    print("agent.start:", e, "— reusing existing agent", flush=True)
res = None
for attempt in range(30):
    drain(1)
    agents = c.request("agent.list").get("agents", [])
    me = [a for a in agents if a["pane_id"] == p1]
    st = me[0].get("agent_status") if me else None
    print(f"  attempt {attempt}: status={st}", flush=True)
    if st == "blocked":
        c.request("agent.send_keys", {"target": p1, "keys": ["enter"]})
        continue
    if st in ("idle", "done", "working"):
        try:
            res = c.request("agent.prompt", {
                "target": p1,
                "text": "Explain in a short paragraph why recording multi-agent terminal sessions is useful, then give 3 example use cases as bullets. No tools.",
                "wait": {"until": ["idle", "done"], "timeout_ms": 120000}}, timeout=130)
            break
        except HerdrError as e:
            print("  prompt retry:", e, flush=True)
print("prompt done:", (res or {}).get("agent", {}).get("agent_status"), flush=True)
drain(6)

# 5. stop recorder gracefully, then tear the session down
rec.send_signal(signal.SIGTERM)
rec.wait(timeout=15)
os.kill(pid, signal.SIGTERM)
time.sleep(0.5)
try: os.kill(pid, signal.SIGKILL)
except ProcessLookupError: pass
subprocess.run(["herdr", "session", "stop", SESSION], capture_output=True)
subprocess.run(["herdr", "session", "delete", SESSION], capture_output=True)
import shutil
shutil.rmtree(os.path.expanduser(f"~/.config/herdr/sessions/{SESSION}"),
              ignore_errors=True)
print(open(f"{SCRATCH}/rec_big.log").read(), flush=True)
print(f"recording in {SCRATCH}/rec_big — render with: "
      f"python3 -m herdrnema html {SCRATCH}/rec_big", flush=True)
