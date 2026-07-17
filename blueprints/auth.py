from flask import Blueprint, render_template, redirect, url_for, request, session, flash
from flask_login import login_user, logout_user, current_user, login_required
from services.player_service import PlayerService
from services.data_service import DataService
from models.player import PlayerModel

auth_bp = Blueprint('auth', __name__)

# 国家对应出生场景
COUNTRY_START = {
    '魏': 'beiping_east.大院',
    '蜀': 'jianing_west.大院',
    '吴': 'wujun_east.大院',
}

# 国家对应剧情场景
COUNTRY_STORY = {
    '魏': 'story_wei',
    '蜀': 'story_shu',
    '吴': 'story_wu',
}


@auth_bp.route("/", methods=["GET", "POST"])
def login_page():
    """登录页面"""
    if current_user.is_authenticated:
        return redirect(url_for('auth.select_server'))

    register_msg = session.pop('register_msg', None)
    # 被单点登录踢下线时携带的提示
    kicked_msg = "该账号在别处登录，您已下线" if request.args.get("kicked") else None

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        player, error = PlayerService.authenticate(username, password)
        if error:
            return render_template("login.html", message=error)
        login_user(player)
        session["username"] = username
        session["player_id"] = player.id
        # 多窗口单点登录：按当前 sid 绑定窗口，并把该账号活动 sid 切到此窗口
        # → 旧窗口的 sid 立即失效，下次请求被踢
        from services import window_session_service as _ws
        sid = _ws.get_sid() or _ws.new_sid()
        _ws.bind_window(sid, player.id)
        # VIP5 broadcast on login
        from services.vip_service import VipService
        if VipService.has_broadcast(player):
            DataService.broadcast_system(f"尊贵的VIP{VipService.get_active_vip_level(player)}玩家【{player.nickname}】上线了！")
        return redirect(url_for("auth.select_server"))
    return render_template("login.html", register_msg=register_msg, message=kicked_msg)


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """注册页面"""
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        password2 = request.form.get("password2")

        if not username or not password or not password2:
            return render_template("register.html", message="请填写完整信息")

        if password != password2:
            return render_template("register.html", message="两次密码不一致")

        # 检查用户名是否已存在
        if PlayerModel.query.filter_by(username=username).first():
            return render_template("register.html", message="用户名已存在")

        # 创建账号（只创建账号，没有角色信息）
        from werkzeug.security import generate_password_hash
        import random
        import string
        # 生成唯一10位player_uid
        while True:
            uid = ''.join(random.choices(string.digits + string.ascii_lowercase, k=10))
            if not PlayerModel.query.filter_by(player_uid=uid).first():
                break
        player = PlayerModel(
            username=username,
            password_hash=generate_password_hash(password),
            player_uid=uid,
            nickname='',
            player_class='',
            gender='男',
            country='魏',
            level=1,
            experience=0,
            exp_to_next_level=50,
            gold=1500,
            health=100,
            max_health=100,
            mana=50,
            max_mana=50,
            attack=10,
            defense=5,
            crit_rate=0.05,
            dodge_rate=0.03,
            current_location='beiping_center.广场',
        )
        from services import db
        db.session.add(player)
        db.session.commit()

        # 注册成功后跳转到登录页面显示成功信息
        session['register_msg'] = f'注册成功，建议截图保管账号密码<br>账号：{username}<br>密码：{password}'
        return redirect(url_for('auth.login_page'))

    return render_template("register.html")


@auth_bp.route("/select_server")
@login_required
def select_server():
    """选区页面"""
    return render_template("select_server.html")


@auth_bp.route("/select_role")
@login_required
def select_role():
    """选角色/创建角色页面"""
    player = current_user
    # 如果已有角色
    if player.nickname and player.player_class:
        # 如果剧情未完成，重新过剧情（重置状态）
        if not player.story_completed:
            return redirect(url_for('auth.story', story_id=0))
        return redirect(url_for('game.scene'))

    # 还没有角色，进入创建角色页面
    return render_template("create_role.html")


@auth_bp.route("/create_role", methods=["GET", "POST"])
@login_required
def create_role():
    """创建角色页面"""
    player = current_user

    if request.method == "POST":
        nickname = request.form.get("nickname")
        player_class = request.form.get("player_class")
        gender = request.form.get("gender")
        country = request.form.get("country")

        if not all([nickname, player_class, gender, country]):
            return render_template("create_role.html", message="请填写完整信息")

        result, error = PlayerService.create_character(player, nickname, player_class, gender, country)
        if error:
            return render_template("create_role.html", message=error)

        # 创建角色成功，进入剧情
        return redirect(url_for('auth.story', story_id=1))

    return render_template("create_role.html", player=player)


@auth_bp.route("/story/<int:story_id>")
@login_required
def story(story_id):
    """剧情页面"""
    player = current_user
    total_stories = 5

    if story_id < 0:
        story_id = 0
    if story_id > total_stories:
        story_id = total_stories

    # 魏蜀吴剧情内容不同
    story_key = f'story_{story_id}'
    country = player.country or '魏'

    return render_template("story.html",
                         player=player,
                         story_id=story_id,
                         total_stories=total_stories,
                         country=country,
                         next_id=story_id + 1 if story_id < total_stories else None)


@auth_bp.route("/story_complete")
@login_required
def story_complete():
    """完成剧情，进入游戏"""
    player = current_user
    player.story_completed = True

    # 设置出生场景
    country = player.country or '魏'
    start_location = COUNTRY_START.get(country, 'beiping_center.广场')
    player.current_location = start_location

    from services import db
    db.session.commit()

    return redirect(url_for('game.scene'))


@auth_bp.route("/logout")
@login_required
def logout():
    from services import window_session_service as _ws
    from services import auth_session_service as _sso
    sid = _ws.get_sid()
    pid = current_user.id
    # 仅登出当前窗口，不影响其他窗口（多开场景）
    if sid:
        _ws.clear_window(sid)
        _sso.clear(pid, sid=sid)
    logout_user()
    session.pop("username", None)
    session.pop("player_id", None)
    return redirect(url_for("auth.login_page"))