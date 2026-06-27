import json
import time
import random
import sys
from pathlib import Path
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from services import db, ConcurrentModificationError
from services.achievement_catalog import (
    ALIGNED_CATEGORIES,
    build_aligned_item_achievements,
)
from models.player import (
    PlayerModel, EquipmentInstance, InventoryItem,
    EquipmentSlot, PlayerSkill, TempEffect, ChatMessage
)


def get_base_path():
    """获取基础路径，支持PyInstaller打包"""
    if getattr(sys, 'frozen', False):
        # 打包后的exe运行时
        return Path(sys.executable).parent
    else:
        # 正常Python运行时
        return Path(__file__).parent.parent


class DataService:
    _app = None
    _cache = {}
    _ground_items = {}  # location_id -> {"items": [...], "next_refresh": timestamp}
    GROUND_REFRESH_INTERVAL = 60  # seconds

    @classmethod
    def init_app(cls, app):
        cls._app = app
        cls._load_all_data()

    @classmethod
    def _load_all_data(cls):
        data_dir = get_base_path() / "data"
        files = {
            'items': 'items.json',
            'monsters': 'monsters.json',
            'copy_dungeons': 'copy_dungeons.json',
            'equipment_templates': 'equipment_templates.json',
            'shops': 'shops.json',
            'skills': 'skills.json',
            'game_config': 'game_config.json',
            'achievements': 'achievements.json',
            'titles': 'titles.json',
            'guides': 'guides.json',
        }
        for key, filename in files.items():
            filepath = data_dir / filename
            if filepath.exists():
                with open(filepath, 'r', encoding='utf-8') as f:
                    cls._cache[key] = json.load(f)
            else:
                cls._cache[key] = {}

        copy_monsters_path = data_dir / 'copy_monsters.json'
        if copy_monsters_path.exists():
            with open(copy_monsters_path, 'r', encoding='utf-8') as f:
                cls._cache.setdefault('monsters', {}).update(json.load(f))

        # Load locations from data/locations/ directory (one file per area)
        loc_dir = data_dir / "locations"
        raw_locations = {}
        if loc_dir.exists():
            for fp in sorted(loc_dir.glob("*.json")):
                with open(fp, 'r', encoding='utf-8') as f:
                    area_data = json.load(f)
                    area_key = fp.stem
                    raw_locations[area_key] = area_data
        # Load equipment sets from data/equipment_sets/ directory
        sets_dir = data_dir / "equipment_sets"
        if sets_dir.exists():
            for fp in sorted(sets_dir.glob("*.json")):
                with open(fp, 'r', encoding='utf-8') as f:
                    set_data = json.load(f)
                    cls._cache['equipment_templates'].update(set_data)

        cls._cache['locations_raw'] = raw_locations
        cls._cache['locations_flat'] = cls._flatten_locations(raw_locations)

    @classmethod
    def _flatten_locations(cls, raw_locations):
        flat = {}
        if not raw_locations:
            return flat
        for area_key, area_data in raw_locations.items():
            if isinstance(area_data, dict) and 'scenes' in area_data:
                area_name = area_data.get('name', area_key)
                area_meta = {key: value for key, value in area_data.items() if key not in {'name', 'scenes'}}
                for scene_key, scene_data in area_data['scenes'].items():
                    full_id = f"{area_key}.{scene_key}"
                    entry = dict(scene_data)
                    entry['area_id'] = area_key
                    entry['area_name'] = area_name
                    entry['scene_id'] = scene_key
                    for meta_key, meta_value in area_meta.items():
                        entry.setdefault(meta_key, meta_value)
                    if 'monster_type' in entry and 'monsters' not in entry:
                        entry['monsters'] = [entry['monster_type']]
                    # Convert exits dict to directional keys
                    exits = entry.get('exits', {})
                    entry['north_exit'] = exits.get('north')
                    entry['south_exit'] = exits.get('south')
                    entry['east_exit'] = exits.get('east')
                    entry['west_exit'] = exits.get('west')
                    flat[full_id] = entry
            elif isinstance(area_data, dict) and 'monster_type' in area_data:
                entry = dict(area_data)
                exits = entry.get('exits', {})
                entry['north_exit'] = exits.get('north')
                entry['south_exit'] = exits.get('south')
                entry['east_exit'] = exits.get('east')
                entry['west_exit'] = exits.get('west')
                flat[area_key] = entry
        return flat

    @classmethod
    def get_items(cls):
        return cls._cache.get('items', {})

    @classmethod
    def get_item(cls, item_id):
        return cls._cache.get('items', {}).get(item_id)

    @classmethod
    def get_item_effect_hint(cls, item_id):
        """返回物品使用效果摘要文本，如 '攻击+5%' '经验+50000' 等"""
        item = cls.get_item(item_id)
        if not item or not item.get('is_usable', False):
            return ''
        effect = item.get('usage_effect', {})
        hints = []
        # stat_changes
        for stat, value in effect.get('stat_changes', {}).items():
            stat_names = {
                'experience': '经验', 'honor': '荣誉', 'gold': '银两',
                'yuanbao': '元宝', 'jinzu': '金珠',
                'pill_attack': '攻击', 'pill_defense': '防御',
                'pill_max_health': '生命', 'pill_max_mana': '魔法',
                'blood_reserve': '生命储备', 'mana_reserve': '魔法储备',
                'health': '生命', 'mana': '魔法',
            }
            name = stat_names.get(stat, stat)
            hints.append(f"{name}+{value}")
        # temp_effects
        for te in effect.get('temp_effects', []):
            stat = te.get('stat', '')
            rate = te.get('rate', 0)
            value = te.get('value', 0)
            stat_names = {
                'max_health': '生命', 'max_mana': '魔法',
                'attack': '攻击', 'defense': '防御',
                'crit_rate': '暴击', 'dodge_rate': '闪避',
                'experience': '经验', 'exp_rate': '经验',
                'lt_exp_rate': '副将经验',
            }
            name = stat_names.get(stat, stat)
            if rate > 0:
                hints.append(f"{name}+{rate*100:.0f}%")
            elif value > 0:
                hints.append(f"{name}+{value}")
        # grant_gold
        grant_gold = effect.get('grant_gold')
        if grant_gold:
            hints.append(f"银两+{grant_gold}")
        # vip_days
        vip_days = effect.get('vip_days')
        if vip_days:
            hints.append(f"VIP+{vip_days}天")
        # restore_vitality
        restore_vitality = effect.get('restore_vitality')
        if restore_vitality:
            hints.append(f"行动力+{restore_vitality}")
        # expand_backpack / expand_warehouse
        expand_bp = effect.get('expand_backpack')
        if expand_bp:
            hints.append(f"背包+{expand_bp}")
        expand_wh = effect.get('expand_warehouse')
        if expand_wh:
            hints.append(f"仓库+{expand_wh}")
        return ' '.join(hints) if hints else ''

    @classmethod
    def get_monsters(cls):
        return cls._cache.get('monsters', {})

    @classmethod
    def get_monster(cls, monster_id):
        return cls._cache.get('monsters', {}).get(monster_id)

    @classmethod
    def get_copy_dungeons(cls):
        return cls._cache.get('copy_dungeons', {})

    @classmethod
    def get_copy_dungeon(cls, dungeon_id):
        return cls.get_copy_dungeons().get(dungeon_id)

    @classmethod
    def get_locations(cls):
        return cls._cache.get('locations_flat', {})

    @classmethod
    def get_location(cls, location_id):
        return cls._cache.get('locations_flat', {}).get(location_id)

    @classmethod
    def get_equipment_templates(cls):
        return cls._cache.get('equipment_templates', {})

    @classmethod
    def get_equipment_template(cls, template_id):
        return cls._cache.get('equipment_templates', {}).get(template_id)

    @classmethod
    def get_shops(cls):
        return cls._cache.get('shops', {})

    @classmethod
    def get_skills(cls):
        skills_data = cls._cache.get('skills', {})
        all_skills = {}
        all_skills.update(skills_data.get('active', {}))
        all_skills.update(skills_data.get('passive', {}))
        return all_skills

    @classmethod
    def get_skill(cls, skill_id):
        return cls.get_skills().get(skill_id)

    @classmethod
    def get_active_skills(cls):
        return cls._cache.get('skills', {}).get('active', {})

    @classmethod
    def get_passive_skills(cls):
        return cls._cache.get('skills', {}).get('passive', {})

    @classmethod
    def get_shops(cls):
        return cls._cache.get('shops', {})

    @classmethod
    def get_game_config(cls):
        return cls._cache.get('game_config', {})

    @classmethod
    def get_achievements(cls):
        base = cls._cache.get('achievements', {}).get('achievements', {})
        # 用站点对齐后的道具成就覆盖旧版道具定义，其他分类先沿用现有本地数据。
        merged = {
            aid: adef for aid, adef in base.items()
            if adef.get('condition_type') != 'item_use'
        }
        merged.update(build_aligned_item_achievements())
        return merged

    @classmethod
    def get_achievement_categories(cls):
        return list(ALIGNED_CATEGORIES)

    # --- Title methods ---
    @classmethod
    def get_titles(cls):
        return cls._cache.get('titles', {})

    @classmethod
    def get_title_prefixes(cls):
        return cls._cache.get('titles', {}).get('prefixes', {})

    @classmethod
    def get_title_suffixes(cls):
        return cls._cache.get('titles', {}).get('suffixes', {})

    @classmethod
    def get_title(cls, title_id, title_type):
        """Get a specific title by ID and type ('prefix' or 'suffix')."""
        titles = cls._cache.get('titles', {})
        if title_type == 'prefix':
            return titles.get('prefixes', {}).get(title_id)
        elif title_type == 'suffix':
            return titles.get('suffixes', {}).get(title_id)
        return None

    @classmethod
    def get_star_bonus(cls, stars):
        """Get the base bonus values for a given star rating."""
        star_bonuses = cls._cache.get('titles', {}).get('star_bonuses', {})
        return star_bonuses.get(str(stars), {})

    # --- Player CRUD ---

    @classmethod
    def get_player_by_username(cls, username):
        return PlayerModel.query.filter_by(username=username).first()

    @classmethod
    def get_player_by_id(cls, player_id):
        return PlayerModel.query.get(player_id)

    @classmethod
    def get_player_by_uid(cls, player_uid):
        return PlayerModel.query.filter_by(player_uid=player_uid).first()

    @classmethod
    def save_player(cls, player):
        old_version = player.version
        player.version = (player.version or 0) + 1
        result = db.session.commit()
        # SQLite doesn't support rowcount on commit, so we verify by re-querying
        fresh = PlayerModel.query.get(player.id)
        if fresh and fresh.version != player.version:
            db.session.rollback()
            raise ConcurrentModificationError(
                f"Player {player.id} was modified by another transaction")

    @classmethod
    def save_players(cls, *players):
        for p in players:
            p.version = (p.version or 0) + 1
        db.session.commit()

    @classmethod
    def get_all_players_in_location(cls, location_id, exclude_player_id=None):
        query = PlayerModel.query.filter_by(current_location=location_id)
        if exclude_player_id:
            query = query.filter(PlayerModel.id != exclude_player_id)
        return query.all()

    # --- Equipment Instance CRUD ---

    @classmethod
    def create_equipment_instance(cls, player_id, template_id, rarity, stars):
        template = cls.get_equipment_template(template_id)
        if not template:
            return None

        ratio = stars / 5
        base_stats = {stat: int(value * ratio) for stat, value in template.get("base_stats", {}).items()}
        initial_stats = base_stats.copy()
        extra_stats = cls._generate_extra_stats(template, rarity, stars)

        equip = EquipmentInstance(
            player_id=player_id,
            template_id=template_id,
            slot=template.get("slot", "weapon"),
            rarity=rarity,
            stars=stars,
            level_required=template.get("level_required", 1),
            class_required=template.get("class_required"),
            is_bound=template.get("is_bound", False),
            enhance_level=0,
        )
        equip.set_base_stats(base_stats)
        equip.set_extra_stats(extra_stats)
        equip.set_initial_stats(initial_stats)
        equip.update_name()

        db.session.add(equip)
        db.session.flush()
        return equip

    @classmethod
    def _generate_extra_stats(cls, template, rarity, stars):
        extra_stats = {}
        stat_counts = {"普通": 1, "精良": 2, "卓越": 3, "史诗": 4, "神器": 5}
        count = stat_counts.get(rarity, 1)

        weapon_order = [
            ["attack"],
            ["attack", "max_health"],
            ["attack", "max_health", "crit_rate"],
            ["attack", "max_health", "crit_rate", "max_mana"],
            ["attack", "max_health", "crit_rate", "max_mana", "defense"],
            ["attack", "max_health", "crit_rate", "max_mana", "defense", "dodge_rate"],
        ]
        armor_order = [
            ["defense"],
            ["defense", "max_health"],
            ["defense", "max_health", "max_mana"],
            ["defense", "max_health", "crit_rate", "max_mana"],
            ["attack", "max_health", "crit_rate", "max_mana", "defense"],
            ["attack", "max_health", "crit_rate", "max_mana", "defense", "dodge_rate"],
        ]

        slot = template.get("slot", "armor")
        selected = (weapon_order[count - 1] if slot == "weapon" else armor_order[count - 1])

        # Shoes and pants prioritize dodge_rate over crit_rate
        if slot in ("shoes", "pants"):
            # Replace crit_rate -> dodge_rate in the selected order, then deduplicate
            selected = [
                "dodge_rate" if s == "crit_rate" else s
                for s in selected
            ]
            # Remove duplicates (keep first)
            seen = set()
            deduped = []
            for s in selected:
                if s not in seen:
                    seen.add(s)
                    deduped.append(s)
            selected = deduped

        for stat in selected:
            stat_stars = min(5, max(1, random.randint(stars - 1, stars + 1)))
            max_value = template.get("max_extra_stats", {}).get(stat, 0)
            actual_value = max_value * (stat_stars / 5)
            extra_stats[stat] = [actual_value, stat_stars]

        return extra_stats

    # --- Inventory CRUD ---

    @classmethod
    def add_item_to_inventory(cls, player_id, item_id, quantity=1, is_bound=False):
        inv = InventoryItem.query.filter_by(
            player_id=player_id, item_id=item_id, is_bound=is_bound).first()
        if inv:
            inv.quantity += quantity
        else:
            inv = InventoryItem(player_id=player_id, item_id=item_id,
                                quantity=quantity, is_bound=is_bound)
            db.session.add(inv)
        db.session.flush()
        return inv

    @classmethod
    def remove_item_from_inventory(cls, player_id, item_id, quantity=1, is_bound=None):
        if is_bound is not None:
            inv = InventoryItem.query.filter_by(
                player_id=player_id, item_id=item_id, is_bound=is_bound).first()
        else:
            inv = InventoryItem.query.filter_by(
                player_id=player_id, item_id=item_id).first()
        if not inv:
            return False
        inv.quantity -= quantity
        if inv.quantity <= 0:
            db.session.delete(inv)
        db.session.flush()
        return True

    @classmethod
    def get_inventory_item(cls, player_id, item_id, is_bound=None):
        if is_bound is not None:
            return InventoryItem.query.filter_by(
                player_id=player_id, item_id=item_id, is_bound=is_bound).first()
        return InventoryItem.query.filter_by(
            player_id=player_id, item_id=item_id).first()

    @classmethod
    def get_inventory(cls, player_id):
        return InventoryItem.query.filter_by(player_id=player_id).all()

    # --- Equipment Slots ---

    @classmethod
    def get_equipped(cls, player_id):
        result = {}
        slots = EquipmentSlot.query.filter_by(player_id=player_id).all()
        for s in slots:
            if s.equipment_instance_id:
                equip = EquipmentInstance.query.get(s.equipment_instance_id)
                result[s.slot_name] = equip
            else:
                result[s.slot_name] = None
        return result

    @classmethod
    def init_equipment_slots(cls, player_id):
        for slot_name in EquipmentInstance.SLOTS:
            existing = EquipmentSlot.query.filter_by(
                player_id=player_id, slot_name=slot_name).first()
            if not existing:
                db.session.add(EquipmentSlot(player_id=player_id, slot_name=slot_name))
        db.session.flush()

    @classmethod
    def get_unequipped_equipment(cls, player_id):
        equipped_ids = {s.equipment_instance_id for s in
                        EquipmentSlot.query.filter_by(player_id=player_id).all()
                        if s.equipment_instance_id}
        return EquipmentInstance.query.filter(
            EquipmentInstance.player_id == player_id,
            ~EquipmentInstance.id.in_(equipped_ids)
        ).all() if equipped_ids else EquipmentInstance.query.filter_by(
            player_id=player_id).all()

    # --- Capacity ---

    @classmethod
    def get_backpack_used_capacity(cls, player_id):
        """背包已用容量：物品 + 未装备的装备"""
        total = 0.0
        # Items: capacity from items.json * quantity
        for inv in cls.get_inventory(player_id):
            item_data = cls.get_item(inv.item_id)
            cap = item_data.get('capacity', 0.5) if item_data else 0.5
            total += cap * inv.quantity
        # Unequipped equipment: each equipment = 1
        for equip in cls.get_unequipped_equipment(player_id):
            total += 1.0
        return total

    @classmethod
    def get_warehouse_used_capacity(cls, player_id):
        """仓库已用容量"""
        from models.player import WarehouseItem
        total = 0.0
        for wh in WarehouseItem.query.filter_by(player_id=player_id).all():
            item_data = cls.get_item(wh.item_id)
            cap = item_data.get('capacity', 0.5) if item_data else 0.5
            total += cap * wh.quantity
        return total

    # --- Temp Effects ---

    @classmethod
    def clear_expired_effects(cls, player_id):
        now = time.time()
        TempEffect.query.filter(
            TempEffect.player_id == player_id,
            TempEffect.expire_time <= now
        ).delete(synchronize_session=False)
        db.session.flush()

    @classmethod
    def get_temp_effects(cls, player_id):
        cls.clear_expired_effects(player_id)
        return TempEffect.query.filter_by(player_id=player_id).all()

    @classmethod
    def get_temp_stat_bonus(cls, player_id, stat):
        cls.clear_expired_effects(player_id)
        effects = TempEffect.query.filter_by(
            player_id=player_id, stat=stat).all()
        flat = sum(e.value for e in effects)
        rate = sum(e.rate for e in effects)
        return flat, rate

    # --- Chat ---

    @classmethod
    def broadcast_system(cls, content):
        msg = ChatMessage(
            sender_id=None,
            content=content,
            message_type='system'
        )
        db.session.add(msg)
        db.session.commit()

    @classmethod
    def broadcast_player(cls, player_id, content):
        msg = ChatMessage(
            sender_id=player_id,
            content=content,
            message_type='player'
        )
        db.session.add(msg)
        db.session.commit()

    @classmethod
    def list_latest_messages(cls, limit=10):
        return ChatMessage.query.filter_by(
            message_type='public'
        ).order_by(
            ChatMessage.created_at.desc()
        ).limit(limit).all()

    @classmethod
    def send_private_message(cls, sender_id, receiver_id, content):
        msg = ChatMessage(
            sender_id=sender_id,
            receiver_id=receiver_id,
            content=content,
            message_type='private'
        )
        db.session.add(msg)
        db.session.commit()
        return msg

    # --- Ground Items ---

    @classmethod
    def get_ground_items(cls, location_id):
        now = time.time()
        ground = cls._ground_items.get(location_id)
        if not ground or now >= ground['next_refresh']:
            cls._refresh_ground_items(location_id)
            ground = cls._ground_items[location_id]
        return ground['items']

    @classmethod
    def _refresh_ground_items(cls, location_id):
        now = time.time()
        items = []
        cls._ground_items[location_id] = {
            'items': items,
            'next_refresh': now + cls.GROUND_REFRESH_INTERVAL
        }

    @classmethod
    def pickup_ground_item(cls, location_id, item_id):
        ground = cls._ground_items.get(location_id)
        if not ground:
            return None
        for i, item in enumerate(ground['items']):
            if item['id'] == item_id:
                ground['items'].pop(i)
                return item
        return None

    # --- Guides ---

    @classmethod
    def get_guides(cls):
        return cls._cache.get('guides', {})
