# # 1. 丢弃 app.py 和 game_data.db 的本地修改，恢复成远程版本
# git checkout -- app.py instance/game_data.db

# # 2. 删除本地多余的 flask_app.py（因为远程也有这个文件，会冲突）
# rm flask_app.py

# # 3. 重新拉取远程代码
# git pull

import os
import traceback
from pathlib import Path
from flask import Flask, send_from_directory
from flask_login import LoginManager
from services import db
from services.data_service import DataService
from models.player import PlayerModel


login_manager = LoginManager()


def create_app():
    app = Flask(__name__)
    app.config['TEMPLATES_AUTO_RELOAD'] = True

    config_name = os.environ.get('FLASK_ENV', 'development')
    if config_name == 'development':
        app.config.from_object('config.Config')
    else:
        app.config.from_object(config_name)

    instance_config = Path(app.instance_path) / 'config.py'
    if instance_config.exists():
        app.config.from_pyfile(instance_config)

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login_page'
    login_manager.login_message = None

    @login_manager.user_loader
    def load_user(user_id):
        return PlayerModel.query.get(int(user_id))

    DataService.init_app(app)

    # ── 多窗口 sid 贯穿机制（Flask 官方 url_defaults/url_value_preprocessor）──
    # 让所有 url_for（模板 468 处 redirect + 167 个模板）自动带上当前 sid，
    # 无需改动任何蓝图或模板。同一浏览器普通标签页靠 URL ?sid= 区分窗口。
    SID_SKIP_ENDPOINTS = {'static'}

    @app.url_value_preprocessor
    def _pull_sid(endpoint, values):
        """从 URL 路由变量取出 sid(ck) 挂到 g。tic 是 query 参数，不在此取。"""
        from flask import g
        if values and 'sid' in values:
            g.sid = values.pop('sid')

    @app.url_defaults
    def _inject_sid(endpoint, values):
        """给所有 url_for 自动注入 sid(ck)/tic/aid（静态资源跳过）。

        - sid: 窗口会话凭证
        - tic: 当前页面签发的请求票据，用于检测复制URL多窗口并发
        - aid: 当前动作/页面标识，用于限流后「点返回」回原页
        即使 values 为空（如 url_for('game.scene') 无参）也要注入。
        """
        if values is None:
            values = {}
        if 'sid' in values:
            return
        if endpoint in SID_SKIP_ENDPOINTS or (endpoint or '').startswith('static'):
            return
        from flask import g, request
        sid = getattr(g, 'sid', None) or (request.args.get('sid') if request else None)
        if sid:
            values['sid'] = sid
            # tic: 本请求签发的票据，渲染时所有链接共享
            tic = getattr(g, 'resp_tic', None)
            if tic is None:
                from services import rate_limit_service as _rl
                tic = _rl.issue_tic(sid)
                g.resp_tic = tic
            values['tic'] = tic
            # aid: 动作标识（endpoint 简名）
            if 'aid' not in values:
                values['aid'] = (endpoint or '').split('.')[-1]

    @app.before_request
    def ensure_sid():
        """无 sid 的 GET 请求尝试从 Referer 恢复 sid，否则分配新 sid。

        带 sid 的请求（绝大多数，由 url_defaults 保证链接带 sid）直接放行。
        无 sid 的 GET 请求来源：
        - GET 表单提交（搜索/过滤）：浏览器丢弃 action URL 的 query 参数，
          只发表单字段，sid 丢失。此时 Referer 是原页面（带 sid 且有登录态），
          从 Referer 恢复 sid 即可复用原窗口登录态。
        - 开新标签页/书签：无 Referer，分配新 sid（新窗口）。
        """
        from flask import request, redirect, g
        from services import window_session_service as _ws
        if request.endpoint == 'static':
            return
        sid = _ws.get_sid()
        if sid:
            g.sid = sid
            return
        # 无 sid：GET 请求先尝试从 Referer 恢复（GET 表单提交丢 sid 的场景）
        if request.method == 'GET':
            ref = request.referrer or ''
            if ref:
                from urllib.parse import urlparse, parse_qs
                ref_sid = parse_qs(urlparse(ref).query).get('sid', [None])[0]
                if ref_sid:
                    g.sid = ref_sid
                    return
            # 无 Referer 或 Referer 无 sid：分配新 sid（开新标签页/书签）
            new = _ws.new_sid()
            args = dict(request.args)
            args['sid'] = new
            query = '&'.join(f'{k}={v}' for k, v in args.items())
            return redirect(request.path + ('?' + query if query else ''), code=302)
        g.sid = None

    @app.before_request
    def setup_window_auth():
        """多窗口认证：按当前 sid 注入 current_user，并检测同账号互踢。

        同一浏览器普通标签页共享 cookie，Flask-Login 默认单用户模型无法区分。
        这里在请求开始时按 URL ``?sid=`` 从服务端多窗口 session 取出该窗口登录的
        user_id，手动设置 ``g._login_user``（Flask-Login 0.6.3 的 current_user 注入点），
        绕过单 cookie 限制。同时检测该窗口的 sso token 是否仍有效——同账号在另一
        sid 登录会使本 sid 失效，此处仅清掉当前 sid 窗口并踢回登录页。
        """
        from flask import session as _sess, g, redirect, url_for, flash, request
        from services import window_session_service as _ws
        # 静态资源不处理
        if request.endpoint == 'static':
            return
        uid = _ws.get_current_user_id()
        if uid is not None:
            user = PlayerModel.query.get(int(uid))
            if user is not None:
                g._login_user = user
                # 单点登录检测：当前窗口 token 失效 → 该账号在别处登录
                if not _ws.is_window_active():
                    sid = _ws.get_sid()
                    if sid:
                        _ws.clear_window(sid)
                    # 注意：只清当前 sid 窗口，不能 _sess.clear()——
                    # 同浏览器其他窗口的 _wins 也在这份共享 session 里
                    _sess.pop("username", None)
                    _sess.pop("player_id", None)
                    flash("该账号在别处登录，您已下线")
                    return redirect(url_for("auth.login_page", kicked=1))
                return
        # 当前窗口未登录：显式设匿名用户，阻止 Flask-Login 用共享 cookie 里的
        # session["_user_id"]（其他窗口写的）误判为已登录
        from flask_login import AnonymousUserMixin
        g._login_user = AnonymousUserMixin()

    @app.before_request
    def track_online():
        from flask import g
        from flask_login import current_user
        from services.party_service import mark_online
        # current_user 已由 setup_window_auth 注入到 g._login_user
        if current_user.is_authenticated:
            mark_online(current_user.id)

    @app.before_request
    def rate_limit():
        """请求频率限制（仿天命三国「手机太猛了」）。

        同一 sid 短时间内并发请求（复制 URL 到新窗口同时操作）→ 限流提示页。
        已认证的非静态请求才检查；限流提示页本身的请求不再限流。
        """
        from flask import g, request, render_template, url_for
        from flask_login import current_user
        from services import window_session_service as _ws
        from services import rate_limit_service as _rl
        if request.endpoint == 'static' or request.endpoint == 'auth.login_page':
            return
        if not getattr(g, '_login_user', None) or not current_user.is_authenticated:
            return
        sid = _ws.get_sid()
        if not sid:
            return
        # 带 rl=1 的请求是限流提示页「返回」链接，豁免一次（避免死循环）
        if request.args.get('rl') == '1':
            _rl.touch(sid)
            return
        # tic 从 query string 取（url_value_preprocessor 只能拿路由变量，拿不到 query）
        tic = request.args.get('tic')
        if _rl.check_and_mark(sid, tic):
            # 限流提示页：返回链接回场景页（最安全，不会 405）。
            # 给返回链接加 rl=1 豁免，避免旧 tic 再次触发限流死循环。
            # 不用 request.referrer 作返回链接，因为：
            # 1. referrer 可能是 POST-only URL（如 /crafting/forge/xxx），GET 访问会 405/500
            # 2. referrer 带旧 tic，即使加 rl=1 豁免，后续导航仍可能因旧 tic 再次限流
            back = url_for('game.scene', sid=sid)
            sep = '&' if '?' in back else '?'
            back = back + sep + 'rl=1'
            return render_template('rate_limit.html', back_url=back), 429

    from services.world_boss_service import WorldBossService
    WorldBossService.init_bosses()

    # Inject bandit monsters into monsters cache for finance (理财·股市) feature
    from services.finance_service import FinanceService
    FinanceService.register_bandit_monster(DataService.get_monsters())

    from blueprints.auth import auth_bp
    from blueprints.game import game_bp
    from blueprints.player import player_bp
    from blueprints.battle import battle_bp
    from blueprints.shop import shop_bp
    from blueprints.social import social_bp
    from blueprints.activity import activity_bp
    from blueprints.lieutenant import lieutenant_bp
    from blueprints.lieutenant_commander import commander_bp
    from blueprints.villa import villa_bp
    from blueprints.vip import vip_bp
    from blueprints.rank import rank_bp
    from blueprints.guide import guide_bp
    from blueprints.map_route import map_bp
    from blueprints.dungeon import dungeon_bp
    from blueprints.workbench import workbench_bp
    from blueprints.medicine_shop import medicine_bp
    from blueprints.warehouse import warehouse_bp
    from blueprints.lost_found import lost_found_bp
    from blueprints.legion import legion_bp
    from blueprints.battlefield import battlefield_bp
    from blueprints.party import party_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(game_bp, url_prefix='/game')
    app.register_blueprint(player_bp, url_prefix='/player')
    app.register_blueprint(battle_bp, url_prefix='/battle')
    app.register_blueprint(shop_bp, url_prefix='/shop')
    app.register_blueprint(social_bp, url_prefix='/social')
    app.register_blueprint(activity_bp)
    app.register_blueprint(lieutenant_bp)
    app.register_blueprint(commander_bp)
    app.register_blueprint(villa_bp)
    app.register_blueprint(vip_bp)
    app.register_blueprint(rank_bp)
    app.register_blueprint(guide_bp)
    app.register_blueprint(map_bp)
    app.register_blueprint(dungeon_bp, url_prefix='/dungeon')
    app.register_blueprint(workbench_bp, url_prefix='/workbench')
    app.register_blueprint(medicine_bp, url_prefix='/medicine')
    app.register_blueprint(warehouse_bp, url_prefix='/warehouse')
    app.register_blueprint(lost_found_bp, url_prefix='/lost_found')
    app.register_blueprint(legion_bp, url_prefix='/legion')
    app.register_blueprint(battlefield_bp, url_prefix='/battlefield')
    app.register_blueprint(party_bp, url_prefix='/party')

    from blueprints.crafting import crafting_bp
    from blueprints.quest import quest_bp
    app.register_blueprint(crafting_bp, url_prefix='/crafting')
    app.register_blueprint(quest_bp, url_prefix='/quest')

    @app.route('/ref/<path:filename>')
    def ref_file(filename):
        ref_dir = Path(app.root_path) / 'ref'
        return send_from_directory(ref_dir, filename)

    @app.route('/')
    def index():
        from flask import redirect, url_for
        return redirect(url_for('game.scene'))

    with app.app_context():
        # 确保 ActiveSession 表被注册后再 create_all（单点登录会话表）
        from models.active_session import ActiveSession  # noqa: F401
        db.create_all()
        # 多窗口 SSO：为旧版 active_session 表补齐 active_sid / tokens 列
        # （旧表只有 player_id/token/updated_at，create_all 不会改已存在的表）
        try:
            db.session.execute(db.text("ALTER TABLE active_session ADD COLUMN active_sid VARCHAR(16)"))
            db.session.commit()
        except Exception:
            db.session.rollback()
        try:
            db.session.execute(db.text("ALTER TABLE active_session ADD COLUMN tokens TEXT"))
            db.session.commit()
        except Exception:
            db.session.rollback()
        # 为已有数据库添加新列（SQLite 不支持 ALTER TABLE ADD COLUMN IF NOT EXISTS）
        try:
            db.session.execute(db.text("ALTER TABLE players ADD COLUMN player_uid VARCHAR(10)"))
            db.session.commit()
        except Exception:
            db.session.rollback()
        try:
            db.session.execute(db.text("ALTER TABLE players ADD COLUMN is_designer BOOLEAN DEFAULT 0"))
            db.session.commit()
        except Exception:
            db.session.rollback()
        # 战斗界面生命/魔法净变化括号显示(带符号)
        for _col_def in (
            "ALTER TABLE players ADD COLUMN last_hp_delta INTEGER DEFAULT 0",
            "ALTER TABLE players ADD COLUMN last_mp_delta INTEGER DEFAULT 0",
        ):
            try:
                db.session.execute(db.text(_col_def))
                db.session.commit()
            except Exception:
                db.session.rollback()
        try:
            db.session.execute(db.text("ALTER TABLE players ADD COLUMN warehouse_gold INTEGER DEFAULT 0"))
            db.session.commit()
        except Exception:
            db.session.rollback()
        try:
            db.session.execute(db.text("ALTER TABLE players ADD COLUMN backpack_capacity INTEGER DEFAULT 20"))
            db.session.commit()
        except Exception:
            db.session.rollback()
        try:
            db.session.execute(db.text("ALTER TABLE players ADD COLUMN warehouse_capacity INTEGER DEFAULT 20"))
            db.session.commit()
        except Exception:
            db.session.rollback()
        try:
            db.session.execute(db.text("ALTER TABLE lieutenant ADD COLUMN tier INTEGER DEFAULT 3"))
            db.session.commit()
        except Exception:
            db.session.rollback()
        # 副将自定义基础属性(工作台副将设计模块):可空,未设则走 get_xxx 公式
        for _col_def in (
            "ALTER TABLE lieutenant ADD COLUMN base_max_health INTEGER",
            "ALTER TABLE lieutenant ADD COLUMN base_max_mana INTEGER",
            "ALTER TABLE lieutenant ADD COLUMN base_attack INTEGER",
            "ALTER TABLE lieutenant ADD COLUMN base_defense INTEGER",
            "ALTER TABLE lieutenant ADD COLUMN base_crit_rate FLOAT",
            "ALTER TABLE lieutenant ADD COLUMN base_dodge_rate FLOAT",
        ):
            try:
                db.session.execute(db.text(_col_def))
                db.session.commit()
            except Exception:
                db.session.rollback()
        # 副将设计专用标记:工作台创建的副将只在设计区可见,不进玩家正式列表
        try:
            db.session.execute(db.text("ALTER TABLE lieutenant ADD COLUMN is_design_only BOOLEAN DEFAULT 0"))
            db.session.commit()
        except Exception:
            db.session.rollback()
        try:
            db.session.execute(db.text("ALTER TABLE legions ADD COLUMN battle_points INTEGER DEFAULT 0"))
            db.session.commit()
        except Exception:
            db.session.rollback()
        try:
            db.session.execute(db.text("ALTER TABLE legion_members ADD COLUMN quest_count INTEGER DEFAULT 0"))
            db.session.commit()
        except Exception:
            db.session.rollback()
        try:
            db.session.execute(db.text("ALTER TABLE legion_members ADD COLUMN quest_date VARCHAR(10) DEFAULT ''"))
            db.session.commit()
        except Exception:
            db.session.rollback()
        try:
            db.session.execute(db.text("ALTER TABLE legion_members ADD COLUMN personal_battle_points INTEGER DEFAULT 0"))
            db.session.commit()
        except Exception:
            db.session.rollback()
        try:
            db.session.execute(db.text("ALTER TABLE players ADD COLUMN in_battlefield BOOLEAN DEFAULT 0"))
            db.session.commit()
        except Exception:
            db.session.rollback()
        try:
            db.session.execute(db.text("ALTER TABLE players ADD COLUMN battlefield_city VARCHAR(32)"))
            db.session.commit()
        except Exception:
            db.session.rollback()
        try:
            db.session.execute(db.text("ALTER TABLE players ADD COLUMN battlefield_death_time FLOAT DEFAULT 0.0"))
            db.session.commit()
        except Exception:
            db.session.rollback()
        try:
            db.session.execute(db.text("ALTER TABLE legions ADD COLUMN occupied_cities_raw TEXT DEFAULT '[]'"))
            db.session.commit()
        except Exception:
            db.session.rollback()
        try:
            db.session.execute(db.text("ALTER TABLE players ADD COLUMN party_id INTEGER"))
            db.session.commit()
        except Exception:
            db.session.rollback()
        try:
            db.session.execute(db.text("ALTER TABLE players ADD COLUMN item_usage_raw TEXT DEFAULT '{}'"))
            db.session.commit()
        except Exception:
            db.session.rollback()
        try:
            db.session.execute(db.text("ALTER TABLE players ADD COLUMN dungeon_clears_raw TEXT DEFAULT '{}'"))
            db.session.commit()
        except Exception:
            db.session.rollback()
        try:
            db.session.execute(db.text("ALTER TABLE players ADD COLUMN tower_max_floor INTEGER DEFAULT 0"))
            db.session.commit()
        except Exception:
            db.session.rollback()
        try:
            db.session.execute(db.text("ALTER TABLE players ADD COLUMN boss_kills_raw TEXT DEFAULT '{}'"))
            db.session.commit()
        except Exception:
            db.session.rollback()
        try:
            db.session.execute(db.text("ALTER TABLE players ADD COLUMN pk_loss_count INTEGER DEFAULT 0"))
            db.session.commit()
        except Exception:
            db.session.rollback()
        try:
            db.session.execute(db.text("ALTER TABLE players ADD COLUMN finance_data TEXT DEFAULT '{}'"))
            db.session.commit()
        except Exception:
            db.session.rollback()
        try:
            db.session.execute(db.text("ALTER TABLE players ADD COLUMN elite_kills_by_area_raw TEXT DEFAULT '{}'"))
            db.session.commit()
        except Exception:
            db.session.rollback()
        try:
            db.session.execute(db.text("ALTER TABLE players ADD COLUMN monster_kills_raw TEXT DEFAULT '{}'"))
            db.session.commit()
        except Exception:
            db.session.rollback()
        try:
            db.session.execute(db.text("ALTER TABLE players ADD COLUMN divine_beast_kills INTEGER DEFAULT 0"))
            db.session.commit()
        except Exception:
            db.session.rollback()
        try:
            db.session.execute(db.text("ALTER TABLE players ADD COLUMN forge_count INTEGER DEFAULT 0"))
            db.session.commit()
        except Exception:
            db.session.rollback()
        try:
            db.session.execute(db.text("ALTER TABLE players ADD COLUMN enhance_success_count INTEGER DEFAULT 0"))
            db.session.commit()
        except Exception:
            db.session.rollback()
        try:
            db.session.execute(db.text("ALTER TABLE players ADD COLUMN enhance_fail_count INTEGER DEFAULT 0"))
            db.session.commit()
        except Exception:
            db.session.rollback()
        try:
            db.session.execute(db.text("ALTER TABLE players ADD COLUMN enhance_50_count INTEGER DEFAULT 0"))
            db.session.commit()
        except Exception:
            db.session.rollback()
        # 为没有 player_uid 的旧玩家生成 UID
        import random
        import string
        from models.player import PlayerModel
        players_without_uid = PlayerModel.query.filter(
            PlayerModel.player_uid == None).all()
        for p in players_without_uid:
            while True:
                uid = ''.join(random.choices(string.digits + string.ascii_lowercase, k=10))
                if not PlayerModel.query.filter_by(player_uid=uid).first():
                    break
            p.player_uid = uid
        if players_without_uid:
            db.session.commit()

    # 服务端的 500 错误兜底:把完整 traceback 落盘,便于生产环境排查
    # (gunicorn 的 --error-logfile - 在手机控制台部署下会被丢弃,导致 500 无迹可寻)。
    import traceback as _tb
    import threading as _threading
    import time as _time
    _err_lock = _threading.Lock()

    @app.errorhandler(Exception)
    def _log_server_error(e):
        try:
            from pathlib import Path as _Path
            import sys as _sys
            _log_dir = app.instance_path
            _Path(_log_dir).mkdir(parents=True, exist_ok=True)
            _trace = "".join(_tb.format_exception(type(e), e, e.__traceback__))
            _stamp = _time.strftime("%Y-%m-%d %H:%M:%S")
            _line = f"\n===== 500 @ {_stamp} =====\n{_trace}\n"
            with _err_lock:
                with open(_Path(_log_dir) / "flask_error.log", "a", encoding="utf-8") as _f:
                    _f.write(_line)
        except Exception:
            pass
        # 返回简洁的生产错误页(不泄露细节)
        from flask import make_response
        return make_response(
            "<h1>Internal Server Error</h1><p>The server encountered an internal "
            "error and was unable to complete your request.</p>", 500)

    return app


if __name__ == '__main__':
    app = create_app()
    # 绑 0.0.0.0 让同 WiFi 的手机可访问预览;关掉 reloader 避免双进程干扰控制台管理。
    # 想要改代码自动热重载时,把 use_reloader 改 True(仅本机调试用)。
    # threaded=True:每个请求独立线程,避免移动浏览器多连接排队导致"网页无法加载"。
    # debug=False:开发服务器的 debug 模式对外网移动端不可靠且有安全隐患。
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False, threaded=True)