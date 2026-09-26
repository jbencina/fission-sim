"""Shared fixtures for the API tests."""

from __future__ import annotations

import pytest

from fission_sim.api.runtime import SimRuntime


@pytest.fixture
async def runtime():
    """Construct a SimRuntime, start it, yield it, then stop it."""
    rt = SimRuntime()
    await rt.start()
    yield rt
    await rt.stop()
