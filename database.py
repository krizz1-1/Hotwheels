import sqlite3
import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

class StockDatabase:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.init_db()

    def _get_connection(self):
        # GitHub-hosted runners start from a clean checkout. Ensure the
        # database's parent directory exists before SQLite opens the file.
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        """Create tables if they don't exist."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    product_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    price TEXT,
                    mrp TEXT,
                    in_stock INTEGER NOT NULL,
                    product_url TEXT,
                    image_url TEXT,
                    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_restocked TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS stock_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    details TEXT
                )
            """)
            # Watchlist for specific Hot Wheels URLs / Product IDs
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS watchlist (
                    product_id TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    name TEXT,
                    price TEXT,
                    in_stock INTEGER DEFAULT 0,
                    image_url TEXT,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_checked TIMESTAMP
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def process_product(self, item: Dict[str, Any]) -> Optional[str]:
        """
        Processes a scanned item and detects state changes.
        Returns:
            'RESTOCK': if item was previously out-of-stock and is now in stock.
            'NEW_DISCOVERY': if item was newly found and is in stock.
            None: if stock status has not changed or went out of stock.
        """
        pid = str(item.get("product_id", "")).strip()
        if not pid:
            return None

        name = item.get("name", "Hot Wheels Car")
        price = item.get("price", "N/A")
        mrp = item.get("mrp", "")
        in_stock = 1 if item.get("in_stock", False) else 0
        product_url = item.get("product_url", "")
        image_url = item.get("image_url", "")
        now = datetime.datetime.now().isoformat()

        event = None

        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT in_stock, price FROM products WHERE product_id = ?", (pid,))
            row = cursor.fetchone()

            if row is None:
                # Newly discovered product
                cursor.execute("""
                    INSERT INTO products (product_id, name, price, mrp, in_stock, product_url, image_url, first_seen, last_seen, last_restocked)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (pid, name, price, mrp, in_stock, product_url, image_url, now, now, now if in_stock else None))

                if in_stock:
                    event = "NEW_DISCOVERY"
                    cursor.execute("""
                        INSERT INTO stock_events (product_id, event_type, details)
                        VALUES (?, ?, ?)
                    """, (pid, event, f"Discovered in stock: {name} at {price}"))
            else:
                prev_in_stock = row["in_stock"]
                # Stock transition: 0 -> 1 (Restock detected!)
                if prev_in_stock == 0 and in_stock == 1:
                    event = "RESTOCK"
                    cursor.execute("""
                        INSERT INTO stock_events (product_id, event_type, details)
                        VALUES (?, ?, ?)
                    """, (pid, event, f"Restocked: {name} at {price}"))
                    cursor.execute("""
                        UPDATE products
                        SET name = ?, price = ?, mrp = ?, in_stock = ?, product_url = ?, image_url = ?, last_seen = ?, last_restocked = ?
                        WHERE product_id = ?
                    """, (name, price, mrp, in_stock, product_url, image_url, now, now, pid))
                else:
                    cursor.execute("""
                        UPDATE products
                        SET name = ?, price = ?, mrp = ?, in_stock = ?, product_url = ?, image_url = ?, last_seen = ?
                        WHERE product_id = ?
                    """, (name, price, mrp, in_stock, product_url, image_url, now, pid))

            conn.commit()
        finally:
            conn.close()

        return event

    def get_all_products(self) -> List[Dict[str, Any]]:
        """Fetch all tracked products."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM products ORDER BY in_stock DESC, last_seen DESC")
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_in_stock_products(self) -> List[Dict[str, Any]]:
        """Fetch currently in-stock products."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM products WHERE in_stock = 1 ORDER BY last_restocked DESC")
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    # ================================================================
    # Watchlist Management (Specific Hot Wheels by URL / Product ID)
    # ================================================================

    def add_to_watchlist(self, product_id: str, url: str, name: str, price: str, in_stock: bool, image_url: str = "") -> bool:
        """Adds or updates a specific Hot Wheels product in the watchlist."""
        pid = str(product_id).strip()
        now = datetime.datetime.now().isoformat()
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO watchlist (product_id, url, name, price, in_stock, image_url, added_at, last_checked)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(product_id) DO UPDATE SET
                    url = excluded.url,
                    name = excluded.name,
                    price = excluded.price,
                    in_stock = excluded.in_stock,
                    image_url = excluded.image_url,
                    last_checked = excluded.last_checked
            """, (pid, url, name, price, 1 if in_stock else 0, image_url, now, now))
            conn.commit()
            return True
        finally:
            conn.close()

    def remove_from_watchlist(self, product_id_or_url: str) -> bool:
        """Removes a product from the watchlist by product_id or URL."""
        term = str(product_id_or_url).strip()
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM watchlist WHERE product_id = ? OR url = ? OR url LIKE ?
            """, (term, term, f"%{term}%"))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def get_watchlist(self) -> List[Dict[str, Any]]:
        """Returns all items currently in the watchlist."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM watchlist ORDER BY in_stock DESC, added_at DESC")
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_watchlist_item(self, product_id: str) -> Optional[Dict[str, Any]]:
        """Get a single watchlist item by product_id."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM watchlist WHERE product_id = ?", (str(product_id).strip(),))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def update_watchlist_item(self, product_id: str, in_stock: bool, price: str = "", name: str = "", image_url: str = "") -> Optional[str]:
        """
        Updates watchlist item stock status.
        Returns 'WATCHLIST_RESTOCK' if status transitioned from 0 -> 1.
        """
        pid = str(product_id).strip()
        now = datetime.datetime.now().isoformat()
        stock_int = 1 if in_stock else 0
        event = None

        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT in_stock, name FROM watchlist WHERE product_id = ?", (pid,))
            row = cursor.fetchone()
            if row is not None:
                prev_stock = row["in_stock"]
                item_name = name or row["name"]
                if prev_stock == 0 and stock_int == 1:
                    event = "WATCHLIST_RESTOCK"
                    cursor.execute("""
                        INSERT INTO stock_events (product_id, event_type, details)
                        VALUES (?, ?, ?)
                    """, (pid, event, f"Watchlist restock: {item_name} at {price}"))

                cursor.execute("""
                    UPDATE watchlist
                    SET in_stock = ?,
                        price = CASE WHEN ? != '' THEN ? ELSE price END,
                        name = CASE WHEN ? != '' THEN ? ELSE name END,
                        image_url = CASE WHEN ? != '' THEN ? ELSE image_url END,
                        last_checked = ?
                    WHERE product_id = ?
                """, (stock_int, price, price, name, name, image_url, image_url, now, pid))
                conn.commit()
        finally:
            conn.close()

        return event

    def get_stats(self) -> Dict[str, Any]:
        """Get summary statistics."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as total FROM products")
            total = cursor.fetchone()["total"]
            cursor.execute("SELECT COUNT(*) as in_stock FROM products WHERE in_stock = 1")
            in_stock = cursor.fetchone()["in_stock"]
            cursor.execute("SELECT COUNT(*) as events FROM stock_events WHERE event_type IN ('RESTOCK', 'NEW_DISCOVERY', 'WATCHLIST_RESTOCK')")
            restocks = cursor.fetchone()["events"]
            cursor.execute("SELECT COUNT(*) as watch_total FROM watchlist")
            watchlist_count = cursor.fetchone()["watch_total"]
            return {
                "total_tracked": total,
                "currently_in_stock": in_stock,
                "total_restock_alerts": restocks,
                "watchlist_count": watchlist_count,
            }
        finally:
            conn.close()
