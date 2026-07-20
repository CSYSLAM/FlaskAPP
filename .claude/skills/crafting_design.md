# 铁匠铺（打造）系统设计规则

NPC 铁匠：史诗装备打造（武器/饰品/套装）、装备强化、批量卖装备/道具。URL 前缀 `/crafting`。

## 一、概述

铁匠铺（`blacksmith.html` 触发）提供四类功能：
- **史诗打造**：武器（按职业）、饰品（无职业限制）、套装（按职业+等级段）。消耗材料+银两，随机掷出 精良/卓越/史诗（**不出神器**）。
- **装备强化**：背包装备强化，消耗银两+强化宝玉，可用幸运符提成功/防爆。
- **批量卖装备**：按稀有度+等级段批量出售（排除已装备）。
- **批量卖道具**：按类别（药品/种子/材料/技能）批量出售。

材料成本表、套装/模板定义硬编码于 `services/crafting_service.py`；装备模板来自 `data/equipment_sets/*.json`。

## 二、关键文件

| 文件 | 内容 |
|------|------|
| `blueprints/crafting.py` | 全部路由 |
| `services/crafting_service.py` | `CraftingService`：材料表、SET_DEFINITIONS、WEAPON/ACCESSORY_TEMPLATES、forge_equipment、sell_* |
| `services/equipment_service.py` | `EquipmentService.enhance`（强化执行） |
| `services/equipment_generator.py` | `_roll_rarity_from_weights`（掷稀有度） |
| `data/equipment_sets/craft_weapons.json` | 武器模板（史诗武器，is_artifact:false） |
| `data/equipment_sets/craft_accessories.json` | 饰品模板（史诗饰品，is_artifact:false） |
| `data/equipment_sets/*.json` | 套装模板（armor sets，由 data_service 合并缓存） |
| `services/data_service.py` | `get_equipment_template`、`create_equipment_instance` |

## 三、路由（前缀 /crafting）

| 路由 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 重定向到 epic_forge |
| `/class/<class_name>` | GET | 旧路由，重定向 epic_forge |
| `/epic_forge` | GET | 史诗打造分类列表（按职业取套装） |
| `/epic_forge/weapons[/<class_name>]` | GET | 武器打造页（职业 tab） |
| `/epic_forge/accessories` | GET | 饰品打造页 |
| `/epic_forge/set/<set_id>[/<class_name>]` | GET | 套装打造页（同 group 渲染职业 tab） |
| `/forge/<template_id>` | POST | 执行打造 |
| `/sell_equipment[/<rarity>]` | GET | 卖装备页（稀有度 tab） |
| `/sell_equipment/do` | POST | 批量卖装备 |
| `/sell_item[/<category>]` | GET | 卖道具页（类别 tab） |
| `/sell_item/do` | POST | 批量卖道具 |
| `/enhance[/<int:page>]` | GET | 强化列表（背包全部装备） |
| `/enhance_page/<equipment_instance_id>` | GET | 单件强化界面 |
| `/enhance_do/<equipment_instance_id>` | POST | 执行强化 |
| `/use_luck/<luck_type>/<equipment_instance_id>` | POST | 强化界面用幸运符（small/medium） |

## 四、核心逻辑 / 设计规则

### 4.1 材料成本表（`crafting_service.py`）

- `LEVEL_MATERIALS`（line 11）：套装按等级段（15-20…55-59），每件 4 材料各 20 + 银两（2440…14440）。
- `WEAPON_MATERIALS`（line 39）：武器按精确等级（20/30/40/50/60），木+矿各 20 + 银两（2440…14440）。
- `ACCESSORY_MATERIALS`（line 48）：饰品按精确等级（10/14/24/28/34/40/46/54），木+矿各 20 + 银两（1940…10440）。
- 模板可自带 `craft_materials`/`blueprint_item`（如 60 级套需图纸）：`get_material_cost`（line 251）优先用模板自带配方，图纸作为「材料」之一参与校验/扣除/绑定判定。

### 4.2 模板与套装定义

