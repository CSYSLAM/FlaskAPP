# 成就系统设计规则

基于 `services/achievement_service.py`、`services/achievement_catalog.py`、`data/achievements.json` 与玩家界面 `blueprints/player.py`，并对照 `agent_context/tmsg-achievement-alignment.md` 的16分类对齐方案。

## 一、概述

成就系统记录玩家在成长、杀怪、PK、副本、财富、社交、装备、副将、活动、任务等维度的累计行为，达成条件后可**领取**一次性永久属性奖励（或称号）。

- **玩家界面所属蓝图**：`player`（`/player`），成就本身不是独立蓝图（`CLAUDE.md` 的 Blueprint Prefix 表无 `achievement` 前缀）。
- **成就定义来源**：`data/achievements.json` 的静态定义（非 `item_use` 类）+ 运行时由 `achievement_catalog.py` 生成的"道具/宝匣使用"类成就（`AchievementService.get_achievements` 合并两份，见 `services/data_service.py:274`）。
- **玩家完成记录**：唯一表 `achievements`（`models/player.py:1006`），`(player_id, achievement_id)` 唯一约束。

## 二、关键文件

| 文件 | 内容 |
|------|------|
| `services/achievement_service.py` | 核心逻辑：`check_all`/`check`/`_check_condition`/`_complete`/`claim`/`get_all`/`_get_progress`/`get_bonuses`/`get_points`/`_normalize_category` |
| `services/achievement_catalog.py` | 16分类常量 `ALIGNED_CATEGORIES`、`ITEM_TIER_DEFINITIONS`/`CHEST_TIER_DEFINITIONS`、`ITEM_SERIES`/`CHEST_SERIES`、`ITEM_REWARD_FAMILIES`/`CHEST_REWARD_FAMILIES`、`build_aligned_item_achievements()` |
| `services/data_service.py` | `get_achievements:274`（合并本地+对齐）、`get_achievement_categories:285` |
| `blueprints/player.py` | `achievements:335`、`achievement_detail:375`、`claim_achievement:422` |
| `models/player.py` | `class Achievement:1006`（`player_id`/`achievement_id`/`claimed`/`completed_at`）；玩家累计字段 `gold_earned:106`、`item_usage:109`、`dungeon_clears:110`、`boss_kills:111`、`elite_kills_by_area:112`、`monster_kills:113`、`divine_beast_kills:114`、`forge_count:115`、`enhance_success_count:116`、`enhance_fail_count:117`、`enhance_50_count:118`、`tower_max_floor:119` |
| `data/achievements.json` | 成就定义（含 `categories` 数组与 `achievements` 字典，约76KB） |
| `data/titles.json` | 成就奖励中 `title` 类型指向的称号定义 |
| `agent_context/tmsg-achievement-alignment.md` | 16分类对齐记录与"道具"分类落地说明 |

## 三、路由（均在 `/player` 蓝图下，需登录）

| 路由 | 函数 | 说明 |
|------|------|------|
| `/player/achievements?category=&page=&per_page=` | `achievements` | 成就总览，按分类分页（默认每页12）；进入时先 `check_all` 再渲染，展示成就点 `get_points` 与已领加成 `get_bonuses` |
| `/player/achievement/<achievement_id>` | `achievement_detail` | 成就详情：进度、`completed`/`claimed`、难度（按 `condition_value`：≤20简单/≤100普通/否则困难） |
| `/player/claim_achievement/<achievement_id>` | `claim_achievement` | 领取奖励，领取后跳回对应分类分页 |

## 四、核心逻辑 / 设计规则

### 4.1 触发与判定

- **全量检查**：`AchievementService.check_all(player)`（`services/achievement_service.py:9`）遍历 `check` 支持的全部 `condition_type` 各调用一次 `check`。仅在成就总览页进入时调用（`blueprints/player.py:343`）。
- **增量检查**：各业务在发生时调用 `AchievementService.check(player, ctype, current_value=None)`（`services/achievement_service.py:19`）。若传 `current_value`（如 `battle_service.py:1229` 传 `player.kill_count`），则当 `current_value >= adef['condition_value']` 直接完成；否则走 `_check_condition(player, adef)` 内部实时读取玩家字段判定。
- **已完成的跳过**：`check` 开头 `if cls.is_completed(player.id, aid): continue`，避免重复插入数据库记录（`is_completed`：`services/achievement_service.py:143`）。
- **完成写入**：`_complete`（`services/achievement_service.py:109`）仅插入 `Achievement(player_id, achievement_id, claimed=False)`，不立即发奖；发奖在 `claim` 阶段。

触发点一览（`AchievementService.check` 调用处）：

