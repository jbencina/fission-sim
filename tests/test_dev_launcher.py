"""Tests for the development launcher helper.

These tests do not start real servers. They monkeypatch subprocess spawning so
launcher lifecycle behavior can be checked quickly and deterministically.
"""

from __future__ import annotations

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
