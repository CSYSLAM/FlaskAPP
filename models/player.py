import random
import time
from models.equipment import Equipment
from services.equipment_generator import EquipmentGenerator, EquipmentSource
from services import db
from datetime import datetime as _dt
import json as _json
from models.skill import Skill
from models.item import Item, ItemType
from services.item_reward_registry import handle_reward
from services.public_chat import broadcast_system
from datetime import datetime

class Player:
    STAT_NAMES = {
        "max_health": "生命值",
        "max_mana": "魔法值", 
        "attack": "攻击力",
        "defense": "防御力",
        "crit_rate": "暴击率",
        "dodge_rate": "闪避率"
    }
    # 在 Player 类开头添加军衔配置
    MILITARY_RANKS = {
        "十夫长": {"level": 20, "attack": 20, "honor": 0},
        "百夫长": {"level": 25, "attack": 50, "honor": 30},
        "校尉": {"level": 30, "attack": 100, "honor": 240},
        "都尉": {"level": 35, "attack": 150, "honor": 1020},
        "裨将": {"level": 40, "attack": 200, "honor": 3120},
        "偏将": {"level": 45, "attack": 300, "honor": 7770},
        "中郎将": {"level": 50, "attack": 400, "honor": 16800},
        "车骑将军": {"level": 55, "attack": 500, "honor": 32760},
        "骠骑将军": {"level": 60, "attack": 620, "honor": 59040},
        "大司马": {"level": 65, "attack": 700, "honor": 100000},
        "大都督": {"level": 70, "attack": 1000, "honor": 161050}
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
        self.learned_skills = {}  # 改为字典存储 {skill_id: skill_level}
        self.skill_exp = {}  # 技能经验值 {skill_id: exp}

        self.gender = "男"  # 默认性别
        self.honor = 0  # 荣誉值
        self.military_rank = "十夫长"  # 默认军衔
        self.rank_attack = 0  # 军衔加成攻击力

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
        self.pill_defense = 0
        self.pill_attack = 0
        self.pill_max_health = 0
        self.pill_max_mana = 0

        # 临时属性
        self.temp_effects = {
            "max_health": [],  # [{value: 100, rate: 0.05, expire_time: timestamp}]
            "max_mana": [],
            "attack": [],
            "defense": [], 
            "crit_rate": [],
            "dodge_rate": []
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

    def update_military_rank(self):
        """更新军衔"""
        current_rank = "士兵"
        rank_attack = 0
        
        for rank, requirements in self.MILITARY_RANKS.items():
            if (self.level >= requirements["level"] and 
                self.honor >= requirements["honor"]):
                current_rank = rank
                rank_attack = requirements["attack"]
        
        self.military_rank = current_rank
        self.rank_attack = rank_attack

    def get_avatar_path(self):
        # 获取军衔等级(1-11)
        rank_level = 1
        for i, (rank, _) in enumerate(self.MILITARY_RANKS.items(), 1):
            if rank == self.military_rank:
                rank_level = i
                break
        
        # 格式化等级为两位数字
        rank_str = f"{rank_level:02d}"
        
        # 根据性别、职业确定图片前缀
        if self.player_class == "刺客":
            prefix = "b" if self.gender == "女" else "a"
        elif self.player_class == "战士":
            prefix = "q" if self.gender == "女" else "c"
        elif self.player_class == "术士":
            prefix = "q" if self.gender == "女" else "f"
            
        return f"images/rongyu/{prefix}{rank_str}.png"

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
    
    def add_temp_effect(self, stat, value=0, rate=0, duration=0, item_id=None, effect_name=None):
        """添加临时属性效果
        
        Args:
            stat: 属性名称
            value: 绝对值加成
            rate: 百分比加成
            duration: 持续时间（秒）
            item_id: 物品ID，用于标识效果来源
            effect_name: 效果名称，用于显示
        """
        if stat not in self.temp_effects:
            return False
        
        current_time = time.time()
        expire_time = current_time + duration
        
        # 如果提供了item_id，查找相同物品的效果进行时间延长
        if item_id:
            for effect in self.temp_effects[stat]:
                if effect.get("item_id") == item_id:
                    # 找到相同物品的效果，延长持续时间
                    remaining_time = max(0, effect["expire_time"] - current_time)
                    effect["expire_time"] = current_time + remaining_time + duration
                    self.update_stats()
                    return True
        
        # 添加新效果
        new_effect = {
            "value": value,
            "rate": rate,
            "expire_time": expire_time,
            "item_id": item_id,
            "effect_name": effect_name or f"{stat}_effect"
        }
        
        self.temp_effects[stat].append(new_effect)
        self.update_stats()
        return True

    def clear_expired_effects(self):
        """清理过期的临时效果"""
        now = time.time()
        for stat in self.temp_effects:
            self.temp_effects[stat] = [
                effect for effect in self.temp_effects[stat]
                if effect["expire_time"] > now
            ]

    def get_temp_stat_bonus(self, stat):
        """获取某个属性的临时加成总和"""
        self.clear_expired_effects()
        
        if stat not in self.temp_effects:
            return 0
        
        base_stat = getattr(self, stat, 0)
        flat_bonus = sum(effect["value"] for effect in self.temp_effects[stat])
        rate_bonus = sum(effect["rate"] for effect in self.temp_effects[stat])
        
        return flat_bonus + base_stat * rate_bonus

    def get_temp_effects_description(self, stat):
        """获取某个属性的临时效果描述"""
        self.clear_expired_effects()
        
        if stat not in self.temp_effects or not self.temp_effects[stat]:
            return []
        
        descriptions = []
        current_time = time.time()
        
        for effect in self.temp_effects[stat]:
            remaining_time = max(0, effect["expire_time"] - current_time)
            minutes = int(remaining_time // 60)
            seconds = int(remaining_time % 60)
            
            effect_parts = []
            if effect["value"] > 0:
                effect_parts.append(f"+{effect['value']}")
            if effect["rate"] > 0:
                effect_parts.append(f"+{effect['rate']*100:.1f}%")
            
            if effect_parts:
                time_str = f"{minutes}分{seconds}秒" if minutes > 0 else f"{seconds}秒"
                effect_name = effect.get("effect_name", "")
                descriptions.append(f"{effect_name}({'+'.join(effect_parts)})剩余{time_str}")
        
        return descriptions

    def apply_temp_effects_from_item(self, item_id, temp_effects):
        """从物品应用临时效果，支持模板化处理"""
        effect_descriptions = []
        
        for effect in temp_effects:
            stat = effect.get("stat")
            value = effect.get("value", 0)
            rate = effect.get("rate", 0)
            duration = effect.get("duration", 0)
            effect_name = effect.get("effect_name", "")
            
            if not stat or stat not in self.temp_effects:
                continue
                
            if self.add_temp_effect(stat, value, rate, duration, item_id, effect_name):
                # 生成效果描述
                effect_parts = []
                if value > 0:
                    effect_parts.append(f"{value}点")
                if rate > 0:
                    effect_parts.append(f"{rate*100:.1f}%")
                
                if effect_parts:
                    stat_name = self.STAT_NAMES.get(stat, stat)
                    minutes = int(duration // 60)
                    seconds = int(duration % 60)
                    time_str = f"{minutes}分{seconds}秒" if minutes > 0 else f"{seconds}秒"
                    
                    effect_descriptions.append(
                        f"{effect_name or stat_name}提升{'+'.join(effect_parts)}，持续{time_str}"
                    )
        
        return effect_descriptions

    def modify_health_and_mana(self):
        if self.health > self.max_health:
            self.health = self.max_health
        if self.mana > self.max_mana:
            self.mana = self.max_mana

    def update_stats(self):
        # 获取职业的等级成长属性
        level_up_stats = self.CLASSES[self.player_class]["level_up_stats"]

        # 计算成长属性 = 基础属性 + (等级-1) * 等级成长值
        for stat, base_value in self.base_stats.items():
            growth = level_up_stats[stat] * (self.level - 1)
            self.growth_stats[stat] = base_value + growth
        
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
        self.max_health = self.growth_stats["max_health"] + self.equipment_stats["max_health"] + self.pill_max_health
        self.max_mana = self.growth_stats["max_mana"] + self.equipment_stats["max_mana"] + self.pill_max_mana
        self.attack = self.growth_stats["attack"] + self.equipment_stats["attack"] + self.pill_attack
        self.defense = self.growth_stats["defense"] + self.equipment_stats["defense"] + self.pill_defense
        self.crit_rate = self.growth_stats["crit_rate"] + self.equipment_stats["crit_rate"]
        self.dodge_rate = self.growth_stats["dodge_rate"] + self.equipment_stats["dodge_rate"]

        self.update_military_rank()  # 更新军衔
        self.attack += self.rank_attack  # 加上军衔攻击加成
        self.modify_health_and_mana()

        # 临时属性
        self.max_health += self.get_temp_stat_bonus("max_health") 
        self.max_mana += self.get_temp_stat_bonus("max_mana")
        self.attack += self.get_temp_stat_bonus("attack")
        self.defense += self.get_temp_stat_bonus("defense")
        self.crit_rate += self.get_temp_stat_bonus("crit_rate")
        self.dodge_rate += self.get_temp_stat_bonus("dodge_rate")

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

    def learn_skill(self, skill_id):
        """学习新技能"""
        skills = Skill.load_skills()
        if skill_id not in skills:
            return False, "技能不存在"
            
        skill = skills[skill_id]
        if skill.class_required and skill.class_required != self.player_class:
            return False, "职业不符合要求"
            
        if skill_id in self.learned_skills:
            return False, "已经学习过该技能"
            
        exp_cost, money_cost = skill.level_up_cost()
        if self.experience < exp_cost:
            return False, f"经验不足,需要{exp_cost}点经验"
            
        if self.money < money_cost:
            return False, f"银两不足,需要{money_cost}银两"
            
        self.experience -= exp_cost
        self.money -= money_cost
        self.learned_skills[skill_id] = 1  # 初始等级为1
        self.skill_exp[skill_id] = 0
        return True, f"成功学习技能【{skill.name}】"
    
    def upgrade_skill(self, skill_id):
        """升级已学技能"""
        if skill_id not in self.learned_skills:
            return False, "未学习该技能"
            
        skills = Skill.load_skills()
        skill = skills[skill_id]
        current_level = self.learned_skills[skill_id]
        
        if current_level >= skill.max_level:
            return False, "技能已达到最高等级"
            
        exp_cost, money_cost = skill.level_up_cost()
        if self.experience < exp_cost:
            return False, f"经验不足,需要{exp_cost}点经验"
            
        if self.money < money_cost:
            return False, f"银两不足,需要{money_cost}银两"
            
        self.experience -= exp_cost
        self.money -= money_cost
        self.learned_skills[skill_id] += 1
        return True, f"成功将【{skill.name}】升级到{self.learned_skills[skill_id]}级"

    def use_skill(self, monster, skill_id):
        """使用技能"""
        if skill_id == "attack":
            return self.attack_monster(monster)
            
        if skill_id not in self.learned_skills:
            self.last_action = "技能未学习"
            return 0
            
        skills = Skill.load_skills()
        skill = skills[skill_id]
        skill.level = self.learned_skills[skill_id]  # 设置技能等级
        mana_cost = skill.get_current_mana_cost()
        
        if self.mana < mana_cost:
            self.last_action = f"魔法值不足，需要{mana_cost}点魔法值"
            self.last_mana_cost = 0
            self.last_damage_dealt = 0
            return 0
            
        self.mana -= mana_cost
        self.last_mana_cost = mana_cost
        self.last_skill = skill.name
        self.last_action = f"使用了{skill.name}"
        
        if random.random() >= monster.dodge_rate:
            base_damage = max(0, self.attack * skill.get_current_damage_rate() - monster.defense)
            
            if skill.hits > 1:
                total_damage = 0
                for _ in range(skill.hits):
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
        if "potion_revive" in self.inventory and self.inventory["potion_revive"]["quantity"] > 0:
            self.inventory["potion_revive"]["quantity"] -= 1
            if self.inventory["potion_revive"]["quantity"] <= 0:
                del self.inventory["potion_revive"]
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

                # 处理临时效果 - 使用新的模板化方法
                if item.usage_effect.temp_effects:
                    temp_effect_descriptions = self.apply_temp_effects_from_item(
                        item_id, item.usage_effect.temp_effects
                    )
                    effect_description.extend(temp_effect_descriptions)
                
                # Apply stat changes
                for stat, value in item.usage_effect.stat_changes.items():
                    if hasattr(self, stat):
                        old_value = getattr(self, stat)
                        setattr(self, stat, old_value + value)
                        
                        # 获取效果描述
                        description = item.usage_effect.effect_descriptions.get(stat)
                        if description:
                            effect_description.append(description.format(value=value))
                        self.update_stats()

                # Apply rng stat changes
                if getattr(item.usage_effect, 'stat_changes_rng', None):
                    for stat, rng in item.usage_effect.stat_changes_rng.items():
                        if not hasattr(self, stat):
                            continue
                        try:
                            low, high = int(rng[0]), int(rng[1])
                        except Exception:
                            continue
                        delta = random.randint(low, high)
                        setattr(self, stat, getattr(self, stat) + delta)
                        description = item.usage_effect.effect_descriptions.get(stat)
                        if description:
                            effect_description.append(description.format(value=delta))
                        self.update_stats()

                # 数据驱动：装备生成器（完全由 items.json 配置）
                if getattr(item.usage_effect, 'equipment_generators', None):
                    for rule in item.usage_effect.equipment_generators:
                        count = int(rule.get('count', 1))
                        chance = float(rule.get('chance', 1.0))
                        awarded = 0
                        for _ in range(count):
                            if random.random() <= chance:
                                if self._apply_equipment_generator_rule(rule):
                                    awarded += 1
                        if awarded > 0:
                            effect_description.append(f"获得装备x{awarded}")

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
                            item_id_reward = item_info["item_id"]
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
                                handled = handle_reward(self, item_id_reward, total_count)
                                if handled:
                                    items_gained.extend(handled)
                                else:
                                    items_gained.append(f"{Item.load_items()[item_id_reward].name}x{total_count}")
                                    for _ in range(total_count):
                                        self.add_item(item_id_reward)
                    
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

    def _apply_equipment_generator_rule(self, rule: dict) -> bool:
        from models.equipment import Equipment
        import json as _json
        # 构造模板池
        with open("data/equipment_templates.json", "r", encoding="utf-8") as f:
            templates = _json.load(f)
        explicit_ids = rule.get('template_ids') or []
        pool = []
        if explicit_ids:
            pool = [tid for tid in explicit_ids if tid in templates]
        else:
            level_min = int(rule.get('level_min', 1))
            level_max = int(rule.get('level_max', 999))
            slots = set(rule.get('slots', [])) if rule.get('slots') else None
            slot_prefixes = rule.get('slot_prefixes', []) or []
            class_required = rule.get('class_required')  # 单值或数组
            class_set = set(class_required) if isinstance(class_required, list) else ({class_required} if class_required else None)
            include_artifact = rule.get('include_artifact', True)
            exclude_artifact = rule.get('exclude_artifact', False)
            for tid, t in templates.items():
                lv = t.get('level_required', 1)
                if lv < level_min or lv > level_max:
                    continue
                slot_val = t.get('slot')
                if slots and slot_val not in slots:
                    continue
                if slot_prefixes and not any(str(slot_val).startswith(pref) for pref in slot_prefixes):
                    continue
                if class_set is not None:
                    tpl_cls = t.get('class_required')
                    if isinstance(tpl_cls, list):
                        if not (set(tpl_cls) & class_set):
                            continue
                    else:
                        if tpl_cls not in class_set:
                            continue
                is_art = t.get('is_artifact', False)
                if exclude_artifact and is_art:
                    continue
                if not include_artifact and is_art:
                    continue
                pool.append(tid)
        if not pool:
            return False
        # 生成
        rarity_weights = rule.get('rarity_weights')
        star_range = None
        if 'star_range' in rule and isinstance(rule['star_range'], list) and len(rule['star_range']) == 2:
            star_range = (int(rule['star_range'][0]), int(rule['star_range'][1]))
        star_weights = rule.get('star_weights')
        template_weights = rule.get('template_weights')
        roll = EquipmentGenerator.generate_from_pool(
            source=EquipmentSource.CHEST,
            template_pool=pool,
            template_weights=template_weights,
            template_loader=Equipment.load_template,
            rarity_weights=rarity_weights,
            star_range=star_range,
            star_weights=star_weights,
        )
        if not roll:
            return False
        equip = Equipment(roll['template_id'], roll['rarity'], roll['stars'])
        new_id = f"equipment_{int(time.time())}_{random.randint(1000, 9999)}"
        self.inventory[new_id] = equip.to_dict()
        # 系统广播：开出神器
        if equip.rarity == "神器":
            broadcast_system(f"恭喜{self.name}开启礼盒获得神器{equip.name}")
        return True

    def _grant_random_equipment_lv1(self, weapon_only: bool):
        from models.equipment import Equipment
        # 选取1级模板池
        from models.equipment import Equipment as _E
        import json as _json
        with open("data/equipment_templates.json", "r", encoding="utf-8") as f:
            templates = _json.load(f)
        pool = []
        for tid, t in templates.items():
            if t.get("level_required", 1) == 1 and not t.get("is_artifact", False):
                if weapon_only and t.get("slot") != "weapon":
                    continue
                pool.append(tid)
        if not pool:
            return False
        roll = EquipmentGenerator.generate_from_pool(
            source=EquipmentSource.CHEST,
            template_pool=pool,
            template_weights=None,
            template_loader=Equipment.load_template,
            rarity_weights={"普通": 0.7, "精良": 0.2, "卓越": 0.09, "史诗": 0.01},
            star_weights={1: 0.35, 2: 0.35, 3: 0.2, 4: 0.08, 5: 0.02}
        )
        if not roll:
            return False
        equip = Equipment(roll["template_id"], roll["rarity"], roll["stars"])
        new_id = f"equipment_{int(time.time())}_{random.randint(1000, 9999)}"
        self.inventory[new_id] = equip.to_dict()
        return True

    def _grant_artifact_lv1(self):
        from models.equipment import Equipment
        roll = EquipmentGenerator.generate(
            source=EquipmentSource.EVENT,
            template_id="artifact_all_class_lv1",
            template_loader=Equipment.load_template,
        )
        equip = Equipment(roll["template_id"], roll["rarity"], roll["stars"])
        new_id = f"equipment_{int(time.time())}_{random.randint(1000, 9999)}"
        self.inventory[new_id] = equip.to_dict()
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





class PlayerModel(db.Model):
    __tablename__ = 'players'

    username = db.Column(db.String(64), primary_key=True)
    player_data = db.Column(db.Text, nullable=False)
    last_login = db.Column(db.DateTime, default=_dt.utcnow)

    # Flask-Login 兼容（若未来使用）
    def get_id(self):
        return self.username

    @property
    def data(self):
        return _json.loads(self.player_data)

    @data.setter
    def data(self, value):
        self.player_data = _json.dumps(value, ensure_ascii=False)
