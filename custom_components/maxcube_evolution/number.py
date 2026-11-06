"""Writable MAX! radiator thermostat parameters."""
from dataclasses import replace
from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory
from .const import DOMAIN
from .entity import CubeEntity

# key, label, min, max, step, unit, command family
PARAMS = (
    ('max_valve_position','Maximale Ventilöffnung',0,100,1,'%', 'valve'),
    ('valve_offset','Ventil-Offset',0,100,1,'%', 'valve'),
    ('boost_valve_position','Boost-Ventilöffnung',0,100,5,'%', 'valve'),
    ('boost_duration','Boost-Dauer',0,30,5,'min', 'valve'),
    ('comfort_temperature','Komforttemperatur',5,30,0.5,'°C', 'temperature'),
    ('eco_temperature','Eco-Temperatur',5,30,0.5,'°C', 'temperature'),
    ('max_temperature','Maximale Solltemperatur',5,30.5,0.5,'°C', 'temperature'),
    ('min_temperature','Minimale Solltemperatur',4.5,30,0.5,'°C', 'temperature'),
    ('temperature_offset','Temperatur-Offset',-3.5,3.5,0.5,'°C', 'temperature'),
    ('window_open_temperature','Fenster-offen-Temperatur',4.5,30.5,0.5,'°C', 'temperature'),
    ('window_open_duration','Fenster-offen-Dauer',0,255,5,'min', 'temperature'),
)

async def async_setup_entry(hass,entry,async_add_entities):
    co=hass.data[DOMAIN][entry.entry_id]
    async_add_entities([CubeNumber(co,serial,*param) for serial,dev in co.data.items()
                        if dev.is_thermostat() for param in PARAMS])

class CubeNumber(CubeEntity, NumberEntity):
    _attr_entity_category=EntityCategory.CONFIG
    _attr_mode=NumberMode.BOX
    def __init__(self,co,serial,key,label,minimum,maximum,step,unit,family):
        super().__init__(co,serial)
        self.key=key
        self.family=family
        self._attr_name=label
        self._attr_unique_id=f'{serial}_config_{key}'
        self._attr_native_min_value=minimum
        self._attr_native_max_value=maximum
        self._attr_native_step=step
        self._attr_native_unit_of_measurement=unit
    @property
    def available(self):
        return super().available and self.serial in self.coordinator.parameter_cache
    @property
    def native_value(self):
        config=self.coordinator.parameter_cache.get(self.serial)
        return getattr(config,self.key) if config else None
    async def async_set_native_value(self,value):
        await self.coordinator.async_write_parameter(self.serial,self.key,value,self.family)
