import uuid
import json
from typing import Dict, Optional

class EquipmentTemplate:
    def __init__(self, 
                 name: str,
                 slot: str, 
                 is_bound: bool,
                 level_required: int,
                 class_required: Optional[str],
                 base_stats: Dict[str, int],
                 max_extra_stats: Dict[str, float]):
        self.template_id = str(uuid.uuid4())
        self.name = name
        self.slot = slot
        self.is_bound = is_bound
        self.level_required = level_required
        self.class_required = class_required
        self.base_stats = base_stats
        self.max_extra_stats = max_extra_stats

    @classmethod
    def load_templates(cls):
        # 从json文件加载装备模板数据
        with open("data/equipment_templates.json", "r", encoding="utf-8") as f:
            templates_data = json.load(f)
            return {
                template_id: cls(**data)
                for template_id, data in templates_data.items()
            }
