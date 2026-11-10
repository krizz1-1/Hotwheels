import logging
import asyncio
from typing import Dict, Any, Optional
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

logger = logging.getLogger(__name__)

class TelegramNotifier:
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self._bot: Optional[Bot] = None
        if token and token != "YOUR_TELEGRAM_BOT_TOKEN_HERE":
            self._bot = Bot(token=token)

    @property
    def is_configured(self) -> bool:
        return bool(self._bot and self.chat_id and self.chat_id != "YOUR_TELEGRAM_CHAT_ID_HERE")

    async def send_restock_alert(self, item: Dict[str, Any], event_type: str = "RESTOCK") -> bool:
        """
        Sends an instant high-priority Telegram alert when an item is restocked or discovered.
        """
        if not self.is_configured:
            logger.warning("TelegramNotifier: Missing bot token or chat ID. Alert not sent.")
            return False

        name = item.get("name", "Hot Wheels Car")
        price = item.get("price", "N/A")
        mrp = item.get("mrp", "")
        url = item.get("product_url", "https://blinkit.com/s/?q=hot+wheels")
        image_url = item.get("image_url")
        locality = item.get("locality", "Your Dark Store")

        if event_type == "RESTOCK":
            title = "🚨 <b>HOT WHEELS RESTOCKED ON BLINKIT!</b> 🚨"
        elif event_type == "NEW_DISCOVERY":
            title = "✨ <b>NEW HOT WHEELS FOUND IN STOCK!</b> ✨"
        else:
            title = "⚡ <b>HOT WHEELS INVENTORY UPDATE!</b> ⚡"

        mrp_text = f" (MRP: <s>{mrp}</s>)" if mrp and mrp != price else ""

        message = (
            f"{title}\n\n"
            f"🏎️ <b>Product:</b> {name}\n"
            f"💰 <b>Price:</b> <b>{price}</b>{mrp_text}\n"
            f"📍 <b>Location:</b> {locality}\n"
            f"⚡ <i>Act fast before scalpers clear the stock!</i>"
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚡ BUY NOW ON BLINKIT", url=url)]
        ])

        try:
            # If product has an image, send photo with caption
            if image_url and image_url.startswith("http"):
                try:
                    await self._bot.send_photo(
                        chat_id=self.chat_id,
                        photo=image_url,
                        caption=message,
                        parse_mode=ParseMode.HTML,
                        reply_markup=keyboard,
                    )
                    logger.info(f"Photo alert sent for {name}")
                    return True
                except Exception as photo_err:
                    logger.warning(f"Failed to send photo ({photo_err}), falling back to text.")

            # Fallback to text message
            await self._bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
                disable_web_page_preview=False,
            )
            logger.info(f"Text alert sent for {name}")
            return True

        except Exception as e:
            logger.error(f"Error sending Telegram alert: {e}")
            return False

    async def send_watchlist_alert(self, item: Dict[str, Any]) -> bool:
        """
        Sends an instant high-priority alert specifically for a user's tracked watchlist URL.
        """
        if not self.is_configured:
            logger.warning("TelegramNotifier: Missing bot token or chat ID. Alert not sent.")
            return False

        name = item.get("name", "Tracked Hot Wheels Car")
        price = item.get("price", "N/A")
        mrp = item.get("mrp", "")
        url = item.get("url") or item.get("product_url", "https://blinkit.com/s/?q=hot+wheels")
        image_url = item.get("image_url")
        locality = item.get("locality", "Your Dark Store")

        mrp_text = f" (MRP: <s>{mrp}</s>)" if mrp and mrp != price else ""

        message = (
            f"🎯 <b>WATCHLIST ITEM RESTOCKED!</b> 🎯\n\n"
            f"Your specifically tracked Hot Wheels is now <b>IN STOCK</b> on Blinkit!\n\n"
            f"🏎️ <b>Product:</b> {name}\n"
            f"💰 <b>Price:</b> <b>{price}</b>{mrp_text}\n"
            f"📍 <b>Location:</b> {locality}\n"
            f"⚡ <i>Go buy it immediately before it goes out of stock again!</i>"
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚡ BUY NOW ON BLINKIT", url=url)]
        ])

        try:
            if image_url and image_url.startswith("http"):
                try:
                    await self._bot.send_photo(
                        chat_id=self.chat_id,
                        photo=image_url,
                        caption=message,
                        parse_mode=ParseMode.HTML,
                        reply_markup=keyboard,
                    )
                    logger.info(f"Watchlist photo alert sent for {name}")
                    return True
                except Exception as photo_err:
                    logger.warning(f"Failed to send photo for watchlist ({photo_err}), sending text.")

            await self._bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
                disable_web_page_preview=False,
            )
            logger.info(f"Watchlist text alert sent for {name}")
            return True
        except Exception as e:
            logger.error(f"Error sending watchlist alert: {e}")
            return False

    async def send_system_message(self, text: str) -> bool:
        """Sends an informational message to the configured chat."""
        if not self.is_configured:
            return False
        try:
            await self._bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode=ParseMode.HTML,
            )
            return True
        except Exception as e:
            logger.error(f"Error sending system message: {e}")
            return False
