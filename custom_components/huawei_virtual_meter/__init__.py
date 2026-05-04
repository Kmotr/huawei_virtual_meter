import asyncio
import logging
import struct
import ipaddress
import errno

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.event import async_track_state_change_event
from .const import DOMAIN, CONF_REGISTERS, CONF_EMULATOR_IP, CONF_SERIAL

_LOGGER = logging.getLogger(__name__)

MAGIC = b"\x5A\x5A\x5A\x5A"
APP_MAGIC = b"\x00\x41\x3A"

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Setzt die Virtual Meter Integration aus einem ConfigEntry auf."""
    hass.data.setdefault(DOMAIN, {})
    
    entry_data = {
        "modbus_values": {},
        "listeners": [],
        "server": None,
        "udp": None
    }
    hass.data[DOMAIN][entry.entry_id] = entry_data

    def update_register_map():
        for unsub in entry_data["listeners"]:
            unsub()
        entry_data["listeners"] = []

        registers_config = entry.options.get(CONF_REGISTERS, {})

        @callback
        def _state_changed_event(event):
            entity_id = event.data["entity_id"]
            new_state = event.data.get("new_state")
            if new_state is None or new_state.state in (None, "unknown", "unavailable"):
                return
            try:
                val = float(new_state.state)
                for addr_str, conf in registers_config.items():
                    if conf["entity_id"] == entity_id:
                        entry_data["modbus_values"][int(addr_str)] = int(val * conf["factor"])
            except (ValueError, TypeError):
                pass

        entities_to_track = set(conf["entity_id"] for conf in registers_config.values())
        for eid in entities_to_track:
            unsub = async_track_state_change_event(hass, eid, _state_changed_event)
            entry_data["listeners"].append(unsub)
            
            state = hass.states.get(eid)
            if state and state.state not in ("unknown", "unavailable"):
                try:
                    val = float(state.state)
                    for addr_str, conf in registers_config.items():
                        if conf["entity_id"] == eid:
                            entry_data["modbus_values"][int(addr_str)] = int(val * conf["factor"])
                except (ValueError, TypeError):
                    continue

    update_register_map()
    
    # Listener, der aufgerufen wird, wenn die Optionen im UI geändert werden
    async def update_listener(hass: HomeAssistant, entry: ConfigEntry):
        update_register_map()

    # Korrekter API-Aufruf, um den Listener hinzuzufügen und beim Entladen zu entfernen
    entry.async_on_unload(entry.add_update_listener(update_listener))

    loop = asyncio.get_running_loop()
    
    class VirtualMeterUDP(asyncio.DatagramProtocol):
        def connection_made(self, transport):
            self.transport = transport

        def datagram_received(self, data, addr):
            if data.startswith(MAGIC + APP_MAGIC):
                try:
                    resp = (MAGIC + APP_MAGIC + b"\x2f\x00" + 
                            entry.data[CONF_SERIAL].encode().ljust(20, b"\x00") + 
                            b"\x00\x05\x00\x01\x02\x00\xf6\x01\x05\x01\x64\x07\x01\x00\x08\x04" + 
                            ipaddress.IPv4Address(entry.data[CONF_EMULATOR_IP]).packed[::-1] + 
                            b"\x0A\x04\x00\x00\x00\x00")
                    self.transport.sendto(resp, addr)
                except Exception as err:
                    _LOGGER.error("Fehler beim Senden der UDP-Antwort: %s", err)

    try:
        transport, _ = await loop.create_datagram_endpoint(
            VirtualMeterUDP, 
            local_addr=("0.0.0.0", 6600), 
            allow_broadcast=True
        )
        entry_data["udp"] = transport
    except OSError as err:
        if err.errno == errno.EADDRINUSE:
            raise ConfigEntryNotReady("UDP Port 6600 wird bereits verwendet") from err
        raise ConfigEntryNotReady(f"UDP Server konnte nicht gestartet werden: {err}") from err

    async def handle_modbus(reader, writer):
        while True:
            try:
                frame = await asyncio.wait_for(reader.read(4096), timeout=60)
                if not frame:
                    break
                if len(frame) >= 12 and frame[7] in (3, 4):
                    start = struct.unpack(">H", frame[8:10])[0]
                    count = struct.unpack(">H", frame[10:12])[0]
                    
                    payload = b""
                    for i in range(start, start + count):
                        val = entry_data["modbus_values"].get(i, 0)
                        payload += struct.pack(">H", val & 0xFFFF)
                    
                    resp = (frame[0:2] + b"\x00\x00" + 
                            struct.pack(">H", len(payload) + 3) + 
                            frame[6:7] + bytes([frame[7], len(payload)]) + 
                            payload)
                    writer.write(resp)
                    await writer.drain()
            except Exception:
                break
        writer.close()
        await writer.wait_closed()

    try:
        server = await asyncio.start_server(handle_modbus, "0.0.0.0", 502)
        entry_data["server"] = server
    except OSError as err:
        transport.close()
        if err.errno == errno.EADDRINUSE:
            raise ConfigEntryNotReady("Modbus Port 502 wird bereits verwendet") from err
        raise ConfigEntryNotReady(f"Modbus Server Fehler: {err}") from err

    async def _async_stop_server(event):
        _LOGGER.info("HA stoppt. Beende Virtual Meter Server...")
        if entry_data["server"]:
            entry_data["server"].close()
            await entry_data["server"].wait_closed()
        if entry_data["udp"]:
            entry_data["udp"].close()

    stop_listener = hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop_server)
    entry.async_on_unload(stop_listener)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    entry_id = entry.entry_id
    if entry_id not in hass.data[DOMAIN]: return True
    entry_data = hass.data[DOMAIN].pop(entry_id)

    if entry_data["server"]:
        entry_data["server"].close()
        await entry_data["server"].wait_closed()
    if entry_data["udp"]:
        entry_data["udp"].close()
    for unsub in entry_data["listeners"]:
        unsub()

    return True
