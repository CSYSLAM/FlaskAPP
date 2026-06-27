装备生成系统设计（通用模板与用法）

一、设计目标
- 统一入口：根据来源（怪物/宝箱/锻造/活动）生成装备的品质与星级。
- 神器与品质独立：模板 is_artifact=true 则直接为”神器”；否则在普通品质池（普通/精良/卓越/史诗）抽取。
- 可配置概率：调用方可自定义掉落概率、模板权重、品质权重、星级规则。
- 易扩展：保持对旧数据的兼容（仍支持 drops.equipment_templates 简写）。

二、核心接口
文件：`services/equipment_generator.py`

- 来源枚举：EquipmentSource = {monster, chest, forge, event}
- 关键方法：
  - generate(source, template_id, template_loader, rarity_weights?, star_range?, star_weights?) -> {template_id, rarity, stars, source}
  - generate_from_pool(source, template_pool, template_weights?, template_loader, rarity_weights?, star_range?, star_weights?) -> 同上

三、怪物掉落配置（新结构）
在 `data/monsters.json` 的 `drops` 中新增 `equipment_drop`，例如：

```json
{
  “drops”: {
    “equipment_drop”: {
      “drop_rate”: 0.35,
      “templates”: [“bronze_sword”, “training_dagger”, “apprentice_staff”],
      “template_weights”: {“bronze_sword”: 1, “training_dagger”: 1, “apprentice_staff”: 0.5},
      “rarity_weights”: {“普通”: 0.7, “精良”: 0.2, “卓越”: 0.09, “史诗”: 0.01},
      “rarity_weights_elite”: {“普通”: 0.4, “精良”: 0.3, “卓越”: 0.2, “史诗”: 0.1},
      “star_min”: 1,
      “star_max”: 5,
      “star_weights”: {“3”: 1, “4”: 0.6, “5”: 0.2}
    },
    “items”: { “potion_heal”: 0.3 },
    “money”: {“min”: 20, “max”: 40},
    “experience”: 30
  }
}
```

说明：
- drop_rate：本次击杀是否出装备的概率。
- templates/template_weights：装备模板池与权重。
- rarity_weights：普通怪的品质权重；rarity_weights_elite：精英怪的品质权重。
- star_range 或 star_weights：星级规则（任选一种，权重优先）。
- 兼容性：若不提供 equipment_drop，仍会读取旧的 `equipment_templates`，并按默认规则生成。

四、神器规则
- 模板 `is_artifact` 为 true 时，直接生成”神器”，跳过普通品质权重；
- 模板 `is_artifact` 为 false 时，最高仅到”史诗”。
- 怪物来源额外强约束：`EquipmentGenerator.generate_from_pool(source=monster, ...)` 必须排除神器模板，不能因为模板池混入 `is_artifact=true` 而掉出神器。
- 普通怪和精英怪都不允许出神器；神器只允许活动、宝箱、专门配置的特殊来源产出。
- 品质权重即使只传入子集，例如 `{common, uncommon}` 或 `{uncommon, rare, epic}`，也必须严格按该子集抽取，不能回退到默认全品质池。

五、宝箱/锻造/活动示例
调用统一接口 `EquipmentGenerator.generate` 或 `generate_from_pool`，将 source 设置为对应来源。

1）宝箱
```python
from services.equipment_generator import EquipmentGenerator, EquipmentSource
from models.equipment import Equipment

cfg = {
    “templates”: [“bronze_sword”, “leather_armor”, “warrior_ring”],
    “template_weights”: {“bronze_sword”: 1, “leather_armor”: 1, “warrior_ring”: 0.5},
    “rarity_weights”: {“普通”: 0.6, “精良”: 0.3, “卓越”: 0.09, “史诗”: 0.01},
    “star_weights”: {1: 0.15, 2: 0.35, 3: 0.3, 4: 0.15, 5: 0.05},
}

roll = EquipmentGenerator.generate_from_pool(
    source=EquipmentSource.CHEST,
    template_pool=cfg[“templates”],
    template_weights=cfg.get(“template_weights”),
    template_loader=Equipment.load_template,
    rarity_weights=cfg.get(“rarity_weights”),
    star_weights=cfg.get(“star_weights”),
)
if roll:
    equip = Equipment(roll[“template_id”], roll[“rarity”], roll[“stars”])
```

2）锻造
```python
forge_cfg = {
    “template_id”: “novice_sword”,
    “rarity_weights”: {“普通”: 0.2, “精良”: 0.4, “卓越”: 0.3, “史诗”: 0.1},
    “star_range”: (3, 5)
}

roll = EquipmentGenerator.generate(
    source=EquipmentSource.FORGE,
    template_id=forge_cfg[“template_id”],
    template_loader=Equipment.load_template,
    rarity_weights=forge_cfg.get(“rarity_weights”),
    star_range=forge_cfg.get(“star_range”),
)
equip = Equipment(roll[“template_id”], roll[“rarity”], roll[“stars”])
```

