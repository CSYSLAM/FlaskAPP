from flask_login import login_required as flask_login_required


# Keep check_pk_status and check_health_status as custom decorators
# login_required now comes from flask_login directly


def check_pk_status(f):
    from functools import wraps
    from flask import redirect, url_for
    from flask_login import current_user

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.is_authenticated and current_user.in_pk:
            return redirect(url_for('battle.pk_battle',
                                   opponent=current_user.pk_opponent))
        return f(*args, **kwargs)
    return decorated_function


def check_health_status(f):
    from functools import wraps
    from flask import redirect, url_for, flash
    from flask_login import current_user

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.is_authenticated and current_user.health <= 0:
            return redirect(url_for("battle.revive"))
        return f(*args, **kwargs)
    return decorated_function