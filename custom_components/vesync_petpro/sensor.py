"""Sensors for Vital Pet Pro purifiers (all read-only)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    PERCENTAGE,
    EntityCategory,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import FAN_LEVEL_OFF, MODE_LABELS
from .coordinator import PetProConfigEntry
from .entity import PetProEntity


def _fan_level(status: dict[str, Any]) -> int | None:
    level = status.get("fanSpeedLevel")
    if level is None:
        return None
    return 0 if level == FAN_LEVEL_OFF else level


def _mode(status: dict[str, Any]) -> str | None:
    mode = status.get("workMode")
    return MODE_LABELS.get(mode, mode) if mode is not None else None


def _seconds_to_hhmm(seconds: Any) -> str | None:
    if not isinstance(seconds, int):
        return None
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}"


def _display_schedule(status: dict[str, Any]) -> str | None:
    pref = status.get("screenPreference")
    if not isinstance(pref, dict):
        return None
    start = _seconds_to_hhmm(pref.get("screenStartTime"))
    end = _seconds_to_hhmm(pref.get("screenEndTime"))
    return f"{start}-{end}" if start and end else None


@dataclass(frozen=True, kw_only=True)
class PetProSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], Any]
    attrs_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


SENSORS: tuple[PetProSensorDescription, ...] = (
    PetProSensorDescription(
        key="pm25",
        name="PM2.5",
        device_class=SensorDeviceClass.PM25,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: s.get("PM25"),
    ),
    PetProSensorDescription(
        key="voc",
        name="VOC",
        icon="mdi:molecule",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: s.get("VOC"),
    ),
    PetProSensorDescription(
        key="odor_level",
        name="Odor level",
        icon="mdi:scent",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: s.get("odorLevel"),
    ),
    PetProSensorDescription(
        key="air_quality_level",
        name="Air quality level",
        icon="mdi:air-filter",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: s.get("AQLevel"),
    ),
    PetProSensorDescription(
        key="filter_life",
        name="Filter life",
        icon="mdi:air-filter",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: s.get("filterLifePercent"),
    ),
    PetProSensorDescription(
        key="filter_days_remaining",
        name="Filter days remaining",
        icon="mdi:calendar-clock",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.DAYS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: s.get("filterRemainDay"),
    ),
    PetProSensorDescription(
        key="fan_speed",
        name="Fan speed",
        icon="mdi:fan",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_fan_level,
    ),
    PetProSensorDescription(
        key="mode",
        name="Mode",
        icon="mdi:tune-variant",
        value_fn=_mode,
    ),
    PetProSensorDescription(
        key="total_clean_air",
        name="Total clean air",
        icon="mdi:weather-windy",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.get("totalCleanAir"),
    ),
    PetProSensorDescription(
        key="cumulative_clean_air",
        name="Cumulative clean air",
        icon="mdi:weather-windy",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.get("cumulativeCleanAir"),
    ),
    PetProSensorDescription(
        key="error_code",
        name="Error code",
        icon="mdi:alert-circle-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.get("errorCode"),
        attrs_fn=lambda s: {"error_codes": s.get("errorCodes")},
    ),
    PetProSensorDescription(
        key="display_schedule",
        name="Display schedule",
        icon="mdi:clock-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_display_schedule,
        attrs_fn=lambda s: {
            "screen_on_type": (s.get("screenPreference") or {}).get("screenOnType")
        },
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: PetProConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        PetProSensor(coordinator, cid, description)
        for cid in coordinator.hub.devices
        for description in SENSORS
    )


class PetProSensor(PetProEntity, SensorEntity):
    entity_description: PetProSensorDescription

    def __init__(self, coordinator, cid: str, description: PetProSensorDescription) -> None:
        super().__init__(coordinator, cid, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        status = self.status
        return self.entity_description.value_fn(status) if status is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        status = self.status
        if status is None or self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(status)
