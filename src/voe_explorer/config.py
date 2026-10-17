"""App-wide constants (values fixed by the design spec §10)."""
import os
from pathlib import Path

BASE_URL = "https://www.voe.com.ua"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"

TIMEOUT_S = 40
RETRIES = 3
RETRY_PAUSE_S = 2

REFRESH_S = 300        # card refresh
PROBE_S = 120          # VOE health probe
PLANNED_S = 3 * 3600   # planned-works list
SLOW_S = 10.0          # slower than this counts as "slow"

# "<github user>/voe-explorer-releases"; empty disables the update check.
RELEASES_REPO = ""

APP_DIR = Path(os.environ.get("APPDATA", Path.home())) / "VOE Explorer"

DEFAULT_CITY = {"value": "м.. Вінниця (Вінницька Область/М.Вінниця)", "id": "510100000"}
