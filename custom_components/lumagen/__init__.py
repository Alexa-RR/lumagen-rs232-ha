"""The Lumagen integration."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import build_url
from .coordinator import LumagenConfigEntry, LumagenCoordinator
from .pylumagen import LumagenClient, LumagenConnectionError

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.REMOTE,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: LumagenConfigEntry) -> bool:
    """Set up a Lumagen processor from a config entry."""
    client = LumagenClient(build_url(dict(entry.data)))
    try:
        await client.connect()
    except LumagenConnectionError as err:
        raise ConfigEntryNotReady(str(err)) from err

    coordinator = LumagenCoordinator(hass, entry, client)
    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryNotReady:
        await client.close()
        raise

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: LumagenConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.client.close()
    return unload_ok
