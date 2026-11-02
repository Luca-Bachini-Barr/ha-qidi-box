"""Helpers for the QIDI Box multi-filament feeder exposed through Moonraker.

The QIDI Box adds ``box_stepper slotN`` and ``box_extras`` objects to Klipper.
Newer firmware reports decoded per-slot details in ``box_extras.boxes[N]``
(``filament_info`` and ``dry_state``); older firmware only stores numeric codes
in ``save_variables`` and drying state in ``box_extras.box_drying_state``. The
lookup tables below mirror the printer's own ``officiall_filas_list.cfg``
(``[filaN]``, ``[colordict]`` and ``[vendor_list]`` sections) and are only used
to turn the older numeric codes into readable values.
"""

import re
from typing import Any

FILAMENTS = {
    1: "PLA Rapido",
    2: "PLA Matte",
    3: "PLA Metal",
    4: "PLA Silk",
    5: "PLA-CF",
    6: "PLA-Wood",
    7: "PLA Basic",
    8: "PLA Matte Basic",
    10: "Support For PLA",
    11: "ABS Rapido",
    12: "ABS-GF",
    13: "ABS-Metal",
    14: "ABS-Odorless",
    15: "TPU-GF",
    18: "ASA",
    19: "ASA-Aero",
    20: "ASA-CF",
    23: "PC",
    24: "UltraPA",
    25: "PA6-CF",
    26: "UltraPA-CF25",
    27: "PA12-CF",
    30: "PAHT-CF",
    31: "PAHT-GF",
    32: "Support For PAHT",
    33: "Support For PET/PA",
    34: "PC/ABS-FR",
    35: "TPEE",
    36: "PEBA",
    37: "PET-CF",
    38: "PET-GF",
    39: "PETG Basic",
    40: "PETG-Tough",
    41: "PETG Rapido",
    42: "PETG-CF",
    43: "PETG-GF",
    44: "PPS-CF",
    45: "PETG Translucent",
    46: "PPS-GF",
    47: "PVA",
    48: "TPU-AERO 64D",
    49: "TPU-Aero",
    50: "TPU 95A-HF",
}
COLORS = {
    1: "#FAFAFA",
    2: "#060606",
    3: "#D9E3ED",
    4: "#5CF30F",
    5: "#63E492",
    6: "#2850FF",
    7: "#FE98FE",
    8: "#DFD628",
    9: "#228332",
    10: "#99DEFF",
    11: "#1714B0",
    12: "#CEC0FE",
    13: "#CADE4B",
    14: "#1353AB",
    15: "#5EA9FD",
    16: "#A878FF",
    17: "#FE717A",
    18: "#FF362D",
    19: "#E2DFCD",
    20: "#898F9B",
    21: "#6E3812",
    22: "#CAC59F",
    23: "#F28636",
    24: "#B87F2B",
}
VENDORS = {
    0: "Generic",
    1: "QIDI",
}


_SLOT_RE = re.compile(r"^box_stepper slot(\d+)$")
_BOX_RE = re.compile(r"^box(\d+)$")
_BOX_HEATER_RE = re.compile(r"^heater_generic (heater_box\d+)$")

# Klipper objects outside the per-slot / per-heater ones that the Box reports through
BOX_OBJECTS = ("box_extras", "save_variables", "multi_color_controller")


def box_objects(objects: list[str]) -> list[str]:
    """Return the Klipper objects to query for the Box, from the printer's object list."""
    return [
        obj
        for obj in objects
        if obj in BOX_OBJECTS or _SLOT_RE.match(obj) or _BOX_HEATER_RE.match(obj)
    ]


def has_box(objects: list[str]) -> bool:
    """Return True when the printer reports a QIDI Box."""
    return "box_extras" in objects and any(_SLOT_RE.match(obj) for obj in objects)


def box_heater(obj: str) -> str | None:
    """Return the heater name (``heater_box1``) for a ``heater_generic heater_boxN`` object."""
    match = _BOX_HEATER_RE.match(obj)
    return match.group(1) if match else None


def slot_index(obj: str) -> int | None:
    """Return the slot number for a ``box_stepper slotN`` object, else None."""
    match = _SLOT_RE.match(obj)
    return int(match.group(1)) if match else None


