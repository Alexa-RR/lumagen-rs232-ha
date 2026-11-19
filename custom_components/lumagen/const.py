"""Constants for the Lumagen integration."""

from __future__ import annotations

import logging
from datetime import timedelta

DOMAIN = "lumagen"
LOGGER = logging.getLogger(__package__)

MANUFACTURER = "Lumagen"
SCAN_INTERVAL = timedelta(seconds=15)

CONF_INPUT_COUNT = "input_count"
DEFAULT_INPUT_COUNT = 8
