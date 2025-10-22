# btc-eth-price-alert

A notifier to push BTC, ETH, and BTC/ETH ratio price alerts at important price slots to iOS devices via Bark.

## 功能特性

- 🪙 **BTC 价格监控**：每 1,000 USD 发送通知
- 💎 **ETH 价格监控**：每 100 USD 发送通知  
- 📊 **BTC/ETH 比率监控**：每 0.5 倍数发送通知（如 26.0、26.5、27.0）
- 📱 **iOS 推送**：通过 Bark 即时推送到 iPhone
- 🔧 **灵活配置**：所有参数均可通过环境变量自定义

## 快速开始

### 使用 Docker Compose（推荐）

1. 克隆仓库
```bash
git clone https://github.com/yourusername/btc-eth-price-alert.git
cd btc-eth-price-alert
```

2. 配置环境变量

```bash
# 复制环境变量模板
cp env.example .env

# 编辑 .env 文件，填入你的 BARK_KEY
vim .env  # 或使用你喜欢的编辑器
```

3. 启动服务
```bash
docker-compose up -d
```

4. 查看日志
```bash
docker-compose logs -f
```

5. 停止服务
```bash
docker-compose down
```

### 使用 Docker

```bash
docker build -t btc-eth-alert .
docker run -d \
  --name btc-eth-alert \
  --restart unless-stopped \
  -e BARK_KEY="YOUR_DEVICE_KEY" \
  -e BTC_STEP=1000 \
  -e ETH_STEP=100 \
  -e RATIO_STEP=0.5 \
  -e INTERVAL=30 \
  btc-eth-alert
```

### 直接运行 Python 脚本

1. 安装依赖
```bash
pip install -r requirements.txt
```

2. 设置环境变量
```bash
export BARK_KEY="YOUR_DEVICE_KEY"
export BTC_STEP=1000
export ETH_STEP=100
export RATIO_STEP=0.5
export INTERVAL=30
```

3. 运行脚本
```bash
python btc_eth_bark_notifier.py
```

## 配置说明

| 环境变量 | 说明 | 默认值 | 必填 |
|---------|------|--------|------|
| `BARK_KEY` | Bark Device Key | - | ✅ |
| `BARK_BASE` | Bark 服务器地址 | `https://api.day.app` | ❌ |
| `BTC_STEP` | BTC 价格步长（USD） | `1000` | ❌ |
| `ETH_STEP` | ETH 价格步长（USD） | `100` | ❌ |
| `RATIO_STEP` | BTC/ETH 比率步长 | `0.5` | ❌ |
| `INTERVAL` | 轮询间隔（秒） | `30` | ❌ |

## 通知示例

- **BTC 上升至 $91,000** - 现价 ≈ $91,250
- **ETH 下降至 $2,600** - 现价 ≈ $2,580
- **BTC/ETH 上升至 35.0** - 现值 ≈ 35.12

## 获取 Bark Key

1. 在 App Store 下载 [Bark](https://apps.apple.com/cn/app/bark-customed-notifications/id1403753865)
2. 打开 App，复制显示的 Device Key
3. 将 Key 配置到环境变量 `BARK_KEY` 中

## License

MIT
