"""Video status sensors from the full-information reply (ZQI21-ZQI24)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import EntityCategory, UnitOfFrequency
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .coordinator import LumagenConfigEntry, LumagenCoordinator
from .entity import LumagenEntity
from .pylumagen import Colorspace, FullInfo, InputStatus
from .pylumagen.models import aspect_to_ratio

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class LumagenSensorDescription(SensorEntityDescription):
    """Describes a sensor derived from the full-information reply."""

    value_fn: Callable[[FullInfo], StateType]


def _source[T](getter: Callable[[FullInfo], T]) -> Callable[[FullInfo], T | None]:
    """Only report source values while a source is present."""
    return lambda info: getter(info) if info.has_source else None


SENSORS = (
    LumagenSensorDescription(
        key="input_status",
        translation_key="input_status",
        device_class=SensorDeviceClass.ENUM,
        options=[status.name.lower() for status in InputStatus],
        value_fn=lambda info: (
            info.input_status.name.lower() if info.input_status is not None else None
        ),
    ),
    LumagenSensorDescription(
        key="source_resolution",
        translation_key="source_resolution",
        value_fn=lambda info: info.source_resolution,
    ),
    LumagenSensorDescription(
        key="source_frame_rate",
        translation_key="source_frame_rate",
        device_class=SensorDeviceClass.FREQUENCY,
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        suggested_display_precision=2,
        value_fn=lambda info: info.source_frame_rate,
    ),
    LumagenSensorDescription(
        key="source_content_aspect",
        translation_key="source_content_aspect",
        suggested_display_precision=2,
        value_fn=_source(lambda info: aspect_to_ratio(info.source_content_aspect)),
    ),
    LumagenSensorDescription(
        key="source_raster_aspect",
        translation_key="source_raster_aspect",
        suggested_display_precision=2,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_source(lambda info: aspect_to_ratio(info.source_raster_aspect)),
    ),
    LumagenSensorDescription(
        key="detected_content_aspect",
        translation_key="detected_content_aspect",
        suggested_display_precision=2,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_source(lambda info: aspect_to_ratio(info.detected_content_aspect)),
    ),
    LumagenSensorDescription(
        key="output_resolution",
        translation_key="output_resolution",
        value_fn=lambda info: info.output_resolution,
    ),
    LumagenSensorDescription(
        key="output_frame_rate",
        translation_key="output_frame_rate",
        device_class=SensorDeviceClass.FREQUENCY,
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        suggested_display_precision=2,
        value_fn=lambda info: info.output_frame_rate,
    ),
    LumagenSensorDescription(
        key="output_aspect",
        translation_key="output_aspect",
        suggested_display_precision=2,
        value_fn=lambda info: aspect_to_ratio(info.output_aspect),
    ),
    LumagenSensorDescription(
        key="output_colorspace",
        translation_key="output_colorspace",
        device_class=SensorDeviceClass.ENUM,
        options=[space.name.lower() for space in Colorspace],
        value_fn=lambda info: (
            info.output_colorspace.name.lower() if info.output_colorspace is not None else None
        ),
    ),
    LumagenSensorDescription(
        key="output_cms",
        translation_key="output_cms",
        value_fn=lambda info: info.output_cms,
    ),
    LumagenSensorDescription(
        key="output_style",
        translation_key="output_style",
        value_fn=lambda info: info.output_style,
    ),
    LumagenSensorDescription(
        key="input_config",
        translation_key="input_config",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda info: info.input_config,
    ),
    LumagenSensorDescription(
        key="physical_input",
        translation_key="physical_input",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda info: info.physical_input,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LumagenConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors."""
    async_add_entities(LumagenSensor(entry.runtime_data, description) for description in SENSORS)


class LumagenSensor(LumagenEntity, SensorEntity):
    """A sensor backed by the full-information reply."""

    entity_description: LumagenSensorDescription
    _requires_power = True

    def __init__(
        self, coordinator: LumagenCoordinator, description: LumagenSensorDescription
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType:
        """Return the sensor value."""
        info = self.coordinator.data.full_info
        return None if info is None else self.entity_description.value_fn(info)
