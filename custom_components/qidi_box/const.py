"""Constants for the QIDI Box integration."""

from homeassistant.const import Platform

DOMAIN = "qidi_box"
MOONRAKER_DOMAIN = "moonraker"

PLATFORMS = [Platform.BINARY_SENSOR, Platform.NUMBER, Platform.SENSOR]

# Config entry data: the Moonraker (marcolivierarsenault/moonraker-home-assistant)
# config entry whose printer has the Box. Its connection details are read from it.
CONF_MOONRAKER_ENTRY_ID = "moonraker_entry_id"
# Keys of the Moonraker config entry's data
MOONRAKER_CONF_URL = "url"
MOONRAKER_CONF_PORT = "port"
MOONRAKER_CONF_TLS = "tls"
MOONRAKER_CONF_API_KEY = "api_key"
MOONRAKER_DEFAULT_PORT = 7125

CONF_POLLING_RATE = "polling_rate"
DEFAULT_POLLING_RATE = 10
MIN_POLLING_RATE = 2
MAX_POLLING_RATE = 300

# Seconds between polls while a filament change runs, and for a while after a command
FAST_POLLING_RATE = 2
# Seconds to keep polling fast after a command, until the printer shows it
COMMAND_FAST_POLL_SECONDS = 30

# Seconds a command sent with wait=false waits for Klipper to reject it
GCODE_ACCEPT_TIMEOUT = 5
# Seconds a G-code script may run (a filament change takes about 2.5 min)
GCODE_TIMEOUT = 600
# Seconds for ordinary requests (object list and queries)
REQUEST_TIMEOUT = 10

# Filament change states during which the coordinator polls fast
IDLE_CHANGE_STATES = (None, "idle")

ATTR_DEVICE_ID = "device_id"
ATTR_GCODE = "gcode"
ATTR_WAIT = "wait"
ATTR_SLOT = "slot"
ATTR_COLOR = "color"
ATTR_VENDOR = "vendor"
ATTR_FILAMENT = "filament"

SERVICE_SEND_GCODE = "send_gcode"
SERVICE_LOAD = "load_filament"
SERVICE_UNLOAD = "unload_filament"
SERVICE_EJECT = "eject_filament"
SERVICE_SET_SLOT_FILAMENT = "set_slot_filament"

# Box slots are 1-based in Home Assistant (Box 1 = slots 1-4); the G-code takes
# the 0-based index as a bare integer (``SLOT=2``; ``SLOT=slot2`` fails to parse).
MAX_SLOT = 16
