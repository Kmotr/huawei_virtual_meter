"""Exercise framing and connection lifecycle over actual TCP streams."""

import asyncio
import struct
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.huawei_virtual_meter import modbus
from custom_components.huawei_virtual_meter.modbus import ModbusTCPServer

from .conftest import assert_disconnected, close_writer, read_request, read_response


@pytest.fixture
async def server():
    unit = {"id": 11}
    queried = set()
    meter = ModbusTCPServer({37113: 0, 37114: 1500}, queried, lambda: unit["id"])
    await meter.async_start("127.0.0.1", 0)
    address = meter._server.sockets[0].getsockname()
    reader, writer = await asyncio.open_connection(*address)
    yield meter, reader, writer, unit, queried
    writer.close()
    await meter.async_close()
    await close_writer(writer)


@pytest.mark.parametrize("transaction", [0, 1, 0xF600, 0xF6FF, 0x1603, 0xFFFF])
@pytest.mark.parametrize("function", [3, 4])
async def test_all_transaction_bytes_are_opaque(server, transaction, function):
    _, reader, writer, _, queried = server
    writer.write(read_request(transaction, function=function))
    assert await read_response(reader) == (
        transaction,
        bytes([11, function, 4, 0, 0, 5, 220]),
    )
    assert queried == {37113, 37114}


@pytest.mark.parametrize("split", range(1, 12))
async def test_fragmented_request(server, split):
    _, reader, writer, _, _ = server
    request = read_request()
    writer.write(request[:split])
    await writer.drain()
    # Give the server time to consume the incomplete ADU before the next write.
    await asyncio.sleep(0.01)
    writer.write(request[split:])
    assert await read_response(reader) == (1, b"\x0b\x03\x04\x00\x00\x05\xdc")


async def test_coalesced_requests(server):
    _, reader, writer, _, _ = server
    writer.write(read_request(1) + read_request(2, function=4))
    assert (await read_response(reader))[0] == 1
    assert (await read_response(reader))[0] == 2


@pytest.mark.parametrize("count", [0, 126, 128, 65535])
async def test_invalid_counts_return_exception_and_keep_connection(server, count):
    _, reader, writer, _, _ = server
    writer.write(read_request(1, count=count) + read_request(2))
    assert await read_response(reader) == (1, b"\x0b\x83\x03")
    assert (await read_response(reader))[0] == 2


async def test_address_overflow(server):
    _, reader, writer, _, _ = server
    writer.write(read_request(start=65535, count=2))
    assert await read_response(reader) == (1, b"\x0b\x83\x02")


async def test_maximum_read(server):
    _, reader, writer, _, _ = server
    writer.write(read_request(start=0, count=125))
    assert await read_response(reader) == (1, b"\x0b\x03\xfa" + bytes(250))


@pytest.mark.parametrize("pdu", [b"\x03", b"\x03\x00\x01\x00\x01\x00"])
async def test_invalid_read_pdu_size(server, pdu):
    _, reader, writer, _, _ = server
    writer.write(struct.pack(">HHHB", 1, 0, len(pdu) + 1, 11) + pdu)
    assert await read_response(reader) == (1, b"\x0b\x83\x03")


async def test_unsupported_function(server):
    _, reader, writer, _, _ = server
    writer.write(read_request(function=6))
    assert await read_response(reader) == (1, b"\x0b\x86\x01")


@pytest.mark.parametrize(
    "header",
    [
        struct.pack(">HHH", 1, 1, 6),
        *[struct.pack(">HHH", 1, 0, n) for n in (0, 1, 255, 65535)],
        b"\x16\x03\x01\x00\x45\x01",  # A TLS record is not Modbus.
        b"\xf6\x00\x01\x02\x03\x04",  # Unknown proprietary format.
    ],
)
async def test_invalid_mbap_is_closed(server, header):
    _, reader, writer, _, queried = server
    writer.write(header)
    assert await asyncio.wait_for(reader.read(), 2) == b""
    assert not queried


async def test_unit_filter_changes_on_existing_connection(server):
    _, reader, writer, unit, _ = server
    writer.write(read_request(1, unit=1) + read_request(2, unit=11))
    assert (await read_response(reader))[0] == 2
    unit["id"] = 1
    writer.write(read_request(3, unit=11) + read_request(4, unit=1))
    assert await read_response(reader) == (4, b"\x01\x03\x04\x00\x00\x05\xdc")


@pytest.mark.parametrize("unit_id", [0, 1, 11, 247, 255])
async def test_legacy_any_unit_mode(server, unit_id):
    _, reader, writer, unit, _ = server
    unit["id"] = 0
    writer.write(read_request(unit=unit_id))
    assert (await read_response(reader))[1][0] == unit_id


async def test_unload_closes_idle_and_partial_clients(server):
    meter, reader, writer, _, _ = server
    address = meter._server.sockets[0].getsockname()
    reader2, writer2 = await asyncio.open_connection(*address)
    writer.write(read_request()[:8])
    await writer.drain()
    await meter.async_close()
    await assert_disconnected(reader)
    await assert_disconnected(reader2)
    assert not meter._writers
    assert not meter._tasks
    await close_writer(writer2)


async def test_close_before_handler_starts():
    meter = ModbusTCPServer({}, set(), lambda: 0)
    writer = Mock()
    writer.wait_closed = AsyncMock()
    meter._client_connected(asyncio.StreamReader(), writer)
    await meter.async_close()
    writer.close.assert_called()
    writer.wait_closed.assert_awaited()
    assert not meter._writers
    assert not meter._tasks


async def test_incomplete_frame_times_out(monkeypatch):
    monkeypatch.setattr(modbus, "REQUEST_TIMEOUT", 0.02)
    meter = ModbusTCPServer({}, set(), lambda: 0)
    await meter.async_start("127.0.0.1", 0)
    reader, writer = await asyncio.open_connection(
        *meter._server.sockets[0].getsockname()
    )
    try:
        writer.write(read_request()[:8])
        await assert_disconnected(reader)
    finally:
        await close_writer(writer)
        await meter.async_close()
