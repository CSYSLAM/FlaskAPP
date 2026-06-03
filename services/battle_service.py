import random
import time
from services import db
from services.data_service import DataService
from services.player_service import PlayerService
from models.player import PlayerModel, EquipmentInstance, InventoryItem, PlayerSkill
from models.monster import Monster
from models.lieutenant import Lieutenant


class BattleService:

    @classmethod
    def _get_deployed_lt(cls, player):
        """Get the deployed lieutenant for a player."""
        lt = Lieutenant.query.filter_by(owner_id=player.id, is_deployed=True).first()
        if lt and not lt.is_alive:
            from services.lieutenant_service import LieutenantService
            LieutenantService.revive(lt)
        return lt

    @classmethod
    def _lt_attack_monster(cls, lt, monster):
        """Lieutenant attacks monster. Returns damage dealt."""
        if not lt.is_alive or not lt.is_deployed:
            return 0
        lt_atk = lt.get_attack()
        if random.random() >= monster.dodge_rate:
            damage = max(1, lt_atk - monster.defense)
            return damage
        return 0

    @classmethod
    def _monster_attack_with_lt(cls, monster, player, lt):
        """Monster attacks, lieutenant absorbs if front position."""
        monster_damage = max(1, monster.attack - PlayerService.get_defense(player))
        is_crit = random.random() <= monster.crit_rate
        if is_crit:
            monster_damage = int(monster_damage * 1.5)

        if lt and lt.is_alive and lt.is_deployed and lt.position == 'front':
            # Front lieutenant absorbs monster damage first
            lt.current_health -= monster_damage
            monster.last_damage_dealt = f"{monster_damage}(副将承受)"
            monster.last_action = f"攻击了副将{lt.name}"
            if lt.current_health <= 0:
                from services.lieutenant_service import LieutenantService
                LieutenantService.handle_death(lt, owner_died=False)
                player.item_effect = f"副将{lt.name}阵亡！"
                # Remaining damage still hits player if lieutenant dies
                remaining = abs(lt.current_health)
                if remaining > 0:
                    player.health -= remaining
                    player.last_damage_taken = remaining
                    player.item_effect += f"溢出伤害{remaining}"
            else:
                player.last_damage_taken = 0
                player.item_effect = f"副将{lt.name}承受{monster_damage}伤害"
        else:
            # No front lieutenant, monster attacks player normally
            player.health -= monster_damage
            player.last_damage_taken = monster_damage
            if is_crit:
                monster.last_damage_dealt = f"{monster_damage}(暴击!)"
            else:
                monster.last_damage_dealt = str(monster_damage)
            monster.last_action = "攻击了你"

        # Check for lieutenant triggered skills (absorb/heal)
        if lt and lt.is_alive and lt.is_deployed:
            cls._process_lt_trigger_skills(lt, player, monster, monster_damage)

    @classmethod
    def _process_lt_trigger_skills(cls, lt, player, monster, damage_taken):
        """Process lieutenant triggered skills during combat."""
        for sk in lt.skills:
            if sk.get('type') != 'triggered':
                continue
            trigger_rate = sk.get('trigger_rate', 0) / 100.0
            if random.random() < trigger_rate:
                if sk.get('absorb_rate'):
                    absorb_pct = sk.get('absorb_rate', 0) / 100.0
                    absorbed = int(damage_taken * absorb_pct)
                    if absorbed > 0:
                        player.health += absorbed
                        player.item_effect += f"|{lt.name}{sk['name']}吸收{absorbed}"
                elif sk.get('heal_rate'):
                    heal_pct = sk.get('heal_rate', 0) / 100.0
                    max_hp = PlayerService.get_max_health(player)
                    heal_amount = int(max_hp * heal_pct)
                    if heal_amount > 0:
                        player.health = min(max_hp, player.health + heal_amount)
                        player.item_effect += f"|{lt.name}{sk['name']}回复{heal_amount}"

    @classmethod
    def start_pve(cls, player):
        if player.in_battle:
            return None, "你已经处于战斗中"

        location_data = DataService.get_locations().get(player.current_location, {})
        monster_ids = location_data.get("monsters", [])

        # Filter out NPCs (non-killable)
        all_monsters = DataService.get_monsters()
        killable_ids = [mid for mid in monster_ids
                        if all_monsters.get(mid, {}).get("killable", True)]
        if not killable_ids:
            return None, "这里没有怪物"

        monster_id = random.choice(killable_ids)
        monster = Monster.create_monster(monster_id)
        if not monster:
            return None, "怪物数据异常"

        player.in_battle = True
        player.last_battle_result = ""
        player.last_damage_taken = 0
        player.last_damage_dealt = ""
        player.last_action = ""
        player.item_effect = ""

        cls._save_encounter(player, monster)
        db.session.commit()
        return monster, None

    @classmethod
    def get_current_monster(cls, player):
        data = player.get_current_encounter_data()
        if not data:
            return None
        return Monster(data.get('monster_id'), data)

    @classmethod
    def _save_encounter(cls, player, monster):
        encounter = {
            'monster_id': monster.monster_id,
            'name': monster.name,
            'level': monster.level,
            'is_elite': monster.is_elite,
            'killable': monster.killable,
            'immortal': monster.immortal,
            'description': monster.description,
            'base_stats': {
                'current_health': monster.health,
                'health': monster.max_health,
                'max_health': monster.max_health,
                'mana': monster.mana,
                'max_mana': monster.max_mana,
                'attack': monster.attack,
                'defense': monster.defense,
                'crit_rate': monster.crit_rate,
                'dodge_rate': monster.dodge_rate,
            },
            'skills': monster.skills,
            'drops': monster.drops,
            'last_damage_taken': monster.last_damage_taken,
            'last_damage_dealt': monster.last_damage_dealt,
            'last_action': monster.last_action,
            'last_skill': monster.last_skill,
        }
        player.set_current_encounter_data(encounter)

    @classmethod
    def player_attack(cls, player):
        if not player.in_battle:
            return None, "你不在战斗中", None

        monster = cls.get_current_monster(player)
        if not monster:
            player.in_battle = False
            db.session.commit()
            return None, "没有怪物", None

        player.last_action = "使用了普通攻击"
        player.last_skill = "普通攻击"
        player.last_mana_cost = 0
        player.item_effect = ""

        if random.random() >= monster.dodge_rate:
            player_atk = PlayerService.get_attack(player)
            damage = max(1, player_atk - monster.defense)
            is_crit = random.random() <= player.crit_rate
            if is_crit:
                damage = int(damage * 1.5)
                player.last_damage_dealt = f"{damage}(暴击!)"
            else:
                player.last_damage_dealt = str(damage)
            monster.health -= damage
            monster.last_damage_taken = damage
        else:
            damage = 0
            player.last_damage_dealt = "闪避"
            monster.last_damage_taken = 0

        # Lieutenant also attacks
        lt = cls._get_deployed_lt(player)
        if lt and lt.is_alive:
            lt_damage = cls._lt_attack_monster(lt, monster)
            if lt_damage > 0:
                monster.health -= lt_damage
                player.last_damage_dealt += f"+副将{lt_damage}"
                monster.last_damage_taken += lt_damage

        cls._save_encounter(player, monster)

        if monster.health <= 0:
            result = cls._handle_monster_defeat(player, monster)
            db.session.commit()
            return monster, None, result

        # Monster attacks, lieutenant absorbs if front
        cls._monster_attack_with_lt(monster, player, lt)
        cls._save_encounter(player, monster)

        if player.health <= 0:
            player.health = 0
            player.in_battle = False
            player.last_battle_result = "你被击败了..."
            player.current_encounter = None
            # Lieutenant loses loyalty/lifespan when owner dies
            if lt and lt.is_alive:
                from services.lieutenant_service import LieutenantService
                LieutenantService.handle_death(lt, owner_died=True)
            db.session.commit()
            return monster, None, "你被击败了"

        db.session.commit()
        return monster, None, None

    @classmethod
    def use_skill(cls, player, skill_id):
        if not player.in_battle:
            return None, "你不在战斗中", None

        monster = cls.get_current_monster(player)
        if not monster:
            player.in_battle = False
            db.session.commit()
            return None, "没有怪物", None

        skill_data = DataService.get_skill(skill_id)
        if not skill_data:
            return monster, "技能不存在", None

        if skill_data.get('skill_type') != 'active':
            return monster, "被动技能无法在战斗中使用", None

        class_req = skill_data.get("class_required")
        if class_req and player.player_class != class_req:
            return monster, "职业不符", None

        ps = PlayerSkill.query.filter_by(
            player_id=player.id, skill_id=skill_id).first()
        if not ps:
            return monster, "你还没有学习这个技能", None

        skill_level = ps.skill_level
        base_mana = skill_data["base_mana_cost"]
        mana_per = skill_data.get("mana_cost_per_level", 0)
        mana_cost = base_mana + mana_per * (skill_level - 1)

        if player.mana < mana_cost:
            return monster, "魔法值不足", None

        player.mana -= mana_cost
        player.last_mana_cost = mana_cost
        player.last_action = f"使用了{skill_data['name']}"
        player.last_skill = skill_data["name"]
        player.item_effect = ""

        base_rate = skill_data["base_damage_rate"]
        rate_per = skill_data.get("damage_rate_per_level", 0)
        damage_rate = base_rate + rate_per * (skill_level - 1)

        hits = skill_data.get("hits", 1)
        total_damage = 0
        for _ in range(hits):
            if random.random() >= monster.dodge_rate:
                player_atk = PlayerService.get_attack(player)
                damage = max(1, int(player_atk * damage_rate) - monster.defense)
                if random.random() <= player.crit_rate:
                    damage = int(damage * 1.5)
                total_damage += damage
            else:
                total_damage += 0

        if hits > 1:
            player.last_damage_dealt = f"{total_damage}({hits}连击)"
        else:
            player.last_damage_dealt = str(total_damage)

        monster.health -= total_damage
        monster.last_damage_taken = total_damage

        # Lieutenant also attacks
        lt = cls._get_deployed_lt(player)
        if lt and lt.is_alive:
            lt_damage = cls._lt_attack_monster(lt, monster)
            if lt_damage > 0:
                monster.health -= lt_damage
                player.last_damage_dealt += f"+副将{lt_damage}"
                monster.last_damage_taken += lt_damage

        cls._save_encounter(player, monster)

        if monster.health <= 0:
            result = cls._handle_monster_defeat(player, monster)
            db.session.commit()
            return monster, None, result

        # Monster attacks, lieutenant absorbs if front
        cls._monster_attack_with_lt(monster, player, lt)
        cls._save_encounter(player, monster)

        if player.health <= 0:
            player.health = 0
            player.in_battle = False
            player.last_battle_result = "你被击败了..."
            player.current_encounter = None
            if lt and lt.is_alive:
                from services.lieutenant_service import LieutenantService
                LieutenantService.handle_death(lt, owner_died=True)
            db.session.commit()
            return monster, None, "你被击败了"

        db.session.commit()
        return monster, None, None

    @classmethod
    def _handle_monster_defeat(cls, player, monster):
        money = monster.get_money_drop()
        exp = monster.get_experience_drop()
        # VIP exp bonus
        from services.vip_service import VipService
        vip_exp_rate = VipService.get_exp_bonus_rate(player)
        if vip_exp_rate > 0:
            exp = int(exp * (1 + vip_exp_rate))
        player.gold += money
        player.gold_earned = (player.gold_earned or 0) + money
        PlayerService.gain_experience(player, exp)

        # Track kill counts
        if monster.is_elite:
            player.elite_kill_count = (player.elite_kill_count or 0) + 1
        else:
            player.kill_count = (player.kill_count or 0) + 1

        # Track daily kill count for diligence ranking
        from services.activity_service import ActivityService
        daily_kills = ActivityService.get_today_value(player, 'kill_count')
        ActivityService.set_today_value(player, 'kill_count', daily_kills + 1)

        loot = monster.get_loot()
        loot_text = ""
        is_bound = not monster.is_elite  # 普通怪掉绑定，精英掉非绑定
        if loot:
            if isinstance(loot, tuple) and loot[0] == "item":
                item_id = loot[1]
                DataService.add_item_to_inventory(player.id, item_id, is_bound=is_bound)
                item_data = DataService.get_item(item_id)
                item_name = item_data.get("name", item_id) if item_data else item_id
                bind_text = "(绑定)" if is_bound else ""
                loot_text = f"获得了 {item_name}{bind_text}"
            elif isinstance(loot, dict) and 'template_id' in loot:
                from services.equipment_service import EquipmentService
                equip = EquipmentService.generate_random_equipment(
                    player.id, loot['template_id'], loot['rarity'], loot['stars'])
                if equip:
                    equip.is_bound = is_bound
                    DataService.add_item_to_inventory(player.id, equip.instance_id)
                    bind_text = "(绑定)" if is_bound else ""
                    loot_text = f"获得了装备 {equip.name}{bind_text}"

        player.in_battle = False
        player.last_battle_result = f"击败了{monster.name}！获得 {money} 金币, {exp} 经验"
        if loot_text:
            player.last_battle_result += f"。{loot_text}"
        player.current_encounter = None
        monster.reset_health()

        from services.achievement_service import AchievementService
        ctype = 'elite_kill' if monster.is_elite else 'kill'
        AchievementService.check(player, ctype, player.elite_kill_count if monster.is_elite else player.kill_count)
        AchievementService.check(player, 'gold_earned', player.gold_earned)

        return player.last_battle_result

    @classmethod
    def flee(cls, player):
        if not player.in_battle:
            return False, "你不在战斗中"

        monster = cls.get_current_monster(player)
        flee_rate = 0.5
        if monster and monster.is_elite:
            flee_rate = 0.3

        if random.random() < flee_rate:
            player.in_battle = False
            player.last_battle_result = "成功逃离了战斗"
            player.current_encounter = None
            db.session.commit()
            return True, "成功逃离"
        else:
            if monster:
                monster.attack_player(player)
                cls._save_encounter(player, monster)
                if player.health <= 0:
                    player.health = 0
                    player.in_battle = False
                    player.last_battle_result = "逃跑失败，被击败了"
                    player.current_encounter = None
                    db.session.commit()
                    return False, "逃跑失败，被击败了"
            db.session.commit()
            return False, "逃跑失败"

    @classmethod
    def start_pk(cls, player, target):
        if player.in_battle or player.in_pk:
            return False, "你已在战斗中"
        if target.in_battle or target.in_pk:
            return False, "对方已在战斗中"

        player.in_pk = True
        player.pk_opponent = target.username
        target.in_pk = True
        target.pk_opponent = player.username
        db.session.commit()
        return True, None

    @classmethod
    def pk_attack(cls, attacker, defender):
        if not attacker.in_pk or attacker.pk_opponent != defender.username:
            return None, "PK状态异常"

        atk_power = PlayerService.get_attack(attacker)
        def_power = PlayerService.get_defense(defender)

        if random.random() >= defender.dodge_rate:
            damage = max(1, atk_power - def_power)
            is_crit = random.random() <= attacker.crit_rate
            if is_crit:
                damage = int(damage * 1.5)
                attacker.last_damage_dealt = f"{damage}(暴击!)"
            else:
                attacker.last_damage_dealt = str(damage)
            defender.health -= damage
            defender.last_damage_taken = damage
        else:
            damage = 0
            attacker.last_damage_dealt = "闪避"
            defender.last_damage_taken = 0

        attacker.last_action = "使用了普通攻击"
        attacker.last_skill = "普通攻击"

        if defender.health <= 0:
            defender.health = 0
            result = cls._handle_pk_defeat(attacker, defender)
            return result, None

        db.session.commit()
        return None, None

    @classmethod
    def pk_use_skill(cls, attacker, defender, skill_id):
        if not attacker.in_pk or attacker.pk_opponent != defender.username:
            return None, "PK状态异常"

        skill_data = DataService.get_skill(skill_id)
        if not skill_data:
            return None, "技能不存在"

        if skill_data.get('skill_type') != 'active':
            return None, "被动技能无法在PK中使用"

        ps = PlayerSkill.query.filter_by(
            player_id=attacker.id, skill_id=skill_id).first()
        if not ps:
            return None, "未学习该技能"

        mana_cost = skill_data["base_mana_cost"] + skill_data.get("mana_cost_per_level", 0) * (ps.skill_level - 1)
        if attacker.mana < mana_cost:
            return None, "魔法不足"

        attacker.mana -= mana_cost
        attacker.last_mana_cost = mana_cost
        attacker.last_action = f"使用了{skill_data['name']}"
        attacker.last_skill = skill_data["name"]

        damage_rate = skill_data["base_damage_rate"] + skill_data.get("damage_rate_per_level", 0) * (ps.skill_level - 1)
        hits = skill_data.get("hits", 1)
        total_damage = 0

        for _ in range(hits):
            atk_power = PlayerService.get_attack(attacker)
            def_power = PlayerService.get_defense(defender)
            if random.random() >= defender.dodge_rate:
                damage = max(1, int(atk_power * damage_rate) - def_power)
                if random.random() <= attacker.crit_rate:
                    damage = int(damage * 1.5)
                total_damage += damage
            else:
                total_damage += 0

        if hits > 1:
            attacker.last_damage_dealt = f"{total_damage}({hits}连击)"
        else:
            attacker.last_damage_dealt = str(total_damage)

        defender.health -= total_damage
        defender.last_damage_taken = total_damage

        if defender.health <= 0:
            defender.health = 0
            result = cls._handle_pk_defeat(attacker, defender)
            return result, None

        db.session.commit()
        return None, None

    @classmethod
    def _handle_pk_defeat(cls, attacker, defender):
        """Handle PK defeat: drops, enemy list, revive state."""
        same_country = attacker.country == defender.country

        # Attacker gains honor, defender loses (only if different country)
        honor_gained = 0
        if not same_country and defender.honor > 0:
            honor_gained = min(10, defender.honor)
            attacker.honor += honor_gained
            defender.honor = max(0, defender.honor - random.randint(3, 8))

        attacker.pk_win_count = (attacker.pk_win_count or 0) + 1
        PlayerService.update_military_rank(attacker)
        PlayerService.update_military_rank(defender)

        # Calculate drops
        drop_gold = random.randint(defender.level * 10, defender.level * 50)
        drop_gold = min(drop_gold, defender.gold)

        drop_honor = 0
        if not same_country:
            drop_honor = random.randint(1, 5)
            drop_honor = min(drop_honor, defender.honor)

        # Find non-bound equipment to drop
        drop_equipment = None
        from models.player import InventoryItem
        equip_items = InventoryItem.query.filter_by(
            player_id=defender.id, is_bound=False).all()
        equip_items = [e for e in equip_items if e.equipment_instance_id]
        if equip_items and random.random() < 0.3:  # 30% chance to drop equipment
            drop_item = random.choice(equip_items)
            from models.player import EquipmentInstance
            drop_equipment = EquipmentInstance.query.get(drop_item.equipment_instance_id)

        # Apply drops
        drop_msg = ""
        if drop_gold > 0:
            defender.gold -= drop_gold
            attacker.gold += drop_gold
            drop_msg += f"{drop_gold}银两 "
        if drop_honor > 0:
            defender.honor -= drop_honor
            attacker.honor += drop_honor
            drop_msg += f"{drop_honor}荣誉 "
        if drop_equipment:
            DataService.remove_item_from_inventory(defender.id, drop_equipment.instance_id, 1, is_bound=False)
            DataService.add_item_to_inventory(attacker.id, drop_equipment.instance_id)
            drop_msg += f"{drop_equipment.name} "

        # Add to enemy list (only if different country)
        if not same_country:
            defender.add_enemy(attacker.username)

        # Set revive state
        defender.need_revive = True
        defender.killed_by = attacker.username

        # Set attacker's last battle result
        result_msg = f"你击杀了{defender.nickname}！"
        if honor_gained > 0:
            result_msg += f"获得{honor_gained}荣誉"
        if drop_msg:
            result_msg += f"，掉落:{drop_msg}"
        attacker.last_battle_result = result_msg

        defender.last_battle_result = f"你被{attacker.nickname}击杀了！"

        cls._end_pk(attacker, defender)
        db.session.commit()

        from services.achievement_service import AchievementService
        AchievementService.check(attacker, 'pk_win', attacker.pk_win_count)

        return attacker.last_battle_result

    @classmethod
    def _end_pk(cls, player1, player2):
        player1.in_pk = False
        player1.pk_opponent = None
        player2.in_pk = False
        player2.pk_opponent = None