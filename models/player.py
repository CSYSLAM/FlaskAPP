import random
from models.equipment import Equipment
from models.item import Item, ItemType
from datetime import datetime

class Player:
    SKILLS = {
        "术士": ["天雷术", "地火术"],
        "战士": ["十刃斩", "暴风杀"],
        "刺客": ["破甲刺", "二连击"]
    }
    
    SKILL_EFFECTS = {
        "天雷术": {"damage_multiplier": 2.0, "mana_cost": 30},
        "地火术": {"damage_multiplier": 1.8, "mana_cost": 25},
        "十刃斩": {"damage_multiplier": 1.9, "mana_cost": 25},
        "暴风杀": {"damage_multiplier": 1.7, "mana_cost": 20},
        "破甲刺": {"damage_multiplier": 2.2, "mana_cost": 35},
        "二连击": {"damage_multiplier": 1.6, "mana_cost": 15, "hits": 2}
    }
    CLASSES = {
        "术士": {
            "base_stats": {
                "max_health": 80,
                "max_mana": 100,
                "attack": 20,
                "defense": 3,
                "crit_rate": 0.03,
                "dodge_rate": 0.03
            },
            "level_up_stats": {
                "max_health": 15,
                "max_mana": 20,
                "attack": 8,
                "defense": 2,
                "crit_rate": 0.005,
                "dodge_rate": 0.005
            }
        },
        "战士": {
            "base_stats": {
                "max_health": 120,
                "max_mana": 50,
                "attack": 15,
                "defense": 8,
                "crit_rate": 0.03,
                "dodge_rate": 0.03
            },
            "level_up_stats": {
                "max_health": 25,
                "max_mana": 10,
                "attack": 5,
                "defense": 4,
                "crit_rate": 0.005,
                "dodge_rate": 0.005
            }
        },
        "刺客": {
            "base_stats": {
                "max_health": 90,
                "max_mana": 60,
                "attack": 18,
                "defense": 4,
                "crit_rate": 0.08,
                "dodge_rate": 0.08
            },
            "level_up_stats": {
                "max_health": 18,
                "max_mana": 12,
                "attack": 6,
                "defense": 3,
                "crit_rate": 0.015,
                "dodge_rate": 0.015
            }
        }
    }

    def __init__(self, name, player_class):
        self.name = name
        self.player_class = player_class
        self.level = 1

        self.experience = 0
        self.exp_to_next_level = 50
        self.money = 0
        self.last_damage_taken = 0
        self.last_damage_dealt = 0
        self.last_battle_result = ""
        self.item_effect = ""
        self.current_location = "outdoor.village"
        self.learned_skills = []
        self.equipment = {slot: None for slot in Equipment.SLOTS}
        self.inventory = {}
        self.last_chat_message = None  # 最后收到的聊天消息
        self.chat_refresh_count = 0    # 场景刷新计数
        self.chat_history = {}         # 聊天历史记录 {username: [messages]}
        self.notifications = []  # Add this line
        self.current_view = "chat"  
        self.enhance_bonus_rate = 0  # 添加全局强化成功率加成

        self.in_battle = False  # Add this line
        self.in_pk = False
        self.pk_opponent = None
        self.last_attack_time = 0

        # 基础属性(每级成长)
        self.base_stats = self.CLASSES[player_class]["base_stats"].copy()

        # 当前实际属性
        self.max_health = 0
        self.health = 0
        self.max_mana = 0
        self.mana = 0
        self.attack = 0
        self.defense = 0
        self.crit_rate = 0
        self.dodge_rate = 0
        
        # 成长属性(等级带来的加成)
        self.growth_stats = {
            "max_health": 0,
            "max_mana": 0,
            "attack": 0,
            "defense": 0,
            "crit_rate": 0,
            "dodge_rate": 0
        }
        
        # 装备属性
        self.equipment_stats = {
            "max_health": 0,
            "max_mana": 0,
            "attack": 0,
            "defense": 0,
            "crit_rate": 0,
            "dodge_rate": 0
        }
        
        # 金丹属性
        self.pill_stats = {
            "max_health": 0,
            "max_mana": 0,
            "attack": 0,
            "defense": 0
        }

        self.update_stats()
        self.health = self.max_health  # Set initial health
        self.mana = self.max_mana     # Set initial mana

        self.shortcuts = {
            'skill1': 'attack',
            'skill2': 'attack',
            'skill3': 'attack',
            'skill4': 'attack',
            'potion1': None,
            'potion2': None
        }

    def enter_battle(self):
        self.in_battle = True

    def exit_battle(self):
        self.in_battle = False

    def can_equip(self, equipment: Equipment) -> tuple[bool, str]:
        if self.level < equipment.level_required:
            return False, f"需要等级{equipment.level_required}"
            
        if equipment.class_required and equipment.class_required != self.player_class:
            return False, f"需要职业{equipment.class_required}"
            
        return True, ""

    def equip(self, equipment_data):
        if isinstance(equipment_data, dict):
            equipment = Equipment.from_dict(equipment_data)
        else:
            equipment = equipment_data

        can_equip, message = self.can_equip(equipment)
        if not can_equip:
            self.item_effect = message
            return None

        # 记录装备前的属性
        old_stats = self.get_current_stats()
        
        # 更换装备
        old_equipment = self.equipment[equipment.slot]
        equipment.update_name()  # 更新装备名称
        self.equipment[equipment.slot] = equipment
        
        if not equipment.is_bound:
            equipment.is_bound = True
        
        # 更新属性并生成变化信息
        self.update_stats()
        new_stats = self.get_current_stats()
        
        changes = self.generate_stat_changes(old_stats, new_stats)
        self.item_effect = f"装备了 {equipment.name}\n{changes}"
        
        return old_equipment

    def unequip(self, slot):
        if self.equipment[slot]:
            # 记录卸下前的属性
            old_stats = self.get_current_stats()
            
            equipment = self.equipment[slot]
            equipment.update_name()  # 更新装备名称
            self.equipment[slot] = None
            
            # 更新属性并生成变化信息
            self.update_stats()
            new_stats = self.get_current_stats()
            
            changes = self.generate_stat_changes(old_stats, new_stats)
            self.item_effect = f"卸下了 {equipment.name}\n{changes}"
            
            return equipment.to_dict()
        return None

    def get_current_stats(self) -> dict:
        return {
            "max_health": self.max_health,
            "max_mana": self.max_mana,
            "attack": self.attack,
            "defense": self.defense,
            "crit_rate": self.crit_rate,
            "dodge_rate": self.dodge_rate
        }

    def generate_stat_changes(self, old_stats: dict, new_stats: dict) -> str:
        changes = []
        for stat, name in Equipment.STAT_NAMES.items():
            old_val = old_stats.get(stat, 0)
            new_val = new_stats.get(stat, 0)
            diff = new_val - old_val
            if diff != 0:
                if stat in ['crit_rate', 'dodge_rate']:
                    changes.append(f"{name}: {diff*100:+.1f}%")
                else:
                    changes.append(f"{name}: {diff:+.1f}")  # Changed from +d to +.1f
        return "\n".join(changes)

    def update_stats(self):
        # 计算成长属性 = 基础属性 * 等级
        for stat, value in self.base_stats.items():
            self.growth_stats[stat] = value * self.level
        
        # 计算装备属性
        self.equipment_stats = {stat: 0 for stat in self.growth_stats}
        for equipment in self.equipment.values():
            if equipment:
                if isinstance(equipment, dict):
                    equipment = Equipment.from_dict(equipment)
                # 基础属性
                for stat, value in equipment.base_stats.items():
                    self.equipment_stats[stat] += value
                # 附加属性
                for stat, (value, stars) in equipment.extra_stats.items():
                    self.equipment_stats[stat] += value
        
        # 最终属性 = 成长属性 + 装备属性 + 金丹属性
        self.max_health = self.growth_stats["max_health"] + self.equipment_stats["max_health"] + self.pill_stats["max_health"]
        self.max_mana = self.growth_stats["max_mana"] + self.equipment_stats["max_mana"] + self.pill_stats["max_mana"]
        self.attack = self.growth_stats["attack"] + self.equipment_stats["attack"] + self.pill_stats["attack"]
        self.defense = self.growth_stats["defense"] + self.equipment_stats["defense"] + self.pill_stats["defense"]
        self.crit_rate = self.growth_stats["crit_rate"] + self.equipment_stats["crit_rate"]
        self.dodge_rate = self.growth_stats["dodge_rate"] + self.equipment_stats["dodge_rate"]

    def level_up(self):
        if self.experience >= self.exp_to_next_level:
            self.level += 1
            self.experience -= self.exp_to_next_level
            self.exp_to_next_level = int(self.exp_to_next_level * 1.5)
            
            self.update_stats()
            self.health = self.max_health
            self.mana = self.max_mana
            return True
        return False

    def attack_monster(self, monster):
        self.last_skill = "普通攻击"
        self.last_action = "使用了普通攻击"
        self.last_mana_cost = 0
        
        if random.random() >= monster.dodge_rate:
            damage = max(0, self.attack - monster.defense)
            
            if random.random() <= self.crit_rate:
                damage *= 2
                self.last_damage_dealt = f"{damage}(暴击!)"
            else:
                self.last_damage_dealt = str(damage)
                
            monster.health -= damage
            monster.last_damage_taken = damage
            return damage
        else:
            self.last_damage_dealt = "闪避"
            monster.last_damage_taken = 0
            return 0

    def learn_skill(self, skill_name):
        if skill_name in self.SKILLS[self.player_class]:
            if skill_name not in self.learned_skills:
                self.learned_skills.append(skill_name)
                return True
        return False

    def use_skill(self, monster, skill_name):
        if skill_name not in self.learned_skills and skill_name != "attack":
            self.last_action = "技能未学习"
            return 0
            
        if skill_name == "attack":
            return self.attack_monster(monster)
            
        skill = self.SKILL_EFFECTS[skill_name]
        mana_cost = skill["mana_cost"]
        
        if self.mana < mana_cost:
            self.last_action = f"魔法值不足，需要{mana_cost}点魔法值"
            self.last_mana_cost = 0
            self.last_damage_dealt = 0
            return 0
            
        self.mana -= mana_cost
        self.last_mana_cost = mana_cost
        self.last_skill = skill_name
        self.last_action = f"使用了{skill_name}"
        
        if random.random() >= monster.dodge_rate:
            base_damage = max(0, self.attack * skill["damage_multiplier"] - monster.defense)
            
            if "hits" in skill:
                total_damage = 0
                for _ in range(skill["hits"]):
                    damage = base_damage
                    if random.random() <= self.crit_rate:
                        damage *= 2
                    total_damage += damage
                self.last_damage_dealt = f"{total_damage}"
                monster.health -= total_damage
                monster.last_damage_taken = total_damage
                return total_damage
            else:
                damage = base_damage
                if random.random() <= self.crit_rate:
                    damage *= 2
                    self.last_damage_dealt = f"{damage}(暴击!)"
                else:
                    self.last_damage_dealt = f"{damage}"
                monster.health -= damage
                monster.last_damage_taken = damage
                return damage
        else:
            self.last_damage_dealt = "闪避"
            monster.last_damage_taken = 0
            return 0

    def to_dict(self):
        data = self.__dict__.copy()
        # 处理聊天历史中的datetime
        if 'chat_history' in data:
            for username in data['chat_history']:
                for message in data['chat_history'][username]:
                    if isinstance(message['time'], datetime):
                        message['time'] = message['time'].strftime('%Y-%m-%d %H:%M:%S')
        
        # 处理最新消息中的datetime
        if data.get('last_chat_message') and isinstance(data['last_chat_message'].get('time'), datetime):
            data['last_chat_message']['time'] = data['last_chat_message']['time'].strftime('%Y-%m-%d %H:%M:%S')
        # Convert inventory items to serializable format
        inventory_data = {}
        for item_id, item_data in self.inventory.items():
            if isinstance(item_data, dict) and "item" in item_data:
                inventory_data[item_id] = {
                    "item": item_data["item"],  # Already a dict, no need for __dict__
                    "quantity": item_data["quantity"]
                }
            else:
                # Handle legacy inventory data
                inventory_data[item_id] = item_data
        data['inventory'] = inventory_data
        
        # Handle equipment as before
        data['equipment'] = {
            slot: equip if isinstance(equip, dict) else equip.to_dict() if equip else None 
            for slot, equip in self.equipment.items()
        }
        return data

    def add_item(self, item_id):
        items = Item.load_items()
        if item_id in items:
            if item_id in self.inventory:
                if isinstance(self.inventory[item_id], dict) and "quantity" in self.inventory[item_id]:
                    self.inventory[item_id]["quantity"] += 1
                else:
                    self.inventory[item_id] = {
                        "item": items[item_id].to_dict(),
                        "quantity": 1
                    }
            else:
                self.inventory[item_id] = {
                    "item": items[item_id].to_dict(),
                    "quantity": 1
                }

    def use_revive_item(self):
        if "续命灯" in self.inventory and self.inventory["续命灯"] > 0:
            self.inventory["续命灯"] -= 1
            if self.inventory["续命灯"] <= 0:
                del self.inventory["续命灯"]
            self.health = self.max_health
            return True
        return False

    def weak_revive(self):
        self.health = max(10, self.max_health // 10)

    def use_item(self, item_id):
        if item_id in self.inventory:
            item_data = self.inventory[item_id]
            item = Item.from_dict(item_data["item"])
            
            if not item.is_usable:
                self.item_effect = f"{item.name}不可使用"
                return False
                    
            # Check usage conditions
            if item.usage_condition:
                if item.usage_condition.level_required > self.level:
                    self.item_effect = f"需要等级{item.usage_condition.level_required}"
                    return False
                        
                for req_item, req_count in item.usage_condition.required_items.items():
                    if req_item not in self.inventory or self.inventory[req_item]["quantity"] < req_count:
                        self.item_effect = f"需要{req_count}个{Item.load_items()[req_item].name}"
                        return False
            
            # Apply usage effects
            if item.usage_effect:
                effect_description = []
                
                # Apply stat changes
                for stat, value in item.usage_effect.stat_changes.items():
                    if stat.startswith('pill_'):
                        # 处理金丹属性
                        stat_name = stat.replace('pill_', '')
                        self.pill_stats[stat_name] += value
                        effect_description.append(f"永久{Equipment.STAT_NAMES[stat_name]}增加了{value}")
                    elif hasattr(self, stat):
                        # 处理临时属性(如生命值、魔法值恢复)
                        old_value = getattr(self, stat)
                        if stat == "health":
                            new_value = min(self.max_health, old_value + value)
                        elif stat == "mana":
                            new_value = min(self.max_mana, old_value + value)
                        else:
                            new_value = old_value + value
                        
                        setattr(self, stat, new_value)
                        actual_change = new_value - old_value
                        if actual_change > 0:
                            if stat == "health":
                                effect_description.append(f"恢复了{actual_change}点生命值")
                            elif stat == "mana":
                                effect_description.append(f"恢复了{actual_change}点魔法值")
                            else:
                                effect_description.append(f"{stat}增加了{actual_change}")
                
                # Apply item changes and random items
                if item.usage_effect.item_changes or item.usage_effect.random_items:
                    items_gained = []
                    
                    # Handle required item consumption
                    for change_item, change_count in item.usage_effect.item_changes.items():
                        if change_count < 0:
                            self.inventory[change_item]["quantity"] += change_count
                            if self.inventory[change_item]["quantity"] <= 0:
                                del self.inventory[change_item]
                    
                    # Handle random rewards
                    if item.usage_effect.random_items:
                        for item_info in item.usage_effect.random_items:
                            item_id = item_info["item_id"]
                            max_count = item_info["max_count"]
                            chance = item_info["chance"]
                            guaranteed_count = item_info["guaranteed_count"]
                            
                            # First add guaranteed items
                            total_count = guaranteed_count
                            
                            # Then calculate random items
                            if max_count > guaranteed_count:
                                remaining_count = max_count - guaranteed_count
                                for _ in range(remaining_count):
                                    if random.random() < chance:
                                        total_count += 1
                            
                            if total_count > 0:
                                items_gained.append(f"{Item.load_items()[item_id].name}x{total_count}")
                                for _ in range(total_count):
                                    self.add_item(item_id)
                    
                    if items_gained:
                        effect_description.append(f"获得了: {', '.join(items_gained)}")
                
                self.item_effect = "、".join(effect_description)

                # 如果是永久属性提升道具，更新属性
                if item.is_permanent_buff:
                    self.update_stats()
            
            # Remove used item
            item_data["quantity"] -= 1
            if item_data["quantity"] <= 0:
                del self.inventory[item_id]
            
            return True



    @classmethod
    def from_dict(cls, data):
        player = cls(data["name"], data["player_class"])
        # Update other attributes
        for key, value in data.items():
            if key != "inventory" and key != "equipment":
                setattr(player, key, value)
        
        # 正确加载装备数据
        if "equipment" in data:
            equipment_data = data["equipment"]
            player.equipment = {
                slot: Equipment.from_dict(equip_data) if equip_data else None
                for slot, equip_data in equipment_data.items()
            }
        
        # 正确加载背包数据，保持原有数据结构
        if "inventory" in data:
            player.inventory = data["inventory"]
            
        # 保持原有的物品加载逻辑
        items = Item.load_items()
        for item_id, item_data in data.get("inventory", {}).items():
            if isinstance(item_data, dict) and "quantity" in item_data:
                if item_id in items and not item_id.startswith('equipment_'):
                    player.inventory[item_id] = {
                        "item": items[item_id].to_dict(),
                        "quantity": item_data["quantity"]
                    }
                    
        return player




