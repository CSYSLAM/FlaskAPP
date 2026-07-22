import json
import time
import random
import uuid
from datetime import datetime
from flask_login import UserMixin
from services import db


class PlayerModel(db.Model, UserMixin):
    __tablename__ = 'players'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    player_uid = db.Column(db.String(10), unique=True, nullable=True, index=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    nickname = db.Column(db.String(64), nullable=False)
    player_class = db.Column(db.String(20), nullable=False)
    gender = db.Column(db.String(4), default='男')

    level = db.Column(db.Integer, default=1)
    experience = db.Column(db.Integer, default=0)
    exp_to_next_level = db.Column(db.Integer, default=50)
    gold = db.Column(db.Integer, default=0)
    yuanbao = db.Column(db.Integer, default=0)
    jinzu = db.Column(db.Integer, default=0)
    yuanbao_spent = db.Column(db.Integer, default=0)  # 累计消费元宝
    jinzu_spent = db.Column(db.Integer, default=0)    # 累计消费金珠

    # Warehouse silver (stored in warehouse)
    warehouse_gold = db.Column(db.Integer, default=0)

    # Backpack and warehouse capacity
    backpack_capacity = db.Column(db.Integer, default=20)
    warehouse_capacity = db.Column(db.Integer, default=20)

    # Country (魏蜀吴)
    country = db.Column(db.String(10), default='魏')

    health = db.Column(db.Integer, default=0)
    max_health = db.Column(db.Integer, default=0)
    mana = db.Column(db.Integer, default=0)
    max_mana = db.Column(db.Integer, default=0)
    attack = db.Column(db.Integer, default=0)
    defense = db.Column(db.Integer, default=0)
    crit_rate = db.Column(db.Float, default=0.0)
    dodge_rate = db.Column(db.Float, default=0.0)

    pill_attack = db.Column(db.Integer, default=0)
    pill_defense = db.Column(db.Integer, default=0)
    pill_max_health = db.Column(db.Integer, default=0)
    pill_max_mana = db.Column(db.Integer, default=0)

    current_location = db.Column(db.String(64), default='beiping_center.广场')
    honor = db.Column(db.Integer, default=0)
    military_rank = db.Column(db.String(20), default='士兵')
    rank_attack = db.Column(db.Integer, default=0)

    in_battle = db.Column(db.Boolean, default=False)
    in_pk = db.Column(db.Boolean, default=False)
    pk_opponent = db.Column(db.String(64), nullable=True)
    in_battlefield = db.Column(db.Boolean, default=False)
    battlefield_city = db.Column(db.String(32), nullable=True)
    battlefield_death_time = db.Column(db.Float, default=0.0)
    party_id = db.Column(db.Integer, nullable=True)
    last_attack_time = db.Column(db.Float, default=0.0)
    enhance_bonus_rate = db.Column(db.Float, default=0.0)  # 强化失败累积成功率加成(每失败+5%)
    enhance_luck_small = db.Column(db.Boolean, default=False)  # 强化小幸运符(+5%)
    enhance_luck_medium = db.Column(db.Boolean, default=False)  # 强化中幸运符(+15%)

    last_damage_taken = db.Column(db.Integer, default=0)
    last_damage_dealt = db.Column(db.String(32), default='')
    last_battle_result = db.Column(db.String(256), default='')
    last_action = db.Column(db.String(128), default='')
    last_skill = db.Column(db.String(64), default='')
    last_mana_cost = db.Column(db.Integer, default=0)
    item_effect = db.Column(db.String(256), default='')
    # 本回合生命/魔法净变化(带符号): 怪物打扣血为正, 回血为负; 用于战斗界面括号显示
    last_hp_delta = db.Column(db.Integer, default=0)
    last_mp_delta = db.Column(db.Integer, default=0)

    # HP/MP reserve pool (血石/魔石)
    blood_reserve = db.Column(db.Integer, default=0)
    mana_reserve = db.Column(db.Integer, default=0)
    blood_reserve_enabled = db.Column(db.Boolean, default=False)
    mana_reserve_enabled = db.Column(db.Boolean, default=False)

    # Quest system: JSON tracking {quest_id: progress, ...}
    active_quests = db.Column(db.Text, default='{}')
    completed_quests = db.Column(db.Text, default='[]')

    current_view = db.Column(db.String(20), default='chat')
    current_encounter = db.Column(db.Text, nullable=True)

    shortcuts_raw = db.Column('shortcuts', db.Text, default='{"skill1":"attack","skill2":"attack","skill3":"attack","skill4":"attack","potion1":null,"potion2":null}')
    chat_history_raw = db.Column('chat_history', db.Text, default='{}')
    last_chat_message = db.Column(db.Text, nullable=True)
    chat_refresh_count = db.Column(db.Integer, default=0)
    notifications_raw = db.Column('notifications', db.Text, default='[]')

    # Achievement tracking counters
    kill_count = db.Column(db.Integer, default=0)
    elite_kill_count = db.Column(db.Integer, default=0)
    pk_win_count = db.Column(db.Integer, default=0)
    pk_loss_count = db.Column(db.Integer, default=0)
    gold_earned = db.Column(db.Integer, default=0)
    gift_count = db.Column(db.Integer, default=0)
    chat_count = db.Column(db.Integer, default=0)
    item_usage_raw = db.Column(db.Text, default='{}')  # JSON: {item_id: count}
    dungeon_clears_raw = db.Column(db.Text, default='{}')  # JSON: {dungeon_id: clear_count}
    boss_kills_raw = db.Column(db.Text, default='{}')  # JSON: {boss_name: kill_count}
    elite_kills_by_area_raw = db.Column(db.Text, default='{}')  # JSON: {area: kill_count} (kunlun/shennong/wokou)
    monster_kills_raw = db.Column(db.Text, default='{}')  # JSON: {monster_id: kill_count}
    divine_beast_kills = db.Column(db.Integer, default=0)  # 神兽累计击杀数
    forge_count = db.Column(db.Integer, default=0)  # 累计打造装备次数
    enhance_success_count = db.Column(db.Integer, default=0)  # 累计强化成功次数
    enhance_fail_count = db.Column(db.Integer, default=0)  # 累计强化失败次数
    enhance_50_count = db.Column(db.Integer, default=0)  # 累计强化到+50的装备件数
    tower_max_floor = db.Column(db.Integer, default=0)
    visited_locations_raw = db.Column('visited_locations', db.Text, default='[]')

    title_prefix_id = db.Column(db.String(64), nullable=True)
    title_suffix_id = db.Column(db.String(64), nullable=True)
    owned_titles_raw = db.Column('owned_titles', db.Text, default='[]')

    activity_data_raw = db.Column('activity_data', db.Text, default='{}')

    # Finance (理财·股市) holdings: {holdings:{stock_id:{shares,avg_cost}}, realized_profit, total_traded}
    finance_data_raw = db.Column('finance_data', db.Text, default='{}')

    # Enemy list (仇人)
    enemies_raw = db.Column('enemies', db.Text, default='[]')

    # Friend list (好友)
    friends_raw = db.Column('friends', db.Text, default='[]')

    # Blacklist (黑名单)
    blacklist_raw = db.Column('blacklist', db.Text, default='[]')

    # Charm value (魅力值)
    charm = db.Column(db.Integer, default=0)

    # Relationship requests pending (结交邀请)
    relation_requests_raw = db.Column('relation_requests', db.Text, default='[]')

    # Need revive flag
    need_revive = db.Column(db.Boolean, default=False)
    killed_by = db.Column(db.String(64), nullable=True)  # Username of killer

    # Battle status effects (rounds remaining; 0 = none)
    # 混乱: 无法普攻/技能/撤退，且受到攻击伤害减半
    status_confuse_rounds = db.Column(db.Integer, default=0)
    # 封魔: 无法使用技能（仅可普攻/撤退）
    status_silence_rounds = db.Column(db.Integer, default=0)
    # 流血: 每回合开始流失固定生命值（PK 用，PVE 怪物流血存于 encounter）
    status_bleed_rounds = db.Column(db.Integer, default=0)
    status_bleed_value = db.Column(db.Integer, default=0)

    # VIP
    vip_level = db.Column(db.Integer, default=1)
    vip_exp = db.Column(db.Integer, default=0)
    vip_expire_time = db.Column(db.DateTime, nullable=True)
    vip_daily_claimed_raw = db.Column('vip_daily_claimed', db.Text, default='{}')

    # Story
    story_completed = db.Column(db.Boolean, default=False)

    # Designer
    is_designer = db.Column(db.Boolean, default=False)

    # Signature
    signature = db.Column(db.String(256), default='')

    @property
    def is_vip(self):
        from datetime import datetime
        if self.vip_expire_time and self.vip_expire_time > datetime.now():
            return True
        return False

    @property
    def shortcuts(self):
        data = self.get_shortcuts()
        class ShortcutProxy:
            _defaults = {'skill1': 'attack', 'skill2': 'attack',
                         'skill3': 'attack', 'skill4': 'attack'}
            def __init__(self, d):
                self._d = d
            def __getattr__(self, name):
                val = self._d.get(name)
                if val is not None:
                    return val
                return self._defaults.get(name)
            def __getitem__(self, name):
                val = self._d.get(name)
                if val is not None:
                    return val
                return self._defaults.get(name)
            def __contains__(self, name):
                return name in self._d
            def items(self):
                return self._d.items()
        return ShortcutProxy(data)

    @shortcuts.setter
    def shortcuts(self, value):
        if isinstance(value, dict):
            self.set_shortcuts(value)
        elif isinstance(value, str):
            self.shortcuts_raw = value

    @property
    def chat_history(self):
        try:
            return json.loads(self.chat_history_raw) if self.chat_history_raw else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    @chat_history.setter
    def chat_history(self, value):
        if isinstance(value, dict):
            self.set_chat_history(value)
        elif isinstance(value, str):
            self.chat_history_raw = value

    @property
    def notifications(self):
        try:
            return json.loads(self.notifications_raw) if self.notifications_raw else []
        except (json.JSONDecodeError, TypeError):
            return []

    @notifications.setter
    def notifications(self, value):
        if isinstance(value, list):
            self.set_notifications(value)
        elif isinstance(value, str):
            self.notifications_raw = value

    @property
    def visited_locations(self):
        try:
            return json.loads(self.visited_locations_raw) if self.visited_locations_raw else []
        except (json.JSONDecodeError, TypeError):
            return []

    @visited_locations.setter
    def visited_locations(self, value):
        self.visited_locations_raw = json.dumps(value, ensure_ascii=False)

    @property
    def item_usage(self):
        try:
            return json.loads(self.item_usage_raw) if self.item_usage_raw else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    @item_usage.setter
    def item_usage(self, value):
        self.item_usage_raw = json.dumps(value, ensure_ascii=False)

    @property
    def dungeon_clears(self):
        try:
            return json.loads(self.dungeon_clears_raw) if self.dungeon_clears_raw else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    @dungeon_clears.setter
    def dungeon_clears(self, value):
        self.dungeon_clears_raw = json.dumps(value, ensure_ascii=False)

    @property
    def boss_kills(self):
        try:
            return json.loads(self.boss_kills_raw) if self.boss_kills_raw else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    @boss_kills.setter
    def boss_kills(self, value):
        self.boss_kills_raw = json.dumps(value, ensure_ascii=False)

    @property
    def elite_kills_by_area(self):
        try:
            return json.loads(self.elite_kills_by_area_raw) if self.elite_kills_by_area_raw else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    @elite_kills_by_area.setter
    def elite_kills_by_area(self, value):
        self.elite_kills_by_area_raw = json.dumps(value, ensure_ascii=False)

    @property
    def monster_kills(self):
        try:
            return json.loads(self.monster_kills_raw) if self.monster_kills_raw else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    @monster_kills.setter
    def monster_kills(self, value):
        self.monster_kills_raw = json.dumps(value, ensure_ascii=False)

    @property
    def owned_titles(self):
        try:
            return json.loads(self.owned_titles_raw) if self.owned_titles_raw else []
        except (json.JSONDecodeError, TypeError):
            return []

    @owned_titles.setter
    def owned_titles(self, value):
        self.owned_titles_raw = json.dumps(value, ensure_ascii=False)

    @property
    def activity_data(self):
        try:
            return json.loads(self.activity_data_raw) if self.activity_data_raw else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    @activity_data.setter
    def activity_data(self, value):
        self.activity_data_raw = json.dumps(value, ensure_ascii=False)

    @property
    def finance_data(self):
        try:
            return json.loads(self.finance_data_raw) if self.finance_data_raw else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    @finance_data.setter
    def finance_data(self, value):
        self.finance_data_raw = json.dumps(value, ensure_ascii=False)

    @property
    def enemies(self):
        try:
            return json.loads(self.enemies_raw) if self.enemies_raw else []
        except (json.JSONDecodeError, TypeError):
            return []

    @enemies.setter
    def enemies(self, value):
        self.enemies_raw = json.dumps(value, ensure_ascii=False)

    def add_enemy(self, username):
        """Add a player to enemy list."""
        enemies = self.enemies
        if username not in enemies:
            enemies.append(username)
            self.enemies = enemies

    @property
    def friends(self):
        try:
            return json.loads(self.friends_raw) if self.friends_raw else []
        except (json.JSONDecodeError, TypeError):
            return []

    @friends.setter
    def friends(self, value):
        self.friends_raw = json.dumps(value, ensure_ascii=False)

    @property
    def blacklist(self):
        try:
            return json.loads(self.blacklist_raw) if self.blacklist_raw else []
        except (json.JSONDecodeError, TypeError):
            return []

    @blacklist.setter
    def blacklist(self, value):
        self.blacklist_raw = json.dumps(value, ensure_ascii=False)

    @property
    def relation_requests(self):
        try:
            return json.loads(self.relation_requests_raw) if self.relation_requests_raw else []
        except (json.JSONDecodeError, TypeError):
            return []

    @relation_requests.setter
    def relation_requests(self, value):
        self.relation_requests_raw = json.dumps(value, ensure_ascii=False)

    @property
    def vip_daily_claimed(self):
        try:
            return json.loads(self.vip_daily_claimed_raw) if self.vip_daily_claimed_raw else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    @vip_daily_claimed.setter
    def vip_daily_claimed(self, value):
        self.vip_daily_claimed_raw = json.dumps(value, ensure_ascii=False)

    def get_today_activity(self, key):
        """Get a daily activity value, auto-resets at midnight."""
        from services.activity_service import ActivityService
        return ActivityService.get_today_value(self, key)

    def set_today_activity(self, key, value):
        """Set a daily activity value."""
        from services.activity_service import ActivityService
        ActivityService.set_today_value(self, key, value)

    def get_title_display(self):
        """Return the full title string (prefix + suffix)."""
        from services.data_service import DataService
        prefix_name = ""
        suffix_name = ""
        if self.title_prefix_id:
            prefix = DataService.get_title(self.title_prefix_id, 'prefix')
            if prefix:
                prefix_name = prefix.get('name', '')
        if self.title_suffix_id:
            suffix = DataService.get_title(self.title_suffix_id, 'suffix')
            if suffix:
                suffix_name = suffix.get('name', '')
        return prefix_name + suffix_name if prefix_name or suffix_name else None

    version = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, default=datetime.utcnow)

    def get_passive_bonuses(self):
        """Calculate passive skill bonuses: rate bonuses for atk/def/hp/mp, flat for crit/dodge."""
        from services.data_service import DataService
        bonuses = {}
        for ps in PlayerSkill.query.filter_by(player_id=self.id).all():
            sdef = DataService.get_skill(ps.skill_id)
            if not sdef or sdef.get('skill_type') != 'passive':
                continue
            btype = sdef.get('bonus_type')
            bval = sdef.get('bonus_value_per_level', 0)
            level = ps.skill_level
            if btype in ('attack', 'defense', 'max_health', 'max_mana'):
                bonuses[btype] = bonuses.get(btype, 0) + bval * level
            elif btype in ('crit_rate', 'dodge_rate'):
                bonuses[btype] = bonuses.get(btype, 0) + bval * level
        return bonuses

    # Relationships
    equipment_instances = db.relationship('EquipmentInstance', backref='player', lazy='dynamic')
    inventory_items = db.relationship('InventoryItem', backref='player', lazy='dynamic')
    lieutenants = db.relationship('Lieutenant', backref='owner', lazy='dynamic')
    equipment_slots = db.relationship('EquipmentSlot', backref='player', lazy='dynamic',
                                      cascade='all, delete-orphan')
    skills = db.relationship('PlayerSkill', backref='player', lazy='dynamic',
                             cascade='all, delete-orphan')
    temp_effects = db.relationship('TempEffect', backref='player', lazy='dynamic',
                                   cascade='all, delete-orphan')
    lieutenants = db.relationship('Lieutenant', backref='owner', lazy='dynamic',
                                  cascade='all, delete-orphan')

    STAT_NAMES = {
        "max_health": "生命值",
        "max_mana": "魔法值",
        "attack": "攻击力",
        "defense": "防御力",
        "crit_rate": "暴击率",
        "dodge_rate": "闪避率"
    }

    CLASSES = {
        "术士": {
            "base_stats": {
                "max_health": 200, "max_mana": 200,
                "attack": 70, "defense": 150,
                "crit_rate": 0, "dodge_rate": 0
            },
            "level_up_stats": {
                "max_health": 80, "max_mana": 40,
                "attack": 6, "defense": 24,
                "crit_rate": 0.0006, "dodge_rate": 0.0006
            }
        },
        "战士": {
            "base_stats": {
                "max_health": 300, "max_mana": 100,
                "attack": 50, "defense": 200,
                "crit_rate": 0, "dodge_rate": 0
            },
            "level_up_stats": {
                "max_health": 120, "max_mana": 20,
                "attack": 4, "defense": 26,
                "crit_rate": 0.0008, "dodge_rate": 0.0008
            }
        },
        "刺客": {
            "base_stats": {
                "max_health": 250, "max_mana": 150,
                "attack": 60, "defense": 180,
                "crit_rate": 0, "dodge_rate": 0
            },
            "level_up_stats": {
                "max_health": 100, "max_mana": 30,
                "attack": 5, "defense": 25,
                "crit_rate": 0.0015, "dodge_rate": 0.0015
            }
        }
    }

    MILITARY_RANKS = {
        "士兵":     {"level": 1,  "honor": 0,     "attack": 0},
        "十夫长":   {"level": 5,  "honor": 100,   "attack": 5},
        "百夫长":   {"level": 10, "honor": 500,    "attack": 15},
        "校尉":     {"level": 15, "honor": 2000,   "attack": 30},
        "都尉":     {"level": 20, "honor": 5000,   "attack": 50},
        "裨将":     {"level": 25, "honor": 10000,  "attack": 80},
        "偏将":     {"level": 30, "honor": 20000,  "attack": 120},
        "中郎将":   {"level": 35, "honor": 40000,  "attack": 170},
        "车骑将军": {"level": 40, "honor": 70000,  "attack": 230},
        "骠骑将军": {"level": 45, "honor": 100000, "attack": 300},
        "大司马":   {"level": 50, "honor": 150000, "attack": 400},
        "大都督":   {"level": 55, "honor": 200000, "attack": 500},
    }

    # Flask-Login
    def get_id(self):
        return str(self.id)

    # Template compatibility properties
    @property
    def money(self):
        return self.gold

    @money.setter
    def money(self, value):
        self.gold = value

    @property
    def name(self):
        return self.nickname

    def get_avatar_path(self):
        from services.player_service import PlayerService
        return PlayerService.get_avatar_path(self)

    @property
    def effective_max_health(self):
        from services.player_service import PlayerService
        return PlayerService.get_max_health(self)

    @property
    def effective_max_mana(self):
        from services.player_service import PlayerService
        return PlayerService.get_max_mana(self)

    @property
    def effective_attack(self):
        from services.player_service import PlayerService
        return PlayerService.get_attack(self)

    @property
    def effective_defense(self):
        from services.player_service import PlayerService
        return PlayerService.get_defense(self)

    @property
    def effective_crit_rate(self):
        from services.title_service import TitleService
        from services.player_service import PlayerService
        passive = self.get_passive_bonuses()
        title_bonuses = TitleService.get_title_bonuses(self)
        lt_bonus = PlayerService._get_lt_passive_bonus(self, 'crit')
        equip_bonus = PlayerService._get_equipment_stat_sum(self, 'crit_rate')
        return self.crit_rate + passive.get('crit_rate', 0) + title_bonuses.get('crit_rate', 0) + lt_bonus + equip_bonus

    @property
    def effective_dodge_rate(self):
        from services.title_service import TitleService
        from services.player_service import PlayerService
        passive = self.get_passive_bonuses()
        title_bonuses = TitleService.get_title_bonuses(self)
        lt_bonus = PlayerService._get_lt_passive_bonus(self, 'dodge')
        equip_bonus = PlayerService._get_equipment_stat_sum(self, 'dodge_rate')
        return self.dodge_rate + passive.get('dodge_rate', 0) + title_bonuses.get('dodge_rate', 0) + lt_bonus + equip_bonus

    @property
    def inventory(self):
        from services.data_service import DataService as DS
        result = {}
        for inv in DS.get_inventory(self.id):
            item_data = DS.get_item(inv.item_id)
            if item_data:
                result[inv.item_id] = {"item": item_data, "quantity": inv.quantity}
            else:
                equip = EquipmentInstance.query.filter_by(
                    instance_id=inv.item_id, player_id=self.id).first()
                if equip:
                    result[f"equipment_{inv.item_id}"] = equip
                else:
                    result[inv.item_id] = {"quantity": inv.quantity}
        return result

    @property
    def inventory_dict(self):
        return self.inventory

    @property
    def equipment(self):
        from services.data_service import DataService as DS
        result = {}
        for slot_name, equip in DS.get_equipped(self.id).items():
            if equip:
                result[slot_name] = equip
        return result

    @property
    def equipment_dict(self):
        return {k: v.to_dict() if hasattr(v, 'to_dict') else v
                for k, v in self.equipment.items()}

    @property
    def temp_effects_list(self):
        effects = TempEffect.query.filter_by(player_id=self.id).all()
        return [
            {
                "stat": e.stat,
                "value": e.value,
                "rate": e.rate,
                "expire_time": e.expire_time,
                "item_id": e.item_id,
                "effect_name": e.effect_name,
            }
            for e in effects
        ]

    @property
    def skills_dict(self):
        player_skills = PlayerSkill.query.filter_by(player_id=self.id).all()
        result = {}
        for ps in player_skills:
            result[ps.skill_id] = {
                "level": ps.skill_level,
                "exp": ps.skill_exp
            }
        return result

    @property
    def learned_skills(self):
        return [ps.skill_id for ps in PlayerSkill.query.filter_by(player_id=self.id).all()]

    @property
    def temp_effects(self):
        from services.data_service import DataService
        DataService.clear_expired_effects(self.id)
        effects = TempEffect.query.filter_by(player_id=self.id).all()
        result = {}
        for e in effects:
            if e.stat not in result:
                result[e.stat] = []
            result[e.stat].append({
                "value": e.value,
                "rate": e.rate,
                "expire_time": e.expire_time,
                "item_id": e.item_id,
                "effect_name": e.effect_name,
            })
        return result

    def get_temp_effects_description(self, stat):
        now = time.time()
        descriptions = []
        for e in TempEffect.query.filter_by(player_id=self.id, stat=stat).all():
            remaining = max(0, e.expire_time - now)
            minutes = int(remaining // 60)
            seconds = int(remaining % 60)
            parts = []
            if e.value > 0:
                parts.append(f"+{int(e.value)}")
            if e.rate > 0:
                parts.append(f"+{e.rate*100:.1f}%")
            if parts:
                time_str = f"{minutes}分{seconds}秒" if minutes > 0 else f"{seconds}秒"
                descriptions.append(
                    f"{e.effect_name or stat}({'+'.join(parts)})剩余{time_str}")
        return descriptions

    @property
    def status_effect(self):
        """根据活跃临时效果生成状态摘要文本，如 '生↑ 攻↑'"""
        from services.data_service import DataService
        DataService.clear_expired_effects(self.id)
        now = time.time()
        effects = TempEffect.query.filter_by(player_id=self.id).all()
        if not effects:
            return None
        # 秘药缩写映射
        potion_short = {
            'max_health': '生', 'max_mana': '魔',
            'attack': '攻', 'defense': '防',
            'crit_rate': '暴', 'dodge_rate': '闪',
            'experience': '经', 'exp_rate': '经',
            'lt_exp_rate': '副经',
        }
        seen = {}
        for e in effects:
            if e.expire_time <= now:
                continue
            stat = e.stat
            short = potion_short.get(stat, stat[:2])
            if stat not in seen:
                seen[stat] = short
        parts = [f"{v}↑" for v in seen.values()]
        return ' '.join(parts) if parts else None

    def get_shortcuts(self):
        try:
            return json.loads(self.shortcuts_raw) if self.shortcuts_raw else {}
        except (json.JSONDecodeError, TypeError):
            return {'skill1': 'attack', 'skill2': 'attack',
                    'skill3': 'attack', 'skill4': 'attack',
                    'potion1': None, 'potion2': None}

    def set_shortcuts(self, data):
        self.shortcuts_raw = json.dumps(data, ensure_ascii=False)

    def get_chat_history(self):
        try:
            return json.loads(self.chat_history_raw) if self.chat_history_raw else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_chat_history(self, data):
        self.chat_history_raw = json.dumps(data, ensure_ascii=False)

    def get_notifications(self):
        try:
            return json.loads(self.notifications_raw) if self.notifications_raw else []
        except (json.JSONDecodeError, TypeError):
            return []

    def set_notifications(self, data):
        self.notifications_raw = json.dumps(data, ensure_ascii=False)

    def get_last_chat_message(self):
        try:
            return json.loads(self.last_chat_message) if self.last_chat_message else None
        except (json.JSONDecodeError, TypeError):
            return None

    def set_last_chat_message(self, data):
        self.last_chat_message = json.dumps(data, ensure_ascii=False) if data else None

    def get_current_encounter_data(self):
        try:
            return json.loads(self.current_encounter) if self.current_encounter else None
        except (json.JSONDecodeError, TypeError):
            return None

    def set_current_encounter_data(self, data):
        self.current_encounter = json.dumps(data, ensure_ascii=False) if data else None


class EquipmentInstance(db.Model):
    __tablename__ = 'equipment_instances'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    instance_id = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=True)
    template_id = db.Column(db.String(64), nullable=False)
    name = db.Column(db.String(128), nullable=False)
    slot = db.Column(db.String(20), nullable=False)
    rarity = db.Column(db.String(10), nullable=False)
    stars = db.Column(db.Integer, default=1)
    level_required = db.Column(db.Integer, default=1)
    class_required = db.Column(db.String(20), nullable=True)
    is_bound = db.Column(db.Boolean, default=False)
    base_stats = db.Column(db.Text, default='{}')
    extra_stats = db.Column(db.Text, default='{}')
    initial_stats = db.Column(db.Text, default='{}')
    enhance_level = db.Column(db.Integer, default=0)
    created_by = db.Column(db.String(64), nullable=True)   # 创建者昵称
    created_at = db.Column(db.DateTime, default=datetime.utcnow)  # 创建时间

    STAT_NAMES = {
        "max_health": "生命上限",
        "max_mana": "魔法上限",
        "attack": "攻击力",
        "defense": "防御力",
        "crit_rate": "暴击率",
        "dodge_rate": "闪避率"
    }

    SLOTS = ['weapon', 'helmet', 'armor', 'gloves', 'pants', 'shoes', 'accessory']
    SLOT_NAMES = {'weapon': '武器', 'helmet': '头盔', 'armor': '衣服',
                  'gloves': '手套', 'pants': '裤子', 'shoes': '鞋子', 'accessory': '饰品'}

    RARITIES = ["普通", "精良", "卓越", "史诗", "神器"]

    def get_base_stats(self):
        try:
            return json.loads(self.base_stats) if self.base_stats else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_base_stats(self, data):
        self.base_stats = json.dumps(data, ensure_ascii=False)

    def get_extra_stats(self):
        try:
            return json.loads(self.extra_stats) if self.extra_stats else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_extra_stats(self, data):
        self.extra_stats = json.dumps(data, ensure_ascii=False)

    def get_initial_stats(self):
        try:
            return json.loads(self.initial_stats) if self.initial_stats else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_initial_stats(self, data):
        self.initial_stats = json.dumps(data, ensure_ascii=False)

    def update_name(self):
        base = f"【{self.rarity}】{_get_template_name(self.template_id)}({self.stars}星)({self.level_required}级)"
        self.name = f"{base}+{self.enhance_level}" if self.enhance_level > 0 else base

    def get_enhance_success_rate(self, fail_bonus=0, luck_small=False, luck_medium=False):
        el = self.enhance_level
        if el < 1: base = 1.0
        elif el < 10: base = 0.95
        elif el < 18: base = 0.90
        elif el < 25: base = 0.80
        elif el < 30: base = 0.75
        elif el < 35: base = 0.60
        elif el < 40: base = 0.55
        elif el < 42: base = 0.50
        elif el < 45: base = 0.40
        elif el < 48: base = 0.35
        else: base = 0.30
        total = base + fail_bonus
        if luck_small:
            total += 0.05
        if luck_medium:
            total += 0.10
        return min(1.0, total)

    def get_sell_price(self):
        from services.data_service import DataService
        template = DataService.get_equipment_template(self.template_id)
        base_price = template.get('base_price', 1000) if template else 1000
        rarity_multipliers = {"普通": 0.2, "精良": 0.4, "卓越": 0.6, "史诗": 0.8, "神器": 1.0}
        return int(base_price * rarity_multipliers.get(self.rarity, 0.2) * (self.stars / 5))

    def to_dict(self):
        return {
            "instance_id": self.instance_id,
            "template_id": self.template_id,
            "name": self.name,
            "slot": self.slot,
            "rarity": self.rarity,
            "stars": self.stars,
            "level_required": self.level_required,
            "class_required": self.class_required,
            "is_bound": self.is_bound,
            "base_stats": self.get_base_stats(),
            "extra_stats": self.get_extra_stats(),
            "enhance_level": self.enhance_level,
            "initial_stats": self.get_initial_stats()
        }

    def get_display_stats(self):
        result = {}
        base = self.get_base_stats()
        extra = self.get_extra_stats()
        for stat, value in base.items():
            display_name = self.STAT_NAMES.get(stat, stat)
            if stat in ['crit_rate', 'dodge_rate']:
                result[display_name] = f"+{value * 100:.1f}%"
            else:
                result[display_name] = f"+{int(value)}"
        for stat, data in extra.items():
            display_name = self.STAT_NAMES.get(stat, stat)
            if isinstance(data, list):
                value = data[0]
            else:
                value = data
            if stat in ['crit_rate', 'dodge_rate']:
                existing = result.get(display_name, "")
                result[display_name] = f"{existing} +{value * 100:.1f}%"
            else:
                existing = result.get(display_name, "")
                result[display_name] = f"{existing} +{int(value)}"
        return result

    def get_total_stats(self):
        total = {}
        for stat, value in self.get_base_stats().items():
            total[stat] = total.get(stat, 0) + value
        for stat, data in self.get_extra_stats().items():
            value = data[0] if isinstance(data, list) else data
            total[stat] = total.get(stat, 0) + value
        return total


