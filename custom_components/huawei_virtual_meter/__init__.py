"""Huawei virtual meter setup, register mapping and resource lifecycle."""

import asyncio
import contextlib
import ipaddress
import logging
import struct

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    ANY_UNIT_ID,
    CONF_EMULATOR_IP,
    CONF_REGISTERS,
    CONF_SERIAL,
    CONF_UDP_PORT,
    CONF_UNIT_ID,
    DEFAULT_PORT,
    DEFAULT_UDP_PORT,
    DOMAIN,
    METER_REGISTERS,
)
from .modbus import ModbusTCPServer

_LOGGER = logging.getLogger(__name__)
MAGIC = b"\x5a\x5a\x5a\x5a"
APP_MAGIC = b"\x00\x41\x3a"


class VirtualMeterUDP(asyncio.DatagramProtocol):
    """Respond to the existing Huawei discovery format on a configurable port."""

    def __init__(self, entry: ConfigEntry) -> None:
        self.entry = entry
        self.closed = asyncio.Event()

    def connection_made(self, transport):
        self.transport = transport

    def connection_lost(self, exc):
        self.closed.set()

    def datagram_received(self, data, addr):
        if not data.startswith(MAGIC + APP_MAGIC):
            return
        try:
            response = (
                MAGIC
                + APP_MAGIC
                + b"\x2f\x00"
                + self.entry.data[CONF_SERIAL].encode().ljust(20, b"\x00")
                + b"\x00\x05\x00\x01\x02\x00\xf6\x01\x05\x01\x64\x07\x01\x00\x08\x04"
                + ipaddress.IPv4Address(self.entry.data[CONF_EMULATOR_IP]).packed[::-1]
                + b"\x0a\x04\x00\x00\x00\x00"
            )
            self.transport.sendto(response, addr)
            _LOGGER.debug("Discovery response sent to %s", addr)
        except (ValueError, OSError) as err:
            _LOGGER.warning("Unable to send discovery response: %s", err)


