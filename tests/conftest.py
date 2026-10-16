"""Fixtures: a fake hub for unit tests, real status data captured from a real LAP-P501S-WUSR."""

from __future__ import annotations

import copy
import sys
from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

import pytest
import pytest_socket
from pytest_homeassistant_custom_component.common import MockConfigEntry

if sys.platform == "win32":
    # The Windows event loop needs a loopback socketpair. Real network stays blocked:
    # the HA plugin's socket_allow_hosts(["127.0.0.1"]) still refuses any other host.
    pytest_socket.disable_socket = lambda *args, **kwargs: None
    # aiodns cannot run on the Windows proactor loop; requests are mocked anyway.
    import aiohttp.connector
    import aiohttp.resolver

    aiohttp.connector.DefaultResolver = aiohttp.resolver.ThreadedResolver
    aiohttp.resolver.DefaultResolver = aiohttp.resolver.ThreadedResolver

from custom_components.vesync_petpro.const import CONF_ALLOW_CONTROL, DOMAIN

# getPurifierStatus result captured from a real LAP-P501S-WUSR (2026-10-15).
PET_PRO_STATUS: dict[str, Any] = {
    "powerSwitch": 1,
    "filterLifePercent": 93,
    "workMode": "odorShieldPerformance",
    "manualSpeedLevel": 1,
    "childLockSwitch": 0,
    "screenSwitch": 1,
    "fanSpeedLevel": 3,
    "screenState": 1,
    "scheduleCount": 2,
    "timerRemain": 0,
    "VOC": 430,
    "errorCode": 0,
    "buzzerSwitch": 0,
    "odorLevel": 4,
    "filterOpenState": 0,
    "cumulativeCleanAir": 20460,
    "PM25": 1,
    "AQLevel": 4,
    "filterRemainDay": 167,
    "resetFilterDate": 0,
    "totalCleanAir": 20499,
    "errorCodes": [],
    "screenPreference": {"screenOnType": 1, "screenStartTime": 28800, "screenEndTime": 79200},
    "childLockPreference": {"childLockAutoSwitch": 0, "childLockAutoSwitchTime": 60},
    "autoCleanPreference": {
        "autoCleanState": 0,
        "autoCleanRemainTime": 0,
        "previousCleanTime": 0,
        "autoCleanTotalTime": 0,
    },
}

CREDS = {
    "token": "TOKEN_ONE",
    "account_id": "1234567",
    "country_code": "US",
    "current_region": "US",
}
ENTRY_DATA = {"email": "user@example.com", "password": "hunter2", **CREDS}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@dataclass
class FakeDevice:
    cid: str
    device_name: str
    device_type: str = "LAP-P501S-WUSR"
    current_firm_version: str | None = "1.0.3"
    config_module: str = "VS_WFON_APR_LAP-P501S-AUSR_US"


class FakeHubState:
    """Shared state the tests drive: what VeSync returns and what was sent."""

    def __init__(self) -> None:
        self.devices = {
            "cid-bedroom": FakeDevice("cid-bedroom", "Bedroom - Vital Pet Pro"),
            "cid-office": FakeDevice("cid-office", "Office - Vital Pet Pro"),
        }
        self.status = {cid: copy.deepcopy(PET_PRO_STATUS) for cid in self.devices}
        self.sent: list[tuple[str, str, dict[str, Any]]] = []
        self.credentials = dict(CREDS)
        self.connect_error: Exception | None = None
        self.status_error: Exception | None = None
        self.connect_calls: list[dict[str, Any] | None] = []


@pytest.fixture
def hub_state():
    state = FakeHubState()

    class FakeHub:
        def __init__(self, session, email, password, time_zone, credentials=None):
            self._credentials = credentials
            self.devices: dict[str, FakeDevice] = {}

        async def async_connect(self):
            state.connect_calls.append(self._credentials)
            if state.connect_error:
                raise state.connect_error
            self.devices = dict(state.devices)

        def credentials(self):
            return dict(state.credentials)

        async def async_get_status(self, cid):
            if state.status_error:
                raise state.status_error
            return copy.deepcopy(state.status[cid])

        async def async_send(self, cid, method, data):
            state.sent.append((cid, method, data))

    with (
        patch("custom_components.vesync_petpro.PetProHub", FakeHub),
        patch("custom_components.vesync_petpro.config_flow.PetProHub", FakeHub),
        patch("custom_components.vesync_petpro.async_get_clientsession"),
        patch("custom_components.vesync_petpro.config_flow.async_get_clientsession"),
    ):
        yield state


@pytest.fixture
def make_entry(hass):
    def _make(allow_control: bool = True) -> MockConfigEntry:
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="user@example.com",
            unique_id=CREDS["account_id"],
            data=dict(ENTRY_DATA),
            options={CONF_ALLOW_CONTROL: allow_control},
        )
        entry.add_to_hass(hass)
        return entry

    return _make
