import os
import sys
import time
import asyncio
import logging
from pathlib import Path

# Add project root
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

# Ensure UTF-8 output
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from config import Config
from database import StockDatabase
from tracker.session import BlinkitSessionManager
from tracker.scraper import BlinkitScraper
from tracker.poller import HotWheelsPoller
from bot.notifier import TelegramNotifier

import urllib.request
import json

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("GitHubCloudSniper")

def trigger_next_github_run():
    """Triggers the next workflow run via GitHub API to keep 24/7 loop alive."""
    token = os.getenv("GITHUB_TOKEN")
    repo = os.getenv("GITHUB_REPOSITORY")
    workflow = os.getenv("GITHUB_WORKFLOW_REF", "sniper.yml")
    if not token or not repo:
        logger.info("Not running in GitHub Actions with GITHUB_TOKEN; skipping auto-retrigger.")
        return

    # Extract workflow file name
    wf_file = "sniper.yml"
    url = f"https://api.github.com/repos/{repo}/actions/workflows/{wf_file}/dispatches"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "BlinkitHotWheelsSniper",
    }
    payload = json.dumps({"ref": os.getenv("GITHUB_REF_NAME", "main")}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req) as resp:
            if resp.status in (200, 204):
                logger.info("Successfully triggered next 24/7 GitHub Actions run!")
            else:
                logger.warning(f"GitHub retrigger response code: {resp.status}")
    except Exception as e:
        logger.warning(f"Could not trigger next GitHub run: {e}")

async def main():
    print("""
    ================================================================
     ☁️  BLINKIT HOT WHEELS SNIPER - 24/7 GITHUB CLOUD RUNNER  ☁️
    ================================================================
    """)

    # Max runtime: default 5.5 hours (19800 seconds) to fit in GitHub Actions 6-hour limit
    max_duration_seconds = int(os.getenv("MAX_RUNTIME_SECONDS", str(5 * 3600 + 30 * 60)))
    start_time = time.time()

    # Preload specific URLs from config into watchlist if configured
    db = StockDatabase(Config.DB_PATH)
    if Config.TARGET_PRODUCT_URLS:
        logger.info(f"Preloading {len(Config.TARGET_PRODUCT_URLS)} specific URLs into watchlist...")
        for u in Config.TARGET_PRODUCT_URLS:
            pid = BlinkitScraper.extract_product_id_from_url(u) or f"hw_{abs(hash(u)) % 1000000}"
            db.add_to_watchlist(product_id=pid, url=u, name="Tracked Hot Wheels", price="N/A", in_stock=False)

    logger.info(f"Target Delivery Location: {Config.TARGET_LOCALITY} (PIN: {Config.TARGET_PINCODE})")
    logger.info(f"Coordinates: Lat {Config.TARGET_LAT}, Lon {Config.TARGET_LON}")
    logger.info(f"Scan Interval: {Config.CHECK_INTERVAL_SECONDS}s")
    logger.info(f"Session Max Duration: {max_duration_seconds // 3600} hours {(max_duration_seconds % 3600) // 60} minutes")

    session_manager = BlinkitSessionManager(
        user_data_dir=Config.USER_DATA_DIR,
        headless=True,
        lat=Config.TARGET_LAT,
        lon=Config.TARGET_LON,
        locality=Config.TARGET_LOCALITY
    )

    scraper = BlinkitScraper(query=Config.SEARCH_QUERY)
    notifier = TelegramNotifier(Config.TELEGRAM_BOT_TOKEN, Config.TELEGRAM_CHAT_ID)
    poller = HotWheelsPoller(session_manager, scraper, db, notifier, Config)

    # Send startup message to Telegram
    if notifier.is_configured:
        await notifier.send_system_message(
            f"☁️ <b>24/7 Cloud Sniper is Active on GitHub!</b>\n\n"
            f"📍 <b>Location:</b> {Config.TARGET_LOCALITY} ({Config.TARGET_PINCODE})\n"
            f"🎯 <b>Watchlist Items:</b> {len(db.get_watchlist())}\n"
            f"⏱️ <b>Scan Frequency:</b> Every {Config.CHECK_INTERVAL_SECONDS}s\n\n"
            f"<i>Your laptop can stay closed. You will receive alerts here 24/7!</i>"
        )

    # Start poller
    await poller.start()

    try:
        while (time.time() - start_time) < max_duration_seconds:
            await asyncio.sleep(5)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        logger.info("Session duration reached. Stopping current runner...")
        await poller.stop()

        # Seamlessly trigger next GitHub Actions run
        trigger_next_github_run()
        logger.info("Handover complete.")

if __name__ == "__main__":
    asyncio.run(main())
