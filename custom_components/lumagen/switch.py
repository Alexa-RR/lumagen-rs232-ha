"""Game mode switch."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import LumagenConfigEntry, LumagenCoordinator
from .entity import LumagenEntity, lumagen_command

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LumagenConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the switch."""
    async_add_entities([LumagenGameModeSwitch(entry.runtime_data)])


class LumagenGameModeSwitch(LumagenEntity, SwitchEntity):
    """Game mode (ZY551 / ZQI53, Radiance Pro firmware 051021 and newer)."""

    _attr_translation_key = "game_mode"
    _requires_power = True

    def __init__(self, coordinator: LumagenCoordinator) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, "game_mode")

    @property
    def is_on(self) -> bool | None:
        """Return True when game mode is on."""
        return self.coordinator.data.game_mode

    @lumagen_command
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn game mode on."""
        await self.coordinator.client.set_game_mode(True)

    @lumagen_command
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn game mode off."""
        await self.coordinator.client.set_game_mode(False)