def _get_template_name(template_id):
    from services.data_service import DataService
    t = DataService.get_equipment_template(template_id)
    return t.get('name', template_id) if t else template_id


class InventoryItem(db.Model):
    __tablename__ = 'inventory_items'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False)
    item_id = db.Column(db.String(64), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    is_bound = db.Column(db.Boolean, default=False)

    __table_args__ = (db.UniqueConstraint('player_id', 'item_id', 'is_bound'),)


class WarehouseItem(db.Model):
    __tablename__ = 'warehouse_items'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False)
    item_id = db.Column(db.String(64), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    is_bound = db.Column(db.Boolean, default=False)

    __table_args__ = (db.UniqueConstraint('player_id', 'item_id', 'is_bound'),)


class EquipmentSlot(db.Model):
    __tablename__ = 'equipment_slots'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False)
    slot_name = db.Column(db.String(20), nullable=False)
    equipment_instance_id = db.Column(db.Integer, db.ForeignKey('equipment_instances.id'), nullable=True)

    equipment = db.relationship('EquipmentInstance', backref='slot_ref')

    __table_args__ = (db.UniqueConstraint('player_id', 'slot_name'),)


class LostItem(db.Model):
    __tablename__ = 'lost_items'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False)
    item_id = db.Column(db.String(64), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    is_bound = db.Column(db.Boolean, default=False)
    lost_at = db.Column(db.DateTime, nullable=False)
    # Stage: 'holding' (owner can redeem), 'auction' (open to all), 'claimed', 'expired'
    stage = db.Column(db.String(20), default='holding')
    # Current bid for auction stage
    current_bid = db.Column(db.Integer, default=0)
    current_bidder_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=True)
    # When the item was moved to auction
    auction_started_at = db.Column(db.DateTime, nullable=True)


