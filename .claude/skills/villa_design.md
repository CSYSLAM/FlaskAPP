# 山庄（别墅）系统设计规则

玩家山庄：改名、镇守副将、演武场训练、百草园种植、好友山庄互动（偷取/祈福）。URL 前缀 `/villa`。

## 一、概述

山庄是玩家的个人领地，包含三大玩法：
- **演武场（训练）**：消耗行动力 + 银两挂机练级，8 小时满收益。
- **百草园（花园）**：种种子收获药品/经验丹，可催熟。
- **社交互动**：访问随机好友山庄，偷菜/偷经验、祈福。

外加山庄改名、设置镇守副将（防御偷取）、活力卡补行动力。所有状态存于 `villa` 表（JSON blob：`training_data`/`garden_data`/`visitor_logs`），行动力每日重置。

## 二、关键文件

| 文件 | 内容 |
|------|------|
| `blueprints/villa.py` | 路由：/、rename、set_defender、remove_defender、use_vitality_card、training、start_training、finish_training、garden、plant、harvest、ripen、friend、steal_plant、steal_training、bless、claim_blessing |
| `services/villa_service.py` | `VillaService`：get_or_create_villa、set_defender、start/finish_training、plant/harvest/ripen、steal_plant/steal_training、bless/claim_blessing、`SEEDS` 字典 |
| `models/villa.py` | `Villa` 模型：字段、get_garden_slots、get_training_cost/exp、get_defense_power、add_visitor_log |
| `data/items.json` | `vitality_card`（活力卡）、`ripening_agent`（催熟剂）、`enhance_gem`（祈福奖励） |

## 三、路由（前缀 /villa）

| 路由 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 山庄主页：训练状态、花园格子、镇守副将、活力卡数量 |
| `/rename` | POST | 改名（name，1–20 字） |
| `/set_defender` | POST | 设镇守副将（lieutenant_id）；无此参则撤下 |
| `/remove_defender` | GET | 撤下镇守副将 |
| `/use_vitality_card` | GET | 用活力卡 +10 行动力 |
| `/training` | GET | 演武场页 |
| `/start_training` | GET | 开始演武 |
| `/finish_training` | GET | 领取演武奖励 |
| `/garden` | GET | 百草园页（按等级过滤可种种子、催熟剂数量） |
| `/plant/<int:plot_index>` | POST | 种植（seed_id） |
| `/harvest/<int:plot_index>` | GET | 收获成熟作物 |
| `/ripen/<int:plot_index>` | GET | 催熟（消耗催熟剂） |
| `/friend` | GET | 随机好友山庄（实为任意其他玩家） |
| `/steal_plant/<int:owner_id>/<int:plot_index>` | GET | 偷摘作物 |
| `/steal_training/<int:owner_id>` | GET | 偷演武经验 |
| `/bless/<int:owner_id>` | GET | 祈福（+50 经验给对方，自己+1 blessing_count） |
| `/claim_blessing` | GET | 领取祈福礼包（blessing_count≥10） |

## 四、核心逻辑 / 设计规则

### 4.1 山庄模型（`models/villa.py`）

- 字段：`owner_id`(唯一)、`name`、`level`(默认1)、`experience`、`action_points`/`max_action_points`(默认120)、`defender_id`、`blessing_count`(默认0)、`training_data`/`garden_data`/`visitor_logs`(JSON)、`last_reset_date`。
- `get_or_create_villa`（villa_service.py:51）：无则建，默认名「{昵称}的山庄」；随后 `_check_daily_reset`。
- `_check_daily_reset`（villa_service.py:62）：`last_reset_date != 今天` → 行动力回满、blessing_count=0、更新日期。
- **等级上限 100**：`_check_level_up`（villa_service.py:469），升级后 `max_action_points = 120 + (level-1)*2`，并补 `min(AP+20, max)`。故山庄行动力上限随等级增长（CLAUDE.md 所述「max 120」为 1 级基准值）。
- 经验升级阈值 `get_exp_to_next_level = 100 + level*50`（models/villa.py:69）。

### 4.2 镇守副将

- `set_defender`（villa_service.py:82）：副将须属于本人且 `is_alive`，写入 `defender_id`。
- `get_defense_power`（models/villa.py:86）：`defender.get_attack() + defender.get_defense()`；无副将/已阵亡返回 0。此值决定好友偷取时被抓概率。

### 4.3 演武场（训练）

- `TRAINING_DURATION = 8*3600`（villa_service.py:48）。
- `start_training`（villa_service.py:105）：需 `action_points >= 5`；银两 = `get_training_cost()` = `level*500 + 10000`（models/villa.py:79）；记录开始等级；8 小时后可领。
- `finish_training`（villa_service.py:129）：
  - 不足 2 小时 → 无奖励取消；
  - `hours = min(8, elapsed/3600)`；不足 8 小时经验 = `get_training_exp(hours) * hours/16`，满 8 小时 = `get_training_exp(8)`；
  - `get_training_exp(hours) = (level*500 + 1000) * hours`（models/villa.py:81）；
  - 山庄经验 = `hours*10`，触发升级。

