# 装备设计规则

## 基础属性（base_stats）

- **所有装备严格只有1种基础属性**
- 武器 → `attack`（攻击）
- 防具（头盔/衣服/手套/裤子/鞋子）→ `defense`（防御）
- 饰品（戒指/项链）→ `defense`（防御）
- **活动装备可以有2种基础属性**（需在模板中明确指定，由设计者自定义搭配）

### 基础属性与品质（与星级无关）

**模板 `base_stats` 定义的是该装备最高品质（史诗）的属性值**。基础属性只受品质影响，**与星级无关**（不管几星，基础属性一致）。低品质按品质系数衰减：

| 品质 | 基础属性系数 | 说明 |
|------|------------|------|
| 普通 | 80% | 模板值 × 0.80 |
| 精良 | 90% | 模板值 × 0.90 |
| 卓越 | 95% | 模板值 × 0.95 |
| 史诗 | 100% | 模板值（模板定义即史诗值） |
| 神器 | 100% | 与史诗同等 |

> 例：模板 `attack: 134`（史诗）。普通武器基础攻击 = 134×0.80 = 107；卓越 = 134×0.95 = 127；史诗/神器 = 134。
> 暴击率/闪避率这类浮点属性同样按系数衰减，不取整；其余属性 `int()` 取整。

### 现有装备示例

| 装备 | 部位 | 基础属性 |
|------|------|---------|
| 雏龙长剑 | 武器 | attack |
| 雏龙头巾 | 头盔 | defense |
| 雏龙衣 | 衣服 | defense |
| 雏龙手套 | 手套 | defense |
| 雏龙鞋 | 鞋子 | defense |
| 黄铜戒指 | 饰品 | defense |
| 灵犀项链 | 饰品 | defense |

## 附加属性（extra_stats）

### 品质与条数

| 品质 | 附加属性条数 |
|------|------------|
| 普通 | 1条 |
| 精良 | 2条 |
| 卓越 | 3条 |
| 史诗 | 4条 |
| 神器 | 5条 |

附加属性从 `max_extra_stats` 中按固定顺序选取（非随机），确保不同品质间属性层级一致。

### 零值属性规则（核心）

- **`max_extra_stats` 中所有装备/武器均包含全部 6 个属性**：`attack`、`defense`、`max_health`、`max_mana`、`crit_rate`、`dodge_rate`，缺失的默认补 `0.0`，不修改已有非零值。
- **某属性值为 `0`（或 `0.0`）时**：
  - **不参与**附加属性随机星级生成（跳过该属性，不占用品质对应的条数名额）
  - **不计入**总体星级汇总
  - **不在**装备详情界面显示该附加属性
- 即按固定顺序选取属性时，遇到 `max_value == 0` 的属性直接跳过，继续向后取下一个非零属性，直到凑满该品质对应的条数（或非零属性用尽）。
- 装备详情模板（`templates/equipment_view.html`、`templates/workbench/equip_test.html`）只渲染实际生成（值非零）的附加属性。


### 武器（weapon）附加属性顺序

```
1条: 攻击力
2条: 攻击力 → 生命上限
3条: 攻击力 → 生命上限 → 暴击率
4条: 攻击力 → 生命上限 → 暴击率 → 魔法上限
5条: 攻击力 → 生命上限 → 暴击率 → 魔法上限 → 防御力
```

### 防具（armor/helmet/gloves）附加属性顺序

```
1条: 防御力
2条: 防御力 → 生命上限
3条: 防御力 → 生命上限 → 魔法上限
4条: 防御力 → 生命上限 → 暴击率 → 魔法上限
5条: 攻击力 → 生命上限 → 暴击率 → 魔法上限 → 防御力
```

### 鞋子/护腿（shoes/pants）附加属性顺序

```
1条: 防御力
2条: 防御力 → 生命上限
3条: 防御力 → 生命上限 → 魔法上限
4条: 防御力 → 生命上限 → 闪避率 → 魔法上限
5条: 攻击力 → 生命上限 → 闪避率 → 魔法上限 → 防御力
```

