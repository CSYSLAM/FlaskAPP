import math
from services import db
from flask_login import UserMixin


QUALITY_NAMES = {0: '普通', 1: '普通', 2: '普通', 3: '普通', 4: '普通',
                 5: '普通', 6: '普通', 7: '普通', 8: '普通', 9: '普通',
                 10: '优良', 11: '优良', 12: '优良', 13: '优良', 14: '优良',
                 15: '优良', 16: '优良',
                 17: '杰出', 18: '杰出', 19: '杰出',
                 20: '完美'}

# 品质倍率: 均匀线性 0→1.00, 20→1.10 (每点+0.005)
# 公式: 1.0 + quality * 0.005
def _quality_mult(quality):
    return 1.0 + quality * 0.005

GENDER_NAMES = {'male': '男', 'female': '女'}
CLASS_NAMES = {'warrior': '战士', 'mage': '术士', 'assassin': '刺客'}
TIER_NAMES = {0: '普通', 1: '一级', 2: '二级', 3: '三级', 4: '顶级', 5: '超凡'}
TIER_FRAGMENTS = {1: 10, 2: 3, 3: 1}

# 职业基础属性(无自定义 base 时用):生命/魔法/攻击/防御
CLASS_BASE_STATS = {
    'warrior':  {'max_health': 60, 'max_mana': 5,  'attack': 8,  'defense': 12},
    'assassin': {'max_health': 50, 'max_mana': 8,  'attack': 10, 'defense': 10},
    'mage':     {'max_health': 40, 'max_mana': 15, 'attack': 12, 'defense': 6},
}


