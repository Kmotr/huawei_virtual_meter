# Huawei Virtual Meter for Home Assistant

![GitHub Release](https://img.shields.io/github/v/release/kmotr/huawei_virtual_meter)
![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)

This custom integration exposes Home Assistant sensor values through a plaintext
Modbus TCP meter server and responds to Huawei UDP discovery requests. Register
mappings, fixed values and scaling factors are configured in the Home Assistant UI.

**Requires Home Assistant 2024.12.5 or newer.** This minimum matches the Config Entry
options-flow API used by the integration. Older entries keep their register options
and continue accepting any unit ID until an explicit filter is configured.

## Firmware compatibility

The default discovery port remains `6600`. The port can also be set to `10086`,
as proposed for SCharger firmware `V100R023C10SPC231` in [PR #2](../../pull/2).
**SPC231 compatibility is experimental and has not been verified end to end by
this correction. No claim is made for all later firmware versions.**

Receiving a UDP discovery reply does not prove successful meter authentication,
register polling or surplus charging. The server supports **plaintext Modbus TCP
only**. It does not implement Huawei's proprietary authentication or TLS/MBAS;
closing an unsupported connection cannot guarantee a plaintext retry.

Unverified header, detection and clock registers from PR #2 are deferred. There
is no automatic register seeding or periodic clock task. Unknown registers return
zero unless explicitly mapped. If a particular device needs additional registers,
map them only after verifying its actual requests and expected values.

See the [SPC231 device validation procedure](docs/SPC231_VALIDATION.md) for the
outstanding hardware checks and the evidence required before declaring support.

## Installation

### HACS

1. In HACS, open **Custom repositories**.
2. Add this repository URL with category **Integration**, then install it.
3. Restart Home Assistant.

### Manual

1. Download a release from the [Releases page](../../releases).
2. Copy `custom_components/huawei_virtual_meter` into your Home Assistant
   `custom_components` directory.
3. Restart Home Assistant.

For a test branch, use that branch's component directory instead of a release.

## Configuration

In **Settings > Devices & Services**, add **Huawei Virtual Meter Emulator**.

- **Emulator IP Address:** The Home Assistant IPv4 address reachable by the charger.
- **Serial Number:** 1–20 printable ASCII characters; default `HV0000000001`.
- **UDP Discovery Port:** Default `6600`; configurable from `1` through `65535`.
  `10086` is available for experimental SPC231 testing.
- **Unit ID:** New setups default to `11`. Set a specific ID from `1` through `255`
  to filter requests, or `0` to accept any incoming unit byte (legacy mode).
  Responses always echo the received unit ID.

Under **CONFIGURE**, choose:

1. **Add a new register mapping:** Select a register or enter an address from
   `0` through `65535`. Choose an entity or a fixed value, then a factor.
2. **Edit configured registers:** Change mappings and factors. Clear both entity
   and fixed-value fields to delete a mapping; its old value is removed immediately.
3. **Edit settings:** Change discovery port and unit ID while retaining register
   mappings. A port change automatically reloads the integration and disconnects
   existing Modbus clients. A unit-ID change applies on the next request, including
   on an existing connection, without reloading.

Entries created before configurable unit IDs keep legacy mode (`0`) when opening
and saving settings. They are not silently changed to ID `11`.

## Register values and factors

The emulator writes `source value × factor`, truncates to an integer, and clamps
known signed/unsigned types to their supported range. INT32 values use two words,
high word first. **The factor is applied once**: a 230 V source with factor `10`
produces raw `2300`. Use the source sensor's actual unit when selecting a factor.

The table documents the existing emulator defaults. The current, reactive-power
and energy factors have been aligned with the corresponding register definitions
in [huawei-solar-lib](https://github.com/wlcrs/huawei-solar-lib/blob/develop/src/huawei_solar/registers.py).
That implementation is a cross-check, not proof of SCharger firmware compatibility.

| Register | Name | Type | Width | Gain | Expected input unit / meaning |
|----------|------|------|-------|------|-------------------------------|
| 37100 | Meter status | UINT16 | 1 | 1 | 0 = offline, 1 = online |
| 37101 | A phase voltage | INT32 | 2 | 10 | V |
| 37103 | B phase voltage | INT32 | 2 | 10 | V |
| 37105 | C phase voltage | INT32 | 2 | 10 | V |
| 37107 | A phase current | INT32 | 2 | 100 | A |
| 37109 | B phase current | INT32 | 2 | 100 | A |
| 37111 | C phase current | INT32 | 2 | 100 | A |
| 37113 | Active power | INT32 | 2 | 1 | W; verify direction on the charger |
| 37115 | Reactive power | INT32 | 2 | 1 | var |
| 37117 | Power factor | INT16 | 1 | 1000 | cos phi, e.g. 0.95 |
| 37118 | Grid frequency | INT16 | 1 | 100 | Hz |
| 37119 | Positive active energy | INT32 | 2 | 100 | kWh; verify direction on device |
| 37121 | Reverse active energy | INT32 | 2 | 100 | kWh; verify direction on device |
| 37123 | Accumulated reactive energy | INT32 | 2 | 100 | kvarh |
| 37125 | Meter type | UINT16 | 1 | 1 | 0 = single-phase, 1 = three-phase |
| 37126 | A-B line voltage | INT32 | 2 | 10 | V |
| 37128 | B-C line voltage | INT32 | 2 | 10 | V |
| 37130 | C-A line voltage | INT32 | 2 | 10 | V |
| 37132 | A phase active power | INT32 | 2 | 1 | W |
| 37134 | B phase active power | INT32 | 2 | 1 | W |
| 37136 | C phase active power | INT32 | 2 | 1 | W |
| 37138 | Meter model detection result | UINT16 | 1 | 1 | Device-specific result |

For a source already measured in Wh, a factor of `0.1` produces the same raw energy
value as the default `100` applied to kWh. For example, `1.5 kWh × 100 = 150` and
`1500 Wh × 0.1 = 150`. A 15.5 A source uses `100`, producing raw `1550`.

For register `37113`, compare a known import condition and a known export condition
with the charger's display before enabling automatic control. The emulator does
not invert the sign automatically. If the sensor and charger use opposite sign
conventions, use a negative factor. Do not infer the sign from discovery success.

## Troubleshooting

- **Port already in use:** TCP `502` and the selected UDP port must be available.
  Failed setup closes already-open sockets and state listeners before HA retries.
- **No discovery:** Check the advertised IPv4 address, local subnet, VLAN/firewall
  rules and the actual UDP destination port sent by the charger.
- **Discovery works, but no readings:** Check the unit ID and register requests.
  TLS or proprietary authentication remains unsupported; changing the discovery
  port alone may not solve this.
- **Unexpected values:** Check source units, factor, sign and the configured meter
  type. Unmapped registers return zero. No fixed header overwrites custom mappings.

To inspect protocol failures, enable debug logging for
`custom_components.huawei_virtual_meter`. Malformed MBAP headers are rejected;
unsupported function codes and invalid read requests receive Modbus exceptions.

## Development and automated tests

The suite uses real loopback TCP/UDP sockets and actual Home Assistant config
entries/options flows. It covers stream fragmentation/coalescing, transaction IDs,
request validation, live unit-ID changes, port reloads, mapping preservation,
shutdown and cleanup after repeated bind failures. No wallbox is simulated as a
successful firmware compatibility test.

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-test.txt
python -m pytest -q
```

Use Python 3.14 for `requirements-test.txt` (HA 2026.10.4), or Python 3.13 for
`requirements-test-min.txt` (HA 2024.12.5) and `requirements-test-2025.txt`
(HA 2025.4.4). The CI runs all three environments.

## Disclaimer

This project is not affiliated with Huawei. Incorrect meter values can cause
unintended charging behaviour. Validate actual readings and charging behaviour
on the target device before relying on automatic control.
