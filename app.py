from flask import Flask
from config import Config
from services.data_service import DataService
from blueprints.auth import auth_bp
from blueprints.game import game_bp
from blueprints.player import player_bp
from blueprints.battle import battle_bp
from blueprints.shop import shop_bp
from blueprints.social import social_bp

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Initialize services
    DataService.init_app(app)
    
    # Register blueprints
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(game_bp)
    app.register_blueprint(player_bp, url_prefix='/player')
    app.register_blueprint(battle_bp, url_prefix='/battle')
    app.register_blueprint(shop_bp, url_prefix='/shop')
    app.register_blueprint(social_bp, url_prefix='/social')
    
    # Root route
    @app.route("/")
    def index():
        from flask import session, redirect, url_for
        if "username" in session:
            return redirect(url_for("game.scene"))
        return redirect(url_for("auth.login_page"))
    
    return app

if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)