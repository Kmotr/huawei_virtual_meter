DOMAIN = "huawei_virtual_meter"
CONF_REGISTERS = "registers"
CONF_EMULATOR_IP = "emulator_ip"
CONF_SERIAL = "serial"
CONF_UDP_PORT = "udp_port"
CONF_UNIT_ID = "unit_id"
DEFAULT_PORT = 502
DEFAULT_UDP_PORT = 6600

# Huawei default Unit/Slave ID for DTSU666 meter
DEFAULT_UNIT_ID = 11  # 0x0B — NOT standard Modbus ID 1

# Huawei meter-detection register: the inverter/wallbox reads holding register
# 0x7D1 during detection and expects the value 3.
DETECTION_REGISTER = 0x7D1
DETECTION_VALUE = 3

# Live clock registers (second, minute, hour, day, month, year as int16)
DATE_REGISTER = 0x2F

# Static header block at register 0 — replicated from jsphuebner/dtsu666-Emulator.
# Contains meter configuration words (CT/PT ratios, wiring mode, address,
# baud rate, ...) that Huawei devices read during meter detection.
HEADER_BLOCK = [
    207, 701, 0, 0, 0, 0, 1, 1, 0, 0, 0, 1, 0, 0, 0, 1000, 0, 0, 1000,
    0, 0, 1000, 0, 0, 1000, 1, 10, 0, 0, 0, 1000, 0, 0, 1000, 0, 0,
    1000, 0, 0, 1000, 0, 0, 0, 0, 11, 3, 4,
]

METER_REGISTERS = {
    37100: {"name": "Meter status", "type": "UINT16", "width": 1, "gain": 1},
    37101: {"name": "Grid voltage (A phase)", "type": "INT32", "width": 2, "gain": 10},
    37103: {"name": "B phase voltage", "type": "INT32", "width": 2, "gain": 10},
    37105: {"name": "C phase voltage", "type": "INT32", "width": 2, "gain": 10},
    37107: {"name": "Grid current (A phase)", "type": "INT32", "width": 2, "gain": 100},
    37109: {"name": "B phase current", "type": "INT32", "width": 2, "gain": 100},
    37111: {"name": "C phase current", "type": "INT32", "width": 2, "gain": 100},
    37113: {"name": "Active power", "type": "INT32", "width": 2, "gain": 1},
    37115: {"name": "Reactive power", "type": "INT32", "width": 2, "gain": 1},
    37117: {"name": "Power factor", "type": "INT16", "width": 1, "gain": 1000},
    37118: {"name": "Grid frequency", "type": "INT16", "width": 1, "gain": 100},
    37119: {"name": "Positive active electricity", "type": "INT32", "width": 2, "gain": 100},
    37121: {"name": "Reverse active electricity", "type": "INT32", "width": 2, "gain": 100},
    37123: {"name": "Accumulated reactive power", "type": "INT32", "width": 2, "gain": 100},
    37125: {"name": "Meter type", "type": "UINT16", "width": 1, "gain": 1},
    37126: {"name": "A-B line voltage", "type": "INT32", "width": 2, "gain": 10},
    37128: {"name": "B-C line voltage", "type": "INT32", "width": 2, "gain": 10},
    37130: {"name": "C-A line voltage", "type": "INT32", "width": 2, "gain": 10},
    37132: {"name": "A phase active power", "type": "INT32", "width": 2, "gain": 1},
    37134: {"name": "B phase active power", "type": "INT32", "width": 2, "gain": 1},
    37136: {"name": "C phase active power", "type": "INT32", "width": 2, "gain": 1},
    37138: {"name": "Meter model detection result", "type": "UINT16", "width": 1, "gain": 1},
}
