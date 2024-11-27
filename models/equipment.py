import random
import uuid
import json
from typing import Dict, Optional

class Equipment:
    STAT_NAMES = {
        "max_health": "生命上限",
        "max_mana": "魔法上限",
        "attack": "攻击力",
        "defense": "防御力",
        "crit_rate": "暴击率",
        "dodge_rate": "闪避率"
    }

    SLOTS = {
        "weapon": "武器",
        "accessory": "饰品",
        "armor": "铠甲",
        "helmet": "头盔",
        "pants": "护腿",
        "shoes": "战靴"
    }

    RARITIES = ["普通", "精良", "卓越", "史诗", "神器"]

    def __init__(self, template_id: str, rarity: str, stars: int):
        self.equipment_id = str(uuid.uuid4())
        self.template = self.load_template(template_id)
        self.slot = self.template["slot"]
        self.rarity = rarity
        self.stars = stars
        self.level_required = self.template.get("level_required", 1)
        self.class_required = self.template.get("class_required")
        self.is_bound = self.template.get("is_bound", False)
        self.name = f"【{self.rarity}】{self.template['name']}({self.stars}星)({self.level_required}级)"
        self.description = self.template['description']
        
        self.base_stats = self._calculate_base_stats()
        self.extra_stats = self._generate_extra_stats()
        self.sell_price = self._calculate_sell_price()

    def _calculate_sell_price(self) -> int:
        base_price = self.template.get('base_price', 1000)
        rarity_multipliers = {
            "普通": 0.2,
            "精良": 0.4,
            "卓越": 0.6,
            "史诗": 0.8,
            "神器": 1.0
        }
        return int(base_price * rarity_multipliers[self.rarity] * (self.stars / 5))

    def _calculate_base_stats(self) -> Dict[str, int]:
        ratio = self.stars / 5
        return {
            stat: int(value * ratio)
            for stat, value in self.template["base_stats"].items()
        }

    def _generate_extra_stats(self) -> Dict[str, tuple]:
        extra_stats = {}
        stat_counts = {
            "普通": 1, "精良": 2, "卓越": 3,
            "史诗": 4, "神器": 6
        }
        
        count = stat_counts[self.rarity]
        if count == 0:
            return extra_stats

        # 定义武器和防具/饰品的属性顺序
        weapon_stats_order = [
            ["attack"],
            ["attack", "max_health"],
            ["attack", "max_health", "crit_rate"],
            ["attack", "max_health", "crit_rate", "max_mana"],
            ["attack", "max_health", "crit_rate", "max_mana", "defense"],
            ["attack", "max_health", "crit_rate", "max_mana", "defense", "dodge_rate"]
        ]
        
        armor_stats_order = [
            ["defense"],
            ["defense", "max_health"],
            ["defense", "max_health", "max_mana"],
            ["defense", "max_health", "crit_rate", "max_mana"],
            ["attack", "max_health", "crit_rate", "max_mana", "defense"],
            ["attack", "max_health", "crit_rate", "max_mana", "defense", "dodge_rate"]
        ]

        selected_stats = (weapon_stats_order[count-1] 
                        if self.slot == "weapon" 
                        else armor_stats_order[count-1])
        
        # 计算平均星级
        avg_stars = self.stars
        num_stats = len(selected_stats)
        
        for stat in selected_stats:
            # 在平均星级的基础上随机浮动，确保在1-5星之间
            stat_stars = min(5, max(1, random.randint(avg_stars - 1, avg_stars + 1)))
            max_value = self.template["max_extra_stats"].get(stat, 0)
            actual_value = max_value * (stat_stars / 5)
            extra_stats[stat] = (actual_value, stat_stars)
        
        return extra_stats


    def generate_stat_changes(self, old_stats: dict, new_stats: dict) -> str:
        changes = []
        for stat, name in Equipment.STAT_NAMES.items():
            if stat in old_stats or stat in new_stats:
                old_val = old_stats.get(stat, 0)
                new_val = new_stats.get(stat, 0)
                diff = new_val - old_val
                if diff != 0:
                    if stat in ['crit_rate', 'dodge_rate']:
                        changes.append(f"{name}: {diff*100:+.1f}%")
                    else:
                        changes.append(f"{name}: {diff:+d}")
        return "\n".join(changes)

    def to_dict(self):
        return {
            "equipment_id": self.equipment_id,
            "template_id": self.template["template_id"],
            "name": self.name,
            "slot": self.slot,
            "rarity": self.rarity,
            "stars": self.stars,
            "level_required": self.level_required,
            "class_required": self.class_required,
            "description": self.description,
            "is_bound": self.is_bound,
            "base_stats": self.base_stats,
            "extra_stats": self.extra_stats
        }

    @classmethod
    def from_dict(cls, data):
        equipment = cls(
            template_id=data["template_id"],
            rarity=data["rarity"],
            stars=data["stars"]
        )
        equipment.equipment_id = data["equipment_id"]
        equipment.base_stats = data["base_stats"]
        equipment.extra_stats = data["extra_stats"]
        equipment.is_bound = data["is_bound"]
        return equipment

    @staticmethod
    def load_template(template_id: str) -> dict:
        with open("data/equipment_templates.json", "r", encoding="utf-8") as f:
            templates = json.load(f)
            template = templates.get(template_id)
            if template:
                template["template_id"] = template_id
                return template
            raise ValueError(f"Equipment template {template_id} not found")

    @classmethod
    def generate_random_equipment(cls, template_id: str) -> 'Equipment':
        rarity = random.choice(cls.RARITIES)
        stars = random.randint(1, 5)
        return cls(template_id, rarity, stars)