- 鞋子和护腿优先闪避率（dodge_rate），暴击率（crit_rate）被替换为闪避率
- 替换后如有重复项会去重（保持首次出现的位置）

### 附加属性数值计算

**每条附加属性有独立星级**，先随机星级，再按该星级对应的系数区间随机出实际值。模板 `max_extra_stats` 定义的是 **5 星上限值**。

```
1. 每条附加属性独立随机星级 stat_stars：
   stat_stars = clamp(random(target_stars - 1, target_stars + 1), 1, 5)
   （target_stars 为调用方传入的“目标星级”，如怪物掉落 star_range/打造 1-5 星）
2. 按该条星级查系数区间，区间内随机一个系数 coef：
   5星: 100% - 110%   4星: 100% - 106%   3星: 100% - 102%
   2星: 98% - 102%    1星: 96% - 100%
3. 实际值 = max_extra_stats[属性] × coef
   （暴击/闪避保留浮点，其余 int() 取整）
4. 装备总星级 = floor(各附加属性星级之和 / 条数)
   （无附加属性时回落到 target_stars）
```

每条附加属性存储为 2 元素数组 `[实际值, 该条星级]`。**装备总星级由各附加属性星级的平均值反推**（下取整），不再由调用方直接决定 —— 调用方传入的 `stars` 仅作为各条附加属性星级波动的中心。

> 例：史诗武器 4 条附加属性，各条星级分别为 5/4/5/4 → 总星级 = floor((5+4+5+4)/4) = 4。
> 注：`max_extra_stats[属性] == 0` 的属性会被跳过（不生成、不显示、不计入总星级），详见上方「零值属性规则」。

#### 附加属性星级系数表

| 附加属性星级 | 系数区间 |
|------------|---------|
| 5星 | 100% - 110% |
| 4星 | 100% - 106% |
| 3星 | 100% - 102% |
| 2星 | 98% - 102% |
| 1星 | 96% - 100% |

> 模板 `max_extra_stats` 的值即 5 星上限；星级越低系数区间整体下移。5 星可略超模板值（最高 110%），1 星最低到 96%。

## 神器规则

**核心原则：神器与普通装备是两条完全独立的品质体系**

- **非神器装备（`is_artifact: false` 或未设置）**：无论是怪物掉落、打造、开宝箱，**永远不会产出神器品质**。可产出品质为：普通、精良、卓越、史诗
- **神器装备（`is_artifact: true`）**：**只会产出神器品质**，不会产出普通/精良/卓越/史诗。只有专门配置了神器掉落的怪物、宝箱才能产出
- **普通怪物、精英怪物永远不出神器**，无论装备模板的 `is_artifact` 是什么值
- **打造系统**：非神器套装不出神器；神器套装（`is_artifact: true`）打造仅出神器
- **代码实现**：`EquipmentGenerator._roll_rarity_from_weights(weights, is_elite, allow_legendary)` 中 `allow_legendary=False` 时自动排除神器品质。`generate_from_pool` 对非 `is_artifact` 模板自动传入 `allow_legendary=False`

| 来源 | 非神器装备 | 神器装备 |
|------|-----------|---------|
| 普通怪物 | 普通、精良 | 不掉落 |
| 精英怪物 | 精良、卓越、史诗 | 不掉落 |
| 打造 | 精良、卓越、史诗 | 仅神器 |
| 宝箱/活动 | 按配置 | 仅神器 |

## 装备模板 JSON 结构

```json
{
  "template_id": {
    "name": "装备名称",
    "slot": "weapon|helmet|armor|gloves|pants|shoes|accessory",
    "set_name": "套装名称",
    "level_required": 10,
    "class_required": null,
    "is_artifact": false,
    "base_stats": {
      "attack": 24
    },
    "max_extra_stats": {
      "attack": 15,
      "defense": 0.0,
      "max_health": 60,
      "max_mana": 30,
      "crit_rate": 0.05,
      "dodge_rate": 0.0
    }
  }
}
```

