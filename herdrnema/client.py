"""Client for the herdr socket API.

Protocol: newline-delimited JSON over a unix socket. The server closes the
connection after each request/response — except `events.subscribe`, which
keeps the connection open and streams event envelopes.
"""

import json
import os
import socket
import subprocess


def default_socket_path():
    env = os.environ.get("HERDR_SOCKET")
    if env:
        return env
    try:
        out = subprocess.run(
            ["herdr", "status"], capture_output=True, text=True, timeout=5
        ).stdout
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("socket:"):
                return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return os.path.expanduser("~/.config/herdr/herdr.sock")


class HerdrError(Exception):
    def __init__(self, code, message):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def _recv_line(sock, buf, timeout=None):
    sock.settimeout(timeout)
    while b"\n" not in buf:
        chunk = sock.recv(1 << 16)
        if not chunk:
            raise ConnectionError("herdr socket closed")
        buf += chunk
    line, rest = buf.split(b"\n", 1)
    return json.loads(line), rest


class HerdrClient:
    """Request/response client. Opens a fresh connection per request
    (the server is one-shot per connection)."""

    def __init__(self, socket_path=None):
        self.path = socket_path or default_socket_path()

    def request(self, method, params=None, timeout=15):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(self.path)
        try:
            sock.sendall(
                json.dumps({"id": "hnema", "method": method, "params": params or {}}).encode()
                + b"\n"
            )
            msg, _ = _recv_line(sock, b"", timeout=timeout)
        finally:
            sock.close()
        if msg.get("error"):
            err = msg["error"]
            raise HerdrError(err.get("code"), err.get("message"))
        return msg.get("result", {})

    def snapshot(self):
        return self.request("session.snapshot")["snapshot"]

    def pane_read(self, pane_id, source="visible", fmt="ansi"):
        return self.request(
            "pane.read",
            {"pane_id": pane_id, "source": source, "format": fmt, "strip_ansi": False},
        )["read"]


class EventStream:
    """Long-lived subscription connection."""

    def __init__(self, subscriptions, socket_path=None):
        self.path = socket_path or default_socket_path()
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(self.path)
        self._buf = b""
        self.sock.sendall(
            json.dumps(
                {"id": "hnema:sub", "method": "events.subscribe",
                 "params": {"subscriptions": subscriptions}}
            ).encode()
            + b"\n"
        )
        msg, self._buf = _recv_line(self.sock, self._buf, timeout=10)
        if msg.get("error"):
            err = msg["error"]
            raise HerdrError(err.get("code"), err.get("message"))

    def next_event(self, timeout=None):
        """Return the next event envelope, or None on timeout."""
        try:
            msg, self._buf = _recv_line(self.sock, self._buf, timeout=timeout)
        except socket.timeout:
            return None
        return msg

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass
