import random
import time
from models.monster import Monster
from models.location import Location
from models.equipment import Equipment
from models.item import Item
from services.data_service import DataService
from services.public_chat import broadcast_system
from services.player_service import PlayerService

class GameService:
    current_monster = None
    
    @classmethod
    def initialize_monster_if_needed(cls, player):
        """如果怪物不存在则初始化"""
        if cls.current_monster is None:
            cls.generate_new_monster(player)
    
    @classmethod
    def generate_new_monster(cls, player):
        locations = Location.get_locations()
        cls.current_monster = Monster.create_monster(
            locations[player.current_location].monster_type
        )
    
    @classmethod
    def get_current_monster(cls):
        return cls.current_monster
    
    @classmethod
    def handle_monster_defeat(cls, player):
        loot = cls.current_monster.get_loot()
        money = cls.current_monster.get_money_drop()
        loot_name = None
        
        if isinstance(loot, Equipment):
            new_id = f"equipment_{int(time.time())}_{random.randint(1000, 9999)}"
            player.inventory[new_id] = loot.to_dict()
            loot_name = loot.name
            # 精英怪掉落装备时广播
            if cls.current_monster.is_elite:
                broadcast_system(f"{player.name}在{Location.get_locations()[player.current_location].name}击杀精英{cls.current_monster.name}，掉落{loot_name}")
        elif loot:
            items = Item.load_items()
            if loot in items:
                player.add_item(loot)
                loot_name = items[loot].name
        
        player.money += money
        PlayerService.gain_experience(player, 20)
        player.last_battle_result = (
            f"你击败了{cls.current_monster.name}！" +
            (f"获得了{loot_name}，" if loot_name else "这次什么也没掉落，") +
            f"经验增加了20，获得{money}银两。"
        )
        
        cls.generate_new_monster(player)
    
    @classmethod
    def handle_pk_victory(cls, winner, loser):
        # 计算金钱掠夺
        money_percent = random.uniform(0.003, 0.013)
        money_gained = int(loser.money * money_percent)
        winner.money += money_gained
        loser.money -= money_gained
        
        # 随机选择一个非绑定物品
        non_bound_items = [
            item_id for item_id, item_data in loser.inventory.items()
            if (item_id.startswith('equipment_') and 
                not Equipment.from_dict(item_data).is_bound)
        ]
        
        lost_item_name = None
        if non_bound_items:
            item_id = random.choice(non_bound_items)
            lost_item_name = loser.inventory[item_id]["name"]
            winner.inventory[item_id] = loser.inventory[item_id]
            del loser.inventory[item_id]
            
        # 更新战斗结果
        winner.last_battle_result = f"你击败了{loser.name}！获得了{money_gained}银两"
        if lost_item_name:
            winner.last_battle_result += f"，获得了 {lost_item_name}"
        
        loser.last_battle_result = f"你被{winner.name}击败了，损失了{money_gained}银两"
        if lost_item_name:
            loser.last_battle_result += f"，失去了 {lost_item_name}"
        
        # 重置PK状态
        winner.in_pk = False
        winner.pk_opponent = None
        loser.in_pk = False
        loser.pk_opponent = None
        
        DataService.save_player_data(winner.username, winner)
        DataService.save_player_data(loser.username, loser)