> `base_stats` 的值是**该装备最高品质（史诗）的属性值**；低品质按品质系数衰减（普通80%/精良90%/卓越95%），与星级无关。
> `max_extra_stats` 必须包含全部 6 个属性（缺失默认 `0.0`），值即 **5 星上限值**；值为 `0` 的属性不生成、不显示、不计入总星级。

## 装备部位（slots）

| 部位 | slot 值 | 基础属性 |
|------|---------|---------|
| 武器 | weapon | attack |
| 头盔 | helmet | defense |
| 衣服 | armor | defense |
| 手套 | gloves | defense |
| 裤子 | pants | defense |
| 鞋子 | shoes | defense |
| 饰品 | accessory | defense |

注：活动装备可以有2种基础属性，需在模板中明确指定。

## 打造系统

### 合成规则

- 武器材料：黄杨木+黄铜矿（L20-30）/ 沉香木+黑铁矿（L40-50）/ 紫檀木+精金矿（L54+）
- 饰品材料：同上，按等级精确映射银两（见 crafting_service.py 中的 ACCESSORY_MATERIALS）
- 防具材料：碎皮+麻布+黄杨木+黄铜矿（L15-30）/ 硬皮+棉布+沉香木+黑铁矿（L35-55）
- 合成成本：材料 + 银两 + 随机品质 + 随机星级
- 非神器套装打造产出：精良、卓越、史诗（不含神器）
- 神器套装打造产出：仅神器

### 品质权重（打造）

```json
{
  "uncommon": 50,  // 精良
  "rare": 35,      // 卓越
  "epic": 15,      // 史诗
  "legendary": 0   // 神器（非神器套装时排除）
}
```

## 强化系统

装备强化通过 `EquipmentService.enhance()`（`services/equipment_service.py`）实现，消耗银两 + 强化宝玉（`enhance_gem`），上限 +50。

### 强化收益

- 每级 +1% 初始属性（向下取整）：`new_base[stat] = initial_value + int(initial_value × 0.01 × enhance_level)`
- 加成基于 `get_initial_stats()`（品质/星级定型时的初始属性），不是当前值——同等级下史诗5星收益远高于精良1星
- `int()` 截断：低属性装备前期强化可能 +0（10% 不足 1 的情况已不存在，1% 更易出现）

### 成功率（`EquipmentInstance.get_enhance_success_rate`，`models/player.py`）

| 强化等级 | 基础成功率 |
| --------- | ---------- |
| +0→+1 | 100% |
| +1~+9 | 95% |
| +10~+17 | 90% |
| +18~+24 | 80% |
| +25~+29 | 75% |
| +30~+34 | 60% |
| +35~+39 | 55% |
| +40~+41 | 50% |
| +42~+44 | 40% |
| +45~+47 | 35% |
| +48~+50 | 30% |

最终成功率 = `min(100%, 基础成功率 + 玩家保底加成 enhance_bonus_rate)`

### 成功 / 失败

- **成功**：`enhance_level += 1`；清零 `enhance_bonus_rate`；按新等级重算 base_stats；**每次成功都全服广播**；触发 `enhance` 成就检查
- **失败**：`enhance_level = max(0, 当前-1)`（掉一级，不为负）；`enhance_bonus_rate += 0.05`（下次 +5% 保底，累加）；按掉级后等级重算 base_stats。无"必成"硬保底，一次成功即清零加成

### 名称

`update_name()` 在装备名后追加 `+{enhance_level}`（0 级不显示）

## 规则变更记录

