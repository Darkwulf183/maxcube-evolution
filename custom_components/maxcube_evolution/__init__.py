"""MAX! Cube Evolution – UI-managed local polling integration."""
from datetime import timedelta
import asyncio
from .discovery import discover, reboot
import logging
from dataclasses import replace
from .protocol import fetch_config, send_config, send_boost, read_cube_header
from maxcube.cube import MaxCube
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.components import persistent_notification
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .const import DOMAIN, DEFAULT_INTERVAL, PLATFORMS
from .migration import async_migrate_core_entities, format_result
_LOGGER = logging.getLogger(__name__)

class CubeCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry):
        super().__init__(hass, _LOGGER, name=f"MAX! Cube {entry.data[CONF_HOST]}", update_interval=timedelta(seconds=entry.options.get("scan_interval", DEFAULT_INTERVAL)))
        self.entry = entry
        self.cube = None
        self.host = entry.data[CONF_HOST]
        self.parameter_cache = {}
        self._io_lock = asyncio.Lock()
        self.duty_cycle = None
        self.free_memory_slots = None
        self.command_error = None
        self._header_poll_count = 0
        # Stable identifier of the Cube device in the device registry.
        self.cube_device_id = entry.data.get("cube_serial") or entry.entry_id
        # Device registry id of the Cube device (set in async_setup_entry).
        self.cube_registry_id = None

    def _release_connection(self):
        """Close the maxcube-api TCP connection so other short-lived connections
        (H header read, c:/s: telegrams) are not blocked by an idle socket."""
        if self.cube is None:
            return
        try:
            self.cube.disconnect()
        except (OSError, TimeoutError, AttributeError):
            pass

    def _sync_update(self):
        try:
            if self.cube is None:
                # The constructor already performs the first update over a
                # persistent connection, so the flag must be set afterwards
                # and the connection closed explicitly.
                self.cube = MaxCube(self.host, self.entry.data[CONF_PORT])
                self.cube.use_persistent_connection = False
            else:
                self.cube.update()
            self._release_connection()
            return {device.serial: device for device in self.cube.devices if device.serial}
        except (OSError, TimeoutError, ConnectionError) as exc:
            if self.cube is not None:
                try:
                    self.cube.disconnect()
                except (OSError, TimeoutError):
                    pass
            self.cube = None
            raise UpdateFailed(f"Cube communication failed: {exc}") from exc

    async def _async_update_data(self):
        async with self._io_lock:
            try:
                result = await self.hass.async_add_executor_job(self._sync_update)
                # Low-rate TCP-only header read; never sends a radio command.
                self._header_poll_count += 1
                if self._header_poll_count == 1 or self._header_poll_count % 5 == 0:
                    try:
                        self.duty_cycle = await self.hass.async_add_executor_job(
                            read_cube_header, self.host, self.entry.data[CONF_PORT]
                        )
                    except (OSError, TimeoutError, RuntimeError, ValueError) as exc:
                        _LOGGER.debug("MAX! Cube duty header unavailable: %s", exc)
                return result
            except UpdateFailed:
                # Discovery is a recovery path for DHCP changes, not every poll.
                serial = self.entry.data.get("cube_serial")
                if serial:
                    try:
                        devices = await self.hass.async_add_executor_job(discover)
                        match = next((d for d in devices if d.serial == serial), None)
                        if match and match.host != self.host:
                            self.host = match.host
                            return await self.hass.async_add_executor_job(self._sync_update)
                    except OSError:
                        pass
                raise

    def _sync_set(self, serial, temperature, mode):
        if self.cube is None:
            raise HomeAssistantError(
                "MAX! Cube is currently not connected; try again after the next update"
            )
        device = (self.data or {}).get(serial)
        if device is None:
            raise HomeAssistantError(f"MAX! device {serial} is unknown")
        try:
            result = self.cube.set_temperature_mode(device, temperature, mode)
        finally:
            self._release_connection()
        if result is False:
            raise HomeAssistantError("Cube did not confirm the command")

    def _rf_address(self, serial):
        dev = self.data[serial]
        address = getattr(dev, "rf_address", None)
        if address is None:
            raise RuntimeError("Device has no RF address")
        return int(address.replace(":", ""), 16) if isinstance(address, str) else int(address)

    async def async_load_parameters(self, serial):
        """One explicit configuration read, requested by the device button."""
        address = self._rf_address(serial)
        async with self._io_lock:
            config = await self.hass.async_add_executor_job(
                fetch_config, self.host, self.entry.data[CONF_PORT], address
            )
            self.parameter_cache[serial] = config
        self.async_update_listeners()

    async def async_reconnect(self):
        async with self._io_lock:
            if self.cube:
                await self.hass.async_add_executor_job(self.cube.disconnect)
            self.cube = None
        await self.async_request_refresh()

    async def async_reboot(self):
        serial = self.entry.data.get("cube_serial") or getattr(self.cube, "serial", None)
        if not serial:
            raise ValueError("Cube serial unknown; discovery is required before reboot")
        async with self._io_lock:
            await self.hass.async_add_executor_job(reboot, serial)
            if self.cube:
                await self.hass.async_add_executor_job(self.cube.disconnect)
            self.cube = None

    def _apply_command_status(self, status):
        if status is None:
            return
        self.duty_cycle, error, self.free_memory_slots = status
        # Keep a reported command error until a later S response confirms success.
        self.command_error = error
        self.async_update_listeners()

    async def async_write_parameter(self, serial, key, value, family):
        """Read before write to preserve fields; read once after to verify."""
        address = self._rf_address(serial)
        if serial not in self.parameter_cache:
            raise RuntimeError("Load thermostat configuration before editing")
        if key == 'boost_duration' and value not in (0, 5, 10, 15, 20, 25, 30, 60):
            raise ValueError('Unsupported boost duration')
        converted = int(value) if key in (
            'max_valve_position', 'valve_offset', 'boost_valve_position',
            'boost_duration', 'window_open_duration') else float(value)
        async with self._io_lock:
            host, port = self.host, self.entry.data[CONF_PORT]
            fresh = await self.hass.async_add_executor_job(fetch_config, host, port, address)
            updated = replace(fresh, **{key: converted})
            status = await self.hass.async_add_executor_job(send_config, host, port, updated, family)
            self._apply_command_status(status)
            if status is not None and status[1]:
                raise RuntimeError("Cube reported a command error")
            try:
                verified = await self.hass.async_add_executor_job(fetch_config, host, port, address)
            except (OSError, ValueError, RuntimeError) as exc:
                self.parameter_cache.pop(serial, None)
                self.async_update_listeners()
                raise RuntimeError("Configuration written, but readback failed; acceptance unverified") from exc
            self.parameter_cache[serial] = verified
        self.async_update_listeners()
        actual = getattr(verified, key)
        if abs(float(actual) - float(converted)) > 0.01:
            raise RuntimeError(
                f"Cube readback differs for {key}: requested {converted}, returned {actual}"
            )

    async def async_boost(self, serial):
        """Send the dedicated MAX! Boost telegram without a temperature value."""
        dev = self.data[serial]
        address = getattr(dev, "rf_address", None)
        room_id = getattr(dev, "room_id", None)
        if address is None or room_id is None:
            raise RuntimeError("Thermostat RF address or room ID unavailable")
        if isinstance(address, str):
            address = int(address.replace(":", ""), 16)
        async with self._io_lock:
            status = await self.hass.async_add_executor_job(
                send_boost, self.host, self.entry.data[CONF_PORT], int(address), int(room_id)
            )
            self._apply_command_status(status)
            if status is not None and status[1]:
                raise RuntimeError("Cube reported a command error")
        await self.async_request_refresh()

    async def async_migrate_core(self):
        """Take over orphaned entities of the core integration "maxcube"."""
        result = await async_migrate_core_entities(
            self.hass, self.entry.entry_id, set(self.data or {})
        )
        persistent_notification.async_create(
            self.hass,
            format_result(result),
            title="MAX! Cube Evolution – Übernahme aus der Core-Integration",
            notification_id=f"{DOMAIN}_migration_{self.entry.entry_id}",
        )
        return result

    async def async_set_target(self, serial, temperature=None, mode=None):
        async with self._io_lock:
            await self.hass.async_add_executor_job(self._sync_set, serial, temperature, mode)
        await self.async_request_refresh()

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = CubeCoordinator(hass, entry)
    try:
        await coordinator.async_config_entry_first_refresh()
    except (UpdateFailed, OSError, TimeoutError) as exc:
        raise ConfigEntryNotReady(str(exc)) from exc
    # Register the Cube itself before any platform references it via via_device.
    if not entry.data.get("cube_serial") and getattr(coordinator.cube, "serial", None):
        coordinator.cube_device_id = coordinator.cube.serial
    cube_device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, coordinator.cube_device_id)},
        name="MAX! Cube",
        manufacturer="eQ-3",
        model="MAX! Cube LAN Gateway",
    )
    coordinator.cube_registry_id = cube_device.id
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # Device actions: explicit services, no automatic reboot.
    if not hass.services.has_service(DOMAIN, "reboot"):
        async def _reboot(call):
            for co in hass.data.get(DOMAIN, {}).values():
                if not call.data.get("entry_id") or call.data["entry_id"] == co.entry.entry_id:
                    await co.async_reboot()
        hass.services.async_register(DOMAIN, "reboot", _reboot)
    if not hass.services.has_service(DOMAIN, "reconnect"):
        async def _reconnect(call):
            for co in hass.data.get(DOMAIN, {}).values():
                if not call.data.get("entry_id") or call.data["entry_id"] == co.entry.entry_id:
                    await co.async_reconnect()
        hass.services.async_register(DOMAIN, "reconnect", _reconnect)
    entry.async_on_unload(entry.add_update_listener(_options_updated))
    return True

async def _options_updated(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        if coordinator.cube:
            await hass.async_add_executor_job(coordinator.cube.disconnect)
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, "reboot")
            hass.services.async_remove(DOMAIN, "reconnect")
    return ok
