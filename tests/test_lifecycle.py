"""Run setup, reload and failure cleanup through Home Assistant's entry manager."""

import asyncio
import errno
import socket
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import EVENT_HOMEASSISTANT_STOP

from custom_components.huawei_virtual_meter import async_setup_entry
from custom_components.huawei_virtual_meter.const import DOMAIN

from .conftest import assert_disconnected, close_writer, read_request, read_response

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


def runtime(hass, entry):
    return hass.data[DOMAIN][entry.entry_id]


async def connect_meter(hass, entry):
    server = runtime(hass, entry)["server"]._server
    return await asyncio.open_connection(*server.sockets[0].getsockname())


async def test_unload_releases_clients_listeners_and_both_ports(
    hass, entry, meter_sockets
):
    hass.states.async_set("sensor.power", "500")
    hass.config_entries.async_update_entry(
        entry,
        options={"registers": {"37113": {"entity_id": "sensor.power", "factor": 1}}},
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    data = runtime(hass, entry)
    tcp_address = data["server"]._server.sockets[0].getsockname()
    udp_address = data["udp"].get_extra_info("sockname")
    reader, writer = await connect_meter(hass, entry)
    writer.write(read_request())
    assert (await read_response(reader))[1][-2:] == b"\x01\xf4"
    assert await hass.config_entries.async_unload(entry.entry_id)
    await assert_disconnected(reader)
    assert not data["listeners"]
    assert not entry.update_listeners
    assert entry.entry_id not in hass.data[DOMAIN]
    hass.states.async_set("sensor.power", "600")
    await hass.async_block_till_done()
    assert data["modbus_values"][37114] == 500  # No stale listener updates this map.
    with socket.socket() as tcp, socket.socket(type=socket.SOCK_DGRAM) as udp:
        tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        tcp.bind(tcp_address)
        udp.bind(udp_address)
    await close_writer(writer)


async def test_shutdown_closes_partial_connection(hass, entry, meter_sockets):
    assert await hass.config_entries.async_setup(entry.entry_id)
    data = runtime(hass, entry)
    reader, writer = await connect_meter(hass, entry)
    writer.write(read_request()[:6])
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
    await hass.async_block_till_done()
    await assert_disconnected(reader)
    assert not data["server"]._tasks
    assert data["udp"] is None
    assert await hass.config_entries.async_unload(entry.entry_id)
    await close_writer(writer)


@pytest.mark.parametrize("failure", ["udp", "tcp"])
async def test_repeated_bind_failure_leaves_no_tasks_or_state_listeners(
    hass, entry, meter_sockets, failure
):
    hass.states.async_set("sensor.power", "500")
    hass.config_entries.async_update_entry(
        entry,
        options={"registers": {"37113": {"entity_id": "sensor.power", "factor": 1}}},
    )
    baseline = hass.bus.async_listeners().get("state_changed", 0)
    path = (
        "custom_components.huawei_virtual_meter.modbus.asyncio.start_server"
        if failure == "tcp"
        else None
    )
    fail = AsyncMock(side_effect=OSError(errno.EADDRINUSE, "test port occupied"))
    active_tasks = set(asyncio.all_tasks())
    for _ in range(2):
        context = (
            patch(path, fail)
            if path
            else patch.object(hass.loop, "create_datagram_endpoint", fail)
        )
        with context:
            assert not await hass.config_entries.async_setup(entry.entry_id)
        assert entry.state is ConfigEntryState.SETUP_RETRY
        entry.async_cancel_retry_setup()
        assert entry.entry_id not in hass.data[DOMAIN]
        assert hass.bus.async_listeners().get("state_changed", 0) == baseline
        assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert not [
        task
        for task in asyncio.all_tasks() - active_tasks
        if "huawei_virtual_meter" in repr(task.get_coro())
    ]
    # A subsequent successful setup must still work.
    assert await hass.config_entries.async_setup(entry.entry_id)
    reader, writer = await connect_meter(hass, entry)
    writer.write(read_request())
    assert (await read_response(reader))[1][-2:] == b"\x01\xf4"
    await close_writer(writer)


async def test_legacy_entry_and_dynamic_unit_changes(hass, entry, meter_sockets):
    assert "unit_id" not in entry.data
    assert await hass.config_entries.async_setup(entry.entry_id)
    reader, writer = await connect_meter(hass, entry)
    writer.write(read_request(unit=1))
    assert (await read_response(reader))[1][0] == 1
    with patch.object(
        hass.config_entries, "async_reload", new_callable=AsyncMock
    ) as reload:
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, "unit_id": 11}
        )
        await hass.async_block_till_done()
        reload.assert_not_called()
    writer.write(read_request(2, unit=1) + read_request(3, unit=11))
    assert (await read_response(reader))[0] == 3
    await close_writer(writer)


