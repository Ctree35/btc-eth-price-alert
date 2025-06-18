#!/usr/bin/env python3
"""
btc_eth_bark_notifier.py
当 BTC 到达新的整数千位 (n*1 000 USD)、
或 ETH 到达新的整数百位 (n*100 USD) 时，
立刻通过 Bark 推送到 iPhone。

依赖：
    pip install requests
环境变量（也可以直接写在脚本里）：
    BARK_KEY   —— 必填，Bark Device Key
    BARK_BASE  —— 选填，Bark 服务器根地址，默认 https://api.day.app
可调参数：
    BTC_STEP   —— BTC 步长（默认 1000）
    ETH_STEP   —— ETH 步长（默认 100）
    INTERVAL   —— 轮询间隔（秒）
"""
import os
import sys
import time
import requests

# ==== 配置（可用环境变量覆盖） ====
BARK_KEY   = os.getenv("BARK_KEY",  "YOUR_DEVICE_KEY")
BARK_BASE  = os.getenv("BARK_BASE", "https://api.day.app")
BTC_STEP   = int(os.getenv("BTC_STEP",  1000))   # BTC 整数档位步长
ETH_STEP   = int(os.getenv("ETH_STEP",   100))   # ETH 整数档位步长
INTERVAL   = int(os.getenv("INTERVAL",    30))   # 秒

COINGECKO_URL = (
    "https://api.coingecko.com/api/v3/simple/price"
    "?ids=bitcoin,ethereum&vs_currencies=usd"
)

# ==== 推送 ====
def bark_push(title: str, body: str):
    url = f"{BARK_BASE}/{BARK_KEY}/{title}/{body}"
    try:
        requests.get(url, timeout=8)
    except requests.RequestException as e:
        print(f"[BARK ERROR] {e}")

# ==== 取价 ====
def fetch_prices() -> tuple[float, float]:
    r = requests.get(COINGECKO_URL, timeout=8)
    data = r.json()
    return data["bitcoin"]["usd"], data["ethereum"]["usd"]

# ==== 主逻辑 ====
def main():
    btc_price, eth_price = fetch_prices()
    btc_slot = int(btc_price // BTC_STEP)  # 当前 BTC 所在整数档
    eth_slot = int(eth_price // ETH_STEP)  # 当前 ETH 所在整数档
    print(f"[INIT] BTC ≈ ${btc_price:,.0f}  ETH ≈ ${eth_price:,.0f}")
    print("[READY] 已开始监控整数节点…")
    # Flush stdout
    sys.stdout.flush()

    while True:
        try:
            btc_price, eth_price = fetch_prices()
            new_btc_slot = int(btc_price // BTC_STEP)
            new_eth_slot = int(eth_price // ETH_STEP)

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

        except Exception as e:
            print(f"[ERROR] {e}")

        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()

