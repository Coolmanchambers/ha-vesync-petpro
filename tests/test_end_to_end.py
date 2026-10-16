"""Through the real vendored pyvesync inside Home Assistant; only the VeSync HTTP API is faked."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)

from custom_components.vesync_petpro._pyvesync.const import API_BASE_URL_US
from custom_components.vesync_petpro._pyvesync.utils.helpers import VESYNC_CERT_SHA1

from .conftest import PET_PRO_STATUS

FIXTURES = Path(__file__).parent / "fixtures"
BEDROOM = "bedroom_vital_pet_pro"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakeVeSync:
    """Minimal VeSync cloud: one valid token, per-device status, records every request."""

    def __init__(self) -> None:
        self.valid_token = "TOKEN_ONE"
        self.status = {
            "cid-bedroom": copy.deepcopy(PET_PRO_STATUS),
            "cid-office": copy.deepcopy(PET_PRO_STATUS),
        }
        self.requests: list[tuple[str, dict, dict]] = []
        self.logins = 0

    def register(self, mock: AiohttpClientMocker, headers_log: list) -> None:
        async def handler(method, url, data):
            path = url.path
            self.requests.append((path, copy.deepcopy(data) if isinstance(data, dict) else data, {}))
            return AiohttpClientMockResponse(method, url, json=self.respond(path, data or {}))

        mock.post(f"{API_BASE_URL_US}/cloud/v1/deviceManaged/devices", side_effect=handler)
        mock.post(f"{API_BASE_URL_US}/cloud/v2/deviceManaged/bypassV2", side_effect=handler)
        mock.post(
            f"{API_BASE_URL_US}/globalPlatform/api/accountAuth/v1/authByPWDOrOTM",
            side_effect=handler,
        )
        mock.post(
            f"{API_BASE_URL_US}/user/api/accountManage/v1/loginByAuthorizeCode4Vesync",
            side_effect=handler,
        )

    def respond(self, path: str, body: dict) -> dict:
        if path.endswith("authByPWDOrOTM"):
            return load("login_step1.json")
        if path.endswith("loginByAuthorizeCode4Vesync"):
            self.logins += 1
            self.valid_token = "sample_tk"
            resp = load("login_step2.json")
            resp["result"]["token"] = "sample_tk"
            return resp
        if body.get("token") != self.valid_token:
            return load("token_error.json")
        if path.endswith("devices"):
            return load("device_list.json")
        payload = body["payload"]
        cid = body["cid"]
        if payload["method"] == "getPurifierStatus":
            result = copy.deepcopy(self.status[cid])
        else:
            result = {}
        return {"code": 0, "msg": "request success", "traceId": "1", "result": {"code": 0, "result": result}}


async def setup_real(hass, make_entry, aioclient_mock):
    cloud = FakeVeSync()
    cloud.register(aioclient_mock, [])
    entry = make_entry()
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry, cloud


async def test_real_library_setup_status_and_signed_command(
    hass: HomeAssistant, make_entry, aioclient_mock: AiohttpClientMocker
):
    entry, cloud = await setup_real(hass, make_entry, aioclient_mock)
    assert entry.state is ConfigEntryState.LOADED
    # stored token reused: no login at all
    assert cloud.logins == 0
    # only the Vital Pet Pros are picked up, not other VeSync purifiers on the account
    assert hass.states.get(f"sensor.{BEDROOM}_filter_life").state == "93"
    assert hass.states.get("sensor.office_vital_pet_pro_voc").state == "430"
    assert hass.states.get("sensor.core_200s_series_pm2_5") is None

    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": f"switch.{BEDROOM}_child_lock"}, blocking=True
    )
    path, body, _ = cloud.requests[-1]
    assert body["payload"] == {"method": "setChildLock", "source": "APP", "data": {"childLockSwitch": 1}}
    assert body["cid"] == "cid-bedroom"
    assert body["token"] == "TOKEN_ONE"
    # the signed header itself is checked in the library tests; here: the body carries a traceId
    assert body["traceId"]


async def test_signature_header_sent_from_inside_ha(
    hass: HomeAssistant, make_entry, aioclient_mock: AiohttpClientMocker
):
    await setup_real(hass, make_entry, aioclient_mock)
    sent = [(url.path, data, headers) for _, url, data, headers in aioclient_mock.mock_calls]
    bypass = [(d, h) for p, d, h in sent if p.endswith("bypassV2")]
    assert bypass
    for body, headers in bypass:
        expected = hashlib.sha256((str(body["traceId"]) + VESYNC_CERT_SHA1).encode()).hexdigest()
        assert headers["_packFileSignature"] == f"v0001-{expected}"
        assert headers["_signOsInfo"] == "Android"


async def test_rejected_token_one_login_one_retry_new_token_saved(
    hass: HomeAssistant, make_entry, aioclient_mock: AiohttpClientMocker
):
    entry, cloud = await setup_real(hass, make_entry, aioclient_mock)
    cloud.valid_token = "ROTATED_SERVER_SIDE"  # VeSync invalidates our token
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert cloud.logins == 1
    assert entry.data["token"] == "sample_tk"
    assert hass.states.get(f"sensor.{BEDROOM}_filter_life").state == "93"
    # a later poll uses the saved token without logging in again
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert cloud.logins == 1
    assert cloud.requests[-1][1]["token"] == "sample_tk"
