# Huawei Virtual Meter for Home Assistant

![GitHub Release](https://img.shields.io/github/v/release/kmotr/huawei_virtual_meter)
![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)

This custom integration for Home Assistant acts as a **virtual Modbus TCP server**, emulating a **Huawei Smart Power Sensor** (Smart Meter). It allows you to feed real-time power, voltage, current, and energy data from any Home Assistant entity directly into your Huawei SCharger (Smart Charger).

By utilizing this integration, your Huawei SCharger will automatically discover the virtual meter on your local network and use its data for dynamic power control, surplus solar charging logic (PV excess charging), and charging statistics—without requiring a physical Huawei Smart Power Sensor.

## Features

- 🔋 **Seamless Integration:** Emulates the official "3.3 Meter Equipment Register" Modbus map required by Huawei SChargers.
- 📡 **Auto-Discovery:** Simulates the Huawei UDP discovery protocol on port 6600, allowing the SCharger to find the meter automatically.
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
4. After adding the integration, click on **CONFIGURE** to map your registers.

## Mapping Registers

Click **CONFIGURE** on the integration page. You will see two options:

1. **Add a new register mapping:**
   - Choose the register you want to provide data for (e.g., `Register 37113: Active power`).
   - On the next screen, you can select the **Home Assistant Entity** you want to map to this register.
   - *Alternatively*, you can provide a **Fixed Value** (e.g., `1` for the "Meter Type" register).
   - The scaling factor (e.g., `10` or `100`) is automatically pre-filled according to the official Huawei Modbus specifications, but you can adjust it if your sensor requires it.
2. **Edit configured registers:**
   - Displays a complete table of all your currently mapped registers.
   - You can quickly adjust entities, fixed values, and factors all in one place.
   - To **delete** a register, simply clear both the Entity ID and the Fixed Value fields and click Submit.

### Common Huawei Registers
To get started, you will typically want to map at least the following:
- **37113 (Active power):** Your total home grid consumption/export. (Positive = consuming from grid, Negative = exporting to grid).
- **37125 (Meter type):** Usually set as a **Fixed Value**: `0` for Single-Phase, `1` for Three-Phase.
- **37101, 37103, 37105 (Phase Voltages):** Can be mapped to voltage sensors or set to a fixed value like `230`.

## Troubleshooting

- **Address already in use:** The integration runs a Modbus TCP server on port `502` and a UDP listener on port `6600`. Ensure no other add-ons or integrations on your Home Assistant OS are occupying these ports.
- **SCharger doesn't connect:** Ensure that your SCharger is on the same local network subnet as your Home Assistant instance, as UDP broadcasts are used for discovery.

## Disclaimer

This project is not affiliated with, endorsed by, or connected to Huawei in any way. Use at your own risk. Incorrect power values fed to the SCharger could lead to unintended charging behavior.
