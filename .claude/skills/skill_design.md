# 技能设计规则

主动技能定义在 `data/skills.json` 的 `active` 段，被动技能在 `passive` 段。由 `DataService.get_skill(skill_id)` 读取。

## 伤害公式

技能伤害走统一乘法模型（见 `combat_formulas.md`）：

```
每击伤害 = 玩家攻击力 × (1 + 玩家攻击力 / max(1, effective_def)) × damage_rate
effective_def = 怪物防御 × (1 - pierce_defense_pct)   # 破甲技能才减防
暴击 ×1.5，目标被混乱 ×0.5
连击(hits>1)：每击独立判定命中/暴击，总伤害求和
```

`damage_rate` 即"技能攻击伤害系数"，普攻为 100%(1.0)。

## 数值推导规则

技能 JSON 的 `base_damage_rate` / `damage_rate_per_level` 由设计稿的"基础伤害%(1级)"和"满级伤害%(10级)"反推：

```
base_damage_rate     = 基础伤害% / 100
damage_rate_per_level = (满级伤害% - 基础伤害%) / (max_level - 1) / 100
base_mana_cost       = 基础魔法
mana_cost_per_level  = (满级魔法 - 基础魔法) / (max_level - 1)
```

`max_level` 默认 10。`description_per_level` 文本应与推导出的每级增量一致。

### 取整规则

- **魔法消耗**：`mana_cost_per_level` 因除法常为小数（如 11.11），实际消耗计算时用 `int(round(base + per_level × (等级-1)))` 取整，保证 1级与满级正好是设计稿的整数（如封魔术 1级=100、10级=200，不会出现 199.99）。见 `battle_service.py` PVE/PK 两处 `mana_cost` 计算
- **伤害系数**：`damage_rate` 同样是浮点累加，但伤害最终 `int()` 取整，小数误差不影响结果，无需额外 round

## 技能 JSON 字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| name | string | 技能名 |
| skill_type | string | `active` / `passive` |
| class_required | string\|null | 职业限制（战士/刺客/术士），null=通用 |
| description | string | 技能描述（剧情向） |
| description_per_level | string | 升级提示文本，如"每级增加X%伤害、Y点耗魔" |
| base_damage_rate | float | 1级伤害系数（1.0=100%攻击力） |
| damage_rate_per_level | float | 每级伤害系数增量 |
| base_mana_cost | int | 1级魔法消耗 |
| mana_cost_per_level | float | 每级魔法消耗增量 |
| hits | int | 连击数，默认1 |
| max_level | int | 最大等级，默认10 |
| effect_description | string | 效果简述（展示用） |
| upgrade_exp_base | int | 升级经验基数 |
| upgrade_gold_base | int | 升级银两基数 |

### 特殊效果字段（可选，命中后触发）

| 字段 | 说明 |
| --- | --- |
| effect_type | `confuse`/`silence`/`bleed`/`lifesteal` 之一；破甲不用此字段 |
| effect_chance | 触发概率（0~1）。lifesteal 通常 1.0 |
| effect_rounds | 持续回合（confuse/silence/bleed，默认3） |
| effect_value | bleed 的流血比例（如0.20=施法者攻击×20%每回合）；lifesteal 的吸血比例（如0.15=造成伤害×15%） |
| pierce_defense_pct | 破甲比例（如0.10=无视10%防御），独立于 effect_type |

## 9 个主动技能（2026-07-02 重做数值）

| skill_id | 名称 | 职业 | 基础% | 满级% | 基础魔 | 满级魔 | hits | 特殊效果 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ten_slash | 十人斩 | 战士 | 98 | 118 | 50 | 170 | 1 | 30%混乱3回合（受击减半） |
| blood_drink | 血饮斩 | 战士 | 107 | 137 | 45 | 195 | 1 | 吸血15% |
| storm_kill | 暴风杀 | 战士 | 110 | 160 | 60 | 210 | 1 | 纯伤害 |
| poison_strike | 毒刃击 | 刺客 | 80 | 130 | 80 | 230 | 1 | 20%流血3回合(atk×20%/回合) |
| pierce | 破甲刺 | 刺客 | 90 | 140 | 50 | 200 | 1 | 无视10%防御 |
| double_hit | 二连击 | 刺客 | 25+25 | 62.5+62.5 | 60 | 660 | 2 | 两段独立判定 |
| seal_magic | 封魔术 | 术士 | 90 | 140 | 100 | 200 | 1 | 30%封魔3回合 |
| earth_fire | 地火术 | 术士 | 105 | 165 | 140 | 240 | 1 | 纯伤害 |
| thunder | 天雷术 | 术士 | 110 | 210 | 1100 | 2100 | 1 | 纯伤害（高额耗魔） |

> 二连击的 `base_damage_rate=0.25` 是**每段**系数，两段合计 1级=50%。满级每段 0.625，合计 125%。

## 状态效果实现要点

- **叠加规则：覆盖刷新**。重复施加同种状态时，直接用新值覆盖旧值（`=`赋值，非累加）：
  - 混乱/封魔：剩余回合数重置为本次 `effect_rounds`，不累加
  - 流血：整个覆盖——回合数重置为 `effect_rounds`，**流血伤害值也换成本次施法者攻击力 × effect_value**（旧 value 丢失）
  - 例：第1回合混乱3回合→第2回合再混乱，则第1~4回合都混乱（第2回合把剩余2刷新成3，再递减2次归零），不会累加成5或6回合
- **混乱(confuse)**：目标本回合无法行动；且受击伤害 `×0.5`。玩家混乱存 `status_confuse_rounds`；怪物混乱存 `encounter.monster_status.confuse`
- **封魔(silence)**：目标无法用技能（可普攻/撤退）。玩家存 `status_silence_rounds`；怪物存 `encounter.monster_status.silence`
- **流血(bleed)**：每回合扣 `int(施法者攻击力 × effect_value)`，持续 effect_rounds 回合。怪物流血存 `encounter.monster_status.bleed={rounds,value}`；PK 玩家流血存 `status_bleed_rounds`+`status_bleed_value`
- **吸血(lifesteal)**：即时回复，不存回合。回血受 `effective_max_health` 上限
- **破甲(pierce)**：`effective_def = int(defense × (1 - pierce_defense_pct))`，仅作用于该次技能

效果施加在 `BattleService._apply_skill_effect`，仅当技能命中且造成伤害(total_damage>0)时触发。

## 规则变更记录

| 日期 | 变更内容 |
| --- | --- |
| 2026-07-02 | 初始版本：技能伤害改用统一乘法模型；9 个主动技能按设计稿重做数值与描述；新增混乱/封魔/流血/吸血/破甲 5 种效果字段与实现 |
