# 战场（Battlefield / 领土战）系统设计规则

战场是**军团领土争夺 PvP** 系统：进入城市、攻击/技能攻击、阵亡/复活、退出、排行榜、城市占领与结算、段位积分。与野外 PK（`pk_combat_design.md`）相互独立。

## 一、概述

前缀 `/battlefield`（blueprint `battlefield`，注册名 `'battlefield'`）。玩家消耗对应段位的**战场令旗**进入某城，与**异国、非同军团**玩家战斗，击杀获得：个人团战积分（`personal_battle_points`）、军团积分（`battle_points`）。**战场击杀不转移荣誉/银两/经验**（有意设计，与野外 PK 的荣誉分档无关）。占领城市由军团长操作，给全军团成员提供固定属性加成。
城市与段位**硬编码**于 `services/battlefield_service.py:13`（`BATTLEFIELD_CITIES`、`TIER_*`），不在 data/ 或 game_config.json。

## 二、关键文件

| 文件 | 内容 |
|------|------|
| `blueprints/battlefield.py` | 全部战场路由 |
| `services/battlefield_service.py` | `BattlefieldService` + `CityState`（内存态）；`BATTLEFIELD_CITIES`、`TIER_POINTS/BONUS/TOKEN/NAME`；进入/攻击/击杀/复活/排行/结算/占领/领土加成 |
| `models/legion.py` | `Legion.occupied_cities`（占领城市，JSON）、`Legion.battle_points`、`LegionMember.personal_battle_points` |
| `models/player.py` | `in_battlefield`、`battlefield_city`、`battlefield_death_time`、`in_pk`、`pk_opponent`、`honor`、`last_attack_time` 等 |
| `services/legion_service.py` | 军团侧 `occupy_city`/`get_claimable_cities` 转发、兑换（见 legion_design.md） |
| `services/player_service.py` | 领土加成 `get_territory_bonuses` 叠加于属性 flat 段（line 152、182、212、238） |

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
- **荣誉不转移**（有意设计）：战场击杀仅结算积分，不转移荣誉/银两/经验，与野外 PK 的荣誉分档无关。仍调双方 `update_military_rank`（荣誉未变通常不触发军衔变动）。
- **军团积分**：该城 `legion_scores[legion_id] += TIER_POINTS[tier]`（内存）+ `Legion.battle_points += TIER_POINTS[tier]`（持久化）。
- 写入 `player_scores`、`kill_log`（保留最近 20 条）。
- 守方进入死亡态：`battlefield_death_time = time.time()`，清 PK 态。无续命灯立即 `force_death_exit` 传出战场；有灯留 15 秒原地复活窗口，超时由 `tick` 清扫强退（见 §六）。

### 6. 死亡与复活（`can_revive_in_battlefield`/`revive_in_battlefield`，battlefield_service.py:342/349）
- 死亡后 **15 秒**内可复活（`can_revive_in_battlefield`：距死亡时间 ≤15 秒）。
- 复活消耗 1 个 `battle_revive_lamp`（战场续命灯），满血满蓝、清死亡时间。
- 超时未复活：路由 `/death` 调 `force_death_exit` 传送出战场。

### 7. 退出（`exit_battlefield`，battlefield_service.py:152）
- 清 `in_battlefield`/`battlefield_city`/死亡时间/ PK 态，从城内存集合移除。

### 8. 排行（`get_city_rankings`，battlefield_service.py:371）
- 玩家榜前 10（按 `player_scores`）、军团榜前 5（按 `legion_scores`），均只列分数 >0。当前 `rankings` 路由汇总所有城市。

### 9. 占领与结算（`_settle_city`/`occupy_city`/`get_claimable_cities`，battlefield_service.py:398/413/437）
- **惰性结算**（2e97abf 后）：`_settle_city`（:398）按城内 `legion_scores` 实时取最高分军团写入 `state.winner_legion_id`；领土战**没有独立的结束触发器**，改由占领/领取操作按需调用 `_settle_city`，因此占领链路实际可用。
- `occupy_city`（:413）：仅**军团长**；调用 `_settle_city` 后校验 `winner_legion_id == 本军团`，写入 `Legion.occupied_cities`（**仅对本军团自己的占领列表去重，无全局归属表**，见 §六）。
- `get_claimable_cities`（:437）：遍历全部城市惰性结算，返回"本军团是当日榜首且尚未被自己占领"的城市。
- `settle_war`（:408，全城市遍历结算）与 `reset_territories`（:470，清空所有占领）均为**死代码**，全仓库无调用方。
- `get_territory_bonuses`（:451）：每座已占城给成员 attack/defense/max_health/max_mana 各 +`TIER_BONUS`（固定值，flat 段叠加）。

