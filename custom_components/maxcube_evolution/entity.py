"""Common device metadata."""
import inspect

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

# Newer Home Assistant versions link child devices by registry id ("via_device_id");
# the identifier tuple ("via_device") is deprecated there. Older versions only know
# "via_device".
_SUPPORTS_VIA_DEVICE_ID = (
    "via_device_id" in inspect.signature(dr.DeviceRegistry.async_get_or_create).parameters
)

MODELS = {
    1: "MAX! Radiator Thermostat",
    2: "MAX! Radiator Thermostat+",
    3: "MAX! Wall Thermostat",
    4: "MAX! Window Contact",
}


def via_cube(coordinator) -> dict:
    if _SUPPORTS_VIA_DEVICE_ID and coordinator.cube_registry_id:
        return {"via_device_id": coordinator.cube_registry_id}
    return {"via_device": (DOMAIN, coordinator.cube_device_id)}


def cube_device_info(coordinator) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, coordinator.cube_device_id)},
        name="MAX! Cube",
        manufacturer="eQ-3",
        model="MAX! Cube LAN Gateway",
    )


class CubeEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, serial):
        super().__init__(coordinator)
        self.serial = serial

    @property
    def device(self):
        return self.coordinator.data.get(self.serial)

    @property
    def available(self):
        return super().available and self.device is not None

    @property
    def device_info(self):
        dev = self.device
        if dev is None:
            return None
        cube = self.coordinator.cube
        room = cube.room_by_id(dev.room_id) if cube is not None else None
        return DeviceInfo(
            identifiers={(DOMAIN, self.serial)},
            name=f"{room.name} {dev.name}" if room else dev.name,
            manufacturer="eQ-3",
            model=MODELS.get(dev.type, "MAX! Device"),
            **via_cube(self.coordinator),
        )


class CubeHubEntity(CoordinatorEntity):
    """Entity that belongs to the Cube itself."""

    _attr_has_entity_name = True

    @property
    def device_info(self):
        return cube_device_info(self.coordinator)
