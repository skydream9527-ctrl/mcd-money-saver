# 麦门省钱助手（mcd-money-saver）

> 麦当劳程序员节创意开发大赛参赛作品 · **非麦当劳官方产品**

「麦门省钱助手」是一个面向麦当劳中国用户的 **Skill / CLI 省钱顾问**：结合优惠券、积分商城兑换与菜单算价，帮你在下单前找到更省钱的组合策略。

本项目通过麦当劳中国官方 MCP（Model Context Protocol）服务 [`https://mcp.mcd.cn`](https://mcp.mcd.cn) 调用只读/查询类工具（查券、查分、查店、查餐、算价等），**默认流程不会调用下单或抽奖类工具**。

---

## 目标用户

- 经常点麦当劳、想最大化用券与积分的消费者
- 希望在 Agent / IDE 中嵌入「点餐前比价」能力的开发者
- 参加麦当劳中国开发者创新挑战、学习 MCP 集成的程序员

---

## 功能亮点

| 能力 | 说明 |
|------|------|
| 我的优惠券 | `query-my-coupons` |
| 门店可用券 | `query-store-coupons` |
| 麦麦省可领券 | `available-coupons` + `auto-bind-coupons`（可选一键领券） |
| 积分账户 | `query-my-account` |
| 积分换券 | `mall-points-products` / `mall-product-detail` |
| 选门店 | `query-nearby-stores` / `delivery-query-stores` |
| 菜单套餐 | `query-meals` / `query-meal-detail` |
| **核心比价** | `calculate-price`（商品列表 + 优惠券算价） |
| 活动日历 | `campaign-calendar` + `now-time-info` |

无 Token 时自动进入 **演示/Mock 模式**（样例数据均标注为示例），便于本地体验与评审。

---

## 环境要求

- Python 3.10+
- 大陆网络可访问 `https://mcp.mcd.cn`
- MCP Token（从 [mcp.mcd.cn 控制台](https://mcp.mcd.cn) 获取）

---

## 快速安装

```bash
cd mcd-money-saver
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -e .            # 可选：支持 python -m mcd_money_saver
```

配置 Token（**切勿写入仓库文件**）：

```bash
export MCD_MCP_TOKEN="你的令牌"
# 可选：覆盖服务地址
export MCD_MCP_URL="https://mcp.mcd.cn"
```

或参考 `mcp-config.example.json`，在本地 MCP 客户端中使用环境变量占位符。

---

## 使用方式

### CLI

```bash
# 查看帮助
python -m mcd_money_saver --help
# 或
python main.py --help

# 演示模式（无 Token 也可跑通）
python main.py plan --items "巨无霸套餐,薯条" --budget 50 --demo

# 真实 MCP（需 MCD_MCP_TOKEN）
python main.py plan --items "麦辣鸡腿堡套餐" --city 上海
python main.py tools          # 列出服务端 tools/list
python main.py coupons        # 查询我的券 / 可领券
python main.py points         # 积分与商城可兑换
```

### 作为 Skill

见根目录 [`SKILL.md`](./SKILL.md)：描述何时启用「麦门省钱助手」、推荐工具顺序，以及**禁止默认调用**的下单类工具。

### 作为库

```python
from mcd_money_saver.money_saver import MoneySaver
from mcd_money_saver.mcp_client import McdMcpClient

client = McdMcpClient.from_env()  # 读 MCD_MCP_TOKEN；缺失则 mock
saver = MoneySaver(client)
report = saver.plan_order(items=["巨无霸套餐"], budget=60)
print(report.to_text())
```

---

---

## 实时样例①：上海黄浦 · 单店算价（到店自取）

> 数据来自 MCP 只读调用（`query-*` + `calculate-price`），**未下单**。券码已脱敏；价格可能随时变化；**非麦当劳官方**。

| 项 | 内容 |
|----|------|
| 门店 | 麦当劳上海黄浦华旭国际大厦餐厅 |
| 地址 | 西藏中路336号 |
| storeCode | `1450713` |
| 餐品 | 巨无霸三件套 · productCode `9900005466` · 菜单约 **¥36.5** |
| 积分（示例） | 可用 **95.2** 麦享会积分 |
| 可用券 | 中薯条买一送一、王牌小食拼（约 **2026-10-16** 到期） |
| 渠道 | 到店自取（`beType=1` / `orderType=1`） |

### 价格表（`calculate-price`）

| 组合 | 应付 | 说明 |
|------|------|------|
| 仅套餐 | **¥36.50** | 无券 |
| 套餐 + 中薯条买一送一 | **¥50.00** | 相对原价 ¥63.50 节省 **¥13.50** |
| 套餐 + 王牌小食拼 | **¥52.40** | 约节省 ¥6.10 |
| 两张券同单 | ❌ 失败 | 暂不支持多张券使用 |
| 套餐商品直接挂券 | ❌ 失败 | 促销规则不支持该商品 |

完整脱敏 JSON：[`examples/shanghai_live_compare.json`](./examples/shanghai_live_compare.json)

---

## 实时样例②：南京鼓楼一带 · 多门店同品比价

> 搜索中心约「南京市鼓楼区中山路 / 湖南路 / 新街口北侧」；`query-nearby-stores`（`beType=1`）取多家门店，对每店 `query-store-coupons` + `query-meals`，锁定同一兴趣餐 **巨无霸三件套**（`9900005466`），再 `calculate-price` 对比无券 vs 最优单券。采集时间约 **2026-10-15 21:50（北京时间）**。只读，未调用下单/领券/抽奖。

### 四店对比（到店自取）

| 门店 | storeCode | 距搜索点 | 仅套餐 | +中薯条买一送一 | +王牌小食拼 |
|------|-----------|----------|--------|----------------|-------------|
| 南京新百餐厅 | `1990346` | ~182m | ¥37.50 | ¥51.00 | ¥53.40 |
| 南京湖南路吾悦广场餐厅 | `1990256` | ~260m | ¥37.50 | ¥51.00 | ¥53.40 |
| **南京凤凰广场餐厅** | `1990260` | ~425m | **¥36.50** | **¥50.00** | **¥52.40** |
| **南京凯瑟琳广场餐厅** | `1990563` | ~501m | **¥36.50** | **¥50.00** | **¥52.40** |

凤凰广场店「套餐+中薯条买一送一」明细：应付 **¥50.00**，原价合计 ¥63.50，节省 **¥13.50**。

### 结论

- **同品更便宜的店**：凤凰广场、凯瑟琳广场（套餐 **¥36.50**，比新百/吾悦广场低 **¥1**）。
- **最优单券组合**：各店均为「套餐 + 中薯条买一送一」；两店最低应付 **¥50.00**。
- **限制**：两张券同单失败（`暂不支持多张券使用`）；把券直接挂在套餐 SKU 上失败（`促销规则不支持该商品`）——券需挂在对应促销商品上。
- 券名可用：中薯条买一送一、王牌小食拼（约 2026-10-16 到期）。

脱敏 JSON：[`examples/nanjing_gulou_multi_store.json`](./examples/nanjing_gulou_multi_store.json)


## 项目结构

```
mcd-money-saver/
├── README.md
├── CONTEST_DECLARATION.md   # 参赛声明（请勿改动）
├── MCP_INTEGRATION.md       # MCP 工具与业务流程说明
├── SKILL.md                 # Skill 定义
├── mcp-config.example.json  # 脱敏 MCP 配置示例
├── requirements.txt
├── main.py                  # 入口
├── examples/
│   ├── sample_plan.json
│   ├── shanghai_live_compare.json   # 上海实时比价样例（脱敏）
│   └── nanjing_gulou_multi_store.json  # 南京鼓楼多店比价（脱敏）
└── src/mcd_money_saver/
    ├── __init__.py
    ├── __main__.py
    ├── mcp_client.py        # Streamable HTTP MCP 客户端
    ├── money_saver.py       # 省钱策略核心逻辑
    └── cli.py               # 命令行
```

---

## 安全与合规

- 不硬编码 Token / 密钥；仅使用 `MCD_MCP_TOKEN` 等环境变量
- 默认省钱顾问为**只读建议**，不调用 `create-order` / `mall-create-order` / `draw-lottery`
- 输出价格与供应状态以麦当劳官方实时结果为准；本工具仅供参考
- 详见 [`CONTEST_DECLARATION.md`](./CONTEST_DECLARATION.md)

---

## 免责声明

本项目为**麦当劳程序员节创意开发大赛**参赛作品，由参赛者独立开发，**非麦当劳官方产品**。餐品信息、价格、优惠券及门店供应以麦当劳 App / 小程序等官方渠道为准。

---

## License

仅用于大赛展示与学习交流。使用麦当劳 MCP 须遵守官方控制台与活动规则。
