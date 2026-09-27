import asyncio
import logging
import struct
import ipaddress
import errno
import datetime

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.event import async_track_state_change_event
from .const import DOMAIN, CONF_REGISTERS, CONF_EMULATOR_IP, CONF_SERIAL, CONF_UDP_PORT, DEFAULT_UDP_PORT, CONF_UNIT_ID, DEFAULT_UNIT_ID, METER_REGISTERS, DETECTION_REGISTER, DETECTION_VALUE, DATE_REGISTER, HEADER_BLOCK

_LOGGER = logging.getLogger(__name__)

MAGIC = b"\x5A\x5A\x5A\x5A"
APP_MAGIC = b"\x00\x41\x3A"


def _crc16_modbus(data: bytes) -> int:
    """Calculate CRC16-Modbus checksum."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


def _seed_static_registers(modbus_values: dict):
    """Seed header block, detection register, and live clock into the register map."""
    # Header block at register 0
    for i, val in enumerate(HEADER_BLOCK):
        modbus_values[i] = val & 0xFFFF
    # Detection register 0x7D1 = 3 (critical for Huawei recognition)
    modbus_values[DETECTION_REGISTER] = DETECTION_VALUE
    # Live clock at register 0x2F
    now = datetime.datetime.now()
    clock_vals = [now.second, now.minute, now.hour, now.day, now.month, now.year]
    for i, val in enumerate(clock_vals):
        modbus_values[DATE_REGISTER + i] = val & 0xFFFF

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Setzt die Virtual Meter Integration aus einem ConfigEntry auf."""
    hass.data.setdefault(DOMAIN, {})
    
    entry_data = {
        "modbus_values": {},
        "listeners": [],
        "server": None,
        "udp": None,
        "udp_protocol": None,
        "queried_registers": set(),
        "active_writers": set()
    }
    hass.data[DOMAIN][entry.entry_id] = entry_data

    def update_register_map():
        for unsub in entry_data["listeners"]:
            unsub()
        entry_data["listeners"] = []

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
            except (ValueError, TypeError):
                pass

        entities_to_track = set()
        for addr_str, conf in registers_config.items():
            if "entity_id" in conf:
                entities_to_track.add(conf["entity_id"])
            elif "fixed_value" in conf:
                _set_modbus_value(int(addr_str), conf["fixed_value"] * conf.get("factor", 1.0))
        for eid in entities_to_track:
            unsub = async_track_state_change_event(hass, eid, _state_changed_event)
            entry_data["listeners"].append(unsub)
            
            state = hass.states.get(eid)
            if state and state.state not in ("unknown", "unavailable"):
                try:
                    val = float(state.state)
                    for addr_str, conf in registers_config.items():
                        if conf.get("entity_id") == eid:
                            _set_modbus_value(int(addr_str), val * conf.get("factor", 1.0))
                except (ValueError, TypeError):
                    continue

    update_register_map()
    
    # Seed static registers (header block, detection register, clock)
    _seed_static_registers(entry_data["modbus_values"])
    
    # Periodic clock update every 10 seconds
    async def _clock_updater():
        while True:
            _seed_static_registers(entry_data["modbus_values"])
            await asyncio.sleep(10)
    clock_task = asyncio.create_task(_clock_updater())
    entry_data["clock_task"] = clock_task
    
    # Listener, der aufgerufen wird, wenn die Optionen im UI geändert werden
    async def update_listener(hass: HomeAssistant, entry: ConfigEntry):
        update_register_map()

    # Korrekter API-Aufruf, um den Listener hinzuzufügen und beim Entladen zu entfernen
    entry.async_on_unload(entry.add_update_listener(update_listener))

    loop = asyncio.get_running_loop()
    
    class VirtualMeterUDP(asyncio.DatagramProtocol):
        def __init__(self):
            self.closed = asyncio.Event()

        def connection_made(self, transport):
            self.transport = transport

        def connection_lost(self, exc):
            self.closed.set()

        def datagram_received(self, data, addr):
            if data.startswith(MAGIC + APP_MAGIC):
                try:
                    _LOGGER.info("UDP discovery request received from %s (%d bytes)", addr[0], len(data))
                    resp = (MAGIC + APP_MAGIC + b"\x2f\x00" + 
                            entry.data[CONF_SERIAL].encode().ljust(20, b"\x00") + 
                            b"\x00\x05\x00\x01\x02\x00\xf6\x01\x05\x01\x64\x07\x01\x00\x08\x04" + 
                            ipaddress.IPv4Address(entry.data[CONF_EMULATOR_IP]).packed[::-1] + 
                            b"\x0A\x04\x00\x00\x00\x00")
                    self.transport.sendto(resp, addr)
                    _LOGGER.info("UDP discovery response sent to %s (emulator IP: %s)", addr[0], entry.data[CONF_EMULATOR_IP])
                except Exception as err:
                    _LOGGER.error("Fehler beim Senden der UDP-Antwort: %s", err)

    udp_protocol = VirtualMeterUDP()
    udp_port = entry.data.get(CONF_UDP_PORT, DEFAULT_UDP_PORT)
    try:
        transport, _ = await loop.create_datagram_endpoint(
            lambda: udp_protocol, 
            local_addr=("0.0.0.0", udp_port), 
            allow_broadcast=True
        )
        entry_data["udp"] = transport
        entry_data["udp_protocol"] = udp_protocol
        _LOGGER.info("UDP discovery server listening on port %d", udp_port)
    except OSError as err:
        if err.errno == errno.EADDRINUSE:
            raise ConfigEntryNotReady(f"UDP Port {udp_port} wird bereits verwendet") from err
        raise ConfigEntryNotReady(f"UDP Server konnte nicht gestartet werden: {err}") from err

    async def handle_modbus(reader, writer):
        entry_data["active_writers"].add(writer)
        handshake_done = False
        try:
            while True:
                try:
                    frame = await asyncio.wait_for(reader.read(4096), timeout=60)
                    if not frame:
                        break
                    
                    # --- Huawei proprietary handshake handler ---
                    # The SCharger wallbox sends a 75-byte auth/handshake frame
                    # (starts with 0xF6, contains serial + crypto challenge +
                    # CRC16-Modbus checksum) BEFORE any Modbus traffic.
                    # If unanswered, the wallbox falls back to TLS.
                    # We do NOT send a response yet — the correct response
                    # format is unknown. Sending a wrong response causes the
                    # wallbox to report "wallBoxPowerSensor communication error".
                    if not handshake_done and len(frame) >= 4 and frame[0] == 0xF6:
                        _LOGGER.info("Huawei handshake frame received (%d bytes) from %s — ignoring (no response)",
                                     len(frame), writer.get_extra_info('peername'))
                        handshake_done = True
                        continue
                    
                    # --- TLS ClientHello detection ---
                    # If the wallbox sends TLS (0x16 0x03 0x01), close the connection
                    # so it cycles back to plaintext.
                    if len(frame) >= 3 and frame[0] == 0x16 and frame[1] == 0x03:
                        _LOGGER.info("TLS ClientHello detected from %s — closing to force plaintext retry",
                                     writer.get_extra_info('peername'))
                        break
                    
                    # --- Standard Modbus TCP handler ---
                    if len(frame) >= 12 and frame[7] in (3, 4):
                        # Read unit_id dynamically (no reload needed)
                        unit_id = entry.data.get(CONF_UNIT_ID, DEFAULT_UNIT_ID)
                        
                        # Check unit ID matches (byte 6 in Modbus TCP)
                        if frame[6] != unit_id:
                            _LOGGER.debug("Unit ID mismatch: got %d, expected %d", frame[6], unit_id)
                            continue
                        
                        start = struct.unpack(">H", frame[8:10])[0]
                        count = struct.unpack(">H", frame[10:12])[0]
                        
                        payload = b""
                        for i in range(start, start + count):
                            entry_data["queried_registers"].add(i)
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
        finally:
            entry_data["active_writers"].discard(writer)
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
        if entry_data.get("clock_task"):
            entry_data["clock_task"].cancel()
            try:
                await entry_data["clock_task"]
            except asyncio.CancelledError:
                pass
        if entry_data["server"]:
            entry_data["server"].close()
            # Force-close all active client connections before waiting
            for writer in list(entry_data["active_writers"]):
                try:
                    writer.close()
                except Exception:
                    pass
            entry_data["active_writers"].clear()
            await entry_data["server"].wait_closed()
        if entry_data["udp"]:
            entry_data["udp"].close()
            if entry_data["udp_protocol"]:
                await entry_data["udp_protocol"].closed.wait()

    stop_listener = hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop_server)
    entry.async_on_unload(stop_listener)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    entry_id = entry.entry_id
    if entry_id not in hass.data[DOMAIN]: return True
    entry_data = hass.data[DOMAIN].pop(entry_id)

    if entry_data.get("clock_task"):
        entry_data["clock_task"].cancel()
        try:
            await entry_data["clock_task"]
        except asyncio.CancelledError:
            pass
    if entry_data["server"]:
        entry_data["server"].close()
        # Force-close all active client connections before waiting
        for writer in list(entry_data.get("active_writers", set())):
            try:
                writer.close()
            except Exception:
                pass
        entry_data["active_writers"].clear()
        await entry_data["server"].wait_closed()
    if entry_data["udp"]:
        entry_data["udp"].close()
        if entry_data["udp_protocol"]:
            await entry_data["udp_protocol"].closed.wait()
    for unsub in entry_data["listeners"]:
        unsub()

    return True
