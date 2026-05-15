"""Tests for user-facing disclaimer helpers."""

from __future__ import annotations

from fission_sim.disclaimer import DISCLAIMER_TEXT, print_disclaimer


def test_disclaimer_names_learning_use_and_not_real_world(capsys) -> None:
    """The console disclaimer should state the project boundary clearly."""
    print_disclaimer()

    captured = capsys.readouterr()
    assert "personal learning project" in DISCLAIMER_TEXT
    assert "not for real-world use" in DISCLAIMER_TEXT
    assert DISCLAIMER_TEXT in captured.err
