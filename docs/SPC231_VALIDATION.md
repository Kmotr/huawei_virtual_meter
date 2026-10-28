# SCharger SPC231 device validation

Status: **NOT RUN on a physical wallbox by this correction.** Automated server
tests do not establish SPC231 authentication or charging compatibility.

This procedure separates discovery, Modbus communication and charging behaviour.
Complete it for each exact firmware version before claiming compatibility. A
successful test on SPC231 alone does not establish support for later versions.

## Record the test configuration

| Field | Value / evidence |
|-------|------------------|
| Test date and tester | Pending |
| Correction commit SHA | Pending |
| Wallbox model | Pending |
| Complete wallbox firmware version | Pending |
| Home Assistant version | Pending |
| Advertised emulator IPv4 address | Pending |
| Selected discovery UDP port | Pending |
| Selected unit ID / actual requested unit ID | Pending |
| Sensor entity, unit and factor for 37113 | Pending |
| Other mapped registers and meter type | Pending |
| Network capture and HA debug log | Pending |
| Outcome and observed wallbox errors | Pending |

Save the current integration settings and register mappings before installing
the test component. Use the component directory from the correction branch,
restart Home Assistant, and retain a working build for rollback.

## 1. Capture discovery and the subsequent connection

Enable integration debug logging in Home Assistant:

```yaml
logger:
  logs:
    custom_components.huawei_virtual_meter: debug
```

Capture on the Home Assistant host or a mirrored network port. An ordinary
third host on a switched LAN will not see all unicast traffic. With Wireshark,
use capture filter `udp port 6600 or udp port 10086 or tcp port 502`, then narrow
the displayed traffic to the wallbox and emulator addresses.

- [ ] Record the UDP destination port actually used by this firmware.
- [ ] Configure that port and observe the discovery request and reply.
- [ ] Verify that the reply advertises the reachable emulator IPv4 address.
- [ ] Record the destination and bytes of the subsequent TCP connection.

If discovery succeeds but the connection contains TLS records or proprietary
authentication rather than valid Modbus TCP, record the capture and wallbox error.
This server does not implement either authentication protocol. **Mark this path
unsupported; a closed connection is not a successful plaintext fallback.** Do not
describe discovery alone as a successful firmware compatibility test.

## 2. Verify actual Modbus polling

- [ ] Observe valid MBAP headers and FC03/FC04 requests, including unit ID.
- [ ] Confirm responses echo the transaction and unit IDs with correct lengths.
- [ ] Record which registers the wallbox requests and how often it polls.
- [ ] Verify that each required mapped value is visible and plausible on the
      charger, rather than assuming that TCP traffic means accepted readings.

If extra identification registers are requested, record their addresses and find
evidence for their expected values before configuring them. The correction does
not automatically inject a header block, detection value or clock.

## 3. Verify units and sign before automatic charging

Use actual, independently checked meter readings. A fixed synthetic power value
is suitable only for a bench test with automatic charging disabled.

- [ ] Compare voltages, currents, frequency and power with independent readings.
- [ ] For a known import condition, record the source value, applied factor, raw
      signed 37113 value and wallbox display/interpretation.
- [ ] Repeat for a known export condition, when available.
- [ ] Confirm the wallbox distinguishes import from available surplus correctly.
- [ ] Verify energy sensor units; the default factor 100 expects kWh, not Wh.
- [ ] Confirm single-/three-phase meter configuration matches the installation.

If export is unavailable during testing, mark sign and surplus charging as
unverified rather than substituting an assumed result.

## 4. Verify recovery and real charging behaviour

- [ ] Change only the unit ID: mappings remain and the next matching request works
      without reloading the listener.
- [ ] Change the discovery port: one automatic reload occurs, old clients close,
      and all mappings survive. Restore the actual port used by the device and
      confirm discovery/polling resumes.
- [ ] Reload the integration and restart HA; confirm the wallbox reconnects and
      resumes valid meter readings without recreating the integration.
- [ ] During a controlled charging session, verify that charging follows actual
      surplus and does not mistake grid import for surplus.
- [ ] As a project acceptance criterion, observe at least 30 minutes of polling
      and charging, including a change in available surplus, without recurring
      communication errors. Record duration and observations.

## Result

Record **pass**, **fail**, or **not tested** for each stage. Declare the exact
tested firmware compatible only after discovery, accepted meter readings,
correct sign/scaling, recovery and controlled charging have all passed. Until
then, keep SPC231 compatibility experimental. General server fixes can be
reviewed independently of this hardware result.
