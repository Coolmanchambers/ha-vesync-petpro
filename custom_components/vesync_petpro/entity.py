"""Base entity for Vital Pet Pro purifiers."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import PetProCoordinator


class PetProEntity(CoordinatorEntity[PetProCoordinator]):
    """One entity of one purifier; reads come from the coordinator's raw status."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: PetProCoordinator, cid: str, key: str) -> None:
        super().__init__(coordinator)
        device = coordinator.hub.devices[cid]
        self._cid = cid
        self._attr_unique_id = f"{cid}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, cid)},
            name=device.device_name,
            manufacturer="Levoit",
            model="Vital Pet Pro",
            model_id=device.device_type,
            sw_version=device.current_firm_version,
        )

    @property
    def status(self) -> dict[str, Any] | None:
        return (self.coordinator.data or {}).get(self._cid)

    @property
    def available(self) -> bool:
        return super().available and self.status is not None

    async def _command(self, method: str, payload: dict[str, Any], expected: dict[str, Any]) -> None:
        await self.coordinator.async_command(self._cid, method, payload, expected)
