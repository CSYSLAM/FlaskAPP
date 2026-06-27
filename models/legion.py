from services import db
from datetime import datetime
import json


class Legion(db.Model):
    __tablename__ = 'legions'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(32), unique=True, nullable=False)
    country = db.Column(db.String(10), nullable=False)
    level = db.Column(db.Integer, default=1)
    leader_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False)
    vice_leader_id = db.Column(db.Integer, nullable=True)
    declaration = db.Column(db.String(128), default='')
    total_contribution = db.Column(db.Integer, default=0)
    vip_aura_hp = db.Column(db.Integer, default=0)
    vip_aura_atk = db.Column(db.Integer, default=0)
    vip_aura_def = db.Column(db.Integer, default=0)
    vip_aura_date = db.Column(db.String(10), default='')
    battle_points = db.Column(db.Integer, default=0)
    occupied_cities_raw = db.Column(db.Text, default='[]')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    members = db.relationship('LegionMember', backref='legion', lazy='dynamic')
    applications = db.relationship('LegionApplication', backref='legion', lazy='dynamic')

    MAX_LEVEL = 20
    # Per level: attack +15, defense +150, health +150, mana +150
    SKILL_PER_LEVEL = {'attack': 15, 'defense': 150, 'max_health': 150, 'max_mana': 150}
    # Member slots by legion level
    LEVEL_SLOTS = {
        1: 50, 2: 55, 3: 60, 4: 65, 5: 70,
        6: 75, 7: 80, 8: 85, 9: 90, 10: 100,
        11: 110, 12: 120, 13: 130, 14: 140, 15: 150,
        16: 160, 17: 170, 18: 180, 19: 190, 20: 200,
    }
    # Upgrade cost per level (in total_contribution)
    UPGRADE_COST = {
        2: 5000, 3: 10000, 4: 15000, 5: 20000,
        6: 30000, 7: 40000, 8: 50000, 9: 60000, 10: 80000,
        11: 100000, 12: 120000, 13: 140000, 14: 160000, 15: 180000,
        16: 200000, 17: 220000, 18: 240000, 19: 260000, 20: 300000,
    }

    def get_max_slots(self):
        return self.LEVEL_SLOTS.get(self.level, 50)

    def get_skill_bonuses(self):
        """Return flat stat bonuses from legion skills for this legion's level."""
        bonuses = {}
        for stat, per_level in self.SKILL_PER_LEVEL.items():
            bonuses[stat] = per_level * self.level
        return bonuses

    def get_upgrade_cost(self):
        return self.UPGRADE_COST.get(self.level + 1, 999999)

    def can_upgrade(self):
        return self.level < self.MAX_LEVEL

    @property
    def occupied_cities(self):
        if self.occupied_cities_raw:
            try:
                return json.loads(self.occupied_cities_raw)
            except (json.JSONDecodeError, TypeError):
                return []
        return []

    @occupied_cities.setter
    def occupied_cities(self, value):
        self.occupied_cities_raw = json.dumps(value, ensure_ascii=False)


class LegionMember(db.Model):
    __tablename__ = 'legion_members'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    legion_id = db.Column(db.Integer, db.ForeignKey('legions.id'), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), unique=True, nullable=False)
    role = db.Column(db.String(20), default='member')  # leader, vice_leader, member
    contribution = db.Column(db.Integer, default=0)
    signed_today = db.Column(db.Boolean, default=False)
    sign_date = db.Column(db.String(10), default='')
    gold_donate_count = db.Column(db.Integer, default=0)
    gold_donate_date = db.Column(db.String(10), default='')
    quest_count = db.Column(db.Integer, default=0)
    quest_date = db.Column(db.String(10), default='')
    personal_battle_points = db.Column(db.Integer, default=0)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)

    player = db.relationship('PlayerModel', backref='legion_member_record')


class LegionApplication(db.Model):
    __tablename__ = 'legion_applications'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    legion_id = db.Column(db.Integer, db.ForeignKey('legions.id'), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False)
    player_level = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    player = db.relationship('PlayerModel', backref='legion_applications')


class LegionChat(db.Model):
    __tablename__ = 'legion_chats'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    legion_id = db.Column(db.Integer, db.ForeignKey('legions.id'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False)
    sender_name = db.Column(db.String(64), nullable=False)
    content = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    sender = db.relationship('PlayerModel')
