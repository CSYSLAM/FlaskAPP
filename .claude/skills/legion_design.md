# 军团（Legion）系统设计规则

军团（公会）系统的完整规则：创建/加入/审批、军团技能与升级、捐献、军团任务、军贡/积分兑换、领土战（占领城市）、军团聊天、成员管理（副团长/踢人/退出）。

## 一、概述

军团是同一国家玩家的公会组织。前缀 `/legion`（blueprint `legion`，注册名 `'legion'`）。
核心能力：
- 军团等级越高，给全体成员的**固定属性加成**越高（攻/防/血/蓝），且人数上限越高。
- 成员每日签到、捐献、做军团任务可获得**军贡**（个人+军团池）。
- 军团积分（`battle_points`）由领土战击杀累积，用于积分兑换。
- **领土战**：在 `/battlefield` 中获胜的军团可由团长占领城市，城市提供额外固定加成（见 battlefield_design.md）。

## 二、关键文件

| 文件 | 内容 |
|------|------|
| `blueprints/legion.py` | 全部军团路由 |
| `services/legion_service.py` | `LegionService`：创建/加入/审批/退出/签到/捐献/升级/管理/聊天/兑换/任务，常量 `CONTRIB_EXCHANGE`、`BATTLE_EXCHANGE` |
| `models/legion.py` | `Legion`、`LegionMember`、`LegionApplication`、`LegionChat` 四个 ORM 模型；`Legion` 上的等级/槽位/升级成本常量与 `get_skill_bonuses()` |
| `services/battlefield_service.py` | `occupy_city`、`get_claimable_cities`、`get_territory_bonuses`（领土与军团互通） |
| `services/player_service.py` | 属性计算里叠加军团技能/VIP光环/领土加成（`get_attack` 等，line 137-146 等） |
| `data/items.json` | `legion_tiger_tally_1`（一级军团虎符，line 2652）、兑换类物品（bag_expand / battle_* / epic_ring_* / strong_* 等） |

## 三、路由（前缀 `/legion`）

| 路由 | 方法 | 说明 |
|------|------|------|
| `/legion/` | GET | 已入团→`/legion/hall`，否则→`/legion/list` |
| `/legion/list` | GET | 军团列表（按 total_contribution 降序，12/页） |
| `/legion/detail/<int:legion_id>` | GET | 军团详情、是否可申请 |
| `/legion/create` | GET, POST | 创建军团 |
| `/legion/apply/<int:legion_id>` | GET | 提交入团申请 |
| `/legion/hall` | GET | 军团大厅（入团后首页，触发每日重置） |
| `/legion/sign_in` | GET | 每日签到 |
| `/legion/skill` | GET | 查看军团技能加成（团长可见升级入口） |
| `/legion/upgrade` | GET | 升级军团（仅团长） |
| `/legion/members` | GET | 成员列表（15/页，团长/副团可管理） |
| `/legion/manage` | GET | 审批申请 + 成员管理（仅团长/副团） |
| `/legion/approve/<int:app_id>` | GET | 通过申请 |
| `/legion/reject/<int:app_id>` | GET | 拒绝申请 |
| `/legion/set_vice/<int:player_id>` | GET | 设为副团长（仅团长） |
| `/legion/remove_vice` | GET | 撤销副团长（仅团长） |
| `/legion/kick/<int:player_id>` | GET | 踢出成员（团长/副团） |
| `/legion/leave` | GET | 退出军团 |
| `/legion/chat` | GET | 军团聊天记录（15/页） |
| `/legion/chat/send` | POST | 发送军团消息（content） |
| `/legion/contribute` | GET | 捐献页（触发每日重置） |
| `/legion/donate_gold` | GET | 捐献银两 |
| `/legion/donate_jinzu` | GET | 捐献金珠 |
| `/legion/donate_yuanbao` | GET | 捐献元宝 |
| `/legion/quest` | GET | 军团任务页（触发每日重置） |
| `/legion/quest/do` | GET | 完成一次军团任务 |
| `/legion/exchange?cat=` | GET | 军贡兑换（分类 other/equip/assist） |
| `/legion/exchange/<item_key>` | POST | 军贡兑换物品（quantity） |
| `/legion/battle_exchange?cat=` | GET | 军团积分兑换（分类 other/equip/assist） |
| `/legion/battle_exchange/<item_key>` | POST | 积分兑换物品（quantity） |
| `/legion/territory` | GET | 领土页：已占领城市 + 可占领城市 |
| `/legion/occupy/<city_key>` | GET | 占领城市（仅团长，转发到 `BattlefieldService.occupy_city`） |

## 四、核心逻辑/设计规则

