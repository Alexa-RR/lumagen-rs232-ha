"""Remote entity: power and raw/named key commands."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from typing import Any

from homeassistant.components.remote import (
    ATTR_DELAY_SECS,
    ATTR_NUM_REPEATS,
    DEFAULT_DELAY_SECS,
    RemoteEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import LumagenConfigEntry
from .entity import LumagenEntity, lumagen_command
from .pylumagen import commands

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LumagenConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the remote."""
    async_add_entities([LumagenRemote(entry.runtime_data, "remote")])


class LumagenRemote(LumagenEntity, RemoteEntity):
    """Power control plus every remote key.

    ``send_command`` accepts the key names in ``pylumagen.commands.KEYS``
    (``menu``, ``up``, ``aspect_2_40`` ...). Anything else is sent verbatim,
    e.g. ``ZY530K1KK\\r`` for raw RS-232 commands.
    """

    _attr_name = None

    @property
    def is_on(self) -> bool | None:
        """Return True when the processor is awake."""
        return self.coordinator.data.power

    @lumagen_command
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Wake the processor."""
        await self.coordinator.client.power_on()

    @lumagen_command
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Put the processor in standby."""
        await self.coordinator.client.standby()

    @lumagen_command
    async def async_send_command(self, command: Iterable[str], **kwargs: Any) -> None:
        """Send named keys or raw command strings."""
        repeats: int = kwargs.get(ATTR_NUM_REPEATS, 1)
        delay: float = kwargs.get(ATTR_DELAY_SECS, DEFAULT_DELAY_SECS)
        client = self.coordinator.client
        for repeat in range(repeats):
            for index, item in enumerate(command):
                if index or repeat:
                    await asyncio.sleep(delay)
                await client.send(commands.KEYS.get(item, item))
