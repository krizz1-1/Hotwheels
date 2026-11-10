import sys
import asyncio
import logging
import signal
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
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
from bot.handlers import BotHandlers

from telegram.ext import ApplicationBuilder, CommandHandler

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(BASE_DIR / "bot.log", encoding="utf-8"),
    ]
)
logger = logging.getLogger("BlinkitSniper")

async def main():
    print("""
    ========================================================
     🔥 BLINKIT HOT WHEELS RESTOCK SNIPER BOT 🔥
    ========================================================
    """)

    # Check configuration
    warnings = Config.validate()
    if warnings:
        print("\n⚠️  CONFIGURATION WARNING:")
        for w in warnings:
            print(f"  • {w}")
        print("\n👉 Please edit '.env' in this folder and add your TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.")
        print("   See README.md for instructions.\n")

    # Initialize components
    logger.info("Initializing database...")
    db = StockDatabase(Config.DB_PATH)

    logger.info(f"Target Delivery Location: {Config.TARGET_LOCALITY} (PIN: {Config.TARGET_PINCODE})")
    logger.info(f"Coordinates: Lat {Config.TARGET_LAT}, Lon {Config.TARGET_LON}")

    session_manager = BlinkitSessionManager(
        user_data_dir=Config.USER_DATA_DIR,
        headless=Config.HEADLESS,
        lat=Config.TARGET_LAT,
        lon=Config.TARGET_LON,
        locality=Config.TARGET_LOCALITY
    )

    scraper = BlinkitScraper(query=Config.SEARCH_QUERY)
    notifier = TelegramNotifier(Config.TELEGRAM_BOT_TOKEN, Config.TELEGRAM_CHAT_ID)
    poller = HotWheelsPoller(session_manager, scraper, db, notifier, Config)
    handlers = BotHandlers(poller, db, Config)

    # Preload specific URLs from config into watchlist if configured
    if Config.TARGET_PRODUCT_URLS:
        logger.info(f"Preloading {len(Config.TARGET_PRODUCT_URLS)} specific URLs into watchlist...")
        for u in Config.TARGET_PRODUCT_URLS:
            pid = BlinkitScraper.extract_product_id_from_url(u) or f"hw_{abs(hash(u)) % 1000000}"
            db.add_to_watchlist(product_id=pid, url=u, name="Tracked Hot Wheels", price="N/A", in_stock=False)

    # Start stock poller
    await poller.start()

    # Build Telegram Bot application if token is provided
    app = None
    if Config.TELEGRAM_BOT_TOKEN and Config.TELEGRAM_BOT_TOKEN != "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        logger.info("Setting up Telegram Bot command listeners...")
        app = ApplicationBuilder().token(Config.TELEGRAM_BOT_TOKEN).build()

        app.add_handler(CommandHandler("start", handlers.start_command))
        app.add_handler(CommandHandler("check", handlers.check_command))
        app.add_handler(CommandHandler("items", handlers.items_command))
        app.add_handler(CommandHandler("status", handlers.status_command))
        app.add_handler(CommandHandler("setinterval", handlers.setinterval_command))
        app.add_handler(CommandHandler("help", handlers.help_command))

        # Watchlist commands for tracking specific Hot Wheels by URL
        app.add_handler(CommandHandler("track", handlers.track_command))
        app.add_handler(CommandHandler("add", handlers.track_command))
        app.add_handler(CommandHandler("untrack", handlers.untrack_command))
        app.add_handler(CommandHandler("remove", handlers.untrack_command))
        app.add_handler(CommandHandler("watchlist", handlers.watchlist_command))
        app.add_handler(CommandHandler("tracked", handlers.watchlist_command))

        # Start bot application
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        logger.info("Telegram Bot listener is active! Send /start in Telegram.")

        # Send startup notification to chat if configured
        if Config.TELEGRAM_CHAT_ID and Config.TELEGRAM_CHAT_ID != "YOUR_TELEGRAM_CHAT_ID_HERE":
            await notifier.send_system_message(
                f"🟢 <b>Blinkit Hot Wheels Sniper is now active!</b>\n\n"
                f"📍 <b>Location:</b> {Config.TARGET_LOCALITY} ({Config.TARGET_PINCODE})\n"
                f"⏱️ <b>Scan Interval:</b> {Config.CHECK_INTERVAL_SECONDS}s\n"
                f"Send /check anytime to see live stock."
            )
    else:
        logger.warning("Telegram Bot is running in STANDALONE MONITORING MODE (no Telegram token supplied).")
        logger.warning("Restock events will be printed to this console.")

    # Keep running until interrupted
    stop_event = asyncio.Event()

    def signal_handler():
        logger.info("Shutdown signal received...")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # Signal handling on Windows
            pass

    try:
        while not stop_event.is_set():
            await asyncio.sleep(1)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        logger.info("Shutting down bot and poller...")
        await poller.stop()
        if app:
            if app.updater:
                await app.updater.stop()
            await app.stop()
            await app.shutdown()
        logger.info("Shutdown complete.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot exited by user.")
