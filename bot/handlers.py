import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from tracker.scraper import BlinkitScraper

logger = logging.getLogger(__name__)

class BotHandlers:
    def __init__(self, poller, database, config):
        self.poller = poller
        self.db = database
        self.config = config

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler for /start command."""
        user = update.effective_user
        chat_id = update.effective_chat.id
        msg = (
            f"👋 Hello {user.first_name or 'Collector'}!\n\n"
            f"🏎️ <b>Welcome to Blinkit Hot Wheels Restock Sniper!</b>\n\n"
            f"I continuously monitor your local Blinkit dark store and instantly send "
            f"you notifications with direct buy links when Hot Wheels are restocked.\n\n"
            f"📍 <b>Current Target Location:</b>\n"
            f"• PIN Code: <code>{self.config.TARGET_PINCODE}</code>\n"
            f"• Locality: <code>{self.config.TARGET_LOCALITY}</code>\n"
            f"• Scan Interval: <code>{self.config.CHECK_INTERVAL_SECONDS}s</code>\n"
            f"• Your Chat ID: <code>{chat_id}</code>\n\n"
            f"<b>🎯 Specific Product Alerts:</b>\n"
            f"• <code>/track &lt;url&gt;</code> - Track a specific Hot Wheels car by Blinkit URL\n"
            f"• <code>/untrack &lt;id/url&gt;</code> - Stop tracking a specific car\n"
            f"• <code>/watchlist</code> - View all specific cars on your watchlist\n\n"
            f"<b>🔍 General Commands:</b>\n"
            f"• <code>/check</code> - Run an instant stock check right now\n"
            f"• <code>/items</code> - List all currently in-stock Hot Wheels\n"
            f"• <code>/status</code> - View bot health, stats, and last scan time\n"
            f"• <code>/setinterval &lt;seconds&gt;</code> - Change scan frequency (min 10s)\n"
            f"• <code>/help</code> - View this help guide\n\n"
            f"🔥 <i>Stay tuned for instant restock alerts!</i>"
        )
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

    async def track_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler for /track <url> or /add <url> command."""
        if not context.args:
            await update.message.reply_text(
                "🎯 <b>How to track a specific Hot Wheels car:</b>\n\n"
                "Send: <code>/track &lt;Blinkit URL or Product ID&gt;</code>\n\n"
                "<b>Example:</b>\n"
                "<code>/track https://blinkit.com/prn/hot-wheels-die-cast-car/prid/601140</code>\n"
                "or simply: <code>/track 601140</code>",
                parse_mode=ParseMode.HTML
            )
            return

        input_url = context.args[0].strip()
        status_msg = await update.message.reply_text(
            f"🔍 <i>Checking product on Blinkit...</i>",
            parse_mode=ParseMode.HTML
        )

        try:
            pid = BlinkitScraper.extract_product_id_from_url(input_url)
            item = await self.poller.check_specific_url(input_url)

            if not item:
                await status_msg.edit_text(
                    f"⚠️ <b>Could not fetch product details</b> for: <code>{input_url}</code>\n"
                    f"Please verify that this is a valid Blinkit product link.",
                    parse_mode=ParseMode.HTML
                )
                return

            prod_id = item.get("product_id") or pid or input_url
            name = item.get("name", "Hot Wheels Car")
            price = item.get("price", "N/A")
            in_stock = item.get("in_stock", False)
            image_url = item.get("image_url", "")
            prod_url = item.get("product_url", input_url)

            # Save to watchlist
            self.db.add_to_watchlist(
                product_id=prod_id,
                url=prod_url,
                name=name,
                price=price,
                in_stock=in_stock,
                image_url=image_url
            )

            stock_emoji = "🟢 <b>IN STOCK</b>" if in_stock else "🔴 <b>OUT OF STOCK</b>"
            reply_text = (
                f"✅ <b>Added to Watchlist!</b>\n\n"
                f"🏎️ <b>Product:</b> {name}\n"
                f"🆔 <b>ID:</b> <code>{prod_id}</code>\n"
                f"💰 <b>Price:</b> <b>{price}</b>\n"
                f"📦 <b>Current Status:</b> {stock_emoji}\n\n"
                f"🔔 <i>I will send you an instant high-priority alert with a direct buy button the exact second this car restocks!</i>"
            )

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("⚡ View on Blinkit", url=prod_url)]
            ])

            if image_url and image_url.startswith("http"):
                try:
                    await status_msg.delete()
                    await update.message.reply_photo(
                        photo=image_url,
                        caption=reply_text,
                        parse_mode=ParseMode.HTML,
                        reply_markup=keyboard
                    )
                    return
                except Exception:
                    pass

            await status_msg.edit_text(reply_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)

        except Exception as e:
            logger.error(f"Error tracking product: {e}")
            await status_msg.edit_text(f"⚠️ Error tracking product: {str(e)[:150]}", parse_mode=ParseMode.HTML)

    async def untrack_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler for /untrack <id/url> command."""
        if not context.args:
            await update.message.reply_text(
                "Usage: <code>/untrack &lt;Product ID or URL&gt;</code>\n"
                "Example: <code>/untrack 601140</code>",
                parse_mode=ParseMode.HTML
            )
            return

        term = context.args[0].strip()
        removed = self.db.remove_from_watchlist(term)
        if removed:
            await update.message.reply_text(f"🗑️ Successfully removed <code>{term}</code> from your watchlist.", parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(f"⚠️ Item <code>{term}</code> was not found in your watchlist.", parse_mode=ParseMode.HTML)

    async def watchlist_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler for /watchlist command - show all specifically tracked items."""
        watchlist = self.db.get_watchlist()
        if not watchlist:
            await update.message.reply_text(
                "📋 <b>Your watchlist is currently empty.</b>\n\n"
                "You can track specific Hot Wheels by sending:\n"
                "<code>/track &lt;Blinkit Product URL&gt;</code>",
                parse_mode=ParseMode.HTML
            )
            return

        text = f"🎯 <b>Your Hot Wheels Watchlist ({len(watchlist)} cars):</b>\n\n"
        buttons = []
        for i, item in enumerate(watchlist, 1):
            status = "🟢 In Stock" if item.get("in_stock") else "🔴 Out of Stock"
            name = item.get("name") or f"Item #{item.get('product_id')}"
            price = item.get("price", "N/A")
            text += f"<b>{i}. {name}</b>\n"
            text += f"   • Status: <b>{status}</b> | Price: {price}\n"
            text += f"   • ID: <code>{item.get('product_id')}</code>\n\n"

            if item.get("url"):
                buttons.append([InlineKeyboardButton(f"⚡ Buy #{i}: {name[:25]}", url=item["url"])])

        text += "💡 <i>To remove an item, send: /untrack &lt;ID&gt;</i>"
        reply_markup = InlineKeyboardMarkup(buttons) if buttons else None
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup, disable_web_page_preview=True)

    async def check_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler for /check command - immediate scan."""
        status_msg = await update.message.reply_text("🔍 <i>Scanning Blinkit dark store right now...</i>", parse_mode=ParseMode.HTML)
        try:
            items = await self.poller.trigger_manual_check()
            if not items:
                await status_msg.edit_text(
                    f"❌ <b>No Hot Wheels items found</b> in your dark store ({self.config.TARGET_PINCODE}).\n"
                    f"They might not be listed yet, or the warehouse has zero inventory.\n"
                    f"I will keep monitoring in the background!",
                    parse_mode=ParseMode.HTML
                )
                return

            in_stock = [item for item in items if item.get("in_stock")]
            out_of_stock = [item for item in items if not item.get("in_stock")]

            text = f"🏁 <b>Blinkit Hot Wheels Scan Results:</b>\n"
            text += f"📍 Locality: {self.config.TARGET_LOCALITY} ({self.config.TARGET_PINCODE})\n\n"

            if in_stock:
                text += f"🟢 <b>IN STOCK ({len(in_stock)}):</b>\n"
                for i, it in enumerate(in_stock[:10], 1):
                    price = it.get('price', 'N/A')
                    text += f"  {i}. <a href='{it.get('product_url')}'>{it.get('name')}</a> - <b>{price}</b>\n"
            else:
                text += "🔴 <b>Currently Out of Stock</b> (0 available).\n"

            if out_of_stock:
                text += f"\n⚪ <b>Catalogued but Out of Stock ({len(out_of_stock)}):</b>\n"
                for i, it in enumerate(out_of_stock[:5], 1):
                    text += f"  • {it.get('name')}\n"

            text += f"\n⚡ <i>Total tracked in catalog: {len(items)} items</i>"

            keyboard = None
            if in_stock:
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("⚡ Buy First In-Stock", url=in_stock[0].get("product_url", "https://blinkit.com/s/?q=hot+wheels"))]
                ])

            await status_msg.edit_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=keyboard)

        except Exception as e:
            logger.error(f"Error during manual check: {e}")
            await status_msg.edit_text(f"⚠️ Error scanning Blinkit: {str(e)[:150]}", parse_mode=ParseMode.HTML)

    async def items_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler for /items command - list currently in-stock items."""
        in_stock_items = self.db.get_in_stock_products()
        if not in_stock_items:
            await update.message.reply_text(
                "🔴 <b>No Hot Wheels are currently marked in stock</b> in your local database.\n"
                "Use /check to run a live scan now.",
                parse_mode=ParseMode.HTML
            )
            return

        text = f"🟢 <b>Currently In-Stock Hot Wheels ({len(in_stock_items)}):</b>\n\n"
        buttons = []
        for i, item in enumerate(in_stock_items[:8], 1):
            text += f"<b>{i}. {item['name']}</b>\n"
            text += f"   💰 Price: <b>{item['price']}</b>\n\n"
            if item.get("product_url"):
                buttons.append([InlineKeyboardButton(f"⚡ Buy #{i}: {item['name'][:25]}...", url=item["product_url"])])

        reply_markup = InlineKeyboardMarkup(buttons) if buttons else None
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler for /status command."""
        stats = self.db.get_stats()
        last_check = self.poller.last_check_time
        last_check_str = last_check.strftime("%H:%M:%S") if last_check else "Never"

        status_text = (
            f"📊 <b>Blinkit Sniper Bot Status</b>\n\n"
            f"• <b>Status:</b> {'🟢 Running' if self.poller.is_running else '🔴 Stopped'}\n"
            f"• <b>Target Locality:</b> {self.config.TARGET_LOCALITY}\n"
            f"• <b>Target PIN:</b> {self.config.TARGET_PINCODE}\n"
            f"• <b>Coordinates:</b> {self.config.TARGET_LAT}, {self.config.TARGET_LON}\n"
            f"• <b>Scan Interval:</b> {self.config.CHECK_INTERVAL_SECONDS} seconds\n"
            f"• <b>Last Check:</b> {last_check_str}\n"
            f"• <b>Specific Watchlist Items:</b> {stats.get('watchlist_count', 0)}\n"
            f"• <b>Total Catalog Items Tracked:</b> {stats['total_tracked']}\n"
            f"• <b>Currently In Stock:</b> {stats['currently_in_stock']}\n"
            f"• <b>Total Restock Alerts Fired:</b> {stats['total_restock_alerts']}\n"
        )
        await update.message.reply_text(status_text, parse_mode=ParseMode.HTML)

    async def setinterval_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler for /setinterval command."""
        if not context.args:
            await update.message.reply_text(
                f"Usage: <code>/setinterval &lt;seconds&gt;</code>\n"
                f"Current interval: <b>{self.config.CHECK_INTERVAL_SECONDS}s</b> (Minimum: {self.config.MIN_INTERVAL_SECONDS}s)",
                parse_mode=ParseMode.HTML
            )
            return

        try:
            val = int(context.args[0])
            if val < self.config.MIN_INTERVAL_SECONDS:
                await update.message.reply_text(f"⚠️ Minimum interval is {self.config.MIN_INTERVAL_SECONDS} seconds to avoid IP rate limits.")
                return
            self.config.CHECK_INTERVAL_SECONDS = val
            await update.message.reply_text(f"✅ Scan interval updated to <b>{val} seconds</b>.", parse_mode=ParseMode.HTML)
        except ValueError:
            await update.message.reply_text("⚠️ Please enter a valid number of seconds.")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler for /help command."""
        await self.start_command(update, context)
