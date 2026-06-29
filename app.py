# # 1. 丢弃 app.py 和 game1.db 的本地修改，恢复成远程版本
# git checkout -- app.py instance/game1.db

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

    @app.before_request
    def track_online():
        from flask_login import current_user
        if current_user.is_authenticated:
            from services.party_service import mark_online
            mark_online(current_user.id)

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