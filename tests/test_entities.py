"""Setup, entity values from real status, commands and the pending-command hold."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from custom_components.vesync_petpro._pyvesync.utils.errors import (
    VeSyncLoginError,
    VeSyncServerError,
)
from custom_components.vesync_petpro.const import PENDING_TIMEOUT

BEDROOM = "bedroom_vital_pet_pro"


async def setup(hass, make_entry, allow_control=True):
    entry = make_entry(allow_control)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def state(hass, entity_id):
    st = hass.states.get(entity_id)
    assert st is not None, f"missing {entity_id}"
    return st


async def refresh(hass, entry):
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()


async def test_sensors_show_real_status(hass: HomeAssistant, hub_state, make_entry):
    await setup(hass, make_entry)
    expect = {
        f"sensor.{BEDROOM}_pm2_5": "1",
        f"sensor.{BEDROOM}_voc": "430",
        f"sensor.{BEDROOM}_odor_level": "4",
        f"sensor.{BEDROOM}_air_quality_level": "4",
        f"sensor.{BEDROOM}_filter_life": "93",
        f"sensor.{BEDROOM}_filter_days_remaining": "167",
        f"sensor.{BEDROOM}_fan_speed": "3",
        f"sensor.{BEDROOM}_mode": "OdorShield Performance",
        f"sensor.{BEDROOM}_total_clean_air": "20499",
        f"sensor.{BEDROOM}_cumulative_clean_air": "20460",
        f"sensor.{BEDROOM}_error_code": "0",
        f"sensor.{BEDROOM}_display_schedule": "08:00-22:00",
        f"binary_sensor.{BEDROOM}_filter_door": "off",
        f"binary_sensor.{BEDROOM}_auto_clean": "off",
        f"binary_sensor.{BEDROOM}_beeper": "off",
        f"switch.{BEDROOM}_child_lock": "off",
        f"switch.{BEDROOM}_display": "on",
        f"fan.{BEDROOM}": "on",
    }
    for entity_id, value in expect.items():
        assert state(hass, entity_id).state == value, entity_id
    fan = state(hass, f"fan.{BEDROOM}")
    assert fan.attributes["percentage"] == 100
    assert fan.attributes["preset_mode"] == "OdorShield Performance"
    assert fan.attributes["preset_modes"] == [
        "Sleep", "OdorShield Quiet", "OdorShield Balanced", "OdorShield Performance"
    ]
    # second purifier gets its own full set
    assert state(hass, "sensor.office_vital_pet_pro_filter_life").state == "93"


async def test_read_only_mode_has_no_controls(hass: HomeAssistant, hub_state, make_entry):
    await setup(hass, make_entry, allow_control=False)
    assert hass.states.get(f"fan.{BEDROOM}") is None
    assert hass.states.get(f"switch.{BEDROOM}_child_lock") is None
    assert state(hass, f"binary_sensor.{BEDROOM}_power").state == "on"
    assert state(hass, f"binary_sensor.{BEDROOM}_child_lock").state == "off"
    assert state(hass, f"binary_sensor.{BEDROOM}_display").state == "on"
    assert hub_state.sent == []


async def test_switch_command_holds_until_confirmed(hass: HomeAssistant, hub_state, make_entry):
    entry = await setup(hass, make_entry)
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": f"switch.{BEDROOM}_child_lock"}, blocking=True
    )
    assert hub_state.sent == [("cid-bedroom", "setChildLock", {"childLockSwitch": 1})]
    assert state(hass, f"switch.{BEDROOM}_child_lock").state == "on"
    # cloud still reports the old value: the hold keeps showing the command
    await refresh(hass, entry)
    assert state(hass, f"switch.{BEDROOM}_child_lock").state == "on"
    # purifier applies it: hold cleared, real value shown
    hub_state.status["cid-bedroom"]["childLockSwitch"] = 1
    await refresh(hass, entry)
    assert entry.runtime_data.pending() == {}
    assert state(hass, f"switch.{BEDROOM}_child_lock").state == "on"


async def test_unconfirmed_command_expires(hass: HomeAssistant, hub_state, make_entry, caplog):
    entry = await setup(hass, make_entry)
    with patch("custom_components.vesync_petpro.coordinator.time.monotonic", return_value=1000.0):
        await hass.services.async_call(
            "switch", "turn_off", {"entity_id": f"switch.{BEDROOM}_display"}, blocking=True
        )
    assert state(hass, f"switch.{BEDROOM}_display").state == "off"
    with patch(
        "custom_components.vesync_petpro.coordinator.time.monotonic",
        return_value=1000.0 + PENDING_TIMEOUT + 1,
    ):
        await refresh(hass, entry)
    assert state(hass, f"switch.{BEDROOM}_display").state == "on"
    assert "did not apply screenSwitch=0" in caplog.text


async def test_fan_speed_from_off_turns_on_first(hass: HomeAssistant, hub_state, make_entry):
    hub_state.status["cid-bedroom"]["powerSwitch"] = 0
    await setup(hass, make_entry)
    await hass.services.async_call(
        "fan", "set_percentage", {"entity_id": f"fan.{BEDROOM}", "percentage": 34}, blocking=True
    )
    assert hub_state.sent == [
        ("cid-bedroom", "setSwitch", {"powerSwitch": 1, "switchIdx": 0}),
        ("cid-bedroom", "setLevel", {"levelIdx": 0, "manualSpeedLevel": 2, "levelType": "wind"}),
    ]
    fan = state(hass, f"fan.{BEDROOM}")
    assert fan.state == "on"
    assert fan.attributes["percentage"] == 66
    assert fan.attributes["preset_mode"] is None


async def test_fan_preset_and_off(hass: HomeAssistant, hub_state, make_entry):
    await setup(hass, make_entry)
    await hass.services.async_call(
        "fan", "set_preset_mode",
        {"entity_id": f"fan.{BEDROOM}", "preset_mode": "OdorShield Quiet"}, blocking=True,
    )
    await hass.services.async_call("fan", "turn_off", {"entity_id": f"fan.{BEDROOM}"}, blocking=True)
    assert hub_state.sent == [
        ("cid-bedroom", "setPurifierMode", {"workMode": "odorShieldQuiet"}),
        ("cid-bedroom", "setSwitch", {"powerSwitch": 0, "switchIdx": 0}),
    ]
    assert state(hass, f"fan.{BEDROOM}").state == "off"
    assert state(hass, f"sensor.{BEDROOM}_mode").state == "OdorShield Quiet"


async def test_rejected_command_raises_and_holds_nothing(hass: HomeAssistant, hub_state, make_entry):
    entry = await setup(hass, make_entry)

    async def reject(cid, method, data):
        raise VeSyncServerError("nope")

    with patch.object(entry.runtime_data.hub, "async_send", reject):
        with pytest.raises(HomeAssistantError):
            await hass.services.async_call(
                "switch", "turn_on", {"entity_id": f"switch.{BEDROOM}_child_lock"}, blocking=True
            )
    assert entry.runtime_data.pending() == {}
    assert state(hass, f"switch.{BEDROOM}_child_lock").state == "off"


async def test_new_token_is_saved_without_reloading(hass: HomeAssistant, hub_state, make_entry):
    entry = await setup(hass, make_entry)
    connects = len(hub_state.connect_calls)
    hub_state.credentials["token"] = "TOKEN_TWO"
    await refresh(hass, entry)
    assert entry.data["token"] == "TOKEN_TWO"
    assert entry.state is ConfigEntryState.LOADED
    assert len(hub_state.connect_calls) == connects


async def test_one_purifier_offline_marks_only_it_unavailable(hass: HomeAssistant, hub_state, make_entry):
    entry = await setup(hass, make_entry)
    hub = entry.runtime_data.hub
    real = hub.async_get_status

    async def flaky(cid):
        if cid == "cid-office":
            raise VeSyncServerError("offline")
        return await real(cid)

    with patch.object(hub, "async_get_status", flaky):
        await refresh(hass, entry)
    assert state(hass, "sensor.office_vital_pet_pro_pm2_5").state == "unavailable"
    assert state(hass, f"sensor.{BEDROOM}_pm2_5").state == "1"


async def test_bad_login_at_setup_starts_reauth(hass: HomeAssistant, hub_state, make_entry):
    hub_state.connect_error = VeSyncLoginError("bad password")
    entry = make_entry()
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler("vesync_petpro")
    assert any(f["context"]["source"] == "reauth" for f in flows)


async def test_vesync_down_at_setup_retries(hass: HomeAssistant, hub_state, make_entry):
    hub_state.connect_error = VeSyncServerError("down")
    entry = make_entry()
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_unload(hass: HomeAssistant, hub_state, make_entry):
    entry = await setup(hass, make_entry)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_diagnostics_redacts_credentials(hass: HomeAssistant, hub_state, make_entry):
    from custom_components.vesync_petpro.diagnostics import async_get_config_entry_diagnostics

    entry = await setup(hass, make_entry)
    diag = await async_get_config_entry_diagnostics(hass, entry)
    flat = repr(diag)
    for secret in ("hunter2", "user@example.com", "TOKEN_ONE", "1234567", "cid-bedroom"):
        assert secret not in flat, secret
    assert diag["devices"][0]["status"]["VOC"] == 430


async def test_toggle_back_before_first_lands_keeps_hold(hass: HomeAssistant, hub_state, make_entry):
    """ON then OFF before ON lands: the old reported 0 must not 'confirm' the OFF."""
    entry = await setup(hass, make_entry)
    eid = f"switch.{BEDROOM}_child_lock"
    await hass.services.async_call("switch", "turn_on", {"entity_id": eid}, blocking=True)
    await hass.services.async_call("switch", "turn_off", {"entity_id": eid}, blocking=True)
    await refresh(hass, entry)  # device still reports 0
    assert entry.runtime_data.pending(), "hold dropped on a stale report"
    hub_state.status["cid-bedroom"]["childLockSwitch"] = 1  # the late ON lands
    await refresh(hass, entry)
    assert state(hass, eid).state == "off"  # still showing the last command


async def test_repeated_token_rejection_asks_for_reauth(hass: HomeAssistant, hub_state, make_entry):
    from custom_components.vesync_petpro._pyvesync.utils.errors import VeSyncTokenError

    entry = await setup(hass, make_entry)
    hub_state.status_error = VeSyncTokenError("rejected")
    await refresh(hass, entry)
    assert entry.state is ConfigEntryState.LOADED  # one bad poll: keep trying
    await refresh(hass, entry)
    flows = hass.config_entries.flow.async_progress_by_handler("vesync_petpro")
    assert any(f["context"]["source"] == "reauth" for f in flows)


async def test_token_rejected_at_setup_is_auth_failure(hass: HomeAssistant, hub_state, make_entry):
    from custom_components.vesync_petpro._pyvesync.utils.errors import VeSyncTokenError

    hub_state.connect_error = VeSyncTokenError("rejected after relogin")
    entry = make_entry()
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
