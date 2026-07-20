# 称号系统设计规则

基于 `services/title_service.py`、`data/titles.json` 与玩家界面 `blueprints/player.py`（前缀/后缀称号的查看、装备、卸下）。

## 一、概述

称号由**前缀（prefix）**与**后缀（suffix）**两部分组成，各自独立装备；拥有数量越多，对应前缀/后缀属性加成越高（最高+50%）。当所装备的前缀与后缀构成"套装对"（`pair_id` 互指）时，激活隐藏属性（暴击率+闪避率）。

- **玩家界面所属蓝图**：`player`（`/player`）。
- **称号定义来源**：`data/titles.json`，分 `prefixes` / `suffixes` / `star_bonuses` 三块，由 `DataService`（`services/data_service.py:294-315`）读取缓存。
- **套装对（pair）**：`prefix.pair_id == suffix_id` 且 `suffix.pair_id == prefix_id` 时成立（见 `titles.json` 末 `_comment`）。

## 二、关键文件

| 文件 | 内容 |
|------|------|
| `services/title_service.py` | `get_title_bonuses:7`、`is_matching_pair:97`、`grant_title:107`、`set_title:117`、`unset_title:130` |
| `services/data_service.py` | `get_title_prefixes:294`、`get_title_suffixes:298`、`get_title:302`、`get_star_bonuses:312` |
| `services/player_service.py` | `get_max_health:192`/`get_max_mana:220`/`get_attack:131`/`get_defense:162` 在实时计算时调用 `TitleService.get_title_bonuses` 应用称号加成 |
| `blueprints/player.py` | `titles:1096`、`title_detail:1123`、`equip_title:1167`、`unequip_title:1226` |
| `data/titles.json` | `prefixes`（13项）、`suffixes`（12项）、`star_bonuses`（1~5星）、`_comment` |
| `models/player.py` | `title_prefix_id:122`、`title_suffix_id:123`、`owned_titles_raw:124`、`owned_titles` 属性:307 |

## 三、路由（均在 `/player` 蓝图下，需登录）

| 路由 | 函数 | 说明 |
|------|------|------|
| `/player/titles?title_type=prefix|suffix` | `titles` | 称号列表（默认 prefix）；展示某类全部称号、已拥有集合、`get_title_bonuses` 汇总、数量/属性标签 |
| `/player/title_detail/<title_type>/<title_id>` | `title_detail` | 称号详情：星级基础加成、`is_owned`/`is_equipped`、配对称号（`pair_id` 指向的另一半） |
| `/player/equip_title/<title_type>/<title_id>` | `equip_title` | 装备指定称号（须已拥有）；装备前后对比最大生命/魔法/攻/防/暴击/闪避并 flash 变化 |
| `/player/unequip_title/<title_type>` | `unequip_title` | 卸下当前前缀或后缀称号 |

## 四、核心逻辑 / 设计规则

### 4.1 加成计算（`get_title_bonuses:7`）

返回字典含 `max_health/max_mana/attack/defense/crit_rate/dodge_rate/prefix_count/suffix_count/hidden_activated`。

1. **拥有数量统计**：遍历 `player.owned_titles`，命中 `prefixes` 则 `prefix_count++`，命中 `suffixes` 则 `suffix_count++`（`title_service.py:31-35`）。数量加成上限50%（`1 + count/100`）。
2. **前缀加成**：若 `player.title_prefix_id` 有值，取该前缀 `stars`→`DataService.get_star_bonus(stars)` 得 `base_hp/mp/atk/def`，再乘 `mult = 1 + prefix_count/100`，`int` 累加进对应属性（`title_service.py:42-56`）。
3. **后缀加成**：同理，乘 `1 + suffix_count/100`（`title_service.py:60-74`）。
4. **隐藏属性（套装对）**：仅当同时装备前缀与后缀，且 `prefix.pair_id == player.title_suffix_id` **且** `suffix.pair_id == player.title_prefix_id`（`title_service.py:78-85`）。满足则按两星均值 `avg_stars = (prefix_stars+suffix_stars)/2` 取整取 `star_bonus`，赋 `crit_rate = hidden_crit`、`dodge_rate = hidden_dodge`，并置 `hidden_activated=True`（`title_service.py:86-93`）。
   - `is_matching_pair`（`:97`）仅校验 `prefix.pair_id == suffix_id`（单向），用于配对判断辅助。

