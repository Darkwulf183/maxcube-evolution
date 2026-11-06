"""Take over entities left behind by the legacy core integration "maxcube".

The core integration is YAML-only and has no config entry, so once it is removed
from configuration.yaml its entities stay in the entity registry as orphans and
keep their entity IDs blocked. The core integration uses the same unique IDs as
this integration (climate and window contact: device serial, battery:
"<serial>_battery").

For every orphaned core entity that belongs to a device of this Cube, this
integration's own entity is renamed to the old entity ID and the orphaned core
entry is deleted. Entity IDs, automations, dashboards and the recorded history
(stored per entity ID) therefore continue. User customisations of the old entry
(name, icon, area, aliases, labels, categories, hidden) are carried over.

Only the entity registry is touched: no TCP or radio traffic to the Cube.
"""
from dataclasses import dataclass, field
import inspect
import logging

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import entity_sources

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

CORE_DOMAIN = "maxcube"
MIGRATABLE_DOMAINS = ("climate", "binary_sensor")
BATTERY_SUFFIX = "_battery"
# Registry fields copied from the old core entry when the user had set them.
COPIED_FIELDS = ("name", "icon", "area_id", "aliases", "labels", "categories", "hidden_by")


@dataclass
class MigrationResult:
    migrated: list[tuple[str, str]] = field(default_factory=list)  # (old id, our former id)
    skipped: list[tuple[str, str]] = field(default_factory=list)  # (entity id, reason)

    @property
    def found(self) -> int:
        return len(self.migrated) + len(self.skipped)


def serial_from_unique_id(unique_id: str) -> str:
    if unique_id.endswith(BATTERY_SUFFIX):
        return unique_id[: -len(BATTERY_SUFFIX)]
    return unique_id


def find_core_entries(hass: HomeAssistant) -> list[er.RegistryEntry]:
    registry = er.async_get(hass)
    return sorted(
        (
            entry
            for entry in registry.entities.values()
            if entry.platform == CORE_DOMAIN and entry.domain in MIGRATABLE_DOMAINS
        ),
        key=lambda entry: entry.entity_id,
    )


def _copied_fields(registry: er.EntityRegistry, old: er.RegistryEntry) -> dict:
    """User customisations of the old entry that this HA version can store."""
    accepted = inspect.signature(registry.async_update_entity).parameters
    values = {}
    for name in COPIED_FIELDS:
        if name not in accepted or not hasattr(old, name):
            continue
        value = getattr(old, name)
        if value:  # None, empty set/list/dict: nothing customised
            values[name] = value
    return values


async def async_migrate_core_entities(
    hass: HomeAssistant, config_entry_id: str, known_serials: set[str]
) -> MigrationResult:
    if CORE_DOMAIN in hass.config.components:
        raise HomeAssistantError(
            "Die Core-Integration „maxcube“ ist noch aktiv. Bitte den Abschnitt "
            "„maxcube:“ aus der configuration.yaml entfernen, Home Assistant neu "
            "starten und die Übernahme danach erneut auslösen."
        )

    registry = er.async_get(hass)
    loaded = entity_sources(hass)
    result = MigrationResult()

    for old in find_core_entries(hass):
        serial = serial_from_unique_id(old.unique_id)
        if serial not in known_serials:
            result.skipped.append((old.entity_id, "Gerät gehört nicht zu diesem Cube"))
            continue
        if old.entity_id in loaded:
            result.skipped.append((old.entity_id, "Core-Entität ist noch aktiv"))
            continue
        ours = registry.async_get_entity_id(old.domain, DOMAIN, old.unique_id)
        if ours is None:
            result.skipped.append((old.entity_id, "keine passende Entität in MAX! Cube Evolution"))
            continue

        old_entity_id = old.entity_id
        customisations = _copied_fields(registry, old)

        registry.async_remove(old_entity_id)
        # The orphan usually still has a "restored" unavailable placeholder state,
        # which would block the entity ID from being reused.
        state = hass.states.get(old_entity_id)
        if state is not None and old_entity_id not in loaded:
            hass.states.async_remove(old_entity_id)

        try:
            registry.async_update_entity(ours, new_entity_id=old_entity_id, **customisations)
        except ValueError as exc:
            result.skipped.append((old_entity_id, f"Umbenennen fehlgeschlagen: {exc}"))
            _LOGGER.warning("Could not take over %s from %s: %s", old_entity_id, ours, exc)
            continue
        result.migrated.append((old_entity_id, ours))
        _LOGGER.info("Took over core entity %s (was %s)", old_entity_id, ours)

    return result


def format_result(result: MigrationResult) -> str:
    if not result.found:
        return "Es wurden keine Entitäten der Core-Integration „maxcube“ gefunden."
    lines = []
    if result.migrated:
        lines.append(f"**Übernommen: {len(result.migrated)}**")
        lines += [f"- `{old}` (bisher `{ours}`)" for old, ours in result.migrated]
    if result.skipped:
        if lines:
            lines.append("")
        lines.append(f"**Übersprungen: {len(result.skipped)}**")
        lines += [f"- `{entity_id}`: {reason}" for entity_id, reason in result.skipped]
    return "\n".join(lines)
