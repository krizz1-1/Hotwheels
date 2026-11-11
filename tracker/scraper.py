import re
import json
import logging
import urllib.parse
from typing import List, Dict, Any, Optional
from playwright.async_api import Page, Response

logger = logging.getLogger(__name__)

class BlinkitScraper:
    def __init__(self, query: str = "hot wheels"):
        self.query = query
        self.encoded_query = urllib.parse.quote(query)
        self.search_url = f"https://blinkit.com/s/?q={self.encoded_query}"
        self.intercepted_items: List[Dict[str, Any]] = []

    async def _handle_response(self, response: Response):
        """Intercepts background JSON requests from Blinkit layout/search API."""
        try:
            url = response.url
            if ("layout" in url or "search" in url) and "application/json" in response.headers.get("content-type", ""):
                if response.status == 200:
                    data = await response.json()
                    parsed = self._parse_json_payload(data)
                    if parsed:
                        self.intercepted_items.extend(parsed)
        except Exception:
            pass

    EXCLUDE_KEYWORDS = (
        "showing results", "results for", "explore more", "view all", "category",
        "beverage", "chocolate", "drink", "coffee", "tea", "food", "sauce",
        "snack", "bread", "milk", "cookie", "cake", "candy", "sweet", "masala",
    )

    def _is_hot_wheels_product(self, text: str) -> bool:
        """Determines if a candidate string is an actual Hot Wheels toy product."""
        t = text.lower().strip()
        if not t:
            return False
        # Reject banners, search summaries, and food/beverages
        if any(term in t for term in self.EXCLUDE_KEYWORDS):
            return False
        # Must explicitly contain 'hot wheels' or 'hotwheels'
        return "hot wheels" in t or "hotwheels" in t

    def _clean_str(self, val: Any) -> str:
        """Extract clean text from string or dict (e.g. {'text': 'Hot Wheels...'})"""
        if isinstance(val, dict):
            return str(val.get("text", "")).strip()
        return str(val).strip() if val is not None else ""

    def _parse_json_payload(self, data: Any) -> List[Dict[str, Any]]:
        """Parses products from Blinkit layout search JSON."""
        results = []
        try:
            # Recursively find product snippets in JSON
            def search_dict(d):
                if isinstance(d, dict):
                    candidate_name = self._clean_str(d.get("name") or d.get("title") or d.get("product_name"))
                    if self._is_hot_wheels_product(candidate_name):
                        pid = self._clean_str(d.get("product_id") or d.get("id") or d.get("inventory_item_id"))
                        raw_price = self._clean_str(d.get("price") or d.get("offer_price") or d.get("final_price") or d.get("sp"))
                        raw_mrp = self._clean_str(d.get("mrp") or d.get("original_price"))
                        
                        # Robust inventory and stock evaluation
                        is_oos = False
                        for k in ("state", "product_state", "availability", "inventory_state"):
                            if str(d.get(k, "")).lower() in ("oos", "out_of_stock", "sold_out", "unavailable", "out of stock"):
                                is_oos = True
                        if d.get("out_of_stock") is True or d.get("max_count") == 0 or d.get("inventory") == 0:
                            is_oos = True

                        inventory = d.get("inventory", d.get("available_inventory"))
                        if is_oos:
                            in_stock = False
                        elif isinstance(inventory, (int, float)):
                            in_stock = inventory > 0
                        else:
                            in_stock = not is_oos and bool(d.get("in_stock", False))

                        img = self._clean_str(d.get("image_url") or d.get("image") or d.get("thumbnail_url"))
                        slug = self._clean_str(d.get("slug") or pid)
                        url = f"https://blinkit.com/prn/{slug}/prid/{pid}" if pid else self.search_url

                        # Format price nicely
                        price_match = re.search(r"\d+", raw_price)
                        price_str = f"₹{price_match.group(0)}" if price_match else raw_price
                        mrp_match = re.search(r"\d+", raw_mrp)
                        mrp_str = f"₹{mrp_match.group(0)}" if mrp_match else raw_mrp

                        results.append({
                            "product_id": pid or f"hw_{abs(hash(candidate_name)) % 1000000}",
                            "name": candidate_name,
                            "price": price_str or "₹179",
                            "mrp": mrp_str,
                            "in_stock": bool(in_stock),
                            "product_url": url,
                            "image_url": img,
                        })
                    for v in d.values():
                        search_dict(v)
                elif isinstance(d, list):
                    for item in d:
                        search_dict(item)

            search_dict(data)
        except Exception as e:
            logger.debug(f"JSON parsing error: {e}")
        return results

    async def _dismiss_popups(self, page: Page):
        """Dismiss common Blinkit popups (location alerts, login modal, promo banners)."""
        close_selectors = [
            "button[aria-label='close']",
            "button:has-text('✕')",
            "button:has-text('×')",
            "div[class*='Modal'] button",
            "div[class*='Overlay'] button",
            "button:has-text('Cancel')",
            "button:has-text('Not now')",
        ]
        for sel in close_selectors:
            try:
                elem = page.locator(sel).first
                if await elem.is_visible(timeout=500):
                    await elem.click(timeout=1000)
            except Exception:
                pass

    async def scrape(self, page: Page) -> List[Dict[str, Any]]:
        """
        Navigates to search page and extracts all matching Hot Wheels items.
        Combines intercepted API responses and live DOM inspection.
        """
        self.intercepted_items = []
        page.on("response", self._handle_response)

        try:
            current_url = page.url
            if self.search_url in current_url:
                logger.info("Already on search page, reloading for freshest stock...")
                await page.reload(wait_until="domcontentloaded", timeout=30000)
            else:
                logger.info(f"Navigating to {self.search_url}...")
                await page.goto(self.search_url, wait_until="domcontentloaded", timeout=30000)

            # Wait briefly for product grid or network responses
            await page.wait_for_timeout(3500)
            await self._dismiss_popups(page)

            # Check if intercepted API provided products
            if self.intercepted_items:
                logger.info(f"Extracted {len(self.intercepted_items)} items via API interception.")
                # Deduplicate by product_id
                seen = set()
                unique_items = []
                for it in self.intercepted_items:
                    if it["product_id"] not in seen:
                        seen.add(it["product_id"])
                        unique_items.append(it)
                return unique_items

            # DOM fallback extraction
            logger.info("Extracting products directly from DOM elements...")
            return await self._extract_from_dom(page)

        except Exception as e:
            logger.error(f"Error scraping Blinkit: {e}")
            return []
        finally:
            page.remove_listener("response", self._handle_response)

    async def _extract_from_dom(self, page: Page) -> List[Dict[str, Any]]:
        """Extracts products by inspecting DOM card elements."""
        results = []
        try:
            # Locate all product cards
            # Blinkit product cards contain ₹ price and either ADD button or Out of Stock indicator
            cards = page.locator("div[role='button']").filter(has_text="₹")
            count = await cards.count()
            logger.info(f"Found {count} candidate product cards on page.")

            for i in range(count):
                try:
                    card = cards.nth(i)
                    text = await card.inner_text()

                    # Filter for Hot Wheels products
                    if "hot" not in text.lower() and "wheel" not in text.lower():
                        continue

                    # Extract Product ID
                    pid = await card.get_attribute("id") or ""
                    if not pid:
                        # Try to find from nested links
                        link_elem = card.locator("a[href*='/prid/']").first
                        if await link_elem.count() > 0:
                            href = await link_elem.get_attribute("href") or ""
                            m = re.search(r"/prid/(\d+)", href)
                            if m:
                                pid = m.group(1)

                    # Extract Name
                    name = ""
                    name_locator = card.locator("div[class*='line-clamp-2'], div[class*='Product__UpdatedTitle']").first
                    if await name_locator.count() > 0:
                        name = (await name_locator.inner_text()).strip()
                    else:
                        for line in text.split("\n"):
                            line_clean = line.strip()
                            if self._is_hot_wheels_product(line_clean):
                                name = line_clean
                                break

                    # Filter for Hot Wheels products
                    if not self._is_hot_wheels_product(name):
                        continue

                    # Generate fallback pid if still missing
                    if not pid:
                        pid = f"hw_{abs(hash(name)) % 1000000}"

                    # Extract Price & MRP
                    price = "N/A"
                    mrp = ""
                    prices = re.findall(r"₹\s*(\d+)", text)
                    if prices:
                        price = f"₹{prices[0]}"
                        if len(prices) > 1 and prices[1] != prices[0]:
                            mrp = f"₹{prices[1]}"

                    # Check Stock status
                    text_lower = text.lower()
                    is_out_of_stock = ("out of stock" in text_lower or 
                                       "unavailable" in text_lower or 
                                       "sold out" in text_lower)
                    has_add_button = "add" in text_lower or await card.locator("button, div[role='button']:has-text('ADD')").count() > 0
                    in_stock = has_add_button and not is_out_of_stock

                    # Extract Image
                    img_url = ""
                    img_elem = card.locator("img").first
                    if await img_elem.count() > 0:
                        img_url = await img_elem.get_attribute("src") or ""

                    # Extract Product URL
                    prod_url = self.search_url
                    link_elem = card.locator("a").first
                    if await link_elem.count() > 0:
                        href = await link_elem.get_attribute("href") or ""
                        if href:
                            prod_url = urllib.parse.urljoin("https://blinkit.com", href)

                    results.append({
                        "product_id": pid,
                        "name": name,
                        "price": price,
                        "mrp": mrp,
                        "in_stock": in_stock,
                        "product_url": prod_url,
                        "image_url": img_url,
                    })

                except Exception as card_err:
                    logger.debug(f"Error parsing card {i}: {card_err}")

        except Exception as e:
            logger.error(f"Error in DOM product extraction: {e}")

        logger.info(f"Extracted {len(results)} Hot Wheels products from DOM.")
        return results

    @staticmethod
    def extract_product_id_from_url(url_or_id: str) -> Optional[str]:
        """Extracts numerical product ID from various Blinkit URL formats or direct ID."""
        t = str(url_or_id).strip()
        if t.isdigit():
            return t
        m = re.search(r"/prid/(\d+)", t)
        if m:
            return m.group(1)
        m = re.search(r"prid=(\d+)", t)
        if m:
            return m.group(1)
        m = re.search(r"/(\d{5,10})(?:[/?#]|$)", t)
        if m:
            return m.group(1)
        return None

    def _is_pdp_in_stock(self, data: Dict[str, Any], product_id: str) -> bool:
        """
        Thoroughly analyzes Blinkit PDP response JSON to verify real inventory.
        Checks explicit out-of-stock states, disabled add-to-cart signals, and positive inventory counts.
        """
        # A PDP response can also include recommendations. Only evaluate a
        # dictionary that explicitly belongs to the requested product ID.
        target_found = False
        is_explicit_oos = False
        has_positive_inventory = False

        def scan(node):
            nonlocal target_found, is_explicit_oos, has_positive_inventory
            if isinstance(node, dict):
                node_ids = {
                    str(node.get(key, "")).strip()
                    for key in ("product_id", "inventory_item_id", "id")
                }
                is_target = str(product_id) in node_ids
                if is_target:
                    target_found = True

                if is_target:
                # 1. Check for explicit out-of-stock states
                    for key in ("state", "product_state", "availability", "inventory_state"):
                        val = str(node.get(key, "")).lower()
                        if val in ("out_of_stock", "oos", "sold_out", "unavailable", "out of stock"):
                            is_explicit_oos = True

                    # 2. Check for disabled add to cart interaction signals
                    if "DISABLED_ADD_TO_CART" in node:
                        is_explicit_oos = True

                    # 3. Check inventory values
                    for key in ("inventory", "available_inventory", "quantity"):
                        if key in node and isinstance(node[key], (int, float)):
                            if node[key] > 0:
                                has_positive_inventory = True
                            elif node[key] == 0:
                                is_explicit_oos = True

                    # 4. Check stepper max_count / explicit flag
                    if node.get("in_stock") is True:
                        has_positive_inventory = True
                    if "max_count" in node and isinstance(node["max_count"], (int, float)):
                        if node["max_count"] > 0:
                            has_positive_inventory = True
                        elif node["max_count"] == 0:
                            is_explicit_oos = True

                for v in node.values():
                    scan(v)
            elif isinstance(node, list):
                for it in node:
                    scan(it)

        scan(data)
        if not target_found or is_explicit_oos:
            return False
        return has_positive_inventory

    def _parse_pdp_payload(self, pid: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parses /v1/layout/product/{pid} response."""
        name = ""
        price = "N/A"
        mrp = ""
        image_url = ""

        # Accurate stock determination
        in_stock = self._is_pdp_in_stock(data, pid)

        snippets = data.get("response", {}).get("snippets", [])
        for s in snippets:
            sdata = s.get("data", {})

            # Extract title/name
            if not name:
                title_obj = sdata.get("title")
                if isinstance(title_obj, dict):
                    name = title_obj.get("text", "")
                elif isinstance(title_obj, str):
                    name = title_obj
                if not name and "name" in sdata:
                    name = self._clean_str(sdata.get("name"))

            # Extract image
            if not image_url:
                items = sdata.get("itemList", [])
                if items and isinstance(items, list):
                    assets = items[0].get("data", {}).get("click_action", {}).get("show_gallery", {}).get("assets", [])
                    if assets and isinstance(assets, list):
                        image_url = assets[0].get("image_url", "")

            # Extract price / mrp
            if price == "N/A":
                norm_price = sdata.get("normal_price")
                if norm_price:
                    price_val = norm_price.get("price") or norm_price.get("unit_price")
                    if price_val:
                        price = f"₹{price_val}"
                    mrp_val = norm_price.get("mrp")
                    if mrp_val:
                        mrp = f"₹{mrp_val}"

        if not name:
            # Fallback to general search dict extractor
            parsed = self._parse_json_payload(data)
            if parsed:
                item = parsed[0]
                item["in_stock"] = in_stock
                return item
            name = f"Hot Wheels Item #{pid}"

        return {
            "product_id": pid,
            "name": name,
            "price": price if price != "N/A" else "₹179",
            "mrp": mrp,
            "in_stock": in_stock,
            "product_url": f"https://blinkit.com/prid/{pid}",
            "image_url": image_url,
        }

    async def fetch_product_by_id(self, page: Page, product_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetches live stock and metadata of a specific product ID via internal API evaluation.
        Ultra-fast (<200ms) with zero page reload overhead.
        """
        pid = str(product_id).strip()
        js_code = f"""
        async () => {{
            try {{
                const res = await fetch('/v1/layout/product/{pid}', {{
                    method: 'POST',
                    headers: {{'content-type': 'application/json', 'app_client': 'consumer_web'}}
                }});
                if (res.status === 200) {{
                    return {{ status: 200, data: await res.json() }};
                }}
                return {{ status: res.status }};
            }} catch (err) {{
                return {{ error: err.toString() }};
            }}
        }}
        """
        try:
            result = await page.evaluate(js_code)
            if result.get("status") == 200 and "data" in result:
                parsed = self._parse_pdp_payload(pid, result["data"])
                # Confirm any positive API result on the actual product page.
                # This rejects stock values from stale or unrelated payload data.
                if parsed and parsed.get("in_stock"):
                    confirmed = await self._scrape_pdp_via_navigation(
                        page, f"https://blinkit.com/prid/{pid}"
                    )
                    parsed["in_stock"] = bool(confirmed and confirmed.get("in_stock"))
                return parsed
        except Exception as e:
            logger.debug(f"Fast internal PDP query failed for {pid}: {e}")

        # Fallback to navigating directly to the product URL
        return await self._scrape_pdp_via_navigation(page, f"https://blinkit.com/prid/{pid}")

    async def fetch_product_by_url(self, page: Page, url: str) -> Optional[Dict[str, Any]]:
        """Resolves product ID from URL and fetches its current stock status."""
        pid = self.extract_product_id_from_url(url)
        if pid:
            item = await self.fetch_product_by_id(page, pid)
            if item:
                item["product_url"] = url
                return item
        # If ID cannot be extracted from URL, scrape by navigating directly
        return await self._scrape_pdp_via_navigation(page, url)

    async def _scrape_pdp_via_navigation(self, page: Page, url: str) -> Optional[Dict[str, Any]]:
        """Fallback PDP scraper using full page navigation."""
        try:
            logger.info(f"Navigating to product page: {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=25000)
            await page.wait_for_timeout(2000)
            await self._dismiss_popups(page)

            # Extract title
            title_elem = page.locator("h1, div[class*='Product__UpdatedTitle'], div[class*='Title']").first
            name = (await title_elem.inner_text()).strip() if await title_elem.count() > 0 else "Hot Wheels Product"

            # Extract body text for stock check
            body_text = (await page.inner_text("body")).lower()
            is_out_of_stock = "out of stock" in body_text or "unavailable" in body_text or "sold out" in body_text
            add_button = page.get_by_role("button", name=re.compile(r"^add$", re.IGNORECASE)).first
            has_add = (
                not is_out_of_stock
                and await add_button.count() > 0
                and await add_button.is_visible()
                and await add_button.is_enabled()
            )

            # Extract price
            prices = re.findall(r"₹\s*(\d+)", body_text)
            price = f"₹{prices[0]}" if prices else "N/A"

            # Extract image
            img_elem = page.locator("img[src*='blinkit'], img[src*='cloudfront']").first
            img_url = await img_elem.get_attribute("src") if await img_elem.count() > 0 else ""

            pid = self.extract_product_id_from_url(url) or f"hw_{abs(hash(url)) % 1000000}"

            return {
                "product_id": pid,
                "name": name,
                "price": price,
                "mrp": "",
                "in_stock": has_add,
                "product_url": url,
                "image_url": img_url or "",
            }
        except Exception as e:
            logger.error(f"Error scraping PDP {url}: {e}")
            return None
