# 装备设计规则

## 基础属性（base_stats）

- **每件装备最多只有1-2种基础属性**
- **一般装备只有1种基础属性**：
  - 武器 → `attack`（攻击）
  - 防具 → `defense`（防御）
- **厉害一点的装备有2种基础属性**（需在模板中明确指定），按部位固定搭配：
  - 头盔/衣服/裤子 → `defense` + `max_health`
  - 手套 → `attack` + `crit_rate`
  - 鞋子 → `dodge_rate` + `defense`
- 特殊饰品可以有 `attack` + `defense`（目前未实现，后续添加）

### 现有装备示例

| 装备 | 部位 | 基础属性 |
|------|------|---------|
| 雏龙长剑 | 武器 | attack |
| 雏龙头巾 | 头盔 | defense、max_health |
| 雏龙衣 | 衣服 | defense、max_health |
| 雏龙手套 | 手套 | attack、crit_rate |
| 雏龙鞋 | 鞋子 | dodge_rate、defense |

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

```
实际值 = max_extra_stats[属性] × (stat_stars / 5)
stat_stars = random(min(1, stars-1), min(5, stars+1))
```

每条附加属性有独立星级（2维数组：`[实际值, 属性星级]`），属性星级在装备星级±1范围内波动，范围控制在1-5。

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
    "slot": "weapon|helmet|armor|gloves|pants|shoes",
    "set_name": "套装名称",
    "level_required": 10,
    "class_required": null,
    "is_artifact": false,
    "base_stats": {
      "attack": 24
    },
    "max_extra_stats": {
      "attack": 15,
      "max_health": 60,
      "crit_rate": 0.05,
      "max_mana": 30,
      "defense": 8
    }
  }
}
```

## 装备部位（slots）

| 部位 | slot 值 | 1种基础属性 | 2种基础属性 |
|------|---------|------------|------------|
| 武器 | weapon | attack | - |
| 头盔 | helmet | defense | defense + max_health |
| 衣服 | armor | defense | defense + max_health |
| 手套 | gloves | attack | attack + crit_rate |
| 裤子 | pants | defense | defense + max_health |
| 鞋子 | shoes | dodge_rate | dodge_rate + defense |

## 打造系统

### 合成规则

- 基础材料：碎皮/麻布/黄杨木/黄铜矿（25-40级精英怪掉落）、硬皮/棉布/沉香木/黑铁矿（41-60级精英怪掉落）
- 合成成本：材料 + 金币 + 随机品质 + 随机星级
- 非神器套装打造产出：精良、卓越、史诗（不含神器）
- 神器套装打造产出：仅神器

### 品质权重（打造）

```json
{
  "uncommon": 40,  // 精良
  "rare": 35,      // 卓越
  "epic": 20,      // 史诗
  "legendary": 5   // 神器（非神器套装时排除）
}
```

## 规则变更记录

| 日期 | 变更内容 |
|------|---------|
| 2026-06-06 | 初始版本：从 monster_equipment_drop_rules.md 拆分出装备设计独立 skill |
| 2026-06-06 | 基础属性规则：每件1-2种，按部位固定搭配 |
| 2026-06-06 | 附加属性规则：品质→条数(普通1/精良2/卓越3/史诗4/神器5)，武器/防具/鞋护腿顺序 |
| 2026-06-06 | 神器规则：独立品质体系，非神器不出神器，神器只出神器 |
| 2026-06-06 | 鞋子/护腿优先闪避率替代暴击率 |