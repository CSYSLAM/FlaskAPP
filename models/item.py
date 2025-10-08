from enum import Enum
from typing import Optional, Dict, Any, List
import json
from pathlib import Path
import random

class ItemType(Enum):
    POTION = "potion"
    EQUIPMENT = "equipment" 
    MATERIAL = "material"
    CHEST = "chest"
    QUEST = "quest"
    OTHER = "other"

class ItemUsageCondition:
    def __init__(self, level_required: int = 0, required_items: Dict[str, int] = None):
        self.level_required = level_required
        self.required_items = required_items or {}
        
    def to_dict(self):
        return {
            "level_required": self.level_required,
            "required_items": self.required_items
        }
    
    @classmethod
    def from_dict(cls, data):
        return cls(
            level_required=data.get("level_required", 0),
            required_items=data.get("required_items", {})
        )

class ItemUsageEffect:
    def __init__(self, 
                 stat_changes: Dict[str, int] = None,
                 stat_changes_rng: Dict[str, list] = None,
                 item_changes: Dict[str, int] = None,
                 random_items: List[Dict[str, int]] = None,
                 temp_effects = None,
                 effect_descriptions: Dict[str, str] = None,
                 equipment_generators: List[Dict[str, any]] = None): 
        self.stat_changes = stat_changes or {}
        # 区间随机，如 {"experience": [1000,3000], "money": [1000,5000]}
        self.stat_changes_rng = stat_changes_rng or {}
        self.item_changes = item_changes or {}
        self.random_items = random_items or []
        self.temp_effects = temp_effects or []
        self.effect_descriptions = effect_descriptions or {} # 新增临时效果
        # 完全数据驱动的装备生成规则列表（可选）
        # 每个规则支持：
        # {
        #   "count": 1, "chance": 1.0,
        #   "template_ids": [..] 或 通过筛选字段构造池：
        #   "level_min": 1, "level_max": 5, "slots": ["weapon","armor",...],
        #   "include_artifact": false, "exclude_artifact": true,
        #   "template_weights": {tid: weight},
        #   "rarity_weights": {"普通":..,"精良":..,"卓越":..,"史诗":..},
        #   "star_range": [1,5] 或 "star_weights": {1:..,2:..}
        # }
        self.equipment_generators = equipment_generators or []
        
    def to_dict(self):
        return {
            "stat_changes": self.stat_changes,
            "stat_changes_rng": self.stat_changes_rng,
            "item_changes": self.item_changes,
            "random_items": self.random_items,
            "temp_effects": self.temp_effects,
            "effect_descriptions": self.effect_descriptions,
            "equipment_generators": self.equipment_generators
        }
    
    @classmethod
    def from_dict(cls, data):
        return cls(
            stat_changes=data.get("stat_changes", {}),
            stat_changes_rng=data.get("stat_changes_rng", {}),
            item_changes=data.get("item_changes", {}),
            random_items=data.get("random_items", []),
            temp_effects=data.get("temp_effects", []),
            effect_descriptions=data.get("effect_descriptions", {}),
            equipment_generators=data.get("equipment_generators", []) 
        )


class Item:
    def __init__(self,
                 item_id: str,
                 name: str,
                 item_type: ItemType,
                 description: str,
                 is_usable: bool = True,
                 can_bulk_use: bool = False,  # 新增属性
                 price: int = 0,
                 is_permanent_buff: bool = False,
                 usage_condition: Optional[ItemUsageCondition] = None,
                 usage_effect: Optional[ItemUsageEffect] = None):
        self.item_id = item_id
        self.name = name
        self.item_type = item_type
        self.description = description
        self.is_usable = is_usable
        self.can_bulk_use = can_bulk_use  # 新增属性
        self.price = price
        self.is_permanent_buff = is_permanent_buff
        self.usage_condition = usage_condition
        self.usage_effect = usage_effect

    def to_dict(self):
        return {
            "item_id": self.item_id,
            "name": self.name,
            "item_type": self.item_type.value,
            "description": self.description,
            "is_usable": self.is_usable,
            "can_bulk_use": self.can_bulk_use,  # 新增属性
            "price": self.price,
            "usage_condition": self.usage_condition.to_dict() if self.usage_condition else None,
            "usage_effect": self.usage_effect.to_dict() if self.usage_effect else None
        }

    @classmethod
    def from_dict(cls, data):
        # Map 'type' to 'item_type' if it exists in data
        if 'type' in data:
            data['item_type'] = data['type']
            
        usage_condition = ItemUsageCondition.from_dict(data["usage_condition"]) if data.get("usage_condition") else None
        usage_effect = ItemUsageEffect.from_dict(data["usage_effect"]) if data.get("usage_effect") else None
        
        return cls(
            item_id=data["item_id"],
            name=data["name"],
            item_type=ItemType(data["item_type"]),
            description=data["description"],
            is_usable=data.get("is_usable", True),
            price=data.get("price", 0),
            usage_condition=usage_condition,
            usage_effect=usage_effect
        )

    @classmethod
    def load_items(cls):
        items_file = Path("data/items.json")
        with open(items_file, 'r', encoding='utf-8') as f:
            items_data = json.load(f)
            
        items = {}
        for item_id, data in items_data.items():
            data["item_id"] = item_id
            items[item_id] = cls.from_dict(data)
        return items

    @classmethod
    def get_shop_items(cls):
        shop_items = {}
        items = cls.load_items()
        for item_id, item in items.items():
            if item.price > 0:
                shop_items[item_id] = item
        return shop_items

    @classmethod
    def get_shop_items_by_ids(cls, item_ids, page=1, per_page=10):
        """根据物品ID列表获取商城物品，支持分页"""
        all_items = cls.load_items()
        shop_items = {}
        
        for item_id in item_ids:
            if item_id in all_items and all_items[item_id].price > 0:
                shop_items[item_id] = all_items[item_id]
        
        # 分页处理
        total_items = len(shop_items)
        start_index = (page - 1) * per_page
        end_index = start_index + per_page
        
        paginated_items = dict(list(shop_items.items())[start_index:end_index])
        
        return {
            'items': paginated_items,
            'total': total_items,
            'page': page,
            'per_page': per_page,
            'total_pages': (total_items + per_page - 1) // per_page,
            'has_prev': page > 1,
            'has_next': page < (total_items + per_page - 1) // per_page
        }

    @classmethod
    def get_shop_items_by_category(cls, category, page=1, per_page=10):
        """根据分类获取商城物品，支持分页"""
        all_items = cls.load_items()
        shop_items = {}
        
        for item_id, item in all_items.items():
            if item.price > 0:
                if category == "all" or item.item_type.value == category:
                    shop_items[item_id] = item
        
        # 分页处理
        total_items = len(shop_items)
        start_index = (page - 1) * per_page
        end_index = start_index + per_page
        
        paginated_items = dict(list(shop_items.items())[start_index:end_index])
        
        return {
            'items': paginated_items,
            'total': total_items,
            'page': page,
            'per_page': per_page,
            'total_pages': (total_items + per_page - 1) // per_page,
            'has_prev': page > 1,
            'has_next': page < (total_items + per_page - 1) // per_page
        }
