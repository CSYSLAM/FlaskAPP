# 活动系统设计规则

日常签到、砸蛋、猜拳、答题、陪太子读书、翻牌、幸运币兑换、每日任务（任务使者）、活跃度领奖等活动的完整规则。财经·股市（金珠理财）另见 `finance_design.md`。

## 一、概述

- **蓝图前缀**：`/activity`（在 `app.py:243` 注册，`app.register_blueprint(activity_bp)`，未设置额外前缀，路由名即完整 URL）。
- **服务类**：`ActivityService`（`services/activity_service.py`），全部为 `@classmethod`，状态存于 `player.activity_data`（JSON Blob）。
- **每日重置**：通过 `activity_data['daily']` 下的 `_date` 字段判定跨天；`get_today_value`（`activity_service.py:190`）在日期变化时自动清空 `daily` 字典，实现每日计数归零。

## 二、关键文件

| 文件 | 内容 |
|------|------|
| `blueprints/activity.py` | 全部活动路由（签到/砸蛋/猜拳/答题/读书/翻牌/幸运币/每日任务/活跃度领奖/财经） |
| `services/activity_service.py` | `ActivityService`：活动定义、计数、奖励发放、加权抽奖、每日任务进度 |
| `models/player.py` | `Player.activity_data`、`Player.finance_data`、`jinzu`/`yuanbao` 等货币字段 |
| `data/items.json` | 各类奖励物品（如 `potion_revive`、`enhance_gem`、`duke_token_1d` 等） |
| `templates/activities.html` 等 | `daily_sign.html` / `smash_egg.html` / `rps.html` / `quiz.html` / `study.html` / `card_flip.html` / `lucky_exchange.html` / `daily_tasks.html` / `npc_daily_tasks.html` |

> 注意：**活动配置（奖励/奖池/题目）全部硬编码在 `activity_service.py`，没有独立的 `data/activity*.json` 文件**（搜索 `data/activity*.json` 无结果）。改活动数值需改代码而非数据文件。

## 三、路由（含完整 URL 前缀 `/activity`）

| 路由 | 方法 | 说明 |
|------|------|------|
| `/activity/` | GET | 活动中心：每日进度、总活跃度、领奖档位 |
| `/activity/sign_in` | GET | 签到页 |
| `/activity/do_sign_in` | GET | 执行签到 |
| `/activity/claim_sign_reward/<int:days>` | GET | 领取签到里程碑奖励（days=2/5/10/17/28） |
| `/activity/smash_egg` | GET | 砸蛋页 |
| `/activity/do_smash_egg?free=1/0` | GET | 砸蛋（`free` 默认 1=免费，0=花费元宝） |
| `/activity/rps` | GET | 猜拳页 |
| `/activity/do_rps/<choice>` | GET | 出拳，choice∈`rock`/`scissors`/`paper` |
| `/activity/quiz` | GET | 答题页 |
| `/activity/do_quiz` | POST | 提交答案（表单 `question_idx`/`answer`） |
| `/activity/study` | GET | 陪太子读书页 |
| `/activity/start_study` | GET | 开始读书（10 分钟计时） |
| `/activity/finish_study` | GET | 领取读书奖励 |
| `/activity/card_flip` | GET | 金珠翻牌页 |
| `/activity/do_card_flip` | GET | 翻牌 |
| `/activity/lucky_exchange` | GET | 幸运币兑换页 |
| `/activity/do_lucky_exchange/<item_id>` | GET | 兑换物品 |
| `/activity/claim_activity_reward/<int:tier_points>` | GET | 领取活跃度档位奖励（30/50/80/100） |
| `/activity/daily_tasks` | GET | 每日任务列表（含传送链接） |
| `/activity/npc_daily_tasks` | GET | 任务使者页（接取/进度/完成） |
| `/activity/daily_task_detail/<task_id>` | GET | 单任务详情 |
| `/activity/accept_daily_task/<task_id>` | GET | 接受任务 |
| `/activity/complete_daily_task/<task_id>` | GET | 完成任务 |
| `/activity/teleport_to_task_npc/<task_id>` | GET | 传送到任务使者（本国中心广场） |
| `/activity/teleport_to_target/<task_id>` | GET | 传送到目标怪场景 |
| `/activity/finance` 等 | GET/POST | 财经·股市，详见 `finance_design.md` |

