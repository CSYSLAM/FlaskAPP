import random
import time
import math
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from services import db
from services.data_service import DataService
from models.player import (
    PlayerModel, EquipmentInstance, InventoryItem,
    EquipmentSlot, PlayerSkill, TempEffect
)


class PlayerService:
    MAX_LEVEL = 60  # 人物等级上限：达到后不再提示/执行升级

    @classmethod
    def get_max_level_exp_cap(cls):
        """经验储存上限 = 60级升级所需经验；达到后经验不再往上增加。"""
        exp_table = DataService.get_game_config().get("level_exp_table", [])
        if not exp_table:
            return 0
        idx = cls.MAX_LEVEL - 1
        return exp_table[idx] if idx < len(exp_table) else exp_table[-1]

    @classmethod
    def register(cls, username, password, nickname, player_class, gender='男', country='魏'):
        if PlayerModel.query.filter_by(username=username).first():
            return None, "用户名已存在"

        class_data = PlayerModel.CLASSES.get(player_class)
        if not class_data:
            return None, "无效职业"

        base = class_data["base_stats"]
        player = PlayerModel(
            username=username,
            password_hash=generate_password_hash(password),
            nickname=nickname,
            player_class=player_class,
            gender=gender,
            country=country,
            level=1,
            experience=0,
            exp_to_next_level=50,
            gold=1500,
            health=base["max_health"],
            max_health=base["max_health"],
            mana=base["max_mana"],
            max_mana=base["max_mana"],
            attack=base["attack"],
            defense=base["defense"],
            crit_rate=base["crit_rate"],
            dodge_rate=base["dodge_rate"],
            current_location='beiping_center.广场',
            current_view='chat',
            story_completed=False,
        )
        db.session.add(player)
        db.session.flush()

        DataService.init_equipment_slots(player.id)

        DataService.add_item_to_inventory(player.id, "potion_heal", 50, is_bound=True)
        DataService.add_item_to_inventory(player.id, "potion_mana", 50, is_bound=True)

        db.session.commit()
        return player, None

    @classmethod
    def create_character(cls, player, nickname, player_class, gender, country):
        """创建角色（注册后已存在player，只需设置角色信息）"""
        class_data = PlayerModel.CLASSES.get(player_class)
        if not class_data:
            return None, "无效职业"

        # 检查昵称是否已使用
        if PlayerModel.query.filter_by(nickname=nickname).first():
            return None, "昵称已被使用"

        base = class_data["base_stats"]
        player.nickname = nickname
        player.player_class = player_class
        player.gender = gender
        player.country = country
        player.level = 1
        player.experience = 0
        player.exp_to_next_level = 50
        player.gold = 1500
        player.health = base["max_health"]
        player.max_health = base["max_health"]
        player.mana = base["max_mana"]
        player.max_mana = base["max_mana"]
        player.attack = base["attack"]
        player.defense = base["defense"]
        player.crit_rate = base["crit_rate"]
        player.dodge_rate = base["dodge_rate"]

        DataService.init_equipment_slots(player.id)
        DataService.add_item_to_inventory(player.id, "potion_heal", 50, is_bound=True)
        DataService.add_item_to_inventory(player.id, "potion_mana", 50, is_bound=True)

        from services import db
        db.session.commit()
        return player, None

    @classmethod
    def authenticate(cls, username, password):
        player = PlayerModel.query.filter_by(username=username).first()
        if not player:
            return None, "用户名或密码错误"
        if not check_password_hash(player.password_hash, password):
            return None, "用户名或密码错误"
        player.last_login = datetime.utcnow()
        db.session.commit()
        return player, None

    @classmethod
    def get_effective_stat(cls, player, stat_name):
        value = getattr(player, stat_name, 0)
        flat, rate = DataService.get_temp_stat_bonus(player.id, stat_name)
        value = value + flat
        value = value * (1 + rate)
        return value

    @classmethod
    def get_attack(cls, player):
        from services.title_service import TitleService
        from services.social_service import SocialService
        from services.vip_service import VipService
        from services.legion_service import LegionService
        from models.lieutenant import Lieutenant
        base = player.attack
        equip_atk = cls._get_equipment_stat_sum(player, "attack")
        pill = player.pill_attack
        flat, rate = DataService.get_temp_stat_bonus(player.id, "attack")
        rank_atk = player.rank_attack
        passive = player.get_passive_bonuses()
        passive_flat = passive.get('attack', 0)
        title_bonuses = TitleService.get_title_bonuses(player)
        title_atk = title_bonuses.get('attack', 0)
        lt_bonus_flat = cls._get_lt_passive_bonus(player, 'attack')
        relation_atk = SocialService.get_online_relation_attack_bonus(player)
        social_rate = SocialService.get_social_bonus_rate(player)
        spouse_rate = SocialService.get_spouse_bonus_rate(player)
        vip_rate = VipService.get_stat_bonus_rate(player)
        legion_skills = LegionService.get_legion_skill_bonuses(player)
        legion_atk = legion_skills.get('attack', 0)
        legion_aura = LegionService.get_vip_aura_bonuses(player)
        aura_atk = legion_aura.get('attack', 0)
        from services.battlefield_service import BattlefieldService
        territory = BattlefieldService.get_territory_bonuses(player)
        territory_atk = territory.get('attack', 0)
        from services.party_service import PartyService
        party_rate = PartyService.get_party_bonus_rate(player)
        return int((base + equip_atk + pill + flat + rank_atk + title_atk + relation_atk + legion_atk + aura_atk + territory_atk + passive_flat + lt_bonus_flat) * (1 + rate + social_rate + spouse_rate + vip_rate + party_rate))

    @classmethod
    def get_defense(cls, player):
        from services.title_service import TitleService
        from services.social_service import SocialService
        from services.vip_service import VipService
        from services.legion_service import LegionService
        from models.lieutenant import Lieutenant
        base = player.defense
        equip_def = cls._get_equipment_stat_sum(player, "defense")
        pill = player.pill_defense
        flat, rate = DataService.get_temp_stat_bonus(player.id, "defense")
        passive = player.get_passive_bonuses()
        passive_flat = passive.get('defense', 0)
        title_bonuses = TitleService.get_title_bonuses(player)
        title_def = title_bonuses.get('defense', 0)
        lt_bonus_flat = cls._get_lt_passive_bonus(player, 'defense')
        social_rate = SocialService.get_social_bonus_rate(player)
        spouse_rate = SocialService.get_spouse_bonus_rate(player)
        vip_rate = VipService.get_stat_bonus_rate(player)
        legion_skills = LegionService.get_legion_skill_bonuses(player)
        legion_def = legion_skills.get('defense', 0)
        legion_aura = LegionService.get_vip_aura_bonuses(player)
        aura_def = legion_aura.get('defense', 0)
        from services.battlefield_service import BattlefieldService
        territory = BattlefieldService.get_territory_bonuses(player)
        territory_def = territory.get('defense', 0)
        from services.party_service import PartyService
        party_rate = PartyService.get_party_bonus_rate(player)
        return int((base + equip_def + pill + flat + title_def + legion_def + aura_def + territory_def + passive_flat + lt_bonus_flat) * (1 + rate + social_rate + spouse_rate + vip_rate + party_rate))

    @classmethod
    def get_max_health(cls, player):
        from services.title_service import TitleService
        from services.social_service import SocialService
        from services.vip_service import VipService
        from services.legion_service import LegionService
        from models.lieutenant import Lieutenant
        base = player.max_health
        equip_hp = cls._get_equipment_stat_sum(player, "max_health")
        pill = player.pill_max_health
        flat, rate = DataService.get_temp_stat_bonus(player.id, "max_health")
        passive = player.get_passive_bonuses()
        passive_flat = passive.get('max_health', 0)
        title_bonuses = TitleService.get_title_bonuses(player)
        title_hp = title_bonuses.get('max_health', 0)
        lt_bonus_flat = cls._get_lt_passive_bonus(player, 'health')
        social_rate = SocialService.get_social_bonus_rate(player)
        spouse_rate = SocialService.get_spouse_bonus_rate(player)
        vip_rate = VipService.get_stat_bonus_rate(player)
        legion_skills = LegionService.get_legion_skill_bonuses(player)
        legion_hp = legion_skills.get('max_health', 0)
        legion_aura = LegionService.get_vip_aura_bonuses(player)
        aura_hp = legion_aura.get('max_health', 0)
        from services.battlefield_service import BattlefieldService
        territory = BattlefieldService.get_territory_bonuses(player)
        territory_hp = territory.get('max_health', 0)
        return int((base + equip_hp + pill + flat + title_hp + legion_hp + aura_hp + territory_hp + passive_flat + lt_bonus_flat) * (1 + rate + social_rate + spouse_rate + vip_rate))

    @classmethod
    def get_max_mana(cls, player):
        from services.title_service import TitleService
        from services.social_service import SocialService
        from services.vip_service import VipService
        from services.legion_service import LegionService
        from models.lieutenant import Lieutenant
        base = player.max_mana
        equip_mp = cls._get_equipment_stat_sum(player, "max_mana")
        pill = player.pill_max_mana
        flat, rate = DataService.get_temp_stat_bonus(player.id, "max_mana")
        passive = player.get_passive_bonuses()
        passive_flat = passive.get('max_mana', 0)
        title_bonuses = TitleService.get_title_bonuses(player)
        title_mp = title_bonuses.get('max_mana', 0)
        lt_bonus_flat = cls._get_lt_passive_bonus(player, 'mana')
        social_rate = SocialService.get_social_bonus_rate(player)
        spouse_rate = SocialService.get_spouse_bonus_rate(player)
        vip_rate = VipService.get_stat_bonus_rate(player)
        legion_skills = LegionService.get_legion_skill_bonuses(player)
        legion_mp = legion_skills.get('max_mana', 0)
        from services.battlefield_service import BattlefieldService
        territory = BattlefieldService.get_territory_bonuses(player)
        territory_mp = territory.get('max_mana', 0)
        return int((base + equip_mp + pill + flat + title_mp + legion_mp + territory_mp + passive_flat + lt_bonus_flat) * (1 + rate + social_rate + spouse_rate + vip_rate))

    @classmethod
    def _get_equipment_stat_sum(cls, player, stat_name):
        total = 0
        equipped = DataService.get_equipped(player.id)
        for slot_name, equip in equipped.items():
            if equip:
                total += equip.get_base_stats().get(stat_name, 0)
                extra = equip.get_extra_stats().get(stat_name)
                if extra and isinstance(extra, list):
                    total += extra[0]
        if stat_name in ('crit_rate', 'dodge_rate'):
            return total
        return int(total)

    @classmethod
    def _get_lt_passive_bonus(cls, player, bonus_type):
        """Get lieutenant passive bonus for a stat type. Returns (flat, rate) tuple.
        attack/defense/health/mana are flat values (already computed from lt stat × %).
        crit/dodge are also flat values (rate points added to player's rate)."""
        from models.lieutenant import Lieutenant
        lt = Lieutenant.query.filter_by(owner_id=player.id, is_deployed=True, is_alive=True).first()
        if not lt:
            return 0
        bonus = lt.get_passive_bonus()
        return bonus.get(bonus_type, 0)

    @classmethod
    def level_up(cls, player):
        if player.level >= cls.MAX_LEVEL:
            return False  # 满级：不再升级(经验保留,由 gain_experience 封顶)
        if player.experience < player.exp_to_next_level:
            return False

        class_data = PlayerModel.CLASSES.get(player.player_class)
        if not class_data:
            return False

        lvl_stats = class_data["level_up_stats"]
        old_max_health = cls.get_max_health(player)
        old_max_mana = cls.get_max_mana(player)

        player.level += 1
        player.experience -= player.exp_to_next_level
        player.max_health += lvl_stats["max_health"]
        player.max_mana += lvl_stats["max_mana"]
        player.attack += lvl_stats["attack"]
        player.defense += lvl_stats["defense"]
        player.crit_rate += lvl_stats["crit_rate"]
        player.dodge_rate += lvl_stats["dodge_rate"]

        new_max_health = cls.get_max_health(player)
        new_max_mana = cls.get_max_mana(player)
        player.health += (new_max_health - old_max_health)
        player.mana += (new_max_mana - old_max_mana)
        player.health = min(player.health, new_max_health)
        player.mana = min(player.mana, new_max_mana)

        exp_table = DataService.get_game_config().get("level_exp_table", [])
        if player.level - 1 < len(exp_table):
            player.exp_to_next_level = exp_table[player.level - 1]

        cls.update_military_rank(player)
        return True

    @classmethod
    def update_military_rank(cls, player):
        new_rank = "士兵"
        new_attack = 0
        for rank_name, rank_data in sorted(
                PlayerModel.MILITARY_RANKS.items(),
                key=lambda x: x[1]["level"], reverse=True):
            if player.level >= rank_data["level"] and player.honor >= rank_data["honor"]:
                new_rank = rank_name
                new_attack = rank_data["attack"]
                break
        player.military_rank = new_rank
        player.rank_attack = new_attack

    @classmethod
    def gain_experience(cls, player, amount):
        # 手动升级：经验够时不再自动升级，由玩家在界面手动点击升级
        # （升级时 HP/MP 恢复满，见 level_up / level_up_now）
        player.experience = (player.experience or 0) + amount
        # 经验储存上限 = 60级升级所需经验，达到后不再往上增加(满级同样适用)
        cap = cls.get_max_level_exp_cap()
        if cap > 0 and player.experience > cap:
            player.experience = cap

    @classmethod
    def can_level_up(cls, player):
        """是否可手动升级(经验达升级线)。"""
        if player.level >= cls.MAX_LEVEL:
            return False
        return player.experience >= player.exp_to_next_level

    @classmethod
    def level_up_now(cls, player):
        """玩家手动升级：消耗经验升一级，HP/MP 恢复满。返回是否成功。"""
        if not cls.can_level_up(player):
            return False
        if not cls.level_up(player):
            return False
        # 升级后状态恢复满
        player.health = cls.get_max_health(player)
        player.mana = cls.get_max_mana(player)
        from services.achievement_service import AchievementService
        AchievementService.check(player, 'level', player.level)
        return True

    @classmethod
    def rest(cls, player):
        player.health = cls.get_max_health(player)
        player.mana = cls.get_max_mana(player)
        player.in_battle = False
        player.current_encounter = None
        DataService.clear_expired_effects(player.id)
        db.session.commit()

    @classmethod
    def use_item(cls, player, item_id, quantity=1):
        inv = DataService.get_inventory_item(player.id, item_id)
        if not inv or inv.quantity < quantity:
            return False, "物品不足"

        item_data = DataService.get_item(item_id)
        if not item_data:
            return False, "物品不存在"

        effect_text = ""
        for _ in range(quantity):
            effect_text += cls._apply_item_effect(player, item_id, item_data)

        DataService.remove_item_from_inventory(player.id, item_id, quantity)
        db.session.commit()
        return True, effect_text

    @classmethod
    def _apply_item_effect(cls, player, item_id, item_data):
        from models.item import Item
        effect = item_data.get("effect", {})
        effect_text = ""

        if effect.get("type") == "heal":
            heal_amount = effect.get("value", 0)
            if effect.get("rate"):
                heal_amount = int(cls.get_max_health(player) * effect["rate"])
            player.health = min(player.health + heal_amount, cls.get_max_health(player))
            effect_text = f"恢复了 {heal_amount} 点生命值"

        elif effect.get("type") == "mana":
            mana_amount = effect.get("value", 0)
            if effect.get("rate"):
                mana_amount = int(cls.get_max_mana(player) * effect["rate"])
            player.mana = min(player.mana + mana_amount, cls.get_max_mana(player))
            effect_text = f"恢复了 {mana_amount} 点魔法值"

        elif effect.get("type") == "exp":
            exp_amount = effect.get("value", 0)
            cls.gain_experience(player, exp_amount)
            effect_text = f"获得了 {exp_amount} 点经验值"

        elif effect.get("type") == "buff":
            for stat, value in effect.get("stats", {}).items():
                if hasattr(player, stat):
                    setattr(player, stat, getattr(player, stat) + value)
            effect_text = f"属性提升了"

        elif effect.get("type") == "temp_buff":
            stat = effect.get("stat")
            value = effect.get("value", 0)
            rate = effect.get("rate", 0)
            duration = effect.get("duration", 300)
            expire = time.time() + duration
            temp = TempEffect(
                player_id=player.id,
                stat=stat,
                value=value,
                rate=rate,
                expire_time=expire,
                item_id=item_id,
                effect_name=item_data.get("name", item_id)
            )
            db.session.add(temp)
            effect_text = f"获得了临时增益效果"

        elif effect.get("type") == "pill":
            stat_map = {
                "attack": "pill_attack",
                "defense": "pill_defense",
                "max_health": "pill_max_health",
                "max_mana": "pill_max_mana"
            }
            for stat, value in effect.get("stats", {}).items():
                col = stat_map.get(stat)
                if col:
                    setattr(player, col, getattr(player, col) + value)
            effect_text = f"属性永久提升"

        return effect_text + "；" if effect_text else ""

    @classmethod
    def get_avatar_path(cls, player):
        # Avatar prefix: gender + class
        prefix_map = {
            ("男", "刺客"): "a", ("女", "刺客"): "b",
            ("男", "战士"): "c", ("女", "战士"): "q",
            ("男", "术士"): "f", ("女", "术士"): "s",
        }
        prefix = prefix_map.get((player.gender, player.player_class), "a")

        # Map military rank to tier number (01-11)
        # 11 avatars, 12 ranks - 列兵 uses 01, 大都督 uses 11
        rank_tiers = [
            "列兵", "十夫长", "百夫长", "校尉", "都尉",
            "裨将", "偏将", "中郎将", "车骑将军", "骠骑将军",
            "大司马", "大都督",
        ]
        idx = rank_tiers.index(player.military_rank) if player.military_rank in rank_tiers else 0
        # Map 12 ranks to 11 tiers: last two share tier 11
        tier = min(idx + 1, 11)
        return f"rongyu/{prefix}{tier:02d}.png"
