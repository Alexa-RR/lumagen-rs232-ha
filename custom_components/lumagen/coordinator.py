"""Coordinator that polls the processor and relays its unsolicited reports."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_INPUT_COUNT, DEFAULT_INPUT_COUNT, DOMAIN, LOGGER, SCAN_INTERVAL
from .pylumagen import LumagenClient, LumagenError, LumagenState, Message

type LumagenConfigEntry = ConfigEntry[LumagenCoordinator]


class LumagenCoordinator(DataUpdateCoordinator[LumagenState]):
    """Owns the client; data is the client's live state object."""

    config_entry: LumagenConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: LumagenConfigEntry, client: LumagenClient
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.client = client
        self._labeled_memories: set[str] = set()
        entry.async_on_unload(client.add_message_listener(self._handle_report))
        entry.async_on_unload(client.add_connection_listener(self._handle_connection))

    @property
    def input_count(self) -> int:
        """Number of inputs offered in the input selector."""
        return int(self.config_entry.options.get(CONF_INPUT_COUNT, DEFAULT_INPUT_COUNT))

    async def _async_update_data(self) -> LumagenState:
        if not self.client.connected:
            raise UpdateFailed("Not connected to the processor")
        try:
            state = await self.client.refresh()
            memory = state.current_memory
            if state.power and memory and memory not in self._labeled_memories:
                await self.client.refresh_labels(memory, self.input_count)
                self._labeled_memories.add(memory)
        except LumagenError as err:
            raise UpdateFailed(f"Processor did not respond: {err}") from err
        return state

    @callback
    def _handle_report(self, message: Message) -> None:
        """Push unsolicited reports (Report mode changes / Echo off with status)."""
        self.async_set_updated_data(self.client.state)

    @callback
    def _handle_connection(self, connected: bool) -> None:
        if connected:
            self._labeled_memories.clear()
            self.config_entry.async_create_background_task(
                self.hass, self.async_request_refresh(), "lumagen reconnect refresh"
            )
        else:
            self.async_set_update_error(UpdateFailed("Connection to the processor lost"))
