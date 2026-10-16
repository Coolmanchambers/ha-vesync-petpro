"""VeSync Vital Pet Pro (LAP-P501S) integration.

Runs beside Home Assistant's own `vesync` integration without touching it: it carries a
private, patched copy of pyvesync in `_pyvesync` (see `_pyvesync/VENDORED.txt`).
Delete this integration once the official one supports the Vital Pet Pro.
"""

from __future__ import annotations

import logging

from aiohttp import ClientError
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from ._pyvesync.utils.errors import VeSyncError, VeSyncLoginError, VeSyncTokenError
from .const import CONF_ALLOW_CONTROL
from .coordinator import PetProConfigEntry, PetProCoordinator
from .hub import PetProHub

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.FAN, Platform.SENSOR, Platform.SWITCH]

# (domain, unique_id key) that exist only in one mode of the allow_control option.
CONTROL_ONLY = {("fan", "fan"), ("switch", "child_lock"), ("switch", "display")}
READ_ONLY_ONLY = {
    ("binary_sensor", "power"),
    ("binary_sensor", "child_lock_state"),
    ("binary_sensor", "display_state"),
}


def _remove_other_mode_entities(hass: HomeAssistant, entry: PetProConfigEntry) -> None:
    """Drop entities left over from the other control mode instead of leaving them unavailable."""
    stale = READ_ONLY_ONLY if entry.options.get(CONF_ALLOW_CONTROL, True) else CONTROL_ONLY
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if any(
            entity.domain == domain and entity.unique_id.endswith(f"_{key}")
            for domain, key in stale
        ):
            registry.async_remove(entity.entity_id)


async def async_setup_entry(hass: HomeAssistant, entry: PetProConfigEntry) -> bool:
    hub = PetProHub(
        async_get_clientsession(hass),
        entry.data[CONF_EMAIL],
        entry.data[CONF_PASSWORD],
        str(hass.config.time_zone),
        credentials=dict(entry.data),
    )
    try:
        await hub.async_connect()
    except (VeSyncLoginError, VeSyncTokenError) as err:
        # A token error here means VeSync rejected the token even after one fresh login;
        # retrying setup would just log in again on every retry.
        raise ConfigEntryAuthFailed(str(err)) from err
    except (VeSyncError, ClientError, TimeoutError) as err:
        raise ConfigEntryNotReady(f"VeSync unavailable: {err}") from err
    if not hub.devices:
        _LOGGER.warning("No Vital Pet Pro purifiers found on this VeSync account")

    coordinator = PetProCoordinator(hass, entry, hub)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    _remove_other_mode_entities(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    options_at_setup = dict(entry.options)

    async def _reload_on_options_change(hass: HomeAssistant, entry: PetProConfigEntry) -> None:
        # The coordinator also updates the entry when VeSync issues a new token; only an
        # options change (controls on/off) needs a reload.
        if dict(entry.options) != options_at_setup:
            await hass.config_entries.async_reload(entry.entry_id)

    entry.async_on_unload(entry.add_update_listener(_reload_on_options_change))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PetProConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
