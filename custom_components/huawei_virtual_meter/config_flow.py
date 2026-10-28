"""Configure meter settings without replacing existing register options."""

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components import network
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    ANY_UNIT_ID,
    CONF_EMULATOR_IP,
    CONF_REGISTERS,
    CONF_SERIAL,
    CONF_UDP_PORT,
    CONF_UNIT_ID,
    DEFAULT_UDP_PORT,
    DEFAULT_UNIT_ID,
    DOMAIN,
    METER_REGISTERS,
)


def _integer(value):
    """Accept integral selector values without truncating fractional inputs."""
    try:
        integer = int(value)
    except (ValueError, TypeError, OverflowError) as err:
        raise vol.Invalid("Expected an integer") from err
    if isinstance(value, bool) or isinstance(value, float) and integer != value:
        raise vol.Invalid("Expected an integer")
    return integer


UDP_PORT = vol.All(_integer, vol.Range(min=1, max=65535))
UNIT_ID = vol.All(_integer, vol.Range(min=0, max=255))
SERIAL = vol.All(str, vol.Length(min=1, max=20), vol.Match(r"^[\x20-\x7e]+$"))


def _validate_settings(user_input):
    """Validate submissions as well as form schemas (including API callers)."""
    data = dict(user_input)
    errors = {}
    for key, validator, error in (
        (CONF_UDP_PORT, UDP_PORT, "invalid_port"),
        (CONF_UNIT_ID, UNIT_ID, "invalid_unit_id"),
        (CONF_SERIAL, SERIAL, "invalid_serial"),
    ):
        if key not in data:
            continue
        try:
            data[key] = validator(data[key])
        except vol.Invalid:
            errors[key] = error
    return data, errors


def _number_box(minimum, maximum):
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimum, max=maximum, step=1, mode=selector.NumberSelectorMode.BOX
        )
    )


class VirtualMeterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            data, errors = _validate_settings(user_input)
            if not errors:
                return self.async_create_entry(
                    title=f"Virtual Meter ({data[CONF_SERIAL]})", data=data
                )

        adapters = await network.async_get_adapters(self.hass)
        ip_options = []
        for adapter in adapters:
            # Zeige IPs von ALLEN Adaptern, auch wenn sie in HA als "nicht aktiviert" gelten
            for ip_info in adapter.get("ipv4", []):
                ip_options.append(
                    {
                        "label": f"{ip_info['address']} ({adapter.get('name', 'Unknown')})",
                        "value": ip_info["address"],
                    }
                )

        if not ip_options:
            ip_options = [{"label": "0.0.0.0 (Fallback)", "value": "0.0.0.0"}]

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_EMULATOR_IP, default=ip_options[0]["value"]
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=ip_options)
                    ),
                    vol.Required(CONF_SERIAL, default="HV0000000001"): SERIAL,
                    vol.Required(CONF_UDP_PORT, default=DEFAULT_UDP_PORT): _number_box(
                        1, 65535
                    ),
                    vol.Required(CONF_UNIT_ID, default=DEFAULT_UNIT_ID): _number_box(
                        0, 255
                    ),
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return VirtualMeterOptionsFlowHandler()


