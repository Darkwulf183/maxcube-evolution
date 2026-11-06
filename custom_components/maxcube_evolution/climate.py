"""Thermostat climate entities."""
from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACMode, HVACAction, PRESET_NONE, PRESET_BOOST, PRESET_COMFORT, PRESET_ECO, PRESET_AWAY
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from maxcube.device import MAX_DEVICE_MODE_AUTOMATIC as AUTO, MAX_DEVICE_MODE_MANUAL as MANUAL, MAX_DEVICE_MODE_BOOST as BOOST, MAX_DEVICE_MODE_VACATION as VACATION
from .const import DOMAIN
from .entity import CubeEntity

async def async_setup_entry(hass, entry, async_add_entities):
    co=hass.data[DOMAIN][entry.entry_id]
    async_add_entities([CubeClimate(co,s) for s,d in co.data.items() if d.is_thermostat() or d.is_wallthermostat()])

class CubeClimate(CubeEntity,ClimateEntity):
    _attr_name = None
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 0.5
    _attr_hvac_modes = [HVACMode.OFF,HVACMode.AUTO,HVACMode.HEAT]
    _attr_preset_modes = [PRESET_NONE,PRESET_BOOST,PRESET_COMFORT,PRESET_ECO,PRESET_AWAY,"on"]
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.PRESET_MODE | ClimateEntityFeature.TURN_OFF | ClimateEntityFeature.TURN_ON
    def __init__(self,co,serial):
        super().__init__(co,serial)
        self._attr_unique_id=serial
    @property
    def min_temp(self):
        return max(5.0,self.device.min_temperature or 5.0)
    @property
    def max_temp(self):
        return self.device.max_temperature or 30.0
    @property
    def current_temperature(self):
        return self.device.actual_temperature
    @property
    def target_temperature(self):
        t=self.device.target_temperature
        return t if t is not None and self.min_temp<=t<=self.max_temp else None
    @property
    def hvac_mode(self):
        d=self.device
        if d.mode==MANUAL and d.target_temperature==4.5:
            return HVACMode.OFF
        return HVACMode.AUTO if d.mode in (AUTO,BOOST) else HVACMode.HEAT
    @property
    def hvac_action(self):
        if self.hvac_mode==HVACMode.OFF:
            return HVACAction.OFF
        d=self.device
        if d.is_thermostat():
            return HVACAction.HEATING if d.valve_position and d.valve_position>0 else HVACAction.IDLE
        cube=self.coordinator.cube
        if cube is None:
            return None
        room=cube.room_by_id(d.room_id)
        return HVACAction.HEATING if room and any(x.is_thermostat() and (x.valve_position or 0)>0 for x in cube.devices_by_room(room)) else HVACAction.IDLE
    @property
    def preset_mode(self):
        d=self.device
        if d.mode==BOOST:return PRESET_BOOST
        if d.mode==VACATION:return PRESET_AWAY
        if d.mode==MANUAL:
            if d.target_temperature==d.comfort_temperature:return PRESET_COMFORT
            if d.target_temperature==d.eco_temperature:return PRESET_ECO
            if d.target_temperature==30.5:return "on"
        return PRESET_NONE
    @property
    def extra_state_attributes(self):
        return {"valve_position":self.device.valve_position} if self.device.is_thermostat() else {}
    async def async_set_temperature(self,**kwargs):
        if ATTR_TEMPERATURE in kwargs:
            await self.coordinator.async_set_target(self.serial,kwargs[ATTR_TEMPERATURE],None)
    async def async_set_hvac_mode(self,hvac_mode):
        if hvac_mode==HVACMode.OFF:await self.coordinator.async_set_target(self.serial,4.5,MANUAL)
        elif hvac_mode==HVACMode.AUTO:await self.coordinator.async_set_target(self.serial,None,AUTO)
        elif hvac_mode==HVACMode.HEAT:await self.coordinator.async_set_target(self.serial,max(self.device.target_temperature or 20,self.min_temp),MANUAL)
    async def async_set_preset_mode(self,preset_mode):
        if preset_mode == PRESET_BOOST:
            await self.coordinator.async_boost(self.serial)
            return
        d=self.device
        mapping={PRESET_COMFORT:(d.comfort_temperature,MANUAL),PRESET_ECO:(d.eco_temperature,MANUAL),"on":(30.5,MANUAL),PRESET_AWAY:(None,VACATION),PRESET_NONE:(None,AUTO)}
        if preset_mode not in mapping:raise ValueError(f"Unsupported preset {preset_mode}")
        await self.coordinator.async_set_target(self.serial,*mapping[preset_mode])
    async def async_turn_off(self):
        await self.async_set_hvac_mode(HVACMode.OFF)
    async def async_turn_on(self):
        await self.async_set_hvac_mode(HVACMode.HEAT)
