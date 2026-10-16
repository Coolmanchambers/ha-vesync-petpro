"""Binary sensors for Vital Pet Pro purifiers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_ALLOW_CONTROL
from .coordinator import PetProConfigEntry
from .entity import PetProEntity


def _flag(field: str) -> Callable[[dict[str, Any]], bool | None]:
    def read(status: dict[str, Any]) -> bool | None:
        value = status.get(field)
        return None if value is None else bool(value)

    return read


def _auto_clean(status: dict[str, Any]) -> bool | None:
    pref = status.get("autoCleanPreference")
    if not isinstance(pref, dict) or pref.get("autoCleanState") is None:
        return None
    return bool(pref["autoCleanState"])


@dataclass(frozen=True, kw_only=True)
class PetProBinaryDescription(BinarySensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], bool | None]


ALWAYS: tuple[PetProBinaryDescription, ...] = (
    PetProBinaryDescription(
        key="filter_door",
        name="Filter door",
        device_class=BinarySensorDeviceClass.OPENING,
        value_fn=_flag("filterOpenState"),
    ),
    PetProBinaryDescription(
        key="auto_clean",
        name="Auto-clean",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=_auto_clean,
    ),
    PetProBinaryDescription(
        key="beeper",
        name="Beeper",
        icon="mdi:volume-high",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_flag("buzzerSwitch"),
    ),
)

# Shown instead of the fan and switches when controls are turned off in the options.
READ_ONLY_STATE: tuple[PetProBinaryDescription, ...] = (
    PetProBinaryDescription(
        key="power",
        name="Power",
        device_class=BinarySensorDeviceClass.POWER,
        value_fn=_flag("powerSwitch"),
    ),
    PetProBinaryDescription(
        key="child_lock_state",
        name="Child lock",
        icon="mdi:lock",
        value_fn=_flag("childLockSwitch"),
    ),
    PetProBinaryDescription(
        key="display_state",
        name="Display",
        icon="mdi:monitor",
        value_fn=_flag("screenSwitch"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: PetProConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    descriptions = ALWAYS
    if not entry.options.get(CONF_ALLOW_CONTROL, True):
        descriptions = ALWAYS + READ_ONLY_STATE
    async_add_entities(
        PetProBinarySensor(coordinator, cid, description)
        for cid in coordinator.hub.devices
        for description in descriptions
    )


class PetProBinarySensor(PetProEntity, BinarySensorEntity):
    entity_description: PetProBinaryDescription

    def __init__(self, coordinator, cid: str, description: PetProBinaryDescription) -> None:
        super().__init__(coordinator, cid, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        status = self.status
        return self.entity_description.value_fn(status) if status is not None else None