class VirtualMeterOptionsFlowHandler(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        """Hauptmenü der Optionen."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["add_register", "edit_registers", "edit_settings"],
        )

    async def async_step_edit_settings(self, user_input=None):
        """UDP Discovery Port, Unit ID und andere Einstellungen bearbeiten."""
        errors = {}
        if user_input is not None:
            data, errors = _validate_settings(user_input)
            if not errors:
                new_data = dict(self.config_entry.data)
                new_data[CONF_UDP_PORT] = data[CONF_UDP_PORT]
                new_data[CONF_UNIT_ID] = data[CONF_UNIT_ID]
                # Only data changes. The integration's update listener owns reloads.
                self.hass.config_entries.async_update_entry(
                    self.config_entry, data=new_data
                )
                return self.async_abort(reason="settings_saved")

        current_udp_port = self.config_entry.data.get(CONF_UDP_PORT, DEFAULT_UDP_PORT)
        current_unit_id = self.config_entry.data.get(CONF_UNIT_ID, ANY_UNIT_ID)

        return self.async_show_form(
            step_id="edit_settings",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_UDP_PORT, default=current_udp_port): _number_box(
                        1, 65535
                    ),
                    vol.Required(CONF_UNIT_ID, default=current_unit_id): _number_box(
                        0, 255
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_add_register(self, user_input=None):
        """Ein neues Register-Mapping hinzufügen (Schritt 1)."""
        errors = {}
        if user_input is not None:
            self.add_addr = user_input["address"]
            return await self.async_step_add_register_details()

        queried = set()
        if (
            DOMAIN in self.hass.data
            and self.config_entry.entry_id in self.hass.data[DOMAIN]
        ):
            entry_data = self.hass.data[DOMAIN][self.config_entry.entry_id]
            queried = set(entry_data.get("queried_registers", set()))

        queried.update(METER_REGISTERS.keys())
        configured = set(self.config_entry.options.get(CONF_REGISTERS, {}).keys())

        available = []
        for r in sorted([int(x) for x in queried]):
            if str(r) in configured:
                continue

            # Verstecke Register, die die untere Hälfte eines 32-Bit Registers sind
            prev_reg = METER_REGISTERS.get(r - 1)
            if prev_reg and prev_reg.get("width", 1) == 2:
                continue

            available.append(str(r))

        options = []
        for r_str in available:
            r = int(r_str)
            reg_def = METER_REGISTERS.get(r)
            if reg_def:
                label = f"Reg {r}: {reg_def['name']} ({reg_def['type']})"
            else:
                label = f"Reg {r} (abgefragt)"
            options.append({"label": label, "value": r_str})

        if not options:
            options = [{"label": "Eigene Adresse eingeben...", "value": ""}]

        return self.async_show_form(
            step_id="add_register",
            data_schema=vol.Schema(
                {
                    vol.Required("address"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options, custom_value=True
                        )
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_add_register_details(self, user_input=None):
        """Ein neues Register-Mapping hinzufügen (Schritt 2)."""
        errors = {}
        try:
            addr_int = int(self.add_addr)
            if not 0 <= addr_int <= 65535:
                raise ValueError
        except (ValueError, TypeError):
            return self.async_abort(reason="invalid_address")

        default_factor = METER_REGISTERS.get(addr_int, {}).get("gain", 1.0)

        if user_input is not None:
            entity_id = user_input.get("entity_id")
            fixed_value = user_input.get("fixed_value")

            if not entity_id and fixed_value is None:
                errors["base"] = "missing_value"
            else:
                regs = dict(self.config_entry.options.get(CONF_REGISTERS, {}))
                regs[str(addr_int)] = {"factor": user_input.get("factor", 1.0)}
                if entity_id:
                    regs[str(addr_int)]["entity_id"] = entity_id
                else:
                    regs[str(addr_int)]["fixed_value"] = fixed_value
                return self.async_create_entry(
                    title="", data={**self.config_entry.options, CONF_REGISTERS: regs}
                )

        return self.async_show_form(
            step_id="add_register_details",
            data_schema=vol.Schema(
                {
                    vol.Optional("entity_id"): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain=["sensor", "number", "input_number"]
                        )
                    ),
                    vol.Optional("fixed_value"): vol.Coerce(float),
                    vol.Required("factor", default=default_factor): vol.Coerce(float),
                }
            ),
            errors=errors,
        )

    async def async_step_edit_registers(self, user_input=None):
        """Bestehende Register in einer Tabelle bearbeiten."""
        current_regs = dict(self.config_entry.options.get(CONF_REGISTERS, {}))

        if user_input is not None:
            new_regs = {}
            for r_str in current_regs.keys():
                ent = user_input.get(f"entity_{r_str}")
                fix = user_input.get(f"fixed_value_{r_str}")
                fac = user_input.get(f"factor_{r_str}", 1.0)

                # Wenn beides leer ist, wird das Register als gelöscht betrachtet
                if ent or fix is not None:
                    new_regs[r_str] = {"factor": fac}
                    if ent:
                        new_regs[r_str]["entity_id"] = ent
                    else:
                        new_regs[r_str]["fixed_value"] = fix

            return self.async_create_entry(
                title="", data={**self.config_entry.options, CONF_REGISTERS: new_regs}
            )

        schema = {}
        for r_str, conf in current_regs.items():
            # HA generiert aus "entity_37101" den Namen "Entity 37101"
            schema[
                vol.Optional(
                    f"entity_{r_str}",
                    description={"suggested_value": conf.get("entity_id")},
                )
            ] = selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain=["sensor", "number", "input_number"]
                )
            )

            schema[
                vol.Optional(
                    f"fixed_value_{r_str}",
                    description={"suggested_value": conf.get("fixed_value")},
                )
            ] = vol.Coerce(float)

            schema[vol.Required(f"factor_{r_str}", default=conf.get("factor", 1.0))] = (
                vol.Coerce(float)
            )

        # Wenn keine konfiguriert sind, abbrechen mit Hinweis
        if not schema:
            return self.async_abort(reason="no_registers")

        return self.async_show_form(
            step_id="edit_registers", data_schema=vol.Schema(schema)
        )
