"""MAX! Cube discovery and manual fallback."""
import socket
try:  # newer Home Assistant versions replaced voluptuous with probatio
    import probatio as schema
except ImportError:  # older Home Assistant versions
    import voluptuous as schema
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from .const import DOMAIN, DEFAULT_PORT, DEFAULT_INTERVAL
from .discovery import discover

class MaxcubeEvolutionConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    _discovered: dict = {}

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            if user_input["choice"] == "manual":
                return await self.async_step_manual()
            selected = self._discovered.get(user_input["choice"])
            if selected is not None:
                try:
                    return await self._create(selected.host, DEFAULT_PORT, selected.serial)
                except OSError:
                    errors["base"] = "cannot_connect"
        if not self._discovered or not errors:
            try:
                devices = await self.hass.async_add_executor_job(discover)
            except OSError:
                devices = []
            self._discovered = {device.serial: device for device in devices}
        choices = {serial: f"{device.name} ({serial}) – {device.host}" for serial, device in self._discovered.items()}
        choices["manual"] = "IP-Adresse manuell eingeben"
        return self.async_show_form(
            step_id="user",
            data_schema=schema.Schema({schema.Required("choice"): schema.In(choices)}),
            errors=errors,
        )

    async def async_step_manual(self, user_input=None):
        errors = {}
        if user_input:
            host, port = user_input[CONF_HOST].strip(), user_input[CONF_PORT]
            try:
                return await self._create(host, port, None)
            except OSError:
                errors["base"] = "cannot_connect"
        return self.async_show_form(step_id="manual", data_schema=schema.Schema({
            schema.Required(CONF_HOST): str,
            schema.Required(CONF_PORT, default=DEFAULT_PORT): schema.All(schema.Coerce(int), schema.Range(min=1, max=65535)),
        }), errors=errors)

    async def _create(self, host, port, serial):
        await self.hass.async_add_executor_job(self._check, host, port)
        await self.async_set_unique_id(serial or f"{host.lower()}:{port}")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=f"MAX! Cube {serial or host}", data={CONF_HOST:host, CONF_PORT:port, **({"cube_serial":serial} if serial else {})})

    @staticmethod
    def _check(host, port):
        with socket.create_connection((host, port), timeout=5):
            pass

    @staticmethod
    def async_get_options_flow(config_entry):
        return CubeOptionsFlow()

class CubeOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(step_id="init", data_schema=schema.Schema({
            schema.Required("scan_interval", default=self.config_entry.options.get("scan_interval", DEFAULT_INTERVAL)):
                schema.All(schema.Coerce(int), schema.Range(min=30, max=600)),
        }))
