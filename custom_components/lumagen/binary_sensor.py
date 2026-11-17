"""Signal and HDR binary sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import LumagenConfigEntry, LumagenCoordinator
from .entity import LumagenEntity
from .pylumagen import FullInfo, InputStatus

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class LumagenBinarySensorDescription(BinarySensorEntityDescription):
    """Describes a binary sensor derived from the full-information reply."""

    value_fn: Callable[[FullInfo], bool | None]


BINARY_SENSORS = (
    LumagenBinarySensorDescription(
        key="signal",
        translation_key="signal",
        value_fn=lambda info: info.input_status is InputStatus.ACTIVE_VIDEO,
    ),
    LumagenBinarySensorDescription(
        key="hdr",
        translation_key="hdr",
        value_fn=lambda info: info.is_hdr if info.has_source else None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LumagenConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensors."""
    async_add_entities(
        LumagenBinarySensor(entry.runtime_data, description) for description in BINARY_SENSORS
    )


class LumagenBinarySensor(LumagenEntity, BinarySensorEntity):
    """A binary sensor backed by the full-information reply."""

    entity_description: LumagenBinarySensorDescription
    _requires_power = True

    def __init__(
        self,
        coordinator: LumagenCoordinator,
        description: LumagenBinarySensorDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """Return the sensor value."""
        info = self.coordinator.data.full_info
        return None if info is None else self.entity_description.value_fn(info)
