"""Config, reauth and options flows."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.vesync_petpro._pyvesync.utils.errors import (
    VeSyncLoginError,
    VeSyncServerError,
)
from custom_components.vesync_petpro.const import CONF_ALLOW_CONTROL, DOMAIN

from .conftest import CREDS

USER_INPUT = {"email": " user@example.com ", "password": "hunter2", CONF_ALLOW_CONTROL: True}


async def test_user_flow_stores_token_so_setup_needs_no_second_login(hass: HomeAssistant, hub_state):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "user@example.com"
    assert result["data"] == {"email": "user@example.com", "password": "hunter2", **CREDS}
    assert result["options"] == {CONF_ALLOW_CONTROL: True}
    # flow login (no stored creds), then setup reuses the stored token
    assert hub_state.connect_calls[0] is None
    assert hub_state.connect_calls[1]["token"] == CREDS["token"]


async def test_user_flow_errors(hass: HomeAssistant, hub_state):
    for error, expected in (
        (VeSyncLoginError("bad"), "invalid_auth"),
        (VeSyncServerError("down"), "cannot_connect"),
        (TimeoutError(), "cannot_connect"),
        (RuntimeError("boom"), "unknown"),
    ):
        hub_state.connect_error = error
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": expected}, error


async def test_user_flow_no_pet_pro(hass: HomeAssistant, hub_state):
    hub_state.devices.clear()
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["errors"] == {"base": "no_devices"}


async def test_duplicate_account_aborts(hass: HomeAssistant, hub_state, make_entry):
    make_entry()
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_updates_password_and_token(hass: HomeAssistant, hub_state, make_entry):
    entry = make_entry()
    hub_state.credentials["token"] = "TOKEN_NEW"
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"password": "newpass"})
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["password"] == "newpass"
    assert entry.data["token"] == "TOKEN_NEW"


async def test_options_flow_toggles_controls(hass: HomeAssistant, hub_state, make_entry):
    entry = make_entry()
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {CONF_ALLOW_CONTROL: False})
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {CONF_ALLOW_CONTROL: False}
    assert hass.states.get("fan.bedroom_vital_pet_pro") is None
    assert hass.states.get("switch.bedroom_vital_pet_pro_child_lock") is None
    assert hass.states.get("binary_sensor.bedroom_vital_pet_pro_power").state == "on"
    # and back again: the read-only binary sensors go away, the controls return
    result = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(result["flow_id"], {CONF_ALLOW_CONTROL: True})
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.bedroom_vital_pet_pro_power") is None
    assert hass.states.get("fan.bedroom_vital_pet_pro").state == "on"
