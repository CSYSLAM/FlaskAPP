from services import db
from flask_login import UserMixin


QUALITY_NAMES = {0: '普通', 1: '平凡', 2: '平凡', 3: '聪颖', 4: '聪颖',
                 5: '优秀', 6: '优秀', 7: '优秀', 8: '卓越', 9: '卓越',
                 10: '卓越', 11: '卓越', 12: '完美', 13: '完美', 14: '完美',
                 15: '完美', 16: '完美', 17: '完美', 18: '完美', 19: '完美', 20: '完美'}

QUALITY_MULTIPLIER = {0: 0.5, 1: 0.6, 2: 0.7, 3: 0.8, 4: 0.9,
                      5: 1.0, 6: 1.1, 7: 1.2, 8: 1.3, 9: 1.4,
                      10: 1.5, 11: 1.6, 12: 1.8, 13: 2.0, 14: 2.2,
                      15: 2.4, 16: 2.6, 17: 2.8, 18: 3.0, 19: 3.2, 20: 3.5}

GENDER_NAMES = {'male': '男', 'female': '女'}
CLASS_NAMES = {'warrior': '战士', 'mage': '术士', 'assassin': '刺客'}
TIER_NAMES = {0: '普通', 1: '一级', 2: '二级', 3: '三级'}
TIER_FRAGMENTS = {1: 10, 2: 3, 3: 1}


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
        return QUALITY_MULTIPLIER.get(self.quality, 0.5)

    @property
    def enlightenment_mult(self):
        return 1.0 + self.enlightenment * 0.05

    def get_max_health(self):
        base = 200 + self.level * 50
        return int(base * self.quality_mult * self.enlightenment_mult * (1 + self.reinforce * 0.03))

    def get_max_mana(self):
        if self.class_type == 'mage':
            base = 150 + self.level * 40
        elif self.class_type == 'assassin':
            base = 80 + self.level * 25
        else:
            base = 60 + self.level * 20
        return int(base * self.quality_mult * self.enlightenment_mult * (1 + self.reinforce * 0.03))

    def get_attack(self):
        if self.class_type == 'warrior':
            base = 20 + self.level * 8
        elif self.class_type == 'assassin':
            base = 18 + self.level * 9
        else:
            base = 12 + self.level * 6
        return int(base * self.quality_mult * self.enlightenment_mult * (1 + self.reinforce * 0.03))

    def get_defense(self):
        if self.class_type == 'warrior':
            base = 15 + self.level * 6
        elif self.class_type == 'mage':
            base = 8 + self.level * 3
        else:
            base = 10 + self.level * 4
        return int(base * self.quality_mult * self.enlightenment_mult * (1 + self.reinforce * 0.03))

    def can_deploy(self):
        if self.loyalty < 30:
            return False, "忠诚度不足30，无法出战"
        if self.lifespan < 30:
            return False, "寿命不足30，无法出战"
        if not self.is_alive:
            return False, "副将已阵亡，需要复活"
        return True, ""

    def get_passive_bonus(self):
        bonus = {'attack': 0, 'defense': 0, 'health': 0, 'mana': 0, 'crit': 0, 'dodge': 0}
        for skill in self.skills:
            if skill.get('type') == 'passive' and skill.get('level', 0) > 0:
                bonus_type = skill.get('bonus_type', '')
                bonus_val = skill.get('bonus_value', 0) * skill.get('level', 1)
                if bonus_type == 'attack':
                    bonus['attack'] += bonus_val
                elif bonus_type == 'defense':
                    bonus['defense'] += bonus_val
                elif bonus_type == 'health':
                    bonus['health'] += bonus_val
                elif bonus_type == 'mana':
                    bonus['mana'] += bonus_val
                elif bonus_type == 'crit':
                    bonus['crit'] += bonus_val
                elif bonus_type == 'dodge':
                    bonus['dodge'] += bonus_val
        return bonus
