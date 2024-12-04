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
                 item_changes: Dict[str, int] = None,
                 random_items: List[Dict[str, int]] = None,
                 temp_effects = None):
        self.stat_changes = stat_changes or {}
        self.item_changes = item_changes or {}
        self.random_items = random_items or []
        self.temp_effects = temp_effects or []  # 新增临时效果
        
    def to_dict(self):
        return {
            "stat_changes": self.stat_changes,
            "item_changes": self.item_changes,
            "random_items": self.random_items,
            "temp_effects": self.temp_effects
        }
    
    @classmethod
    def from_dict(cls, data):
        return cls(
            stat_changes=data.get("stat_changes", {}),
            item_changes=data.get("item_changes", {}),
            random_items=data.get("random_items", []),
            temp_effects=data.get("temp_effects", [])
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
