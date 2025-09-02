import json
from pathlib import Path
from models.player import Player, PlayerModel
from models.equipment import Equipment
from config import Config
from services import db

class DataService:
    _app = None
    
    @classmethod
    def init_app(cls, app):
        cls._app = app
    
    @staticmethod
    def save_player_data(username, player):
        # 保存到数据库
        model = PlayerModel.query.filter_by(username=username).first()
        if not model:
            model = PlayerModel(username=username)
            db.session.add(model)
        model.player_data = json.dumps(player.to_dict(), ensure_ascii=False)
        db.session.commit()

    @staticmethod
    def load_player_data(username):
        # 先从数据库取
        model = PlayerModel.query.filter_by(username=username).first()
        if model:
            try:
                return json.loads(model.player_data)
            except Exception:
                pass
        # 兜底：从本地 JSON 读取（迁移兼容）
        file_path = Config.SAVE_DIR / f"{username}.json"
        if file_path.exists():
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None

    @staticmethod
    def get_current_player(session):
        if "username" not in session:
            return None
        player_data = DataService.load_player_data(session["username"])
        if not player_data:
            return None
        
        player = Player(player_data["name"], player_data["player_class"])
        if "equipment" in player_data:
            equipment_data = player_data["equipment"]
            player.equipment = {
                slot: Equipment.from_dict(equip_data) if equip_data else None
                for slot, equip_data in equipment_data.items()
            }
        player_data_copy = player_data.copy()
        player_data_copy.pop('equipment', None)
        player.__dict__.update(player_data_copy)
        player.update_stats()
        player.update_military_rank()
        player.get_avatar_path()
        return player

    @staticmethod
    def get_all_players_in_location(location_id, exclude_username=None):
        other_players = []
        # 优先数据库
        for model in PlayerModel.query.all():
            if exclude_username and model.username == exclude_username:
                continue
            try:
                data = json.loads(model.player_data)
                if data.get("current_location") == location_id:
                    other_players.append(data)
            except Exception:
                continue
        # 若数据库没有，兜底到文件（兼容迁移期）
        if not other_players:
            for file in Config.SAVE_DIR.glob("*.json"):
                if exclude_username and file.stem == exclude_username:
                    continue
                with open(file, 'r', encoding='utf-8') as f:
                    other_player = json.load(f)
                    if other_player["current_location"] == location_id:
                        other_players.append(other_player)
        return other_players