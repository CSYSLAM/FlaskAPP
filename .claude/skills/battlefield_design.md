# 战场（Battlefield / 领土战）系统设计规则

战场是**军团领土争夺 PvP** 系统：进入城市、攻击/技能攻击、阵亡/复活、退出、排行榜、城市占领与结算、段位积分。与野外 PK（`pk_combat_design.md`）相互独立。

## 一、概述

前缀 `/battlefield`（blueprint `battlefield`，注册名 `'battlefield'`）。玩家消耗对应段位的**战场令旗**进入某城，与**异国、非同军团**玩家战斗，击杀获得：个人段位荣誉、个人团战积分（`personal_battle_points`）、军团积分（`battle_points`）。占领城市由军团长操作，给全军团成员提供固定属性加成。
城市与段位**硬编码**于 `services/battlefield_service.py:13`（`BATTLEFIELD_CITIES`、`TIER_*`），不在 data/ 或 game_config.json。

## 二、关键文件

| 文件 | 内容 |
|------|------|
| `blueprints/battlefield.py` | 全部战场路由 |
| `services/battlefield_service.py` | `BattlefieldService` + `CityState`（内存态）；`BATTLEFIELD_CITIES`、`TIER_HONOR/POINTS/BONUS/TOKEN/NAME`；进入/攻击/击杀/复活/排行/结算/占领/领土加成 |
| `models/legion.py` | `Legion.occupied_cities`（占领城市，JSON）、`Legion.battle_points`、`LegionMember.personal_battle_points` |
| `models/player.py` | `in_battlefield`、`battlefield_city`、`battlefield_death_time`、`in_pk`、`pk_opponent`、`honor`、`last_attack_time` 等 |
| `services/legion_service.py` | 军团侧 `occupy_city`/`get_claimable_cities` 转发、兑换（见 legion_design.md） |
| `services/player_service.py` | 领土加成 `get_territory_bonuses` 叠加于属性 flat 段（line 142、172、202、228） |

## 三、路由（前缀 `/battlefield`）

| 路由 | 方法 | 说明 |
|------|------|------|
| `/battlefield/` | GET | 战场首页：城市列表、是否开放/可进入 |
| `/battlefield/enter/<city_key>` | GET | 进入城市（消耗对应令旗） |
| `/battlefield/city` | GET | 城内视图（玩家列表/排行/击杀日志/可用技能） |
| `/battlefield/attack/<int:target_id>` | POST | 普通攻击（2 秒冷却） |
| `/battlefield/skill_attack/<int:target_id>/<skill_id>` | POST | 技能攻击（2 秒冷却） |
| `/battlefield/revive` | GET | 复活页（显示剩余复活时间、是否有续命灯） |
| `/battlefield/revive_action` | GET | 使用战场续命灯复活 |
| `/battlefield/death` | GET | 死亡页（超时则强制退出） |
| `/battlefield/exit` | GET | 主动退出战场 |
| `/battlefield/rankings` | GET | 全城排行榜（玩家前 10 / 军团前 5） |

> 城市占领不在本 blueprint，而由军团侧 `/legion/occupy/<city_key>` 转发 `BattlefieldService.occupy_city`（详见 legion_design.md 第 11 条）。

## 四、核心逻辑/设计规则

### 1. 城市与段位（`battlefield_service.py:13`）
- 低级 `basic`（蜀/魏/吴各 3 城，限本国进入）、中级 `mid`（江陵/下邳/汉中，中立）、高级 `high`（洛阳，中立）。
- 段位映射（同一城市三套数值，均随段位 1/2/3）：
  - `TIER_HONOR`：击杀转移荣誉数（basic1/mid2/high3）。
  - `TIER_POINTS`：个人/军团积分（basic1/mid2/high3）。
  - `TIER_BONUS`：占领后给成员的固定加成（basic1/mid2/high3）。
  - `TIER_TOKEN`：进入所需令旗（basic→`battle_flag_1`、mid→`battle_flag_2`、high→`battle_flag_3`）。
  - `TIER_NAME`：低级/中级/高级。

### 2. 时间控制（`TESTING_MODE = True`，battlefield_service.py:59）
- 当前 `is_war_time`/`is_entry_allowed` 恒返回 True；`should_force_exit` 恒返回 False。
- 生产逻辑（TESTING_MODE=False）：仅周六 20:00–20:30 开放；20:30 后强制退出。代码已写好但未启用。

### 3. 进入（`can_enter_city`/`enter_battlefield`，battlefield_service.py:104/125）
- 城市须存在；限本国城须 `player.country` 匹配；不能在其它战斗中。
- 须在开放时间（`is_entry_allowed`）。
- 须持对应段位令旗（`TIER_TOKEN`）≥1，进入即消耗 1 个。
- **必须已加入军团**（`LegionMember` 存在）。否则“需要加入军团才能进入战场”。
- 进入后：`in_battlefield=True`、`battlefield_city`、死亡时间清零、清 PK 态、满血满蓝、加入该城内存 `players` 集合并初始化 `player_scores`。

