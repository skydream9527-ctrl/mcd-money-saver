# MCP 集成说明 · 麦门省钱助手

## 服务概览

| 项 | 值 |
|----|-----|
| MCP Server | `https://mcp.mcd.cn` |
| 传输 | Streamable HTTP（MCP streamable-http） |
| 鉴权 | `Authorization: Bearer ${MCD_MCP_TOKEN}` |
| Token 来源 | [mcp.mcd.cn 控制台](https://mcp.mcd.cn)（大陆网络） |

本 Skill **默认只做省钱建议**（查券、查分、查店、查餐、算价），不执行下单或抽奖。

---

## 省钱流程优先工具

以下名称来自麦当劳中国 MCP 官方能力；客户端启动后仍会调用 `tools/list` 做能力探测，若某工具暂不可用则跳过并在报告中说明。

### 1. 优惠券

| 工具名 | 中文 | 在省钱流程中的作用 |
|--------|------|-------------------|
| `query-my-coupons` | 我的优惠券 | 拿到账户已有券，作为比价候选 |
| `query-store-coupons` | 当前门店可用优惠券 | 按门店过滤真正可用的券 |
| `available-coupons` | 麦麦省可领券列表 | 发现尚未领取、可立即使用的券 |
| `auto-bind-coupons` | 一键领券 | 可选；领完后再算价（仍不落单） |

### 2. 积分与积分商城

| 工具名 | 中文 | 作用 |
|--------|------|------|
| `query-my-account` | 积分账户 | 余额、等级等，判断能否换券 |
| `mall-points-products` | 积分商城商品列表 | 找出可用积分兑换的优惠券类商品 |
| `mall-product-detail` | 积分商城商品详情 | 确认兑换成本与券面额 |

> 默认流程**只查询**商城，不调用 `mall-create-order`。若发现「积分换券更划算」，在报告中提示用户自行在官方渠道兑换。

### 3. 门店

| 工具名 | 中文 | 作用 |
|--------|------|------|
| `query-nearby-stores` | 附近门店 | 到店场景选店 |
| `delivery-query-stores` | 外卖可配送门店 | 外卖场景选店（影响门店可用券） |

### 4. 菜单与算价（核心）

| 工具名 | 中文 | 作用 |
|--------|------|------|
| `query-meals` | 餐品/套餐列表 | 按关键词匹配想点的商品 |
| `query-meal-detail` | 餐品详情 | 规格、价格、可选项 |
| `calculate-price` | 算价 | **核心比价**：商品列表 + 优惠券组合 → 应付金额 |

### 5. 活动与时间

| 工具名 | 中文 | 作用 |
|--------|------|------|
| `campaign-calendar` | 活动日历 | 当前/即将开始的活动，辅助判断是否等待更优活动 |
| `now-time-info` | 当前时间 | 对齐活动与券的生效时段 |

---

## 默认禁止调用的工具

省钱顾问 Skill **不会**在默认流程中调用：

- `create-order` — 创建订单
- `mall-create-order` — 积分商城下单
- `draw-lottery` — 抽奖

如需下单，应引导用户到麦当劳官方 App / 小程序，或由用户明确授权的独立流程处理。

---

## 推荐调用流程（业务价值）

```
1. now-time-info          → 对齐活动时段
2. campaign-calendar      → 是否有限时更优活动
3. query-nearby-stores / delivery-query-stores
                          → 选定门店（券与库存依赖门店）
4. query-meals + query-meal-detail
                          → 锁定目标商品/套餐
5. query-my-coupons
   + query-store-coupons
   + available-coupons
   (+ 可选 auto-bind-coupons)
                          → 券池最大化
6. query-my-account
   + mall-points-products / mall-product-detail
                          → 积分能否换到更优券
7. calculate-price（多组券组合）
                          → 输出「原价 / 最优券后价 / 预估节省」
8. 生成可读省钱报告（不落单）
```

**业务价值**：把分散的「券、分、店、餐、活动」收成一条 Agent 可执行的比价链路，降低用户漏用券、错过积分换券的成本，同时保持只读建议、降低误下单风险。

---

## 客户端实现要点

- 传输：向 MCP 端点发送 JSON-RPC（`initialize`、`tools/list`、`tools/call`），支持 streamable HTTP 响应（含 SSE 风格分块时按行解析 `data:`）。
- 鉴权：每个请求带 `Authorization: Bearer <token>`；Token 仅来自环境变量 `MCD_MCP_TOKEN`。
- 容错：无 Token 或网络失败 → 进入标注清晰的 **Demo/Mock** 模式，使用本地示例数据演示同一套流程。
- 工具名以服务端 `tools/list` 为准；代码内维护「期望工具别名表」，匹配官方名后再调用。

详见源码：`src/mcd_money_saver/mcp_client.py`、`money_saver.py`。

---

## 配置示例

见仓库根目录 `mcp-config.example.json`（仅占位符，无真实密钥）。
