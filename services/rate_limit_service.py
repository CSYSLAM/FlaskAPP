"""请求票据与限流服务（仿天命三国 ck/tic/aid 凭证体系）。

URL 凭证：
- ``ck``（会话凭证）= 现有 ``sid``，标识窗口会话。
- ``tic``（请求票据）= 每次响应签发的时间戳票据，随页面内链接携带。
- ``aid``（动作标识）= 当前页面/动作。

限流规则：请求 tic < 上次接受的 tic 即限流（旧票据 = 复制旧URL / 后退到旧页）。
正常导航每次签发更大 tic，不受影响。同页多按钮共享同一 tic（工作台
测试/生成/查询、商城翻页、场景多怪物/NPC、背包多操作等），tic == last
时放行——否则同页点第二个按钮就会被误判「操作太频繁」。
同账号多标签页并发属于正常用法，不再用 tic 拦截；防机器人刷接口应靠
IP/账号级时间窗，不在此处。

不做纯时间窗限流：tic 旧票据检测已能精准识别复制旧URL，时间窗会误伤
正常快速操作（如搜索后立即购买）。单窗口快速连点带不同 tic，放行。
"""
import time


def _accepted_key(ck):
    return f'_accepted_tic_{ck}'


def issue_tic(ck):
    """为某 ck 签发一个新的时间戳票据。

    只返回新 tic 给 URL，**不写 session**（避免覆盖 _accepted_tic）。
    一次请求内多次 url_for 应共享同一 tic（由调用方用 g 缓存）。
    """
    return time.time()


def check_and_mark(ck, tic):
    """检查当前请求是否应限流。返回 (limited: bool)。

    限流条件：tic 非空且严格 < 上次接受的 tic（旧票据 / 复制旧 URL / 后退到旧页）。
    tic == last（同页多按钮共享 tic 的连点、刷新当前页）放行，不更新 last——
    避免工作台测试/商城翻页等同页多按钮被误判「操作太频繁」。
    tic > last 时记录为已接受。
    """
    from flask import session
    if not ck or tic is None:
        return False
    try:
        tic_f = float(tic)
    except (TypeError, ValueError):
        return False
    last = session.get(_accepted_key(ck))
    if last is not None and tic_f < float(last):
        return True  # 旧票据，不更新
    if last is None or tic_f > float(last):
        session[_accepted_key(ck)] = tic_f
    return False


def touch(ck):
    """豁免一次限流（限流页「返回」链接用）：记当前时间为已接受，放行后续。"""
    from flask import session
    if ck:
        session[_accepted_key(ck)] = time.time()


def clear(ck):
    """登出时清掉该 ck 的票据记录。"""
    from flask import session
    session.pop(_accepted_key(ck), None)
