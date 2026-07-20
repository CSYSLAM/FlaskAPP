# 失物招领与拍卖行系统设计规则

丢失物品托管（赎回）+ 拍卖行（竞价）。蓝图注册前缀 `/lost_found`。

## 一、概述

`lost_found` 模块提供两个界面的视图与操作：
- **我的失物（holding）**：玩家取回自己丢失的物品，需消耗赎金券。
- **拍卖行（auction）**：对所有玩家开放的竞价物品，可出价。

数据模型为 `LostItem`（`lost_items` 表，models/player.py:949），含 `stage`（holding/auction 等）、`lost_at`、`auction_started_at`、`current_bid`/`current_bidder_id` 字段。

> ⚠️ **重要现状（已对照代码核实）**：本模块**仅有视图与赎回/竞价操作**，代码中**不存在**：创建 `LostItem` 记录的逻辑（全仓 grep 无 `LostItem(` 实例化）、holding→auction 的流转逻辑、以及按 30/7/37 天清理的定时任务。下列「生命周期」仅为列表页按时间差**展示**出来的倒计时，并未被任何代码强制执行或驱动状态切换。详见第六节。

## 二、关键文件

| 文件 | 内容 |
|------|------|
| `blueprints/lost_found.py` | 路由：lost_found（/）、redeem（/redeem/<id>）、bid（/bid/<id>） |
| `models/player.py` | `LostItem` 模型（line 949，表 `lost_items`） |
| `services/data_service.py` | `get_item`、`get_inventory`、`get_inventory_item`、`add_item_to_inventory`、`remove_item_from_inventory`、`get_backpack_used_capacity` |
| `data/items.json` | `redemption_ticket`（赎金券） |

## 三、路由（前缀 /lost_found）

> 蓝图 `lost_found_bp` 本身无 `url_prefix`（lost_found.py:8），由 `app.py:255` 注册为 `/lost_found`。

| 路由 | 方法 | 说明 |
|------|------|------|
| `/lost_found/` | GET | 列表：我的失物（holding）+ 拍卖行（auction） |
| `/lost_found/redeem/<int:item_id>` | POST | 赎回归还物品（须赎金券） |
| `/lost_found/bid/<int:item_id>` | POST | 拍卖行出价 |

## 四、核心逻辑 / 设计规则

### 4.1 列表 `lost_found`（lost_found.py:11）

- **holding**：`LostItem.query.filter_by(player_id, stage='holding')`；`days_left = 30 - (now - lost_at).days`，仅 `days_left > 0` 展示（lost_found.py:28）。
- **auction**：`LostItem.query.filter_by(stage='auction')`；`days_left = 7 - (now - auction_started_at).days`，仅 >0 展示（lost_found.py:45）。
- 物品名由 `DataService.get_item(item_id)` 取得。

### 4.2 赎回 `redeem`（lost_found.py:63）

- 仅限 `stage='holding'` 且归属当前玩家。
- **必须背包有 `redemption_ticket`（赎金券）≥1**，否则提示「需要赎金券才能取回物品」（lost_found.py:78）。
- 背包容量校验：`item_def.get('capacity', 0.5) * quantity` 累加，超出 `player.backpack_capacity` 则失败。
- 消耗 1 赎金券，`add_item_to_inventory(item_id, quantity, is_bound=原is_bound)`，**删除该 LostItem 记录**（lost_found.py:96-104）。

### 4.3 竞价 `bid`（lost_found.py:110）

- 仅限 `stage='auction'`。
- `bid_amount > 0` 且 `> current_bid`（不高于当前价报错）。
- 银两不足报错；出价前若有旧最高出价者，先**退款** `prev_bidder.gold += current_bid`（lost_found.py:134-137）。
- 扣当前出价者银两，更新 `current_bid`/`current_bidder_id`（lost_found.py:140-142）。

## 五、数据模型

`LostItem`（models/player.py:949）：

| 字段 | 类型 | 说明 |
|------|------|------|
| player_id | FK players | 失主 |
| item_id | String(64) | 物品 ID |
| quantity | Integer | 数量（默认1） |
| is_bound | Boolean | 是否绑定 |
| lost_at | DateTime(not null) | 丢失时间 |
| stage | String(20) | 默认 'holding'；注释枚举 holding/auction/claimed/expired |
| current_bid | Integer | 拍卖当前价（默认0） |
| current_bidder_id | FK players(null) | 当前最高出价者 |
| auction_started_at | DateTime(null) | 进入拍卖的时间 |

## 六、注意事项 / 坑

- **生命周期未实现（关键）**：prompt 所述「30 天赎回 + 7 天拍卖 + 37 天删除」在代码中**均不存在对应机制**。30/7 仅出现在列表页的倒计时显示（`30 - (now-lost_at).days`、`7 - (now-auction_started_at).days`），但没有任何代码创建 `LostItem`、把 holding 转 auction、或在 37 天后删除。换言之，当前 `lost_items` 表若无外部/手动写入则始终为空，赎回/竞价界面不会出现任何物品。
- **赎金券来源不在本模块**：`redemption_ticket` 仅在赎回时被消耗，代码中未出现其发放逻辑（应定义在 `data/items.json`，由其它途径产出）。
- `redeem` 用 POST，`bid` 用 POST；列表为 GET，无创建/删除物品的写操作入口。
- 赎回后物品 `is_bound` 沿用原失物记录值，可能恢复为绑定态。
- `days_left` 用 `.days` 取整，临界日（如正好满 30 天）会展示为 0 被过滤掉。

## 七、相关文档

- `.claude/skills/warehouse_and_drop_rules.md` → 物品掉落/背包容量/绑定规则（赎回容量校验同源）
- `CLAUDE.md` →「Blueprint URL Prefixes（lost_found）」
