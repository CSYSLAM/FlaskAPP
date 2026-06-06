import random
from services import db
from services.data_service import DataService
from models.player import EquipmentInstance
from services.equipment_generator import EquipmentGenerator


class CraftingService:

    # Materials for each level range
    LEVEL_MATERIALS = {
        (15, 20): {
            "items": {"craft_suipi": 20, "craft_mabu": 20, "craft_huangyangmu": 20, "craft_huangtongkuang": 20},
            "silver": 2440,
        },
        (25, 30): {
            "items": {"craft_suipi": 20, "craft_mabu": 20, "craft_huangyangmu": 20, "craft_huangtongkuang": 20},
            "silver": 4440,
        },
        (35, 40): {
            "items": {"craft_yingpi": 20, "craft_mianbu": 20, "craft_chenxiangmu": 20, "craft_heitiekuang": 20},
            "silver": 6440,
        },
        (45, 50): {
            "items": {"craft_yingpi": 20, "craft_mianbu": 20, "craft_chenxiangmu": 20, "craft_heitiekuang": 20},
            "silver": 8440,
        },
        (50, 55): {
            "items": {"craft_yingpi": 20, "craft_mianbu": 20, "craft_chenxiangmu": 20, "craft_heitiekuang": 20},
            "silver": 10440,
        },
    }

    # Set definitions for crafting UI: set_id -> {name, class, level_range, templates}
    SET_DEFINITIONS = [
        {
            "set_id": "baopi",
            "name": "豹皮套",
            "class_name": "战士",
            "level_range": "15-20级",
            "templates": ["baopi_helmet_19", "baopi_armor_18", "baopi_pants_17", "baopi_gloves_16", "baopi_shoes_15"],
        },
        {
            "set_id": "shuiwen",
            "name": "水纹套",
            "class_name": "术士",
            "level_range": "15-20级",
            "templates": ["shuiwen_helmet_19", "shuiwen_armor_18", "shuiwen_pants_17", "shuiwen_gloves_16", "shuiwen_shoes_15"],
        },
        {
            "set_id": "canglang",
            "name": "苍狼套",
            "class_name": "刺客",
            "level_range": "15-20级",
            "templates": ["canglang_helmet_19", "canglang_armor_18", "canglang_pants_17", "canglang_gloves_16", "canglang_shoes_15"],
        },
        {
            "set_id": "leiting",
            "name": "雷霆套",
            "class_name": "战士",
            "level_range": "25-30级",
            "templates": ["leiting_helmet_29", "leiting_armor_28", "leiting_pants_27", "leiting_gloves_26", "leiting_shoes_25"],
        },
        {
            "set_id": "riguang",
            "name": "日光套",
            "class_name": "术士",
            "level_range": "25-30级",
            "templates": ["riguang_helmet_29", "riguang_armor_28", "riguang_pants_27", "riguang_gloves_26", "riguang_shoes_25"],
        },
        {
            "set_id": "yese",
            "name": "夜色套",
            "class_name": "刺客",
            "level_range": "25-30级",
            "templates": ["yese_helmet_29", "yese_armor_28", "yese_pants_27", "yese_gloves_26", "yese_shoes_25"],
        },
        {
            "set_id": "jinggang",
            "name": "精钢套",
            "class_name": "战士",
            "level_range": "35-40级",
            "templates": ["jinggang_helmet_39", "jinggang_armor_38", "jinggang_pants_37", "jinggang_gloves_36", "jinggang_shoes_35"],
        },
        {
            "set_id": "yuanlv",
            "name": "远虑套",
            "class_name": "术士",
            "level_range": "35-40级",
            "templates": ["yuanlv_helmet_39", "yuanlv_armor_38", "yuanlv_pants_37", "yuanlv_gloves_36", "yuanlv_shoes_35"],
        },
        {
            "set_id": "jifeng",
            "name": "疾风套",
            "class_name": "刺客",
            "level_range": "35-40级",
            "templates": ["jifeng_helmet_39", "jifeng_armor_38", "jifeng_pants_37", "jifeng_gloves_36", "jifeng_shoes_35"],
        },
        {
            "set_id": "bailian",
            "name": "百炼套",
            "class_name": "战士",
            "level_range": "45-50级",
            "templates": ["bailian_helmet_49", "bailian_armor_48", "bailian_pants_47", "bailian_gloves_46", "bailian_shoes_45"],
        },
        {
            "set_id": "jinxiu",
            "name": "锦绣套",
            "class_name": "术士",
            "level_range": "45-50级",
            "templates": ["jinxiu_helmet_49", "jinxiu_armor_48", "jinxiu_pants_47", "jinxiu_gloves_46", "jinxiu_shoes_45"],
        },
        {
            "set_id": "queling",
            "name": "雀翔套",
            "class_name": "刺客",
            "level_range": "45-50级",
            "templates": ["queling_helmet_49", "queling_armor_48", "queling_pants_47", "queling_gloves_46", "queling_shoes_45"],
        },
        {
            "set_id": "heilong",
            "name": "黑龙套",
            "class_name": "战士",
            "level_range": "50-55级",
            "templates": ["heilong_helmet_54", "heilong_armor_53", "heilong_pants_52", "heilong_gloves_51", "heilong_shoes_50"],
        },
        {
            "set_id": "fengluan",
            "name": "凤鸾套",
            "class_name": "术士",
            "level_range": "50-55级",
            "templates": ["fengluan_helmet_54", "fengluan_armor_53", "fengluan_pants_52", "fengluan_gloves_51", "fengluan_shoes_50"],
        },
        {
            "set_id": "yanling",
            "name": "雁翔套",
            "class_name": "刺客",
            "level_range": "50-55级",
            "templates": ["yanling_helmet_54", "yanling_armor_53", "yanling_pants_52", "yanling_gloves_51", "yanling_shoes_50"],
        },
    ]

    @classmethod
    def get_sets_by_class(cls, player_class):
        return [s for s in cls.SET_DEFINITIONS if s["class_name"] == player_class]

    @classmethod
    def get_material_cost(cls, template):
        level = template.get("level_required", 0)
        for (lo, hi), cost in cls.LEVEL_MATERIALS.items():
            if lo <= level <= hi:
                return cost
        return None

    @classmethod
    def forge_equipment(cls, player, template_id):
        template = DataService.get_equipment_template(template_id)
        if not template:
            return False, "装备模板不存在"

        cost = cls.get_material_cost(template)
        if not cost:
            return False, "无法确定打造材料"

        # Check silver
        if player.gold < cost["silver"]:
            return False, f"银两不足，需要{cost['silver']}银两"

        # Check materials
        for item_id, required_qty in cost["items"].items():
            inv = DataService.get_inventory_item(player.id, item_id)
            if not inv or inv.quantity < required_qty:
                item_data = DataService.get_item(item_id)
                item_name = item_data.get("name", item_id) if item_data else item_id
                return False, f"材料不足，需要{item_name}x{required_qty}"

        # Check if all materials are non-bound
        all_unbound = True
        for item_id, required_qty in cost["items"].items():
            inv = DataService.get_inventory_item(player.id, item_id, is_bound=False)
            if not inv or inv.quantity < required_qty:
                all_unbound = False
                break

        # Consume silver
        player.gold -= cost["silver"]

        # Consume materials
        for item_id, required_qty in cost["items"].items():
            DataService.remove_item_from_inventory(player.id, item_id, required_qty)

        # Roll rarity: 精良/卓越/史诗, no 神器 (only is_artifact items can be 神器)
        rarity_weights = {"common": 0, "uncommon": 50, "rare": 35, "epic": 15, "legendary": 0}
        rarity = EquipmentGenerator._roll_rarity_from_weights(rarity_weights, allow_legendary=False)
        stars = random.randint(1, 5)

        equip = DataService.create_equipment_instance(
            player.id, template_id, rarity, stars)

        # Mixed materials = bound; all non-bound materials = non-bound
        if not all_unbound:
            equip.is_bound = True

        db.session.commit()
        return True, equip

    @classmethod
    def get_template_slot_name(cls, template):
        slot = template.get("slot", "")
        names = {"weapon": "武器", "helmet": "头盔", "armor": "衣服",
                 "gloves": "手套", "pants": "裤子", "shoes": "鞋子"}
        return names.get(slot, slot)

    @classmethod
    def get_template_info(cls, template_id):
        template = DataService.get_equipment_template(template_id)
        if not template:
            return None

        cost = cls.get_material_cost(template)
        info = {
            "template_id": template_id,
            "name": template.get("name", template_id),
            "level_required": template.get("level_required", 0),
            "slot": template.get("slot", ""),
            "slot_name": cls.get_template_slot_name(template),
            "class_required": template.get("class_required"),
            "silver": cost["silver"] if cost else 0,
            "materials": [],
        }

        if cost:
            for item_id, qty in cost["items"].items():
                item_data = DataService.get_item(item_id)
                if item_data:
                    info["materials"].append({
                        "item_id": item_id,
                        "name": item_data.get("name", item_id),
                        "quantity": qty,
                    })

        return info