### 4.4 百草园（花园）

**格子数**：`get_garden_slots = 3 + (level-1)//5`（models/villa.py:73，即 1级3格，每5级+1）。

**SEEDS 字典**（villa_service.py:12，21 种，公开别名 `SEEDS`）：
- 旧种子：`seed_herb`/`seed_flower`/`seed_ginseng`，收获走 `HARVEST_ITEMS` 映射（herb→potion_heal，flower→flower_rose，ginseng→ginseng）。
- 新种子：`seed_jinchuangyao`…`seed_qinglinglu`（直接存 item_id 于 `harvest` 字段）、经验丹 `exp_seed`/`seed_big_exp`。
- 每种子字段：`name`、`grow_time`(秒)、`harvest`/`harvest_name`、`count`、`ap_cost`(默认2)、`min_level`(默认1)。

**种植规则**（`plant_seed` villa_service.py:217）：
- 校验种子在 SEEDS；扣 `ap_cost` 行动力；
- 等级须 ≥ `min_level`（不足提示「需要百草园N级」）；
- 格子编号须在 `[0, slots)`；格子状态须为 `empty` 或 `harvested`；
- 背包须有该种子（扣 1）。写入 `garden_data[str(i)] = {status:'growing', seed_id, start_time}`。

**成熟判定**（`get_garden_status` villa_service.py:180）：`elapsed >= grow_time` 自动把状态置为 `ready`（写入 `ready_count`）。

**收获**（`harvest_plot` villa_service.py:263）：`harvest_id = HARVEST_ITEMS.get(harvest_key, harvest_key)` —— 新种子用 `harvest` 原值（已是 item_id），旧种子走映射；加物品、+5 山庄经验、格子清空。

**催熟**（`ripen_plot` villa_service.py:292）：须格子 `growing`，消耗 1 个 `ripening_agent`（催熟剂，`is_usable:false` 仅此处用），直接置 `ready`。对应 CLAUDE.md `is_usable:false` 物品规则。

### 4.5 好友山庄互动

- `get_random_friend_villa`（villa_service.py:323）：从**所有其他玩家**随机取 1 人（非真正的「好友列表」），无 villa 则建。
- **偷菜** `steal_plant`（villa_service.py:340）：须 `action_points>=5`；目标格子须 `ready`；被抓率 `catch_rate = min(0.8, defense_power/200)`；被抓罚 `level*100+500` 银两（转给目标）；成功偷 1 个（即便 count 更多），扣 5 行动力，记访客日志。
- **偷演武** `steal_training`（villa_service.py:387）：目标须演武中且 ≥2 小时；同样被抓率与罚款；成功偷 `full_exp*0.2`（20%）经验，扣 5 行动力。
- **祈福** `bless_villa`（villa_service.py:431）：消耗 100 银两；目标 `blessing_count`+1（满 10 停止）；祈福者+50 经验。
- **领礼包** `claim_blessing_reward`（villa_service.py:449）：`blessing_count>=10` → 得 1000 银两、1 元宝、1 `enhance_gem`，计数清零。

### 4.6 活力卡补行动力

`use_vitality_card`（villa.py:71）：行动力满则提示；须背包有 `vitality_card`，扣 1，行动力 `min(max, AP+10)`。每次固定 +10。

## 五、数据文件 / 配置

- `services/villa_service.py:12` `SEEDS` / `HARVEST_ITEMS`（硬编码，非 data/*.json）。
- `data/items.json`：`vitality_card`、`ripening_agent`、`enhance_gem`、`seed_*`（百草园种子，其中部分可在医药铺购买，见 medicine_design.md）。

## 六、注意事项 / 坑

- 山庄行动力 `max_action_points` 随等级增长（120 起，每级 +2），与 CLAUDE.md 概括的「max 120」略有出入（120 为 1 级值）。
- `get_random_friend_villa` 是**全服随机玩家**，并非社交好友列表。
- 偷菜只偷 1 个（代码硬编码 `min(1, count)`），即便种子 count>1。
- 被抓罚款在玩家与镇守方之间直接转账（`player.gold` ↔ `target.gold`），无银两上限保护（最低 0）。
- SEEDS 是代码内常量，新增种子需改 `villa_service.py`（无 data 文件）。

## 七、相关文档

- `CLAUDE.md` →「Garden (百草园) System」与「Item Usage Rules」（催熟剂/活力卡 `is_usable:false`）
- `.claude/skills/equipment_design.md` → 祈福奖励 `enhance_gem` 用于装备强化
- `.claude/skills/medicine_design.md` → 百草园种子可在医药铺购买
