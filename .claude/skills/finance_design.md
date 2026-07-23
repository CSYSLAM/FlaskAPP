# 财经·股市（金珠理财）系统设计规则

`/activity/finance/*` 下的股票模拟市场 + 劫匪系统。活动入口与每日任务见 `activity_design.md`，二者共享 `/activity` 蓝图。

## 一、概述

- **URL 前缀**：`/activity/finance`（路由写在 `blueprints/activity.py`，蓝图前缀 `/activity`，服务 `services/finance_service.py`）。
- **服务类**：`FinanceService`（`finance_service.py:491`），行情/统计/劫匪以类级缓存运行，并通过 `finance_state` 表持久化；启动后台维护线程每 60 秒推进跨天、tick、委托撮合和落库。
- **关键性质**：
  - 股价/当日统计/劫匪状态落库到 `finance_state`，后台维护线程每 60 秒推进跨天、tick 和委托撮合。
  - 玩家持仓存于 `player.finance_data`（JSON Blob）的 `holdings`/`realized_profit`/`frozen` 等字段（**持久化**）。
- **货币**：全部用 **金珠 `jinzu`**（非元宝）。

## 二、关键文件

| 文件 | 内容 |
|------|------|
| `blueprints/activity.py` | `/activity/finance*` 全部路由（:303~:491） |
| `services/finance_service.py` | `FinanceService`：时段、tick、撮合、买卖、委托单、劫匪、人气 |
| `data/finance_stocks.json` | 9 只股票定义（stock_id/name/city/npc_keyword/area_id/base_price/total_shares） |
| `app.py:212` | `FinanceService.register_bandit_monster(DataService.get_monsters())` 注入劫匪到怪物缓存 |
| `app.py:243` | `activity_bp` 注册（无额外前缀） |
| `services/battle_service.py:443` | 场景显示 `get_bandit_at_location` |
| `services/battle_service.py:1210` | 击败劫匪调 `record_bandit_kill` |
| `blueprints/game.py:107, :347` | 场景查劫匪 / NPC 对话调 `record_npc_visit` |
| `templates/finance.html` 等 | `finance_stock.html` / `finance_orders.html` / `finance_holdings.html` / `finance_rank.html` |

## 三、路由（`/activity/finance` 前缀）

| 路由 | 方法 | 说明 |
|------|------|------|
| `/activity/finance` | GET | 行情总览、持仓汇总、劫匪情报、时段、倒计时 |
| `/activity/finance/rules` | GET | 规则说明页 |
| `/activity/finance/stock/<stock_id>` | GET | 单只股票详情（含持仓/可交易态/是否显示价） |
| `/activity/finance/buy` | POST | 即时买入（表单 `stock_id`/`shares`） |
| `/activity/finance/sell` | POST | 即时卖出（表单 `stock_id`/`shares`） |
| `/activity/finance/order` | POST | 提交限价委托单（`side`/`shares`/`limit_price`） |
| `/activity/finance/orders` | GET | 我的委托单列表 |
| `/activity/finance/order/cancel/<order_id>` | POST | 撤销未成交委托单 |
| `/activity/finance/holdings` | GET | 我的持仓明细 |
| `/activity/finance/rank/finance` | GET | 股神榜（按总盈亏排序 Top30） |
| `/activity/finance/rank/bandit` | GET | 义士榜（按各城市击杀劫匪数排序） |

## 四、核心逻辑/设计规则

### 1. 交易时段（`finance_service.py:7`~`:17`，`get_market_phase` `:572`）

| 时段 | 时间 | 股价显示 | 即时买卖 | 委托单 |
|------|------|---------|---------|--------|
| `pre_open` 盘前 | 00:00–09:00 | 不显示 | 不可 | 可挂 |
| `auction` 集合竞价 | 09:00–09:30 | 不显示 | 不可 | 可挂，**按开盘价(=昨收)撮合** |
| `open` 连续交易 | 09:30–18:00 | 显示实时价 | 可 | 可挂，按实时价逐 tick 撮合 |
| `closed` 盘后 | 18:00–24:00 | 不显示 | 不可 | 可挂 |

- `is_tradable()` `:589` = 仅 `open`；`shows_price()` `:599` = 仅 `open`（盘前/竞价不显示股价）。
- `_match_price(s)` `:604`：竞价段用 `open_price`（昨收），连续段用实时 `price`。

### 2. 股价模拟（`_settle_day_change` `:661` + 50 种 K 线策略）

每股票当日涨跌 = **A 纯随机 + B 人气(排名) + C 劫匪(排名)**，并 clamp 到 `±DAILY_MAX_CHANGE=±10%`（`:20`）。

