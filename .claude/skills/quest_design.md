# 任务系统（主线/支线/副本）设计规则

`/quest/*` 下的主·支线任务与副本阶段任务的完整规则，含任务 JSON Schema、进度追踪、接取/完成/放弃/传送。

## 一、概述

- **URL 前缀**：`/quest`（`blueprints/quest.py:8`）。
- **服务类**：`QuestService`（`services/quest_service.py:7`），数据全部来自 `data/quests.json`（`_load` `:60`，按国家前缀过滤）。
- **状态存储**：
  - 进行中：`player.active_quests`（JSON 字符串，`{quest_id: {'progress':int, 'target':int}}`）。
  - 已完成：`player.completed_quests`（JSON 数组）。
- **国家隔离**：主线按 id 前缀分国——魏 `main_wei_`、吴 `main_wu_`、蜀 `main_shu_`（`_COUNTRY_PREFIX` `:12`），共享主线 `main_all_` 三国通用（`_ALL_COUNTRY_PREFIX` `:14`）；支线 `side_` 按 `country` 字段过滤（空=三国通用，`_is_own_country_quest` `:23`）。

## 二、关键文件

| 文件 | 内容 |
|------|------|
| `blueprints/quest.py` | 任务路由：列表/可接/详情/接取/完成/放弃/传送 |
| `services/quest_service.py` | `QuestService`：国家过滤、接取校验、进度追踪、奖励发放 |
| `data/quests.json` | 全部任务定义（约 327KB），Schema 见下 |
| `services/copy_dungeon_service.py` | 副本阶段任务 `copy_*` 的构造与跳转（`get_current_stage_quest` `:306`、`get_stage_quest` `:602`、`jump_to_entry` `:410`、`jump_to_current_stage` `:427`） |
| `blueprints/dungeon.py:226, :235` | `/dungeon/quest_jump_entry/<id>`、`/dungeon/quest_jump_stage/<id>` |
| `services/battle_service.py:1109` | 击败怪物后 `update_kill_progress` |
| `services/battle_service.py:1117` | `ActivityService.record_daily_task_kill`（每日任务，见 `activity_design.md`） |
| `services/shop_service.py:161` / `blueprints/medicine_shop.py:118` | 购买后 `update_buy_item_progress` |
| `templates/quest_list.html` 等 | `quest_available.html` / `quest_detail.html` / `quest_dialog.html` / `quest_complete.html` / `copy_quest_detail.html` |

## 三、路由（`/quest` 前缀）

| 路由 | 方法 | 说明 |
|------|------|------|
| `/quest/` | GET | 任务中心：进行中/已完成/本国全部任务 |
| `/quest/available` | GET | 可接任务列表（含副本当前阶段任务） |
| `/quest/detail/<quest_id>` | GET | 任务详情（含接取/进度/完成） |
| `/quest/accept/<quest_id>` | GET | 接取任务 |
| `/quest/complete/<quest_id>` | GET | 完成任务并发奖 |
| `/quest/abandon/<quest_id>` | GET | 放弃任务（目标已达成则禁止放弃，`quest.py:250`） |
| `/quest/go/<quest_id>` | GET | 快速传送到任务 NPC 处 |
| `/quest/go_target/<quest_id>` | GET | 快速传送到任务目标场景 |

> `quest_id` 以 `copy_` 开头的走 `CopyDungeonService`（副本阶段任务），其余走 `QuestService`。

## 四、核心逻辑/设计规则

### 1. 任务 JSON Schema（`data/quests.json`）

代表性主键（以 `main_wei_01` 为例，`quests.json:2`）：

```jsonc
{
  "id": "main_wei_01",
  "name": "主·初入三国",
  "type": "main",            // 'main' 主线 | 'side' 支线
  "npc_id": "npc_beiping_east_香凝",
  "npc_name": "香凝",
  "npc_location": "beiping_east.大院",
  "npc_location_name": "大院(北平东区)",
  "level_required": 1,        // 接取所需等级
  "prerequisite": "main_wei_02", // 前置任务 id（可选）
  "description": "前往「大院」与『香凝』对话",
  "target_location": "beiping_east.大院", // 目标场景（go_target 用，可选）
  "objective": {               // 目标类型见下
    "type": "collect_item",
    "item_id": "quest_qingnangshu",
    "item_name": "青囊书",
    "count": 1,
    "monster_name": "窃贼"
  },
  "rewards": { "experience": 100, "gold": 100, "honor": 0 }, // 奖励（honor 可选）
  "dialogs": {               // 接取/完成对话
    "accept": [ {"speaker":"香凝","text":"..."}, ... ],
    "complete": [ {"speaker":"你","text":"..."}, ... ]
  },
  "next_hint": "前往「厢房」与『曹樱』对话",
  "next_quest": "main_wei_02",  // 链上下一任务（可选）
  "grant_item": { "item_id": "...", "count": 1 },      // 完成后发放物品（可选）
  "reward_equipment": { "template_id": "...", "rarity_weights": {...} }, // 生成随机品质装备（可选）
  "is_repeatable": true,     // 可重复接取（可选）
  "country": "魏"             // 支线限国家，空=三国通用（可选）
}
```

### 2. 目标类型（objective.type）

| type | 字段 | 进度推进来源（service 方法） |
|------|------|------------------------------|
| `talk_npc` | `npc_id`,`count` | 与 NPC 对话 `update_talk_progress`（`:338`） |
| `kill_monster` | `monster_name`,`count` | 击败怪物 `update_kill_progress`（`:277`） |
| `collect_item` | `item_id`,`item_name`,`monster_name`,`count` | 击败指定怪且掉落含 `item_name` `update_kill_progress`（`:291`） |
| `deliver_item` | `item_id`,`item_name`,`count` | 背包已有则接取即满；完成扣背包 `refresh_deliver_progress`（`:423`） |
| `buy_item` | `item_id`,`count` | 商店购买 `update_buy_item_progress`（`:303`） |
| `learn_skill` | `count` | 学习技能 `update_learn_skill_progress`（`:320`） |

