# 战斗系统公式和规则

## 核心伤害公式（统一乘法模型）

所有伤害路径（玩家打怪/怪物打玩家/PK双方/副将）统一用此公式，由 `BattleService._compute_damage(atk, defense, coefficient, min_damage)` 实现：

```
最终伤害 = atk × (1 + atk / max(1, defense)) × coefficient
```

- `coefficient`：伤害系数。普攻 = 1.0；技能 = `damage_rate`（见技能章）
- `max(1, defense)`：防除零。defense≤0 时按 1 计，此时 atk/1 项会让伤害暴涨（低防单位受高攻打击会爆伤，符合"破甲"直觉，但怪物防御须与玩家攻击同量级才平衡）
- `min_damage`：保底。**仅怪物打玩家保留等级保底**（普通怪=等级，精英=等级×2）；玩家/副将/PK 无保底（min_damage=0，但公式天然 ≥1）
- 暴击：`× 1.5`（怪物暴击原 ×2，已统一为 ×1.5）
- 闪避：伤害归 0
- 全部 `int()` 向下取整

### 数值特性（设计注意）

- 当 `atk ≪ def`：`atk/def` 项趋 0，伤害≈`atk×coefficient`，防御有效压制攻击
- 当 `atk ≈ def`：伤害≈`2×atk×coefficient`
- 当 `atk ≫ def`：`atk/def` 项爆炸，伤害远超 atk——**防御形同虚设**。因此怪物防御值必须随玩家攻击力同步增长，否则高战玩家会秒杀低防怪

## 一、普通攻击公式

### 玩家攻击怪物
```
coefficient = 1.0
命中: random() >= monster.dodge_rate
damage = _compute_damage(玩家攻击力, 怪物防御力, 1.0)
暴击: random() <= 玩家暴击率 → damage = int(damage × 1.5)
怪物被混乱时: damage = int(damage × 0.5)   # 受击减半
闪避时: damage = 0
```

### 怪物攻击玩家
```
coefficient = 1.0
min_damage = 怪物等级 (普通怪) 或 怪物等级×2 (精英怪)
命中: random() >= 玩家闪避率
damage = _compute_damage(怪物攻击力, 玩家防御力, 1.0, min_damage)
暴击: × 1.5
闪避时: 0
怪物被混乱时: 本回合无法行动，伤害=0
```

### 副将攻击怪物
```
coefficient = 1.0
damage = _compute_damage(副将攻击力, 怪物防御力, 1.0)
暴击 = 无 (副将不暴击)
闪避时: 0
```

### 怪物攻击副将（前置位）
```
伤害计算同"怪物攻击玩家"（用副将所在格的防御逻辑：怪物攻击力 vs 玩家防御力）
副将承受全部伤害
副将死亡时，溢出伤害由玩家承受
```

## 二、技能伤害公式

### 主动技能
```
coefficient = damage_rate = base_damage_rate + damage_rate_per_level × (技能等级 - 1)
破甲技能(pierce_defense_pct): effective_def = int(defense × (1 - pierce_pct))，例如破甲刺无视10%防
每击: damage = _compute_damage(玩家攻击力, effective_def, damage_rate)
       暴击 ×1.5；目标被混乱 ×0.5
连击技能(hits>1): 每击独立判定命中/暴击，总伤害=各击之和
魔法消耗 = base_mana_cost + mana_cost_per_level × (技能等级 - 1)
```

### 技能类型
- **active**：战斗中使用，消耗魔法
- **passive**：被动加成（atk/def/hp/mp为比率加成，crit/dodge为固定加成）

## 三、属性计算公式

### 玩家有效属性
```
有效攻击力 = 基础攻击 + 装备加成 + 被动技能加成 + 称号加成 + 军衔加成 + 丹药加成
有效防御力 = 基础防御 + 装备加成 + 被动技能加成 + 称号加成 + 丹药加成
有效生命上限 = 基础生命 + 装备加成 + 被动技能加成 + 称号加成 + 丹药加成
有效魔法上限 = 基础魔法 + 装备加成 + 被动技能加成 + 称号加成 + 丹药加成
有效暴击率 = 基础暴击 + 装备加成 + 被动技能加成 + 称号加成 + 副将加成
有效闪避率 = 基础闪避 + 装备加成 + 被动技能加成 + 称号加成 + 副将加成
```

### 装备属性加成
- 基础属性（base_stats）：直接加算；强化后 base_stats = 初始属性 + int(初始属性 × 0.01 × enhance_level)（每级 +1%，向下取整，上限 +50）
- 附加属性（extra_stats）：直接加算
- 所有品质装备属性均参与计算（包括神器）
- 部位基础属性规则见 `monster_equipment_drop_rules.md`