## 四、核心逻辑/设计规则

### 1. 每日活动定义（`activity_service.py:11` `DAILY_ACTIVITIES`）

| key | 名称 | 每日上限 | 活跃度 |
|------|------|----------|--------|
| `rps` | 每日猜拳 | 3 | 15 |
| `sign_in` | 每日签到 | 1 | 10 |
| `smash_egg` | 每日砸蛋 | 1 | 10 |
| `study` | 陪太子读书 | 5 | 10 |
| `quiz` | 每日答题 | 5 | 10 |
| `card_flip` | 幸运金珠翻牌 | 1 | 25 |
| `daily_tasks` | 每日任务 | 10 | 10 |

活跃度累计：完成计数达到 `max` 即把该项的 `points` 计入总活跃度（`get_total_activity_points` `:216`；`get_daily_progress` `:236`）。注意 `daily_tasks` 的完成判定读取 `daily['npc_tasks']` 中 `accepted` 为真的条目数（见下"每日任务"）。

### 2. 签到（`sign_in` `:327` / `claim_sign_reward` `:356`）

- `do_sign_in`：今日未签到（`sign_in_done >= 1` 则提示已签）→ 置 `sign_in_done=1`，累计 `activity_data['sign_total'] += 1`，随机得银两 10~50。
- 里程碑 `SIGN_REWARDS`（`:182`）：`days`∈{2,5,10,17,28}，发放对应物品+元宝。需 `sign_total >= days` 且未领取（`sign_claimed` 列表）。

### 3. 砸蛋（`smash_egg` `:383`）

- 免费每日 1 次（`free=1` 时消耗 `smash_egg_free`），之后每次花 **50 元宝**（`yuanbao`，记录 `yuanbao_spent`）。
- 加权随机从 `EGG_PRIZES`（`:60`，52 项）抽奖 → `_grant_prize`（`:638`）。
- 系统公告：`{昵称}参与砸蛋活动：拿下了{奖名}，太有实力啦！`
- 触发成就 `AchievementService.check(player,'yuanbao_spent',...)`。

### 4. 猜拳（`play_rps` `:422`）

- 每日上限 3 次（`rps_done`）。NPC 随机出 `rock/scissors/paper`，`_rps_result`（`:458`）判胜负。
- 奖励按等级缩放：胜 `经验=level*100+500，银两=level*50+200`；平 `经验=level*80+300`；负 `经验=level*50+100`。每次后 `rps_done += 1`。

### 5. 答题（`start_quiz` `:467` / `answer_quiz` `:476`）

- 题库 `QUIZ_POOL`（`:164`，14 题），每日上限 5 次。
- 正确：`经验=level*200+1000，银两=level*100+500`；错误：`经验=level*50+100`。错误时告知正确答案（`ord(answer)-ord('A')` 取选项文本）。

### 6. 陪太子读书（`start_study` `:507` / `finish_study` `:531`）

- `STUDY_DURATION = 600`（秒=10 分钟，`activity_service.py:504`）。
- `start_study`：写入 `activity_data['study']['start_time']=time.time()`；若已在读且未满则提示剩余秒数。
- `finish_study`：须 `elapsed >= 600`，否则提示剩余；发放 `经验=level*500+1000`，加 2 点活跃度（`_add_activity_points` `:582`），清空 `study` 并 `study_done += 1`。

### 7. 金珠翻牌（`card_flip` `:596`）

- 优先消耗背包 `card_flip_token`；否则花 **50 金珠**（`jinzu`，记录 `jinzu_spent`），不足提示。
- 加权随机从 `CARD_PRIZES`（`:109`，72 项）抽奖；每次翻牌 **额外得 1 个 `lucky_coin`**（幸运币）。
- 系统公告 + 触发 `jinzu_spent` 成就。

