"""Constants for the Lumagen integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.const import CONF_DEVICE, CONF_HOST, CONF_PORT, CONF_PROTOCOL

DOMAIN = "lumagen"
LOGGER = logging.getLogger(__package__)

MANUFACTURER = "Lumagen"
SCAN_INTERVAL = timedelta(seconds=15)

CONF_CONNECTION_TYPE = "connection_type"
CONNECTION_USB = "usb"
CONNECTION_NETWORK = "network"

PROTOCOL_SOCKET = "socket"
PROTOCOL_RFC2217 = "rfc2217"
DEFAULT_NETWORK_PORT = 2000

CONF_INPUT_COUNT = "input_count"
DEFAULT_INPUT_COUNT = 8


def build_url(data: dict[str, Any]) -> str:
    """Build the serialx URL for a config entry's connection settings."""
    if data[CONF_CONNECTION_TYPE] == CONNECTION_USB:
        return str(data[CONF_DEVICE])
    host = str(data[CONF_HOST])
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"  # IPv6 literal
    return f"{data[CONF_PROTOCOL]}://{host}:{data[CONF_PORT]}"
