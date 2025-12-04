#!/usr/bin/env python3
"""
btc_eth_bark_notifier.py
当 BTC 到达新的整数千位 (n*1 000 USD)、
或 ETH 到达新的整数百位 (n*100 USD)、
或 BTC/ETH 比率到达新的 0.5 倍数档位时，
或 BTC/ETH 比率达到24h/72h/144h新高/新低时，
立刻通过 Bark 推送到 iPhone。

依赖：
    pip install requests
环境变量（也可以直接写在脚本里）：
    BARK_KEY   —— 必填，Bark Device Key
    BARK_BASE  —— 选填，Bark 服务器根地址，默认 https://api.day.app
可调参数：
    BTC_STEP      —— BTC 步长（默认 1000）
    ETH_STEP      —— ETH 步长（默认 100）
    RATIO_STEP    —— BTC/ETH 比率步长（默认 0.5）
    INTERVAL      —— 轮询间隔（秒）
    DB_PATH       —— SQLite数据库路径（默认 ratio_history.db）
                     用于持久化BTC/ETH价格和比率历史数据，重启后不丢失
"""
import os
import sys
import time
import sqlite3
import requests
from urllib.parse import quote
from datetime import datetime, timedelta

# ==== 配置（可用环境变量覆盖） ====
BARK_KEY   = os.getenv("BARK_KEY",  "YOUR_DEVICE_KEY")
BARK_BASE  = os.getenv("BARK_BASE", "https://api.day.app")
BTC_STEP   = int(os.getenv("BTC_STEP",  1000))   # BTC 整数档位步长
ETH_STEP   = int(os.getenv("ETH_STEP",   100))   # ETH 整数档位步长
RATIO_STEP = float(os.getenv("RATIO_STEP", 0.5)) # BTC/ETH 比率步长
INTERVAL   = int(os.getenv("INTERVAL",    30))   # 秒
DB_PATH    = os.getenv("DB_PATH", "ratio_history.db")  # SQLite 数据库路径

COINGECKO_URL = (
    "https://api.coingecko.com/api/v3/simple/price"
    "?ids=bitcoin,ethereum&vs_currencies=usd"
)

# ==== 推送 ====
def bark_push(title: str, body: str):
    # URL-encode title and body to handle special characters like "/"
    # Use safe='' to encode ALL characters including "/"
    encoded_title = quote(title, safe='')
    encoded_body = quote(body, safe='')
    url = f"{BARK_BASE}/{BARK_KEY}/{encoded_title}/{encoded_body}"
    try:
        r = requests.get(url, timeout=8)
        if r.status_code != 200:
            print(f"[BARK ERROR] {r.status_code} {r.text}")
            return
        print(f"[BARK SUCCESS] {r.status_code} {r.text}")
    except requests.RequestException as e:
        print(f"[BARK ERROR] {e}")

# ==== 取价 ====
def fetch_prices() -> tuple[float, float]:
    r = requests.get(COINGECKO_URL, timeout=8)
    data = r.json()
    return data["bitcoin"]["usd"], data["ethereum"]["usd"]