### 4. 攻击（`can_attack_in_battlefield`/`battlefield_strike`/`battlefield_skill_strike`）
- 条件：双方都在同一战场、异国（`attacker.country != defender.country`）、非同军团、对方未死亡。
- 路由层额外有 **2 秒攻击冷却**（`last_attack_time`，blueprints/battlefield.py:94、122）。
- 普通攻击 `battlefield_strike`（battlefield_service.py:184）：伤害 `max(1, 攻-防)`，暴击 ×1.5（按 `crit_rate`）；闪避按 `dodge_rate`。
- 技能攻击 `battlefield_skill_strike`（battlefield_service.py:222）：按技能 `damage_rate`/`hits`/`mana_cost` 计算，消耗魔法；伤害公式 `int(攻×damage_rate) - 防` 逐段。
- 致死时调用 `_handle_battlefield_kill`。

### 5. 击杀结算（`_handle_battlefield_kill`，battlefield_service.py:280）
- **个人团战积分**：`personal_battle_points += TIER_POINTS[tier]`。
- **荣誉零和转移**：`honor_gained = min(TIER_HONOR[tier], defender.honor)`；攻方 `+honor_gained`、守方 `-honor_gained`（受守方荣誉余额上限）。随后双方 `update_military_rank`。
- **军团积分**：该城 `legion_scores[legion_id] += TIER_POINTS[tier]`（内存）+ `Legion.battle_points += TIER_POINTS[tier]`（持久化）。
- 写入 `player_scores`、`kill_log`（保留最近 20 条）。
- 守方进入死亡态：`battlefield_death_time = time.time()`，清 PK 态。

### 6. 死亡与复活（`can_revive_in_battlefield`/`revive_in_battlefield`，battlefield_service.py:342/349）
- 死亡后 **15 秒**内可复活（`can_revive_in_battlefield`：距死亡时间 ≤15 秒）。
- 复活消耗 1 个 `battle_revive_lamp`（战场续命灯），满血满蓝、清死亡时间。
- 超时未复活：路由 `/death` 调 `force_death_exit` 传送出战场。

### 7. 退出（`exit_battlefield`，battlefield_service.py:152）
- 清 `in_battlefield`/`battlefield_city`/死亡时间/ PK 态，从城内存集合移除。

### 8. 排行（`get_city_rankings`，battlefield_service.py:371）
- 玩家榜前 10（按 `player_scores`）、军团榜前 5（按 `legion_scores`），均只列分数 >0。当前 `rankings` 路由汇总所有城市。

### 9. 占领与结算（`settle_war`/`occupy_city`/`get_claimable_cities`，battlefield_service.py:398/408/432）
- 城内积分最高军团写入 `state.winner_legion_id`（由 `settle_war` 计算）。
- `occupy_city`：仅**军团长**；须 `winner_legion_id == 本军团`；写入 `Legion.occupied_cities`（去重）。
- `get_territory_bonuses`（battlefield_service.py:446）：每座已占城给成员 attack/defense/max_health/max_mana 各 +`TIER_BONUS`（固定值，flat 段叠加）。
- `reset_territories`：清空所有军团占领（未接路由）。

## 五、数据文件/配置

- 城市/段位完全硬编码于 `services/battlefield_service.py:13-40`，**不在 data/ 或 game_config.json**。
- 消耗物：`battle_flag_1/2/3`（战场令旗，按段位）、`battle_revive_lamp`（战场续命灯）。
- 积分兑换的产出物品（令旗、强效秘药、鸳鸯剑图纸等）见 `legion_service.py` 的 `BATTLE_EXCHANGE` 与 `data/items.json`。
- 占领结果持久化于 `Legion.occupied_cities_raw`（JSON），积分持久化于 `Legion.battle_points` / `LegionMember.personal_battle_points`；但**内存态 `CityState`（含 `winner_legion_id`、`legion_scores`）随服务器重启清空**。

## 六、注意事项/坑

- **占领链路未闭合**：`settle_war()` 全代码**从未被调用**（`should_force_exit` 仅退出不结算），故 `state.winner_legion_id` 永远为空，`get_claimable_cities` 恒空、`/legion/occupy` 恒报“未赢得该城市”。当前仅能在战斗中累积 `personal_battle_points`/`battle_points`，但**无法实际占领城市**。若启用领土，须接入 `settle_war` 调用（建议在战争结束时触发）。
- 战场属性加成（领土）是**固定值**叠加在 flat 段；而个人攻击里 `party_rate`/`social_rate`/`spouse_rate`/`vip_rate` 是乘区比率——叠加位置不同（player_service.py:146）。
- `in_battlefield` 与 `in_pk` 互相排斥：进战场会清 PK 态；战场攻击不受野外 PK 的 25 级/安全区/频率限制约束——**战场是独立 PvP 系统，不适用 `pk_combat_design.md` 的荣誉分档/银两转移/免战/仇敌规则**。
- 测试模式 `TESTING_MODE=True` 下全天开放且无强制退出；生产逻辑（周六 20:00-20:30）已写好但未启用。

## 七、相关文档

- [legion_design.md](legion_design.md) — 军团（占领城市的操作入口、`battle_points` 来源与兑换、领土加成互通）
- [pk_combat_design.md](pk_combat_design.md) — 野战 PK（**独立**系统；其荣誉分档/银两/免战/仇敌规则不适用于战场）
- [CLAUDE.md](../../CLAUDE.md) — “Blueprint URL Prefixes” 中 `battlefield`/`legion` 前缀；“Item Usage Rules” 中 `battle_revive_lamp`/`battle_flag_*`/`battle_challenge_token` 等
