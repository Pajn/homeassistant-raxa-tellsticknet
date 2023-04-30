"""Raxa TellstickNet integration."""
import ipaddress
import logging

import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN

# Loading the config flow file will register the flow
from .config_flow import configured_hosts

REQUIREMENTS = []

_LOGGER = logging.getLogger(__name__)

CONF_BRIDGES = "bridges"

BRIDGE_CONFIG_SCHEMA = vol.Schema(
    {
        # Validate as IP address and then convert back to a string.
        vol.Required(CONF_HOST): vol.All(ipaddress.ip_address, cv.string),
    }
)

# CONFIG_SCHEMA = vol.Schema(
#     {
#         DOMAIN: vol.Schema(
#             {
#                 vol.Optional(CONF_BRIDGES): vol.All(
#                     cv.ensure_list, [BRIDGE_CONFIG_SCHEMA]
#                 ),
#             }
#         ),
#     },
#     extra=vol.ALLOW_EXTRA,
# )


# async def async_setup(hass, config):
#     """Set up the Hue platform."""
#     conf = config.get(DOMAIN)
#     if conf is None:
#         conf = {}

#     hass.data[DOMAIN] = {}
#     configured = configured_hosts(hass)

#     # User has configured bridges
#     if CONF_BRIDGES in conf:
#         bridges = conf[CONF_BRIDGES]

#     # Component is part of config but no bridges specified, discover.
#     elif DOMAIN in config:
#         # discover from nupnp
#         websession = aiohttp_client.async_get_clientsession(hass)

#         async with websession.get(API_NUPNP) as req:
#             hosts = await req.json()

#         bridges = []
#         for entry in hosts:
#             # Filter out already configured hosts
#             if entry["internalipaddress"] in configured:
#                 continue

#             # Run through config schema to populate defaults
#             bridges.append(
#                 BRIDGE_CONFIG_SCHEMA(
#                     {
#                         CONF_HOST: entry["internalipaddress"],
#                         # Careful with using entry['id'] for other reasons. The
#                         # value is in lowercase but is returned uppercase from hub.
#                         CONF_FILENAME: ".hue_{}.conf".format(entry["id"]),
#                     }
#                 )
#             )
#     else:
#         # Component not specified in config, we're loaded via discovery
#         bridges = []

#     if not bridges:
#         return True

#     for bridge_conf in bridges:
#         host = bridge_conf[CONF_HOST]

#         # Store config in hass.data so the config entry can find it
#         hass.data[DOMAIN][host] = bridge_conf

#         # If configured, the bridge will be set up during config entry phase
#         if host in configured:
#             continue

#         # No existing config entry found, try importing it or trigger link
#         # config flow if no existing auth. Because we're inside the setup of
#         # this component we'll have to use hass.async_add_job to avoid a
#         # deadlock: creating a config entry will set up the component but the
#         # setup would block till the entry is created!
#         hass.async_add_job(
#             hass.config_entries.flow.async_init(
#                 DOMAIN,
#                 source="import",
#                 data={
#                     "host": bridge_conf[CONF_HOST],
#                     "path": bridge_conf[CONF_FILENAME],
#                 },
#             )
#         )

#     return True


# async def async_setup_entry(hass, entry):
#     """Set up a bridge from a config entry."""
#     host = entry.data["host"]
#     config = hass.data[DOMAIN].get(host)

#     if config is None:
#         allow_unreachable = DEFAULT_ALLOW_UNREACHABLE
#         allow_groups = DEFAULT_ALLOW_HUE_GROUPS
#     else:
#         allow_unreachable = config[CONF_ALLOW_UNREACHABLE]
#         allow_groups = config[CONF_ALLOW_HUE_GROUPS]

#     bridge = HueBridge(hass, entry, allow_unreachable, allow_groups)
#     hass.data[DOMAIN][host] = bridge
#     return await bridge.async_setup()


# async def async_unload_entry(hass, entry):
#     """Unload a config entry."""
#     bridge = hass.data[DOMAIN].pop(entry.data["host"])
#     return await bridge.async_reset()


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Raxa TellstickNet component from yaml configuration."""
    hass.data.setdefault(DOMAIN, {})

    # Forward the setup to the light platform.
    # hass.async_create_task(hass.config_entries.async_setup_platforms(config, ["light"]))
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up platform from a ConfigEntry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry.data

    # Forward the setup to the light platform.
    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(entry, "light")
    )

    hass_data = dict(entry.data)
    # Registers update listener to update config entry when options are updated.
    unsub_options_update_listener = entry.add_update_listener(options_update_listener)
    # Store a reference to the unsubscribe function to cleanup if an entry is unloaded.
    hass_data["unsub_options_update_listener"] = unsub_options_update_listener
    hass.data[DOMAIN][entry.entry_id] = hass_data

    return True


async def options_update_listener(hass: HomeAssistant, config_entry: ConfigEntry):
    """Handle options update."""
    await hass.config_entries.async_reload(config_entry.entry_id)