class MarketListing(db.Model):
    """集市挂单：玩家将非绑物品/装备挂到集市售卖。

    物品与装备二选一：
    - 可堆叠物品：item_id 指向 items.json 的物品 id，quantity 可 >1（支持部分购买）；
    - 装备实例：equipment_instance_id 指向 EquipmentInstance.instance_id(UUID)，quantity 恒为 1。
    挂单期间装备实例归属置空(player_id=None)锁定，卖家无法穿戴/赠送/重复上架，
    买入/取消/过期时再转移归属（参考 lost_found grant_lost_item 模式）。
    """
    __tablename__ = 'market_listings'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    seller_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False)
    # 二选一：可堆叠物品用 item_id，装备用 equipment_instance_id，另一个为 NULL
    item_id = db.Column(db.String(64), nullable=True)
    equipment_instance_id = db.Column(db.String(36), nullable=True)
    # 反范式快照（列表页无需 join 装备表/重读 items.json）
    item_name = db.Column(db.String(128), nullable=False)
    item_type = db.Column(db.String(20), nullable=False)   # material/potion/consumable/equipment/chest/...
    category = db.Column(db.String(10), nullable=False)    # 材料/药品/消耗品/装备/宝箱/其他（tab UI）
    rarity = db.Column(db.String(10), nullable=True)       # 仅装备：普通/精良/卓越/史诗/神器
    quantity = db.Column(db.Integer, default=1)            # 剩余数量（可堆叠物品支持部分购买）；装备恒为 1
    unit_price = db.Column(db.Integer, nullable=False)
    is_bound = db.Column(db.Boolean, default=False)        # 恒 False（绑定物不可上架）
    status = db.Column(db.String(20), default='active')    # active/partial/sold/cancelled/expired
    ad_tier = db.Column(db.Integer, default=0)             # 0无/1基础(1000,全服通知)/2置顶(3000,通知+置顶3h)
    pin_until = db.Column(db.DateTime, nullable=True)      # ad_tier==2 时 = created_at+3h
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)    # created_at+7d
    sold_at = db.Column(db.DateTime, nullable=True)
    buyer_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=True)  # 最近买者（审计）

    __table_args__ = (
        db.Index('ix_market_status', 'status'),
        db.Index('ix_market_seller', 'seller_id'),
        db.Index('ix_market_category', 'category'),
        db.Index('ix_market_expires', 'expires_at'),
    )


