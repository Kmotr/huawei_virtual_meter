import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
from .const import DOMAIN, CONF_REGISTERS, CONF_EMULATOR_IP, CONF_SERIAL

class VirtualMeterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title=f"Virtual Meter ({user_input[CONF_SERIAL]})", data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_EMULATOR_IP): str,
                vol.Required(CONF_SERIAL, default="HV2340181405"): str,
            })
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return VirtualMeterOptionsFlowHandler(config_entry)

class VirtualMeterOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Hauptmenü der Optionen."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["add_register", "manage_registers"]
        )

    async def async_step_add_register(self, user_input=None):
        """Ein neues Register-Mapping hinzufügen."""
        if user_input is not None:
            regs = dict(self.config_entry.options.get(CONF_REGISTERS, {}))
            reg_addr = str(user_input["address"])
            regs[reg_addr] = {
                "entity_id": user_input["entity_id"],
                "factor": user_input["factor"]
            }
            return self.async_create_entry(title="", data={CONF_REGISTERS: regs})

        return self.async_show_form(
            step_id="add_register",
            data_schema=vol.Schema({
                vol.Required("address"): vol.All(vol.Coerce(int), vol.Range(min=0)),
                vol.Required("entity_id"): selector.EntitySelector(selector.EntitySelectorConfig(domain=["sensor", "number", "input_number"])),
                vol.Required("factor", default=1.0): vol.Coerce(float),
            })
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
