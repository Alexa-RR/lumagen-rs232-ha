"""Config flow for the Lumagen integration."""

from __future__ import annotations

from typing import Any, override

import probatio
from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_DEVICE, CONF_HOST, CONF_PORT, CONF_PROTOCOL
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    SerialPortSelector,
    TextSelector,
)

from .const import (
    CONF_CONNECTION_TYPE,
    CONF_INPUT_COUNT,
    CONNECTION_NETWORK,
    CONNECTION_USB,
    DEFAULT_INPUT_COUNT,
    DEFAULT_NETWORK_PORT,
    DOMAIN,
    LOGGER,
    PROTOCOL_RFC2217,
    PROTOCOL_SOCKET,
    build_url,
)
from .coordinator import LumagenConfigEntry
from .pylumagen import Identity, LumagenConnectionError, LumagenTimeoutError, async_probe
from .pylumagen.commands import MAX_INPUTS

USB_SCHEMA = probatio.Schema({probatio.Required(CONF_DEVICE): SerialPortSelector()})

NETWORK_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_HOST): TextSelector(),
        probatio.Required(CONF_PORT, default=DEFAULT_NETWORK_PORT): NumberSelector(
            NumberSelectorConfig(min=1, max=65535, mode=NumberSelectorMode.BOX)
        ),
        probatio.Required(CONF_PROTOCOL, default=PROTOCOL_SOCKET): SelectSelector(
            SelectSelectorConfig(
                options=[PROTOCOL_SOCKET, PROTOCOL_RFC2217],
                mode=SelectSelectorMode.LIST,
                translation_key="protocol",
            )
        ),
    }
)


class LumagenConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up a Lumagen processor over USB serial or a network serial bridge."""

    VERSION = 1

    @staticmethod
    @callback
    @override
    def async_get_options_flow(config_entry: LumagenConfigEntry) -> LumagenOptionsFlow:
        """Return the options flow."""
        return LumagenOptionsFlow()

    @override
    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask how the processor is connected."""
        return self.async_show_menu(
            step_id="user", menu_options=[CONNECTION_USB, CONNECTION_NETWORK]
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change how an existing processor is connected."""
        return self.async_show_menu(
            step_id="reconfigure", menu_options=[CONNECTION_USB, CONNECTION_NETWORK]
        )

    async def async_step_usb(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Connect through a serial port on the Home Assistant host."""
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {CONF_CONNECTION_TYPE: CONNECTION_USB, CONF_DEVICE: user_input[CONF_DEVICE]}
            result = await self._async_validate_and_finish(data, errors)
            if result is not None:
                return result
        return self.async_show_form(
            step_id="usb",
            data_schema=self.add_suggested_values_to_schema(USB_SCHEMA, user_input or {}),
            errors=errors,
        )

    async def async_step_network(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Connect through a network serial bridge such as ser2net on a Raspberry Pi."""
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {
                CONF_CONNECTION_TYPE: CONNECTION_NETWORK,
                CONF_HOST: user_input[CONF_HOST].strip(),
                CONF_PORT: int(user_input[CONF_PORT]),
                CONF_PROTOCOL: user_input[CONF_PROTOCOL],
            }
            result = await self._async_validate_and_finish(data, errors)
            if result is not None:
                return result
        return self.async_show_form(
            step_id="network",
            data_schema=self.add_suggested_values_to_schema(NETWORK_SCHEMA, user_input or {}),
            errors=errors,
        )

    async def _async_validate_and_finish(
        self, data: dict[str, Any], errors: dict[str, str]
    ) -> ConfigFlowResult | None:
        """Probe the processor; return a result on success or fill ``errors``."""
        url = build_url(data)
        if self.source == SOURCE_RECONFIGURE:
            entry = self._get_reconfigure_entry()
            if build_url(dict(entry.data)) == url:
                # The running entry holds this port open, so it can't be probed.
                return self.async_update_reload_and_abort(entry, data_updates=data)
        else:
            # Same reason: an already configured port would fail the probe.
            self._async_abort_entries_match(
                {CONF_DEVICE: data[CONF_DEVICE]}
                if data[CONF_CONNECTION_TYPE] == CONNECTION_USB
                else {CONF_HOST: data[CONF_HOST], CONF_PORT: data[CONF_PORT]}
            )
        try:
            identity = await async_probe(url)
        except LumagenConnectionError:
            errors["base"] = "cannot_connect"
            return None
        except LumagenTimeoutError:
            errors["base"] = "no_response"
            return None
        except Exception:
            LOGGER.exception("Unexpected error probing %s", url)
            errors["base"] = "unknown"
            return None

        await self.async_set_unique_id(_unique_id(identity))
        if self.source == SOURCE_RECONFIGURE:
            self._abort_if_unique_id_mismatch(reason="wrong_device")
            return self.async_update_reload_and_abort(
                self._get_reconfigure_entry(), data_updates=data
            )
        self._abort_if_unique_id_configured(updates=data)
        return self.async_create_entry(title=_title(identity), data=data)


def _unique_id(identity: Identity) -> str:
    return identity.serial_number or f"{identity.model_number}-{identity.model_name}"


def _title(identity: Identity) -> str:
    name = identity.model_name or "Radiance"
    return f"Lumagen {name}"


class LumagenOptionsFlow(OptionsFlowWithReload):
    """Options: how many inputs to offer in the input selector."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(
                data={CONF_INPUT_COUNT: int(user_input[CONF_INPUT_COUNT])}
            )
        schema = probatio.Schema(
            {
                probatio.Required(CONF_INPUT_COUNT): NumberSelector(
                    NumberSelectorConfig(min=1, max=MAX_INPUTS, mode=NumberSelectorMode.BOX)
                )
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                schema,
                {
                    CONF_INPUT_COUNT: self.config_entry.options.get(
                        CONF_INPUT_COUNT, DEFAULT_INPUT_COUNT
                    )
                },
            ),
        )
