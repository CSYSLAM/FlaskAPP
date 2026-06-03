import math
import random
from services import db
from services.data_service import DataService
from models.player import InventoryItem, EquipmentInstance


class ShopService:

    PER_PAGE_OPTIONS = [5, 10, 20, 50]

    @classmethod
    def _get_all_shop_items(cls, shop_id):
        shops = DataService.get_shops()
        shop_config = shops.get(shop_id)
        if not shop_config:
            return None

        all_items = DataService.get_items()
        all_templates = DataService.get_equipment_templates()

        shop_items = {}
        item_ids = shop_config.get("item_ids")

        for item_id, item_data in all_items.items():
            if item_ids is not None and item_id not in item_ids:
                continue
            category = shop_config.get("category")
            if category and category != "all":
                if item_data.get("category") != category:
                    continue
            if item_data.get("price"):
                shop_items[item_id] = {
                    "name": item_data.get("name", item_id),
                    "description": item_data.get("description", ""),
                    "price": item_data.get("price", 0),
                    "currency": item_data.get("currency", "gold"),
                    "type": "item",
                }

        equipment_entries = shop_config.get("equipment", [])
        for entry in equipment_entries:
            tid = entry.get("template_id")
            template = all_templates.get(tid) if tid else None
            if template:
                key = f"eq_{tid}"
                shop_items[key] = {
                    "name": template.get("name", tid),
                    "description": template.get("description", ""),
                    "price": entry.get("price", 0),
                    "type": "equipment",
                    "template_id": tid,
                    "rarity": entry.get("rarity", "精良"),
                    "stars": entry.get("stars", 1),
                }
        return shop_items

    @classmethod
    def get_shop_data(cls, shop_id, page=1, per_page=10):
        all_shop_items = cls._get_all_shop_items(shop_id)
        if all_shop_items is None:
            return None

        shops = DataService.get_shops()
        shop_config = shops.get(shop_id)

        total = len(all_shop_items)
        total_pages = max(1, math.ceil(total / per_page))
        page = max(1, min(page, total_pages))
        start = (page - 1) * per_page
        end = start + per_page

        paginated_items = dict(list(all_shop_items.items())[start:end])

        return {
            "name": shop_config.get("name", shop_id),
            "shop_items": paginated_items,
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
            "has_prev": page > 1,
            "has_next": page < total_pages,
        }

    @classmethod
    def buy_item(cls, player, shop_id, item_id, quantity=1):
        all_shop_items = cls._get_all_shop_items(shop_id)
        if all_shop_items is None:
            return False, "商店不存在"

        item_entry = all_shop_items.get(item_id)
        if not item_entry:
            return False, "商品不存在"

        price = item_entry["price"] * quantity
        currency = item_entry.get("currency", "gold")
        currency_names = {"gold": "银两", "yuanbao": "元宝", "jinzu": "金珠"}

        # Check balance
        if currency == "yuanbao":
            if player.yuanbao < price:
                return False, f"元宝不足，需要{price}元宝"
            player.yuanbao -= price
        elif currency == "jinzu":
            if player.jinzu < price:
                return False, f"金珠不足，需要{price}金珠"
            player.jinzu -= price
        else:
            if player.gold < price:
                return False, f"银两不足，需要{price}银两"
            player.gold -= price

        if item_entry.get("type") == "equipment":
            from services.equipment_service import EquipmentService
            template_id = item_entry.get("template_id", item_id)
            equip = EquipmentService.generate_random_equipment(
                player.id, template_id,
                rarity=item_entry.get("rarity", "精良"),
                stars=item_entry.get("stars", 1))
            if equip:
                DataService.add_item_to_inventory(player.id, equip.instance_id)
                db.session.commit()
                return True, f"购买了 {equip.name}"
            else:
                # Refund
                if currency == "yuanbao":
                    player.yuanbao += price
                elif currency == "jinzu":
                    player.jinzu += price
                else:
                    player.gold += price
                return False, "装备生成失败"
        else:
            # Check if this is a direct exchange item
            if item_id.startswith('buy_yuanbao_') or item_id.startswith('buy_jinzu_'):
                # Direct exchange - apply effect immediately
                usage_effect = DataService.get_item(item_id).get("usage_effect", {})
                stat_changes = usage_effect.get("stat_changes", {})
                for stat, value in stat_changes.items():
                    if hasattr(player, stat):
                        setattr(player, stat, getattr(player, stat) + value * quantity)
                db.session.commit()
                cn = currency_names.get(currency, "银两")
                return True, f"兑换成功，花费{price}{cn}"
            else:
                DataService.add_item_to_inventory(player.id, item_id, quantity)
                db.session.commit()
                cn = currency_names.get(currency, "银两")
                return True, f"购买了{quantity}个，花费{price}{cn}"

    @classmethod
    def buy_equipment(cls, player, shop_id, template_id):
        all_shop_items = cls._get_all_shop_items(shop_id)
        if all_shop_items is None:
            return False, "商店不存在"

        equip_entry = None
        for key, entry in all_shop_items.items():
            if entry.get("type") == "equipment" and entry.get("template_id") == template_id:
                equip_entry = entry
                break

        if not equip_entry:
            return False, "装备不存在"

        price = equip_entry["price"]
        if player.gold < price:
            return False, "银两不足"

        player.gold -= price

        from services.equipment_service import EquipmentService
        equip = EquipmentService.generate_random_equipment(
            player.id, template_id,
            rarity=equip_entry.get("rarity", "精良"),
            stars=equip_entry.get("stars", 1))

        if equip:
            DataService.add_item_to_inventory(player.id, equip.instance_id)
            db.session.commit()
            return True, f"购买了 {equip.name}"
        else:
            player.gold += price
            db.session.commit()
            return False, "装备生成失败"

    @classmethod
    def sell_item(cls, player, item_id, quantity=1, is_bound=None):
        inv = DataService.get_inventory_item(player.id, item_id, is_bound=is_bound)
        if not inv or inv.quantity < quantity:
            return False, "物品不足", 0

        item_data = DataService.get_item(item_id)
        if not item_data:
            return False, "物品不存在", 0

        sell_price = item_data.get("sell_price", 10)
        total_price = sell_price * quantity

        player.gold += total_price
        player.gold_earned = (player.gold_earned or 0) + total_price
        DataService.remove_item_from_inventory(player.id, item_id, quantity, is_bound=is_bound)
        db.session.commit()

        from services.achievement_service import AchievementService
        AchievementService.check(player, 'gold_earned', player.gold_earned)
        db.session.commit()
        return True, f"出售了 {quantity} 个，获得 {total_price} 银两", total_price