## 三半、战斗状态效果

技能命中后可施加状态效果，由 `BattleService._apply_skill_effect` 处理。状态以"剩余回合数"计，回合结束时递减。

### 效果类型

| effect_type | 触发概率字段 | 持续 | 效果 |
| --- | --- | --- | --- |
| confuse | effect_chance | effect_rounds(默认3) | 目标无法普攻/技能/撤退；且受击伤害减半 |
| silence | effect_chance | effect_rounds(默认3) | 目标无法使用技能（可普攻/撤退） |
| bleed | effect_chance | effect_rounds(默认3) | 每回合扣 `int(施法者攻击力 × effect_value)` 血，持续 effect_rounds 回合 |
| lifesteal | 1.0（必触发） | 即时 | 施法者回复 `int(造成伤害 × effect_value)` 生命 |
| pierce | — | 即时 | `pierce_defense_pct` 无视目标防御百分比（破甲刺=10%），写法不同：直接在技能 JSON 设 `pierce_defense_pct: 0.10`，不配 effect_type |

### 状态存储位置

- **玩家身上**（持久化列，PVE/PK 通用）：`status_confuse_rounds`、`status_silence_rounds`、`status_bleed_rounds`、`status_bleed_value`
- **怪物身上**（怪物非 ORM，存于 `current_encounter` JSON 的 `monster_status` 字段）：`{confuse: 回合数, silence: 回合数, bleed: {rounds, value}}`

### 回合结算顺序

1. 玩家行动（攻击/技能，命中后施加效果）
2. 副将攻击
3. 怪物反击（怪物混乱则跳过）
4. **状态递减**：`_tick_monster_status`（怪物流血即时扣血）+ `_tick_player_status`（玩家混乱/封魔回合-1）；PK 用 `_tick_pk_bleed` 结算双方流血

### 关键代码

- 公式：`BattleService._compute_damage`
- 效果施加：`BattleService._apply_skill_effect`
- 玩家状态：`_player_is_confused` / `_player_is_silenced` / `_tick_player_status`
- 怪物状态：`_get_monster_status` / `_set_monster_status` / `_tick_monster_status`
- PK 流血：`_tick_pk_bleed`

## 四、战斗流程

### 进入战斗（start_pve）
1. 检查玩家是否已在战斗中
2. 从当前位置怪物列表中过滤可击杀怪物
3. 随机选择一只怪物
4. 世界BOSS检查：是否在复活中
5. 世界BOSS使用共享血量，普通怪使用模板血量
6. 保存遭遇数据到 `current_encounter`

### 攻击流程（player_attack / use_skill）
1. 玩家攻击怪物（计算伤害、暴击、闪避）
2. 世界BOSS：同步伤害到 `WorldBossService` 共享状态
3. 副将攻击（如有）
4. 检查怪物是否死亡 → 处理击杀
5. 怪物反击（前置副将承受，否则攻击玩家）
6. 检查玩家是否死亡 → 处理战败

### 逃跑（flee）
- 普通怪：50% 成功率
- 精英怪：30% 成功率
- 逃跑失败则怪物攻击一次
- 世界BOSS逃跑不影响BOSS血量

### 击杀处理（_handle_monster_defeat）
1. 计算金币和经验掉落（VIP经验加成）
2. 增加击杀计数（普通/精英分别计数）
3. 随机掉落装备或物品
4. 普通怪掉落绑定，精英怪掉落非绑定
5. 清除 `current_encounter`
6. 世界BOSS：标记 `is_alive=False`，记录击败时间，开始复活倒计时

## 五、世界BOSS规则

### 精英怪分类：世界BOSS vs 个人精英怪

| 特性 | 普通怪 | 个人精英怪（副本内） | 世界BOSS（副本外精英） |
|------|--------|---------------------|----------------------|
| 血量 | 个人专属 | 个人专属（encounter中） | 全局共享（WorldBossService） |
| 挑战 | 单人 | 只能自己打 | 多人可同时攻击 |
| 退出重进 | 满血新怪 | 继承上次已扣血量 | 继承当前血量 |
| 死亡后重打 | 满血新怪 | 继承上次已扣血量 | 等待复活 |
| 击杀 | 谁打死归谁 | 个人独立击杀 | 最后击杀者得奖励 |
| 击败后 | 立即刷新 | 个人进度记录 | 进入复活倒计时 |
| 物品绑定 | 绑定 | 非绑定 | 非绑定 |
| 逃跑成功率 | 50% | 30% | 30% |
| 复活公告 | 无 | 无 | 有（系统频道广播） |

