"""Valve opening sensors."""
from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE, EntityCategory
from .const import DOMAIN
from .entity import CubeEntity, CubeHubEntity

async def async_setup_entry(hass,entry,async_add_entities):
    co=hass.data[DOMAIN][entry.entry_id]
    async_add_entities([CubeValve(co,serial) for serial,d in co.data.items() if d.is_thermostat()] + [
        CubeDiagnostic(co, "duty_cycle", "Funkauslastung", "%", "mdi:radio-tower"),
        CubeDiagnostic(co, "free_memory_slots", "Freie Speicherplätze", None, "mdi:memory"),
        CubeDiagnostic(co, "command_error", "Befehlsfehler", None, "mdi:alert-circle-outline"),
    ])

class CubeValve(CubeEntity,SensorEntity):
    _attr_name='Ventilöffnung'
    _attr_native_unit_of_measurement=PERCENTAGE
    _attr_icon='mdi:valve'
    def __init__(self,co,serial):
        super().__init__(co,serial)
        self._attr_unique_id=f'{serial}_valve'
    @property
    def native_value(self):
        return self.device.valve_position if self.device else None


class CubeDiagnostic(CubeHubEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    def __init__(self, coordinator, key, name, unit, icon):
        super().__init__(coordinator)
        self.key = key
        self._attr_name = name
        self._attr_icon = icon
        self._attr_native_unit_of_measurement = unit
        self._attr_unique_id = f"{coordinator.entry.data.get('cube_serial') or coordinator.entry.entry_id}_{key}"
        if key != "command_error":
            self._attr_state_class = SensorStateClass.MEASUREMENT
    @property
    def native_value(self):
        value = getattr(self.coordinator, self.key)
        if self.key == "command_error" and value is not None:
            return "Fehler" if value else "OK"
        return value
