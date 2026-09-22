"""Owlet integration coordinator class."""
from __future__ import annotations

from datetime import timedelta
import logging

from pyowletapi.exceptions import (
    OwletAuthenticationError,
    OwletConnectionError,
    OwletError,
)
from pyowletapi.sock import Sock

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_REGION
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_OWLET_REFRESH, DOMAIN
from .sleep_data import ProfileContext, fetch_latest_body_position, resolve_profile_for_dsn

_LOGGER = logging.getLogger(__name__)


class OwletCoordinator(DataUpdateCoordinator):
    """Coordinator is responsible for querying the device at a specified route."""

    def __init__(
        self, hass: HomeAssistant, sock: Sock, interval, entry: ConfigEntry
    ) -> None:
        """Initialise a custom coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
        )
        self.sock = sock
        self.config_entry: ConfigEntry = entry
        self.body_position: str | None = None
        self._profile: ProfileContext | None = None

    async def _async_update_data(self) -> None:
        """Fetch the data from the device."""
        try:
            properties = await self.sock.update_properties()
            if "tokens" in properties:
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data={**self.config_entry.data, **properties["tokens"]},
                )
            await self._async_update_body_position()
        except OwletAuthenticationError as err:
            raise ConfigEntryAuthFailed(
                f"Authentication failed for {self.config_entry.data[CONF_EMAIL]}"
            ) from err
        except (OwletError, OwletConnectionError) as err:
            raise UpdateFailed(err) from err

    async def _async_update_body_position(self) -> None:
        """Fetch the latest body position from Owlet sleep-data."""
        if self.sock.version != 3:
            self.body_position = None
            return

        refresh_token = self.config_entry.data.get(CONF_OWLET_REFRESH)
        region = self.config_entry.data.get(CONF_REGION)
        if not refresh_token or not region:
            return

        session = async_get_clientsession(self.hass)
        device_version = self.sock.oem_model or self.sock.model or "SS3"

        if self._profile is None:
            self._profile = await resolve_profile_for_dsn(
                session,
                region,
                refresh_token,
                self.sock.serial,
                device_version,
            )

        self.body_position = await fetch_latest_body_position(
            session,
            region,
            refresh_token,
            self.sock.serial,
            device_version,
            profile=self._profile,
        )