### 1. 创建军团（`LegionService.create_legion`，legion_service.py:60）
- 等级 ≥ **30**（`player.level < 30` 拒绝）。
- 本人不能已加入军团（`player.py` 中 `LegionMember` 唯一约束）。
- 银两 ≥ **50万**（`player.gold < 500000` 拒绝）。
- 背包需 **1 个一级军团虎符** `legion_tiger_tally_1`（`is_usable: false`，非背包使用，由获得途径发放）。
- 名称 2–12 字且唯一。
- 创建者自动成为 `leader`，军团 `country` 取创建者国籍。

### 2. 加入/申请（`apply_to_join`，legion_service.py:108）
- 等级 ≥ **20**。
- 只能加入**本国**军团（`legion.country == player.country`）。
- 不可重复申请；人数未达上限（`get_max_slots()`）才可申请。
- 审批：`approve_application`（团长/副团）/ `reject_application`。审批通过生成 `LegionMember`（role=`member`）。

### 3. 退出（`leave_legion`，legion_service.py:199）
- 团长退出时若还有成员：优先晋升副团长为团长，否则晋升最早加入的成员为团长；若是最后成员则删除军团。
- 副团退出会清空 `legion.vice_leader_id`。

### 4. 军团技能与升级（模型 `models/legion.py`，`Legion.get_skill_bonuses`）
- “技能”即**随军团等级线性增长的全员固定加成**，并非可学习技能树。`SKILL_PER_LEVEL = {attack:15, defense:150, max_health:150, max_mana:150}`，加成 = 该值 × `legion.level`（legion.py:30, 49）。
- 最高 `MAX_LEVEL = 20`。
- 升级（`upgrade_legion`，legion_service.py:343）：仅团长；消耗 `total_contribution`；成本表 `UPGRADE_COST`（如 2级5000、5级20000、10级80000…20级300000，legion.py:39）。
- 等级同时决定人数上限 `LEVEL_SLOTS`（1级50人 → 20级200人，legion.py:32）。
- 在属性计算里，军团技能加成是**固定值**（加在 flat 部分，非乘区）：见 `player_service.py:152-156、182-186、212-214、238-240`（`legion_atk/legion_def/legion_hp` 与 VIP 光环、领土加成同在 flat 段）。

### 5. 捐献（每日重置 `check_daily_reset`，legion_service.py:624）
- `donate_gold`：每次 5000 银两，个人军贡+10、军团军贡+10；每日上限 **10 次**（`gold_donate_count` 按 `gold_donate_date` 重置）。
- `donate_jinzu`：每次 10 金珠，军贡+10；触发 `yuanbao`/`jinzu_spent` 成就（`AchievementService.check`）。
- `donate_yuanbao`：每次 10 元宝，军贡+10；触发成就。

### 6. 签到与任务
- 签到 `sign_in`（legion_service.py:242）：每日 1 次，军贡+10；若是 VIP，额外给军团光环叠加（`vip_aura_hp += 30`、`vip_aura_atk += 6`、`vip_aura_def += 30`，并记录 `vip_aura_date`）。
- 军团任务 `do_quest`（legion_service.py:599）：每日上限 **3 次**，每次军贡+10；`get_quest_count` 返回剩余次数（未变天则重置为 3）。

### 7. VIP 光环（`_refresh_vip_aura`，legion_service.py:40）
- 当日已签到且 `is_vip` 的成员，每人贡献 攻击+6 / 防御+30 / 生命+30（与签到时直接累加一致）。
- 跨天自动按“今日已签到成员”重算（仅统计 signed_vip_count）。
- 光环为**固定加成**，叠加在属性 flat 部分（`player_service.py:156、186、214、240` 的 `aura_atk/aura_def/aura_hp`）。
- `get_vip_aura_text`（legion_service.py:689）展示文案（魔法/暴击/闪避固定 +0）。
- ⚠️ 已知 bug：`_refresh_vip_aura` 只按 `signed_today=True` 计数，**不校验签到日期是今天**；而 `check_daily_reset` 只在成员访问大厅/捐献/任务页时才重置其 `signed_today`——昨天签到的 VIP 若今天没上线开页，其光环会残留计入今天。

### 8. 兑换（`CONTRIB_EXCHANGE` / `BATTLE_EXCHANGE`，legion_service.py:473/503）
- 军贡兑换 `exchange_contrib_item`：扣 `member.contribution`，发放物品到背包。分类 other/equip/assist（秘背包扩容卷、战场请战符、战场续命灯、5 个史诗戒指、小血/魔石等）。
- 军团积分兑换 `exchange_battle_item`：扣 `member.personal_battle_points`，发放物品（战场令旗、强效秘药系列、鸳鸯剑图纸等）。
- 注意：兑换在内存遍历所有分类查找 `item_key`，找不到则报“兑换物品不存在”。