class MarketTransaction(db.Model):
    """集市成交流水：每次购买成功落一笔（同时是买家的购买、卖家的出售）。

    与 MarketListing 不同，这里按「每笔成交」记录，能完整覆盖部分购买
    （status=partial 的挂单可能被多个买家分次买走，每笔都独立成记录）。
    """

    __tablename__ = 'market_transactions'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    listing_id = db.Column(db.Integer, db.ForeignKey('market_listings.id'), nullable=True)
    buyer_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False)
    seller_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False)
    # 反范式快照，列表/详情无需 join 装备表或重读 items.json
    item_name = db.Column(db.String(128), nullable=False)
    item_type = db.Column(db.String(20), nullable=False)
    category = db.Column(db.String(10), nullable=False)
    rarity = db.Column(db.String(10), nullable=True)        # 仅装备：普通/精良/卓越/史诗/神器
    quantity = db.Column(db.Integer, default=1)            # 本笔成交数量（可堆叠物品可 >1）
    unit_price = db.Column(db.Integer, nullable=False)
    total_price = db.Column(db.Integer, nullable=False)    # = unit_price * quantity
    buyer_fee = db.Column(db.Integer, default=0)           # 买家手续费
    seller_receive = db.Column(db.Integer, default=0)      # 卖家实收
    is_equipment = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.Index('ix_mt_buyer', 'buyer_id'),
        db.Index('ix_mt_seller', 'seller_id'),
        db.Index('ix_mt_created', 'created_at'),
    )


