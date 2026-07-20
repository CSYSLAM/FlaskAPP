# 副将系统设计规则

## 属性公式（六项统一）

所有属性统一公式：`base × level × 悟性倍率 × 品质倍率 × 强化加成`

- **HP/MP/ATK/DEF**: `math.ceil(base * level * enlightenment_mult * quality_mult * reinforce_mult)`
- **暴击/闪避**: `base * level * enlightenment_mult * quality_mult * reinforce_mult`（不取整，返回浮点率值）

### 倍率表

| 维度 | 范围 | 公式 | 极值 |
|------|------|------|------|
| 品质 quality | 0-20 | `1.0 + quality * 0.005` | 0→1.00, 20→1.10 |
| 悟性 enlightenment | 0-10 | `1.0 + enlightenment * 0.02` | 0→1.00, 10→1.20 |
| 强化 reinforce | 0-20 | `1.0 + reinforce * 0.015` | 0→1.00, 20→1.30 |

满倍率 = 1.10 × 1.20 × 1.30 = 1.716

### 品质名称

0-9=普通, 10-16=优良, 17-19=杰出, 20=完美

## base 值来源

- **名将副将**（tier 1-3）: 创建时从 `LIEUTENANT_DATA` 取 `base_*` 字段写入 DB（`grant_lieutenant_from_soul`）
- **普通副将**（tier 0）: `base_*` 为 None，走 `CLASS_BASE_STATS` / `CLASS_BASE_CRIT` / `CLASS_BASE_DODGE` 默认值
- **工作台设计**: 可手动指定 `base_*`，优先于职业默认

## 职业默认 base 值

| 职业 | HP | MP | ATK | DEF | 暴击(每级) | 闪避(每级) |
|------|-----|-----|-----|-----|-----------|-----------|
| 战士 warrior | 60 | 5 | 8 | 12 | 0.00065 | 0.00050 |
| 刺客 assassin | 50 | 8 | 10 | 10 | 0.00080 | 0.00065 |
| 术士 mage | 40 | 15 | 12 | 6 | 0.00050 | 0.00040 |

## 名将档位与 base 值（LIEUTENANT_DATA）

18个名将分3档，暴击/闪避梯度：一级 > 二级 > 三级 > 普通

**一级名将**（3个，base属性×0.75，暴击×0.8）:

| 名将 | 职业 | HP | MP | ATK | DEF | 暴击 | 闪避 |
|------|------|-----|-----|-----|-----|------|------|
| 太史慈 | 术士 | 105 | 112 | 22 | 57 | 0.00128 | 0.00090 |
| 许褚 | 战士 | 126 | 37 | 19 | 71 | 0.00124 | 0.00086 |
| 周瑜 | 刺客 | 117 | 60 | 21 | 62 | 0.00160 | 0.00112 |

**二级名将**（6个）:

| 名将 | 职业 | HP | MP | ATK | DEF | 暴击 | 闪避 |
|------|------|-----|-----|-----|-----|------|------|
| 关平 | 术士 | 78 | 150 | 17 | 42 | 0.00110 | 0.00085 |
| 曹真 | 战士 | 94 | 50 | 14 | 53 | 0.00110 | 0.00085 |
| 小乔 | 刺客 | 87 | 80 | 16 | 46 | 0.00135 | 0.00105 |
| 大乔 | 术士 | 78 | 150 | 17 | 42 | 0.00110 | 0.00085 |
| 庞德 | 战士 | 94 | 50 | 14 | 53 | 0.00110 | 0.00085 |
| 刘封 | 刺客 | 87 | 80 | 16 | 48 | 0.00135 | 0.00105 |

**三级名将**（9个）:

| 名将 | 职业 | HP | MP | ATK | DEF | 暴击 | 闪避 |
|------|------|-----|-----|-----|-----|------|------|
| 阿斗 | 术士 | 39 | 150 | 9 | 21 | 0.00070 | 0.00055 |
| 廖化 | 战士 | 47 | 50 | 7 | 26 | 0.00075 | 0.00060 |
| 夏侯霸 | 刺客 | 43 | 80 | 8 | 23 | 0.00090 | 0.00072 |
| 赵广 | 战士 | 39 | 50 | 9 | 21 | 0.00070 | 0.00055 |
| 吴国太 | 战士 | 47 | 50 | 7 | 26 | 0.00075 | 0.00060 |
| 甄姬 | 刺客 | 43 | 80 | 8 | 23 | 0.00090 | 0.00072 |
| 王美人 | 术士 | 39 | 150 | 9 | 21 | 0.00070 | 0.00055 |
| 许攸 | 战士 | 47 | 50 | 7 | 26 | 0.00075 | 0.00060 |
| 乐进 | 刺客 | 43 | 80 | 8 | 23 | 0.00090 | 0.00072 |

## 创建与招募

- **名将**: 通过聚魂幡获得魂魄 → `grant_lieutenant_from_soul` 创建，品质0-9随机，悟性=0，强化=0
- **普通副将**: 通过招募令/银两 → `recruit` 创建，品质=0，tier=0，base_*全None走职业默认
- **聚魂幡概率**: 80%三级魂魄、19%二级、1%一级

