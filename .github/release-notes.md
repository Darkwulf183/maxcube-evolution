Erste öffentliche Version.

### Installation
HACS → ⋮ → Benutzerdefinierte Repositories → `https://github.com/Darkwulf183/maxcube-evolution` (Typ: Integration). Danach Home Assistant neu starten. Details stehen in der README.

### Inhalt
- Thermostate, Ventilöffnung, Fensterkontakte und Batteriestatus für den eQ-3 MAX! Cube
- Echtes MAX!-Boost-Telegramm
- Parameter der Heizkörperthermostate einstellbar (Temperaturen, Offset, Fenster, Boost, Ventil)
- Cube-Diagnose: Funkauslastung, freie Speicherplätze, Befehlsfehler
- Automatische Suche, Dienste zum Neuverbinden und Neustarten
- Taste **Entitäten aus Core-Integration übernehmen**: übernimmt die Entitäts-IDs der Core-Integration `maxcube`, Automationen und Verlauf bleiben erhalten
- Eigene Icons im Ordner `brand/` (ab HA 2026.3)

### Korrekturen gegenüber den Vorabversionen (`maxcube_extended`)
- Kein Absturz mehr beim Setzen von Temperatur oder Modus, wenn der Cube gerade nicht verbunden ist
- TCP-Verbindung wird nach jeder Abfrage freigegeben, damit Diagnose und Parameter-Befehle nicht blockiert werden
- Cube-Gerät wird vor den Thermostaten angelegt
- Einrichtung zeigt „Keine Verbindung zum Cube möglich“ statt eines unbekannten Fehlers
- Übersetzungen werden angezeigt (Ordner `translations/`)
- Kompatibel mit neueren Home-Assistant-Versionen (`probatio`, `via_device_id`)

### Umstieg von `maxcube_extended`
Die interne Kennung heißt jetzt `maxcube_evolution`. Alte Integration löschen, Ordner `custom_components/maxcube_extended` entfernen, neu starten, dann diese Version installieren und den Cube neu einrichten.
