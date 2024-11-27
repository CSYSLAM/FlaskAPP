import random
import json
from pathlib import Path
from models.equipment import Equipment
from models.equipment_template import EquipmentTemplate

class Monster:
    def __init__(self, monster_id: str, data: dict):
        self.monster_id = monster_id
        self.is_elite = data.get("is_elite", False)
        self.name = f"【精】{data['name']}" if self.is_elite else data["name"]
        self.level = data["level"]
        self.killable = data["killable"]
        self.immortal = data["immortal"]
        self.description = data["description"]
        
        # Set base stats
        stats = data["base_stats"]
        self.health = stats["health"]
        self.max_health = stats["health"]
        self.mana = stats["mana"]
        self.max_mana = stats["mana"]
        self.attack = stats["attack"]
        self.defense = stats["defense"]
        self.crit_rate = stats["crit_rate"]
        self.dodge_rate = stats["dodge_rate"]
        
        self.skills = data["skills"]
        self.drops = data["drops"]
        self.last_damage_taken = 0

    @classmethod
    def load_monsters(cls):
        with open(Path("data/monsters.json"), 'r', encoding='utf-8') as f:
            return json.load(f)

    @classmethod
    def create_monster(cls, monster_id: str):
        monsters = cls.load_monsters()
        if monster_id in monsters:
            return cls(monster_id, monsters[monster_id])
        print(f"Warning: Monster {monster_id} not found in monsters.json")
        return None

    def attack_player(self, player):
        self.last_action = "使用了普通攻击"
        self.last_skill = "普通攻击"
        
        if random.random() >= player.dodge_rate:
            damage = max(0, self.attack - player.defense)
            if random.random() <= self.crit_rate:
                damage *= 2
                self.last_damage_dealt = f"{damage}(暴击!)"
            else:
                self.last_damage_dealt = str(damage)
            player.health -= damage
            player.last_damage_taken = damage
            return damage
        else:
            self.last_damage_dealt = "闪避"
            player.last_damage_taken = "闪避"
            return 0

    def get_loot(self):
        if random.random() < 0.4:  # 30% chance for equipment
            if self.drops["equipment_templates"]:
                template_id = random.choice(self.drops["equipment_templates"])
                template = Equipment.load_template(template_id)
                
                if template.get("is_artifact", False):
                    rarity = "神器"
                else:
                    if self.is_elite:
                        rarity_chances = {
                            "普通": 0.4,
                            "精良": 0.3,
                            "卓越": 0.2,
                            "史诗": 0.1
                        }
                    else:
                        rarity_chances = {"普通": 1.0}
                        
                    rarity = random.choices(
                        list(rarity_chances.keys()),
                        list(rarity_chances.values())
                    )[0]
                
                stars = random.randint(1, 5)
                return Equipment(template_id, rarity, stars)
        
        # Then try to drop items based on drop rates
        for item_id, chance in self.drops["items"].items():
            if random.random() < chance:
                return item_id
        return None


    def get_money_drop(self):
        return random.randint(self.drops["money"]["min"], 
                            self.drops["money"]["max"])

    def get_experience_drop(self):
        return self.drops["experience"]

    def reset_health(self):
        if self.immortal:
            self.health = self.max_health
