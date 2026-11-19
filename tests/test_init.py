"""Setup, entity and command tests using the in-memory processor."""

from __future__ import annotations

from datetime import timedelta

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_DEVICE,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.lumagen.const import DOMAIN
from custom_components.lumagen.coordinator import UNAVAILABLE_AFTER

from .fake_lumagen import I24_NO_SOURCE, FakeLumagen

REMOTE = "remote.lumagen_radiancepro"
INPUT = "select.lumagen_radiancepro_input"
MEMORY = "select.lumagen_radiancepro_input_memory"
GAME_MODE = "switch.lumagen_radiancepro_game_mode"
SOURCE_RES = "sensor.lumagen_radiancepro_source_resolution"


@pytest.fixture
async def entry(hass: HomeAssistant, fake_lumagen: FakeLumagen) -> MockConfigEntry:
    """Set up the integration against the fake processor."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="1234",
        title="Lumagen RadiancePro",
        data={CONF_DEVICE: "/dev/ttyUSB0"},
    )
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    yield config_entry
    if config_entry.state is ConfigEntryState.LOADED:
        assert await hass.config_entries.async_unload(config_entry.entry_id)


async def _poll(hass: HomeAssistant) -> None:
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=16))
    await hass.async_block_till_done(wait_background_tasks=True)


def _state(hass: HomeAssistant, entity_id: str) -> str:
    state = hass.states.get(entity_id)
    assert state is not None, f"{entity_id} missing"
    return state.state


async def test_entities(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    assert entry.state is ConfigEntryState.LOADED
    assert _state(hass, REMOTE) == STATE_ON
    assert _state(hass, INPUT) == "3: Kaleidescape"
    assert hass.states.get(INPUT).attributes["options"][:2] == ["1: Apple TV", "2: Input 2A"]
    assert _state(hass, MEMORY) == "a"
    assert _state(hass, GAME_MODE) == STATE_OFF
    assert _state(hass, SOURCE_RES) == "2160p"
    assert float(_state(hass, "sensor.lumagen_radiancepro_source_frame_rate")) == 23.976
    assert float(_state(hass, "sensor.lumagen_radiancepro_source_aspect_ratio")) == 2.4
    assert _state(hass, "sensor.lumagen_radiancepro_output_colorspace") == "rec2100"
    assert _state(hass, "sensor.lumagen_radiancepro_input_status") == "active_video"
    assert _state(hass, "binary_sensor.lumagen_radiancepro_hdr") == STATE_ON
    assert _state(hass, "binary_sensor.lumagen_radiancepro_video_signal") == STATE_ON


async def test_commands(
    hass: HomeAssistant, entry: MockConfigEntry, fake_lumagen: FakeLumagen
) -> None:
    fake_lumagen.received = ""
    await hass.services.async_call(
        "select", "select_option", {ATTR_ENTITY_ID: INPUT, "option": "1: Apple TV"}, blocking=True
    )
    await hass.services.async_call(
        "select", "select_option", {ATTR_ENTITY_ID: MEMORY, "option": "c"}, blocking=True
    )
    await hass.services.async_call("switch", "turn_on", {ATTR_ENTITY_ID: GAME_MODE}, blocking=True)
    await hass.services.async_call(
        "remote",
        "send_command",
        {ATTR_ENTITY_ID: REMOTE, "command": ["menu", "down", "ZY530K1KK\r"], "delay_secs": 0},
        blocking=True,
    )
    assert "i1" in fake_lumagen.received
    assert "c" in fake_lumagen.received
    assert "ZY5511\r" in fake_lumagen.received
    assert "MvZY530K1KK\r" in fake_lumagen.received
    await _poll(hass)
    assert _state(hass, MEMORY) == "c"
    assert _state(hass, GAME_MODE) == STATE_ON


async def test_standby_and_wake(
    hass: HomeAssistant, entry: MockConfigEntry, fake_lumagen: FakeLumagen
) -> None:
    await hass.services.async_call("remote", "turn_off", {ATTR_ENTITY_ID: REMOTE}, blocking=True)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert fake_lumagen.power is False
    assert _state(hass, REMOTE) == STATE_OFF
    # Video entities are unavailable in standby; the remote stays usable.
    assert _state(hass, SOURCE_RES) == STATE_UNAVAILABLE
    assert _state(hass, INPUT) == STATE_UNAVAILABLE

    await hass.services.async_call("remote", "turn_on", {ATTR_ENTITY_ID: REMOTE}, blocking=True)
    await hass.async_block_till_done(wait_background_tasks=True)
    # Power is shown as on immediately; video status follows on the next poll.
    assert _state(hass, REMOTE) == STATE_ON
    await _poll(hass)
    assert _state(hass, SOURCE_RES) == "2160p"


async def test_unsolicited_report_updates_entities(
    hass: HomeAssistant, entry: MockConfigEntry, fake_lumagen: FakeLumagen
) -> None:
    fake_lumagen.push(I24_NO_SOURCE)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert _state(hass, "sensor.lumagen_radiancepro_input_status") == "no_source"
    assert _state(hass, "binary_sensor.lumagen_radiancepro_video_signal") == STATE_OFF


async def test_short_connection_drop_stays_available(
    hass: HomeAssistant, entry: MockConfigEntry, fake_lumagen: FakeLumagen
) -> None:
    # e.g. ser2net handing the port to another client for a moment
    fake_lumagen.drop_connection()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert _state(hass, REMOTE) == STATE_ON
    for _ in range(20):
        await hass.async_block_till_done(wait_background_tasks=True)
        if entry.runtime_data.client.connected:
            break
    assert entry.runtime_data.client.connected
    assert _state(hass, REMOTE) == STATE_ON


async def test_connection_loss_and_recovery(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    fake_lumagen: FakeLumagen,
    freezer: FrozenDateTimeFactory,
) -> None:
    fake_lumagen.refuse_connections = True
    fake_lumagen.drop_connection()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert _state(hass, REMOTE) == STATE_ON  # within the grace period

    freezer.tick(UNAVAILABLE_AFTER + timedelta(seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert _state(hass, REMOTE) == STATE_UNAVAILABLE

    fake_lumagen.refuse_connections = False
    for _ in range(20):
        await hass.async_block_till_done(wait_background_tasks=True)
        if _state(hass, REMOTE) == STATE_ON:
            break
    assert _state(hass, REMOTE) == STATE_ON


async def test_silent_while_booting_stays_available(
    hass: HomeAssistant, entry: MockConfigEntry, fake_lumagen: FakeLumagen
) -> None:
    coordinator = entry.runtime_data
    coordinator.client._query_timeout = 0.05
    # The Radiance ignores queries for a while after power-on.
    fake_lumagen.silent = {"ZQS02"}
    await _poll(hass)
    assert _state(hass, REMOTE) == STATE_ON
    assert _state(hass, SOURCE_RES) == "2160p"

    # Still silent once the grace period has passed: now it is unavailable.
    coordinator._last_contact -= UNAVAILABLE_AFTER
    await _poll(hass)
    assert _state(hass, REMOTE) == STATE_UNAVAILABLE

    fake_lumagen.silent = set()
    await _poll(hass)
    assert _state(hass, REMOTE) == STATE_ON


async def test_setup_retries_when_port_missing(
    hass: HomeAssistant, fake_lumagen: FakeLumagen
) -> None:
    fake_lumagen.refuse_connections = True
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="1234",
        data={CONF_DEVICE: "/dev/ttyUSB0"},
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_retries_when_processor_silent(
    hass: HomeAssistant, fake_lumagen: FakeLumagen
) -> None:
    fake_lumagen.silent = {"ZQS01", "ZQS02"}
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="1234",
        data={CONF_DEVICE: "/dev/ttyUSB0"},
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY
