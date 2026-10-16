"""Fan entity: power, three speeds and the purifier's preset modes."""

from __future__ import annotations

from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.percentage import (
    ordered_list_item_to_percentage,
    percentage_to_ordered_list_item,
)

from .const import (
    CONF_ALLOW_CONTROL,
    FAN_LEVEL_OFF,
    FAN_LEVELS,
    MODE_LABELS,
    MODE_MANUAL,
    PRESET_MODES,
)
from .coordinator import PetProConfigEntry
from .entity import PetProEntity

POWER_ON = ("setSwitch", {"powerSwitch": 1, "switchIdx": 0}, {"powerSwitch": 1})
POWER_OFF = ("setSwitch", {"powerSwitch": 0, "switchIdx": 0}, {"powerSwitch": 0})


async def async_setup_entry(
    hass: HomeAssistant, entry: PetProConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    if not entry.options.get(CONF_ALLOW_CONTROL, True):
        return
    coordinator = entry.runtime_data
    async_add_entities(PetProFan(coordinator, cid) for cid in coordinator.hub.devices)


class PetProFan(PetProEntity, FanEntity):
    _attr_name = None
    _attr_speed_count = len(FAN_LEVELS)
    _attr_preset_modes = list(PRESET_MODES)
    _attr_supported_features = (
        FanEntityFeature.SET_SPEED
        | FanEntityFeature.PRESET_MODE
        | FanEntityFeature.TURN_ON
        | FanEntityFeature.TURN_OFF
    )

    def __init__(self, coordinator, cid: str) -> None:
        super().__init__(coordinator, cid, "fan")

    @property
    def is_on(self) -> bool | None:
        status = self.status
        if status is None or status.get("powerSwitch") is None:
            return None
        return bool(status["powerSwitch"])

    @property
    def percentage(self) -> int | None:
        status = self.status
        if status is None:
            return None
        if not status.get("powerSwitch"):
            return 0
        level = status.get("fanSpeedLevel")
        if level in FAN_LEVELS:
            return ordered_list_item_to_percentage(FAN_LEVELS, level)
        return 0 if level == FAN_LEVEL_OFF else None

    @property
    def preset_mode(self) -> str | None:
        status = self.status
        mode = status.get("workMode") if status else None
        if mode is None or mode == MODE_MANUAL:
            return None
        return MODE_LABELS.get(mode, mode)

    async def _ensure_on(self) -> None:
        if not self.is_on:
            await self._command(*POWER_ON)

    async def async_turn_on(
        self, percentage: int | None = None, preset_mode: str | None = None, **kwargs: Any
    ) -> None:
        if preset_mode is not None:
            await self.async_set_preset_mode(preset_mode)
        elif percentage is not None:
            await self.async_set_percentage(percentage)
        else:
            await self._command(*POWER_ON)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._command(*POWER_OFF)

    async def async_set_percentage(self, percentage: int) -> None:
        if percentage == 0:
            await self.async_turn_off()
            return
        level = percentage_to_ordered_list_item(FAN_LEVELS, percentage)
        await self._ensure_on()
        await self._command(
            "setLevel",
            {"levelIdx": 0, "manualSpeedLevel": level, "levelType": "wind"},
            {"manualSpeedLevel": level, "fanSpeedLevel": level, "workMode": MODE_MANUAL},
        )

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        mode = PRESET_MODES[preset_mode]
        await self._ensure_on()
        await self._command("setPurifierMode", {"workMode": mode}, {"workMode": mode})
