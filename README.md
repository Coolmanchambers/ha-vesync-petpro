# VeSync Vital Pet Pro for Home Assistant

Unofficial custom integration for the **Levoit Vital Pet Pro** air purifier (LAP-P501S-WUSR /
LAP-P501S-AUSR). Home Assistant's built-in VeSync integration doesn't support this model yet
(see [pyvesync PR #532](https://github.com/webdjoe/pyvesync/pull/532)). This fills the gap until
it does.

It runs **beside** the built-in VeSync integration and doesn't change it. Your other VeSync
devices stay where they are, and this integration only picks up Vital Pet Pro units.

> Temporary by design. When Home Assistant's VeSync integration supports the Vital Pet Pro,
> remove this integration and add the purifiers there.

## Install (HACS)

1. HACS > three-dot menu > **Custom repositories**. Add
   `https://github.com/Coolmanchambers/ha-vesync-petpro` with type **Integration**.
2. Find **VeSync Vital Pet Pro** in HACS and download it.
3. Restart Home Assistant.
4. Settings > Devices & services > **Add integration** > **VeSync Vital Pet Pro**. Sign in with
   your VeSync account and choose whether to enable controls.

## What you get per purifier

| Entity | Type |
|---|---|
| PM2.5, VOC, odor level, air quality level | sensor |
| Filter life (%), filter days remaining | sensor |
| Fan speed, mode | sensor |
| Filter door, auto-clean running | binary sensor |
| Purifier: power, 3 speeds, Sleep and OdorShield presets | fan (controls on) |
| Child lock, display | switch (controls on) |
| Beeper, display schedule, error code, clean-air totals | diagnostic |

With controls turned off (integration options), power, child lock and display show as
read-only binary sensors instead.

## Good to know

- **Commands are slow to show.** VeSync accepts a command right away, but the purifier's
  reported state can take two to three minutes to change. The integration shows the value you
  set for up to 5 minutes while it waits. If the purifier never reports it, the integration
  logs a warning and goes back to what the purifier reports.
- **Air quality level** is shown as the raw number the purifier reports. Its scale has not been
  confirmed against the VeSync app yet.
- **Logins are kept to a minimum.** Setup logs in once and stores the session token. Restarts
  reuse it. If VeSync rejects the token, the integration logs in again at most once every 5
  minutes. If the token is rejected again, it asks you to re-enter your password instead of
  retrying. Repeated logins can get a VeSync account temporarily locked.
- Polls VeSync's cloud every 60 seconds.

## How it works

The integration carries its own private copy of
[pyvesync](https://github.com/webdjoe/pyvesync) (MIT) in
`custom_components/vesync_petpro/_pyvesync`, so the built-in integration's copy is never
touched. The copy is pyvesync's `dev` branch with:

- PR #532 by @rocord01 (Vital Pet Pro support and the `_packFileSignature` request header)
- a dedicated Vital Pet Pro device entry (fan 1-3, OdorShield modes) and a fix for camelCase
  mode names
- a fresh trace ID and current token on every request (the upstream versions are cached)
- a bounded token retry (upstream issue #558) and a separate terminal ID, so this integration
  and the built-in one never share a VeSync session

The changes are in [`patches/`](patches). `tools/vendor_pyvesync.py` rebuilds the vendored
copy.

## Uninstall

Remove the integration under Settings > Devices & services, remove it in HACS, then restart.

## Development

Tests use `pytest-homeassistant-custom-component`:

```bash
pip install pytest-homeassistant-custom-component
pytest
```

## Credits and license

- pyvesync by Joe Trabulsy, Mark Perdue and contributors (MIT).
- Vital Pet Pro support and signature work by @rocord01 in pyvesync PR #532.
- This repository: MIT, see [LICENSE](LICENSE).

Not affiliated with Levoit, VeSync or Etekcity.
