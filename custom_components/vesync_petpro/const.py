"""Constants for the VeSync Vital Pet Pro integration."""

from datetime import timedelta

DOMAIN = "vesync_petpro"
MODEL_PREFIX = "LAP-P501S"

CONF_ALLOW_CONTROL = "allow_control"
CONF_TOKEN = "token"
CONF_ACCOUNT_ID = "account_id"
CONF_COUNTRY_CODE = "country_code"
CONF_REGION = "current_region"

SCAN_INTERVAL = timedelta(seconds=60)
REQUEST_TIMEOUT = 30

# VeSync accepts commands immediately but the purifier can apply them minutes later
# (observed 2026-10-15: not applied after 6 s, applied within 5 min). An unconfirmed
# write is shown over contradicting cloud polls for this long, then dropped.
PENDING_TIMEOUT = 300

MODE_MANUAL = "manual"
MODE_LABELS = {
    "sleep": "Sleep",
    "manual": "Manual",
    "odorShieldQuiet": "OdorShield Quiet",
    "odorShieldBalanced": "OdorShield Balanced",
    "odorShieldPerformance": "OdorShield Performance",
}
PRESET_MODES = {label: mode for mode, label in MODE_LABELS.items() if mode != MODE_MANUAL}
FAN_LEVELS = [1, 2, 3]
FAN_LEVEL_OFF = 255