### 9. 成员管理
- 角色：`leader` / `vice_leader` / `member`（LegionMember.role）。
- `set_vice_leader`：先把原副团降为 member，再指定新副团；副团唯一（`vice_leader_id`）。
- `kick_member`：团长/副团可踢 member；副团不可踢团长或副团（仅团长可踢副团）。

### 10. 聊天（`LegionChat`，models/legion.py:108）
- `send_message` 内容截断 30 字（`content.strip()[:30]`），空内容拒绝。
- 列表按时间倒序分页（15/页）。

### 11. 领土战（与 battlefield 互通）
- 领土页列出 `legion.occupied_cities`（JSON 存于 `occupied_cities_raw`）与可占领城市（`BattlefieldService.get_claimable_cities`，battlefield_service.py:437）。
- 占领 `occupy_city`（转发 battlefield_service.py:413）：仅团长；内部调用 `_settle_city`（:398）**惰性结算**——按该城当前 `legion_scores` 取最高分军团为胜者，校验 `winner_legion_id == member.legion_id` 后写入占领列表。**占领链路实际可用**：本军团是某城当日积分榜第一即可占领，无需等待独立结算事件。
- 已占领城市通过 `get_territory_bonuses`（battlefield_service.py:451）给成员加固定值：每城 attack/defense/max_health/max_mana += `TIER_BONUS`（低级1/中级2/高级3）。
- ⚠️ 已知问题（重复占领/内存依赖/无赛季重置等）详见下方"注意事项/坑"。

## 五、数据文件/配置

- 城市与段位（`TIER_*`）**硬编码**在 `services/battlefield_service.py:13`（`BATTLEFIELD_CITIES`、`TIER_POINTS`、`TIER_BONUS`、`TIER_TOKEN`、`TIER_NAME`），**不在 data/ 或 game_config.json**。
- `data/items.json`：`legion_tiger_tally_1`（创建凭证）、兑换产出的物品（`bag_expand`、`battle_revive_lamp`、`epic_ring_*`、`strong_*_potion`、`yuanyang_sword_blueprint`、`battle_flag_*`、`blood_stone_small` 等）。
- 无独立军团配置文件；等级/槽位/成本表均在 `models/legion.py` 常量中。

## 六、注意事项/坑

- **领土占领已可用（惰性结算）**：早期版本 `settle_war()` 从未被调用导致 `/legion/occupy` 恒报"未赢得该城市"；2e97abf 后 `occupy_city`/`get_claimable_cities` 内部调用 `_settle_city` 按需结算，本军团是某城当日积分榜第一时团长即可占领。`settle_war`/`reset_territories` 仍是死代码。
- **占领遗留问题**（详见 battlefield_design.md §六）：无全局归属表，同城可被多个军团先后重复占领并同时拿加成；胜者依赖内存态（每日/重启清零），占领须在刷分当天完成；无赛季重置，占领永久且无剥夺。
- **VIP 光环跨天残留**：`_refresh_vip_aura`（:40）按 `signed_today=True` 计数但不校验签到日期，`check_daily_reset` 又只在成员访问特定页面时惰性重置——昨日签到的 VIP 今日未上线时，其光环贡献会残留到今天。
- **团长移交数据残留**：`leave_legion` 把副团长升为团长时（:218-219）更新了 `leader_id`，但未清 `legion.vice_leader_id`，导致其仍指向现任团长（轻微数据不一致，影响 manage 页展示逻辑）。
- **死物品**：`battle_challenge_token`（战场请战符，100 军贡可兑）全代码无消费点。
- 军团技能无独立技能树，仅是随等级的线性固定加成；别误以为有可学习技能。
- 军团加成、VIP光环、领土加成都是**固定值**（加在属性公式 flat 段），而社交/配偶/队伍加成是**比率**（乘区）——二者来源不同，叠加位置不同（见 player_service.py:156）。
- `player.party_id` 与军团无关，是独立的队伍系统（见 party_design.md）。

## 七、相关文档

- [battlefield_design.md](battlefield_design.md) — 领土战/城市占领/段位积分（与本节第 11 条互通）
- [pk_combat_design.md](pk_combat_design.md) — 野战 PK（与领土战 PvP 独立）
- [CLAUDE.md](../../CLAUDE.md) — “Blueprint URL Prefixes” 中 `legion`/`battlefield` 前缀；“Item Usage Rules” 中 `legion_tiger_tally_1` 等
