import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.components import network
from .const import DOMAIN, CONF_REGISTERS, CONF_EMULATOR_IP, CONF_SERIAL, METER_REGISTERS

class VirtualMeterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title=f"Virtual Meter ({user_input[CONF_SERIAL]})", data=user_input)

        adapters = await network.async_get_adapters(self.hass)
        ip_options = []
        for adapter in adapters:
            # Zeige IPs von ALLEN Adaptern, auch wenn sie in HA als "nicht aktiviert" gelten
            for ip_info in adapter.get("ipv4", []):
                ip_options.append({
                    "label": f"{ip_info['address']} ({adapter.get('name', 'Unknown')})", 
                    "value": ip_info['address']
                })
        
        if not ip_options:
            ip_options = [{"label": "0.0.0.0 (Fallback)", "value": "0.0.0.0"}]

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_EMULATOR_IP, default=ip_options[0]["value"]): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=ip_options)
                ),
                vol.Required(CONF_SERIAL, default="HV0000000001"): str,
            })
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
            menu_options=["add_register", "edit_registers"]
        )

    async def async_step_add_register(self, user_input=None):
        """Ein neues Register-Mapping hinzufügen (Schritt 1)."""
        errors = {}
        if user_input is not None:
            self.add_addr = user_input["address"]
            return await self.async_step_add_register_details()

        queried = set()
        if DOMAIN in self.hass.data and self.config_entry.entry_id in self.hass.data[DOMAIN]:
            entry_data = self.hass.data[DOMAIN][self.config_entry.entry_id]
            queried = entry_data.get("queried_registers", set())
            
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
            data_schema=vol.Schema({
                vol.Required("address"): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=options, custom_value=True)
                )
            }),
            errors=errors
        )

    async def async_step_add_register_details(self, user_input=None):
        """Ein neues Register-Mapping hinzufügen (Schritt 2)."""
        errors = {}
        try:
            addr_int = int(self.add_addr)
            if addr_int < 0: raise ValueError
        except ValueError:
            return self.async_abort(reason="invalid_address")
            
        default_factor = METER_REGISTERS.get(addr_int, {}).get("gain", 1.0)
        
        if user_input is not None:
            entity_id = user_input.get("entity_id")
            fixed_value = user_input.get("fixed_value")
            
            if not entity_id and fixed_value is None:
                errors["base"] = "missing_value"
            else:
                regs = dict(self.config_entry.options.get(CONF_REGISTERS, {}))
                regs[str(addr_int)] = {
                    "factor": user_input.get("factor", 1.0)
                }
                if entity_id: regs[str(addr_int)]["entity_id"] = entity_id
                else: regs[str(addr_int)]["fixed_value"] = fixed_value
                return self.async_create_entry(title="", data={CONF_REGISTERS: regs})
                
        return self.async_show_form(
            step_id="add_register_details",
            data_schema=vol.Schema({
                vol.Optional("entity_id"): selector.EntitySelector(selector.EntitySelectorConfig(domain=["sensor", "number", "input_number"])),
                vol.Optional("fixed_value"): vol.Coerce(float),
                vol.Required("factor", default=default_factor): vol.Coerce(float),
            }),
            errors=errors
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
                    if ent: new_regs[r_str]["entity_id"] = ent
                    else: new_regs[r_str]["fixed_value"] = fix
                    
            return self.async_create_entry(title="", data={CONF_REGISTERS: new_regs})

        schema = {}
        for r_str, conf in current_regs.items():
            r = int(r_str)
            
            # HA generiert aus "entity_37101" den Namen "Entity 37101"
            schema[vol.Optional(f"entity_{r_str}", description={"suggested_value": conf.get("entity_id")})] = selector.EntitySelector(selector.EntitySelectorConfig(domain=["sensor", "number", "input_number"]))
            
            schema[vol.Optional(f"fixed_value_{r_str}", description={"suggested_value": conf.get("fixed_value")})] = vol.Coerce(float)
            
            schema[vol.Required(f"factor_{r_str}", default=conf.get("factor", 1.0))] = vol.Coerce(float)

        # Wenn keine konfiguriert sind, zurück zum Menü
        if not schema:
            return await self.async_step_init()

        return self.async_show_form(
            step_id="edit_registers",
            data_schema=vol.Schema(schema)
        )
