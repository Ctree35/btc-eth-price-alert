#!/usr/bin/env python3
"""
btc_eth_bark_notifier.py
当 BTC 到达新的整数千位 (n*1 000 USD)、
或 ETH 到达新的整数百位 (n*100 USD)、
或 BTC/ETH 比率到达新的 0.5 倍数档位时，
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
"""
import os
import sys
import time
import requests
from urllib.parse import quote
from collections import deque
from datetime import datetime, timedelta

# ==== 配置（可用环境变量覆盖） ====
BARK_KEY   = os.getenv("BARK_KEY",  "YOUR_DEVICE_KEY")
BARK_BASE  = os.getenv("BARK_BASE", "https://api.day.app")
BTC_STEP   = int(os.getenv("BTC_STEP",  1000))   # BTC 整数档位步长
ETH_STEP   = int(os.getenv("ETH_STEP",   100))   # ETH 整数档位步长
RATIO_STEP = float(os.getenv("RATIO_STEP", 0.5)) # BTC/ETH 比率步长
INTERVAL   = int(os.getenv("INTERVAL",    30))   # 秒

COINGECKO_URL = (
    "https://api.coingecko.com/api/v3/simple/price"
    "?ids=bitcoin,ethereum&vs_currencies=usd"
)

# ==== 推送 ====
def bark_push(title: str, body: str):
    # URL-encode title and body to handle special characters like "/"
    encoded_title = quote(title)
    encoded_body = quote(body)
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

# ==== 历史比率追踪 ====
class RatioTracker:
    def __init__(self):
        # Store (timestamp, ratio) tuples for up to 144 hours
        self.history = deque()
        # Track last alerted extremes to avoid duplicate alerts
        self.last_alerted = {
            "24h_low": None,
            "24h_high": None,
            "72h_low": None,
            "72h_high": None,
            "144h_low": None,
            "144h_high": None,
        }
    
    def add_ratio(self, ratio: float):
        """Add a new ratio measurement with current timestamp"""
        now = datetime.now()
        self.history.append((now, ratio))
        
        # Keep only last 144 hours of data (plus a small buffer)
        cutoff = now - timedelta(hours=145)
        while self.history and self.history[0][0] < cutoff:
            self.history.popleft()
    
    def check_extremes(self, current_ratio: float) -> list[str]:
        """Check if current ratio is a new low/high for any period.
        Returns list of alert messages."""
        alerts = []
        now = datetime.now()
        
        periods = [
            ("24h", 24),
            ("72h", 72),
            ("144h", 144)
        ]
        
        for period_name, hours in periods:
            cutoff = now - timedelta(hours=hours)
            # Get all ratios within this period
            period_ratios = [ratio for ts, ratio in self.history if ts >= cutoff]
            
            if not period_ratios:
                continue  # Not enough data yet
            
            min_ratio = min(period_ratios)
            max_ratio = max(period_ratios)
            
            # Check for new low
            if current_ratio <= min_ratio:
                low_key = f"{period_name}_low"
                # Only alert if this is a different extreme than last time
                if self.last_alerted[low_key] != current_ratio:
                    alerts.append((
                        f"BTC/ETH {period_name} 新低！",
                        f"现值 ≈ {current_ratio:.2f} (过去{hours}小时最低)"
                    ))
                    self.last_alerted[low_key] = current_ratio
            
            # Check for new high
            if current_ratio >= max_ratio:
                high_key = f"{period_name}_high"
                # Only alert if this is a different extreme than last time
                if self.last_alerted[high_key] != current_ratio:
                    alerts.append((
                        f"BTC/ETH {period_name} 新高！",
                        f"现值 ≈ {current_ratio:.2f} (过去{hours}小时最高)"
                    ))
                    self.last_alerted[high_key] = current_ratio
        
        return alerts

# ==== 主逻辑 ====
def main():
    btc_price, eth_price = fetch_prices()
    btc_slot = int(btc_price // BTC_STEP)  # 当前 BTC 所在整数档
    eth_slot = int(eth_price // ETH_STEP)  # 当前 ETH 所在整数档
    ratio = btc_price / eth_price           # BTC/ETH 比率
    ratio_slot = int(ratio / RATIO_STEP)    # 当前比率所在档位
    
    # Initialize ratio tracker
    tracker = RatioTracker()
    tracker.add_ratio(ratio)
    
    print(f"[INIT] BTC ≈ ${btc_price:,.0f}  ETH ≈ ${eth_price:,.0f}  BTC/ETH ≈ {ratio:.2f}")
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
            
            # 追踪比率历史并检查24h/72h/144h极值
            tracker.add_ratio(ratio)
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

