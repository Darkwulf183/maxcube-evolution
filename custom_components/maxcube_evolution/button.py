"""On-demand thermostat configuration reads and Cube maintenance actions."""
from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from .const import DOMAIN
from .entity import CubeEntity, CubeHubEntity

async def async_setup_entry(hass, entry, async_add_entities):
    co = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        LoadConfigButton(co, serial) for serial, dev in co.data.items()
        if dev.is_thermostat() and getattr(dev, "rf_address", None) is not None
    ] + [MigrateCoreButton(co)])

class LoadConfigButton(CubeEntity, ButtonEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_name = "Konfiguration laden"
    _attr_icon = "mdi:download"

    def __init__(self, coordinator, serial):
        super().__init__(coordinator, serial)
        self._attr_unique_id = f"{serial}_load_config"

    async def async_press(self):
        await self.coordinator.async_load_parameters(self.serial)


class MigrateCoreButton(CubeHubEntity, ButtonEntity):
    """Take over entity IDs of the legacy core integration "maxcube".

    Only edits the entity registry; nothing is sent to the Cube. Safe to press
    repeatedly: entities that were already taken over are no longer found.
    """

    _attr_entity_category = EntityCategory.CONFIG
    _attr_name = "Entitäten aus Core-Integration übernehmen"
    _attr_icon = "mdi:database-import"

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.cube_device_id}_migrate_core"

    @property
    def available(self):
        # Registry-only action: usable even while the Cube is unreachable.
        return True

    async def async_press(self):
        await self.coordinator.async_migrate_core()
