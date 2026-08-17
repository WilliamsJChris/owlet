"""Constants for the Owlet Smart Sock integration."""

DOMAIN = "owlet"

CONF_OWLET_EXPIRY = "expiry"
CONF_OWLET_REFRESH = "refresh"

SUPPORTED_VERSIONS = [2, 3]
POLLING_INTERVAL = 5
MANUFACTURER = "Owlet Baby Care"
SLEEP_STATES = {0: "unknown", 1: "awake", 8: "light_sleep", 15: "deep_sleep"}

BODY_POSITION_STATES = (
    "no_data",
    "undetected",
    "on_back",
    "on_side",
    "tummy",
    "moving",
)


def decode_body_position(code: int) -> str:
    """Map Owlet sleep-data body position codes to sensor states."""
    if code == 1:
        return "moving"
    if code == 2:
        return "undetected"
    if code in (0, 3):
        return "no_data"
    if code in (4, 5):
        return "on_back"
    if 6 <= code <= 9:
        return "on_side"
    return "tummy"
