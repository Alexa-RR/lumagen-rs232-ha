"""Exceptions raised by the Lumagen client."""

from __future__ import annotations


class LumagenError(Exception):
    """Base class for Lumagen errors."""


class LumagenConnectionError(LumagenError):
    """The serial connection could not be opened or was lost."""


class LumagenTimeoutError(LumagenError):
    """The processor did not answer a query in time."""
