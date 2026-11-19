"""Coordinator that polls the processor and relays its unsolicited reports."""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import CONF_INPUT_COUNT, DEFAULT_INPUT_COUNT, DOMAIN, LOGGER, SCAN_INTERVAL
from .pylumagen import LumagenClient, LumagenConnectionError, LumagenError, LumagenState, Message

type LumagenConfigEntry = ConfigEntry[LumagenCoordinator]

# How long the processor may go quiet before its entities become unavailable.
# It ignores queries for ~20 s while booting after power-on, and a network
# bridge connection can drop and come back within seconds; neither should
# blank every entity.
UNAVAILABLE_AFTER = timedelta(seconds=60)


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
        self._last_contact: datetime | None = None
        self._offline_timer: CALLBACK_TYPE | None = None
        entry.async_on_unload(client.add_message_listener(self._handle_report))
        entry.async_on_unload(client.add_connection_listener(self._handle_connection))
        entry.async_on_unload(self._cancel_offline_timer)

    @property
    def input_count(self) -> int:
        """Number of inputs offered in the input selector."""
        return int(self.config_entry.options.get(CONF_INPUT_COUNT, DEFAULT_INPUT_COUNT))

    def _grace_remaining(self) -> timedelta:
        """Time left before silence makes the entities unavailable."""
        if self._last_contact is None:
            return timedelta(0)
        return max(timedelta(0), self._last_contact + UNAVAILABLE_AFTER - dt_util.utcnow())

    async def _async_update_data(self) -> LumagenState:
        try:
            if not self.client.connected:
                raise LumagenConnectionError("Not connected to the processor")
            state = await self.client.refresh()
            memory = state.current_memory
            if state.power and memory and memory not in self._labeled_memories:
                await self.client.refresh_labels(memory, self.input_count)
                self._labeled_memories.add(memory)
        except LumagenError as err:
            if self._grace_remaining():
                LOGGER.debug("No answer from the processor (%s); keeping the last state", err)
                return self.client.state
            raise UpdateFailed(f"Processor did not respond: {err}") from err
        self._last_contact = dt_util.utcnow()
        return state

    @callback
    def _handle_report(self, message: Message) -> None:
        """Push unsolicited reports (Report mode changes / Echo off with status)."""
        self._last_contact = dt_util.utcnow()
        self.async_set_updated_data(self.client.state)

    @callback
    def _handle_connection(self, connected: bool) -> None:
        self._cancel_offline_timer()
        if connected:
            self._labeled_memories.clear()
            self.config_entry.async_create_background_task(
                self.hass, self.async_request_refresh(), "lumagen reconnect refresh"
            )
            return
        remaining = self._grace_remaining()
        if remaining:
            self._offline_timer = async_call_later(self.hass, remaining, self._async_went_offline)
        else:
            self._async_went_offline()

    @callback
    def _async_went_offline(self, _now: datetime | None = None) -> None:
        self._offline_timer = None
        if not self.client.connected:
            self.async_set_update_error(UpdateFailed("Connection to the processor lost"))

    @callback
    def _cancel_offline_timer(self) -> None:
        if self._offline_timer is not None:
            self._offline_timer()
            self._offline_timer = None
