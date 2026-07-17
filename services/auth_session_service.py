"""单点登录会话服务（Single-Session per account）。

目的：同一账号同一时间只允许一个有效窗口（sid），新窗口登录会踢掉旧窗口，
旧窗口下次请求时被检测到失效 → 登出该窗口并跳回登录页提示「该账号在别处登录」。

为什么需要：PlayerModel 的 inventory/equipment/health 等是同一行上的 JSON blob，
多端同时在线会互相覆盖写，造成数据竞争与回档。

实现：用数据库表 ActiveSession 存储
{player_id: {active_sid, tokens:{sid:token}}}。
- ``bind(player_id, sid)``：为该 (player_id, sid) 生成新 token，并把 active_sid 切到 sid，
  旧 sid 的 token 立即失效（被 active_sid 判定排除）。
- ``is_active(player_id, sid, token)``：token 匹配且 sid == active_sid 才有效。
- 多 worker（gunicorn）下所有 worker 共享同一张表，状态一致。
- 首次过渡：旧会话无 token 视为合法，不踢；等下次主动登录才绑定。

线程安全靠 SQLite 自身的写锁；并发登录竞争由数据库层串行化。

与 [[window_session_service]] 协作：window_session 按窗口存 {user_id, sso_token}，
本服务按账号存活动 sid + 各 sid 的 token，二者配合实现"同账号唯一活动窗口"。
"""
import json
import secrets


def new_token():
    """生成一个会话 token。"""
    return secrets.token_urlsafe(32)


def _get_model():
    """延迟导入，避免循环依赖（model 需在 app 上下文里建表）。"""
    from models.active_session import ActiveSession
    return ActiveSession


def bind(player_id, sid):
    """登录成功时调用：为 (player_id, sid) 生成新 token 并设为该账号唯一活动 sid。

    返回 token。旧 sid 的 token 仍在表里但 active_sid 已切换，
    ``is_active`` 会判定旧 sid 失效，从而踢掉旧窗口。
    """
    from services import db
    ActiveSession = _get_model()
    token = new_token()
    row = ActiveSession.query.filter_by(player_id=player_id).first()
    if row:
        tokens = _parse_tokens(row.tokens)
        tokens[sid] = token
        row.tokens = _dump_tokens(tokens)
        row.active_sid = sid
        row.token = token  # 兼容字段：当前活动 token
    else:
        row = ActiveSession(
            player_id=player_id,
            token=token,
            active_sid=sid,
            tokens=_dump_tokens({sid: token}),
        )
        db.session.add(row)
    db.session.commit()
    return token


def is_active(player_id, sid, token):
    """当前 (player_id, sid, token) 是否仍是有效会话。

    有效条件：sid == active_sid 且 tokens[sid] == token。
    首次过渡：token 为 None（旧会话无 token）视为合法（不踢）。
    """
    if player_id is None:
        return True
    if token is None or sid is None:
        # 旧会话（本功能上线前已登录，或服务重启后残留 cookie）—— 不踢，
        # 等下次主动登录才绑定。避免上线/重启瞬间把所有人踢下线。
        return True
    ActiveSession = _get_model()
    row = ActiveSession.query.filter_by(player_id=player_id).first()
    if row is None:
        return False
    if row.active_sid != sid:
        return False  # 该账号活动窗口已是另一个 sid
    tokens = _parse_tokens(row.tokens)
    return tokens.get(sid) == token


def clear(player_id, sid=None):
    """登出时调用：清除该账号的活动会话。

    传 sid 时只清该 sid 的 token（多窗口下登出单个窗口）；
    不传 sid 时清整行（完全登出）。
    """
    if player_id is None:
        return
    from services import db
    ActiveSession = _get_model()
    row = ActiveSession.query.filter_by(player_id=player_id).first()
    if not row:
        return
    if sid:
        tokens = _parse_tokens(row.tokens)
        tokens.pop(sid, None)
        if row.active_sid == sid:
            # 活动窗口被登出：若有其他 sid 则切到任一个，否则删整行（完全登出）。
            # 不留 token=None 的空行——旧 DB 的 token 列可能是 NOT NULL 约束。
            if tokens:
                new_sid = next(iter(tokens))
                row.active_sid = new_sid
                row.token = tokens[new_sid]
                row.tokens = _dump_tokens(tokens)
                db.session.commit()
            else:
                db.session.delete(row)
                db.session.commit()
        else:
            row.tokens = _dump_tokens(tokens)
            db.session.commit()
    else:
        db.session.delete(row)
        db.session.commit()


def _parse_tokens(raw):
    if not raw:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return {}


def _dump_tokens(tokens):
    return json.dumps(tokens, ensure_ascii=False)
