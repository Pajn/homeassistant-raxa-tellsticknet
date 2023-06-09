"""Platform for light integration."""
from __future__ import annotations
from datetime import timedelta

import socket
import threading
import async_timeout
from typing import Any, List, Optional

import voluptuous as vol
from .const import DOMAIN, LOGGER

# Import the device class from the component that you want to support
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    PLATFORM_SCHEMA,
    LightEntity,
    ColorMode,
)
from homeassistant import config_entries, core
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType


# Validation of the user's configuration
LIGHT_SCHEMA = vol.Schema(
    {
        vol.Required("name"): str,
        vol.Required("device_code"): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=67234433)
        ),
        vol.Required("group_code"): vol.All(vol.Coerce(int), vol.Range(min=0, max=15)),
        vol.Optional("dimmable", default=False): bool,
    }
)

# Validation of the user's configuration
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required("lights"): vol.All(cv.ensure_list, [LIGHT_SCHEMA]),
    }
)

COMMUNICATION_PORT = 42314
BROADCAST_PORT = 30303

tellstick: TellstickNet | None = None


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    LOGGER.warn("light setup_platform")
    global tellstick
    if tellstick is None:
        tellstick = TellstickNet(hass)
        async with async_timeout.timeout(30):
            await hass.async_add_executor_job(lambda: tellstick.start())
    lights = [NexaSelfLearningLight(tellstick, light) for light in config["lights"]]
    add_entities(lights)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    add_entities: AddEntitiesCallback,
):
    """Set up entry."""
    config = hass.data[DOMAIN][config_entry.entry_id]
    if config_entry.options:
        config.update(config_entry.options)
    LOGGER.warn("light async_setup_entry %s", config)
    global tellstick
    if tellstick is None:
        tellstick = TellstickNet(hass)
        async with async_timeout.timeout(30):
            await hass.async_add_executor_job(lambda: tellstick.start())
    lights = [NexaSelfLearningLight(tellstick, light) for light in config["lights"]]
    add_entities(lights)


