"""Support for Owlet switches."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import timedelta
import json
from typing import Any

from pyowletapi.sock import Sock

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import OwletCoordinator
from .entity import OwletBaseEntity

SCAN_INTERVAL = timedelta(seconds=5)
PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class OwletSwitchEntityDescription(SwitchEntityDescription):
    """Describes Owlet switch entity."""

    turn_on_fn: Callable[[Sock], Callable[[bool], Coroutine[Any, Any, None]]]
    turn_off_fn: Callable[[Sock], Callable[[bool], Coroutine[Any, Any, None]]]
    available_during_charging: bool


SWITCHES: tuple[OwletSwitchEntityDescription, ...] = (
    OwletSwitchEntityDescription(
        key="base_station_on",
        translation_key="base_on",
        turn_on_fn=lambda sock: (lambda state: sock.control_base_station(state)),
        turn_off_fn=lambda sock: (lambda state: sock.control_base_station(state)),
        available_during_charging=False,
    ),
    OwletSwitchEntityDescription(
        key="mon_recovery",
        translation_key="recovery_mode",
        turn_on_fn=lambda sock: sock.control_recovery_mode(True),
        turn_off_fn=lambda sock: sock.control_recovery_mode(False),
        available_during_charging=True,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Owlet switch based on a config entry."""
    coordinators: OwletCoordinator = hass.data[DOMAIN][config_entry.entry_id].values()

    switches = []
    for coordinator in coordinators:
        switches.extend([OwletBaseSwitch(coordinator, switch) for switch in SWITCHES])
        switches.append(OwletRecoveryModeSwitch(coordinator))
    async_add_entities(switches)


# class OwletRecoveryModeSwitch(OwletBaseEntity, SwitchEntity):
#     """Switch entity to monitor and control Owlet recovery mode."""

#     _attr_has_entity_name = True
#     _attr_name = "Recovery Mode"
#     _attr_icon = "mdi:shield-refresh"

#     def __init__(self, coordinator: OwletCoordinator) -> None:
#         super().__init__(coordinator)
#         self._attr_unique_id = f"{self.sock.serial}_recovery_mode"

#     @property
#     def is_on(self) -> bool:
#         """Return True if recovery mode is currently active."""
#         response = self.sock.raw_properties.get("APP_CMD_RESPONSE", {})
#         value = response.get("value", "")
#         if isinstance(value, str):
#             try:
#                 value = json.loads(value)
#             except json.JSONDecodeError:
#                 return value.lower() == "true"
#         if isinstance(value, dict):
#             return str(value.get("val", "")).lower() == "true"
#         return False

#     async def _set_recovery_mode(self, enabled: bool) -> None:
#         """Set recovery mode and refresh the current device state."""
#         payload = json.dumps(
#             {"cmd": "mon_recovery", "val": "true" if enabled else "false"},
#             separators=(",", ":"),
#         )
#         await self.sock._api.post_command(
#             self.sock.serial,
#             "APP_CMD_REQUEST",
#             {"datapoint": {"metadata": {}, "value": payload}},
#         )
#         await self.coordinator.async_request_refresh()

#     async def async_turn_on(self, **kwargs: Any) -> None:
#         """Enable recovery mode."""
#         await self._set_recovery_mode(True)

#     async def async_turn_off(self, **kwargs: Any) -> None:
#         """Disable recovery mode."""
#         await self._set_recovery_mode(False)

class OwletBaseSwitch(OwletBaseEntity, SwitchEntity):
    """Defines a Owlet switch."""

    entity_description: OwletSwitchEntityDescription

    def __init__(
        self,
        coordinator: OwletCoordinator,
        description: OwletSwitchEntityDescription,
    ) -> None:
        """Initialize owlet switch platform."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{self.sock.serial}-{description.key}"
        self._attr_is_on = False

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return super().available and (
            not self.sock.properties["charging"]
            or self.entity_description.available_during_charging
        )

    @property
    def is_on(self) -> bool:
        """Return if switch is on or off."""
        return self.sock.properties[self.entity_description.key]

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the switch."""
        await self.entity_description.turn_on_fn(self.sock)(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the switch."""
        await self.entity_description.turn_off_fn(self.sock)(False)

class OwletRecoverySwitch(OwletBaseEntity, SwitchEntity):
    """Defines a Owlet Recovery switch."""

    entity_description: OwletSwitchEntityDescription

    def __init__(
        self,
        coordinator: OwletCoordinator,
        description: OwletSwitchEntityDescription,
    ) -> None:
        """Initialize owlet switch platform."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{self.sock.serial}-{description.key}"
        self._attr_is_on = False

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return super().available and (
            not self.sock.properties["charging"]
            or self.entity_description.available_during_charging
        )

    @property
    def is_on(self) -> bool:
        """Return if switch is on or off."""
        return self.sock.properties[self.entity_description.key]

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the switch."""
        await self.entity_description.turn_on_fn(self.sock)(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the switch."""
        await self.entity_description.turn_off_fn(self.sock)(False)
