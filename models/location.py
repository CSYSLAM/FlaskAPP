import json
import time
import random
from pathlib import Path

class Location:
    def __init__(self, scene_id, name, area_id, area_name, monster_type, exits=None):
        self.scene_id = scene_id
        self.name = name
        self.area_id = area_id
        self.area_name = area_name
        self.monster_type = monster_type
        self.north_exit = exits.get("north") if exits else None
        self.south_exit = exits.get("south") if exits else None
        self.east_exit = exits.get("east") if exits else None
        self.west_exit = exits.get("west") if exits else None
        self.players = set()
        self.ground_items = []
        self.last_refresh_time = time.time()

    def refresh_ground_items(self):
        current_time = time.time()
        if current_time - self.last_refresh_time > 1:  # 5分钟刷新
            self.ground_items.clear()
            if random.random() < 0.8:  # 80%概率出现地面物品
                self.ground_items.append("money_small")
            self.last_refresh_time = current_time

    @classmethod
    def get_locations(cls):
        locations = {}
        data_file = Path("data/locations.json")
        
        with open(data_file, 'r', encoding='utf-8') as f:
            areas_data = json.load(f)
            
        for area_id, area_data in areas_data.items():
            for scene_id, scene_data in area_data["scenes"].items():
                full_scene_id = f"{area_id}.{scene_id}"
                locations[full_scene_id] = cls(
                    scene_id=scene_id,
                    name=scene_data["name"],
                    area_id=area_id,
                    area_name=area_data["name"],
                    monster_type=scene_data["monster_type"],
                    exits=scene_data.get("exits", {})
                )
                
        return locations

    def add_player(self, player):
        self.players.add(player)

    def remove_player(self, player):
        self.players.remove(player)