- **A 纯随机**：开盘一次性 `random.uniform(-0.08, 0.08)`（玩家不可预知）。
- **B 人气排名** / **C 劫匪排名**：调用 `_ranked_change`（`:694`）——按全市场当日 `npc_visits` / `bandit_kills` 排名分配区间：
  - 最高者 ∈ `[RANK_BEST_LO=-0.005, RANK_BEST_HI=+0.01]`
  - 最低者 ∈ `[RANK_WORST_LO=-0.01, RANK_WORST_HI=+0.005]`
  - 中间线性插值。
- **K 线路径**：`_settle_day_change` 随机选 1/50 策略（`:449` `_STRATEGIES`），调用返回 `[(t_ratio, price_ratio), ...]` 路径（首点 (0,0)，末点 (1, final_change)）。`t_ratio∈[0,1]` 为当日时间比例，末点 = 当日累计涨跌。
- **实时 tick**（`_maybe_tick` `:730`）：距上次 ≥ `TICK_INTERVAL=300` 秒（5 分钟）才推进。**盘前/竞价段不刷新股价**；连续段按 `_day_progress`（`:716`，9:00→0、18:00→1）在路径上 `_interp_path` 线性插值出目标价，再叠加 `±TICK_DRIFT/2`（`:21`，±0.5%）抖动，且相邻 tick 差 ≤ ±1%，结果保留两位小数 ≥0.01。每次 tick 后对 `open` 段撮合委托单。

### 3. 即时买卖（`buy` `:866` / `sell` `:909`）

- 仅 `open` 时段可成交（否则提示改用委托单）。
- 买入校验：发行量余量 `total_shares - outstanding` ≥ 股数；花费 `cost=shares*price`，手续费 `fee=cost*FEE_RATE`（`:22`，万五=0.0005），`total=cost+fee`；金珠不足报错。
- 持仓均价计算：`new_avg = (old_shares*old_avg + cost) / new_shares`（买入）；卖出保留原均价（`sell` `:940` 分支）。
- 卖出：收入 `income=shares*price`，净得 `net=income-fee`，金珠增加 `int(round(net))`，已实现盈亏 `realized += shares*price - shares*avg - fee`。
- 每次买卖更新 `s.outstanding`（流通量），并 `db.session.commit()`。

### 4. 委托单系统（`place_order` `:970` / `_match_orders` `:1029` / `_fill_order` `:1054` / `cancel_order` `:1173`）

- **限价单语义**：任何时段可挂（`can_place_order` 恒 True）。买单 `委托价 ≥ 市价` 成交；卖单 `委托价 ≤ 市价` 成交；**按当前撮合价成交，委托价只作为保护价**。买单不得低于市价成交，避免低买高卖套利。
- **预冻结**：买单冻结 `金珠=shares*limit_price*(1+FEE_RATE)`（记 `finance_data['frozen']`）；卖单冻结持仓（`holdings[stock]['shares']` 减、`locked` 加）。
- **撮合触发**：竞价段（按开盘价）+ 每个连续 tick（`_maybe_tick`）。
- **部分成交**：买单受流通量限制，`fill = min(order_shares, available)`，剩余继续挂单，按比例解冻金珠（`_fill_order` `:1054`）。
- **撤销** `cancel_order`：仅 `pending` 可撤，调 `_refund_order`（`:1130`）退回冻结资金/持仓。
- **跨天清空**：`_ensure_day`（`:616`）把 `cls._orders = {}`，未成交委托单隔日作废。

### 5. 人气（NPC 对话计数，`record_npc_visit` `:1209`）

- 玩家点击 NPC 时 `game.py:347` 调用，按 `npc_keyword` 子串匹配股票累加 `npc_visits`。
- **每人每日每股票仅计 1 次**（用 `npc_visitors` set 去重）。
- 该统计直接影响次日 `B 人气` 排名涨跌（见上"股价模拟"）。

### 6. 劫匪系统（`BanditState` `:480` + 相关方法）

- **注册**：`register_bandit_monster`（`:1283`，`app.py:212`）为每只股票的 `city` 生成一个 `bandit_{city}` 怪物，注入怪物缓存（`get_bandit_monster_data` `:1253`：15 级、HP300、掉落银两 50~150/经验80）。
- **出没位置**：`_randomize_bandit_location`（`:641`）随机刷新到该城市 `area_id` 下、非副本场景之一；存 `b.location_id`。
- **场景显示**：`get_bandit_at_location`（`:1330`，`battle_service.py:443`）——当玩家当前场景 = `location_id` 且 `spawned` 时返回 `(monster_id, city, 0)`，击败后消失。
- **击杀结算** `record_bandit_kill`（`:1291`，`battle_service.py:1210`）：
  - 标记 `spawned=False`、`defeated_at=now`、记录 `killer_today`。
  - 该城市 **所有关联股票** 的 `bandit_kills += 1`（如击杀北平劫匪→北平全部股票 +1）。
  - **积分制**：每次 +1 `bandit_points`，满 `BANDIT_POINTS_PER_JINZU=100` 自动兑 1 金珠（即每次约 0.01 金珠），全服广播答谢。