### 判断逻辑
- 怪物数据中 `is_copy` 或 `copy_only` 或 `copy_dungeon_id` 任一为 true → 个人精英怪
- `is_elite=true` 且无副本标记 → 世界BOSS
- `WorldBossService.init_bosses()` 自动排除副本精英怪
- `start_pve` 中对副本精英怪跳过世界BOSS血量同步

### 与普通怪的区别
| 特性 | 普通怪 | 世界BOSS（精英怪） |
|------|--------|-------------------|
| 血量 | 个人专属 | 全局共享 |
| 挑战 | 单人 | 多人可同时攻击 |
| 退出重进 | 满血新怪 | 继承当前血量 |
| 击杀 | 谁打死归谁 | 最后击杀者得奖励 |
| 击败后 | 立即刷新 | 进入复活倒计时 |
| 物品绑定 | 绑定 | 非绑定 |
| 逃跑成功率 | 50% | 30% |

### 复活时间
| 地图类型 | 复活时间 |
|----------|---------|
| 国家地图（北平/柴桑/成都等） | 60秒 |
| 下邳/汉中/江陵/洛阳 | 120秒 |
| 粮草营（下邳南区） | 180秒 |
| 寒门（洛阳北区） | 240秒 |
| 虎牢关（洛阳北区） | 360秒 |
| 神兽（is_divine_beast） | 600秒 |

### 复活公告
- 世界BOSS/神兽复活时，`_check_respawn` 自动调用 `_announce_respawn`
- 神兽格式：`{description}在{area_name}{loc_name}复活了，请速速前往击杀！`
- 精英怪格式：`【精】{name}在{area_name}{loc_name}复活了，请速速前往击杀！`
- 消息通过 `DataService.broadcast_system()` 发送，存入 `chat_messages` 表，类型为 `system`
- 副本精英怪（个人精英怪）不触发复活公告

### 共享状态
- 存储在 `WorldBossService._bosses` 类变量中
- 每次攻击同步伤害到共享状态
- 击败时记录时间戳，到期自动复活
- 参与人数 = 其他参与攻击的玩家数（不含自己）

### 界面显示
- 场景：复活中显示 `【精】名称(等级精,复活中)` 不可点击
- 战斗：显示 `『【精】名称』(等级) 玩家:N`
- 击败提示：`[世界BOSS已被击败，N秒后复活]`

## 六、掉落规则（详见 monster_equipment_drop_rules.md）

### 金币掉落
```
金币 = random(min, max)  // 从怪物配置的 money.min 到 money.max
```

### 经验掉落
```
基础经验 = 怪物配置的 experience
VIP经验加成 = 基础经验 × VIP经验倍率
最终经验 = 基础经验 + VIP经验加成
```

### 装备掉落
- 受 `drop_rate` 控制（普通怪0.15，精英怪0.3）
- 品质权重见 `monster_equipment_drop_rules.md`
- 非神器模板永远不会出神器品质

### 材料掉落（精英怪专属）
- 25-40级精英怪：随机掉落碎皮/麻布/黄杨木/黄铜矿，概率随等级递增
- 41-60级精英怪：随机掉落硬皮/棉布/沉香木/黑铁矿，概率随等级递增

## 七、规则变更记录

| 日期 | 变更内容 |
|------|---------|
| 2026-06-06 | 初始版本：总结战斗公式、流程、世界BOSS规则 |
| 2026-06-06 | 修正怪物攻击最低伤害：普通怪=等级，精英怪=等级×2 |
| 2026-06-06 | 修正 effective_crit_rate/dodge_rate 未包含装备加成 |
| 2026-06-06 | 修正 _get_equipment_stat_sum 对 crit_rate/dodge_rate 返回 float 而非 int |
| 2026-06-07 | 新增个人精英怪（副本精英）vs 世界BOSS的区分规则 |
| 2026-06-07 | 新增神兽/精英怪复活公告机制 |
| 2026-07-02 | 装备强化收益调整：每级 +1% 初始属性（原 +10%），成功每次全服广播（原每 +10 级广播） |
| 2026-07-02 | **伤害公式重构为统一乘法模型** `atk×(1+atk/max(1,def))×coefficient`，废弃减法模型。4 条路径（玩家打怪/怪物打玩家/PK/副将）统一用 `BattleService._compute_damage`。怪物暴击由 ×2 统一为 ×1.5。详见核心伤害公式章 |
| 2026-07-02 | **新增战斗状态效果系统**：混乱/封魔/流血/吸血/破甲。玩家状态存于新列 `status_confuse_rounds`/`status_silence_rounds`/`status_bleed_rounds`/`status_bleed_value`；怪物状态存于 `current_encounter.monster_status`。详见「三半、战斗状态效果」章。迁移脚本 `scripts/migrate_add_status_columns.py` |
