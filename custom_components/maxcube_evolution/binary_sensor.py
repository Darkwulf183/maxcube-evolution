"""MAX! window and battery status."""
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.const import EntityCategory
from .const import DOMAIN
from .entity import CubeEntity
async def async_setup_entry(hass,entry,async_add_entities):
    co=hass.data[DOMAIN][entry.entry_id]
    entities=[]
    for serial,dev in co.data.items():
        entities.append(CubeBattery(co,serial))
        if dev.is_windowshutter():entities.append(CubeWindow(co,serial))
    async_add_entities(entities)
class CubeBattery(CubeEntity,BinarySensorEntity):
    _attr_name="Battery low"
    _attr_device_class=BinarySensorDeviceClass.BATTERY
    _attr_entity_category=EntityCategory.DIAGNOSTIC
    def __init__(self,co,serial):
        super().__init__(co,serial)
        self._attr_unique_id=f"{serial}_battery"
    @property
    def is_on(self):return self.device.battery==1
class CubeWindow(CubeEntity,BinarySensorEntity):
    _attr_name=None
    _attr_device_class=BinarySensorDeviceClass.WINDOW
    def __init__(self,co,serial):
        super().__init__(co,serial)
        self._attr_unique_id=serial
    @property
    def is_on(self):return self.device.is_open
