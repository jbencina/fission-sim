"""Tests for the development launcher helper.

These tests do not start real servers. They monkeypatch subprocess spawning,
or spawn tiny Python processes, so launcher lifecycle behavior can be checked
quickly and deterministically.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

import scripts.dev as dev


class FakeProcess:
    """Minimal subprocess.Popen stand-in for launcher cleanup tests."""

    def __init__(self, pid: int) -> None:
        self.pid = pid
        self.stdout = []


def test_start_children_cleans_up_backend_when_frontend_spawn_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the second child fails to spawn, the first child must not be orphaned."""
    backend = FakeProcess(pid=1234)
    popen_calls = 0
    cleanup_seen: list[list[FakeProcess]] = []

    def fake_popen(*_args: Any, **_kwargs: Any) -> FakeProcess:
        nonlocal popen_calls
        popen_calls += 1
        if popen_calls == 1:
            return backend
        raise OSError("npm not found")

    def fake_terminate_children() -> None:
        cleanup_seen.append(list(dev._children))
        dev._children.clear()

    monkeypatch.setattr(dev.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(dev, "_terminate_children", fake_terminate_children)
    dev._children.clear()

    with pytest.raises(OSError, match="npm not found"):
        dev._start_children({})

    assert cleanup_seen == [[backend]]
    assert dev._children == []


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


@pytest.mark.skipif(sys.platform == "win32", reason="launcher relies on Unix process groups")
def test_terminate_children_stops_descendants_of_an_exited_leader(monkeypatch: pytest.MonkeyPatch) -> None:
    """A wrapper that dies while its child survives must not leave the child running.

    The leader starts a sleeping child in its own process group, prints the
    child's PID, and exits. Cleanup then has no live leader to ask for a group
    ID; it must use the group ID recorded at spawn.
    """
    leader_code = (
        "import subprocess, sys\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'],\n"
        "                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
        "print(child.pid, flush=True)\n"
    )
    monkeypatch.setattr(dev, "_children", [])
    monkeypatch.setattr(dev, "_process_groups", [])
    leader = dev._spawn(
        [sys.executable, "-c", leader_code],
        {"stdout": subprocess.PIPE, "text": True, "start_new_session": True},
    )
    pgid = leader.pid
    try:
        descendant = int(leader.stdout.readline())
        leader.wait(timeout=10)
        leader.stdout.close()
        assert _alive(descendant), "precondition: the child outlives its leader"

        dev._terminate_children(timeout=2.0)

        deadline = time.monotonic() + 5.0  # allow init/launchd to reap it
        while _alive(descendant) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not _alive(descendant)
    finally:
        try:
            os.killpg(pgid, signal.SIGKILL)  # never leak the sleeper, even on failure
        except ProcessLookupError:
            pass


def test_backend_port_defaults_to_8780(monkeypatch: pytest.MonkeyPatch) -> None:
    """The default avoids 8000, which many other local services use."""
    monkeypatch.delenv(dev.API_PORT_ENV, raising=False)
    assert dev._api_port() == 8780
    assert dev._backend_cmd(8780)[-3:] == ["--port", "8780", "--reload"]


def test_default_port_matches_vite_proxy_default() -> None:
    vite_config = (Path(__file__).resolve().parents[1] / "web" / "vite.config.ts").read_text()
    assert f"FISSION_SIM_API_PORT ?? '{dev.DEFAULT_API_PORT}'" in vite_config


def test_backend_port_follows_fission_sim_api_port(monkeypatch: pytest.MonkeyPatch) -> None:
    """The same variable moves the backend and Vite's proxy target."""
    monkeypatch.setenv(dev.API_PORT_ENV, "8781")
    assert dev._api_port() == 8781
    assert "8781" in dev._backend_cmd(8781)


@pytest.mark.parametrize("bad", ["abc", "0", "70000", "-1"])
def test_backend_port_rejects_invalid_values(monkeypatch: pytest.MonkeyPatch, bad: str) -> None:
    monkeypatch.setenv(dev.API_PORT_ENV, bad)
    with pytest.raises(SystemExit, match=dev.API_PORT_ENV):
        dev._api_port()
