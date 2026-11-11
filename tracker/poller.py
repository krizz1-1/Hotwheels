import asyncio
import logging
import datetime
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

class HotWheelsPoller:
    def __init__(self, session_manager, scraper, database, notifier, config):
        self.session = session_manager
        self.scraper = scraper
        self.db = database
        self.notifier = notifier
        self.config = config

        self.is_running = False
        self.last_check_time: Optional[datetime.datetime] = None
        self._task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    async def start(self):
        """Starts the background polling loop."""
        if self.is_running:
            return
        self.is_running = True
        logger.info(f"Starting Hot Wheels restock poller (Interval: {self.config.CHECK_INTERVAL_SECONDS}s)...")
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self):
        """Stops the background poller cleanly."""
        self.is_running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self.session.close()
        logger.info("Hot Wheels restock poller stopped.")

    async def trigger_manual_check(self) -> List[Dict[str, Any]]:
        """Performs an immediate stock check (used by /check command)."""
        async with self._lock:
            return await self._perform_check()

    async def check_specific_url(self, url: str) -> Optional[Dict[str, Any]]:
        """Checks a specific product URL or ID immediately."""
        async with self._lock:
            page = await self.session.get_page()
            return await self.scraper.fetch_product_by_url(page, url)

    async def _perform_check(self) -> List[Dict[str, Any]]:
        """Single stock check iteration covering general search and specific watchlist."""
        page = await self.session.get_page()
        items = await self.scraper.scrape(page)
        self.last_check_time = datetime.datetime.now()

        # 1. Process general search items
        restock_count = 0
        for item in items:
            item["locality"] = self.config.TARGET_LOCALITY
            event = self.db.process_product(item)
            if event == "RESTOCK" or (
                event == "NEW_DISCOVERY" and self.config.ALERT_NEW_DISCOVERIES
            ):
                logger.info(f"🚨 {event} DETECTED: {item.get('name')} at {item.get('price')}!")
                restock_count += 1
                asyncio.create_task(self.notifier.send_restock_alert(item, event))

        # 2. Process specific Watchlist items
        watchlist = self.db.get_watchlist()
        if watchlist:
            logger.info(f"Checking {len(watchlist)} specific watchlist items...")
            for w in watchlist:
                w_pid = w["product_id"]
                try:
                    live_pdp = await self.scraper.fetch_product_by_id(page, w_pid)
                    if live_pdp:
                        live_pdp["locality"] = self.config.TARGET_LOCALITY
                        live_pdp["url"] = w["url"]
                        event = self.db.update_watchlist_item(
                            product_id=w_pid,
                            in_stock=live_pdp.get("in_stock", False),
                            price=live_pdp.get("price", ""),
                            name=live_pdp.get("name", ""),
                            image_url=live_pdp.get("image_url", ""),
                        )
                        if event == "WATCHLIST_RESTOCK":
                            logger.info(f"🎯 WATCHLIST RESTOCK DETECTED: {live_pdp.get('name')}!")
                            asyncio.create_task(self.notifier.send_watchlist_alert(live_pdp))
                except Exception as w_err:
                    logger.debug(f"Error checking watchlist item {w_pid}: {w_err}")

        if restock_count > 0:
            logger.info(f"Fired {restock_count} instant restock alerts!")

        return items

    async def _poll_loop(self):
        """Continuous background monitoring loop."""
        # Initial wait to let bot initialize
        await asyncio.sleep(2)

        while self.is_running:
            try:
                logger.info("Running scheduled Hot Wheels stock scan...")
                async with self._lock:
                    items = await self._perform_check()
                in_stock = sum(1 for it in items if it.get("in_stock"))
                logger.info(f"Scan complete: {len(items)} items found ({in_stock} in stock).")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error during stock scan: {e}", exc_info=True)

            # Wait for next interval
            interval = max(self.config.CHECK_INTERVAL_SECONDS, self.config.MIN_INTERVAL_SECONDS)
            await asyncio.sleep(interval)
