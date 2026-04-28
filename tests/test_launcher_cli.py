import os
import socket
from unittest.mock import MagicMock, patch

import httpx
import pytest


def test_find_free_port_finds_one():
    from promptpressure.launcher import find_free_port
    p = find_free_port(8000, 8019)
    assert 8000 <= p <= 8019
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", p))
    finally:
        s.close()


def test_find_free_port_raises_when_all_taken():
    from promptpressure.launcher import find_free_port

    sockets = []
    try:
        for port in range(9050, 9055):
            s = socket.socket()
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", port))
            s.listen(1)
            sockets.append(s)
        with pytest.raises(RuntimeError, match="Could not find a free port"):
            find_free_port(9050, 9054)
    finally:
        for s in sockets:
            s.close()


def test_build_subprocess_env_preserves_path_and_adds_launcher_flags():
    from promptpressure.launcher import build_subprocess_env
    parent = {"PATH": "/usr/bin", "OPENROUTER_API_KEY": "secret", "HOME": "/home/x"}
    env = build_subprocess_env(parent)
    assert env["PATH"] == "/usr/bin"
    assert env["OPENROUTER_API_KEY"] == "secret"
    assert env["HOME"] == "/home/x"
    assert env["PROMPTPRESSURE_DEV_NO_AUTH"] == "1"
    assert env["PROMPTPRESSURE_LAUNCHER"] == "1"


def test_build_subprocess_env_does_not_mutate_input():
    from promptpressure.launcher import build_subprocess_env
    parent = {"PATH": "/usr/bin"}
    _ = build_subprocess_env(parent)
    assert parent == {"PATH": "/usr/bin"}


def test_probe_existing_launcher_returns_port_when_health_says_launcher_true():
    from promptpressure.launcher import probe_existing_launcher

    def mock_get(url, timeout):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"status": "ok", "launcher": True}
        return resp

    with patch.object(httpx, "get", side_effect=mock_get):
        port = probe_existing_launcher((8000,))
    assert port == 8000


def test_probe_existing_launcher_skips_non_launcher_servers():
    from promptpressure.launcher import probe_existing_launcher

    def mock_get(url, timeout):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"status": "ok"}  # No launcher field
        return resp

    with patch.object(httpx, "get", side_effect=mock_get):
        port = probe_existing_launcher((8000, 8001))
    assert port is None
