"""Polling coordinator with a hold for commands the purifier has not applied yet."""

from __future__ import annotations

import logging
import time
from typing import Any

from aiohttp import ClientError
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from ._pyvesync.utils.errors import VeSyncError, VeSyncLoginError, VeSyncTokenError
from .const import CONF_TOKEN, DOMAIN, PENDING_TIMEOUT, SCAN_INTERVAL
from .hub import PetProHub

_LOGGER = logging.getLogger(__name__)

type PetProConfigEntry = ConfigEntry[PetProCoordinator]


class PetProCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any] | None]]):
    """Polls every purifier on the account; data maps device cid to its raw status."""

    config_entry: PetProConfigEntry

    def __init__(self, hass: HomeAssistant, entry: PetProConfigEntry, hub: PetProHub) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.hub = hub
        # (cid, field) -> (value sent, monotonic deadline, value the purifier reported when sent)
        self._pending: dict[tuple[str, str], tuple[Any, float, Any]] = {}
        # Last raw status per purifier, before any pending value is overlaid.
        self._reported: dict[str, dict[str, Any]] = {}
        self._token_rejections = 0

    async def _async_update_data(self) -> dict[str, dict[str, Any] | None]:
        data: dict[str, dict[str, Any] | None] = {}
        errors: list[str] = []
        token_rejected = False
        for cid in self.hub.devices:
            try:
                data[cid] = await self.hub.async_get_status(cid)
            except VeSyncLoginError as err:
                raise ConfigEntryAuthFailed(str(err)) from err
            except VeSyncTokenError as err:
                token_rejected = True
                errors.append(f"{self.hub.devices[cid].device_name}: {err}")
                data[cid] = None
            except (VeSyncError, ClientError, TimeoutError) as err:
                errors.append(f"{self.hub.devices[cid].device_name}: {err}")
                data[cid] = None
        if token_rejected:
            # The library already logged in once and retried. A token that is still
            # rejected on the next poll will not fix itself: stop and ask for reauth
            # rather than logging in every few minutes forever.
            self._token_rejections += 1
            if self._token_rejections >= 2:
                raise ConfigEntryAuthFailed("VeSync keeps rejecting the login token")
        else:
            self._token_rejections = 0
        if self.hub.devices and len(errors) == len(self.hub.devices):
            raise UpdateFailed("; ".join(errors))
        self._reported = {cid: dict(status) for cid, status in data.items() if status is not None}
        for message in errors:
            _LOGGER.warning("Status read failed for %s", message)
        self._apply_pending(data)
        self._persist_token()
        return data

    def _apply_pending(self, data: dict[str, dict[str, Any] | None]) -> None:
        now = time.monotonic()
        for (cid, field), (value, deadline, snapshot) in list(self._pending.items()):
            status = data.get(cid)
            if status is None:
                continue
            reported = status.get(field)
            if reported == value and value != snapshot:
                del self._pending[(cid, field)]
                _LOGGER.debug("%s=%s confirmed by the purifier", field, value)
            elif now > deadline:
                del self._pending[(cid, field)]
                if reported != value:
                    _LOGGER.warning(
                        "%s did not apply %s=%s within %s s; showing the reported %s",
                        self.hub.devices[cid].device_name,
                        field,
                        value,
                        PENDING_TIMEOUT,
                        reported,
                    )
            else:
                # Includes reported == value == snapshot: an earlier, opposite command
                # may still land, so keep holding until the deadline.
                status[field] = value

    def _persist_token(self) -> None:
        creds = self.hub.credentials()
        entry = self.config_entry
        if creds.get(CONF_TOKEN) and creds[CONF_TOKEN] != entry.data.get(CONF_TOKEN):
            _LOGGER.debug("VeSync token changed; saving it")
            self.hass.config_entries.async_update_entry(entry, data={**entry.data, **creds})

    def pending_fields(self, cid: str) -> list[str]:
        """Status fields of one purifier still waiting for the purifier to confirm a command."""
        return sorted(field for (pcid, field) in self._pending if pcid == cid)

    def pending(self) -> dict[str, Any]:
        now = time.monotonic()
        return {
            f"{self.hub.devices[cid].device_name}: {field}": {
                "value": value,
                "expires_in_s": round(deadline - now),
            }
            for (cid, field), (value, deadline, _snapshot) in self._pending.items()
        }

    async def async_command(
        self, cid: str, method: str, payload: dict[str, Any], expected: dict[str, Any]
    ) -> None:
        """Send a command and hold the expected fields until the purifier reports them."""
        try:
            await self.hub.async_send(cid, method, payload)
        except VeSyncLoginError as err:
            self.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(f"VeSync login failed: {err}") from err
        except (VeSyncError, ClientError, TimeoutError) as err:
            raise HomeAssistantError(f"VeSync rejected {method}: {err}") from err
        deadline = time.monotonic() + PENDING_TIMEOUT
        status = (self.data or {}).get(cid)
        reported = self._reported.get(cid, {})
        for field, value in expected.items():
            self._pending[(cid, field)] = (value, deadline, reported.get(field))
            if status is not None:
                status[field] = value
        self._persist_token()
        self.async_update_listeners()
