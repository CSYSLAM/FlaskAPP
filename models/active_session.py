from services import db
from datetime import datetime


class ActiveSession(db.Model):
    """单点登录会话表：每个 player_id 记录其当前活动窗口与各窗口 token。

    - ``active_sid``：该账号当前唯一活动窗口的 sid；新登录切换到此 sid，
      旧 sid 立即失效（被踢）。
    - ``tokens``：JSON，{sid: token}，记录该账号各窗口的 token。
    - ``token``：当前活动 token（兼容字段，便于人工排查）。

    新登录覆盖 active_sid（踢掉旧窗口）；登出删除行或清对应 sid。多 worker 共享此表。
    """
    __tablename__ = 'active_session'

    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), primary_key=True)
    token = db.Column(db.String(64), nullable=True)
    active_sid = db.Column(db.String(16), nullable=True)
    tokens = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