| 日期 | 变更内容 |
|------|---------|
| 2026-06-06 | 初始版本：从 monster_equipment_drop_rules.md 拆分出装备设计独立 skill |
| 2026-06-06 | 基础属性规则：每件1-2种，按部位固定搭配 |
| 2026-06-06 | 附加属性规则：品质→条数(普通1/精良2/卓越3/史诗4/神器5)，武器/防具/鞋护腿顺序 |
| 2026-06-06 | 神器规则：独立品质体系，非神器不出神器，神器只出神器 |
| 2026-06-06 | 鞋子/护腿优先闪避率替代暴击率 |
| 2026-06-09 | 基础属性简化为严格1种：武器=attack，防具/饰品=defense；活动装备可自定义2种 |
| 2026-06-09 | 武器打造品质权重调整：精良50%/卓越35%/史诗15%（移除神器5%） |
| 2026-06-27 | 工作台装备设计系统：查看/增删改/测试生成功能 |
| 2026-06-27 | 工作台怪物设计系统：查看/增删改/战斗掉落测试功能 |
| 2026-06-27 | 精英怪神器权重数据修复：130个非神兽精英legendary归零 |
| 2026-06-27 | 怪物设计：套装批量添加装备到掉落池、等级区间筛选、复活时间、掉落说明 |
| 2026-06-27 | 工作台物品设计系统：查看/增删改/使用效果测试功能 |
| 2026-06-29 | 零值属性规则：`max_extra_stats` 全部补齐 6 属性（缺失补 0.0，不改已有值）；值为 0 的属性不参与随机星级生成、不计入总体星级、不在装备详情显示 |
| 2026-07-01 | 基础属性与星级解耦：模板 `base_stats` 定义最高品质（史诗）值，基础属性只按品质系数衰减（普通80%/精良90%/卓越95%/史诗100%/神器100%），不再随星级变化 |
| 2026-07-01 | 附加属性星级系数重做：每条附加属性独立随机星级，按星级查系数区间（5星100-110%/4星100-106%/3星100-102%/2星98-102%/1星96-100%）随机，`max_extra_stats` 即 5 星上限；装备总星级由各附加属性星级平均值反推（下取整） |
| 2026-07-02 | 强化收益重做：每级 +1% 初始属性（原 +10%），`new_base = initial + int(initial×0.01×enhance_level)`；强化成功每次全服广播（原仅每 +10 级）；新增「强化系统」章节 |

## 工作台装备设计系统

设计师账号（`is_designer=True`）可通过工作台 → 装备设计系统对 `data/equipment_sets/` 下的装备模板进行增删改查和测试生成。

### 访问入口

- 主页：`/workbench/equip_design`
- 需要设计师权限，非设计师自动跳转回场景

### 功能与路由

| 路由 | 方法 | 功能 |
|------|------|------|
| `/workbench/equip_design` | GET | 主页面：按套装分组浏览所有装备，显示数据文件列表 |
| `/workbench/equip_view/<template_id>` | GET | 查看单件装备详情（属性范围预览、来源文件） |
| `/workbench/equip_add` | GET/POST | 添加单件装备（选择写入已有文件或新建文件） |
| `/workbench/equip_add_set` | GET/POST | 添加套装（勾选启用部位，统一设置套装属性） |
| `/workbench/equip_edit/<template_id>` | GET/POST | 编辑已有装备（仅 equipment_sets 目录内的可编辑） |
| `/workbench/equip_delete/<template_id>` | GET/POST | 删除装备（二次确认） |
| `/workbench/equip_test/<template_id>` | GET/POST | 单件装备随机生成测试（指定品质/星级/数量） |
| `/workbench/equip_test_set/<set_name>` | GET/POST | 套装随机生成测试（生成整套+属性汇总） |
| `/workbench/equip_set/<set_name>` | GET | 查看套装所有部件 |
| `/workbench/equip_file/<filename>` | GET | 查看数据文件内容 |

### 关键业务规则

#### 神器品质限制
- 神器装备（`is_artifact: true`）测试生成时品质固定为"神器"，品质选择框只有"神器"
- 非神器装备测试生成时不能选"神器"品质，若强行指定则自动降级为"史诗"
- 神器套装（全件 `is_artifact: true`）品质固定"神器"；非神器套装不能选"神器"
- 随机生成时：神器→固定神器；非神器→从普通/精良/卓越/史诗中随机

