"""多窗口会话服务（Multi-Window Session）。

目的：在**单域名单端口 + 同一浏览器普通标签页**的部署形态下，
支持玩家同时多开多个不同账号（每个标签页一个账号），同时保证
同一账号不能在两个标签页同时在线（防数据竞争 / 防刷 bug）。

为什么需要：同一浏览器的普通标签页共享同一个 session cookie，
Flask-Login 默认基于 cookie 的单用户模型无法区分标签页。
本服务在服务端 session 里用 ``session['_wins'][sid] = {user_id, sso_token}``
按窗口标识 sid 存多账号；sid 通过 URL ``?sid=xxx`` 在所有链接间传递。

与单点登录([[auth_session_service]])的协作：
- 登录时调用 ``bind_window(sid, player_id)``：为该 (player_id, sid) 生成 sso token，
  并把该 player_id 的活动 sid 切到新 sid——旧 sid 的 token 立即失效。
- 每次请求按当前 sid 取窗口里的 token，用 ``is_active(player_id, sid, token)``
  检测；若失效说明该账号在别处（另一 sid）登录，仅踢掉当前 sid 窗口。

sid 的来源：优先 URL ``?sid=``，其次 cookie ``_cur_sid``（同浏览器共享，
仅用于"无 sid 的旧链接"兜底，不作为多开依据）。新窗口从登录页进入时
自动分配新 sid 并重定向带 sid，之后所有 url_for 自动带上。
"""
import secrets


def new_sid():
    """生成一个窗口标识（6 位，足够区分同浏览器的少量标签页）。"""
    return secrets.token_urlsafe(4)[:6]


def _wins():
    """返回 session 里的窗口字典 {sid: {user_id, sso_token}}。"""
    from flask import session
    wins = session.get('_wins')
    if not isinstance(wins, dict):
        wins = {}
        session['_wins'] = wins
    return wins


def get_sid():
    """当前请求的 sid：优先 URL ``?sid=``，其次 ``g.sid``（ensure_sid 从
    Referer 恢复的，用于 GET 表单提交丢 sid 的场景），无则 None。

    返回 None 表示这是一个"无 sid 的入口请求"（手输 URL / 书签），
    调用方（ensure_sid）应分配新 sid 并重定向。

    不从共享 cookie/session 兜底取 sid：同一浏览器多窗口共享 session，无法可靠区分
    "当前请求属于哪个窗口"，用兜底 sid 会导致 A 窗口误用 B 窗口身份造成数据串扰。
    站内链接由 url_defaults 保证都带 sid，正常操作不会丢窗口。
    """
    from flask import request, g
    sid = (request.args.get('sid') or '').strip()
    if sid:
        return sid
    # 回退到 g.sid（ensure_sid 从 Referer 恢复，或 _pull_sid 从路由变量取出）
    gsid = getattr(g, 'sid', None)
    return gsid or None


def get_current_window():
    """当前 sid 对应的窗口 dict，无则 None。"""
    sid = get_sid()
    if not sid:
        return None
    return _wins().get(sid)


def get_current_user_id():
    """当前 sid 窗口登录的 user_id，未登录则 None。"""
    win = get_current_window()
    return win.get('user_id') if win else None


def set_window(sid, user_id, sso_token):
    """绑定/覆盖一个窗口的登录态。"""
    _wins()[sid] = {'user_id': user_id, 'sso_token': sso_token}


def clear_window(sid):
    """登出时清掉指定窗口（不影响其他窗口）。"""
    wins = _wins()
    if sid in wins:
        wins.pop(sid, None)


def bind_window(sid, player_id):
    """登录成功时调用：为 (player_id, sid) 绑定 sso token，
    并把该账号的活动 sid 切到新 sid——旧 sid 立即失效。

    返回 sso_token。
    """
    from services import auth_session_service as _sso
    token = _sso.bind(player_id, sid)
    set_window(sid, player_id, token)
    return token


def is_window_active():
    """当前 sid 窗口是否仍是该账号的有效会话。

    首次过渡：窗口无 token（旧会话/重启残留）视为合法，不踢。
    """
    win = get_current_window()
    if not win:
        return True  # 未登录，无所谓
    token = win.get('sso_token')
    user_id = win.get('user_id')
    if user_id is None or token is None:
        return True  # 旧会话过渡
    from services import auth_session_service as _sso
    return _sso.is_active(user_id, sid=get_sid(), token=token)
