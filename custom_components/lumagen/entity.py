"""Base entity for the Lumagen integration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, Concatenate

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import LumagenCoordinator
from .pylumagen import LumagenError


class LumagenEntity(CoordinatorEntity[LumagenCoordinator]):
    """Common device info, unique IDs and availability."""

    _attr_has_entity_name = True
    _requires_power = False
    """Make the entity unavailable while the processor is in standby."""

    def __init__(self, coordinator: LumagenCoordinator, key: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        serial = coordinator.config_entry.unique_id
        self._attr_unique_id = f"{serial}_{key}"
        identity = coordinator.data.identity
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(serial))},
            manufacturer=MANUFACTURER,
            name=coordinator.config_entry.title,
            model=identity.model_name if identity else None,
            model_id=identity.model_number if identity else None,
            sw_version=identity.software_revision if identity else None,
            serial_number=identity.serial_number if identity else None,
        )

    @property
    def available(self) -> bool:
        """Return True when connected (and powered on, if required)."""
        if not super().available or not self.coordinator.client.connected:
            return False
        return not self._requires_power or bool(self.coordinator.data.power)


def lumagen_command[E: LumagenEntity, **P](
    func: Callable[Concatenate[E, P], Awaitable[Any]],
) -> Callable[Concatenate[E, P], Awaitable[None]]:
    """Turn client errors into HomeAssistantError and refresh afterwards."""

    @wraps(func)
    async def wrapper(self: E, *args: P.args, **kwargs: P.kwargs) -> None:
        try:
            await func(self, *args, **kwargs)
        except LumagenError as err:
            raise HomeAssistantError(f"Lumagen command failed: {err}") from err
        # Publish optimistic state now; the refresh confirms it.
        self.coordinator.async_update_listeners()
        await self.coordinator.async_request_refresh()

    return wrapper
