"""Diagnostics: raw purifier status and pending commands, credentials redacted."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant

from .const import CONF_ACCOUNT_ID, CONF_TOKEN
from .coordinator import PetProConfigEntry

TO_REDACT = {CONF_EMAIL, CONF_PASSWORD, CONF_TOKEN, CONF_ACCOUNT_ID}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: PetProConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    devices = []
    for cid, device in coordinator.hub.devices.items():
        devices.append(
            {
                "name": device.device_name,
                "device_type": device.device_type,
                "config_module": device.config_module,
                "firmware": device.current_firm_version,
                "status": (coordinator.data or {}).get(cid),
            }
        )
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "devices": devices,
        "pending": coordinator.pending(),
    }
