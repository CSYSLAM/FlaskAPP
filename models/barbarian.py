"""蛮夷入侵（南蛮 / 北夷）活动数据模型。

- BarbarianInvasion: 每方（南/北）一行，记录各国士卒剩余数量、上次刷新/清零时间戳与常驻开关。
- BarbarianLeader: 每方三名首领（老三/老二/老大）的状态，供活动页展示与击杀后复苏。
"""
from services import db


class BarbarianInvasion(db.Model):
    __tablename__ = 'barbarian_invasion'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    # 南 / 北
    side = db.Column(db.String(4), unique=True, nullable=False)
    # 各国士卒剩余数量（活动界面仅显示本国数量）
    wei_soldiers = db.Column(db.Integer, default=0)
    shu_soldiers = db.Column(db.Integer, default=0)
    wu_soldiers = db.Column(db.Integer, default=0)
    # 上次士卒刷新（12:00/18:00 置 300）的时间戳；用于幂等的时间跃迁
    last_soldier_tick = db.Column(db.DateTime, nullable=True)
    # 上次首领刷新（13:00/19:00 置 alive）的时间戳
    last_leader_tick = db.Column(db.DateTime, nullable=True)
    # 常驻开关：True=始终可玩（默认），False=按真实时钟窗口启停
    active = db.Column(db.Boolean, default=True)

    COUNTRIES = ('魏', '蜀', '吴')

    def soldier_count(self, country):
        return {
            '魏': self.wei_soldiers or 0,
            '蜀': self.shu_soldiers or 0,
            '吴': self.wu_soldiers or 0,
        }.get(country, 0)

    def set_soldier(self, country, value):
        value = max(0, int(value))
        if country == '魏':
            self.wei_soldiers = value
        elif country == '蜀':
            self.shu_soldiers = value
        elif country == '吴':
            self.wu_soldiers = value


class BarbarianLeader(db.Model):
    __tablename__ = 'barbarian_leaders'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    side = db.Column(db.String(4), nullable=False)          # 南 / 北
    key = db.Column(db.String(20), nullable=False)          # laosan/laoer/laoda
    name = db.Column(db.String(40), nullable=False)
    level = db.Column(db.Integer, default=10)
    tier = db.Column(db.String(10), default='basic')        # basic/mid/high
    monster_id = db.Column(db.String(60), nullable=False)   # monsters.json 中的怪物 id
    status = db.Column(db.String(20), default='alive')      # alive / recovering
    killed_at = db.Column(db.DateTime, nullable=True)
    # 当前刷新落点（单实例）；空表示未刷新/复苏中
    location_id = db.Column(db.String(80), nullable=True)

    __table_args__ = (
        db.Index('ix_barbarian_leaders_side_key', 'side', 'key'),
    )
