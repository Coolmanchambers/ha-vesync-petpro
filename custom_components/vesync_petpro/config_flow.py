"""Config flow: one VeSync account per entry; options toggle the controls."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from aiohttp import ClientError
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from ._pyvesync.utils.errors import VeSyncError, VeSyncLoginError
from .const import CONF_ACCOUNT_ID, CONF_ALLOW_CONTROL, DOMAIN
from .hub import PetProHub

_LOGGER = logging.getLogger(__name__)

PASSWORD_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


class NoPetPro(Exception):
    """The account has no Vital Pet Pro purifier."""


async def _validate(hass: HomeAssistant, email: str, password: str) -> dict[str, Any]:
    """Log in once and return the credentials to store, so setup needs no second login."""
    hub = PetProHub(async_get_clientsession(hass), email, password, str(hass.config.time_zone))
    await hub.async_connect()
    if not hub.devices:
        raise NoPetPro
    return hub.credentials()


class PetProConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> PetProOptionsFlow:
        return PetProOptionsFlow()

    async def _try_login(self, email: str, password: str) -> tuple[dict[str, Any] | None, str | None]:
        try:
            return await _validate(self.hass, email, password), None
        except VeSyncLoginError:
            return None, "invalid_auth"
        except NoPetPro:
            return None, "no_devices"
        except (VeSyncError, ClientError, TimeoutError):
            return None, "cannot_connect"
        except Exception:
            _LOGGER.exception("Unexpected error validating VeSync login")
            return None, "unknown"

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            email = user_input[CONF_EMAIL].strip()
            creds, error = await self._try_login(email, user_input[CONF_PASSWORD])
            if creds is not None:
                await self.async_set_unique_id(str(creds[CONF_ACCOUNT_ID]))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=email,
                    data={CONF_EMAIL: email, CONF_PASSWORD: user_input[CONF_PASSWORD], **creds},
                    options={CONF_ALLOW_CONTROL: user_input[CONF_ALLOW_CONTROL]},
                )
            errors["base"] = error or "unknown"
        schema = vol.Schema(
            {
                vol.Required(CONF_EMAIL): str,
                vol.Required(CONF_PASSWORD): PASSWORD_SELECTOR,
                vol.Required(CONF_ALLOW_CONTROL, default=True): bool,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            creds, error = await self._try_login(entry.data[CONF_EMAIL], user_input[CONF_PASSWORD])
            if creds is not None:
                return self.async_update_reload_and_abort(
                    entry, data={**entry.data, CONF_PASSWORD: user_input[CONF_PASSWORD], **creds}
                )
            errors["base"] = error or "unknown"
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): PASSWORD_SELECTOR}),
            description_placeholders={"email": entry.data[CONF_EMAIL]},
            errors=errors,
        )


class PetProOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = self.config_entry.options.get(CONF_ALLOW_CONTROL, True)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({vol.Required(CONF_ALLOW_CONTROL, default=current): bool}),
        )