3）活动
```python
event_cfg = {
    “templates”: [“ancient_blade”, “bronze_sword”],
    “template_weights”: {“ancient_blade”: 0.05, “bronze_sword”: 0.95},
    “rarity_weights”: {“普通”: 0.0, “精良”: 0.0, “卓越”: 0.0, “史诗”: 1.0},
    “star_weights”: {5: 1.0}
}

roll = EquipmentGenerator.generate_from_pool(
    source=EquipmentSource.EVENT,
    template_pool=event_cfg[“templates”],
    template_weights=event_cfg.get(“template_weights”),
    template_loader=Equipment.load_template,
    rarity_weights=event_cfg.get(“rarity_weights”),
    star_weights=event_cfg.get(“star_weights”),
)
equip = Equipment(roll[“template_id”], roll[“rarity”], roll[“stars”])
```

六、在怪物逻辑中的使用
文件：`models/monster.py`，方法 `get_loot` 已接入新生成器，支持 `drops.equipment_drop`：

```12:45:models/monster.py
    def get_loot(self):
        # 先尝试装备掉落
        equip_cfg = self.drops.get(“equipment_drop”, {})
        drop_rate = equip_cfg.get(“drop_rate”, 0.0)
        if random.random() < drop_rate:
            pool = equip_cfg.get(“templates”, self.drops.get(“equipment_templates”, []))
            template_weights = equip_cfg.get(“template_weights”)
            rarity_weights = equip_cfg.get(“rarity_weights_elite” if self.is_elite else “rarity_weights”)
            star_range = None
            if “star_min” in equip_cfg or “star_max” in equip_cfg:
                star_range = (equip_cfg.get(“star_min”, 1), equip_cfg.get(“star_max”, 5))
            star_weights = equip_cfg.get(“star_weights”)

            roll = EquipmentGenerator.generate_from_pool(
                source=EquipmentSource.MONSTER,
                template_pool=pool,
                template_weights=template_weights,
                template_loader=Equipment.load_template,
                rarity_weights=rarity_weights,
                star_range=star_range,
                star_weights=star_weights,
            )
            if roll:
                return Equipment(roll[“template_id”], roll[“rarity”], roll[“stars”])
```

七、物品使用生成装备（generate_equipment效果）
文件：`services/item_service.py`

物品usage_effect中的generate_equipment配置：
```json
{
  “usage_effect”: {
    “generate_equipment”: {
      “template_id”: “wedding_diamond_ring”,
      “rarity”: “神器”,
      “rarity_range”: [“普通”, “精良”, “卓越”, “史诗”],
      “stars_range”: [1, 5]
    }
  }
}
```

处理逻辑：
```python
generate_equipment = usage_effect.get(“generate_equipment”)
if generate_equipment:
    template_id = generate_equipment.get(“template_id”)
    rarity = generate_equipment.get(“rarity”)
    rarity_range = generate_equipment.get(“rarity_range”)
    if rarity_range:
        rarity = random.choice(rarity_range)
    stars_range = generate_equipment.get(“stars_range”, [1, 5])
    stars = random.randint(int(stars_range[0]), int(stars_range[1]))
    
    equip = EquipmentService.generate_random_equipment(player.id, template_id, rarity, stars)
    DataService.add_item_to_inventory(player.id, equip.instance_id)
```

### 使用场景

| 物品 | 配置 | 生成装备 |
|------|------|----------|
| 新婚钻戒包 | rarity=”神器”, stars_range=[1,5] | 20级神器饰品（1-5星随机） |
| 新婚草戒包 | rarity_range=[“普通”,”精良”,”卓越”,”史诗”] | 20级饰品（品质随机） |

八、数据要点与默认值
- 非精英默认品质池：{“普通”: 1.0}
- 精英默认品质池：{“普通”:0.4, “精良”:0.3, “卓越”:0.2, “史诗”:0.1}
- 默认星级范围：(1,5)
- 模板 is_artifact=true 时强制”神器”
- 品质使用中文：普通/精良/卓越/史诗/神器（不是英文）

九、怪物掉落实现约束
- 普通怪默认回退品质只能是：`普通 / 精良`
- 精英怪默认回退品质只能是：`精良 / 卓越 / 史诗`
- `generate_from_pool` 在怪物来源下要先过滤 `is_artifact=true` 模板，再做模板抽取
- `rarity_weights` 为字典时，不论键数量是 2、3、4 还是 5，都要直接按传入键集合抽取，不能因为”不满五档”就退回默认品质池

十、黄巾副本专用约束
- `黄巾士兵`、`黄巾头目`、`偷伐人` 只允许掉落 `普通 / 精良`
- 这些怪的掉落模板来自雏龙套、麻布套等普通套装，绝不允许出现 `【神器】`
- 如果出现普通副本怪掉落神器，优先检查：
  - 模板池是否混入 `is_artifact=true`
  - `generate_from_pool` 是否对 monster source 正确过滤神器模板
  - `_roll_rarity_from_weights` 是否错误回退到了默认全品质池

十一、装备命名规则
文件：`models/player.py` EquipmentInstance.update_name

装备名称格式：`【品质】模板名(星级)(等级)`
示例：
- `【卓越】新婚草戒(3星)(20级)`
- `【神器】新婚钻戒(5星)(20级)`

品质必须是中文，不能使用英文（如”rare”）。

十二、变更记录

| 日期 | 变更内容 |
|------|---------|
| 2026-06-27 | 添加generate_equipment效果处理，用于物品使用生成装备 |
| 2026-06-27 | 品质必须使用中文，rarity_range配置改为中文数组 |


