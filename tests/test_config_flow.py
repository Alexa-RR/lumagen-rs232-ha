"""Config flow tests."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_DEVICE, CONF_HOST, CONF_PORT, CONF_PROTOCOL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lumagen.const import (
    CONF_CONNECTION_TYPE,
    CONF_INPUT_COUNT,
    CONNECTION_NETWORK,
    CONNECTION_USB,
    DOMAIN,
)

from .fake_lumagen import FakeLumagen

USB_DATA = {CONF_CONNECTION_TYPE: CONNECTION_USB, CONF_DEVICE: "/dev/serial/by-id/usb-FTDI"}


async def _start(hass: HomeAssistant, step: str) -> str:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": step}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == step
    return result["flow_id"]


async def test_usb_flow(hass: HomeAssistant, fake_lumagen: FakeLumagen) -> None:
    flow_id = await _start(hass, "usb")
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_DEVICE: "/dev/serial/by-id/usb-FTDI"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Lumagen RadiancePro"
    assert result["data"] == USB_DATA
    assert result["result"].unique_id == "1234"
    assert fake_lumagen.connect_calls[0] == ("/dev/serial/by-id/usb-FTDI", {"baudrate": 9600})
    await hass.config_entries.async_unload(result["result"].entry_id)


async def test_network_flow(hass: HomeAssistant, fake_lumagen: FakeLumagen) -> None:
    flow_id = await _start(hass, "network")
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_HOST: " 192.168.1.50 ", CONF_PORT: 3000.0, CONF_PROTOCOL: "rfc2217"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_CONNECTION_TYPE: CONNECTION_NETWORK,
        CONF_HOST: "192.168.1.50",
        CONF_PORT: 3000,
        CONF_PROTOCOL: "rfc2217",
    }
    assert fake_lumagen.connect_calls[0][0] == "rfc2217://192.168.1.50:3000"
    await hass.config_entries.async_unload(result["result"].entry_id)


async def test_cannot_connect_then_recover(hass: HomeAssistant, fake_lumagen: FakeLumagen) -> None:
    flow_id = await _start(hass, "usb")
    fake_lumagen.refuse_connections = True
    result = await hass.config_entries.flow.async_configure(flow_id, {CONF_DEVICE: "/dev/ttyUSB9"})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}

    fake_lumagen.refuse_connections = False
    result = await hass.config_entries.flow.async_configure(flow_id, {CONF_DEVICE: "/dev/ttyUSB0"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.config_entries.async_unload(result["result"].entry_id)


async def test_no_response(hass: HomeAssistant, fake_lumagen: FakeLumagen) -> None:
    fake_lumagen.silent = {"ZQS01"}
    flow_id = await _start(hass, "usb")
    result = await hass.config_entries.flow.async_configure(flow_id, {CONF_DEVICE: "/dev/ttyUSB0"})
    assert result["errors"] == {"base": "no_response"}


async def test_already_configured_port(hass: HomeAssistant, fake_lumagen: FakeLumagen) -> None:
    MockConfigEntry(domain=DOMAIN, unique_id="1234", data=USB_DATA).add_to_hass(hass)
    flow_id = await _start(hass, "usb")
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_DEVICE: USB_DATA[CONF_DEVICE]}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert fake_lumagen.connect_calls == []


async def test_moving_device_to_network_updates_entry(
    hass: HomeAssistant, fake_lumagen: FakeLumagen
) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id="1234", data=USB_DATA)
    entry.add_to_hass(hass)
    flow_id = await _start(hass, "network")
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_HOST: "pi.local", CONF_PORT: 2000, CONF_PROTOCOL: "socket"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_HOST] == "pi.local"
    assert entry.data[CONF_CONNECTION_TYPE] == CONNECTION_NETWORK


async def test_reconfigure(hass: HomeAssistant, fake_lumagen: FakeLumagen) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id="1234", data=USB_DATA)
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "network"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "pi.local", CONF_PORT: 2000, CONF_PROTOCOL: "socket"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_HOST] == "pi.local"
    await hass.async_block_till_done()
    await hass.config_entries.async_unload(entry.entry_id)


async def test_reconfigure_wrong_device(hass: HomeAssistant, fake_lumagen: FakeLumagen) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id="9999", data=USB_DATA)
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "network"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "pi.local", CONF_PORT: 2000, CONF_PROTOCOL: "socket"}
    )
    assert result["reason"] == "wrong_device"


async def test_options_flow(hass: HomeAssistant, fake_lumagen: FakeLumagen) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="1234", title="Lumagen RadiancePro", data=USB_DATA
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_INPUT_COUNT: 4.0}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options == {CONF_INPUT_COUNT: 4}
    state = hass.states.get("select.lumagen_radiancepro_input")
    assert state is not None
    assert len(state.attributes["options"]) == 4
    await hass.config_entries.async_unload(entry.entry_id)
