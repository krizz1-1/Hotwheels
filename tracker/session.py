import os
import logging
from pathlib import Path
from typing import Optional
from playwright.async_api import async_playwright, BrowserContext, Page, Playwright

logger = logging.getLogger(__name__)

STEALTH_JS = """
// Overwrite navigator.webdriver to prevent bot detection
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined
});
// Mock chrome runtime
window.chrome = {
    runtime: {}
};
// Mock languages
Object.defineProperty(navigator, 'languages', {
    get: () => ['en-US', 'en']
});
// Mock plugins length
Object.defineProperty(navigator, 'plugins', {
    get: () => [1, 2, 3, 4, 5]
});
"""

class BlinkitSessionManager:
    def __init__(self, user_data_dir: Path, headless: bool = True, lat: float = 28.6139, lon: float = 77.2090, locality: str = "Delhi"):
        self.user_data_dir = str(user_data_dir)
        self.headless = headless
        self.lat = lat
        self.lon = lon
        self.locality = locality

        self._playwright: Optional[Playwright] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    async def initialize(self) -> Page:
        """Launches persistent browser context and prepares the page."""
        if self._page and not self._page.is_closed():
            return self._page

        logger.info(f"Initializing Blinkit browser session (Headless: {self.headless})...")
        os.makedirs(self.user_data_dir, exist_ok=True)

        self._playwright = await async_playwright().start()

        # Launch persistent context to preserve Cloudflare clearance & cookies
        self._context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=self.user_data_dir,
            headless=self.headless,
            viewport={"width": 1366, "height": 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            permissions=["geolocation"],
            geolocation={"latitude": self.lat, "longitude": self.lon},
            locale="en-IN",
            timezone_id="Asia/Kolkata",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-infobars",
            ]
        )

        # Inject stealth evasions into all pages
        await self._context.add_init_script(STEALTH_JS)

        # Preload Blinkit location cookies
        domain = ".blinkit.com"
        cookies = [
            {"name": "gr_1_lat", "value": str(self.lat), "domain": domain, "path": "/"},
            {"name": "gr_1_lon", "value": str(self.lon), "domain": domain, "path": "/"},
            {"name": "gr_1_locality", "value": self.locality, "domain": domain, "path": "/"},
            {"name": "lat", "value": str(self.lat), "domain": domain, "path": "/"},
            {"name": "lon", "value": str(self.lon), "domain": domain, "path": "/"},
        ]
        await self._context.add_cookies(cookies)

        pages = self._context.pages
        self._page = pages[0] if pages else await self._context.new_page()
        return self._page

    async def get_page(self) -> Page:
        if not self._page or self._page.is_closed():
            return await self.initialize()
        return self._page

    async def update_location(self, lat: float, lon: float, locality: str):
        """Updates coordinates and re-applies location cookies."""
        self.lat = lat
        self.lon = lon
        self.locality = locality
        if self._context:
            domain = ".blinkit.com"
            cookies = [
                {"name": "gr_1_lat", "value": str(lat), "domain": domain, "path": "/"},
                {"name": "gr_1_lon", "value": str(lon), "domain": domain, "path": "/"},
                {"name": "gr_1_locality", "value": locality, "domain": domain, "path": "/"},
            ]
            await self._context.add_cookies(cookies)

    async def close(self):
        """Cleanly closes browser session."""
        try:
            if self._context:
                await self._context.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            logger.debug(f"Error during browser close: {e}")
        finally:
            self._context = None
            self._page = None
            self._playwright = None
