from services import db
from datetime import datetime


class ActiveSession(db.Model):
    """单点登录会话表：每个 player_id 对应一个当前有效 token。

    新登录覆盖 token（踢掉旧窗口）；登出删除行。多 worker 共享此表。
    """
    __tablename__ = 'active_session'

    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), primary_key=True)
    token = db.Column(db.String(64), nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