async def _async_close_resources(entry_data: dict) -> None:
    """Clean up successful and partially completed setup, shutdown or unload."""
    async with entry_data["close_lock"]:
        entry_data["closed"] = True
        for unsubscribe in entry_data["listeners"]:
            unsubscribe()
        entry_data["listeners"].clear()
        await entry_data["server"].async_close()
        if entry_data["udp"] is not None:
            entry_data["udp"].close()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(entry_data["udp_protocol"].closed.wait(), 5)
            entry_data["udp"] = None


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Start listeners transactionally; leave no resources behind on failure."""
    hass.data.setdefault(DOMAIN, {})
    entry_data = {
        "modbus_values": {},
        "listeners": [],
        "udp": None,
        "udp_protocol": VirtualMeterUDP(entry),
        "queried_registers": set(),
        "close_lock": asyncio.Lock(),
        "closed": False,
        "reload_requested": False,
    }
    entry_data["server"] = ModbusTCPServer(
        entry_data["modbus_values"],
        entry_data["queried_registers"],
        lambda: entry.data.get(CONF_UNIT_ID, ANY_UNIT_ID),
    )
    hass.data[DOMAIN][entry.entry_id] = entry_data

    def update_register_map():
        for unsub in entry_data["listeners"]:
            unsub()
        entry_data["listeners"] = []

        # Rebuild in place: the server keeps a reference to this dictionary.
        # Removed mappings must not keep serving stale values.
        entry_data["modbus_values"].clear()
        registers_config = entry.options.get(CONF_REGISTERS, {})

        def _set_modbus_value(addr, raw_val):
            reg_def = METER_REGISTERS.get(addr)
            if reg_def:
                if reg_def["width"] == 2:
                    if reg_def["type"] == "INT32":
                        raw_val = max(min(int(raw_val), 2147483647), -2147483648)
                        packed = struct.pack(">i", raw_val)
                    else:
                        raw_val = max(min(int(raw_val), 4294967295), 0)
                        packed = struct.pack(">I", raw_val)
                    high, low = struct.unpack(">HH", packed)
                    entry_data["modbus_values"][addr] = high
                    entry_data["modbus_values"][addr + 1] = low
                else:
                    if reg_def["type"] == "INT16":
                        raw_val = max(min(int(raw_val), 32767), -32768)
                        packed = struct.pack(">h", raw_val)
                    else:
                        raw_val = max(min(int(raw_val), 65535), 0)
                        packed = struct.pack(">H", raw_val)
                    entry_data["modbus_values"][addr] = struct.unpack(">H", packed)[0]
            else:
                entry_data["modbus_values"][addr] = int(raw_val) & 0xFFFF

        @callback
        def _state_changed_event(event):
            entity_id = event.data["entity_id"]
            new_state = event.data.get("new_state")
            if new_state is None or new_state.state in (None, "unknown", "unavailable"):
                return
            try:
                val = float(new_state.state)
                for addr_str, conf in registers_config.items():
                    if conf.get("entity_id") == entity_id:
                        _set_modbus_value(int(addr_str), val * conf.get("factor", 1.0))
            except (ValueError, TypeError, OverflowError):
                pass

        entities_to_track = set()
        for addr_str, conf in registers_config.items():
            if "entity_id" in conf:
                entities_to_track.add(conf["entity_id"])
            elif "fixed_value" in conf:
                _set_modbus_value(
                    int(addr_str), conf["fixed_value"] * conf.get("factor", 1.0)
                )
        for eid in entities_to_track:
            unsub = async_track_state_change_event(hass, eid, _state_changed_event)
            entry_data["listeners"].append(unsub)

            state = hass.states.get(eid)
            if state and state.state not in ("unknown", "unavailable"):
                try:
                    val = float(state.state)
                    for addr_str, conf in registers_config.items():
                        if conf.get("entity_id") == eid:
                            _set_modbus_value(
                                int(addr_str), val * conf.get("factor", 1.0)
                            )
                except (ValueError, TypeError, OverflowError):
                    continue

    udp_port = entry.data.get(CONF_UDP_PORT, DEFAULT_UDP_PORT)
    try:
        update_register_map()
        try:
            transport, _ = await asyncio.get_running_loop().create_datagram_endpoint(
                lambda: entry_data["udp_protocol"],
                local_addr=("0.0.0.0", udp_port),
                allow_broadcast=True,
            )
            entry_data["udp"] = transport
        except OSError as err:
            raise ConfigEntryNotReady(
                f"Cannot start UDP discovery on port {udp_port}: {err}"
            ) from err
        try:
            await entry_data["server"].async_start("0.0.0.0", DEFAULT_PORT)
        except OSError as err:
            raise ConfigEntryNotReady(
                f"Cannot start Modbus TCP on port {DEFAULT_PORT}: {err}"
            ) from err
    except BaseException:
        # HA cannot unload an entry whose setup did not complete successfully.
        # This also handles cancellation while starting either socket.
        await _async_close_resources(entry_data)
        hass.data[DOMAIN].pop(entry.entry_id, None)
        raise

    async def update_listener(hass: HomeAssistant, entry: ConfigEntry):
        if entry_data["closed"] or entry_data["reload_requested"]:
            return
        if entry.data.get(CONF_UDP_PORT, DEFAULT_UDP_PORT) != udp_port:
            # All data/options updates use this one path. There is no delayed
            # flow-owned task and concurrent notifications request only one reload.
            entry_data["reload_requested"] = True
            await hass.config_entries.async_reload(entry.entry_id)
            return
        update_register_map()

    async def async_stop_server(event):
        await _async_close_resources(entry_data)

    entry.async_on_unload(entry.add_update_listener(update_listener))
    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, async_stop_server)
    )
    _LOGGER.debug("Meter listening on UDP %d and TCP %d", udp_port, DEFAULT_PORT)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Release sockets, accepted clients and state listeners before reloading."""
    entries = hass.data.get(DOMAIN, {})
    if (entry_data := entries.get(entry.entry_id)) is not None:
        await _async_close_resources(entry_data)
        entries.pop(entry.entry_id, None)
    return True
