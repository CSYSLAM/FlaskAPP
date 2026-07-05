"""单点登录会话服务（Single-Session）。

目的：同一账号同一时间只允许一个有效会话，新登录会踢掉旧会话，
旧窗口下次请求时被检测到失效 → 登出并跳回登录页提示「该账号在别处登录」。

为什么需要：PlayerModel 的 inventory/equipment/health 等是同一行上的 JSON blob，
多端同时在线会互相覆盖写，造成数据竞争与回档。

实现：用数据库表 ActiveSession 存储 {player_id: token}。
- 多 worker（gunicorn）下所有 worker 共享同一张表，状态一致。
- 首次过渡：旧会话的 session 里没有 _sso_token（重启或本功能上线前已登录的玩家），
  视为合法，不踢；等该玩家下次主动登录时才绑定 token。

线程安全靠 SQLite 自身的写锁；并发登录竞争由数据库层串行化。
"""
import secrets


def new_token():
    """生成一个会话 token。"""
    return secrets.token_urlsafe(32)


def _get_model():
    """延迟导入，避免循环依赖（model 需在 app 上下文里建表）。"""
    from models.active_session import ActiveSession
    return ActiveSession


def bind(player_id):
    """登录成功时调用：生成新 token 并绑定为该玩家唯一有效 token。

    返回 token，调用方需将其存入 Flask session 以便后续比对。
    旧 token 自动失效（被覆盖）。
    """
    from services import db
    ActiveSession = _get_model()
    token = new_token()
    row = ActiveSession.query.filter_by(player_id=player_id).first()
    if row:
        row.token = token
    else:
        row = ActiveSession(player_id=player_id, token=token)
        db.session.add(row)
    db.session.commit()
    return token


def is_active(player_id, token):
    """当前 (player_id, token) 是否仍是有效会话。

    首次过渡：若 token 为 None（旧会话无 token），视为合法（不踢）。
    """
    if player_id is None:
        return True
    if token is None:
        # 旧会话（本功能上线前已登录，或服务重启后残留 cookie）—— 不踢，
        # 等下次主动登录才绑定。避免上线/重启瞬间把所有人踢下线。
        return True
    ActiveSession = _get_model()
    row = ActiveSession.query.filter_by(player_id=player_id).first()
    return row is not None and row.token == token


def clear(player_id):
    """登出时调用：清除该玩家的有效 token。"""
    if player_id is None:
        return
    from services import db
    ActiveSession = _get_model()
    row = ActiveSession.query.filter_by(player_id=player_id).first()
    if row:
        db.session.delete(row)
        db.session.commit()