# ==== 历史价格追踪（SQLite持久化） ====
class PriceTracker:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()
        # Track last alerted extremes to avoid duplicate alerts
        self.last_alerted = {
            "24h_low": None,
            "24h_high": None,
            "72h_low": None,
            "72h_high": None,
            "144h_low": None,
            "144h_high": None,
        }
        self._load_last_alerted()
    
    def _init_db(self):
        """Initialize SQLite database and create tables if needed"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        # Table for price history (BTC, ETH, and ratio)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                btc_price REAL NOT NULL,
                eth_price REAL NOT NULL,
                ratio REAL NOT NULL
            )
        ''')
        # Index for faster timestamp queries
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_price_timestamp ON price_history(timestamp)
        ''')
        # Table for last alerted values (persisted across restarts)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS last_alerted (
                key TEXT PRIMARY KEY,
                value REAL
            )
        ''')
        conn.commit()
        conn.close()
    
    def _load_last_alerted(self):
        """Load last alerted values from database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT key, value FROM last_alerted')
        for key, value in cursor.fetchall():
            if key in self.last_alerted:
                self.last_alerted[key] = value
        conn.close()
    
    def _save_last_alerted(self, key: str, value: float):
        """Save last alerted value to database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO last_alerted (key, value) VALUES (?, ?)
        ''', (key, value))
        conn.commit()
        conn.close()
    
    def add_prices(self, btc_price: float, eth_price: float, ratio: float):
        """Add new price measurements with current timestamp"""
        now = datetime.now()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Insert new prices and ratio
        cursor.execute('''
            INSERT INTO price_history (timestamp, btc_price, eth_price, ratio) VALUES (?, ?, ?, ?)
        ''', (now.isoformat(), btc_price, eth_price, ratio))
        
        # Clean up old data (keep only last 145 hours)
        cutoff = (now - timedelta(hours=145)).isoformat()
        cursor.execute('DELETE FROM price_history WHERE timestamp < ?', (cutoff,))
        
        conn.commit()
        conn.close()
    
    def _get_oldest_timestamp(self) -> datetime | None:
        """Get the oldest timestamp in the database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT MIN(timestamp) FROM price_history')
        result = cursor.fetchone()[0]
        conn.close()
        if result:
            return datetime.fromisoformat(result)
        return None
    
    def _get_period_ratios(self, hours: int) -> list[float]:
        """Get all ratios within the specified period"""
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT ratio FROM price_history WHERE timestamp >= ?
        ''', (cutoff,))
        ratios = [row[0] for row in cursor.fetchall()]
        conn.close()
        return ratios
    
    def check_extremes(self, current_ratio: float) -> list[tuple[str, str]]:
        """Check if current ratio is a new low/high for any period.
        Returns list of alert messages (only longest period for each extreme type)."""
        now = datetime.now()
        oldest_timestamp = self._get_oldest_timestamp()
        
        if not oldest_timestamp:
            return []
        
        data_span_hours = (now - oldest_timestamp).total_seconds() / 3600
        
        # Periods sorted from longest to shortest
        periods = [
            ("144h", 144),
            ("72h", 72),
            ("24h", 24)
        ]
        
        # Track the longest period extreme for each type
        longest_low = None   # (period_name, hours, current_ratio)
        longest_high = None  # (period_name, hours, current_ratio)
        
        for period_name, hours in periods:
            # Skip if we don't have enough historical data
            if data_span_hours < hours:
                continue
            
            period_ratios = self._get_period_ratios(hours)
            if not period_ratios:
                continue
            
            min_ratio = min(period_ratios)
            max_ratio = max(period_ratios)
            
            # Check for new low (only if we haven't found a longer period low yet)
            if longest_low is None and current_ratio <= min_ratio:
                low_key = f"{period_name}_low"
                if self.last_alerted[low_key] != current_ratio:
                    longest_low = (period_name, hours, current_ratio, low_key)
            
            # Check for new high (only if we haven't found a longer period high yet)
            if longest_high is None and current_ratio >= max_ratio:
                high_key = f"{period_name}_high"
                if self.last_alerted[high_key] != current_ratio:
                    longest_high = (period_name, hours, current_ratio, high_key)
        
        # Build alerts for the longest periods only
        alerts = []
        
        if longest_low:
            period_name, hours, ratio_val, low_key = longest_low
            alerts.append((
                f"BTC/ETH {period_name} 新低！",
                f"现值 ≈ {ratio_val:.2f} (过去{hours}小时最低)"
            ))
            self.last_alerted[low_key] = ratio_val
            self._save_last_alerted(low_key, ratio_val)
        
        if longest_high:
            period_name, hours, ratio_val, high_key = longest_high
            alerts.append((
                f"BTC/ETH {period_name} 新高！",
                f"现值 ≈ {ratio_val:.2f} (过去{hours}小时最高)"
            ))
            self.last_alerted[high_key] = ratio_val
            self._save_last_alerted(high_key, ratio_val)
        
        return alerts
    
    def get_data_info(self) -> str:
        """Get info about stored data for display"""
        oldest = self._get_oldest_timestamp()
        if not oldest:
            return "无历史数据"
        data_span = (datetime.now() - oldest).total_seconds() / 3600
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM price_history')
        count = cursor.fetchone()[0]
        conn.close()
        return f"历史数据: {count}条记录, 跨度{data_span:.1f}小时"

# ==== 主逻辑 ====
def main():
    btc_price, eth_price = fetch_prices()
    btc_slot = int(btc_price // BTC_STEP)  # 当前 BTC 所在整数档
    eth_slot = int(eth_price // ETH_STEP)  # 当前 ETH 所在整数档
    ratio = btc_price / eth_price           # BTC/ETH 比率
    ratio_slot = int(ratio / RATIO_STEP)    # 当前比率所在档位
    
    # Initialize price tracker (loads historical data from SQLite)
    tracker = PriceTracker()
    
    print(f"[INIT] BTC ≈ ${btc_price:,.0f}  ETH ≈ ${eth_price:,.0f}  BTC/ETH ≈ {ratio:.2f}")
    print(f"[DB] {tracker.get_data_info()}")
    print("[READY] 已开始监控整数节点和24h/72h/144h极值…")
    # Flush stdout
    sys.stdout.flush()

    while True:
        try:
            btc_price, eth_price = fetch_prices()
            new_btc_slot = int(btc_price // BTC_STEP)
            new_eth_slot = int(eth_price // ETH_STEP)
            ratio = btc_price / eth_price
            new_ratio_slot = int(ratio / RATIO_STEP)

            # 如果跨过一个或多个 BTC 档位
            if new_btc_slot != btc_slot:
                direction = "上升至" if new_btc_slot > btc_slot else "下降至"
                final_threshold = new_btc_slot * BTC_STEP if new_btc_slot > btc_slot else (new_btc_slot + 1) * BTC_STEP
                bark_push(
                    f"BTC {direction} ${final_threshold:,.0f}",
                    f"现价 ≈ ${btc_price:,.0f}"
                )
                print(f"[BTC] {direction} ${final_threshold:,.0f} 现价 ≈ ${btc_price:,.0f}")
                # Flush stdout
                sys.stdout.flush()
                btc_slot = new_btc_slot

            # 如果跨过一个或多个 ETH 档位
            if new_eth_slot != eth_slot:
                direction = "上升至" if new_eth_slot > eth_slot else "下降至"
                final_threshold = new_eth_slot * ETH_STEP if new_eth_slot > eth_slot else (new_eth_slot + 1) * ETH_STEP
                bark_push(
                    f"ETH {direction} ${final_threshold:,.0f}",
                    f"现价 ≈ ${eth_price:,.0f}"
                )
                print(f"[ETH] {direction} ${final_threshold:,.0f} 现价 ≈ ${eth_price:,.0f}")
                # Flush stdout
                sys.stdout.flush()
                eth_slot = new_eth_slot

            # 如果跨过一个或多个 BTC/ETH 比率档位
            if new_ratio_slot != ratio_slot:
                direction = "上升至" if new_ratio_slot > ratio_slot else "下降至"
                final_ratio = new_ratio_slot * RATIO_STEP if new_ratio_slot > ratio_slot else (new_ratio_slot + 1) * RATIO_STEP
                bark_push(
                    f"BTC/ETH {direction} {final_ratio:.1f}",
                    f"现值 ≈ {ratio:.2f}"
                )
                print(f"[BTC/ETH] {direction} {final_ratio:.1f} 现值 ≈ {ratio:.2f}")
                # Flush stdout
                sys.stdout.flush()
                ratio_slot = new_ratio_slot
            
            # 追踪价格历史并检查24h/72h/144h极值
            tracker.add_prices(btc_price, eth_price, ratio)
            extreme_alerts = tracker.check_extremes(ratio)
            for title, body in extreme_alerts:
                bark_push(title, body)
                print(f"[EXTREME] {title} {body}")
                sys.stdout.flush()

        except Exception as e:
            print(f"[ERROR] {e}")

        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()