| 业务 | 文件:行 | condition_type |
|------|---------|----------------|
| 击杀/精英/神兽/掉落银两 | `battle_service.py:1229-1237` | `elite_kill`/`elite_kill_area`/`elite_kill_monster`/`kill_monster`/`divine_beast_kill`/`gold_earned` |
| PK胜负 | `battle_service.py:1602-1603` | `pk_win`/`pk_loss` |
| 商城消费 | `shop_service.py:168,171` | `yuanbao_spent`/`jinzu_spent` |
| 升级 | `player_service.py:330` | `level` |
| 穿装/强化 | `equipment_service.py:69,162,167,186,211` | `equip_full`/`enhance_success`/`enhance_50`/`enhance_fail`/`gold_earned` |
| 打造 | `crafting_service.py:335` | `forge` |
| 副本通关/爬塔 | `copy_dungeon_service.py:879-880` | `dungeon_clear`/`dungeon_tower` |
| 使用道具 | `item_service.py:370,443`、`lieutenant_service.py:869` | `item_use` |
| VIP等级 | `vip_service.py:122` | `vip_level` |
| 日常/活动消费 | `activity_service.py:405,622`、`legion_service.py:316,337` | `yuanbao_spent`/`jinzu_spent` |
| 拥有副将 | `lieutenant_service.py:492` | `lieutenant_owned` |
| 聊天/送礼 | `social_service.py:54,71,139` | `chat`/`gift` |
| 访问地点 | `game.py:302` | `visit` |

### 4.2 进度与判定条件（`_check_condition:33` / `_get_progress:184`）

每个 `condition_type` 对应一个玩家字段或聚合查询（进度函数与原函数字段一一对应）：

| condition_type | 判定/进度来源 |
|----------------|--------------|
| `level` | `player.level` |
| `kill` / `elite_kill` | `kill_count` / `elite_kill_count` |
| `pk_win` / `pk_loss` | `pk_win_count` / `pk_loss_count` |
| `enhance` | `max(EquipmentInstance.enhance_level)`（按 `player_id` 查询，`models/player.py:778`） |
| `visit` | `len(player.visited_locations)` |
| `equip_full` | 已装备槽位数（`DataService.get_equipped:542` 非 None 计数） |
| `gold_earned` / `gold_total` | 累计获得银两 / `gold + warehouse_gold` |
| `yuanbao_spent` / `jinzu_spent` | 对应累计消费字段 |
| `gift` / `chat` | `gift_count` / `chat_count` |
| `vip_level` | `player.vip_level` |
| `lieutenant_owned` | 按 `adef['lt_name']` 查 `Lieutenant`（进度为0/1） |
| `item_use` | `_get_item_use_progress`（见 4.4） |
| `dungeon_clear` / `dungeon_tower` | `dungeon_clears[dungeon_id]` / `tower_max_floor` |
| `boss_kill` | `boss_kills[boss_name]` |
| `elite_kill_area` / `elite_kill_monster` / `kill_monster` | `elite_kills_by_area[area]` / `monster_kills[monster_id]` |
| `divine_beast_kill` | `divine_beast_kills` |
| `forge` / `enhance_success` / `enhance_fail` / `enhance_50` | 对应累计字段 |
| `artifact_owned` | 查 `EquipmentInstance`（`is_bound=True`、`rarity='神器'`、`template_id` 匹配）数量 |
| `quest` / `quest_done` | `completed_quests` 解析数组长度 / 是否命中 `condition_quests` |

### 4.3 领取奖励（`claim:120`）

- 校验：`record` 存在且 `claimed=False`，否则返回 `("成就未完成"/"已领取"/"成就不存在")`。
- 奖励写入 `adef['reward']`（`services/achievement_service.py:133`）：
  - `stat == 'title'`：调用 `TitleService.grant_title(player, value, 'prefix' if value.startswith('prefix') else 'suffix')` 授予称号（不直接装备）。
  - 其它数值 `stat`：**直接 `setattr(player, stat, current+value)`** 永久累加到玩家对应列（如 `max_health`），若玩家无该属性则新增一个属性（非 ORM 列，无害但不持久）。
- 系统播报：`DataService.broadcast_system(f"{nickname}完成了{name}成就，太有实力了！")`。
- **重要**：属性奖励在领取瞬间写进玩家字段并持久化（非每次重算），`get_bonuses` 仅用于在界面汇总已领加成展示（`services/achievement_service.py:255`，只累加数值奖励，跳过 `title`）。

### 4.4 分类归一（`_normalize_category:398`）

- 若 `adef['category']` 命中 `ALIGNED_CATEGORIES` 则直接用该分类。
- 否则按 `condition_type` 回退归类：`item_use→道具`、`level/enhance→成长`、各杀怪→`杀怪`、`pk_*→P K`、`equip_full/forge/enhance_*→装备`、`gold_*/yuanbao/jinzu→财富`、`gift/chat→社交`、`lieutenant_owned→副将`、`vip_level→活动`、`dungeon_*→副本`、`quest*→任务`，兜底 `其他`。
- `get_all`（`:154`）按 `categories` 初始化 `{cat: []}`，每项放入归一后的分类；未命中任何分类的项落入 `成长`（`services/achievement_service.py:180`）。

