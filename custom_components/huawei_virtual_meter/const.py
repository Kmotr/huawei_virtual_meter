DOMAIN = "huawei_virtual_meter"
CONF_REGISTERS = "registers"
CONF_EMULATOR_IP = "emulator_ip"
CONF_SERIAL = "serial"
DEFAULT_PORT = 502
DEFAULT_UDP_PORT = 6600

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
