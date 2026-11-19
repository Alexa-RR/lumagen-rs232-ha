"""Config flow tests."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_DEVICE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lumagen.const import CONF_INPUT_COUNT, DOMAIN

from .fake_lumagen import FakeLumagen

USB_PORT = "/dev/serial/by-id/usb-FTDI"
USB_DATA = {CONF_DEVICE: USB_PORT}


async def _start(hass: HomeAssistant) -> str:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    return result["flow_id"]


async def test_usb_port(hass: HomeAssistant, fake_lumagen: FakeLumagen) -> None:
    flow_id = await _start(hass)
    result = await hass.config_entries.flow.async_configure(flow_id, {CONF_DEVICE: USB_PORT})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Lumagen RadiancePro"
    assert result["data"] == USB_DATA
    assert result["result"].unique_id == "1234"
    assert fake_lumagen.connect_calls[0] == (USB_PORT, {"baudrate": 9600})
    await hass.config_entries.async_unload(result["result"].entry_id)


async def test_network_bridge_url(hass: HomeAssistant, fake_lumagen: FakeLumagen) -> None:
    flow_id = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_DEVICE: " socket://192.168.1.50:2000 "}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_DEVICE: "socket://192.168.1.50:2000"}
    assert fake_lumagen.connect_calls[0][0] == "socket://192.168.1.50:2000"
    await hass.config_entries.async_unload(result["result"].entry_id)


async def test_cannot_connect_then_recover(hass: HomeAssistant, fake_lumagen: FakeLumagen) -> None:
    flow_id = await _start(hass)
    fake_lumagen.refuse_connections = True
    result = await hass.config_entries.flow.async_configure(flow_id, {CONF_DEVICE: "/dev/ttyUSB9"})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "cannot_connect"}

    fake_lumagen.refuse_connections = False
    result = await hass.config_entries.flow.async_configure(flow_id, {CONF_DEVICE: "/dev/ttyUSB0"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.config_entries.async_unload(result["result"].entry_id)


async def test_no_response_troubleshoot_then_retry(
    hass: HomeAssistant, fake_lumagen: FakeLumagen
) -> None:
    fake_lumagen.silent = {"ZQS01"}
    flow_id = await _start(hass)
    result = await hass.config_entries.flow.async_configure(flow_id, {CONF_DEVICE: "/dev/ttyUSB0"})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "troubleshoot"

    # Submitting the troubleshooting page goes back to the form, prefilled.
    result = await hass.config_entries.flow.async_configure(flow_id, {})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    schema_key = next(iter(result["data_schema"].schema))
    assert schema_key.description == {"suggested_value": "/dev/ttyUSB0"}

    fake_lumagen.silent = set()
    result = await hass.config_entries.flow.async_configure(flow_id, {CONF_DEVICE: "/dev/ttyUSB0"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.config_entries.async_unload(result["result"].entry_id)


async def test_already_configured_port(hass: HomeAssistant, fake_lumagen: FakeLumagen) -> None:
    MockConfigEntry(domain=DOMAIN, unique_id="1234", data=USB_DATA).add_to_hass(hass)
    flow_id = await _start(hass)
    result = await hass.config_entries.flow.async_configure(flow_id, {CONF_DEVICE: USB_PORT})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert fake_lumagen.connect_calls == []


async def test_same_processor_on_new_port_updates_entry(
    hass: HomeAssistant, fake_lumagen: FakeLumagen
) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id="1234", data=USB_DATA)
    entry.add_to_hass(hass)
    flow_id = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_DEVICE: "socket://pi.local:2000"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data == {CONF_DEVICE: "socket://pi.local:2000"}


async def test_reconfigure(hass: HomeAssistant, fake_lumagen: FakeLumagen) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id="1234", data=USB_DATA)
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICE: "rfc2217://pi.local:2000"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data == {CONF_DEVICE: "rfc2217://pi.local:2000"}
    await hass.async_block_till_done()
    await hass.config_entries.async_unload(entry.entry_id)


async def test_reconfigure_same_port_skips_probe(
    hass: HomeAssistant, fake_lumagen: FakeLumagen
) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id="1234", data=USB_DATA)
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICE: USB_PORT}
    )
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    # Only the reload connected; the flow itself did not probe.
    assert all(call[0] == USB_PORT for call in fake_lumagen.connect_calls)
    await hass.config_entries.async_unload(entry.entry_id)


async def test_reconfigure_no_response_returns_to_reconfigure(
    hass: HomeAssistant, fake_lumagen: FakeLumagen
) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id="1234", data=USB_DATA)
    entry.add_to_hass(hass)
    fake_lumagen.silent = {"ZQS01"}
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICE: "socket://pi.local:2000"}
    )
    assert result["step_id"] == "troubleshoot"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["step_id"] == "reconfigure"


async def test_reconfigure_wrong_device(hass: HomeAssistant, fake_lumagen: FakeLumagen) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id="9999", data=USB_DATA)
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICE: "socket://pi.local:2000"}
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
