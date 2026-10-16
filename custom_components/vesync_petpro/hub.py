"""Thin wrapper over the vendored pyvesync: login, token reuse, raw status and raw commands."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiohttp import ClientSession

from ._pyvesync import VeSync
from ._pyvesync.base_devices.vesyncbasedevice import VeSyncBaseDevice
from ._pyvesync.utils.errors import VeSyncAPIResponseError
from .const import (
    CONF_ACCOUNT_ID,
    CONF_COUNTRY_CODE,
    CONF_REGION,
    CONF_TOKEN,
    MODEL_PREFIX,
    REQUEST_TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)


def is_pet_pro(device: VeSyncBaseDevice) -> bool:
    return (device.device_type or "").startswith(MODEL_PREFIX)


def inner_result(resp: Any) -> dict[str, Any]:
    """Return result.result of a bypassV2 response, raising if VeSync reported an error."""
    if not isinstance(resp, dict):
        raise VeSyncAPIResponseError("empty response")
    outer = resp.get("result")
    if resp.get("code") != 0 or not isinstance(outer, dict) or outer.get("code") != 0:
        raise VeSyncAPIResponseError(
            f"code={resp.get('code')} result_code="
            f"{outer.get('code') if isinstance(outer, dict) else None} msg={resp.get('msg')}"
        )
    inner = outer.get("result")
    return inner if isinstance(inner, dict) else {}


class PetProHub:
    """Owns the VeSync session for one account and its Vital Pet Pro purifiers."""

    def __init__(
        self,
        session: ClientSession,
        email: str,
        password: str,
        time_zone: str,
        credentials: dict[str, str] | None = None,
    ) -> None:
        self.manager = VeSync(email, password, session=session, time_zone=time_zone)
        self._credentials = credentials
        self.devices: dict[str, VeSyncBaseDevice] = {}

    async def async_connect(self) -> None:
        """Reuse a stored token if there is one, otherwise log in, then list devices.

        A stored token that VeSync rejects is replaced by one (rate limited) password
        login inside the library, so a restart never costs more than one login.
        """
        creds = self._credentials
        async with asyncio.timeout(REQUEST_TIMEOUT * 2):
            if creds and creds.get(CONF_TOKEN) and creds.get(CONF_ACCOUNT_ID):
                self.manager.set_credentials(
                    creds[CONF_TOKEN],
                    creds[CONF_ACCOUNT_ID],
                    creds.get(CONF_COUNTRY_CODE, "US"),
                    creds.get(CONF_REGION, "US"),
                )
                self.manager.enabled = True
            else:
                await self.manager.login()
            await self.manager.get_devices()
        self.devices = {d.cid: d for d in self.manager.devices if is_pet_pro(d)}
        _LOGGER.debug("Found %d Vital Pet Pro purifier(s)", len(self.devices))

    def credentials(self) -> dict[str, str]:
        """Current token data, to persist in the config entry."""
        out = self.manager.output_credentials_dict() or {}
        return {
            CONF_TOKEN: out.get("token", ""),
            CONF_ACCOUNT_ID: out.get("account_id", ""),
            CONF_COUNTRY_CODE: out.get("country_code", "US"),
            CONF_REGION: out.get("current_region", "US"),
        }

    async def async_get_status(self, cid: str) -> dict[str, Any]:
        device = self.devices[cid]
        async with asyncio.timeout(REQUEST_TIMEOUT):
            resp = await device.call_bypassv2_api("getPurifierStatus")
        return inner_result(resp)

    async def async_send(self, cid: str, method: str, data: dict[str, Any]) -> None:
        """Send one signed command. Success only means VeSync accepted it, not that it applied."""
        device = self.devices[cid]
        async with asyncio.timeout(REQUEST_TIMEOUT):
            resp = await device.call_bypassv2_api(method, data)
        inner_result(resp)
        _LOGGER.debug("%s %s accepted for %s", method, data, device.device_name)