## 副将技能系统

12个技能，3级（入门/进阶/精通），定义在 `services/lieutenant_service.py` `LIEUTENANT_SKILLS`，可持久化到 `data/lieutenant_skills.json`。

### 主动技能 active（3个，职业限定）

战斗中按 `trigger_rate`% 概率释放，消耗 `mana_cost` 副将魔法；蓝量不足降级为普攻。伤害走 `BattleService._compute_damage` 统一公式。

| skill_id | 名称 | 职业 | trigger_rate | mana_cost | 特殊效果 |
|----------|------|------|-------------|-----------|---------|
| combo | 连击 | 刺客 | [12,18,24] | [40,70,100] | 打两次，每次独立计算伤害 |
| smash | 猛击 | 战士 | [12,18,24] | [30,50,80] | 本回合攻+50%，damage_rate倍伤害，自身下2回合防御减半 |
| thunder | 天雷 | 术士 | [12,18,24] | [120,200,300] | damage_rate=[2.0,2.8,3.6]倍巨额伤害 |

### 触发技能 triggered（3个，职业限定）

主人受击时按 `trigger_rate`% 触发，前后置都可触发（只有挡刀限front）。

| skill_id | 名称 | 职业 | trigger_rate | 效果 |
|----------|------|------|-------------|------|
| absorb | 吸收 | 刺客 | [12,18,24] | 吸收absorb_rate=[10,15,20]%伤害 |
| heal_trigger | 回春 | 战士 | [10,15,20] | 回复主人生命上限heal_rate=[5,8,12]% |
| magic_shield | 法相 | 术士 | [10,15,20] | 护盾=主人当前魔法×shield_rate=[0.4,0.6,0.8] |

### 被动技能 passive（6个，通用）

出战即给主人加成。`bonus_value` 在 learn/upgrade 时已按等级从数组取好（如 `[5,8,11]` → 3级存11），`get_passive_bonus()` 直接使用不再乘level。

| skill_id | 名称 | bonus_type | bonus_value | 说明 |
|----------|------|-----------|-------------|------|
| sharp | 锐利 | attack | [5,8,11] | 副将攻击×%给主人 |
| protect | 护佑 | health | [5,8,13] | 副将生命×%给主人 |
| tough | 坚韧 | defense | [5,8,13] | 副将防御×%给主人 |
| magic | 法能 | mana | [5,8,13] | 副将魔法×%给主人 |
| brave | 勇猛 | crit | [5,8,11] | 副将暴击率×%给主人 |
| calm | 冷静 | dodge | [5,8,11] | 副将闪避率×%给主人 |

### 被动加成计算要点

`get_passive_bonus()` 中 `bonus_value` 处理逻辑：
- 数组（如 `[5,8,11]`）→ 按 `level-1` 索引取值
- 数字（如 `11`）→ 直接使用（learn/upgrade已按等级取好）
- **不再乘以 level**（旧bug已修复：之前错误地把已取好的值再乘level导致加成翻3倍）

## 系统播报

洗资质/提升悟性成功/强化成功时，系统播报 `XXX给副将【YYY】提升ZZZ成功，恭喜恭喜！`（失败不播报）

## 战斗集成

- `_lt_attack_monster(lt, monster, player)` 返回 `(damage, skill_name|None)`
- 副将战斗状态（猛击buff/debuff、法相护盾）存于 `player.current_encounter` JSON 的 `lt_status`，回合末由 `_tick_lt_status` 递减
- 副将进场时补满生命/魔法（`start_pve`）
- `class_required` 限定：主动/触发技能只能被对应职业副将学习

## 技能书与遗忘

- 36本技能书 `lt_skill_<id>_<level>`（12技能×3级）
- 学1级需50本入门、升2级需20本进阶、升3级需10本精通
- 遗忘技能消耗1个遗忘之章（50个残页合成1个）

## 工作台设计

`blueprints/workbench.py`（designer-only via `_require_designer()`）：
- `lieutenant_design` 列出所有副将
- `lieutenant_view/edit/delete` CRUD
- `lieutenant_skill_edit` / `lieutenant_skill_reset` 管理技能定义
- `lieutenant_damage_test` 单次伤害测试
- `lieutenant_battle_test` 回合制战斗模拟

## 关键文件

| 文件 | 内容 |
|------|------|
| `models/lieutenant.py` | Lieutenant模型、属性公式、倍率表、CLASS_BASE_* |
| `services/lieutenant_service.py` | LIEUTENANT_DATA(18名将)、LIEUTENANT_SKILLS(12技能)、招募/强化/悟性/技能逻辑 |
| `blueprints/lieutenant.py` | 副将路由 |
| `blueprints/workbench.py` | 工作台设计路由 |
| `data/lieutenant_skills.json` | 技能定义持久化（工作台编辑后写入） |
| `templates/lieutenant_detail.html` | 副将详情页 |
| `templates/lieutenant_skills.html` | 副将技能页 |
| `templates/workbench/lieutenant_view.html` | 工作台副将查看页 |
