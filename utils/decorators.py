from functools import wraps
from flask import session, redirect, url_for
from services.data_service import DataService

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("auth.login_page"))
        return f(*args, **kwargs)
    return decorated_function

def check_pk_status(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        player = DataService.get_current_player(session)
        if player and player.in_pk:
            return redirect(url_for('battle.pk_battle', opponent=player.pk_opponent))
        return f(*args, **kwargs)
    return decorated_function

def check_health_status(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        player = DataService.get_current_player(session)
        if player and player.health <= 0:
            return redirect(url_for("battle.revive"))
        return f(*args, **kwargs)
    return decorated_function