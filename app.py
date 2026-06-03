import os
import traceback
from pathlib import Path
from flask import Flask
from flask_login import LoginManager
from services import db
from services.data_service import DataService
from models.player import PlayerModel


login_manager = LoginManager()


def create_app():
    app = Flask(__name__)

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

    @login_manager.user_loader
    def load_user(user_id):
        return PlayerModel.query.get(int(user_id))

    DataService.init_app(app)

    from blueprints.auth import auth_bp
    from blueprints.game import game_bp
    from blueprints.player import player_bp
    from blueprints.battle import battle_bp
    from blueprints.shop import shop_bp
    from blueprints.social import social_bp
    from blueprints.activity import activity_bp
    from blueprints.lieutenant import lieutenant_bp
    from blueprints.villa import villa_bp
    from blueprints.vip import vip_bp
    from blueprints.rank import rank_bp
    from blueprints.guide import guide_bp
    from blueprints.map_route import map_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(game_bp, url_prefix='/game')
    app.register_blueprint(player_bp, url_prefix='/player')
    app.register_blueprint(battle_bp, url_prefix='/battle')
    app.register_blueprint(shop_bp, url_prefix='/shop')
    app.register_blueprint(social_bp, url_prefix='/social')
    app.register_blueprint(activity_bp)
    app.register_blueprint(lieutenant_bp)
    app.register_blueprint(villa_bp)
    app.register_blueprint(vip_bp)
    app.register_blueprint(rank_bp)
    app.register_blueprint(guide_bp)
    app.register_blueprint(map_bp)

    @app.route('/')
    def index():
        from flask import redirect, url_for
        return redirect(url_for('game.scene'))

    with app.app_context():
        db.create_all()

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)