- **复活**：`_check_bandit_respawn`（`:1238`）——`defeated_at` 满 `BANDIT_RESPAWN=300` 秒（5 分钟）后 `spawned=True` 并随机刷新到新场景。
- **榜单/情报**：`get_bandit_status`（`:1343`，前端显示复活倒计时）、`get_city_kill_rank`（`:1381`，义士榜 Top30，按城市击杀数）。
- 阈值：`POP_THRESHOLD=20`（人气满档所需 NPC 访问次数）、`BANDIT_THRESHOLD=10`（劫匪满档所需击杀次数），用于 `pop_factor`/`bandit_factor` 展示（`:807`）。

### 7. 排名（股神榜 / 义士榜）

- `get_player_profit`（`:954`）= 已实现盈亏 + 浮动盈亏（持仓×当前价 − 持仓×均价），用于 `finance/rank/finance`。
- `get_player_summary`（`:841`）= 市值/成本/浮动盈亏/已实现/总成交/冻结/劫匪积分等，`finance` 页与持仓页展示。

## 五、数据文件/配置

- **`data/finance_stocks.json`**：`stocks` 数组，9 只：
  - 北平：客栈(`beiping_inn`，王老板)、钱庄(`beiping_bank`，金掌柜)
  - 下邳：铁匠铺(`xiapi_blacksmith`，铁匠)
  - 汉中：客栈(`hanzhong_inn`，王老板)
  - 柴桑：钱庄(`chaisang_bank`，金掌柜)
  - 洛阳：钱庄(`luoyang_bank`，金掌柜)
  - 建邺：客栈(`jianye_inn`，王老板)
  - 成都：铁匠铺(`chengdu_blacksmith`，铁匠)
  - 许昌：钱庄(`xuchang_bank`，金掌柜)
  - 字段：`stock_id`、`name`、`city`、`npc_keyword`（用于人气匹配）、`area_id`、`base_price`、`total_shares`(均 5000)。
  - **劫匪无独立 JSON**——由 `finance_service.py` 按 `city` 动态生成（见上）。
- **可调常量**（`finance_service.py:18`~`:33`）：`TICK_INTERVAL`/`DAILY_MAX_CHANGE`/`TICK_DRIFT`/`FEE_RATE`/`ORDER_BUY_TOLERANCE`/`POP_THRESHOLD`/`BANDIT_THRESHOLD`/`BANDIT_RESPAWN`/`BANDIT_POINTS_PER_JINZU`/`HISTORY_LEN`(48)。
- **玩家持仓结构**（`player.finance_data`）：
  - `holdings`: `{stock_id: {'shares':int, 'avg_cost':float, 'locked':int(委托冻结)}}`
  - `realized_profit`、`total_traded`、`frozen`、`bandit_points`

## 六、注意事项/坑

- **行情状态已持久化**：股价/当日统计/劫匪位置写入 `finance_state`；pending 委托同步保存在玩家 `finance_data.finance_orders`。重启后恢复行情和委托，后台线程每 60 秒推进跨天和 tick。
- **交易日程固定**：纯按服务器本地时钟判断时段，无周末休市。
- **盘前/竞价不显示股价**：玩家此时看不到实时价，只能挂委托单；竞价段委托单按开盘价撮合。
- **当日涨跌幅 ±10% 硬上限**：`A+B+C` 会被 clamp。
- **买入冻结/卖出冻结**：委托单提交即冻结金珠或持仓；撤销或成交后释放。重复提交/未撤销会持续占用。
- **劫匪积分极微**：每杀 1 次仅 `1/100` 金珠，需满 100 次击杀才兑 1 金珠并广播。
- **人气去重**：同一玩家对同一股票当日只计 1 次 NPC 访问，刷同一 NPC 无效。
- **跨天委托单作废**：未成交的隔夜委托单在 `_ensure_day` 被清空，不会自动滚存。

## 七、相关文档

- `activity_design.md` — 同前缀 `/activity` 下的签到/砸蛋/猜拳/答题/读书/翻牌/幸运币/每日任务（劫匪与每日任务无关）
- `pk_combat_design.md` — VIP 权益 `pk_drop_reduction` 等由 `vip_service.py` 提供，与财经无直接关系
- `vip_design.md` — VIP 与诸侯令（财经页"义士榜/股神榜"独立展示）
- `CLAUDE.md` — Blueprint URL Prefixes（`activity` 前缀）