- `accept_quest`（`:171`）依 `objective.count` 初始化 `target`，`deliver_item` 若背包已足则直接 `progress=count`。
- `complete_quest`（`:195`）校验 `progress >= target`；`deliver_item`/`collect_item` 完成时会从背包扣除所需数量（`:210`）——**防止"交完任务材料还在"的残留**。

### 3. 接取校验（`can_accept_quest` `:143`）

依次判定：
1. 任务存在；
2. 国家隔离（`_is_own_country_quest`）；
3. 等级 `player.level >= level_required`；
4. 共享主线入口（`main_all_` 且无前置）须先完成本国 1–39 级主线（`_country_chain_complete` `:107`）；
5. 非可重复任务且已 `completed` → 拒绝；
6. 已在 `active` → 拒绝；
7. 前置任务 `prerequisite` 须在 `completed`。

### 4. 完成与奖励（`complete_quest` `:195`）

- 发放 `rewards`：`experience` 走 `PlayerService.gain_experience`（`:222`），`gold` 累加 `old`+`old_earned`，`honor` 累加。
- `grant_item`：若 `item_id` 以 `equipment_` 开头则按模板生成随机品质装备（`:236`），否则直接入包。
- `reward_equipment`：按 `rarity_weights` 滚稀有度生成装备（`:247`，`allow_legendary=False`）。
- 非可重复任务记入 `completed_quests`。

### 5. 进度追踪调用点（集成）

- 击败怪物 → `battle_service.py:1109` `update_kill_progress(player, monster.name, quest_drops)`（kill/collect）。
- 商店购买 → `shop_service.py:161`、`medicine_shop.py:118` `update_buy_item_progress`。
- 学习技能 / 对话 → 对应流程调 `update_learn_skill_progress` / `update_talk_progress`。
- 目标已达成时禁止放弃（`quest.py:250`，防刷精英怪）。

### 6. 副本阶段任务（`copy_`）与 quest_jump

- 玩家位于副本地图（`is_copy_map`）时，`CopyDungeonService.get_current_stage_quest`（`:306`）把当前阶段包装成类主线任务 dict，列入"可接任务"/详情页，支持传送与快速前往。
- 任务 id 形如 `copy_<dungeon_id>_<stage>`，`parse_stage_quest_id` 解析出 `dungeon_id`/`stage_index`。
- **传送入口**：`/dungeon/quest_jump_entry/<dungeon_id>`（`dungeon.py:226` → `jump_to_entry` `:410`）传送到阶段 NPC；`/dungeon/quest_jump_stage/<dungeon_id>`（`dungeon.py:235` → `jump_to_current_stage` `:427`）传送到当前阶段目标场景。
- 接受/完成阶段任务分别走 `CopyDungeonService.accept_task` / `complete_stage`，末阶段完成渲染 `copy_dungeon_result.html`。

## 五、数据文件/配置

- **`data/quests.json`**（其余 ~327KB）：键为任务 id，值即上 Schema。包含：
  - 各国主线 `main_wei_*`/`main_wu_*`/`main_shu_*`、共享主线 `main_all_*`；
  - 支线 `side_*`（如 `side_bs_xitiesha_wei/shu/wu`，带 `country` 与 `is_repeatable`）；
  - 目标类型覆盖 `talk_npc`/`collect_item`/`deliver_item`/`kill_monster`/`buy_item`/`learn_skill`。
- 数据由 `QuestService._load`（`:60`）一次性读取并缓存（类级 `_quests`），**无运行时热更新**。
- NPC 任务索引：`_npc_quest_map`（`:371`）按 `npc_id` 预建，供 `get_available_quests_for_npc` 快速查询。

## 六、注意事项/坑

- **任务数据全量缓存**：`quests.json` 改完需重启（或清 `_quests` 缓存）才生效。
- **国家隔离易踩**：主线只能接本国前缀；`side_` 支线看 `country` 字段，空=三国通用。跨国玩家在本国 NPC 处不会看到他国主线。
- **共享主线入口门槛**：`main_all_*`（无前置）须先完成本国 1–39 级主线（`_country_chain_complete`），否则 `can_accept_quest` 拒绝。
- **deliver/collect 完成扣背包**：接任务后若材料被用掉，完成时会再次校验背包数量，不足则失败（`complete_quest` `:215`）——需保留材料到交任务。
- **目标已达成禁止放弃**：防玩家放弃重复刷掉落（`quest.py:250`），应先完成而非放弃。
- **副本任务独立**：`copy_` 任务的接取/放弃/完成走 `CopyDungeonService`，不写 `player.active_quests` 的普通结构（由副本状态机管理），但会在"可接/详情"页以统一任务 dict 呈现。
- **NPC 对话触发**：`talk_npc` 目标需真正"对话"（调 `update_talk_progress`），仅访问场景不计数。

## 七、相关文档

- `activity_design.md` — 每日任务（任务使者）是独立系统（在 `activity_service.py`），与普通 `quest` 任务链不同
- `finance_design.md` — 无直接关系，但 `quest` 页与 `/activity` 同属活动玩法
- `pk_combat_design.md` — 战斗死亡/击杀触发任务进度（`update_kill_progress`），与战斗系统耦合
- `CLAUDE.md` — Blueprint URL Prefixes（`quest` 前缀）