- `SET_DEFINITIONS`（line 60）：21 个套装，每套 `set_id/name/class_name/level_range/group/templates(5槽)`。共享 `group` 的套装（如 青龙/朱雀/白虎 55-59）在套装页渲染**职业 tab**（`get_set_class_tabs` line 213）。
- `WEAPON_TEMPLATES`（line 169）：每职业 9 把（20/30/40/50/60 级各 2 + 60 级 1），`class_required` 限定。
- `ACCESSORY_TEMPLATES`（line 194）：8 件（10/14/24/28/34/40/46/54 级），`class_required:null`（全职业）。

### 4.3 打造 `forge_equipment`（crafting_service.py:284）

1. 取模板与成本；校验银两。
2. 逐项校验材料数量（`get_inventory_item`）。
3. **绑定判定**：所有材料均有非绑定库存 → 成品非绑定；否则成品 `is_bound=True`（混合材料即绑定，line 329）。
4. 扣银两+材料。
5. **掷稀有度**：`rarity_weights = {common:0, uncommon:50, rare:35, epic:15, legendary:0}`，经 `_roll_rarity_from_weights(..., allow_legendary=False)` → 仅 **精良/卓越/史诗**，无神器（line 321）。`stars = randint(1,5)`。
6. `create_equipment_instance` 生成；`player.forge_count++` 触发成就 `forge`（line 335）。

### 4.4 强化（enhance）

- `enhance_list`：背包全部 `EquipmentInstance`（先未装备、后已装备），分页 40。
- `enhance_equipment`（页面）：`enhance_cost = game_config['enhance_cost']`（默认 5000）；`can_enhance = 银两≥cost 且 enhance_level<50 且 有 enhance_gem`（crafting.py:262）。
- 属性增量：`int(initial * 0.01 * level)`（crafting.py:274），逐属性展示。
- `enhance_do` → `EquipmentService.enhance`（实际执行，扣银两+宝玉）。
- `use_luck`：`small`→`enhance_lucky`，`medium`→`enhance_lucky_medium`，经 `ItemService.use_item` 在强化界面触发（幸运符，`is_usable:false` 仅此处用）。

### 4.5 批量卖装备 `sell_equipment_batch`（crafting_service.py:421）

- 按 `rarity` 过滤（普通/精良/卓越/史诗/神器），排除已装备（`EquipmentSlot`）。
- 列表按等级段分组：`lo=((level-1)//10)*10+1, hi=lo+9`（如 1-10、11-20…），勾选 level_ranges 批量卖。
- 单价 `eq.get_sell_price()`，累加 `player.gold` 与 `player.gold_earned`，删除实例。

### 4.6 批量卖道具 `sell_item_batch`（crafting_service.py:492）

- 类别映射：药品→consumable/potion；种子→seed；材料→material；技能→skill_book。
- 按物品名分组，单价 = `item_def.get('sell_price', 10)`，按数量结算。

## 五、数据文件 / 配置

- `data/equipment_sets/craft_weapons.json`：9×3 武器模板，`set_name:"史诗武器"`，`is_artifact:false`，含 `base_stats`/`max_extra_stats`/`base_price`。
- `data/equipment_sets/craft_accessories.json`：8 饰品模板，`set_name:"史诗饰品"`，`is_artifact:false`。
- 套装模板存于同名 equipment_sets json（由 `data_service` 加载合并）。
- `game_config['enhance_cost']`（强化单次银两，默认 5000）。

## 六、注意事项 / 坑

- 打造**永远不出神器**（legendary 权重 0 且 `allow_legendary=False`），最高史诗；但卖装备页的稀有度 tab 含「神器」仅作筛选（实际无神器可卖）。
- 材料绑定判定是「全非绑定→成品非绑定，任一绑定→成品绑定」，无部分绑定概念。
- 60 级套装等依赖 `blueprint_item`（图纸），无图纸则 `get_material_cost` 回退到按等级查表（找不到对应等级会返回 None → 打造失败「无法确定打造材料」）。
- 强化上限 `enhance_level < 50`，且须持有 `enhance_gem`；银两不足也拦截。
- 批量卖**自动排除已装备装备**，但已装备判定依赖 `EquipmentSlot` 表，装备数据异常时可能误卖。

## 七、相关文档

- `.claude/skills/equipment_design.md` → 装备实例、强化、sell_price、槽位
- `.claude/skills/equipment_generation.md` → 程序化生成与稀有度权重（本模块的 `_roll_rarity_from_weights` 同源于此）
- `CLAUDE.md` →「Blacksmith crafting」设计要点