class TellstickNet:
    """Communicates with the tellsticks"""

    tellsticks: set[socket.socket] = set()

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._run_event = threading.Event()
        self._thread = threading.Thread(target=self.listen, daemon=True)

    def start(self) -> None:
        LOGGER.debug("TellstickNet starting")
        self._thread.start()
        LOGGER.debug("  Thread started")
        self._run_event.wait()
        LOGGER.debug("  Event set")
        self.discover()
        LOGGER.debug("  Discovered")

    def listen(self):
        LOGGER.debug("starting listen")
        self._sock = socket.socket(
            socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP
        )
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("0.0.0.0", COMMUNICATION_PORT))
        LOGGER.debug("started listening")

        self._run_event.set()

        while self._run_event.is_set():
            (data, addr) = self._sock.recvfrom(1024)
            message = data.decode()
            LOGGER.debug("Received %r from %s" % (message, addr))
            if message.startswith("TellStickNet"):
                _header, mac, activation_code, version = message.split(":")
                LOGGER.debug("Found tellstick: {mac} {activation_code} {version}")
                self._hass.bus.fire(
                    "raxa_tellsticknet_event",
                    {
                        "mac": mac,
                        "activation_code": activation_code,
                        "version": version,
                        "type": "tellstick_detected",
                    },
                )
            elif message.startswith("TSNETRC") and not message.endswith("data:;\r\n"):
                self._hass.bus.fire(
                    "raxa_tellsticknet_event",
                    {
                        "data": message.removeprefix("TSNETRC").removesuffix("\r\n"),
                        "type": "message_received",
                    },
                )
            ip, port = addr
            self.tellsticks.add(ip)

    def stop(self):
        self._run_event.clear()
        self._sock.close()
        self._thread.join()

    def discover(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.sendto(b"D", ("255.255.255.255", BROADCAST_PORT))

    def send(self, message: bytes, repeats=8, pause=15):
        buffer = (
            b"4:sendh1:S"
            + bytes(hex(len(message))[2:].upper(), "latin1")
            + b":"
            + message
            + b"1:Pi"
            + bytes(hex(pause)[2:].upper(), "latin1")
            + b"s1:Ri"
            + bytes(hex(repeats)[2:].upper(), "latin1")
            + b"ss"
        )
        LOGGER.warn("light send %s", str(buffer))
        for ip in self.tellsticks:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.sendto(buffer, (ip, COMMUNICATION_PORT))


class NexaSelfLearningLight(LightEntity):
    def __init__(self, tellstick: TellstickNet, light) -> None:
        self._tellstick = tellstick
        self._name = light["name"]
        self._unique_id = "{}::{}".format(light["device_code"], light["group_code"])
        self._device_code = light["device_code"]
        self._group_code = light["group_code"]
        self._dimmable = light["dimmable"]
        self._state = None
        self._brightness = None
        LOGGER.debug("NexaSelfLearningLight {self._name}")

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={
                # Serial numbers are unique identifiers within a specific domain
                (DOMAIN, self._unique_id)
            },
            name=self.name,
            manufacturer="Nexa",
            model="selflearning",
            # via_device=(DOMAIN, self.api.bridgeid),
        )

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return self._unique_id

    @property
    def assumed_state(self) -> str:
        return True

    @property
    def name(self) -> str:
        """Return the display name of this light."""
        return self._name

    @property
    def supported_color_modes(self) -> set[ColorMode]:
        if self._dimmable:
            return {ColorMode.ONOFF, ColorMode.BRIGHTNESS}
        return {ColorMode.ONOFF}

    @property
    def brightness(self):
        """Return the brightness of the light.

        This method is optional. Removing it indicates to Home Assistant
        that brightness is not supported for this light.
        """
        return self._brightness

    @property
    def is_on(self) -> bool | None:
        """Return true if light is on."""
        return self._state

    def turn_on(self, **kwargs: Any) -> None:
        """Instruct the light to turn on.

        You can skip the brightness part if your light does not support
        brightness control.
        """
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        # self._light.turn_on()
        if brightness is None:
            self._tellstick.send(
                self_learning_pulse(self._device_code, False, self._group_code, ON)
            )
        else:
            self._tellstick.send(
                self_learning_pulse(
                    self._device_code,
                    False,
                    self._group_code,
                    DIM,
                    int(brightness / 256.0 * 16),
                )
            )
        self._state = True
        self._brightness = brightness

    def turn_off(self, **kwargs: Any) -> None:
        """Instruct the light to turn off."""
        self._tellstick.send(
            self_learning_pulse(self._device_code, False, self._group_code, OFF)
        )
        self._state = False

    # def update(self) -> None:
    #     """Fetch new state data for this light.

    #     This is the only method that should fetch new data for Home Assistant.
    #     """
    #     self._light.update()
    #     self._state = self._light.is_on()
    #     self._brightness = self._light.brightness


OFF = 0
ON = 1
DIM = 2


def self_learning_pulse(
    device_code: int,
    group_mode: bool,
    group_code: int,
    action: int,
    dim_level: Optional[int] = None,
) -> bytes:
    T = 26
    T5 = T * 5
    ZERO = bytes([T, T, T, T5])
    ONE = bytes([T, T5, T, T])
    DIM_BIT = bytes([T, T, T, T])

    pulse = bytes([T, 254])

    for i in range(25, -1, -1):
        if (device_code & (1 << i)) == 0:
            pulse += ZERO
        else:
            pulse += ONE

    if group_mode:
        pulse += ONE
    else:
        pulse += ZERO

    if action == ON:
        pulse += ONE
    elif action == OFF:
        pulse += ZERO
    elif action == DIM:
        pulse += DIM_BIT

    for i in range(3, -1, -1):
        if (group_code & (1 << i)) == 0:
            pulse += ZERO
        else:
            pulse += ONE

    if action == DIM:
        for i in range(3, -1, -1):
            if (dim_level & (1 << i)) == 0:
                pulse += ZERO
            else:
                pulse += ONE

    pulse += bytes([T, 255])

    return pulse
