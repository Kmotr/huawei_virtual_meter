import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.components import network
from .const import DOMAIN, CONF_REGISTERS, CONF_EMULATOR_IP, CONF_SERIAL

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
            menu_options=["add_register", "manage_registers"]
        )

    async def async_step_add_register(self, user_input=None):
        """Ein neues Register-Mapping hinzufügen."""
        errors = {}
        if user_input is not None:
            try:
                addr_int = int(user_input["address"])
                if addr_int < 0:
                    raise ValueError
                
                regs = dict(self.config_entry.options.get(CONF_REGISTERS, {}))
                reg_addr = str(addr_int)
                regs[reg_addr] = {
                    "entity_id": user_input["entity_id"],
                    "factor": user_input["factor"]
                }
                return self.async_create_entry(title="", data={CONF_REGISTERS: regs})
            except ValueError:
                errors["address"] = "invalid_address"

        queried = set()
        if DOMAIN in self.hass.data and self.config_entry.entry_id in self.hass.data[DOMAIN]:
            entry_data = self.hass.data[DOMAIN][self.config_entry.entry_id]
            queried = entry_data.get("queried_registers", set())
            
        configured = set(self.config_entry.options.get(CONF_REGISTERS, {}).keys())
        available = sorted([str(r) for r in queried if str(r) not in configured], key=lambda x: int(x))
        
        options = [{"label": f"Register {r} (abgefragt)", "value": str(r)} for r in available]

        # Wenn keine Optionen da sind, fügen wir einen Platzhalter hinzu, damit das Dropdown nicht leer aussieht
        if not options:
            options = [{"label": "Eigene Adresse eingeben...", "value": ""}]

        return self.async_show_form(
            step_id="add_register",
            data_schema=vol.Schema({
                vol.Required("address"): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=options, custom_value=True)
                ),
                vol.Required("entity_id"): selector.EntitySelector(selector.EntitySelectorConfig(domain=["sensor", "number", "input_number"])),
                vol.Required("factor", default=1.0): vol.Coerce(float),
            }),
            errors=errors
        )

    async def async_step_manage_registers(self, user_input=None):
        """Bestehende Register löschen."""
        current_regs = self.config_entry.options.get(CONF_REGISTERS, {})
        if user_input is not None:
            new_regs = {k: v for k, v in current_regs.items() if k not in user_input["to_delete"]}
            return self.async_create_entry(title="", data={CONF_REGISTERS: new_regs})

        options = {k: f"Reg {k} -> {v['entity_id']}" for k, v in current_regs.items()}
        return self.async_show_form(
            step_id="manage_registers",
            data_schema=vol.Schema({
                vol.Optional("to_delete", default=[]): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=[{"value": k, "label": v} for k, v in options.items()], multiple=True)
                ),
            })
        )
