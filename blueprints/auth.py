from flask import Blueprint, render_template, redirect, url_for, request, session
from models.player import Player
from services.data_service import DataService
from utils.decorators import check_health_status

auth_bp = Blueprint('auth', __name__)

@auth_bp.route("/login", methods=["GET", "POST"])
@check_health_status
def login_page():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        
        player_data = DataService.load_player_data(username)
        if player_data and player_data.get("password") == password:
            session["username"] = username
            return redirect(url_for("game.scene"))
        return render_template("login.html", message="账号或密码错误")
    return render_template("login.html")

@auth_bp.route("/register", methods=["POST"])
def register():
    username = request.form.get("username")
    password = request.form.get("password")
    nickname = request.form.get("nickname")
    player_class = request.form.get("player_class")
    
    if DataService.load_player_data(username):
        return render_template("login.html", message="账号已存在")
    
    if player_class not in Player.CLASSES:
        return render_template("login.html", message="无效的职业选择")
    
    gender = request.form.get("gender")
    player = Player(nickname, player_class)
    player.username = username
    player.password = password
    player.gender = gender
    player.current_location = "outdoor.village"
    
    DataService.save_player_data(username, player)
    session["username"] = username
    return redirect(url_for("game.scene"))

@auth_bp.route("/logout")
def logout():
    if "username" in session:
        session.pop("username", None)
    return redirect(url_for("auth.login_page"))