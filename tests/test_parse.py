"""Decoding the Box's Klipper objects."""

from custom_components.qidi_box.parse import (
    box_heater,
    box_label,
    box_objects,
    box_warnings,
    drying_active,
    drying_box_keys,
    filament_change_attributes,
    filament_change_state,
    has_box,
    slot_attributes,
    slot_filament,
    slot_index,
    slot_is_active,
    slot_number,
)

from .conftest import OBJECTS, q2_status


def test_objects() -> None:
    """Only the Box's objects are queried, and a Box is recognised."""
    assert box_objects(OBJECTS) == [
        "box_extras",
        "save_variables",
        "multi_color_controller",
        "box_stepper slot0",
        "box_stepper slot1",
        "box_stepper slot2",
        "box_stepper slot3",
        "heater_generic heater_box1",
    ]
    assert has_box(OBJECTS)
    assert not has_box(["extruder", "box_extras"])
    assert not has_box(["box_stepper slot0"])
    assert box_heater("heater_generic heater_box1") == "heater_box1"
    assert box_heater("heater_generic chamber") is None
    assert slot_index("box_stepper slot3") == 3
    assert slot_index("box_extras") is None
    assert box_label("box2") == "Box 2"
    assert box_label("odd_key") == "Odd Key"


def test_q2_slots() -> None:
    """Real Q2 data: 1A/1B empty without a colour, 1C/1D black PLA Basic."""
    status = q2_status()
    assert [slot_filament(status, i) for i in range(4)] == [
        "Empty",
        "Empty",
        "PLA Basic",
        "PLA Basic",
    ]
    empty = slot_attributes(status, 0)
    assert empty["color"] is None
    assert empty["active"] is False
    assert empty["runout"] is True
    loaded = slot_attributes(status, 2)
    assert loaded["color"] == "#060606"
    assert loaded["vendor"] == "QIDI"
    assert loaded["filament_type"] == "PLA"
    assert loaded["runout"] is False
    # nothing in the toolhead (loaded_slot slot16)
    assert not any(slot_is_active(status, i) for i in range(4))


def test_active_slot() -> None:
    """The slot feeding the toolhead is active (slotN == 2 or box_extras.loaded_slot)."""
    status = q2_status()
    status["save_variables"]["variables"]["slot2"] = 2
    assert slot_attributes(status, 2)["active"] is True
    assert slot_attributes(status, 3)["active"] is False

    status = q2_status()
    status["box_extras"]["loaded_slot"] = "slot3"
    assert slot_attributes(status, 3)["active"] is True
    assert slot_attributes(status, 2)["active"] is False

    # an empty slot is never active
    status["box_extras"]["loaded_slot"] = "slot0"
    assert slot_attributes(status, 0)["active"] is False


def test_old_firmware_codes() -> None:
    """Older firmware: numeric codes in save_variables only."""
    status = {
        "save_variables": {
            "variables": {
                "filament_slot0": 7,
                "color_slot0": 18,
                "vendor_slot0": 1,
                "filament_slot1": 99,
                "filament_slot2": "QFA00",
            }
        },
        "box_stepper slot0": {"runout_button": 0},
    }
    assert slot_filament(status, 0) == "PLA Basic"
    attrs = slot_attributes(status, 0)
    assert attrs["color"] == "#FF362D"
    assert attrs["vendor"] == "QIDI"
    assert slot_filament(status, 1) == "Unknown (99)"
    assert slot_filament(status, 2) == "QFA00"
    assert slot_filament(status, 3) is None
    assert slot_attributes(status, 3)["color"] is None


def test_colors() -> None:
    """Colours come as a list of hex, a hex string or a palette id."""
    status = q2_status()
    info = status["box_extras"]["boxes"][0].setdefault("filament_info", [{}] * 4)
    info[2] = {"color_rgb_str": "abcdef", "filament_str": "PETG"}
    assert slot_attributes(status, 2)["color"] == "#abcdef"
    assert slot_filament(status, 2) == "PETG"


def test_drying() -> None:
    """Drying comes from boxes[N].dry_state, or box_drying_state on old firmware."""
    status = q2_status()
    assert drying_box_keys(status) == ["box1"]
    assert drying_active(status, "box1") is False
    status["box_extras"]["boxes"][0]["dry_state"] = 1
    assert drying_active(status, "box1") is True
    assert drying_active(status, "nonsense") is False

    old = {"box_extras": {"box_drying_state": {"box1": {"dry_state": 1}}}}
    assert drying_box_keys(old) == ["box1"]
    assert drying_active(old, "box1") is True


def test_filament_change() -> None:
    """A change's steps, target and loaded slot."""
    status = q2_status()
    assert filament_change_state(status) == "idle"
    assert filament_change_state({}) is None

    status["multi_color_controller"]["task"] = {
        "flow_id": 7,
        "current_queue": ["BOX_CUT", "BOX_UNLOAD", "BOX_LOAD"],
        "current_step": "BOX_UNLOAD",
        "is_paused": False,
    }
    status["multi_color_controller"]["operation"] = {"active_slot": "slot0"}
    status["box_extras"]["loaded_slot"] = "slot2"
    assert filament_change_state(status) == "unloading"
    attrs = filament_change_attributes(status)
    assert attrs["target_slot"] == 1
    assert attrs["loaded_slot"] == 3
    assert attrs["steps"] == ["BOX_CUT", "BOX_UNLOAD", "BOX_LOAD"]

    status["multi_color_controller"]["task"]["is_paused"] = True
    assert filament_change_state(status) == "paused"
    status["multi_color_controller"]["task"].update(is_paused=False, current_step="")
    assert filament_change_state(status) == "starting"
    status["multi_color_controller"]["task"]["current_step"] = "BOX_HEAT"
    assert filament_change_state(status) == "heat"

    status = q2_status()
    status["box_extras"]["is_tool_change"] = 1
    assert filament_change_state(status) == "changing"
    assert slot_number("slot16") is None
    assert slot_number(None) is None


def test_warnings() -> None:
    """Box warnings."""
    status = q2_status()
    status["multi_color_controller"]["box_warning_info"] = [{"code": 1}]
    assert box_warnings(status) == [{"code": 1}]
    assert box_warnings({}) == []
