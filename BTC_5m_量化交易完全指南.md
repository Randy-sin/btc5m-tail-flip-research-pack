# Polymarket BTC 5分钟量化交易 - 完全技术指南

**编制日期：2026年4月13日**
**目标：构建市面上最优秀的BTC 5m自动交易Bot**
**部署环境：爱尔兰服务器 (AWS eu-west-1)**

---

## 当前实现状态（2026-04-14）

当前服务器已部署并运行在 AWS Ireland：

```text
Host: 18.201.88.231
Path: /home/ubuntu/new_PolyMarket
Runtime: python3 main.py + python3 dashboard_server.py
Mode: PAPER_MODE=true
Active strategy: Tier 2 Tail Flip only
```

重要边界：

- 现在跑的是**纸盘验证**，不是真钱 LIVE；不会真实下单。
- 当前代码启用的是本文和《Polymarket中文心经》里的 **Tier 2 尾部翻盘 / B 系数策略**：1c 倾向 GTC maker，2c 极端机会可 FOK 抢单。
- 本文中的 **Tier 1 Oracle 延迟套利** 和 **Tier 3 做市/返佣** 仍属于路线图/研究方向，当前 `main.py` 没有启用。
- 官方 CLOB User Channel 已在代码里接好，但在 `PAPER_MODE=true` 时会自动禁用；切 LIVE 前必须先做小额/干跑成交确认。
- 当前数据交叉验证以 Polymarket RTDS Chainlink（结算源）为主，Binance direct 只做参考和延迟/价差 cross-check。
- 当前 paper validation 默认关闭日风险/日损失 cap：`TAIL_FLIP_MAX_DAILY_RISK <= 0` 和 `MAX_DAILY_LOSS_PCT <= 0` 表示不触发对应上限。第 8 节的 2% 日风险分配是研究型仓位建议，不是当前服务器运行配置。

---

## 目录

