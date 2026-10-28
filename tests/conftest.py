"""Use real HA config entries and real sockets bound only to loopback."""

import asyncio
import contextlib
import struct
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.huawei_virtual_meter.const import DOMAIN


@pytest.fixture(autouse=True)
def allow_loopback_sockets(socket_enabled):
    """The network tests explicitly bind to 127.0.0.1 and ephemeral ports."""


@pytest.fixture
def entry(hass):
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={"serial": "HV0000000001", "emulator_ip": "127.0.0.1"},
        options={
            "registers": {
                "37113": {"fixed_value": 1500, "factor": 1},
                "2001": {"fixed_value": 99, "factor": 1},
            },
            "retained_option": "keep",
        },
    )
    config_entry.add_to_hass(hass)
    return config_entry


@pytest.fixture
def meter_sockets(hass, enable_custom_integrations):
    """Run production setup/unload but redirect binds away from privileged ports."""
    start_server = asyncio.start_server
    create_endpoint = hass.loop.create_datagram_endpoint
    bound_udp_ports = []

    async def bind_tcp(callback, host, port):
        return await start_server(callback, "127.0.0.1", 0)

    async def bind_udp(factory, *, local_addr, allow_broadcast):
        bound_udp_ports.append(local_addr[1])
        return await create_endpoint(
            factory, local_addr=("127.0.0.1", 0), allow_broadcast=allow_broadcast
        )

    with (
        patch("asyncio.start_server", side_effect=bind_tcp),
        patch.object(hass.loop, "create_datagram_endpoint", side_effect=bind_udp),
    ):
        yield bound_udp_ports


def read_request(transaction=1, *, unit=11, function=3, start=37113, count=2):
    """Build a standard register-read ADU."""
    return struct.pack(">HHHBBHH", transaction, 0, 6, unit, function, start, count)


async def read_response(reader):
    """Read exactly one response, with a bounded wait on test failures."""
    header = await asyncio.wait_for(reader.readexactly(6), 2)
    transaction, protocol, length = struct.unpack(">HHH", header)
    assert protocol == 0
    body = await asyncio.wait_for(reader.readexactly(length), 2)
    return transaction, body


async def assert_disconnected(reader):
    """EOF or a TCP reset both prove that unload released the client socket."""
    try:
        assert await asyncio.wait_for(reader.read(), 2) == b""
    except ConnectionError:
        pass


async def close_writer(writer):
    writer.close()
    with contextlib.suppress(ConnectionError):
        await writer.wait_closed()