#### 未分类装备
- 无 `set_name` 的装备（来自 `equipment_templates.json` 的测试神器、任务铁剑、婚戒等）归入"未分类"
- 未分类装备无法使用套装测试生成，但每件提供单独的"测试"按钮
- 未分类装备不在 `equipment_sets/` 目录中，无法编辑/删除

#### 新建文件规则
- 文件名只允许小写英文、数字、下划线，必须字母开头（正则 `^[a-z][a-z0-9_]*$`）
- 不允许中文、大写字母、数字开头、特殊字符
- 禁止使用 `equipment_templates.json`（系统基础文件）
- 与已有文件重名时拒绝
- `.json` 后缀自动补全
- 命名风格参考：`chulong_set` / `baopi_set` / `artifact_weapons` / `craft_accessories`

### 数据操作范围
- **只修改** `data/equipment_sets/` 下的 JSON 文件
- **不触碰** `data/equipment_templates.json`（基础模板文件）
- 增删改操作会同步刷新 `DataService._cache['equipment_templates']` 缓存
- 删除操作有二次确认页面

### 关键代码位置

| 文件 | 说明 |
|------|------|
| `blueprints/workbench.py` | 装备设计系统所有路由和辅助函数 |
| `templates/workbench/equip_*.html` | 10个装备设计模板 |
| `data/equipment_sets/*.json` | 装备模板数据（22个文件） |
| `services/data_service.py` | `_generate_extra_stats()` 额外属性生成、`create_equipment_instance()` 实例创建 |
| `services/equipment_generator.py` | `EquipmentGenerator` 品质/星级随机逻辑 |

## 工作台怪物设计系统

设计师账号（`is_designer=True`）可通过工作台 → 怪物设计系统对 `data/monsters.json` 和 `data/copy_monsters.json` 中的怪物数据进行增删改查和战斗/掉落测试。

### 访问入口

- 主页：`/workbench/monster_design`
- 需要设计师权限，非设计师自动跳转回场景

### 功能与路由

| 路由 | 方法 | 功能 |
|------|------|------|
| `/workbench/monster_design` | GET | 主页面：按类型分组浏览（世界怪物/副本怪物/NPC），按等级排序 |
| `/workbench/monster_view/<monster_id>` | GET | 查看怪物详情（属性、技能、掉落配置、品质权重实际生效值、复活时间） |
| `/workbench/monster_add` | GET/POST | 添加怪物（选择写入 monsters.json 或 copy_monsters.json） |
| `/workbench/monster_edit/<monster_id>` | GET/POST | 编辑已有怪物 |
| `/workbench/monster_delete/<monster_id>` | GET/POST | 删除怪物（二次确认） |
| `/workbench/monster_test/<monster_id>` | GET/POST | 战斗/掉落模拟测试（指定玩家等级和模拟次数，展示掉落结果+统计汇总） |

### 怪物数据文件

| 文件 | 内容 | 说明 |
|------|------|------|
| `data/monsters.json` | 474条 | 世界怪物 + NPC，添加时选择此文件 |
| `data/copy_monsters.json` | ~40条 | 副本怪物 + NPC，添加时选择此文件 |
| 两文件合并缓存到 `DataService._cache['monsters']` | — | 增删改后直接刷新此缓存 |

### 怪物分类规则（列表页）

- **世界怪物**：`killable=True` 且 `is_copy=False` 且 `copy_only=False`
- **副本怪物**：`killable=True` 且 (`is_copy=True` 或 `copy_only=True`)
- **NPC**：`killable=False`，不显示测试按钮

### 怪物 JSON 完整字段

```json
{
  "name": "人妖",
  "level": 10,
  "is_elite": false,
  "killable": true,
  "immortal": false,
  "description": "人妖",
  "base_stats": { "health": 500, "mana": 125, "attack": 35, "defense": 17, "crit_rate": 0.05, "dodge_rate": 0.03 },
  "skills": ["normal_attack"],
  "drops": {
    "equipment_drop": {
      "drop_rate": 0.15,
      "templates": ["chulong_sword_1", "chulong_helmet_1"],
      "rarity_weights": { "common": 50, "uncommon": 30, "rare": 15, "epic": 4, "legendary": 0 }
    },
    "items": { "potion_heal": 0.2, "potion_mana": 0.1 },
    "money": { "min": 25, "max": 75 },
    "experience": 100
  },
  "is_divine_beast": false,
  "is_copy": false,
  "copy_only": false,
  "max_health": 100
}
```

