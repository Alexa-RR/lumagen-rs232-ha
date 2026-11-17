"""Shared fixtures."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import patch

import pytest

from custom_components.lumagen.pylumagen import client as client_module

from .fake_lumagen import FakeLumagen


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let Home Assistant load custom_components/lumagen."""


@pytest.fixture
def fake_lumagen() -> Generator[FakeLumagen]:
    """Replace serialx with an in-memory Radiance Pro."""
    device = FakeLumagen()
    with (
        patch.object(
            client_module.serialx, "open_serial_connection", device.open_serial_connection
        ),
        patch.object(client_module, "RECONNECT_DELAYS", (0,)),
    ):
        yield device
