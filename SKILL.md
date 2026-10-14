# Skill：麦门省钱助手

## 名称

麦门省钱助手（mcd-money-saver）

## 何时使用

当用户希望：

- 点麦当劳前比较「用哪张券 / 是否值得用积分换券」更便宜
- 根据预算或想吃的餐品，给出优惠组合建议
- 查看门店可用券、麦麦省可领券、活动日历与当前算价

时启用本 Skill，并连接麦当劳中国 MCP（`https://mcp.mcd.cn`）。

## 鉴权

- 环境变量：`MCD_MCP_TOKEN`（Bearer Token）
- 无 Token 时使用本地 Demo/Mock 数据，并明确标注「示例」

## 推荐工具顺序

1. `now-time-info` — 当前时间
2. `campaign-calendar` — 活动日历
3. `query-nearby-stores` 或 `delivery-query-stores` — 选门店
4. `query-meals` / `query-meal-detail` — 菜单与套餐
5. `query-my-coupons` / `query-store-coupons` / `available-coupons` — 券池
6. （可选）`auto-bind-coupons` — 一键领券后再比价
7. `query-my-account` / `mall-points-products` / `mall-product-detail` — 积分能否换券
8. `calculate-price` — **核心**：多组券组合算价并选最优

## 禁止（默认流程）

不要调用：

- `create-order`
- `mall-create-order`
- `draw-lottery`

本 Skill 是**只读省钱顾问**；下单请引导用户使用麦当劳官方渠道。

## 输出要求

- 给出：原价估算、最优券后价、预估节省、使用的券/积分策略说明
- 标明数据来源（实时 MCP / 演示示例）
- 提醒：价格与供应以官方 App/小程序实时结果为准；非官方产品

## 本地运行

```bash
export MCD_MCP_TOKEN=your_token   # 可选
python main.py plan --items "巨无霸套餐" --budget 50
```
