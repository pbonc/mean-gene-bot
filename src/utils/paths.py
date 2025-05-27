from pathlib import Path

BASE_DIR = Path(__file__).parents[2]  # Adjust to root of project if needed
DWF_DIR = BASE_DIR / "dwf"
PROMO_DIR = DWF_DIR / "promos"

WRESTLERS_FILE = DWF_DIR / "wrestlers.json"
PENDING_PROMOS_FILE = PROMO_DIR / "pending.json"
APPROVED_PROMOS_FILE = PROMO_DIR / "approved.json"
HISTORY_PROMOS_FILE = PROMO_DIR / "history.json"