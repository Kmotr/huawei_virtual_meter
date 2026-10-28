"""Bounded Modbus TCP framing and connection lifecycle.

Only plaintext Modbus TCP is supported. Transaction IDs are opaque: their
bytes must never be used to guess TLS or a proprietary authentication protocol.
"""

import asyncio
import contextlib
import logging
import struct
from collections.abc import Callable

_LOGGER = logging.getLogger(__name__)
REQUEST_TIMEOUT = 60
CLOSE_TIMEOUT = 5
MAX_MBAP_LENGTH = 254  # One unit byte plus a maximum 253-byte PDU.


class InvalidFrame(ValueError):
    """The stream does not contain a valid Modbus TCP ADU."""


async def _read_request(reader: asyncio.StreamReader) -> tuple[int, int, bytes]:
    """Read exactly one ADU, retaining subsequent ADUs in the stream buffer."""
    transaction_id, protocol_id, length = struct.unpack(
        ">HHH", await reader.readexactly(6)
    )
    if protocol_id != 0 or not 2 <= length <= MAX_MBAP_LENGTH:
        raise InvalidFrame("invalid MBAP protocol ID or length")
    body = await reader.readexactly(length)
    return transaction_id, body[0], body[1:]


def _response_pdu(pdu: bytes, values: dict[int, int], queried: set[int]) -> bytes:
    """Handle FC03/FC04 or return a Modbus exception PDU."""
    function = pdu[0]
    if function not in (3, 4):
        return bytes([function | 0x80, 1])  # Illegal function.
    if len(pdu) != 5:
        return bytes([function | 0x80, 3])  # Illegal data value.
    start, count = struct.unpack(">HH", pdu[1:])
    if not 1 <= count <= 125:
        return bytes([function | 0x80, 3])
    if start + count > 65536:
        return bytes([function | 0x80, 2])  # Illegal data address.
    queried.update(range(start, start + count))
    payload = b"".join(
        struct.pack(">H", values.get(address, 0) & 0xFFFF)
        for address in range(start, start + count)
    )
    return bytes([function, len(payload)]) + payload


class ModbusTCPServer:
    """Own the listener and every accepted client, including pending handlers."""

    def __init__(
        self,
        values: dict[int, int],
        queried: set[int],
        get_unit_id: Callable[[], int],
    ) -> None:
        self._values = values
        self._queried = queried
        self._get_unit_id = get_unit_id
        self._server: asyncio.Server | None = None
        self._writers: set[asyncio.StreamWriter] = set()
        self._tasks: set[asyncio.Task] = set()
        self._closing = False

    async def async_start(self, host: str, port: int) -> None:
        """Bind the Modbus listener."""
        self._server = await asyncio.start_server(self._client_connected, host, port)

    def _client_connected(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        # Register synchronously so unload cannot miss a just-accepted connection.
        self._writers.add(writer)
        if self._closing:
            writer.close()
        task = asyncio.create_task(self._handle_client(reader, writer))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            while not self._closing:
                transaction_id, unit_id, pdu = await asyncio.wait_for(
                    _read_request(reader), REQUEST_TIMEOUT
                )
                expected_unit_id = self._get_unit_id()
                # 0 means any unit ID, preserving pre-filter behaviour for old entries.
                if expected_unit_id and unit_id != expected_unit_id:
                    continue
                response = _response_pdu(pdu, self._values, self._queried)
                writer.write(
                    struct.pack(">HHHB", transaction_id, 0, len(response) + 1, unit_id)
                    + response
                )
                await asyncio.wait_for(writer.drain(), REQUEST_TIMEOUT)
        except InvalidFrame as err:
            _LOGGER.debug(
                "Closing non-Modbus or malformed connection from %s: %s; "
                "TLS and proprietary authentication are not supported",
                writer.get_extra_info("peername"),
                err,
            )
        except (asyncio.IncompleteReadError, TimeoutError, ConnectionError, OSError):
            pass
        finally:
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), CLOSE_TIMEOUT)
            except (TimeoutError, ConnectionError, OSError):
                writer.transport.abort()
            finally:
                self._writers.discard(writer)

    async def async_close(self) -> None:
        """Close all clients and finish their handlers before releasing the server."""
        self._closing = True
        if self._server is not None:
            self._server.close()
        for writer in tuple(self._writers):
            writer.close()
        tasks = tuple(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        # A task cancelled before its first instruction has no finally block.
        for writer in tuple(self._writers):
            with contextlib.suppress(TimeoutError, ConnectionError, OSError):
                await asyncio.wait_for(writer.wait_closed(), CLOSE_TIMEOUT)
            writer.transport.abort()
        self._writers.clear()
        if self._server is not None:
            await self._server.wait_closed()
            self._server = None
