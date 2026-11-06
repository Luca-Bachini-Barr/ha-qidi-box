# QIDI Box for Moonraker

A Home Assistant integration that adds the **QIDI Box** (QIDI's multi-filament feeder, e.g. on the Q2 / Plus4) to a printer set up with the [Moonraker integration](https://github.com/marcolivierarsenault/moonraker-home-assistant).

It does not replace the Moonraker integration: it reads the printer's address from the Moonraker config entry, talks to Moonraker itself, and puts its entities **on the existing printer device**, next to the printer's own sensors.

## Entities

| Entity | What it shows |
|---|---|
| `sensor.<printer>_box_slot_N_filament` | Filament name in slot N, or `Empty`. Attributes: `color` (`#RRGGBB`, left out for an empty slot), `active` (the slot feeding the toolhead), `vendor`, `filament_id`, `filament_type`, `min_temp`, `max_temp`, `slot_state`, `runout` |
| `binary_sensor.<printer>_box_N_drying` | On while box N dries filament |
| `sensor.<printer>_box_filament_change` | `idle`, or the step of a running change (`starting`, `heat`, `cutting`, `unloading`, `loading`, `wipe`, `eject`, `paused`, `changing`). Attributes: `target_slot`, `loaded_slot` (1-based), `step`, `steps`, `flow_id`, `tool_change`, `warnings` |
| `sensor.<printer>_box_warnings` | Number of Box warnings, the list in `warnings` |
| `number.<printer>_heater_box1_target` | Box heater (drying) target, 0 = off |

Slots are numbered from 1: slots 1-4 are Box 1 (1A-1D), 5-8 Box 2, and so on.

The `color` and `active` attributes follow the convention other tools use for multi-material units (for example the 3D printer card of [NextFloor](https://github.com/therealMRBK/NextFloor) shows the active slot's colour first).

## Actions

| Action | G-code sent |
|---|---|
| `qidi_box.load_filament` (device, slot) | `LOAD_FILAMENT_CONTROL SLOT=<slot-1>` |
| `qidi_box.unload_filament` (device, slot) | `UNLOAD_FILAMENT_CONTROL SLOT=<slot-1>` |
| `qidi_box.eject_filament` (device, slot) | `EJECT_FILAMENT_CONTROL SLOT=<slot-1>` |
| `qidi_box.set_slot_filament` (device, slot, color, vendor, filament) | `UPDATE_FILAMENT_INFORMATION SLOT=<slot-1> COLOR='<hex>' VENDOR='<vendor>' FILAMENT='<name>'` |
| `qidi_box.send_gcode` (device, gcode, wait) | the G-code |

These are the commands the printer's touchscreen sends. A load/unload/eject runs for about 2.5 minutes, so these actions return once Klipper has accepted the command (a few seconds) instead of waiting; an error Klipper reports straight away is raised, a later one is logged. `send_gcode` waits for the command unless `wait: false`, and raises Klipper's error message when a command fails.

`filament` is the filament **name** from the printer's list (`PLA Basic`), not its id (`QFA00`).

## Polling

The Box is polled every 10 s (configurable), every 2 s while a filament change runs and for 30 s after a command. While the printer is switched off, or is on without its Box, the entities are unavailable and nothing is logged.

## Installation

1. Set the printer up with the Moonraker integration.
2. HACS → ⋮ → Custom repositories → `https://github.com/Luca-Bachini-Barr/ha-qidi-box`, type *Integration* → download, restart Home Assistant.
3. Settings → Devices & services → Add integration → **QIDI Box for Moonraker**, and choose the printer.

Requires Home Assistant 2026.8 or newer.

## Development

```
uv venv --python 3.14 && uv pip install pytest-homeassistant-custom-component pytest-cov
pytest --cov=custom_components.qidi_box
```

The test data in `tests/q2_status.json` is a real Q2 with one Box.