### 4.5 "道具"成就由目录生成（`achievement_catalog.py`）

- `ITEM_TIER_DEFINITIONS`（`:19`）：3档——`开始磕(10, +10点)`、`药就是饭(100, +30点)`、`吃一辈子(1000, +50点)`。
- `CHEST_TIER_DEFINITIONS`（`:25`）：2档——`开始开(20, +20点)`、`开箱高手(100, +40点)`。
- `ITEM_SERIES`（`:113`，**代码实测33组**，每组按 `10/100/1000` 展开3条成就；靠 `reward_family` 映射 `ITEM_REWARD_FAMILIES` 的3档奖励）、`CHEST_SERIES`（`:149`，**代码实测3组**：铁/银/金，每组2条成就，奖励来自 `CHEST_REWARD_FAMILIES` 的2档）。
- `build_aligned_item_achievements()`（`:162`）：生成 `condition_type='item_use'` 的成就定义，`tracking_key = "name:" + series['name']`，并附带系列 `tracking_keys`（如 `potion_heal`、`chest_iron`）；第1档若有 `legacy_start_id`（如 `item_zhixuecao`）则复用旧ID，否则用 `item_use_<slug>_<value>`。
- `DataService.get_achievements`（`:274`）：**先剔除 `achievements.json` 中所有 `condition_type=='item_use'` 的旧定义**，再 `merged.update(build_aligned_item_achievements())` 覆盖，因此"道具"类成就完全由目录生成。

### 4.6 进度追踪（`_get_item_use_progress:284`）

合并 `tracking_key`（`name:<道具名>`）、`tracking_keys` 列表、`item_name→"name:"`、以及 `item_id` 四类键，在 `player.item_usage` 字典中任一命中即返回其计数；否则0。`item_usage` 由 `item_service.py` 在使用道具时按这些键累加。

## 五、数据文件 / 配置

- `data/achievements.json`：顶层 `categories`（13项数组）+ `achievements`（字典，键为成就ID）。每项字段：`name`/`category`/`description`/`condition_type`/`condition_value`/`reward`/`points`，并可能带 `item_id`/`tracking_key`/`tracking_keys`/`lt_name`/`dungeon_id`/`boss_name`/`area`/`monster_id`/`template_id`/`condition_quests` 等。
- `services/achievement_catalog.py`：运行时生成"道具"成就的全部常量（见 4.5）。
- **16分类对齐**：`agent_context/tmsg-achievement-alignment.md` 记录目标分类序为 `道具/成长/副本/杀怪/社交/P K/赛事/装备/财富/副将/活动/任务/其他/长安/大漠/沧海`（共16）。但**代码中 `ALIGNED_CATEGORIES`（`achievement_catalog.py:1`）仅含前13项**，不含 `长安/大漠/沧海`；`get_achievement_categories`（`data_service.py:285`）即返回这13项。区域类（长安/大漠/沧海）在对齐记录里列出但未接入代码。

## 六、注意事项 / 坑

1. **`get_achievements` 会覆盖 `achievements.json` 的道具类定义**：所有 `item_use` 成就以 `achievement_catalog.py` 运行时生成为准，改 `achievements.json` 里的道具条目无效。
2. **分类对齐仅落地前13类**：对齐记录提到的 `长安/大漠/沧海`（区域分类）未出现在 `ALIGNED_CATEGORIES`，`_normalize_category` 对 `condition_type` 也映射不到这些分类，故区域成就目前实际归类不到这三个分类。
3. **"道具"组数差异**：对齐记录写"消耗类34组、宝匣类7组，共116条"，但代码实测 `ITEM_SERIES=33`、`CHEST_SERIES=3`，以代码为准（约33×3+3×2=105条"道具"成就）。
4. **奖励在领取时固化**：数值奖励通过 `setattr` 直接累加进玩家 ORM 列，不是按 `get_bonuses` 实时重算；已领成就重复领取被 `claimed` 拦截。
5. **`claim` 的 `title` 奖励只"授予"不"装备"**：需在称号界面另行装备（`title_design.md`）。
6. **`check_all` 仅成就总览页触发**：其它业务靠各自的 `check` 增量触发；若某业务漏接 `check`，对应成就不会被判定。
7. **`gold_total` 含仓库银两**：`gold + warehouse_gold`（`services/achievement_service.py:61`），与单纯 `gold` 不同。

## 七、相关文档

- `CLAUDE.md` —— "Blueprint URL Prefixes"（玩家 `/player`）、"Item Usage Rules"
- `.claude/skills/title_design.md` —— 成就 `title` 奖励的授予/装备逻辑
- `.claude/skills/pk_combat_design.md` —— `pk_win`/`pk_loss` 成就触发点
- `.claude/skills/lieutenant_design.md` —— `lieutenant_owned` 成就的副将数据来源
- `agent_context/tmsg-achievement-alignment.md` —— 16分类对齐原始记录