可选字段：`respawn_time`(秒)、`guaranteed_items`(数组)、`copy_dungeon_id`、`copy_stage`、`copy_final_boss`(bool)、`copy_role`、`drops.equipment_drop.artifact_template`、`drops.equipment_drop.artifact_drop_rate`

### 关键业务规则

#### 精英怪品质限制（核心规则）

- **非神兽精英怪**：不能设置神器(`legendary`)品质权重，提交时自动归零，前端输入框自动禁用
- **神兽**：可以有神器权重和独立神器掉落(`artifact_template`/`artifact_drop_rate`)
- **运行时过滤**：`Monster._sanitize_monster_rarity_weights()` 在实际掉落时过滤品质
  - 普通怪只出普通/精良
  - 精英怪只出精良/卓越/史诗
  - 神兽可出全部品质含神器
- **数据修复**：2026-06-27 已将 130 个非神兽精英的 `legendary` 权重从 5 改为 0

#### 掉落机制说明

- **装备掉落率**(`drop_rate`)：每次击杀先判定是否触发装备掉落，触发后从掉落池按品质权重随机抽一件
- **物品掉落**：每件物品独立概率判定，可与装备掉落同时发生
- **神器掉落**：神兽专属，独立于装备掉落另行判定
- **查看页**同时展示"数据中的品质权重"和"实际生效品质权重"（经过 `_sanitize` 过滤后），如有被过滤品质则红色警告

#### 复活时间

- `respawn_time` 字段：自定义复活秒数，0 = 由系统根据区域自动计算
- `WorldBossService._get_respawn_time()` 优先读 `respawn_time`，否则按区域推导（神兽600秒、虎牢关360秒等）
- 查看页显示实际复活时间（调用 `WorldBossService._get_respawn_time` 计算）

#### 装备选择器（添加/编辑页）

三种方式添加装备到掉落池：
1. **按套装添加**：下拉框列出22个套装（含等级范围、件数、神器标记），点击"添加整套"一键追加
2. **按等级筛选**：输入最低/最高等级，筛选范围内装备，点击追加（最多显示50条）
3. **搜索添加**：输入名称或ID模糊搜索，点击追加

选择器数据由 `_build_picker_data()` 构建，返回 `item_choices`(361物品)、`eq_choices`(142装备模板)、`set_index`(22套装索引)

#### Jinja2 字典键冲突

- `monster_index` 用 `dungeon` 而非 `copy`（`dict.copy()` 是内置方法，Jinja2 点号优先解析属性）
- `monster.drops['items']` 用方括号访问（`dict.items()` 同理）
- `loot_preview` 中用 `dropped_items` 而非 `items`

### 数据操作范围

- **可修改** `data/monsters.json` 和 `data/copy_monsters.json`
- 增删改操作同步刷新 `DataService._cache['monsters']` 缓存
- 删除操作有二次确认页面
- NPC 类怪物不显示测试按钮

### 战斗/掉落模拟

- 使用 `Monster.from_dict()` + `get_loot()` / `get_money_drop()` / `get_experience_drop()`
- 与实际战斗逻辑一致（含品质权重过滤、神器独立掉落判定）
- 测试页底部统计汇总：装备掉落率%、物品掉落率%

### 关键代码位置

| 文件 | 说明 |
|------|------|
| `blueprints/workbench.py` | 怪物设计系统所有路由、辅助函数（`_build_monster_index`、`_find_monster_source`、`_simulate_monster_battle`、`_build_monster_from_form`、`_build_picker_data`） |
| `templates/workbench/monster_*.html` | 6个怪物设计模板 |
| `data/monsters.json` | 世界怪物+NPC数据（474条） |
| `data/copy_monsters.json` | 副本怪物+NPC数据（~40条） |
| `models/monster.py` | `Monster` 类、`_sanitize_monster_rarity_weights()`、`get_loot()`、`MONSTER_ALLOWED_RARITIES` |
| `services/world_boss_service.py` | 精英怪复活时间计算 `_get_respawn_time()` |
| `services/data_service.py` | 怪物数据加载/缓存 `get_monsters()`/`get_monster()` |

