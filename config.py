import os
from pathlib import Path
from dotenv import load_dotenv

# Base Directory
BASE_DIR = Path(__file__).resolve().parent

# Load environment variables from .env
env_path = BASE_DIR / ".env"
load_dotenv(dotenv_path=env_path)

class Config:
    # Telegram settings
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    # Target Location settings (Hyperlocal)
    # Default coordinates fallback (e.g., Delhi Central) if not specified
    TARGET_PINCODE = os.getenv("TARGET_PINCODE", "110001").strip()
    TARGET_LAT = float(os.getenv("TARGET_LAT", "28.6139"))
    TARGET_LON = float(os.getenv("TARGET_LON", "77.2090"))
    TARGET_LOCALITY = os.getenv("TARGET_LOCALITY", "Connaught Place").strip()

    # Tracking & Search settings
    SEARCH_QUERY = os.getenv("SEARCH_QUERY", "hot wheels").strip()
    # Check frequency in seconds (default 30 seconds for optimal speed without IP bans)
    CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL_SECONDS", "30"))
    # Minimum interval allowed
    MIN_INTERVAL_SECONDS = 10

    # Specific Hot Wheels URLs to monitor automatically (comma-separated)
    _raw_urls = os.getenv("TARGET_PRODUCT_URLS", "").strip()
    TARGET_PRODUCT_URLS = [u.strip() for u in _raw_urls.split(",") if u.strip()]

    # Browser & Scraper settings
    HEADLESS = os.getenv("HEADLESS", "true").lower() in ("true", "1", "yes")
    BROWSER_TYPE = os.getenv("BROWSER_TYPE", "chromium")
    # Keep mutable browser data outside the source tree. In Docker this is a
    # mounted volume, so the session survives container recreation.
    DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    USER_DATA_DIR = DATA_DIR / "browser_data"

    # SQLite Database path for stock status persistence
    DB_PATH = DATA_DIR / "hotwheels_stock.db"

    @classmethod
    def validate(cls) -> list[str]:
        """Validate required configuration and return list of warnings/errors."""
        errors = []
        if not cls.TELEGRAM_BOT_TOKEN or cls.TELEGRAM_BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
            errors.append("TELEGRAM_BOT_TOKEN is not set. Please add it to your .env file.")
        if not cls.TELEGRAM_CHAT_ID or cls.TELEGRAM_CHAT_ID == "YOUR_TELEGRAM_CHAT_ID_HERE":
            errors.append("TELEGRAM_CHAT_ID is not set. Please add it to your .env file.")
        return errors