async def test_port_change_reloads_once_and_preserves_registers(
    hass, entry, meter_sockets
):
    assert await hass.config_entries.async_setup(entry.entry_id)
    reader, writer = await connect_meter(hass, entry)
    original_options = dict(entry.options)
    actual_reload = hass.config_entries.async_reload
    with patch.object(
        hass.config_entries, "async_reload", wraps=actual_reload
    ) as reload:
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, "udp_port": 10086}
        )
        # A second notification before the reload runs must not create a second reload.
        hass.config_entries.async_update_entry(
            entry, options={**entry.options, "extra": 1}
        )
        await hass.async_block_till_done()
        assert reload.await_count == 1
    assert meter_sockets == [6600, 10086]
    assert entry.options["registers"] == original_options["registers"]
    assert entry.options["retained_option"] == "keep"
    await assert_disconnected(reader)
    await close_writer(writer)
    reader, writer = await connect_meter(hass, entry)
    writer.write(read_request())
    assert (await read_response(reader))[1][-2:] == b"\x05\xdc"
    await close_writer(writer)


async def test_register_deletion_clears_values_without_reload(
    hass, entry, meter_sockets
):
    assert await hass.config_entries.async_setup(entry.entry_id)
    reader, writer = await connect_meter(hass, entry)
    with patch.object(
        hass.config_entries, "async_reload", new_callable=AsyncMock
    ) as reload:
        hass.config_entries.async_update_entry(entry, options={"registers": {}})
        await hass.async_block_till_done()
        reload.assert_not_called()
    writer.write(read_request())
    assert (await read_response(reader))[1] == b"\x0b\x03\x04\x00\x00\x00\x00"
    await close_writer(writer)


async def test_no_unsolicited_header_or_detection_values(hass, entry, meter_sockets):
    assert await hass.config_entries.async_setup(entry.entry_id)
    reader, writer = await connect_meter(hass, entry)
    writer.write(
        read_request(1, start=0, count=53) + read_request(2, start=2001, count=1)
    )
    assert (await read_response(reader))[1][3:] == bytes(106)
    assert await read_response(reader) == (2, b"\x0b\x03\x02\x00\x63")
    # Rebuilding mappings must not seed automatic values over custom registers.
    hass.config_entries.async_update_entry(entry, data={**entry.data, "unit_id": 11})
    await hass.async_block_till_done()
    writer.write(read_request(3, start=2001, count=1))
    assert await read_response(reader) == (3, b"\x0b\x03\x02\x00\x63")
    await close_writer(writer)


async def test_udp_discovery_reply_on_configured_listener(hass, entry, meter_sockets):
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, "udp_port": 10086}
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    address = runtime(hass, entry)["udp"].get_extra_info("sockname")
    with socket.socket(type=socket.SOCK_DGRAM) as client:
        client.setblocking(False)
        await hass.loop.sock_sendto(client, b"\x5a\x5a\x5a\x5a\x00\x41\x3a", address)
        reply = await asyncio.wait_for(hass.loop.sock_recv(client, 1024), 2)
    assert meter_sockets == [10086]
    assert reply.startswith(b"\x5a\x5a\x5a\x5a\x00\x41\x3a\x2f\x00")
    assert len(reply) == 55
    assert reply[9:29] == b"HV0000000001".ljust(20, b"\x00")


async def test_cancelled_setup_closes_udp_and_state_listeners(
    hass, entry, meter_sockets
):
    hass.states.async_set("sensor.power", "500")
    hass.config_entries.async_update_entry(
        entry,
        options={"registers": {"37113": {"entity_id": "sensor.power", "factor": 1}}},
    )
    baseline = hass.bus.async_listeners().get("state_changed", 0)
    entered_tcp_start = asyncio.Event()
    udp_address = None

    async def cancel_during_tcp_bind(*args, **kwargs):
        nonlocal udp_address
        udp_address = runtime(hass, entry)["udp"].get_extra_info("sockname")
        entered_tcp_start.set()
        await asyncio.Event().wait()

    with patch("asyncio.start_server", side_effect=cancel_during_tcp_bind):
        setup = asyncio.create_task(async_setup_entry(hass, entry))
        await asyncio.wait_for(entered_tcp_start.wait(), 2)
        setup.cancel()
        with pytest.raises(asyncio.CancelledError):
            await setup
    assert entry.entry_id not in hass.data[DOMAIN]
    assert hass.bus.async_listeners().get("state_changed", 0) == baseline
    with socket.socket(type=socket.SOCK_DGRAM) as udp:
        udp.bind(udp_address)
