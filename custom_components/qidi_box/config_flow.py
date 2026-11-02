"""Config flow: pick the Moonraker printer the Box is attached to."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
)

from . import client_for
from .api import MoonrakerError
from .const import (
    CONF_MOONRAKER_ENTRY_ID,
    CONF_POLLING_RATE,
    DEFAULT_POLLING_RATE,
    DOMAIN,
    MAX_POLLING_RATE,
    MIN_POLLING_RATE,
    MOONRAKER_DOMAIN,
)
from .parse import has_box


class QidiBoxConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add a QIDI Box to a printer of the Moonraker integration."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose the printer."""
        configured = {
            entry.data.get(CONF_MOONRAKER_ENTRY_ID)
            for entry in self._async_current_entries(include_ignore=False)
        }
        printers = [
            entry
            for entry in self.hass.config_entries.async_entries(MOONRAKER_DOMAIN)
            if entry.entry_id not in configured
        ]
        if not printers:
            return self.async_abort(reason="no_printers")

        errors: dict[str, str] = {}
        if user_input is not None:
            moonraker_entry = self.hass.config_entries.async_get_entry(
                user_input[CONF_MOONRAKER_ENTRY_ID]
            )
            if moonraker_entry is None:
                errors["base"] = "unknown_printer"
            elif moonraker_entry.state is not ConfigEntryState.LOADED:
                errors["base"] = "printer_not_loaded"
            else:
                try:
                    objects = await client_for(
                        self.hass, moonraker_entry
                    ).objects_list()
                except MoonrakerError:
                    errors["base"] = "cannot_connect"
                else:
                    if not has_box(objects):
                        errors["base"] = "no_box"
            if not errors:
                await self.async_set_unique_id(moonraker_entry.entry_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"QIDI Box ({moonraker_entry.title})",
                    data={CONF_MOONRAKER_ENTRY_ID: moonraker_entry.entry_id},
                )

        options = [
            SelectOptionDict(value=entry.entry_id, label=entry.title)
            for entry in printers
        ]
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_MOONRAKER_ENTRY_ID, default=printers[0].entry_id
                    ): SelectSelector(SelectSelectorConfig(options=options))
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return QidiBoxOptionsFlow()


class QidiBoxOptionsFlow(OptionsFlow):
    """How often to poll while nothing happens."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Set the polling rate."""
        if user_input is not None:
            return self.async_create_entry(
                data={CONF_POLLING_RATE: int(user_input[CONF_POLLING_RATE])}
            )
        current = self.config_entry.options.get(CONF_POLLING_RATE, DEFAULT_POLLING_RATE)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_POLLING_RATE, default=current): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_POLLING_RATE,
                            max=MAX_POLLING_RATE,
                            step=1,
                            unit_of_measurement="s",
                            mode=NumberSelectorMode.BOX,
                        )
                    )
                }
            ),
        )