class Lieutenant(db.Model):
    __tablename__ = 'lieutenant'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False)
    name = db.Column(db.String(50), nullable=False, default='副将')
    gender = db.Column(db.String(10), nullable=False, default='male')
    class_type = db.Column(db.String(20), nullable=False, default='warrior')
    quality = db.Column(db.Integer, nullable=False, default=0)
    enlightenment = db.Column(db.Integer, nullable=False, default=0)
    reinforce = db.Column(db.Integer, nullable=False, default=0)
    loyalty = db.Column(db.Integer, nullable=False, default=80)
    lifespan = db.Column(db.Integer, nullable=False, default=100)
    level = db.Column(db.Integer, nullable=False, default=1)
    experience = db.Column(db.Integer, nullable=False, default=0)
    position = db.Column(db.String(10), nullable=False, default='front')
    is_deployed = db.Column(db.Boolean, nullable=False, default=False)
    current_health = db.Column(db.Integer, nullable=False, default=0)
    current_mana = db.Column(db.Integer, nullable=False, default=0)
    skills_raw = db.Column(db.Text, nullable=False, default='[]')
    skill_slots = db.Column(db.Integer, nullable=False, default=3)
    tier = db.Column(db.Integer, nullable=False, default=3)
    is_alive = db.Column(db.Boolean, nullable=False, default=True)
    # 设计专用标记:工作台创建的副将=True,只在工作台设计区可见,不进玩家正式副将列表
    is_design_only = db.Column(db.Boolean, nullable=False, default=False)
    # 自定义基础属性(可空):设计者手动指定时优先于公式;None 则走 get_max_health 等公式
    base_max_health = db.Column(db.Integer, nullable=True, default=None)
    base_max_mana = db.Column(db.Integer, nullable=True, default=None)
    base_attack = db.Column(db.Integer, nullable=True, default=None)
    base_defense = db.Column(db.Integer, nullable=True, default=None)
    base_crit_rate = db.Column(db.Float, nullable=True, default=None)
    base_dodge_rate = db.Column(db.Float, nullable=True, default=None)

    @property
    def quality_name(self):
        return QUALITY_NAMES.get(self.quality, '普通')

    @property
    def gender_name(self):
        return GENDER_NAMES.get(self.gender, '男')

    @property
    def class_name(self):
        return CLASS_NAMES.get(self.class_type, '战士')

    @property
    def skills(self):
        import json
        if not self.skills_raw:
            return []
        return json.loads(self.skills_raw)

    @skills.setter
    def skills(self, value):
        import json
        self.skills_raw = json.dumps(value, ensure_ascii=False)

    @property
    def quality_mult(self):
        """品质倍率: 均匀线性 0→1.00, 20→1.10 (每点+0.005)。"""
        return _quality_mult(self.quality)

    @property
    def reinforce_mult(self):
        """强化加成: 0→1.00, 20→1.30 (每点+0.015)。"""
        return 1.0 + self.reinforce * 0.015

    @property
    def enlightenment_mult(self):
        """悟性倍率: 0→1.00, 10→1.20 (每点+0.02)。"""
        return 1.0 + self.enlightenment * 0.02

    def _stat_base(self, stat_key):
        """取某项基础属性:有自定义 base 用自定义,否则用职业基础表。"""
        base_field = 'base_' + stat_key
        custom = getattr(self, base_field, None)
        if custom is not None:
            return custom
        return CLASS_BASE_STATS.get(self.class_type, CLASS_BASE_STATS['warrior']).get(stat_key, 0)

    def get_max_health(self):
        # 公式: 基础属性 × 副将等级 × 悟性倍率 × 品质倍率 × 强化加成（向上取整）
        return math.ceil(self._stat_base('max_health') * self.level * self.enlightenment_mult * self.quality_mult * self.reinforce_mult)

    def get_max_mana(self):
        return math.ceil(self._stat_base('max_mana') * self.level * self.enlightenment_mult * self.quality_mult * self.reinforce_mult)

    def get_attack(self):
        return math.ceil(self._stat_base('attack') * self.level * self.enlightenment_mult * self.quality_mult * self.reinforce_mult)

    def get_defense(self):
        return math.ceil(self._stat_base('defense') * self.level * self.enlightenment_mult * self.quality_mult * self.reinforce_mult)

    # 暴击/闪避每级基础值(按职业，用于无自定义base的普通副将)
    # 公式与攻击/防御/生命一致: base * level * enlightenment_mult * quality_mult * reinforce_mult
    CLASS_BASE_CRIT = {'warrior': 0.00065, 'assassin': 0.00080, 'mage': 0.00050}
    CLASS_BASE_DODGE = {'warrior': 0.00050, 'assassin': 0.00065, 'mage': 0.00040}

    def get_crit_rate(self):
        """副将暴击率: base * level * 悟性 * 品质 * 强化; 无自定义走职业基础。"""
        if self.base_crit_rate is not None:
            base = self.base_crit_rate
        else:
            base = self.CLASS_BASE_CRIT.get(self.class_type, 0.00065)
        return base * self.level * self.enlightenment_mult * self.quality_mult * self.reinforce_mult

    def get_dodge_rate(self):
        """副将闪避率: base * level * 悟性 * 品质 * 强化; 无自定义走职业基础。"""
        if self.base_dodge_rate is not None:
            base = self.base_dodge_rate
        else:
            base = self.CLASS_BASE_DODGE.get(self.class_type, 0.00050)
        return base * self.level * self.enlightenment_mult * self.quality_mult * self.reinforce_mult

    def can_deploy(self):
        if self.loyalty < 30:
            return False, "忠诚度不足30，无法出战"
        if self.lifespan < 30:
            return False, "寿命不足30，无法出战"
        if not self.is_alive:
            return False, "副将已阵亡，需要复活"
        return True, ""

    def get_passive_bonus(self):
        """被动技能给主人的属性加成：副将对应属性 × bonus_value%。
        勇猛(暴击)/冷静(闪避)的bonus基于副将暴击率/闪避率，其他基于副将面板属性。
        bonus_value为数组时按等级取值(如[5,8,11]→1级5%,2级8%,3级11%)，为数字时直接使用(已按等级取好)。"""
        bonus = {'attack': 0, 'defense': 0, 'health': 0, 'mana': 0, 'crit': 0, 'dodge': 0}
        for skill in self.skills:
            if skill.get('type') == 'passive' and skill.get('level', 0) > 0:
                bonus_type = skill.get('bonus_type', '')
                bv = skill.get('bonus_value', 0)
                lv = skill.get('level', 1)
                # bonus_value为数组时按等级索引取值，为数字时直接使用(learn/upgrade已按等级取好)
                if isinstance(bv, list) and len(bv) >= lv:
                    bonus_pct = bv[lv - 1]
                elif isinstance(bv, (int, float)):
                    bonus_pct = bv
                else:
                    bonus_pct = 0
                if bonus_pct <= 0:
                    continue
                rate = bonus_pct / 100.0
                if bonus_type == 'attack':
                    bonus['attack'] += int(self.get_attack() * rate)
                elif bonus_type == 'defense':
                    bonus['defense'] += int(self.get_defense() * rate)
                elif bonus_type == 'health':
                    bonus['health'] += int(self.get_max_health() * rate)
                elif bonus_type == 'mana':
                    bonus['mana'] += int(self.get_max_mana() * rate)
                elif bonus_type == 'crit':
                    bonus['crit'] += self.get_crit_rate() * rate
                elif bonus_type == 'dodge':
                    bonus['dodge'] += self.get_dodge_rate() * rate
        return bonus
