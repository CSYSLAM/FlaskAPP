import json
import os
from services import db
from services.data_service import DataService


class ShopService:
    """Shop service supporting reference-server-style multi-tab shops."""

    _shops_cache = None

    @classmethod
    def _load_shops(cls):
        if cls._shops_cache is None:
            with open(os.path.join(os.path.dirname(__file__), '..', 'data', 'shops.json'), 'r', encoding='utf-8') as f:
                cls._shops_cache = json.load(f)
        return cls._shops_cache

    @classmethod
    def get_shop_data(cls, shop_id, tab=None, **kwargs):
        """Return shop config with items for a given tab."""
        shops = cls._load_shops()
        shop = shops.get(shop_id)
        if not shop:
            return None
        tabs = shop.get('tabs', {})
        if not tab:
            tab = list(tabs.keys())[0] if tabs else None

        # Special handling for test shop: populate with all items at 1 gold.
        # Supports pagination + search since the catalog is large (~360 items).
        if shop_id == 'test':
            page = max(1, int(kwargs.get('page') or 1))
            per_page = max(1, min(100, int(kwargs.get('per_page') or 30)))
            search = (kwargs.get('search') or '').strip()
            all_items = cls._build_test_items(search=search)
            total = len(all_items)
            total_pages = max(1, (total + per_page - 1) // per_page)
            page = min(page, total_pages)
            start = (page - 1) * per_page
            return {
                'id': shop_id,
                'name': shop.get('name', shop_id),
                'currency': 'gold',
                'tab': tab,
                'tabs': tabs,
                'items': all_items[start:start + per_page],
                # pagination metadata (only used by test shop template)
                'page': page,
                'per_page': per_page,
                'total': total,
                'total_pages': total_pages,
                'search': search,
            }

        items = shop.get('items', {}).get(tab, [])
        return {
            'id': shop_id,
            'name': shop.get('name', shop_id),
            'currency': shop.get('currency', 'gold'),
            'tab': tab,
            'tabs': tabs,
            'items': items,
        }

    @classmethod
    def _build_test_items(cls, search=''):
        """Build test shop items: all items at 1 gold, optionally filtered by search.

        Search matches against item id, name, type, and description (case-insensitive).
        """
        search = (search or '').strip().lower()
        items = []
        all_items = DataService.get_items()
        for item_id, item_data in all_items.items():
            if search:
                haystack = ' '.join(str(x) for x in (
                    item_id,
                    item_data.get('name', ''),
                    item_data.get('type', ''),
                    item_data.get('description', ''),
                )).lower()
                if search not in haystack:
                    continue
            items.append({
                'id': item_id,
                'name': item_data.get('name', item_id),
                'price': 1,
                'item_id': item_id,
            })
        return items

    @classmethod
    def get_all_shops(cls):
        """Return list of all shop IDs and names."""
        shops = cls._load_shops()
        return [(sid, s['name']) for sid, s in shops.items()]

    @classmethod
    def buy_item(cls, player, shop_id, item_id, quantity=1):
        """Buy an item from the shop."""
        shops = cls._load_shops()
        shop = shops.get(shop_id)
        if not shop:
            return False, "商店不存在"

        # Find item in any tab
        item_entry = None
        if shop_id == 'test':
            # Test shop: dynamically load all items
            all_items = DataService.get_items()
            if item_id in all_items:
                item_data = all_items[item_id]
                item_entry = {
                    'id': item_id,
                    'name': item_data.get('name', item_id),
                    'price': 1,
                    'item_id': item_id,
                }
        else:
            for tab_items in shop.get('items', {}).values():
                for entry in tab_items:
                    if entry.get('id') == item_id:
                        item_entry = entry
                        break
                if item_entry:
                    break

        if not item_entry:
            return False, "商品不存在"

        price = item_entry["price"] * quantity
        currency = shop.get("currency", "gold")
        currency_names = {"gold": "银两", "yuanbao": "元宝", "jinzu": "金珠", "points": "积分"}

        # Check balance
        if currency == "yuanbao":
            if player.yuanbao < price:
                return False, f"元宝不足，需要{price}元宝"
            player.yuanbao -= price
        elif currency == "jinzu":
            if player.jinzu < price:
                return False, f"金珠不足，需要{price}金珠"
            player.jinzu -= price
        elif currency == "points":
            # Points are virtual, not stored on player; skip balance check for now
            pass
        else:
            if player.gold < price:
                return False, f"银两不足，需要{price}银两"
            player.gold -= price

        # Grant item
        real_item_id = item_entry.get('item_id', item_id)
        DataService.add_item_to_inventory(player.id, real_item_id, quantity)

        # Track quest progress
        from services.quest_service import QuestService
        QuestService.update_buy_item_progress(player, real_item_id)

        db.session.commit()
        cn = currency_names.get(currency, "银两")
        return True, f"购买了{quantity}个{item_entry['name']}，花费{price}{cn}"