class PlayerSkill(db.Model):
    __tablename__ = 'player_skills'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False)
    skill_id = db.Column(db.String(64), nullable=False)
    skill_level = db.Column(db.Integer, default=1)
    skill_exp = db.Column(db.Integer, default=0)

    __table_args__ = (db.UniqueConstraint('player_id', 'skill_id'),)


class TempEffect(db.Model):
    __tablename__ = 'temp_effects'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False)
    stat = db.Column(db.String(20), nullable=False)
    value = db.Column(db.Float, default=0.0)
    rate = db.Column(db.Float, default=0.0)
    expire_time = db.Column(db.Float, default=0.0)
    item_id = db.Column(db.String(64), nullable=True)
    effect_name = db.Column(db.String(64), nullable=True)


class ChatMessage(db.Model):
    __tablename__ = 'chat_messages'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=True)
    receiver_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=True)
    content = db.Column(db.String(512), nullable=False)
    message_type = db.Column(db.String(10), default='system')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    sender = db.relationship('PlayerModel', foreign_keys=[sender_id])
    receiver = db.relationship('PlayerModel', foreign_keys=[receiver_id])


class PartyChat(db.Model):
    """队伍聊天消息（持久化，按 party_id 存储）。"""
    __tablename__ = 'party_chats'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    party_id = db.Column(db.Integer, nullable=False, index=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False)
    sender_name = db.Column(db.String(64), nullable=False)
    content = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    sender = db.relationship('PlayerModel')


class Achievement(db.Model):
    __tablename__ = 'achievements'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False)
    achievement_id = db.Column(db.String(64), nullable=False)
    claimed = db.Column(db.Boolean, default=False)
    completed_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('player_id', 'achievement_id'),)
