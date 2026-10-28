"""Catch the register-factor discrepancies found in the original PR."""

import json
from pathlib import Path

from custom_components.huawei_virtual_meter.const import METER_REGISTERS

ROOT = Path(__file__).resolve().parents[1]


def test_documented_register_types_widths_and_gains_match_defaults():
    rows = {}
    for line in (ROOT / "README.md").read_text().splitlines():
        cells = [cell.strip() for cell in line.split("|")]
        if len(cells) == 8 and cells[1].isdigit():
            rows[int(cells[1])] = (cells[3], int(cells[4]), int(cells[5]))
    assert rows == {
        address: (definition["type"], definition["width"], definition["gain"])
        for address, definition in METER_REGISTERS.items()
    }


def test_translation_keys_match():
    def keys(value):
        if isinstance(value, dict):
            return {key: keys(item) for key, item in value.items()}
        return None

    directory = ROOT / "custom_components/huawei_virtual_meter/translations"
    assert keys(json.loads((directory / "de.json").read_text())) == keys(
        json.loads((directory / "en.json").read_text())
    )
