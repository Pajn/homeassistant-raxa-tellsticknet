from typing import Any, Dict, List, Optional
from homeassistant import config_entries
from homeassistant.core import callback
import voluptuous as vol
import homeassistant.helpers.config_validation as cv

from .light import LIGHT_SCHEMA
from .const import DOMAIN, LOGGER

DEVICE_SCHEMA = vol.Schema(
    {
        vol.Required("name"): str,
        vol.Required("device_code"): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=67234433)
        ),
        vol.Required("group_code"): vol.All(vol.Coerce(int), vol.Range(min=0, max=15)),
        vol.Optional("dimmable", default=False): bool,
        vol.Optional("add_another"): cv.boolean,
    }
)


@callback
def configured_hosts(hass):
    """Return a set of the configured hosts."""
    return set(
        entry.data["host"] for entry in hass.config_entries.async_entries(DOMAIN)
    )


@config_entries.HANDLERS.register(DOMAIN)
class RaxaTellstickNetConfigFlow(config_entries.ConfigFlow):
    """Example config flow."""

    # The schema version of the entries that it creates
    # Home Assistant will call your migrate method if the version changes
    VERSION = 1

    data: Optional[Dict[str, Any]] = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        if self.data is None:
            self.data = {}
            self.data["lights"] = []

        if user_input is not None:
            # Input is valid, set data.
            self.data["lights"].append(
                {
                    "name": user_input["name"],
                    "device_code": user_input["device_code"],
                    "group_code": user_input["group_code"],
                    "dimmable": user_input["dimmable"],
                }
            )

            # If user ticked the box show this form again so they can add an
            # additional repo.
            if user_input.get("add_another", False):
                return await self.async_step_user()

            # User is done adding lights, create the config entry.
            return self.async_create_entry(title="Raxa TellstickNet", data=self.data)

        return self.async_show_form(
            step_id="user",
            data_schema=DEVICE_SCHEMA,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handles options flow for the component."""

    data: Optional[Dict[str, Any]] = None

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        if user_input is not None:
            if user_input["action"] == "remove_device":
                return await self.async_step_remove_device()
            return await self.async_step_add_device()

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required("action"): vol.In(["add_device", "remove_device"]),
                }
            ),
        )

    async def async_step_add_device(self, user_input: dict[str, Any] | None = None):
        if self.data is None:
            self.data = {}
            self.data["lights"] = []

        if user_input is not None:
            # Input is valid, set data.
            self.data["lights"].append(
                {
                    "name": user_input["name"],
                    "device_code": user_input["device_code"],
                    "group_code": user_input["group_code"],
                    "dimmable": user_input["dimmable"],
                }
            )

            # If user ticked the box show this form again so they can add an
            # additional repo.
            if user_input.get("add_another", False):
                return await self.async_step_add_device()

            # User is done adding lights, create the config entry.
            return self.async_create_entry(title="Raxa TellstickNet", data=self.data)

        return self.async_show_form(
            step_id="add_device",
            data_schema=DEVICE_SCHEMA,
        )

    async def async_step_remove_device(self, user_input: dict[str, Any] | None = None):
        pass
