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

    from services.world_boss_service import WorldBossService
    WorldBossService.init_bosses()

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
    from blueprints.dungeon import dungeon_bp
    from blueprints.workbench import workbench_bp

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
    app.register_blueprint(dungeon_bp, url_prefix='/dungeon')
    app.register_blueprint(workbench_bp, url_prefix='/workbench')

    from blueprints.crafting import crafting_bp
    app.register_blueprint(crafting_bp, url_prefix='/crafting')

    @app.route('/ref/<path:filename>')
    def ref_file(filename):
        ref_dir = Path(app.root_path) / 'ref'
        return send_from_directory(ref_dir, filename)

    @app.route('/')
    def index():
        from flask import redirect, url_for
        return redirect(url_for('game.scene'))

    with app.app_context():
        db.create_all()
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

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)