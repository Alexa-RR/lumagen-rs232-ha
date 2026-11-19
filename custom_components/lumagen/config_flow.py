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
from homeassistant.const import CONF_DEVICE
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SerialPortSelector,
)

from .const import CONF_INPUT_COUNT, DEFAULT_INPUT_COUNT, DOMAIN, LOGGER
from .coordinator import LumagenConfigEntry
from .pylumagen import Identity, LumagenConnectionError, LumagenTimeoutError, async_probe
from .pylumagen.commands import MAX_INPUTS

DATA_SCHEMA = probatio.Schema({probatio.Required(CONF_DEVICE): SerialPortSelector()})

# Outcome of _async_attempt_connect meaning the port opened but no Lumagen
# answered; this routes the user to the troubleshooting step.
RESULT_NO_RESPONSE = "no_response"


async def _async_attempt_connect(port: str) -> Identity | str:
    """Probe the processor at ``port``.

    Returns its identity on success, otherwise an outcome key: "cannot_connect"
    when the port could not be opened, RESULT_NO_RESPONSE when it opened but no
    Lumagen answered, or "unknown" for an unexpected error.
    """
    try:
        return await async_probe(port)
    except LumagenTimeoutError:
        return RESULT_NO_RESPONSE
    except LumagenConnectionError:
        return "cannot_connect"
    except Exception:
        LOGGER.exception("Unexpected error probing %s", port)
        return "unknown"


class LumagenConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up a Lumagen processor on a serial port or a network serial bridge."""

    VERSION = 1

    _user_input: dict[str, Any] | None = None

    @staticmethod
    @callback
    @override
    def async_get_options_flow(config_entry: LumagenConfigEntry) -> LumagenOptionsFlow:
        """Return the options flow."""
        return LumagenOptionsFlow()

    @override
    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the serial port."""
        errors: dict[str, str] = {}

        if user_input is not None:
            port = user_input[CONF_DEVICE].strip()
            # A configured port is held open by its entry, so probing it would fail.
            self._async_abort_entries_match({CONF_DEVICE: port})
            result = await _async_attempt_connect(port)
            if isinstance(result, Identity):
                await self.async_set_unique_id(_unique_id(result))
                self._abort_if_unique_id_configured(updates={CONF_DEVICE: port})
                return self.async_create_entry(title=_title(result), data={CONF_DEVICE: port})
            if result == RESULT_NO_RESPONSE:
                self._user_input = user_input
                return await self.async_step_troubleshoot()
            errors["base"] = result

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                DATA_SCHEMA, user_input or self._user_input or {}
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the serial port of an existing processor."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            port = user_input[CONF_DEVICE].strip()
            if port == entry.data[CONF_DEVICE]:
                # The running entry holds this port open, so it can't be probed.
                return self.async_update_reload_and_abort(entry)
            result = await _async_attempt_connect(port)
            if isinstance(result, Identity):
                await self.async_set_unique_id(_unique_id(result))
                self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(entry, data_updates={CONF_DEVICE: port})
            if result == RESULT_NO_RESPONSE:
                self._user_input = user_input
                return await self.async_step_troubleshoot()
            errors["base"] = result

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                DATA_SCHEMA, user_input or self._user_input or dict(entry.data)
            ),
            errors=errors,
        )

    async def async_step_troubleshoot(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Explain what to check after the processor did not answer."""
        if user_input is not None:
            if self.source == SOURCE_RECONFIGURE:
                return await self.async_step_reconfigure()
            return await self.async_step_user()

        return self.async_show_form(step_id="troubleshoot")


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
