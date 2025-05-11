import os
import logging
import traceback
from bot.core import MeanGeneBot

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(LOG_DIR, "mean-gene-bot-crash.log"),
    level=logging.ERROR,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

if __name__ == "__main__":
    try:
        print("🛠 Constructing MeanGeneBot...")
        bot = MeanGeneBot()
        print("🚀 Running bot...")
        bot.run()
    except Exception:
        print("💥 Bot failed to start.")
        traceback.print_exc()