## 工作台物品设计系统

设计师账号（`is_designer=True`）可通过工作台 → 物品设计系统对 `data/items.json` 中的物品数据进行增删改查和使用效果测试。

### 访问入口

- 主页：`/workbench/item_design`
- 需要设计师权限，非设计师自动跳转回场景

### 功能与路由

| 路由 | 方法 | 功能 |
|------|------|------|
| `/workbench/item_design` | GET | 主页面：按类型分组浏览（材料/药水/消耗品/宝箱/其他/VIP/任务/装备/物品） |
| `/workbench/item_view/<item_id>` | GET | 查看物品详情（基本信息、使用条件、使用效果预览、完整JSON） |
| `/workbench/item_add` | GET/POST | 添加物品（基本信息表单 + usage_condition/usage_effect JSON编辑） |
| `/workbench/item_edit/<item_id>` | GET/POST | 编辑已有物品 |
| `/workbench/item_delete/<item_id>` | GET/POST | 删除物品（二次确认） |
| `/workbench/item_test/<item_id>` | GET/POST | 使用效果模拟测试（随机效果实际模拟，固定效果直接展示） |

### 物品数据文件

| 文件 | 内容 | 说明 |
|------|------|------|
| `data/items.json` | 361条 | 所有物品数据，增删改直接操作此文件 |
| 缓存 `DataService._cache['items']` | — | 增删改后直接刷新此缓存 |

### 物品分类（9种类型）

| 类型 | type值 | 数量 | 说明 |
|------|--------|------|------|
| 材料 | material | 179 | 打造/任务材料，最常见类型 |
| 消耗品 | consumable | 73 | 银两包、血石、活力卡、扩展卷等 |
| 其他 | other | 46 | 大喇叭、药丸、改名卡、强化符等 |
| 药水 | potion | 27 | 临时增益药水 |
| 宝箱 | chest | 15 | 礼包/宝匣，含装备生成器 |
| VIP | vip | 9 | 诸侯令 |
| 任务 | quest | 6 | 任务物品，不可使用不可出售 |
| 装备 | equipment | 5 | 预定义装备（史诗戒指等） |
| 物品 | item | 1 | 扩展卷（极少使用） |

### 物品 JSON 完整字段

```json
{
  "name": "物品名称",
  "type": "material|potion|consumable|chest|other|vip|quest|equipment|item",
  "description": "描述文本",
  "price": 100,
  "sell_price": 50,
  "currency": "yuanbao|jinzu",
  "is_usable": true,
  "is_permanent_buff": false,
  "can_bulk_use": false,
  "capacity": 0.1,
  "usage_condition": {
    "level_required": 10,
    "required_items": { "chest_key": 1 }
  },
  "usage_effect": {
    "stat_changes": { "experience": 100, "gold": 50 },
    "stat_changes_rng": { "experience": [100, 200], "gold": [200, 500] },
    "effect_descriptions": { "experience": "获得{value}点经验" },
    "temp_effects": [{ "stat": "attack", "rate": 0.1, "duration": 300, "effect_name": "攻击秘药" }],
    "grant_title": "prefix迷茫",
    "grant_gold": 100000,
    "grant_item": ["item_id", 1],
    "random_one_of": ["potion_health", "potion_mana"],
    "random_items": [{ "item_id": "craft_huangyangmu", "max_count": 4, "chance": 0.6, "guaranteed_count": 1 }],
    "item_changes": { "chest_key": -1 },
    "equipment_generators": [{ "count": 1, "chance": 1.0, "template_ids": [...], "rarity_weights": {...}, "star_weights": {...} }],
    "generate_equipment": { "template_id": "xxx", "rarity_range": ["普通","精良","卓越","史诗"] },
    "special": "enhance_lucky|rename",
    "vip_days": 1,
    "restore_vitality": 10,
    "expand_backpack": 5,
    "expand_warehouse": 5,
    "grant_lieutenant": "adou",
    "random_soul": true,
    "peace_status": 300
  }
}
```