### 4.2 星级基础加成（`star_bonuses`）

`data/titles.json` 的 `star_bonuses` 按字符串键 `"1"~"5"` 提供：

| 星 | base_hp | base_mp | base_atk | base_def | hidden_crit | hidden_dodge |
|----|---------|---------|----------|----------|-------------|-------------|
| 1 | 200 | 150 | 80 | 100 | 0.005 | 0.005 |
| 2 | 400 | 300 | 160 | 200 | 0.010 | 0.010 |
| 3 | 800 | 600 | 320 | 400 | 0.020 | 0.020 |
| 4 | 1400 | 1100 | 560 | 700 | 0.030 | 0.030 |
| 5 | 1960 | 1560 | 818 | 996 | 0.035 | 0.035 |

> `get_star_bonus`（`:312`）按 `str(stars)` 取；隐藏属性仅在套装对激活时生效。

### 4.3 授予 / 装备 / 卸下

- **授予 `grant_title`（`:107`）**：`title_id` 不在 `player.owned_titles` 时追加并写回；用于成就奖励发称号（`achievement_service.py:136` 调用，只授予不装备）。
- **装备 `set_title`（`:117`）**：要求 `title_id in player.owned_titles`，按 `title_type` 写入 `title_prefix_id` / `title_suffix_id`；不在拥有列表则返回 `False`。
- **卸下 `unset_title`（`:130`）**：将对应 `title_prefix_id` / `title_suffix_id` 置 `None`。
- 路由层 `equip_title`/`unequip_title`（`blueprints/player.py:1167,1226`）在改库前后用 `PlayerService.get_max_health/get_attack/...` 与 `player.effective_crit_rate/effective_dodge_rate` 计算差值并 flash 提示。

### 4.4 加成实时生效

称号加成**非固化到玩家字段**，而是在计算有效属性时实时调用 `TitleService.get_title_bonuses`（`player_service.py:130,161,191,219` 等四处）。即装备/卸下称号后立即反映到攻防血魔与暴击/闪避，无需重算成就奖励。

## 五、数据文件 / 配置

- `data/titles.json`：
  - `prefixes`：键如 `prefix龙`，含 `name`/`stars`/`description`/`pair_id`（可为 `null`）。
  - `suffixes`：键如 `suffix传人`，结构与前缀一致，且 `pair_id` 指回对应前缀键。
  - `star_bonuses`：见 4.2。
  - `_comment`：说明隐藏属性激活条件。
- 配对示例（互指）：`prefix龙↔suffix传人`、`prefix血腥↔suffix屠夫`、`prefix战无不胜↔suffix将军`、`prefix最热血↔suffix忠义之魂` 等；部分称号 `pair_id=null`（如 `prefix啸傲西方`、`suffix霸王`）无法激活隐藏属性。

## 六、注意事项 / 坑

1. **加成实时计算**：称号奖励通过 `get_title_bonuses` 在计算有效属性时叠加，与成就的"领取即固化"（`achievement_design.md` 4.3）机制不同——称号可随时装备/卸下改变战力。
2. **套装对需双向互指**：仅 `prefix.pair_id==suffix_id` 不够，必须后缀的 `pair_id` 也指回前缀（`title_service.py:85`），否则隐藏属性不激活。
3. **数量加成上限50%**：`1 + count/100` 随拥有同类称号数量增长，但 `count` 越大加成越高（与多数系统"越少越好"相反）。
4. **授予≠装备**：成就发放称号只写 `owned_titles`，需玩家到称号界面手动装备才会生效。
5. **`pair_id` 指向的是另一半的 title_id 键**（如 `suffix传人`），不是名称；`title_detail` 用 `DataService.get_title(pair_id, other_type)` 取配对定义（`:1152`）。
6. **`title_detail` 的 `title_type` 决定取哪张表**：`prefix` 取 `get_title(id,'prefix')`，`suffix` 取 `get_title(id,'suffix')`（`blueprints/player.py:1129-1134`）。

## 七、相关文档

- `CLAUDE.md` —— "Blueprint URL Prefixes"（玩家 `/player`）
- `.claude/skills/achievement_design.md` —— 成就 `title` 奖励的授予（`grant_title`）触发点
- `.claude/skills/lieutenant_design.md` —— 有效属性计算体系（称号加成与副将被动加成同属 `player_service` 实时计算）
