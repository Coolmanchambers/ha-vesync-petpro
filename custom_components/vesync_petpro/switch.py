"""Child lock and display switches (only when controls are enabled)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_ALLOW_CONTROL
from .coordinator import PetProConfigEntry
from .entity import PetProEntity


@dataclass(frozen=True, kw_only=True)
class PetProSwitchDescription(SwitchEntityDescription):
    method: str
    field: str


SWITCHES: tuple[PetProSwitchDescription, ...] = (
    PetProSwitchDescription(
        key="child_lock",
        name="Child lock",
        icon="mdi:lock",
        entity_category=EntityCategory.CONFIG,
        method="setChildLock",
        field="childLockSwitch",
    ),
    PetProSwitchDescription(
        key="display",
        name="Display",
        icon="mdi:monitor",
        entity_category=EntityCategory.CONFIG,
        method="setDisplay",
        field="screenSwitch",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: PetProConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    if not entry.options.get(CONF_ALLOW_CONTROL, True):
        return
    coordinator = entry.runtime_data
    async_add_entities(
        PetProSwitch(coordinator, cid, description)
        for cid in coordinator.hub.devices
        for description in SWITCHES
    )


class PetProSwitch(PetProEntity, SwitchEntity):
    entity_description: PetProSwitchDescription

    def __init__(self, coordinator, cid: str, description: PetProSwitchDescription) -> None:
        super().__init__(coordinator, cid, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        status = self.status
        field = self.entity_description.field
        if status is None or status.get(field) is None:
            return None
        return bool(status[field])

    async def _set(self, on: bool) -> None:
        field = self.entity_description.field
        await self._command(self.entity_description.method, {field: int(on)}, {field: int(on)})

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)