### 8. 幸运币兑换（`LUCKY_COIN_EXCHANGE` `:658` / `exchange_lucky_coin` `:674`）

- 12 个兑换项，消耗背包 `lucky_coin`。如 `续命灯`(5) / `强化宝玉`(10) / `宝匣钥匙`(15) / `活力卡`(20) / `副将招募令`(30) / `装备重塑符`(300) / `诸侯令30天`(200) 等。
- 兑换检查 `lucky_coin` 数量 ≥ `cost`，扣除并发放 1 个目标物品。

### 9. 活跃度领奖（`ACTIVITY_REWARD_TIERS` `:52` / `claim_activity_reward` `:291`）

- 档位 30/50/80/100，发放物品 + 元宝。`claim` 校验总活跃度达标且 `claimed_tiers` 未含该档。
- 状态查询：`get_reward_tiers_status`（`:272`）返回 `locked`/`claimable`/`claimed`。

### 10. 每日任务·任务使者（`DAILY_NPC_TASKS` `:22` / `COUNTRY_CITY` `:42`）

- 两种任务：`daily_money`（银两+2000，≥30 级）、`daily_exp`（经验+20000，≥30 级）。
- 按国家分发目标：魏→北平/冀州步兵；蜀→建宁/流民；吴→吴郡/淘金者；各需击杀 `target_count=10`。
- 流程：`accept_daily_task`（`:711`，置 `npc_tasks[task_id]={accepted:True}`）→ 击杀目标怪时 `record_daily_task_kill`（`:745`，由战斗服务在击败怪物后调用，`battle_service.py:1117`）累加 `killed`，满 10 置 `completed` → `complete_daily_task`（`:775`，发奖励并置 `claimed`，`daily_tasks_done += 1`）。
- 传送：`teleport_to_task_npc`（`:278`）→ 本国中心广场（如 `beiping_center.广场`）；`teleport_to_target`（`:290`）→ 北区场景（如 `beiping_north.燕山`）。

## 五、数据文件/配置

- **无独立活动数据文件**：所有奖池、题目、奖励、任务定义、国家目标均硬编码于 `services/activity_service.py`（见上各常量）。
- 奖励物品定义在 `data/items.json`（如 `duke_token_1d`、`potion_package`、`double_exp_card`、`equip_reshape_talisman` 等）。
- 货币：砸蛋用 `yuanbao`（元宝），翻牌/财经用 `jinzu`（金珠），二者不同。

## 六、注意事项/坑

- **每日计数依赖 `daily['_date']` 跨天重置**：`get_today_value` 发现日期变化会整体清空 `daily`（包括 `claimed_tiers`、`npc_tasks` 等），所以每日奖励/任务每天重置。
- **`daily_tasks` 活跃度判定**：`get_total_activity_points` 统计 `npc_tasks` 中 `accepted` 条目（最多 2 个任务），而非 `daily_tasks_done`；任务完成虽递增 `daily_tasks_done` 但活跃度按"已接受数"计，二者口径不同，新增每日任务时需注意。
- **翻牌必得幸运币**：每次 `card_flip` 无论抽到什么都 +1 `lucky_coin`，是幸运币主要来源。
- **砸蛋花元宝、翻牌花金珠**：两种货币别混淆；砸蛋免费额度用尽后才扣元宝。
- **答题 `do_quiz` 用 POST**：前端须以表单提交 `question_idx`/`answer`，其余活动多为 GET。
- 砸蛋/翻牌触发系统公告，频繁参与会刷屏。

## 七、相关文档

- `finance_design.md` — 同前缀 `/activity/finance/*` 的股市/劫匪系统
- `pk_combat_design.md` — `pk_drop_reduction` 等 VIP 权益由 `vip_service.py` 提供，活动无直接关系
- `vip_design.md` — VIP 与诸侯令（活动奖池里含 `duke_token_*`）
- `CLAUDE.md` — Blueprint URL Prefixes（`activity` 前缀说明）、Item Usage Rules（部分活动产出物的使用限制）
