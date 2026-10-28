"""Verify actual Home Assistant flows and preservation of config entry data."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.data_entry_flow import FlowResultType, InvalidData

from custom_components.huawei_virtual_meter.const import DOMAIN

from .conftest import close_writer, read_request, read_response
from .test_lifecycle import connect_meter

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


async def options_step(hass, entry, step):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    return await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": step}
    )


@pytest.mark.parametrize("unit", [0, 1, 11, 255])
async def test_settings_preserve_data_and_register_options(hass, entry, unit):
    original_data = dict(entry.data)
    original_options = dict(entry.options)
    result = await options_step(hass, entry, "edit_settings")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"udp_port": 10086, "unit_id": unit}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "settings_saved"
    assert dict(entry.data) == {**original_data, "udp_port": 10086, "unit_id": unit}
    assert dict(entry.options) == original_options


@pytest.mark.parametrize(
    ("key", "value", "error"),
    [
        ("unit_id", -1, "invalid_unit_id"),
        ("unit_id", 256, "invalid_unit_id"),
        ("unit_id", "invalid", "invalid_unit_id"),
        ("udp_port", 0, "invalid_port"),
        ("udp_port", 65536, "invalid_port"),
        ("udp_port", "invalid", "invalid_port"),
    ],
)
async def test_invalid_settings_leave_entry_unchanged(hass, entry, key, value, error):
    before = dict(entry.data), dict(entry.options)
    result = await options_step(hass, entry, "edit_settings")
    # The real flow manager rejects invalid form schema data before the step runs.
    with pytest.raises(InvalidData):
        await hass.config_entries.options.async_configure(
            result["flow_id"], {"udp_port": 6600, "unit_id": 11, key: value}
        )
    assert (dict(entry.data), dict(entry.options)) == before


@pytest.mark.parametrize("key", ["unit_id", "udp_port"])
async def test_fractional_settings_are_not_truncated(hass, entry, key):
    before = dict(entry.data), dict(entry.options)
    result = await options_step(hass, entry, "edit_settings")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"udp_port": 6600, "unit_id": 11, key: 12.5}
    )
    assert result["type"] is FlowResultType.FORM
    assert key in result["errors"]
    assert (dict(entry.data), dict(entry.options)) == before


async def test_legacy_settings_form_keeps_any_unit_default(hass, entry):
    result = await options_step(hass, entry, "edit_settings")
    validated = result["data_schema"]({})
    assert validated["unit_id"] == 0
    assert validated["udp_port"] == 6600


async def test_settings_flow_reloads_live_entry_and_keeps_values(
    hass, entry, meter_sockets
):
    assert await hass.config_entries.async_setup(entry.entry_id)
    result = await options_step(hass, entry, "edit_settings")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"udp_port": 10086, "unit_id": 11}
    )
    assert result["reason"] == "settings_saved"
    await hass.async_block_till_done()
    assert meter_sockets == [6600, 10086]
    reader, writer = await connect_meter(hass, entry)
    writer.write(read_request())
    assert (await read_response(reader))[1][-2:] == b"\x05\xdc"
    await close_writer(writer)


async def test_edit_registers_keeps_other_options(hass, entry):
    result = await options_step(hass, entry, "edit_registers")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"fixed_value_37113": 2500, "factor_37113": 1}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {
        "retained_option": "keep",
        "registers": {"37113": {"fixed_value": 2500, "factor": 1}},
    }


async def test_add_register_keeps_other_options(hass, entry):
    result = await options_step(hass, entry, "add_register")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"address": "37101"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"fixed_value": 230, "factor": 10}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["retained_option"] == "keep"
    assert entry.options["registers"]["37113"]["fixed_value"] == 1500
    assert entry.options["registers"]["37101"] == {"fixed_value": 230, "factor": 10}


@pytest.mark.parametrize("address", ["-1", "65536", "invalid"])
async def test_invalid_register_address(hass, entry, address):
    result = await options_step(hass, entry, "add_register")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"address": address}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "invalid_address"


async def test_initial_flow(hass, meter_sockets):
    with patch(
        "custom_components.huawei_virtual_meter.config_flow.network.async_get_adapters",
        return_value=[{"name": "eth0", "ipv4": [{"address": "127.0.0.1"}]}],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
    validated = result["data_schema"]({})
    assert validated["unit_id"] == 11
    assert validated["udp_port"] == 6600
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], validated
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert result["result"].data["unit_id"] == 11


@pytest.mark.parametrize("serial", ["", "x" * 21, "ü", "line\nbreak"])
async def test_invalid_serial_does_not_create_entry(hass, serial):
    with (
        patch(
            "custom_components.huawei_virtual_meter.config_flow.network.async_get_adapters",
            return_value=[{"name": "eth0", "ipv4": [{"address": "127.0.0.1"}]}],
        ),
        patch(
            "custom_components.huawei_virtual_meter.async_setup_entry",
            new_callable=AsyncMock,
        ) as setup,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        with pytest.raises(InvalidData):
            await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {
                    "serial": serial,
                    "emulator_ip": "127.0.0.1",
                    "unit_id": 11,
                    "udp_port": 6600,
                },
            )
    setup.assert_not_called()
