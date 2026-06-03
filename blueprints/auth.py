from flask import Blueprint, render_template, redirect, url_for, request, session, flash
from flask_login import login_user, logout_user, current_user, login_required
from services.player_service import PlayerService
from services.data_service import DataService
from models.player import PlayerModel

auth_bp = Blueprint('auth', __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        player, error = PlayerService.authenticate(username, password)
        if error:
            return render_template("login.html", message=error)
        login_user(player)
        session["username"] = username
        session["player_id"] = player.id
        # VIP5 broadcast on login
        from services.vip_service import VipService
        if VipService.has_broadcast(player):
            DataService.broadcast_system(f"尊贵的VIP{VipService.get_active_vip_level(player)}玩家【{player.nickname}】上线了！")
        return redirect(url_for("game.scene"))
    return render_template("login.html")


@auth_bp.route("/register", methods=["POST"])
def register():
    username = request.form.get("username")
    password = request.form.get("password")
    nickname = request.form.get("nickname")
    player_class = request.form.get("player_class")
    gender = request.form.get("gender")
    country = request.form.get("country", "魏")

    player, error = PlayerService.register(
        username, password, nickname, player_class, gender, country)
    if error:
        return render_template("login.html", message=error)

    login_user(player)
    session["username"] = username
    session["player_id"] = player.id
    return redirect(url_for("game.scene"))


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    session.pop("username", None)
    session.pop("player_id", None)
    return redirect(url_for("auth.login_page"))
