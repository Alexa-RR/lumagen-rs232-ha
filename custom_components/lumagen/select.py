"""Input and input-memory selectors."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import LumagenConfigEntry, LumagenCoordinator
from .entity import LumagenEntity, lumagen_command
from .pylumagen import commands

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LumagenConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the selectors."""
    coordinator = entry.runtime_data
    async_add_entities([LumagenInputSelect(coordinator), LumagenMemorySelect(coordinator)])


class LumagenInputSelect(LumagenEntity, SelectEntity):
    """Selects the input; options use the labels set on the processor."""

    _attr_translation_key = "input"
    _requires_power = True

    def __init__(self, coordinator: LumagenCoordinator) -> None:
        """Initialize the selector."""
        super().__init__(coordinator, "input")

    def _option(self, number: int) -> str:
        label = self.coordinator.data.input_label(number)
        return f"{number}: {label}" if label else f"Input {number}"

    @property
    def options(self) -> list[str]:
        """Return one option per configured input."""
        return [self._option(n) for n in range(1, self.coordinator.input_count + 1)]

    @property
    def current_option(self) -> str | None:
        """Return the selected input."""
        number = self.coordinator.data.current_input
        if number is None or number > self.coordinator.input_count:
            return None
        return self._option(number)

    @lumagen_command
    async def async_select_option(self, option: str) -> None:
        """Select an input."""
        await self.coordinator.client.select_input(self.options.index(option) + 1)


class LumagenMemorySelect(LumagenEntity, SelectEntity):
    """Selects input memory A-D."""

    _attr_translation_key = "memory"
    _requires_power = True

    def __init__(self, coordinator: LumagenCoordinator) -> None:
        """Initialize the selector."""
        super().__init__(coordinator, "memory")
        self._attr_options = [memory.lower() for memory in commands.MEMORIES]

    @property
    def current_option(self) -> str | None:
        """Return the active memory."""
        memory = self.coordinator.data.current_memory
        return memory.lower() if memory else None

    @lumagen_command
    async def async_select_option(self, option: str) -> None:
        """Select a memory."""
        await self.coordinator.client.select_memory(option)