1. [市场本质与结算机制](#1-市场本质与结算机制)
2. [Polymarket技术架构](#2-polymarket技术架构)
3. [API完整参考](#3-api完整参考)
4. [数据源与延迟优化](#4-数据源与延迟优化)
5. [数据合并策略](#5-数据合并策略)
6. [量化策略体系](#6-量化策略体系)
7. [逼迫系数B构建方法](#7-逼迫系数b构建方法)
8. [风控与仓位管理](#8-风控与仓位管理)
9. [回测框架](#9-回测框架)
10. [基础设施与部署](#10-基础设施与部署)
11. [开源资源与工具](#11-开源资源与工具)
12. [安全与合规](#12-安全与合规)
13. [2026年4月V2升级注意事项](#13-2026年4月v2升级注意事项)
14. [实施路线图](#14-实施路线图)

---

## 1. 市场本质与结算机制

### 1.1 BTC 5分钟市场是什么

每5分钟（Unix时间戳能被300整除的时刻）开启一个新的二元期权市场：

- **问题**：5分钟后BTC价格相比5分钟前是更高还是更低？
- **关键区别**：不是"接下来5分钟涨还是跌"，而是**窗口结束时刻的价格vs窗口开始时刻的价格**
- **代币**：UP（价格>=开盘价则赢）和DOWN（价格<开盘价则赢）
- **频率**：每天288场，24/7/365
- **日交易量**：约6000万美元，占Polymarket全平台交易量约30%

### 1.2 结算Oracle：Chainlink Data Streams

**这是整个系统最关键的信息：结算用的是Chainlink，不是Binance、Coinbase或任何单一交易所。**


| 参数     | 值                                             |
| ------ | --------------------------------------------- |
| Oracle | Chainlink Data Streams + Chainlink Automation |
| 数据类型   | Pull-based（按需拉取，非定时推送）                        |
| 更新频率   | 平时10-30秒/次，剧烈波动时加速                            |
| 触发条件   | 时间心跳 或 0.5%价格偏离                               |
| 数据源    | 多交易所聚合（具体权重不公开）                               |


**结算流程：**

```
T=0     窗口开启。Chainlink快照第一个报价 = "Price to Beat"（开盘价）
T=300s  窗口关闭。Chainlink Automation触发链上结算
T+2-30s Chainlink聚合oracle报告（收盘价）
T+~128s 64区块确认后（Polygon ~2秒/区块），USDC分配完成
```

### 1.3 关键结算规则

- **平局规则**：收盘价 >= 开盘价 → **UP赢**（平局算UP赢）
- **Oracle失败**：如果Chainlink无法在超时窗口内提供有效报告 → **平局**，所有仓位退回
- **赢家赎回**：无截止日期，随时可赎回$1.00 USDC

### 1.4 Market ID规律（可预计算）

```python
import time

def get_current_btc5m_slug():
    now = int(time.time())
    window_ts = (now // 300) * 300
    return f"btc-updown-5m-{window_ts}"

def get_next_btc5m_slug():
    now = int(time.time())
    window_ts = (now // 300) * 300
    return f"btc-updown-5m-{window_ts + 300}"
```

无需轮询API即可知道下一个市场的slug。

---

## 2. Polymarket技术架构

### 2.1 混合去中心化设计

- **链下**：订单簿匹配引擎（高速、免gas、即时）
- **链上**：Polygon PoS（Chain ID 137）上的CTF合约完成原子结算
- **关键约束**：YES + NO 永远 = $1.00 USDC（由合约强制执行）

### 2.2 核心合约地址


| 合约                       | 地址                                           |
| ------------------------ | -------------------------------------------- |
| CTF Exchange             | `0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E` |
| Neg Risk CTF Exchange    | `0xC5d563A36AE78145C45a50134d48A1215220f80a` |
| Conditional Tokens (CTF) | `0x4D97DCd97eC945f40cF65F87097ACe5EA0476045` |
| USDC.e (质押物)             | `0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174` |


**注意**：2026年4月V2升级中，USDC.e将被pUSD替代，合约地址会更新。

### 2.3 代币机制

三种匹配场景：

1. **Direct Match**：已有YES和NO订单直接撮合，USDC在双方之间转移
2. **Mint**：YES买方+NO买方合计出$1.00，CTF合约锁定$1铸造1 YES + 1 NO
3. **Merge**：YES+NO持有者同时退出，销毁代币释放$1.00 USDC

### 2.4 费率结构

**核心公式：**

```
fee = C × feeRate × p × (1 - p)
```


| 参数             | 值                      |
| -------------- | ---------------------- |
| Crypto类feeRate | 0.072 (7.2%)           |
| p=0.50时有效费率    | ~1.80%                 |
| p=0.01或0.99时费率 | 接近0                    |
| Maker费率        | **0%**                 |
| Maker返佣        | 每日USDC，为taker费的**20%** |
| 卖单taker费       | **0**                  |


**对策略的关键影响：**

- 1c/2c尾部翻盘策略在极端价格下费率几乎为0 → 可行
- 50/50附近的延迟套利费率1.80% → 需要>53.3%胜率才能盈利
- **做Maker（挂单）是最优选择**：0费率 + 20%返佣

---

## 3. API完整参考

### 3.1 三套API


| API       | Base URL                           | 用途             |
| --------- | ---------------------------------- | -------------- |
| CLOB API  | `https://clob.polymarket.com`      | 交易核心：下单、撤单、订单簿 |
| Gamma API | `https://gamma-api.polymarket.com` | 市场元数据、发现、分类    |
| Data API  | `https://data-api.polymarket.com`  | 历史交易、用户仓位      |


### 3.2 CLOB REST端点

**公开（无需认证）：**


| 方法  | 端点                             | 说明        |
| --- | ------------------------------ | --------- |
| GET | `/ok`                          | 健康检查      |
| GET | `/time`                        | 服务器时间     |
| GET | `/order-book/{token_id}`       | 完整订单簿快照   |
| GET | `/price?token_id=X&side=BUY`   | 最优价格      |
| GET | `/midpoint?token_id=X`         | 中间价       |
| GET | `/prices-history`              | 历史token价格 |
| GET | `/last-trade-price?token_id=X` | 最新成交价     |
| GET | `/trades`                      | 最近交易      |


**认证（L2 HMAC）：**


| 方法     | 端点            | 说明               |
| ------ | ------------- | ---------------- |
| POST   | `/order`      | 下单（单笔）           |
| POST   | `/orders`     | 批量下单（最多15笔/次）    |
| DELETE | `/order/{id}` | 撤单               |
| DELETE | `/cancel-all` | 全部撤单             |
| POST   | `/heartbeats` | 心跳（每5秒，否则自动撤所有单） |
| GET    | `/positions`  | 查仓位              |


### 3.3 WebSocket端点


| 频道         | URL                                                    | 认证       |
| ---------- | ------------------------------------------------------ | -------- |
| Market     | `wss://ws-subscriptions-clob.polymarket.com/ws/market` | 无        |
| User       | `wss://ws-subscriptions-clob.polymarket.com/ws/user`   | 需API key |
| RTDS（实时数据） | `wss://ws-live-data.polymarket.com`                    | 无        |


**订阅Market频道：**

```json
{
  "assets_ids": ["<token_id>"],
  "type": "market",
  "custom_feature_enabled": true
}
```

**订阅Chainlink价格流（最关键）：**

```json
{
  "action": "subscribe",
  "subscriptions": [{
    "topic": "crypto_prices_chainlink",
    "type": "*",
    "filters": ""
  }]
}
```

注意：官方 RTDS 文档示例使用空 filter。空 filter 可能推送多个 crypto symbol，所以代码必须在本地只接受 `symbol == "btc/usd"` 的消息，不能把所有 `crypto_prices_chainlink` 都当作 BTC 结算价。

**订阅Binance价格（参考信号）：**

```json
{
  "action": "subscribe",
  "subscriptions": [{
    "topic": "crypto_prices",
    "type": "update",
    "filters": "btcusdt"
  }]
}
```

**订阅User频道（真实成交确认，LIVE才启用）：**

```json
{
  "auth": {
    "apiKey": "<POLY_API_KEY>",
    "secret": "<POLY_SECRET>",
    "passphrase": "<POLY_PASSPHRASE>"
  },
  "markets": ["<condition_id>"],
  "type": "user"
}
```

注意：User Channel 的 `markets` 使用的是 **condition_id**，不是 CLOB token_id。真实 GTC maker 单只能在收到 User Channel 的 `TRADE/MATCHED` 等成交事件后才应该记入 position，不能把 REST 下单返回 `live` 当作成交。

### 3.4 WebSocket事件类型


| 事件                 | 触发时机          | 用途                             |
| ------------------ | ------------- | ------------------------------ |
| `book`             | 订阅时 + 每次成交后   | 完整订单簿快照                        |
| `price_change`     | 新单/撤单         | 增量更新                           |
| `last_trade_price` | 每次成交          | 实时交易流                          |
| `tick_size_change` | 价格>0.96或<0.04 | 精度从0.01变为0.001                 |
| `best_bid_ask`     | 盘口变化          | 最优买卖价（需custom_feature_enabled） |
| `new_market`       | 新市场创建         | 自动发现新BTC 5m市场                  |
| `market_resolved`  | 结算完成          | 获取结算结果                         |


### 3.5 Rate Limits

**全局上限：15,000 req/10s**


| 端点                   | Burst (10s) | Sustained (10min) |
| -------------------- | ----------- | ----------------- |
| POST /order          | 3,500       | 36,000            |
| DELETE /order        | 3,000       | 30,000            |
| POST /orders (batch) | 1,000       | 15,000            |
| GET /book, /price    | 1,500/10s   | -                 |
| WebSocket            | **无限制**     | -                 |


**WebSocket限制：**

- 每连接最多500个instruments
- 每IP最多5个并发WebSocket连接
- 心跳：每10秒发PING

### 3.6 认证体系

**两级认证：**

**L1 - EIP-712钱包签名**（用于创建API凭证和签名订单）：

```
Headers: POLY_ADDRESS, POLY_SIGNATURE, POLY_TIMESTAMP, POLY_NONCE
```

**L2 - HMAC-SHA256 API Key**（用于高频订单管理）：

```
Headers: POLY_API_KEY, POLY_PASSPHRASE, POLY_SIGNATURE(HMAC), POLY_TIMESTAMP
```

```python
from py_clob_client.client import ClobClient

client = ClobClient(
    "https://clob.polymarket.com",
    key=PRIVATE_KEY,
    chain_id=137,
    signature_type=1,
    funder=FUNDER_ADDRESS
)
creds = client.create_or_derive_api_creds()
client.set_api_creds(creds)
```

---

## 4. 数据源与延迟优化

### 4.1 数据源分级（按重要性排序）


| 优先级   | 数据源                           | 从爱尔兰延迟          | 角色                         |
| ----- | ----------------------------- | --------------- | -------------------------- |
| **1** | Polymarket RTDS Chainlink     | <2ms (伦敦)       | **结算Oracle - 唯一真相源**       |
| **2** | Polymarket RTDS Binance relay | <2ms (同连接)      | 价差信号（Binance vs Chainlink） |
| **3** | Binance Direct WebSocket      | ~147-211ms (东京) | 最高频BTC价格变动                 |
| **4** | Coinbase WebSocket            | ~125ms (美东)     | 机构参考价格                     |
| **5** | Kraken WebSocket              | ~5-30ms (欧洲)    | L3订单簿压力信号                  |
| **6** | Bybit WebSocket               | ~200ms (新加坡)    | 期货动量、资金费率                  |


### 4.2 关键发现：爱尔兰服务器是全球最佳位置之一

**Polymarket CLOB API服务器位于 AWS eu-west-2（伦敦）**

```
爱尔兰 (eu-west-1) → Polymarket (eu-west-2): < 2ms RTT
美国东部 → Polymarket: ~80ms
亚洲 → Polymarket: ~200ms+
```

你的爱尔兰服务器在下单延迟上比美国和亚洲的竞争者有**巨大优势**。

### 4.3 各交易所匹配引擎位置


| 交易所        | 引擎位置           | 从爱尔兰延迟     |
| ---------- | -------------- | ---------- |
| Polymarket | 伦敦 (eu-west-2) | ~2ms       |
| Binance    | 东京             | ~147-211ms |
| Coinbase   | 美东 (Virginia)  | ~125ms     |
| Kraken     | 欧洲/美东          | ~5-30ms    |
| Bitstamp   | 卢森堡            | ~10ms      |
| Bybit/OKX  | 新加坡            | ~200ms+    |


### 4.4 WebSocket连接配置

**必须连接（3条）：**

```python
# 连接1: Polymarket RTDS (Chainlink + Binance)
ws1 = "wss://ws-live-data.polymarket.com"
# 订阅: crypto_prices_chainlink (BTC/USD) + crypto_prices (btcusdt)

# 连接2: Polymarket CLOB Market Channel
ws2 = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
# 订阅: 当前+下一个BTC 5m市场的UP和DOWN token_id

# 连接3: Binance Direct
ws3 = "wss://stream.binance.com:9443/ws/btcusdt@bookTicker"
# 最优买卖价，最低延迟
```

**可选增强（2条）：**

```python
# 连接4: Kraken L3 订单簿
ws4 = "wss://ws.kraken.com/"

# 连接5: Binance 强制清算流
ws5 = "wss://fstream.binance.com/ws/btcusdt@forceOrder"
# 检测大额清算级联
```

---

## 5. 数据合并策略

### 5.1 核心原则：Oracle锚定聚合

目标不是计算"真实"BTC价格，而是**预测下一次Chainlink更新值**。

Chainlink更新逻辑：

- 时间心跳（约60秒正常情况）
- 0.5%价格偏离触发（Binance/Coinbase偏离上次Oracle值≥0.5%时）

### 5.2 信号融合方案

```python
class SignalAggregator:
    def __init__(self):
        self.chainlink_last = None      # 最新Chainlink价格
        self.chainlink_timestamp = None
        self.binance_mid = None          # Binance最优买卖均价
        self.window_open_price = None    # 本轮开盘价
    
    def compute_signals(self):
        signals = {}
        
        # 信号1: Oracle偏离度（最重要）
        # Binance已经动了但Chainlink还没更新 → 预测方向
        if self.binance_mid and self.chainlink_last:
            signals['oracle_divergence'] = (
                (self.binance_mid - self.chainlink_last) / self.chainlink_last
            )
        
        # 信号2: 窗口内Delta
        # 当前BTC价格 vs 本轮开盘价
        if self.binance_mid and self.window_open_price:
            signals['window_delta'] = (
                (self.binance_mid - self.window_open_price) / self.window_open_price
            )
        
        # 信号3: 多时间窗口VWAP斜率
        # 30s / 60s / 120s / 240s
        # 权重偏向短期: [0.35, 0.30, 0.20, 0.15]
        
        # 信号4: 订单簿压力
        # pressure = (bid_vol - ask_vol) / (bid_vol + ask_vol)
        # 范围 [-1, +1]
        
        return signals
```

### 5.3 延迟偏移校正

不同交易所数据到达时间不同，必须校正：

```python
# 每条消息记录两个时间戳
msg_data = {
    'exchange_ts': exchange_reported_timestamp,  # 交易所报告的时间
    'arrival_ts': time.time_ns(),                # 本地收到时间
    'latency_offset': arrival_ts - exchange_ts   # 延迟偏移
}

# 合并信号前先对齐时间
# 永远不要用未校正的Binance价格和刚收到的Chainlink价格直接比较
```

### 5.4 时间同步

```bash
# 使用chrony对齐AWS内部NTP
# 精度: <1ms（完全满足5分钟窗口需求）
sudo apt install chrony
# 配置 169.254.169.123 (AWS内部NTP)
```

---

## 6. 量化策略体系

### 6.1 三层策略架构

当前仓库运行状态：只启用 **Tier 2 Tail Flip**。Tier 1 和 Tier 3 是完整系统蓝图，不代表当前服务器已经实盘运行这些策略。

```
┌─────────────────────────────────────────────────────────┐
│ Tier 1: Oracle延迟套利 (主策略)                           │
│ - 信号: Chainlink vs CLOB价格gap ≥ 0.05%               │
│ - 入场: Taker单（付1.80%费率，赚5-10%胜率优势）            │
│ - 预期胜率: 55-63%                                      │
│ - 日交易次数: 20-40                                      │
│ - 仓位: Quarter-Kelly, max 0.25%/笔                     │
├─────────────────────────────────────────────────────────┤
│ Tier 2: 尾部翻盘/逼迫系数B (辅助策略)                     │
│ - 信号: Token价格≤2c + B>阈值 + Maker挂单               │
│ - 入场: GTC Maker单（0%费率 + 20%返佣）                   │
│ - 预期翻盘率: 1c≈1.21%, 2c≈2.5%（过滤后）               │
│ - 日交易次数: 5-15                                       │
│ - 仓位: Quarter-Kelly at极端赔率, max 0.05%/笔           │
├─────────────────────────────────────────────────────────┤
│ Tier 3: 做市/返佣收割 (稳定收益)                          │
│ - 策略: 双边挂单在2-3c和97-98c                           │
│ - 收益: 0% Maker费 + 20%返佣                            │
│ - Delta对冲保持中性                                      │
│ - 仓位: 固定0.10%/边                                    │
└─────────────────────────────────────────────────────────┘
```

### 6.2 Tier 1: Oracle延迟套利详解

**已验证的最高收益策略。** 一个公开案例：oracle-lag-sniper，5,017笔交易，61.4%胜率，3周赚$59,244。

**机制：**

1. 同时订阅Binance BTC/USD + Polymarket Chainlink RTDS
2. 当Binance显示BTC急剧单向移动时，Polymarket订单簿尚未重新定价（2-10秒延迟）
3. 在预测方向上以偏低价格买入

**入场条件（5分钟市场）：**

- |delta_btc| ≥ 0.05% from 开盘价
- 窗口剩余 ≥ 90秒
- 目标Token价格 ≤ $0.62（尚未充分定价）
- 10分钟趋势方向一致

**当前状态（2026年Q1）：**

- 套利窗口从12.3秒缩短到**2.7秒**
- 73%利润被<100ms执行的Bot捕获
- 50/50附近因1.80% taker费已不可行
- **仅在价格>$0.85时可行**（费率随p×(1-p)降低）

### 6.3 Tier 2: 尾部翻盘策略详解

**核心逻辑：**

- 当UP或DOWN Token跌到1-2美分时买入
- 赢了赚98-99美元，输了亏1-2美元
- 基础翻盘率~~0.64%（1c），用逼迫系数B过滤后提升到~~1.21%

**盈亏平衡分析：**


| Token价格 | 赔率   | 需要翻盘率（无费） | 需要翻盘率（Taker） | 需要翻盘率（Maker） |
| ------- | ---- | --------- | ------------ | ------------ |
| 1c      | 99:1 | >1.00%    | >1.80%       | <1.00%       |
| 2c      | 49:1 | >2.00%    | >3.80%       | <2.00%       |
| 3c      | 32:1 | >3.00%    | >4.80%       | <3.00%       |


**关键结论：1c/2c策略必须用Maker单才能盈利。**

**挂单方式选择：**

- **GTC挂1c**：等待成交，无费率，适合逼迫系数高的场景
- **FOK抢2c**：立即成交（taker），费率几乎为0（p=0.02时），适合紧急翻盘信号

当前实现细节（2026-04-14）：

- Proactive path：当输家侧价格足够低且 B 高于更严格阈值时，挂 1c GTC；LIVE 下只有 User Channel 确认成交后才入账。
- Reactive path：当某侧 ask 已经到 1-2c 且 B 过阈值时，FOK 抢单；每局每方向最多触发一次，避免重复下单。
- 每轮新市场会记录 round snapshot；每次成交会写入 SQLite 和 dashboard 日志。

**成功案例：** 文中提到的交易员只玩2c，每天288场筛选约100场，2天命中6次，盈利5万美元后离场。

### 6.4 Tier 3: 做市策略详解

**经济模型：**

- 散户Taker以$0.56买入（支付~1.80%费率）
- 做市商以$0.56卖出，赚取spread
- 做市商额外获得taker费的20%作为每日USDC返佣

**核心风险 - 逆向选择：**

- BTC剧烈波动时，知情Bot会集中打做市商一边
- 做市商被迫持有大量输家代币

**库存管理策略：**

```python
class InventoryManager:
    MAX_INVENTORY_RATIO = 0.30  # 单边不超过30%
    
    def skew_quotes(self, inventory_delta):
        """库存偏斜 → 报价偏斜"""
        if inventory_delta > 0:  # 多了UP
            # 扩大UP卖价，缩小UP买价 → 鼓励卖出UP
            up_ask_offset = +0.01
            up_bid_offset = -0.01
        else:
            up_ask_offset = -0.01
            up_bid_offset = +0.01
        return up_bid_offset, up_ask_offset
    
    def should_flatten(self, time_remaining, inventory_ratio):
        """窗口结束前2分钟强制平仓"""
        if time_remaining < 120 and abs(inventory_ratio) > 0.1:
            return True
        return False
```

### 6.5 T-10秒终盘策略

**机制：**

- 在窗口关闭前10秒计算复合信号
- 信号来源：Window Delta（权重5-7x）、RSI、ATR、订单簿深度
- 4时间窗口加权线性回归（30s/60s/120s/240s）
- 信号>阈值 → FOK市价单

**实际限制：** Polygon确认延迟2-5秒，实际最后可执行时刻约在T-15到T-30秒。

### 6.6 清算级联翻盘策略

```python
# Binance强制清算WebSocket
# wss://fstream.binance.com/ws/btcusdt@forceOrder

# 当清算 > $2M / 10秒内 且 token_price < 0.05 → 翻盘候选
# BTC急跌后反弹，1-3c的Token可能翻盘
```

---

## 7. 逼迫系数B构建方法

### 7.1 概念基础

逼迫系数B衡量市场被推到极端价格状态的程度，以及翻盘条件是否高于基准概率。类似于传统期权的**pin risk**和**gamma squeeze**。

### 7.2 公式构建

```
B = w1 × T_factor + w2 × Vol_factor + w3 × Spread_factor + w4 × Momentum_factor
```

**组件1: 时间压力 (T_factor)**

```python
T_factor = 1 - (t_remaining / 300)
# 越接近到期，压力越大
# T-10s: T_factor = 0.967
# T-60s: T_factor = 0.800
```

**组件2: 局内波动率 (Vol_factor)**

```python
Vol_factor = sigma_intraround / sigma_hourly_avg
# sigma_intraround = 本轮BTC tick收益率的实现波动率
# sigma_hourly_avg = 前12个5分钟窗口波动率的EWMA (lambda=0.94)
# 比值>1 = 本轮比平时更波动 → 翻盘概率提升
# 归一化到0-1 (sigmoid或min-max)
```

**组件3: 价格偏离 (Spread_factor)**

```python
delta_btc = (BTC_current - BTC_window_open) / BTC_window_open
token_implied_prob = current_token_price  # 如0.01
model_prob = 0.5 + sigmoid(delta_btc * time_decay_multiplier)
Spread_factor = abs(token_implied_prob - model_prob)
# 偏离越大 → Token可能被错误定价
```

**组件4: BTC小时动量 (Momentum_factor)**

```python
btc_1h_return = (BTC_current - BTC_1h_ago) / BTC_1h_ago
Momentum_factor = 1 - abs(normalize(btc_1h_return))
# 趋势越弱 → 翻盘越容易
# 周末应给+0.10加分（流动性薄 → 翻盘信号更可靠）
```

**建议权重（需回测校准）：**

```python
w1 = 0.30  # 时间压力（到期时主导）
w2 = 0.35  # 波动率（最强翻盘预测因子）
w3 = 0.25  # 偏离信号
w4 = 0.10  # 趋势修正
```

**决策规则：** `B > threshold_B` 时才入场。阈值需从历史数据中校准，使条件翻盘率超过盈亏平衡点。

### 7.3 Black-Scholes二元期权概率估计

```python
from scipy.stats import norm
import numpy as np

def bs_binary_prob(current_price, strike, sigma_per_second, time_remaining_seconds):
    """
    二元期权的B-S概率（cash-or-nothing）
    返回BTC在到期时高于strike的概率
    """
    if time_remaining_seconds <= 0:
        return 1.0 if current_price >= strike else 0.0
    
    sigma_T = sigma_per_second * np.sqrt(time_remaining_seconds)
    d2 = np.log(current_price / strike) / sigma_T
    return norm.cdf(d2)

def ewma_vol(returns, lambda_=0.94):
    """指数加权移动平均波动率"""
    var = returns[0] ** 2
    for r in returns[1:]:
        var = lambda_ * var + (1 - lambda_) * r ** 2
    return np.sqrt(var)
```

### 7.4 时段效应


| 时段   | UTC时间       | 波动性 | Oracle延迟质量 | 翻盘率预期    |
| ---- | ----------- | --- | ---------- | -------- |
| 亚洲   | 00:00-08:00 | 低   | 延迟大（套利者少）  | **高于平均** |
| 伦敦开盘 | 08:00-10:00 | 高峰  | 快速重定价      | 低于平均     |
| 美国开盘 | 13:30-16:00 | 最高  | 最快         | 最低       |
| 纽约收盘 | 20:00-00:00 | 中   | 中          | 中        |


**建议：** 亚洲时段加权B_score（流动性薄 → 尾部定价效率低 → 翻盘率高）。

### 7.5 周末vs工作日

- 工作日波动率高20-40%（机构参与）
- 周末由Bot主导，订单簿更薄
- 周末翻盘的不可预测性更高 → **分别校准B阈值**
- 建议：周末Momentum_factor权重×0.85，Vol_factor阈值+0.10

---

## 8. 风控与仓位管理

### 8.1 Kelly公式应用

```python
def kelly_fraction(flip_prob, token_price):
    """
    标准Kelly: f* = (bp - q) / b
    b = 净赔率 = (1 - token_price) / token_price
    p = 翻盘概率
    q = 1 - p
    """
    b = (1 - token_price) / token_price
    p = flip_prob
    q = 1 - p
    f_star = (b * p - q) / b
    return max(0, f_star)

# 1c翻盘 (p=0.0121):
# b = 99, f* = (99×0.0121 - 0.9879)/99 = 0.00212
# Quarter-Kelly: 0.053% per trade

# 2c翻盘 (p=0.025):
# b = 49, f* = (49×0.025 - 0.975)/49 = 0.00561
# Quarter-Kelly: 0.14% per trade
```

**强烈建议使用Quarter-Kelly（1/4 Kelly）**，因为翻盘概率估计有不确定性。

### 8.2 每日资金分配

> 当前实现注：服务器 paper validation 为了持续收集样本，默认关闭日风险/日损失 cap；下面的 2% 是研究建议和上线前可选风控模板，不代表当前 `PAPER_MODE=true` 的运行配置。

```
总日风险上限: 总资金的2%

Tier 1 (Oracle延迟套利): 50%日分配
Tier 2 (尾部翻盘):       30%日分配
Tier 3 (做市/返佣):      20%日分配

单笔上限:
- Oracle延迟: 0.25%资金/笔
- 尾部翻盘:   0.05%资金/笔
- 做市:       0.10%资金/边
```

### 8.3 期望值计算

```python
def calculate_ev(flip_prob, token_price, order_type="maker"):
    """
    每美元下注的期望收益
    """
    if order_type == "taker":
        fee = 0.072 * token_price * (1 - token_price)
        effective_cost = token_price + fee
        ev = flip_prob * (1.0 - effective_cost) - (1 - flip_prob) * effective_cost
    elif order_type == "maker":
        # 0费率 + 对手方费率的20%返佣
        rebate = (1 - token_price) * 0.072 * token_price * (1 - token_price) * 0.20
        ev = flip_prob * (1.0 - token_price + rebate) - (1 - flip_prob) * (token_price - rebate)
    
    return ev / token_price

# 1c Maker, 过滤翻盘率1.21%:
# EV ≈ +0.449% per dollar → 盈利
```

### 8.4 最大回撤场景


| 场景   | 描述          | 最大回撤   | 恢复时间 |
| ---- | ----------- | ------ | ---- |
| 正常运作 | 优势保持        | 8-12%  | 1-2周 |
| 翻盘干旱 | 24h无翻盘      | 15-25% | 3-7天 |
| 策略失效 | 新Bot出现      | 30-40% | 数周   |
| 闪崩   | BTC 5分钟跌10% | 20-40% | 不确定  |
| 费率变化 | 平台提高费率      | 立即负EV  | 立即停止 |


**24小时无翻盘概率：**

```python
p_no_flip = (1 - 0.0121) ** 13  # 13笔/天 at 1c
# = 0.855 → ~14.5%概率 → 大约每7天发生一次
# Quarter-Kelly下，一天损失 = 13 × 0.05% = 0.65%资金 → 可接受
```

### 8.5 熔断器

```python
class CircuitBreaker:
    def should_trade(self, strategy, edge, state):
        # 硬止损
        if state.daily_loss / state.bankroll > 0.02:        # 日亏2%停
            return False
        if state.bankroll / state.session_start < 0.85:     # 回撤15%停
            return False
        if state.consecutive_losses >= 7 and edge < 0.05:   # 连亏7次且edge低
            return False
        
        # 策略特定止损
        if strategy == 'tail_flip':
            if state.consecutive_losses >= 10:               # 翻盘连亏10次停
                return False
            if edge < 0.002:                                  # edge太薄停
                return False
        
        return True
```

### 8.6 Edge衰减监测

```python
import scipy.stats as stats

class EdgeMonitor:
    def __init__(self, window=100, theoretical_rate=0.0121):
        self.results = []
        self.window = window
        self.rate = theoretical_rate
    
    def is_edge_intact(self, alpha=0.05):
        """单侧二项检验：实际翻盘率是否显著低于理论值"""
        recent = self.results[-self.window:]
        if len(recent) < 30:
            return True
        
        k = sum(recent)
        n = len(recent)
        p_value = stats.binom_test(k, n, self.rate, alternative='less')
        return p_value > alpha
    
    def decay_alert(self):
        rate = sum(self.results[-self.window:]) / len(self.results[-self.window:])
        if rate < self.rate * 0.5:
            return "HALT: Edge严重衰减"
        elif rate < self.rate * 0.75:
            return "WARNING: Edge低于预期"
        return "OK"
```

---

## 9. 回测框架

### 9.1 数据采集


| 数据源                   | 类型                         | 粒度  | 备注              |
| --------------------- | -------------------------- | --- | --------------- |
| PolyBackTest.com      | 订单簿快照+Oracle价格             | 亚秒级 | 付费，$19.90/月，最方便 |
| Bitquery GraphQL      | 链上交易                       | 逐交易 | 近7天免费，历史需付费     |
| Dune Analytics        | 聚合数据+结算结果                  | 逐区块 | SQL查询，免费        |
| polyrec (GitHub)      | 实时录制Chainlink+Binance+CLOB | CSV | 开源，自建数据集        |
| n8n+Supabase workflow | 自动价格采集                     | 5分钟 | 自托管，免费          |
| Tardis.dev            | BTC tick级数据                | 逐笔  | 付费，最完整          |


### 9.2 每轮必需数据点

1. 本轮开盘BTC价格（Chainlink Oracle快照）
2. 本轮收盘BTC价格（结算价格）
3. Token价格时序（YES和NO，1秒间隔）
4. 订单簿深度快照（bid/ask前5档，5秒间隔）
5. 结算结果（YES赢还是NO赢）
6. 同时刻Binance BTC价格（分析Oracle延迟）
7. BTC资金费率（CoinGlass API）
8. BTC未平仓合约变化（Coinalyze）

### 9.3 统计验证

**翻盘概率表：**

```
对每个价格桶(1c, 2c, ... 10c)和每个B值十分位：
flip_prob(price, B_decile) = count(flips) / count(observations)
置信区间 = flip_prob ± 1.96 × sqrt(flip_prob×(1-flip_prob)/n)
```

**最小样本量（95%置信，±0.3%误差）：**

- 1%翻盘率需要~4,300个观测值
- 每天288轮，约5-15%到达1c → 14-43观测/天
- 需要**100-300天数据**

**验证方法：**

- 滚动前向优化：前60天训练，后20天测试，滚动前进
- Information Ratio > 0.5
- Calmar Ratio > 1.0
- 连续翻盘独立性检验（runs test）
- 翻盘率平稳性检验（Chow test）

### 9.4 历史Chainlink Oracle价格重建

```python
# Chainlink在Polygon上的BTC/USD价格合约会emit AnswerUpdated事件
# 用Bitquery查询历史价格
query = """
{
  EVM(network: polygon) {
    SmartContractEvents(
      where: {
        Block: {Time: {after: "2026-02-01T00:00:00Z"}}
        SmartContract: {Address: {is: "<chainlink_btc_feed_address>"}}
      }
    ) {
      Block { Time }
      Arguments { Value { ... on EVM_ABI_Integer_Value_Arg { integer } } }
    }
  }
}
"""
```

---

## 10. 基础设施与部署

### 10.1 推荐架构（单服务器，适合起步）

当前服务器是 AWS eu-west-1，适合验证和低延迟接近 Polymarket 欧洲基础设施。当前实例为小规模验证环境；若切 LIVE 并提高频率，建议再评估 CPU、网络、systemd 管理和日志轮转。

```
┌──────────────────────────────────────┐
│  AWS eu-west-1 (Dublin, Ireland)     │
│  Instance: c7i.xlarge 或 c7g.xlarge  │
│                                      │
│  ┌──────────────────────────────┐    │
│  │ WebSocket Manager (asyncio)  │    │
│  │ - Polymarket RTDS (Chainlink)│    │
│  │ - Polymarket RTDS (Binance)  │    │
│  │ - Polymarket CLOB Market     │    │
│  │ - Binance Direct             │    │
│  │ - Kraken L3 (可选)           │    │
│  └──────────┬───────────────────┘    │
│             │                        │
│  ┌──────────▼───────────────────┐    │
│  │ Signal Aggregator            │    │
│  │ - Oracle偏离度计算            │    │
│  │ - 窗口Delta                  │    │
│  │ - VWAP斜率                   │    │
│  │ - 逼迫系数B                  │    │
│  └──────────┬───────────────────┘    │
│             │                        │
│  ┌──────────▼───────────────────┐    │
│  │ Strategy Engine              │    │
│  │ - Tier 1: Oracle Lag Arb     │    │
│  │ - Tier 2: Tail Flip          │    │
│  │ - Tier 3: Market Making      │    │
│  └──────────┬───────────────────┘    │
│             │                        │
│  ┌──────────▼───────────────────┐    │
│  │ Order Manager                │    │
│  │ - EIP-712签名                │    │
│  │ - Rate limiter               │    │
│  │ - Heartbeat (5s)             │    │
│  │ - Circuit breaker            │    │
│  └──────────┬───────────────────┘    │
│             │                        │
│  ┌──────────▼───────────────────┐    │
│  │ Risk & Monitoring            │    │
│  │ - Edge衰减监测               │    │
│  │ - P&L追踪                    │    │
│  │ - Telegram/Discord告警       │    │
│  │ - TimescaleDB日志            │    │
│  └──────────────────────────────┘    │
└──────────────────────────────────────┘
```

### 10.2 TCP优化

```python
import socket

# 禁用Nagle算法（减少40ms缓冲延迟）
sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

# TCP keepalive（快速检测断连）
sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

# 增大socket缓冲区
sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4 * 1024 * 1024)
```

```bash
# CPU核心绑定（减少上下文切换抖动）
taskset -c 0 python ws_manager.py
taskset -c 1 python strategy_engine.py
taskset -c 2 python order_manager.py
```

### 10.3 时间同步

```bash
# chrony配置AWS内部NTP
server 169.254.169.123 prefer iburst minpoll 4 maxpoll 4
# 精度 <1ms，足够5分钟窗口使用
```

### 10.4 技术栈推荐


| 组件  | 推荐                     | 备注                |
| --- | ---------------------- | ----------------- |
| 语言  | Python (asyncio)       | 起步快；生产级可考虑Rust/Go |
| SDK | py-clob-client         | 官方Python SDK      |
| WS库 | websockets / aiohttp   | 异步WebSocket       |
| 数据库 | TimescaleDB            | 时间序列优化            |
| 缓存  | Redis                  | 实时状态存储            |
| 监控  | FastAPI + Telegram Bot | Dashboard + 告警    |
| 签名  | eth_account (Python)   | EIP-712签名         |


**注意**：py-clob-client有已知Bug（float精度错误、WebSocket挂起、tick缓存泄漏）。生产级Bot应考虑Rust/Go自定义实现。

---

## 11. 开源资源与工具

### 11.1 GitHub仓库


| 仓库                                                                                    | 策略            | 语言     | 质量                  |
| ------------------------------------------------------------------------------------- | ------------- | ------ | ------------------- |
| [oracle-lag-sniper](https://github.com/JonathanPetersonn/oracle-lag-sniper)           | Chainlink延迟套利 | Python | 最高 - 61.4%胜率，$59K利润 |
| [polymarket-trade-engine](https://github.com/KaustubhPatange/polymarket-trade-engine) | 5m BTC策略引擎    | TS/Bun | 高 - 真实盈利            |
| [polymarket-bot-arena](https://github.com/ThinkEnigmatic/polymarket-bot-arena)        | 贝叶斯自适应4-bot竞技 | Python | 高 - 进化学习            |
| [polymarket/agents](https://github.com/Polymarket/agents)                             | LLM交易         | Python | 中 - 官方参考            |
| [polymarket-nonce-guard](https://github.com/TheOneWhoBurns/polymarket-nonce-guard)    | Ghost Order检测 | Python | 高 - 安全必备            |
| [polyrec](https://github.com/txbabaxyz/polyrec)                                       | 实时数据录制        | Python | 高 - 自建数据集           |
| [py-clob-client](https://github.com/Polymarket/py-clob-client)                        | 官方Python SDK  | Python | 官方                  |
| [rs-clob-client](https://github.com/Polymarket/rs-clob-client)                        | 官方Rust SDK    | Rust   | 官方（低延迟）             |


### 11.2 数据平台


| 平台                                                                 | 用途           | 价格        |
| ------------------------------------------------------------------ | ------------ | --------- |
| [PolyBackTest.com](https://polybacktest.com/)                      | 历史Oracle+订单簿 | $19.90/月  |
| [Tardis.dev](https://tardis.dev/)                                  | BTC tick级数据  | 付费        |
| [Dune Analytics](https://dune.com/rchen8/polymarket)               | 链上聚合数据       | 免费        |
| [Bitquery](https://docs.bitquery.io/docs/examples/polymarket-api/) | GraphQL链上查询  | 免费(7天)/付费 |
| [CoinGlass](https://www.coinglass.com/FundingRate/BTC)             | BTC资金费率      | 免费API     |
| [Coinalyze](https://coinalyze.net/bitcoin/open-interest/)          | BTC未平仓合约     | 免费        |


---

## 12. 安全与合规

### 12.1 爱尔兰运营状态

- **爱尔兰是不受限制的支持国家** ✅
- AWS eu-west-1 (Dublin) IP不被封锁 ✅
- 无需KYC（国际版仅用IP封锁）
- Bot交易无官方限制，API明确支持自动化交易

### 12.2 Ghost Order漏洞（必须防御）

**漏洞机制：** 攻击者通过调用`incrementNonce()`使链上结算时其输家订单失效，实现无风险套利。

**成本：** <$0.10 Polygon gas，周期~50秒。已记录案例：单日$16,427利润。

**防御措施：**

1. 运行 [polymarket-nonce-guard](https://github.com/TheOneWhoBurns/polymarket-nonce-guard) 监控
2. 每笔成交后检查对手方是否在黑名单
3. 发现攻击者地址立即退出仓位

### 12.3 VPN警告

Polymarket ToS明确**禁止VPN绑架地理限制**。使用VPN可能导致资金冻结。确保服务器IP为爱尔兰（AWS eu-west-1）。

### 12.4 受限国家

**完全封锁**：法国、比利时、葡萄牙、匈牙利、瑞士、乌克兰
**交易受限**：意大利、德国、波兰（仅可平仓）
**可用**：英国、西班牙、荷兰、**爱尔兰** ✅

---

## 13. 2026年4月V2升级注意事项

CTF Exchange V2正在部署中，预计2026年4月6日公告后2-3周全面上线。

### 关键变化


| 变化              | 影响              |
| --------------- | --------------- |
| pUSD替代USDC.e    | 需一次性wrap授权      |
| 时间戳+签名替代nonce模型 | 修复Ghost Order漏洞 |
| 费率在撮合时计算（非下单时）  | 影响Bot定价逻辑       |
| EIP-1271支持      | 智能合约钱包可用        |
| 更快更省gas的撮合引擎    | 降低确认延迟          |
| 新合约地址           | SDK必须更新         |


**行动项：**

- 关注官方SDK更新（py-clob-client, rs-clob-client）
- 准备pUSD迁移流程
- V2上线后重新测试所有API调用

---

## 14. 实施路线图

### Phase 1: 数据基础 (第1-2周)

- 部署AWS eu-west-1服务器（当前：18.201.88.231 `/home/ubuntu/new_PolyMarket`）
- 搭建WebSocket数据采集管道（Polymarket RTDS + Binance + CLOB Market）
- 搭建FastAPI Dashboard基础版
- 接入SQLite round/trade记录（验证阶段）
- 切换到TimescaleDB或保留SQLite并增加归档/备份策略
- 运行polyrec开始积累历史数据
- 购买PolyBackTest.com订阅获取历史数据
- LIVE前验证CLOB User Channel真实成交确认链路

### Phase 2: 回测验证 (第2-4周)

- 构建Oracle延迟信号回测（Binance vs Chainlink时间戳）
- 校准逼迫系数B权重
- 验证翻盘概率表（各价格桶 × B值十分位）
- 计算Kelly仓位
- 分时段/周末分别校准

### Phase 3: 模拟交易 (第4-6周)

- Paper trade Tier 1 (Oracle延迟套利) 2周
- Paper trade Tier 2 (尾部翻盘) 2周
- 验证Edge Monitor和Circuit Breaker
- 优化执行延迟

### Phase 4: 实盘上线 (第6-8周)

- 小资金($500)上线Tier 1
- 验证实盘vs回测偏差
- 逐步增加资金
- 加入Tier 2
- 部署Telegram告警和P&L Dashboard

### Phase 5: 优化迭代 (持续)

- 加入做市策略(Tier 3)
- 增加衍生品信号（资金费率、未平仓合约）
- 清算级联检测
- 考虑Rust/Go重写核心路径
- Edge衰减检测自动化

---

## 附录A: 关键数字速查表


| 参数               | 值                                                      |
| ---------------- | ------------------------------------------------------ |
| 区块链              | Polygon PoS, Chain ID 137                              |
| CLOB API         | `https://clob.polymarket.com`                          |
| Gamma API        | `https://gamma-api.polymarket.com`                     |
| RTDS WebSocket   | `wss://ws-live-data.polymarket.com`                    |
| Market WebSocket | `wss://ws-subscriptions-clob.polymarket.com/ws/market` |
| 结算Oracle         | Chainlink Data Streams                                 |
| 窗口边界             | Unix epoch % 300 == 0                                  |
| Slug格式           | `btc-updown-5m-{unix_ts}`                              |
| 平局               | UP赢 (>=)                                               |
| 结算延迟             | ~128秒 (64区块确认)                                         |
| Maker费           | 0%                                                     |
| Taker费 (Crypto)  | 7.2% feeRate, ~1.80% at p=0.50                         |
| Maker返佣          | 20% taker费, 日结USDC                                     |
| 心跳间隔             | 每5秒                                                    |
| 批量下单             | 最多15单/次                                                |
| POST /order限制    | 3,500/10s burst, 36,000/10min                          |
| WS instruments上限 | 500/连接                                                 |
| 爱尔兰→Polymarket延迟 | <2ms                                                   |
| 历史翻盘率 (1c)       | ~0.64%                                                 |
| 过滤翻盘率 (1c)       | ~1.21%                                                 |
| 日交易量             | ~$60M                                                  |
| 每日市场数            | 288                                                    |


## 附录B: 重要信息来源

- [Polymarket Official Docs](https://docs.polymarket.com)
- [Polymarket CLOB API](https://docs.polymarket.com/developers/CLOB/introduction)
- [Polymarket RTDS](https://docs.polymarket.com/developers/RTDS/RTDS-crypto-prices)
- [Polymarket Fees](https://docs.polymarket.com/trading/fees)
- [Polymarket Contract Addresses](https://docs.polymarket.com/resources/contract-addresses)
- [Chainlink Data Streams](https://docs.chain.link/data-streams)
- [py-clob-client GitHub](https://github.com/Polymarket/py-clob-client)
- [oracle-lag-sniper GitHub](https://github.com/JonathanPetersonn/oracle-lag-sniper)
- [polymarket-nonce-guard GitHub](https://github.com/TheOneWhoBurns/polymarket-nonce-guard)
- [PolyBackTest.com](https://polybacktest.com/)
- [Tardis.dev](https://tardis.dev/)
- [Medium: Unlocking Edges in 5-Min Markets](https://medium.com/@benjamin.bigdev/unlocking-edges-in-polymarkets-5-minute-crypto-markets-last-second-dynamics-bot-strategies-and-db8efcb5c196)
- [Medium: AI-Augmented Arbitrage](https://medium.com/@gwrx2005/ai-augmented-arbitrage-in-short-duration-prediction-markets-live-trading-analysis-of-polymarkets-8ce1b8c5f362)
- [The Block: Chainlink Integration](https://www.theblock.co/post/370444/polymarket-turns-to-chainlink-oracles-for-resolution-of-price-focused-bets)
- [Finance Magnates: Dynamic Fees](https://www.financemagnates.com/cryptocurrency/polymarket-introduces-dynamic-fees-to-curb-latency-arbitrage-in-short-term-crypto-markets/)
- [Dyutam: $60M Daily Volume](https://dyutam.com/news/polymarket-5-minute-bitcoin-bets-60m-bots-retail/)

