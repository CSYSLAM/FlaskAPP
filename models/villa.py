"""Mountain Villa (山庄) model."""
import json
import time
from services import db


class Villa(db.Model):
    __tablename__ = 'villa'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('players.id'), unique=True, nullable=False)
    name = db.Column(db.String(50), nullable=False, default='我的山庄')
    level = db.Column(db.Integer, nullable=False, default=1)
    experience = db.Column(db.Integer, nullable=False, default=0)

    # Action points reset daily
    action_points = db.Column(db.Integer, nullable=False, default=120)
    max_action_points = db.Column(db.Integer, nullable=False, default=120)

    # Defender lieutenant
    defender_id = db.Column(db.Integer, db.ForeignKey('lieutenant.id'), nullable=True)

    # Blessing count (祈福)
    blessing_count = db.Column(db.Integer, nullable=False, default=0)

    # Buildings data
    training_data_raw = db.Column('training_data', db.Text, default='{}')
    garden_data_raw = db.Column('garden_data', db.Text, default='{}')

    # Visitor logs
    visitor_logs_raw = db.Column('visitor_logs', db.Text, default='[]')

    # Daily reset tracking
    last_reset_date = db.Column(db.String(10), nullable=False, default='')

    @property
    def training_data(self):
        try:
            return json.loads(self.training_data_raw) if self.training_data_raw else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    @training_data.setter
    def training_data(self, value):
        self.training_data_raw = json.dumps(value, ensure_ascii=False)

    @property
    def garden_data(self):
        try:
            return json.loads(self.garden_data_raw) if self.garden_data_raw else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    @garden_data.setter
    def garden_data(self, value):
        self.garden_data_raw = json.dumps(value, ensure_ascii=False)

    @property
    def visitor_logs(self):
        try:
            return json.loads(self.visitor_logs_raw) if self.visitor_logs_raw else []
        except (json.JSONDecodeError, TypeError):
            return []

    @visitor_logs.setter
    def visitor_logs(self, value):
        self.visitor_logs_raw = json.dumps(value, ensure_ascii=False)

    def get_exp_to_next_level(self):
        """Experience needed for next level."""
        return 100 + self.level * 50

    def get_garden_slots(self):
        """Get number of garden slots based on level. Starts with 3, +1 every 5 levels."""
        return 3 + (self.level - 1) // 5

    def get_training_cost(self):
        """Get training cost based on level."""
        return self.level * 500 + 10000

    def get_training_exp(self, hours):
        """Get training experience based on hours and level."""
        base_exp = self.level * 500 + 1000
        return base_exp * hours

    def get_defense_power(self):
        """Get total defense power from defender lieutenant."""
        if not self.defender_id:
            return 0
        from models.lieutenant import Lieutenant
        lt = Lieutenant.query.get(self.defender_id)
        if not lt or not lt.is_alive:
            return 0
        return lt.get_attack() + lt.get_defense()

    def add_visitor_log(self, visitor_name, action, detail=''):
        """Add a visitor log entry."""
        logs = self.visitor_logs
        from datetime import datetime
        log_entry = {
            'time': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'visitor': visitor_name,
            'action': action,
            'detail': detail
        }
        logs.insert(0, log_entry)
        # Keep only last 20 logs
        self.visitor_logs = logs[:20]