def box_label(box_key: str) -> str:
    """Return a readable label such as ``Box 1`` for a ``box1`` key."""
    match = _BOX_RE.match(box_key)
    if match:
        return f"Box {match.group(1)}"
    return box_key.replace("_", " ").title()


SLOTS_PER_BOX = 4


def _variables(status: dict[str, Any]) -> dict[str, Any]:
    save_variables = status.get("save_variables")
    variables = (
        save_variables.get("variables") if isinstance(save_variables, dict) else None
    )
    return variables if isinstance(variables, dict) else {}


def _boxes(status: dict[str, Any]) -> list[Any]:
    extras = status.get("box_extras")
    boxes = extras.get("boxes") if isinstance(extras, dict) else None
    return boxes if isinstance(boxes, list) else []


def _box(status: dict[str, Any], number: int) -> dict[str, Any]:
    """Return box ``number`` (1-based) from ``box_extras.boxes``, else ``{}``."""
    boxes = _boxes(status)
    box = boxes[number - 1] if 0 < number <= len(boxes) else None
    return box if isinstance(box, dict) else {}


def _filament_info(status: dict[str, Any], index: int) -> dict[str, Any]:
    """Return the decoded ``filament_info`` entry for a slot, else ``{}``."""
    info = _box(status, index // SLOTS_PER_BOX + 1).get("filament_info")
    position = index % SLOTS_PER_BOX
    entry = info[position] if isinstance(info, list) and position < len(info) else None
    return entry if isinstance(entry, dict) else {}


def _lookup(table: dict[int, str], code: Any) -> str | None:
    return table.get(code) if isinstance(code, int) else None


def _hex_color(value: Any) -> str | None:
    """Return ``#RRGGBB`` from a colour id, hex string or list of hex strings."""
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, int):
        return _lookup(COLORS, value)
    if isinstance(value, str) and value:
        return value if value.startswith("#") else f"#{value}"
    return None


def slot_is_empty(status: dict[str, Any], index: int) -> bool:
    """Return True when the slot's runout switch reports no filament."""
    stepper = status.get(f"box_stepper slot{index}")
    return isinstance(stepper, dict) and stepper.get("runout_button") == 1


def slot_filament(status: dict[str, Any], index: int) -> str | None:
    """Return the filament name loaded in a slot, or ``Empty``."""
    if slot_is_empty(status, index):
        return "Empty"
    name = _filament_info(status, index).get("filament_str")
    if isinstance(name, str) and name:
        return name
    code = _variables(status).get(f"filament_slot{index}")
    if code is None:
        return None
    if isinstance(code, int):
        return FILAMENTS.get(code, f"Unknown ({code})")
    return str(code)


def slot_is_active(status: dict[str, Any], index: int) -> bool:
    """Return True when the slot is the one feeding the toolhead.

    ``save_variables.slotN == 2`` marks the feeding slot; ``box_extras.loaded_slot``
    (``slotN``, ``slot16`` = nothing / external spool) says the same on Box V2.
    """
    if _variables(status).get(f"slot{index}") == 2:
        return True
    loaded = slot_number(_section(status, "box_extras").get("loaded_slot"))
    return loaded == index + 1


def slot_attributes(status: dict[str, Any], index: int) -> dict[str, Any]:
    """Return decoded slot details for use as entity attributes.

    ``color`` is left out (None) for an empty slot: the printer keeps the last
    spool's colour, which would otherwise show a spool that is not there.
    """
    variables = _variables(status)
    info = _filament_info(status, index)
    color_id = variables.get(f"color_slot{index}")
    vendor = info.get("vendor_str")
    empty = slot_is_empty(status, index)
    return {
        "color": None
        if empty
        else _hex_color(info.get("color_rgb_str")) or _hex_color(color_id),
        "active": not empty and slot_is_active(status, index),
        "vendor": vendor
        if isinstance(vendor, str) and vendor
        else _lookup(VENDORS, variables.get(f"vendor_slot{index}")),
        "filament_id": info.get("filament_id", variables.get(f"filament_slot{index}")),
        "filament_type": info.get("filament_type"),
        "min_temp": info.get("min_temp"),
        "max_temp": info.get("max_temp"),
        "color_id": color_id,
        "slot_state": variables.get(f"slot{index}"),
        "runout": empty,
    }


