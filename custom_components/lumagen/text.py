"""Input names stored on the processor, editable from Home Assistant."""

from __future__ import annotations

from homeassistant.components.text import TextEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import LumagenConfigEntry, LumagenCoordinator
from .entity import LumagenEntity, lumagen_command
from .pylumagen.commands import LABEL_MAX_LENGTH, MAX_LABELED_INPUTS

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LumagenConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up one name entity per labelled input."""
    coordinator = entry.runtime_data
    count = min(coordinator.input_count, MAX_LABELED_INPUTS)
    async_add_entities(LumagenInputLabel(coordinator, number) for number in range(1, count + 1))


class LumagenInputLabel(LumagenEntity, TextEntity):
    """The name of one input (ZY524 to write, ZQS1 to read).

    Shows the name in the current memory; writing sets it in all four
    memories and saves the configuration so it survives a power cycle.
    """

    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "input_label"
    _attr_native_min = 1
    _attr_native_max = LABEL_MAX_LENGTH
    # The processor only accepts 0x20-0x7A; anything else ends the command.
    _attr_pattern = r"^[ -z]+$"
    _requires_power = True

    def __init__(self, coordinator: LumagenCoordinator, number: int) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, f"input_{number}_label")
        self._number = number
        self._attr_translation_placeholders = {"number": str(number)}

    @property
    def native_value(self) -> str | None:
        """Return the input's name in the current memory."""
        label = self.coordinator.data.input_label(self._number)
        # Labels are at most 10 characters; never let a longer one break the entity.
        return label[:LABEL_MAX_LENGTH] if label is not None else None

    @lumagen_command
    async def async_set_value(self, value: str) -> None:
        """Rename the input on the processor."""
        await self.coordinator.client.set_input_label(self._number, value)