## 五、数据文件/配置

- 城市/段位完全硬编码于 `services/battlefield_service.py:13-40`，**不在 data/ 或 game_config.json**。
- 消耗物：`battle_flag_1/2/3`（战场令旗，按段位）、`battle_revive_lamp`（战场续命灯）。
- 积分兑换的产出物品（令旗、强效秘药、鸳鸯剑图纸等）见 `legion_service.py` 的 `BATTLE_EXCHANGE` 与 `data/items.json`。
- 占领结果持久化于 `Legion.occupied_cities_raw`（JSON），积分持久化于 `Legion.battle_points` / `LegionMember.personal_battle_points`；但**内存态 `CityState`（含 `winner_legion_id`、`legion_scores`、`kill_log`）既随服务器重启清空，也按自然日重置**（`_ensure_city` :93 发现 `war_date != today` 即重建该城状态）。

## 六、注意事项/坑

- **占领链路已闭合（惰性结算）**：早期版本 `settle_war()` 从未被调用导致无法占领；后 `occupy_city`/`get_claimable_cities` 内部调用 `_settle_city` 按需结算，**只要本军团是某城积分榜第一，团长即可在 `/legion/territory` 页面占领**。
- **同城唯一归属（已修）**：`occupy_city` 调 `_set_city_owner` 遍历所有军团，清除其它军团的同名占领后再写入本军团，全局唯一归属成立；`get_claimable_cities` 的漏判由 `_set_city_owner` 兜底剥夺。
- **胜者持久化回退（已修）**：`_settle_city` 内存 `legion_scores` 为空（跨天/重启清零）时回退到持久化 `Legion.battle_points` 降序取首，占领不再依赖易失内存。
- **赛季周重置（已修）**：`ensure_weekly_territory_reset` 周六 0 点清空所有占领 + `reset_weekly_points` 清 `battle_points`/`personal_battle_points`/内存 CityState，待本周团战后再占领；`tick()`/`get_territory_bonuses` 触发。
- **攻方阵亡检查（已修）**：`can_attack_in_battlefield` 开头加 `attacker.health<=0 or attacker.battlefield_death_time>0` 守卫，阵亡攻方无法再 POST 攻击。2 秒攻击冷却仍在路由层（`last_attack_time`，与 PvE 共用）。
- **换城白嫖满血满蓝（已修）**：`can_enter_city` 加 `player.in_battlefield` 检查，已在 A 城须先离开才能进 B 城。
- **死亡清场（已修）**：被击杀无续命灯立即 `force_death_exit`；有灯留 15 秒复活窗口，`tick()` 对超 15 秒的死亡态玩家被动 `force_death_exit` 清扫，避免离线/不复活玩家永久滞留 `in_battlefield`。
- 战场属性加成（领土）是**固定值**叠加在 flat 段；而个人攻击里 `party_rate`/`social_rate`/`spouse_rate`/`vip_rate` 是乘区比率——叠加位置不同（player_service.py:156）。数值上领土加成（7 城全占约 +12 四维）远小于军团技能（20 级 +300 攻/+3000 血），更多是荣誉象征。
- `in_battlefield` 与 `in_pk` 互相排斥：进战场会清 PK 态；战场攻击不受野外 PK 的 25 级/安全区/频率限制约束——**战场是独立 PvP 系统，战败不转移荣誉/银两/经验，不适用 `pk_combat_design.md` 的荣誉分档/银两转移/免战/仇敌规则**。
- 测试模式 `TESTING_MODE=True` 下全天开放且无强制退出；生产逻辑（周六 20:00-20:30）已写好但未启用。工作台 `/workbench/battlefield_test` 可由设计师开启 10 分钟测试战（清加成→开放→结束自动按积分占领），模板 `battlefield_index.html` 展示周六文案。

## 七、相关文档

- [legion_design.md](legion_design.md) — 军团（占领城市的操作入口、`battle_points` 来源与兑换、领土加成互通）
- [pk_combat_design.md](pk_combat_design.md) — 野战 PK（**独立**系统；其荣誉分档/银两/免战/仇敌规则不适用于战场）
- [CLAUDE.md](../../CLAUDE.md) — “Blueprint URL Prefixes” 中 `battlefield`/`legion` 前缀；“Item Usage Rules” 中 `battle_revive_lamp`/`battle_flag_*`/`battle_challenge_token` 等
