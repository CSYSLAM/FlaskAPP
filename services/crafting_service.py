import random
from services import db
from services.data_service import DataService
from models.player import EquipmentInstance
from services.equipment_generator import EquipmentGenerator


class CraftingService:

    # Material costs for armor sets (by level range)
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
        (45, 49): {
            "items": {"craft_yingpi": 20, "craft_mianbu": 20, "craft_chenxiangmu": 20, "craft_heitiekuang": 20},
            "silver": 8440,
        },
        (50, 54): {
            "items": {"craft_yingpi": 20, "craft_mianbu": 20, "craft_chenxiangmu": 20, "craft_heitiekuang": 20},
            "silver": 10440,
        },
        (55, 59): {
            "items": {"craft_houpi": 20, "craft_nirong": 20, "craft_zitanmu": 20, "craft_jingjinkuang": 20},
            "silver": 14440,
        },
    }

    # Material costs for weapons (by exact level)
    WEAPON_MATERIALS = {
        20: {"items": {"craft_huangyangmu": 20, "craft_huangtongkuang": 20}, "silver": 2440},
        30: {"items": {"craft_huangyangmu": 20, "craft_huangtongkuang": 20}, "silver": 4440},
        40: {"items": {"craft_chenxiangmu": 20, "craft_heitiekuang": 20}, "silver": 6440},
        50: {"items": {"craft_chenxiangmu": 20, "craft_heitiekuang": 20}, "silver": 8440},
        60: {"items": {"craft_zitanmu": 20, "craft_jingjinkuang": 20}, "silver": 14440},
    }

    # Material costs for accessories (by exact level)
    ACCESSORY_MATERIALS = {
        10: {"items": {"craft_huangyangmu": 20, "craft_huangtongkuang": 20}, "silver": 1940},
        14: {"items": {"craft_huangyangmu": 20, "craft_huangtongkuang": 20}, "silver": 2440},
        24: {"items": {"craft_huangyangmu": 20, "craft_huangtongkuang": 20}, "silver": 4440},
        28: {"items": {"craft_huangyangmu": 20, "craft_huangtongkuang": 20}, "silver": 5440},
        34: {"items": {"craft_chenxiangmu": 20, "craft_heitiekuang": 20}, "silver": 6440},
        40: {"items": {"craft_chenxiangmu": 20, "craft_heitiekuang": 20}, "silver": 8440},
        46: {"items": {"craft_chenxiangmu": 20, "craft_heitiekuang": 20}, "silver": 9640},
        54: {"items": {"craft_zitanmu": 20, "craft_jingjinkuang": 20}, "silver": 10440},
    }

    # Set definitions for armor (class_name matches to filter by player class)
    SET_DEFINITIONS = [
        {
            "set_id": "baopi", "name": "豹皮套", "class_name": "战士",
            "level_range": "15-20级", "group": "15-20级",
            "templates": ["baopi_helmet_19", "baopi_armor_18", "baopi_pants_17", "baopi_gloves_16", "baopi_shoes_15"],
        },
        {
            "set_id": "shuiwen", "name": "水纹套", "class_name": "术士",
            "level_range": "15-20级", "group": "15-20级",
            "templates": ["shuiwen_helmet_19", "shuiwen_armor_18", "shuiwen_pants_17", "shuiwen_gloves_16", "shuiwen_shoes_15"],
        },
        {
            "set_id": "canglang", "name": "苍狼套", "class_name": "刺客",
            "level_range": "15-20级", "group": "15-20级",
            "templates": ["canglang_helmet_19", "canglang_armor_18", "canglang_pants_17", "canglang_gloves_16", "canglang_shoes_15"],
        },
        {
            "set_id": "leiting", "name": "雷霆套", "class_name": "战士",
            "level_range": "25-30级", "group": "25-30级",
            "templates": ["leiting_helmet_29", "leiting_armor_28", "leiting_pants_27", "leiting_gloves_26", "leiting_shoes_25"],
        },
        {
            "set_id": "riguang", "name": "日光套", "class_name": "术士",
            "level_range": "25-30级", "group": "25-30级",
            "templates": ["riguang_helmet_29", "riguang_armor_28", "riguang_pants_27", "riguang_gloves_26", "riguang_shoes_25"],
        },
        {
            "set_id": "yese", "name": "夜色套", "class_name": "刺客",
            "level_range": "25-30级", "group": "25-30级",
            "templates": ["yese_helmet_29", "yese_armor_28", "yese_pants_27", "yese_gloves_26", "yese_shoes_25"],
        },
        {
            "set_id": "jinggang", "name": "精钢套", "class_name": "战士",
            "level_range": "35-40级", "group": "35-40级",
            "templates": ["jinggang_helmet_39", "jinggang_armor_38", "jinggang_pants_37", "jinggang_gloves_36", "jinggang_shoes_35"],
        },
        {
            "set_id": "yuanlv", "name": "远虑套", "class_name": "术士",
            "level_range": "35-40级", "group": "35-40级",
            "templates": ["yuanlv_helmet_39", "yuanlv_armor_38", "yuanlv_pants_37", "yuanlv_gloves_36", "yuanlv_shoes_35"],
        },
        {
            "set_id": "jifeng", "name": "疾风套", "class_name": "刺客",
            "level_range": "35-40级", "group": "35-40级",
            "templates": ["jifeng_helmet_39", "jifeng_armor_38", "jifeng_pants_37", "jifeng_gloves_36", "jifeng_shoes_35"],
        },
        {
            "set_id": "bailian", "name": "百炼套", "class_name": "战士",
            "level_range": "45-50级", "group": "45-50级",
            "templates": ["bailian_helmet_49", "bailian_armor_48", "bailian_pants_47", "bailian_gloves_46", "bailian_shoes_45"],
        },
        {
            "set_id": "jinxiu", "name": "锦绣套", "class_name": "术士",
            "level_range": "45-50级", "group": "45-50级",
            "templates": ["jinxiu_helmet_49", "jinxiu_armor_48", "jinxiu_pants_47", "jinxiu_gloves_46", "jinxiu_shoes_45"],
        },
        {
            "set_id": "queling", "name": "雀翔套", "class_name": "刺客",
            "level_range": "45-50级", "group": "45-50级",
            "templates": ["queling_helmet_49", "queling_armor_48", "queling_pants_47", "queling_gloves_46", "queling_shoes_45"],
        },
        {
            "set_id": "heilong", "name": "黑龙套", "class_name": "战士",
            "level_range": "50-55级", "group": "50-55级",
            "templates": ["heilong_helmet_54", "heilong_armor_53", "heilong_pants_52", "heilong_gloves_51", "heilong_shoes_50"],
        },
        {
            "set_id": "fengluan", "name": "凤鸾套", "class_name": "术士",
            "level_range": "50-55级", "group": "50-55级",
            "templates": ["fengluan_helmet_54", "fengluan_armor_53", "fengluan_pants_52", "fengluan_gloves_51", "fengluan_shoes_50"],
        },
        {
            "set_id": "yanling", "name": "雁翔套", "class_name": "刺客",
            "level_range": "50-55级", "group": "50-55级",
            "templates": ["yanling_helmet_54", "yanling_armor_53", "yanling_pants_52", "yanling_gloves_51", "yanling_shoes_50"],
        },
        {
            "set_id": "qinglong", "name": "青龙套", "class_name": "战士",
            "level_range": "55-59级", "group": "55-59级",
            "templates": ["qinglong_helmet_59", "qinglong_armor_58", "qinglong_pants_57", "qinglong_gloves_56", "qinglong_shoes_55"],
        },
        {
            "set_id": "zhuque", "name": "朱雀套", "class_name": "术士",
            "level_range": "55-59级", "group": "55-59级",
            "templates": ["zhuque_helmet_59", "zhuque_armor_58", "zhuque_pants_57", "zhuque_gloves_56", "zhuque_shoes_55"],
        },
        {
            "set_id": "baihu", "name": "白虎套", "class_name": "刺客",
            "level_range": "55-59级", "group": "55-59级",
            "templates": ["baihu_helmet_59", "baihu_armor_58", "baihu_pants_57", "baihu_gloves_56", "baihu_shoes_55"],
        },
        {
            "set_id": "tiangang", "name": "天罡套", "class_name": "战士",
            "level_range": "60级", "group": "60级",
            "templates": ["tiangang_helmet_60", "tiangang_armor_60", "tiangang_pants_60", "tiangang_gloves_60", "tiangang_shoes_60"],
        },
        {
            "set_id": "ziyun", "name": "紫云套", "class_name": "术士",
            "level_range": "60级", "group": "60级",
            "templates": ["ziyun_helmet_60", "ziyun_armor_60", "ziyun_pants_60", "ziyun_gloves_60", "ziyun_shoes_60"],
        },
        {
            "set_id": "lieyan", "name": "烈焰套", "class_name": "刺客",
            "level_range": "60级", "group": "60级",
            "templates": ["lieyan_helmet_60", "lieyan_armor_60", "lieyan_pants_60", "lieyan_gloves_60", "lieyan_shoes_60"],
        },
    ]

    # Weapon templates by class
    WEAPON_TEMPLATES = {
        "战士": [
            "chelun_fu_20_zhanshi", "baisheng_dao_20_zhanshi",
            "kaishan_fu_30_zhanshi", "bailu_dao_30_zhanshi",
            "pojun_fu_40_zhanshi", "xuezhan_dao_40_zhanshi",
            "shanhe_fu_50_zhanshi", "langyabang_50_zhanshi",
            "zhanyue_60_zhanshi",
        ],
        "术士": [
            "huojing_jian_20_shushi", "emao_shan_20_shushi",
            "duanshui_jian_30_shushi", "moya_yushan_30_shushi",
            "qingyun_jian_40_shushi", "kongque_yushan_40_shushi",
            "feifeng_jian_50_shushi", "fengling_yushan_50_shushi",
            "qixing_longyuan_60_shushi",
        ],
        "刺客": [
            "duanying_20_cike", "taomujian_20_cike",
            "qingyun_jian_30_cike", "hanguang_bishou_30_cike",
            "jifengci_40_cike", "yangjiao_bishou_40_cike",
            "hanbing_jian_50_cike", "feilong_qiang_50_cike",
            "suipo_60_cike",
        ],
    }

    # Accessory templates (all classes)
    ACCESSORY_TEMPLATES = [
        "huangtong_jiezhi_10", "xuanhuang_jiezhi_14",
        "maoyan_jiezhi_24", "hongyan_jiezhi_28",
        "hongxue_jiezhi_34", "lingxi_xianglian_40",
        "ziyu_xianglian_46", "feicui_zhihuan_54",
    ]

    @classmethod
    def get_sets_by_class(cls, player_class):
        return [s for s in cls.SET_DEFINITIONS if s["class_name"] == player_class]

    @classmethod
    def get_set_by_id(cls, set_id):
        for s in cls.SET_DEFINITIONS:
            if s["set_id"] == set_id:
                return s
        return None

    @classmethod
    def get_set_class_tabs(cls, set_def):
        """Return list of classes that share this set's group (for in-page class tabs).

        Sets without a ``group`` field are single-class and return an empty list
        (no tabs rendered). Sets sharing a group (e.g. 青龙/朱雀/白虎 55-59) return
        the ordered class list [战士, 术士, 刺客] of all sets in that group.
        """
        group = set_def.get("group") if set_def else None
        if not group:
            return []
        seen = []
        for s in cls.SET_DEFINITIONS:
            if s.get("group") == group and s["class_name"] not in seen:
                seen.append(s["class_name"])
        return seen

    @classmethod
    def get_set_in_group_by_class(cls, set_def, class_name):
        """Find the set of ``class_name`` within the same group as ``set_def``.

        Falls back to ``set_def`` itself when there is no group or no match.
        """
        group = set_def.get("group") if set_def else None
        if group:
            for s in cls.SET_DEFINITIONS:
                if s.get("group") == group and s["class_name"] == class_name:
                    return s
        return set_def

    @classmethod
    def get_weapon_templates_by_class(cls, player_class):
        return cls.WEAPON_TEMPLATES.get(player_class, cls.WEAPON_TEMPLATES["战士"])

    @classmethod
    def get_accessory_templates(cls):
        return cls.ACCESSORY_TEMPLATES

    @classmethod
    def get_material_cost(cls, template):
        level = template.get("level_required", 0)
        slot = template.get("slot", "")

        # 优先使用模板自带配方（含图纸的60级史诗套等）：craft_silver + craft_materials + blueprint_item
        craft_materials = template.get("craft_materials")
        if craft_materials or template.get("blueprint_item"):
            items = dict(craft_materials) if craft_materials else {}
            # 图纸作为一种"材料"统一参与校验/扣除/绑定判定/tooltip展示
            blueprint = template.get("blueprint_item")
            if blueprint:
                items[blueprint] = items.get(blueprint, 0) + 1
            return {
                "silver": template.get("craft_silver", 0),
                "items": items,
            }

        if slot == "weapon":
            cost = cls.WEAPON_MATERIALS.get(level)
            if cost:
                return cost
        elif slot == "accessory":
            cost = cls.ACCESSORY_MATERIALS.get(level)
            if cost:
                return cost

        # Fallback to armor level range
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

        # Roll rarity: 精良/卓越/史诗, no 神器
        rarity_weights = {"common": 0, "uncommon": 50, "rare": 35, "epic": 15, "legendary": 0}
        rarity = EquipmentGenerator._roll_rarity_from_weights(rarity_weights, allow_legendary=False)
        stars = random.randint(1, 5)

        equip = DataService.create_equipment_instance(
            player.id, template_id, rarity, stars)

        # Mixed materials = bound; all non-bound materials = non-bound
        if not all_unbound:
            equip.is_bound = True

        # Track forge count
        player.forge_count = (player.forge_count or 0) + 1
        from services.achievement_service import AchievementService
        AchievementService.check(player, 'forge', player.forge_count)

        db.session.commit()
        return True, equip

    @classmethod
    def get_template_slot_name(cls, template):
        slot = template.get("slot", "")
        names = {"weapon": "武器", "helmet": "头盔", "armor": "衣服",
                 "gloves": "手套", "pants": "裤子", "shoes": "鞋子", "accessory": "饰品"}
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
            blueprint_id = template.get("blueprint_item")
            for item_id, qty in cost["items"].items():
                # 图纸单独抽出，由模板在银两前渲染（贴合"图纸→银两→材料"展示顺序）
                if item_id == blueprint_id:
                    info["blueprint"] = {"item_id": item_id, "name": "", "quantity": qty}
                    continue
                item_data = DataService.get_item(item_id)
                if item_data:
                    info["materials"].append({
                        "item_id": item_id,
                        "name": item_data.get("name", item_id),
                        "quantity": qty,
                    })
            # 补全图纸名称
            if info.get("blueprint"):
                bp_data = DataService.get_item(blueprint_id)
                if bp_data:
                    info["blueprint"]["name"] = bp_data.get("name", blueprint_id)

        return info

    @classmethod
    def get_sell_equipment_groups(cls, player, rarity_filter="普通"):
        """Group player's equipment by level range for selling."""
        equipments = EquipmentInstance.query.filter_by(
            player_id=player.id, rarity=rarity_filter
        ).all()

        # Filter out equipped items
        from models.player import EquipmentSlot
        equipped_ids = set()
        slots = EquipmentSlot.query.filter_by(player_id=player.id).all()
        for s in slots:
            if s.equipment_instance_id:
                equipped_ids.add(s.equipment_instance_id)

        groups = {}
        for eq in equipments:
            if eq.id in equipped_ids:
                continue
            level = eq.level_required
            if level < 1:
                lo = 1
            else:
                lo = ((level - 1) // 10) * 10 + 1
            hi = lo + 9
            key = f"{lo}-{hi}"
            if key not in groups:
                groups[key] = {"level_key": key, "level_range": f"{lo}-{hi}级装备", "items": [], "count": 0}
            groups[key]["items"].append(eq)
            groups[key]["count"] += 1

        sorted_groups = sorted(groups.items(), key=lambda x: int(x[0].split("-")[0]))
        return [g[1] for g in sorted_groups]

    @classmethod
    def sell_equipment_batch(cls, player, level_ranges):
        """Sell equipment by level ranges. Returns (total_gold, count)."""
        from models.player import EquipmentSlot
        equipped_ids = set()
        slots = EquipmentSlot.query.filter_by(player_id=player.id).all()
        for s in slots:
            if s.equipment_instance_id:
                equipped_ids.add(s.equipment_instance_id)

        total_gold = 0
        total_count = 0

        for level_range in level_ranges:
            parts = level_range.split("-")
            if len(parts) != 2:
                continue
            lo, hi = int(parts[0]), int(parts[1])

            equipments = EquipmentInstance.query.filter(
                EquipmentInstance.player_id == player.id,
                EquipmentInstance.level_required >= lo,
                EquipmentInstance.level_required <= hi,
            ).all()

            for eq in equipments:
                if eq.id in equipped_ids:
                    continue
                price = eq.get_sell_price()
                player.gold += price
                player.gold_earned = (player.gold_earned or 0) + price
                total_gold += price
                total_count += 1
                db.session.delete(eq)

        db.session.commit()
        return total_gold, total_count

    @classmethod
    def get_sell_item_groups(cls, player, category="药品"):
        """Group player's items by category for selling."""
        from models.player import InventoryItem
        all_items = DataService.get_items()

        if category == "药品":
            category_types = ["consumable", "potion"]
        elif category == "种子":
            category_types = ["seed"]
        elif category == "材料":
            category_types = ["material"]
        elif category == "技能":
            category_types = ["skill_book"]
        else:
            category_types = []

        inv_items = InventoryItem.query.filter_by(player_id=player.id).all()
        groups = {}
        for inv in inv_items:
            item_data = all_items.get(inv.item_id, {})
            item_type = item_data.get("type", "")
            if category_types and item_type not in category_types:
                continue
            item_name = item_data.get("name", inv.item_id)
            key = item_name
            if key not in groups:
                groups[key] = {"name": key, "item_id": inv.item_id, "is_bound": inv.is_bound,
                              "count": 0, "sell_price": item_data.get("sell_price", 10)}
            groups[key]["count"] += inv.quantity

        return list(groups.values())

    @classmethod
    def sell_item_batch(cls, player, item_names):
        """Sell items by names. Returns (total_gold, total_count)."""
        all_items = DataService.get_items()
        total_gold = 0
        total_count = 0

        for item_name in item_names:
            # Find item_id by name
            matching_items = []
            for item_id, item_data in all_items.items():
                if item_data.get("name") == item_name:
                    matching_items.append((item_id, item_data))
            if not matching_items:
                continue

            for item_id, item_data in matching_items:
                inv = DataService.get_inventory_item(player.id, item_id)
                if not inv or inv.quantity <= 0:
                    continue
                sell_price = item_data.get("sell_price", 10)
                qty = inv.quantity
                gold = sell_price * qty
                player.gold += gold
                player.gold_earned = (player.gold_earned or 0) + gold
                total_gold += gold
                total_count += qty
                DataService.remove_item_from_inventory(player.id, item_id, qty)

        db.session.commit()
        return total_gold, total_count