def drying_box_keys(status: dict[str, Any]) -> list[str]:
    """Return keys such as ``box1`` for every box that reports drying state."""
    extras = status.get("box_extras")
    drying = extras.get("box_drying_state") if isinstance(extras, dict) else None
    if isinstance(drying, dict):
        return list(drying)
    return [
        f"box{number}"
        for number, box in enumerate(_boxes(status), start=1)
        if isinstance(box, dict) and box.get("is_online") and "dry_state" in box
    ]


def drying_active(status: dict[str, Any], box_key: str) -> bool:
    """Return True when the box reports a non-idle drying state."""
    extras = status.get("box_extras")
    drying = extras.get("box_drying_state") if isinstance(extras, dict) else None
    if isinstance(drying, dict):
        state = drying.get(box_key)
        return isinstance(state, dict) and bool(state.get("dry_state"))
    match = _BOX_RE.match(box_key)
    if not match:
        return False
    return bool(_box(status, int(match.group(1))).get("dry_state"))


# Filament changes on Box V2 firmware run as a ``multi_color_controller`` task
# whose queue is BOX_CUT -> BOX_UNLOAD -> BOX_LOAD. ``box_extras.is_tool_change``
# is set a few seconds before the task starts and stays set while the nozzle is
# purged afterwards. ``slot16`` is the external spool / "nothing loaded".
CHANGE_STEPS = {
    "BOX_CUT": "cutting",
    "BOX_UNLOAD": "unloading",
    "BOX_LOAD": "loading",
}
_SLOT_NAME_RE = re.compile(r"^slot(\d+)$")
EXTERNAL_SLOT = 16


def _section(status: dict[str, Any], *keys: str) -> dict[str, Any]:
    """Return a nested dict from ``status`` (``{}`` when missing or malformed)."""
    value: Any = status
    for key in keys:
        value = value.get(key) if isinstance(value, dict) else None
    return value if isinstance(value, dict) else {}


def slot_number(value: Any) -> int | None:
    """Return the 1-based slot number for ``slotN``, or None for ``slot16``."""
    match = _SLOT_NAME_RE.match(value) if isinstance(value, str) else None
    if not match or int(match.group(1)) >= EXTERNAL_SLOT:
        return None
    return int(match.group(1)) + 1


def _change_task(status: dict[str, Any]) -> dict[str, Any]:
    return _section(status, "multi_color_controller", "task")


def _change_active(task: dict[str, Any]) -> bool:
    return task.get("flow_id") is not None or bool(task.get("current_step"))


def filament_change_state(status: dict[str, Any]) -> str | None:
    """Return the current filament change step, ``changing`` or ``idle``."""
    if "multi_color_controller" not in status and "box_extras" not in status:
        return None
    task = _change_task(status)
    if _change_active(task):
        if task.get("is_paused"):
            return "paused"
        step = task.get("current_step")
        if not isinstance(step, str) or not step:
            return "starting"
        return CHANGE_STEPS.get(step, step.lower().removeprefix("box_"))
    if _section(status, "box_extras").get("is_tool_change"):
        return "changing"
    return "idle"


def box_warnings(status: dict[str, Any]) -> list[Any]:
    """Return the box warnings reported by ``multi_color_controller``."""
    warnings = _section(status, "multi_color_controller").get("box_warning_info")
    return warnings if isinstance(warnings, list) else []


def filament_change_attributes(status: dict[str, Any]) -> dict[str, Any]:
    """Return details of the running (or last) filament change."""
    task = _change_task(status)
    active = _change_active(task)
    operation = _section(status, "multi_color_controller", "operation")
    queue = task.get("current_queue")
    step = task.get("current_step")
    return {
        "step": step if isinstance(step, str) and step else None,
        "steps": queue if isinstance(queue, list) else [],
        "target_slot": slot_number(operation.get("active_slot")) if active else None,
        "loaded_slot": slot_number(_section(status, "box_extras").get("loaded_slot")),
        "flow_id": task.get("flow_id"),
        "tool_change": bool(_section(status, "box_extras").get("is_tool_change")),
        "warnings": box_warnings(status),
    }
