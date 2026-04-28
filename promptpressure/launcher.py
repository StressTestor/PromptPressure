"""
`pp` launcher CLI: spawn the API server in a subprocess and open a browser.

Parent process MUST NOT import promptpressure.api (it would trigger the same
auth-gate RuntimeError that the subprocess handles via env vars).
"""
import argparse
import os
import socket
import subprocess
import sys
import time
import webbrowser
from typing import Iterable, Optional

import httpx

PORT_RANGE = range(8000, 8020)
HEALTH_TIMEOUT_SECONDS = 10.0


def find_free_port(start: int, end: int) -> int:
    """Return the first port in [start, end] inclusive that's bindable on 127.0.0.1."""
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(
        f"Could not find a free port in {start}-{end}. "
        f"Stop another launcher or kill whatever is using these ports: lsof -i :{start}-{end}"
    )


def build_subprocess_env(parent_env: Optional[dict] = None) -> dict:
    """Copy parent env, add launcher flags. Never mutates input."""
    env = dict(parent_env if parent_env is not None else os.environ)
    env["PROMPTPRESSURE_DEV_NO_AUTH"] = "1"
    env["PROMPTPRESSURE_LAUNCHER"] = "1"
    return env


def probe_existing_launcher(ports: Iterable[int]) -> Optional[int]:
    """Return the first port whose /health response includes launcher: true."""
    for port in ports:
        try:
            r = httpx.get(f"http://127.0.0.1:{port}/health", timeout=0.5)
        except Exception:
            continue
        if r.status_code != 200:
            continue
        try:
            body = r.json()
        except Exception:
            continue
        if body.get("launcher") is True:
            return port
    return None


def wait_for_health(port: int, timeout: float = HEALTH_TIMEOUT_SECONDS) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = httpx.get(f"http://127.0.0.1:{port}/health", timeout=0.5)
            if r.status_code == 200 and r.json().get("launcher") is True:
                return True
        except Exception:
            pass
        time.sleep(0.2)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="pp",
        description="PromptPressure launcher: spawns the API and opens a browser. Binds 127.0.0.1 only.",
    )
    parser.add_argument("--version", action="store_true", help="Print package version and exit")
    args = parser.parse_args()

    if args.version:
        try:
            from importlib.metadata import version
            print(version("promptpressure"))
        except Exception:
            print("unknown")
        return 0

    existing = probe_existing_launcher(PORT_RANGE)
    if existing is not None:
        url = f"http://127.0.0.1:{existing}/"
        print(f"Found running launcher at {url}. Opening browser. (--new not yet implemented; v2)")
        if not webbrowser.open(url):
            print(f"Could not auto-open a browser. Visit {url} manually.", file=sys.stderr)
        return 0

    port = find_free_port(PORT_RANGE.start, PORT_RANGE.stop - 1)
    env = build_subprocess_env()
    cmd = [sys.executable, "-m", "uvicorn", "promptpressure.api:app",
           "--host", "127.0.0.1", "--port", str(port)]

    print(f"Starting PromptPressure launcher on http://127.0.0.1:{port}/")
    proc = subprocess.Popen(cmd, env=env)

    try:
        if not wait_for_health(port, HEALTH_TIMEOUT_SECONDS):
            print(
                f"PromptPressure server didn't respond on http://127.0.0.1:{port}/health "
                f"within {HEALTH_TIMEOUT_SECONDS:.0f} seconds. Check the subprocess output above for the real error. "
                f"Common causes: missing env vars, port collision, broken venv.",
                file=sys.stderr,
            )
            proc.terminate()
            return 2

        url = f"http://127.0.0.1:{port}/"
        if not webbrowser.open(url):
            print(f"Could not auto-open a browser. Visit {url} manually.", file=sys.stderr)
        print("Press Ctrl-C to stop.")
        proc.wait()
        return proc.returncode or 0

    except KeyboardInterrupt:
        print("\nShutting down...")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        return 0


if __name__ == "__main__":
    sys.exit(main())