必填字段：`name`, `type`, `description`, `price`, `is_usable`, `capacity`
可选字段：`sell_price`, `currency`, `is_permanent_buff`, `can_bulk_use`, `usage_condition`, `usage_effect`

### 关键业务规则

#### 表单设计策略

- **基本信息字段**用表单控件（文本框/数字框/下拉框/复选框），便于快速编辑
- **usage_condition 和 usage_effect** 用 JSON 文本框编辑，因为：
  - usage_effect 有 20 种可能的键，每种键的值结构不同
  - equipment_generators 等嵌套结构复杂（数组→对象→权重字典）
  - 直接编辑 JSON 更灵活，不易遗漏字段
- 添加页提供 JSON 示例模板，方便参考

#### 使用效果测试

- **固定效果**（stat_changes, grant_gold, grant_title 等）：每次结果相同，直接展示
- **随机效果**（stat_changes_rng, random_one_of, random_items, equipment_generators, generate_equipment, random_soul）：每次模拟做实际随机
- 装备生成调用 `EquipmentGenerator.generate_from_template()`，与实际游戏逻辑一致
- 模拟不写入数据库，仅预览效果

#### usage_effect 20 种键

| 键 | 类型 | 说明 |
|----|------|------|
| stat_changes | {stat: int} | 固定属性变化 |
| stat_changes_rng | {stat: [min, max]} | 随机属性变化（范围内） |
| effect_descriptions | {stat: "text"} | 效果描述文本，{value}占位 |
| temp_effects | [{stat, value, rate, duration, effect_name}] | 临时增益效果 |
| grant_title | string | 授予称号ID |
| grant_gold | int | 直接给银两 |
| grant_item | [item_id, count] | 直接给指定物品 |
| random_one_of | [item_id, ...] | 随机选一个物品 |
| random_items | [{item_id, max_count, chance, guaranteed_count}] | 概率物品掉落 |
| item_changes | {item_id: int} | 物品变动（负数=扣除） |
| equipment_generators | [{count, chance, template_ids, rarity_weights, star_weights, ...}] | 装备生成器 |
| generate_equipment | {template_id, rarity_range} | 指定模板生成装备 |
| special | string | 特殊效果（enhance_lucky/rename） |
| vip_days | int | VIP天数 |
| restore_vitality | int | 恢复活力值 |
| expand_backpack | int | 扩展背包容量 |
| expand_warehouse | int | 扩展仓库容量 |
| grant_lieutenant | string | 授予副将（pinyin ID） |
| random_soul | bool | 随机副将魂魄 |
| peace_status | int | 免战状态（分钟） |

#### stat_changes 可修改属性

health, mana, experience, gold, honor, yuanbao, jinzu, pill_attack, pill_defense, pill_max_health, pill_max_mana, blood_reserve, mana_reserve

### 数据操作范围

- **只修改** `data/items.json`
- 增删改操作同步刷新 `DataService._cache['items']` 缓存
- 删除操作有二次确认页面
- 添加时检查物品ID唯一性

### 关键代码位置

| 文件 | 说明 |
|------|------|
| `blueprints/workbench.py` | 物品设计系统所有路由、辅助函数（`_build_item_index`、`_build_item_from_form`、`_simulate_item_use`、`_load_item_data`、`_save_item_data`） |
| `templates/workbench/item_*.html` | 6个物品设计模板 |
| `data/items.json` | 物品数据（361条） |
| `services/item_service.py` | `ItemService.use_item()` 物品使用逻辑（20种效果处理） |
| `services/data_service.py` | 物品数据加载/缓存 `get_items()`/`get_item()`/`get_item_effect_hint()` |
