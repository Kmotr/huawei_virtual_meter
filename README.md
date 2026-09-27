# Huawei Virtual Meter for Home Assistant

![GitHub Release](https://img.shields.io/github/v/release/kmotr/huawei_virtual_meter)
![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)

This custom integration for Home Assistant acts as a **virtual Modbus TCP server**, emulating a **Huawei Smart Power Sensor** (Smart Meter). It allows you to feed real-time power, voltage, current, and energy data from any Home Assistant entity directly into your Huawei SCharger (Smart Charger).

By utilizing this integration, your Huawei SCharger will automatically discover the virtual meter on your local network and use its data for dynamic power control, surplus solar charging logic (PV excess charging), and charging statistics—without requiring a physical Huawei Smart Power Sensor.

## Features

- 🔋 **Seamless Integration:** Emulates the official "3.3 Meter Equipment Register" Modbus map required by Huawei SChargers.
- 📡 **Auto-Discovery:** Simulates the Huawei UDP discovery protocol, allowing the SCharger to find the meter automatically. The discovery port is configurable (default `6600` for older firmware, `10086` for SPC231+).
- ⚙️ **Direct UI Configuration:** Configure, map, and edit all your Modbus registers directly from the Home Assistant UI. No YAML required!
- 🎛️ **Entity & Fixed Value Support:** Map live Home Assistant entities (e.g., `sensor.grid_power`) or set fixed values (e.g., a static `230V` for voltage) for specific registers.
- 🧮 **Automatic Data Handling:** Automatically manages data types (`INT16`, `UINT16`, `INT32`), correct 32-bit value splitting (High/Low words), and applies the required Huawei scaling factors (gains).

## Installation

### Method 1: HACS (Recommended)
1. Open HACS in Home Assistant.
2. Click on the 3 dots in the top right corner and select **Custom repositories**.
3. Add the URL of this repository and select **Integration** as the category.
4. Click **Install** and restart Home Assistant.

### Method 2: Manual
1. Download the latest release `.zip` file from the [Releases page](../../releases).
2. Extract the `huawei_virtual_meter` folder.
3. Copy the folder into your Home Assistant's `custom_components/` directory.
4. Restart Home Assistant.

## Configuration

1. In Home Assistant, navigate to **Settings** > **Devices & Services**.
2. Click **+ ADD INTEGRATION** and search for **Huawei Virtual Meter Emulator**.
3. During the initial setup:
   - **Emulator IP Address:** Select the IP address of your Home Assistant instance that the SCharger should connect to.
   - **Serial Number:** Provide a simulated serial number (default `HV0000000001` is fine).
   - **UDP Discovery Port:** Set the port for the Huawei UDP discovery protocol. Use `6600` for older SCharger firmware (pre-SPC231). Use `10086` for SCharger firmware `V100R023C10SPC231` and later. You can change this later via **Settings** > **Edit settings**.
   - **Unit ID:** The Modbus unit ID the virtual meter responds to (default `11`). Must match the unit ID the SCharger expects. Can be changed later via **Edit settings** without reloading.
4. After adding the integration, click on **CONFIGURE** to map your registers.

## Mapping Registers

Click **CONFIGURE** on the integration page. You will see three options:

1. **Add a new register mapping:**
   - Choose the register you want to provide data for (e.g., `Register 37113: Active power`).
   - On the next screen, you can select the **Home Assistant Entity** you want to map to this register.
   - *Alternatively*, you can provide a **Fixed Value** (e.g., `1` for the "Meter Type" register).
   - The scaling factor (e.g., `10` or `100`) is automatically pre-filled according to the official Huawei Modbus specifications, but you can adjust it if your sensor requires it.
2. **Edit configured registers:**
   - Displays a complete table of all your currently mapped registers.
   - You can quickly adjust entities, fixed values, and factors all in one place.
   - To **delete** a register, simply clear both the Entity ID and the Fixed Value fields and click Submit.
3. **Edit settings:**
   - Change the **UDP Discovery Port** without recreating the integration.
   - Change the **Unit ID** (Modbus slave address, default `11`).
   - Use `6600` for older SCharger firmware (pre-SPC231) or `10086` for SCharger firmware `V100R023C10SPC231` and later.
   - Changing the port requires reloading the integration to take effect. Unit ID changes take effect immediately (no reload needed).

### Supported Huawei Modbus Registers

| Register | Name | Type | Width | Gain | Description |
|----------|------|------|-------|------|-------------|
| 37100 | Meter status | UINT16 | 1 | 1 | Online/offline status |
| 37101 | Grid voltage (A phase) | INT32 | 2 | 10 | Volts |
| 37103 | B phase voltage | INT32 | 2 | 10 | Volts |
| 37105 | C phase voltage | INT32 | 2 | 10 | Volts |
| 37107 | Grid current (A phase) | INT32 | 2 | 10 | Amps |
| 37109 | B phase current | INT32 | 2 | 10 | Amps |
| 37111 | C phase current | INT32 | 2 | 10 | Amps |
| 37113 | Active power | INT32 | 2 | 1 | Watts. **Positive = export/surplus**, Negative = import |
| 37115 | Reactive power | INT32 | 2 | 1000 | VAR |
| 37117 | Power factor | INT16 | 1 | 1000 | cos phi |
| 37118 | Grid frequency | INT16 | 1 | 100 | Hz |
| 37119 | Positive active electricity | INT32 | 2 | 1 | Wh accumulated import |
| 37121 | Reverse active electricity | INT32 | 2 | 1 | Wh accumulated export |
| 37123 | Accumulated reactive power | INT32 | 2 | 1 | varh |
| 37125 | Meter type | UINT16 | 1 | 1 | 0 = single-phase, 1 = three-phase |
| 37126 | A-B line voltage | INT32 | 2 | 10 | Volts |
| 37128 | B-C line voltage | INT32 | 2 | 10 | Volts |
| 37130 | C-A line voltage | INT32 | 2 | 10 | Volts |
| 37132 | A phase active power | INT32 | 2 | 1 | Watts |
| 37134 | B phase active power | INT32 | 2 | 1 | Watts |
| 37136 | C phase active power | INT32 | 2 | 1 | Watts |
| 37138 | Meter model detection | UINT16 | 1 | 1 | Detection result |

### Typical Register Configuration

For a typical single-phase setup with a Huawei SCharger:

| Register | Source | Factor | Notes |
|----------|--------|--------|-------|
| 37101 | Fixed value: 230 | 10 | Voltage L1 (230.0V × 10 = 2300) |
| 37103 | Fixed value: 230 | 10 | Voltage L2 |
| 37105 | Fixed value: 230 | 10 | Voltage L3 |
| 37113 | HA entity (grid power) | 1 | Primary surplus sensor. Positive = export |
| 37117 | HA entity (power factor) | 1000 | cos phi × 1000 |
| 37118 | HA entity (frequency) | 100 | Hz × 100 (50.0 Hz → 5000) |
| 37125 | Fixed value: 0 | 1 | Single-phase meter |

### Common Huawei Registers
To get started, you will typically want to map at least the following:

#### Essential Registers

- **37113 (Active power):** The most important register. Maps to your home grid power sensor. The SCharger uses this to determine available PV surplus. **Positive = exporting to grid / surplus available**, Negative = consuming from grid. Factor = 1 (value in watts).
- **37125 (Meter type):** Tells the SCharger whether the meter is single-phase or three-phase. Set as a **Fixed Value**: `0` for Single-Phase, `1` for Three-Phase. Factor = 1.
- **37101, 37103, 37105 (Phase Voltages):** Grid voltage for phases A, B, and C. Can be mapped to voltage sensors or set to a **Fixed Value** of `230` (representing 230.0 V). Factor = 10 (230.0 × 10 = 2300 in the register).

#### Recommended Registers

- **37117 (Power factor):** Cos phi of the grid connection. Map to your power factor sensor. Factor = 1000 (e.g., 0.95 → 950 in the register).
- **37118 (Grid frequency):** Grid frequency in Hz. Map to your frequency sensor. Factor = 100 (e.g., 50.0 Hz → 5000 in the register).
- **37100 (Meter status):** Online/offline status of the meter. Set as a **Fixed Value** of `1` (online). Factor = 1.

#### Optional Registers (for completeness)

- **37107, 37109, 37111 (Phase Currents):** Grid current for phases A, B, and C. Map to current sensors if available. Factor = 10 (e.g., 15.5 A → 155 in the register).
- **37115 (Reactive power):** Total reactive power in VAR. Map to a reactive power sensor if available. Factor = 1000.
- **37119 (Positive active electricity):** Accumulated imported energy in Wh. Map to a grid import energy sensor. Factor = 1.
- **37121 (Reverse active electricity):** Accumulated exported energy in Wh. Map to a grid export energy sensor. Factor = 1.
- **37123 (Accumulated reactive power):** Accumulated reactive energy in varh. Factor = 1.
- **37126, 37128, 37130 (Line Voltages):** A-B, B-C, and C-A line-to-line voltages. Typically only needed for three-phase setups. Factor = 10.
- **37132, 37134, 37136 (Phase Active Power):** Per-phase active power breakdown. Map to individual phase power sensors if available. Factor = 1.
- **37138 (Meter model detection):** Detection result for the meter model. Usually left unmapped or set to a fixed value.

## Troubleshooting

- **Address already in use:** The integration runs a Modbus TCP server on port `502` and a UDP discovery listener (default port `6600`, or `10086` for SPC231+ firmware). Ensure no other add-ons or integrations on your Home Assistant OS are occupying these ports.
- **SCharger doesn't connect:** Ensure that your SCharger is on the same local network subnet as your Home Assistant instance, as UDP broadcasts are used for discovery.
- **Wrong UDP discovery port:** SCharger firmware `V100R023C10SPC231` and later changed the UDP discovery port from `6600` to `10086`. If your SCharger is running SPC231+, go to **Settings** > **Devices & Services** > **Huawei Virtual Meter Emulator** > **CONFIGURE** > **Edit settings** and set the UDP Discovery Port to `10086`. Then reload the integration.
- **SCharger sends TLS on port 502:** SChargers with firmware SPC231 enforce TLS-secured Modbus (MBAS) when the discovery handshake is not completed. Ensuring the UDP discovery port is correct (10086 for SPC231+) allows the SCharger to receive the discovery response and establish a non-TLS connection.

## Disclaimer

This project is not affiliated with, endorsed by, or connected to Huawei in any way. Use at your own risk. Incorrect power values fed to the SCharger could lead to unintended charging behavior.
