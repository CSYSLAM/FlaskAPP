import random
import time
from services import db
from services.data_service import DataService
from services.player_service import PlayerService
from services.world_boss_service import WorldBossService
from services.copy_dungeon_service import CopyDungeonService
from services.one_time_elite_service import OneTimeEliteService
from models.player import PlayerModel, EquipmentInstance, InventoryItem, PlayerSkill
from models.monster import Monster
from models.lieutenant import Lieutenant


class BattleService:

    # ----- Core damage formula & battle status effects -----

    # 技能特殊效果配置：skill_id -> {effect: {...}}
    # 状态效果以「剩余回合数」计，存于：
    #   - 玩家身上：PlayerModel.status_confuse_rounds / status_silence_rounds
    #   - 怪物身上：encounter['monster_status'] = {bleed: {rounds, value}, ...}
    #   - PK 双方：PlayerModel 同上（PK 期间也走玩家状态列）

    # 伤害公式（统一）：
    #   damage = atk × (1 + atk / max(1, def)) × coefficient
    # 暴击 ×1.5，闪避归零。def 用 max(1, def) 防除零。
    # min_damage 为保底（仅怪物打玩家保留等级保底）。
    @classmethod
    def _compute_damage(cls, atk, defense, coefficient=1.0, min_damage=0):
        def_eff = max(1, defense)
        raw = atk * (1.0 + atk / def_eff) * coefficient
        damage = max(min_damage, int(raw))
        return max(1, damage) if min_damage == 0 else max(min_damage, damage)

    # ---- 玩家状态效果 helpers ----
    @classmethod
    def _player_is_confused(cls, player):
        return (player.status_confuse_rounds or 0) > 0

    @classmethod
    def _player_is_silenced(cls, player):
        return (player.status_silence_rounds or 0) > 0

    @classmethod
    def _tick_player_status(cls, player):
        """回合结束时把玩家身上的状态回合数 -1（不低于 0）。流血单独由 _tick_pk_bleed 结算后递减。"""
        if player.status_confuse_rounds and player.status_confuse_rounds > 0:
            player.status_confuse_rounds -= 1
        if player.status_silence_rounds and player.status_silence_rounds > 0:
            player.status_silence_rounds -= 1

    @classmethod
    def _tick_lt_status(cls, player):
        """回合结束递减副将战斗状态：猛击防减半回合数 -1；护盾本回合清空。"""
        lt_status = cls._get_lt_status(player)
        changed = False
        if lt_status.get('def_debuff_rounds', 0) > 0:
            lt_status['def_debuff_rounds'] -= 1
            if lt_status['def_debuff_rounds'] <= 0:
                lt_status.pop('def_debuff_rounds', None)
            changed = True
        if 'atk_buff_rounds' in lt_status:
            lt_status.pop('atk_buff_rounds', None)
            changed = True
        if 'shield' in lt_status:
            lt_status.pop('shield', None)
            changed = True
        if changed:
            cls._set_lt_status(player, lt_status)

    @classmethod
    def _tick_pk_bleed(cls, p1, p2):
        """PK 回合结算：双方若有流血，扣血并递减回合。返回扣血信息写入 last_action 由调用方处理。"""
        for p in (p1, p2):
            if p.status_bleed_rounds and p.status_bleed_rounds > 0:
                val = p.status_bleed_value or 0
                if val > 0:
                    p.health -= val
                    p.last_damage_taken = (p.last_damage_taken or 0) + val
                p.status_bleed_rounds -= 1
                if p.status_bleed_rounds <= 0:
                    p.status_bleed_value = 0

    # ---- 怪物状态效果 helpers（存于 encounter JSON）----
    @classmethod
    def _get_monster_status(cls, player):
        data = player.get_current_encounter_data() or {}
        return data.get('monster_status', {}) or {}

    @classmethod
    def _set_monster_status(cls, player, status):
        data = player.get_current_encounter_data() or {}
        data['monster_status'] = status or {}
        player.set_current_encounter_data(data)

    # ---- 副将战斗状态 helpers（存于 encounter JSON 的 lt_status）----
    # 存：atk_buff_rounds(猛击本回合攻+50%,1回合)、def_debuff_rounds(猛击自身防减半,2回合)、shield(法相护盾,本回合)
    @classmethod
    def _get_lt_status(cls, player):
        data = player.get_current_encounter_data() or {}
        return data.get('lt_status', {}) or {}

    @classmethod
    def _set_lt_status(cls, player, status):
        data = player.get_current_encounter_data() or {}
        data['lt_status'] = status or {}
        player.set_current_encounter_data(data)

    @classmethod
    def _tick_monster_status(cls, player, monster):
        """回合结束时递减怪物身上的流血等状态，并即时结算流血伤害。"""
        status = cls._get_monster_status(player)
        bleed = status.get('bleed')
        msgs = []
        if bleed and bleed.get('rounds', 0) > 0:
            value = bleed.get('value', 0)
            if value > 0:
                monster.health -= value
                monster.last_damage_taken = (monster.last_damage_taken or 0) + value
                msgs.append(f"*『{monster.name}』流血损失{value}生命.")
            bleed['rounds'] -= 1
            if bleed['rounds'] <= 0:
                status.pop('bleed', None)
            else:
                status['bleed'] = bleed
        cls._set_monster_status(player, status)
        return msgs

    # ---- 技能特殊效果应用 ----
    # skill_data 中 effect_type 标识效果，命中后按概率触发：
    #   confuse(混乱3回合,受击伤害减半) / silence(封魔3回合)
    #   bleed(流血:额外造成atk×20%×3回合) / lifesteal(吸血15%)
    #   pierce(无视10%防御)
    @classmethod
    def _apply_skill_effect(cls, skill_data, attacker_atk, damage_dealt, target_player=None,
                            target_monster=None, player=None):
        """技能命中后施加特殊效果。返回 (extra_msg, heal_amount)。"""
        extra_msg = ""
        heal_amount = 0
        effect_type = skill_data.get('effect_type')
        effect_chance = skill_data.get('effect_chance', 0.0)
        if effect_type and random.random() < effect_chance:
            if effect_type == 'confuse':
                rounds = skill_data.get('effect_rounds', 3)
                if target_player is not None:
                    target_player.status_confuse_rounds = rounds
                    extra_msg = f"使{target_player.name}混乱{rounds}回合"
                elif target_monster is not None:
                    # 怪物混乱：存入 encounter，混乱期间怪物受击伤害减半
                    status = cls._get_monster_status(player)
                    status['confuse'] = rounds
                    cls._set_monster_status(player, status)
                    extra_msg = f"使{target_monster.name}混乱{rounds}回合"
            elif effect_type == 'silence':
                rounds = skill_data.get('effect_rounds', 3)
                if target_player is not None:
                    target_player.status_silence_rounds = rounds
                    extra_msg = f"封印{target_player.name}法力{rounds}回合"
                elif target_monster is not None:
                    status = cls._get_monster_status(player)
                    status['silence'] = rounds
                    cls._set_monster_status(player, status)
                    extra_msg = f"封印{target_monster.name}法力{rounds}回合"
            elif effect_type == 'bleed':
                rounds = skill_data.get('effect_rounds', 3)
                bleed_pct = skill_data.get('effect_value', 0.20)
                bleed_value = int(attacker_atk * bleed_pct)
                if bleed_value > 0 and target_monster is not None:
                    status = cls._get_monster_status(player)
                    status['bleed'] = {'rounds': rounds, 'value': bleed_value}
                    cls._set_monster_status(player, status)
                    extra_msg = f"使{target_monster.name}流血({bleed_value}/回合×{rounds})"
                elif bleed_value > 0 and target_player is not None:
                    # PK 流血：直接用玩家状态列存数值
                    target_player.status_bleed_rounds = rounds
                    target_player.status_bleed_value = bleed_value
                    extra_msg = f"使{target_player.name}流血({bleed_value}/回合×{rounds})"
            elif effect_type == 'lifesteal':
                # 吸血：即时结算（无需回合递减）
                lifesteal_pct = skill_data.get('effect_value', 0.15)
                heal_amount = int(damage_dealt * lifesteal_pct)
                extra_msg = f"汲取{heal_amount}生命"
        return extra_msg, heal_amount

    @classmethod
    def _get_deployed_lt(cls, player):
        """Get the deployed lieutenant for a player."""
        lt = Lieutenant.query.filter_by(owner_id=player.id, is_deployed=True).first()
        if lt and not lt.is_alive:
            from services.lieutenant_service import LieutenantService
            LieutenantService.revive(lt)
        return lt

    @classmethod
    def _lt_attack_monster(cls, lt, monster, player=None):
        """Lieutenant attacks monster. Returns (damage, skill_name|None).
        主动技能按 trigger_rate 概率释放，消耗 lt.current_mana；蓝量不足则降级为普攻。
        伤害一律走 _compute_damage 统一公式。player 用于读写 lt_status(猛击buff/护盾)。"""
        if not lt.is_alive or not lt.is_deployed:
            return 0, None
        if lt.current_mana <= 0:
            lt.current_mana = 0
        lt_atk = lt.get_attack()
        lt_status = cls._get_lt_status(player) if player else {}

        # 猛击：本回合攻+50%(atk_buff_rounds>0 表示本回合猛击生效)
        if lt_status.get('atk_buff_rounds', 0) > 0:
            lt_atk = int(lt_atk * 1.5)

        # 选一个可放的主动技能(按 trigger_rate 随机)
        active_skill = None
        for sk in lt.skills:
            if sk.get('type') != 'active':
                continue
            trigger_rate = sk.get('trigger_rate', 0) / 100.0
            if random.random() < trigger_rate:
                # 蓝量检查：不够则跳过此技能(继续找下一个或降级普攻)
                if lt.current_mana >= sk.get('mana_cost', 0):
                    active_skill = sk
                    break

        # 闪避判定(普攻/技能都吃怪物闪避)
        if random.random() < monster.dodge_rate:
            return 0, None

        if not active_skill:
            # 普攻
            damage = cls._compute_damage(lt_atk, monster.defense, coefficient=1.0)
            return damage, None

        # 释放主动技能：扣蓝
        lt.current_mana = max(0, lt.current_mana - active_skill.get('mana_cost', 0))
        skill_name = active_skill.get('name')
        sid = active_skill.get('id')

        if sid == 'combo':
            # 连击：打两次，每次独立计算(系数用 damage_rate，默认1.0即与普攻同)
            coef = active_skill.get('damage_rate', 1.0)
            d1 = cls._compute_damage(lt_atk, monster.defense, coefficient=coef)
            d2 = cls._compute_damage(lt_atk, monster.defense, coefficient=coef)
            return d1 + d2, skill_name
        elif sid == 'smash':
            # 猛击：本回合攻已+50%(上面已乘)，造成 damage_rate 倍伤害，并设自身防减半2回合
            coef = active_skill.get('damage_rate', 1.2)
            damage = cls._compute_damage(lt_atk, monster.defense, coefficient=coef)
            if player:
                lt_status['atk_buff_rounds'] = 0  # 本回合用完即消
                lt_status['def_debuff_rounds'] = active_skill.get('def_debuff_rounds', 2)
                cls._set_lt_status(player, lt_status)
            return damage, skill_name
        elif sid == 'thunder':
            # 天雷：消耗大量蓝(已扣)，巨额伤害
            coef = active_skill.get('damage_rate', 2.0)
            damage = cls._compute_damage(lt_atk, monster.defense, coefficient=coef)
            return damage, skill_name
        else:
            # 兜底：其他主动技能按 damage_rate 一次
            coef = active_skill.get('damage_rate', 1.0)
            damage = cls._compute_damage(lt_atk, monster.defense, coefficient=coef)
            return damage, skill_name

    @classmethod
    def _lt_effective_defense(cls, lt, player):
        """副将当前防御(猛击 debuff 期间减半)。"""
        defense = lt.get_defense()
        if player:
            lt_status = cls._get_lt_status(player)
            if lt_status.get('def_debuff_rounds', 0) > 0:
                defense = defense // 2
        return defense

    @classmethod
    def _monster_attack_with_lt(cls, monster, player, lt):
        """Monster attacks, lieutenant absorbs if front position. Logs in reference format."""
        # 怪物若被混乱（玩家技能施加，存于 encounter.monster_status），本回合无法行动
        m_status = cls._get_monster_status(player)
        if m_status.get('confuse', 0) > 0:
            monster.last_skill = "混乱"
            monster.last_action = f"*『{monster.name}』处于混乱状态，无法行动."
            monster.last_damage_dealt = "0(混乱)"
            player.last_damage_taken = 0
            return

        min_damage = monster.level * 2 if monster.is_elite else monster.level
        monster_damage = cls._compute_damage(
            monster.attack, PlayerService.get_defense(player),
            coefficient=1.0, min_damage=min_damage)
        is_crit = random.random() <= monster.crit_rate
        dodge = random.random() <= player.dodge_rate
        if dodge:
            monster_damage = 0
        elif is_crit:
            monster_damage = int(monster_damage * 1.5)

        # 法相(术士触发技能)：主人受击前有几率生成护盾抵消伤害(护盾=主人当前魔法×rate)
        # 护盾存于 lt_status.shield，本回合有效；少了主人扣血，多了主人不扣且护盾消失。
        lt_status = cls._get_lt_status(player)
        if monster_damage > 0 and lt and lt.is_alive and lt.is_deployed:
            for sk in lt.skills:
                if sk.get('type') != 'triggered' or not sk.get('shield_rate'):
                    continue
                if random.random() < sk.get('trigger_rate', 0) / 100.0:
                    shield = int(player.mana * sk.get('shield_rate', 0))
                    if shield > 0:
                        lt_status['shield'] = shield
                        player.item_effect = (player.item_effect or "") + f"|{lt.name}{sk['name']}生成护盾{shield}"
                    break
            cls._set_lt_status(player, lt_status)

        # 护盾抵消伤害
        shield = lt_status.get('shield', 0)
        if shield > 0 and monster_damage > 0:
            absorbed = min(shield, monster_damage)
            monster_damage -= absorbed
            lt_status['shield'] = shield - absorbed
            if lt_status['shield'] <= 0:
                lt_status.pop('shield', None)
            cls._set_lt_status(player, lt_status)
            if monster_damage <= 0:
                player.item_effect = (player.item_effect or "") + f"|护盾抵消全部伤害"
            else:
                player.item_effect = (player.item_effect or "") + f"|护盾抵消{absorbed}"

        monster.last_skill = "普攻"
        if dodge:
            dmg_text = "0(闪避)"
        elif is_crit and monster_damage > 0:
            dmg_text = f"{monster_damage}(暴击)"
        elif monster_damage == 0 and shield > 0:
            dmg_text = f"0(护盾)"
        else:
            dmg_text = str(monster_damage)

        if lt and lt.is_alive and lt.is_deployed and lt.position == 'front':
            # 副将挡刀：剩余伤害打副将(猛击 debuff 期间副将防御减半)
            lt_def = cls._lt_effective_defense(lt, player)
            # 注：挡刀直接承受怪物原始伤害(monster_damage 已被护盾抵减过)
            lt.current_health -= monster_damage
            monster.last_action = f"*『{monster.name}』使出[普攻],『{lt.name}』受到{dmg_text}伤害."
            monster.last_damage_dealt = dmg_text
            player.last_damage_taken = 0
            if lt.current_health <= 0:
                from services.lieutenant_service import LieutenantService
                LieutenantService.handle_death(lt, owner_died=False)
                remaining = abs(lt.current_health)
                if remaining > 0:
                    player.health -= remaining
                    player.last_damage_taken = remaining
                    player.item_effect = f"副将{lt.name}阵亡！溢出{remaining}伤害"
            else:
                if not player.item_effect:
                    player.item_effect = ""
        else:
            player.health -= monster_damage
            player.last_damage_taken = monster_damage if not dodge else 0
            monster.last_action = f"*『{monster.name}』使出[普攻],『{player.name}』受到{dmg_text}伤害."
            monster.last_damage_dealt = dmg_text

        # Check for lieutenant triggered skills (absorb/heal) — 前后置都触发
        if lt and lt.is_alive and lt.is_deployed:
            cls._process_lt_trigger_skills(lt, player, monster, monster_damage)

    @classmethod
    def _process_lt_trigger_skills(cls, lt, player, monster, damage_taken):
        """Process lieutenant triggered skills during combat.
        法相(护盾)已在 _monster_attack_with_lt 抵伤害阶段处理，这里只处理吸收(刺客)/回春(战士)。
        前后置副将都可触发。"""
        for sk in lt.skills:
            if sk.get('type') != 'triggered':
                continue
            if sk.get('shield_rate'):
                continue  # 法相已在上游处理
            trigger_rate = sk.get('trigger_rate', 0) / 100.0
            if random.random() < trigger_rate:
                if sk.get('absorb_rate'):
                    absorb_pct = sk.get('absorb_rate', 0) / 100.0
                    absorbed = int(damage_taken * absorb_pct)
                    if absorbed > 0:
                        max_hp = PlayerService.get_max_health(player)
                        player.health = min(max_hp, player.health + absorbed)
                        player.item_effect = (player.item_effect or "") + f"|{lt.name}{sk['name']}吸收{absorbed}"
                elif sk.get('heal_rate'):
                    heal_pct = sk.get('heal_rate', 0) / 100.0
                    max_hp = PlayerService.get_max_health(player)
                    heal_amount = int(max_hp * heal_pct)
                    if heal_amount > 0:
                        player.health = min(max_hp, player.health + heal_amount)
                        player.item_effect = (player.item_effect or "") + f"|{lt.name}{sk['name']}回复{heal_amount}"

    @classmethod
    def start_pve(cls, player, monster_id=None):
        if player.in_battle:
            return None, "你已经处于战斗中"

        location_data = DataService.get_locations().get(player.current_location, {})
        monster_ids = location_data.get("monsters", [])

        # Filter out NPCs (non-killable)
        all_monsters = DataService.get_monsters()
        killable_ids = [mid for mid in monster_ids
                        if all_monsters.get(mid, {}).get("killable", True)
                        and CopyDungeonService.should_show_monster_in_scene(player, mid)
                        and OneTimeEliteService.should_show_in_scene(player, mid)]
        if not killable_ids and not monster_id:
            return None, "这里没有怪物"

        # Finance bandit: a bandit present at this location may be targeted (理财·劫匪, 世界BOSS)
        from services.finance_service import FinanceService
        if monster_id is None:
            # 副本地图内：优先重打“刚击杀的那只”常驻普通副本怪，其次取场景内任一常驻普通副本怪。
            if location_data.get('is_copy_map'):
                _ad = player.activity_data or {}
                last_copy = _ad.get('last_copy_kill')
                if last_copy and last_copy in killable_ids:
                    monster_id = last_copy
                elif killable_ids:
                    # 兜底：选场景内第一个非精英/非despawn的常驻副本怪
                    def _is_persistent_copy(mid):
                        md = all_monsters.get(mid, {})
                        return (md.get('is_copy') or md.get('copy_only')) \
                            and not md.get('is_elite') and not md.get('copy_final_boss') \
                            and not md.get('despawn_after_defeat')
                    _pool = [mid for mid in killable_ids if _is_persistent_copy(mid)]
                    monster_id = random.choice(_pool) if _pool else None
            if monster_id is None:
                # 非副本或副本内无常驻副本怪：随机遇怪，只能是本场景【常驻】的【普通】怪物。
                # 排除：精英/世界boss(需主动点链接挑战)、副本怪、以及非本场景常驻的刷新怪(如理财·劫匪)。
                def _is_resident_normal(mid):
                    md = all_monsters.get(mid, {})
                    if not md.get("killable", True):
                        return False
                    if md.get("is_elite") or md.get("is_divine_beast"):
                        return False
                    if md.get("is_copy") or md.get("copy_only"):
                        return False
                    if str(mid).startswith("bandit_") or md.get("is_bandit"):
                        return False
                    return True
                random_pool = [mid for mid in killable_ids if _is_resident_normal(mid)]
                monster_id = random.choice(random_pool) if random_pool else None
        else:
            # 指定怪物：劫匪需在该场景且在场，其它怪需属于该场景
            bandit_info = FinanceService.get_bandit_at_location(player.current_location)
            is_bandit = bandit_info and bandit_info[0] == monster_id
            if not is_bandit and monster_id not in killable_ids:
                return None, "该怪物不在此处"

        if not monster_id:
            return None, "这里没有怪物"
        monster_data = all_monsters.get(monster_id, {})
        is_elite = monster_data.get("is_elite", False)
        is_copy_monster = monster_data.get("is_copy") or monster_data.get("copy_only")
        is_one_time = monster_data.get("is_one_time_elite", False)

        # World boss check (one-time elites use personal full-HP fights, no respawn lock)
        if is_elite and not is_copy_monster and not is_one_time:
            remaining = WorldBossService.get_respawn_remaining(monster_id)
            if remaining > 0:
                return None, f"该怪物已被击杀，正在复活中（剩余{remaining}秒）"

        monster = Monster.create_monster(monster_id)
        if not monster:
            return None, "怪物数据异常"

        # World boss: use shared HP (copy dungeon elites & one-time elites are personal, not world bosses)
        if is_elite and not is_copy_monster and not is_one_time:
            boss = WorldBossService.get_boss(monster_id)
            if boss:
                monster.health = boss.current_health
                monster.max_health = boss.max_health

        player.in_battle = True
        player.last_battle_result = ""
        player.last_damage_taken = 0
        player.last_damage_dealt = ""
        player.last_action = ""
        player.item_effect = ""

        # 出战副将进场补满生命/魔法(每场战斗满状态开始)
        lt = cls._get_deployed_lt(player)
        if lt:
            lt.current_health = lt.get_max_health()
            lt.current_mana = lt.get_max_mana()

        cls._save_encounter(player, monster)
        db.session.commit()

        # Monster strikes first
        lt = cls._get_deployed_lt(player)
        cls._monster_attack_with_lt(monster, player, lt)
        cls._save_encounter(player, monster)
        if player.health <= 0:
            player.health = 0
            player.in_battle = False
            player.last_battle_result = "你被击败了..."
            player.current_encounter = None
            player.need_revive = True
            if lt and lt.is_alive:
                from services.lieutenant_service import LieutenantService
                LieutenantService.handle_death(lt, owner_died=True)
            db.session.commit()
            return None, "怪物先发制人，你被击败了"
        cls._apply_reserve_restore(player, monster)
        player.last_damage_taken = monster.last_damage_dealt or 0
        db.session.commit()
        return monster, None

    @classmethod
    def get_current_monster(cls, player):
        data = player.get_current_encounter_data()
        if not data:
            return None
        monster = Monster(data.get('monster_id'), data)
        # Sync world boss HP from shared state
        if data.get('is_world_boss'):
            boss = WorldBossService.get_boss(monster.monster_id)
            if boss:
                monster.health = boss.current_health
                monster.max_health = boss.max_health
        return monster

    @classmethod
    def _save_encounter(cls, player, monster):
        encounter = {
            'monster_id': monster.monster_id,
            'name': monster.name,
            'level': monster.level,
            'is_elite': monster.is_elite,
            'is_one_time_elite': getattr(monster, 'is_one_time_elite', False),
            'is_divine_beast': monster.is_divine_beast,
            'is_copy': getattr(monster, 'is_copy', False),
            'copy_only': getattr(monster, 'copy_only', False),
            'copy_dungeon_id': getattr(monster, 'copy_dungeon_id', None),
            'copy_stage': getattr(monster, 'copy_stage', None),
            'copy_role': getattr(monster, 'copy_role', None),
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
            'is_world_boss': monster.is_elite and not getattr(monster, 'is_copy', False) and not getattr(monster, 'is_one_time_elite', False),
            'guaranteed_items': getattr(monster, 'guaranteed_items', []),
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

        player.last_skill = "普攻"
        player.last_mana_cost = 0
        player.last_action = ""
        player.item_effect = ""
        player.last_hp_delta = 0
        player.last_mp_delta = 0

        encounter_data = player.get_current_encounter_data()

        # 玩家被混乱：无法普攻/技能/撤退，跳过本回合行动（怪物仍会反击）
        if cls._player_is_confused(player):
            player_log = f"*『{player.name}』处于混乱状态，无法行动"
            player.last_action = player_log
            player.last_damage_dealt = "0(混乱)"
            # 回合结算：递减玩家状态 + 怪物流血
            bleed_msgs = cls._tick_monster_status(player, monster)
            cls._tick_player_status(player)
            if bleed_msgs:
                player.item_effect = "".join(bleed_msgs)
            cls._save_encounter(player, monster)
            if monster.health <= 0:
                result = cls._handle_monster_defeat(player, monster)
                db.session.commit()
                return monster, None, result
            cls._monster_attack_with_lt(monster, player, lt)
            cls._save_encounter(player, monster)
            if player.health <= 0:
                player.health = 0
                player.in_battle = False
                player.last_battle_result = "你被击败了..."
                player.current_encounter = None
                player.need_revive = True
                db.session.commit()
                return monster, None, "你被击败了"
            db.session.commit()
            return monster, "混乱中，无法行动", None

        # Build battle log: player attack
        player_log = f"*『{player.name}』使出[普攻]"
        lt = cls._get_deployed_lt(player)
        lt_damage = 0
        # 怪物被混乱时，受到的攻击伤害减半
        m_status = cls._get_monster_status(player)
        monster_confused = m_status.get('confuse', 0) > 0
        if random.random() >= monster.dodge_rate:
            player_atk = PlayerService.get_attack(player)
            damage = cls._compute_damage(player_atk, monster.defense, coefficient=1.0)
            if monster_confused:
                damage = int(damage * 0.5)
            is_crit = random.random() <= player.crit_rate
            dmg_text = f"{damage}"
            if is_crit:
                damage = int(damage * 1.5)
                dmg_text = f"{damage}(暴击)"
            monster.health -= damage
            monster.last_damage_taken = damage
            if encounter_data.get('is_world_boss'):
                WorldBossService.damage_boss(monster.monster_id, player.id, damage)
            # Lieutenant also attacks
            if lt and lt.is_alive:
                lt_damage, lt_skill = cls._lt_attack_monster(lt, monster, player)
                if lt_damage > 0:
                    monster.health -= lt_damage
                    monster.last_damage_taken += lt_damage
                    player_log += f",『{lt.name}』使出[{lt_skill or '普攻'}]"
                    dmg_text += f"＋{lt_damage}"
                    if encounter_data.get('is_world_boss'):
                        WorldBossService.damage_boss(monster.monster_id, player.id, lt_damage)
            player_log += f",『{monster.name}』受到{dmg_text}伤害."
            player.last_damage_dealt = dmg_text
        else:
            damage = 0
            monster.last_damage_taken = 0
            if lt and lt.is_alive:
                lt_damage, lt_skill = cls._lt_attack_monster(lt, monster, player)
                if lt_damage > 0:
                    monster.health -= lt_damage
                    monster.last_damage_taken += lt_damage
                    player_log += f",『{lt.name}』使出[{lt_skill or '普攻'}]"
                    if encounter_data.get('is_world_boss'):
                        WorldBossService.damage_boss(monster.monster_id, player.id, lt_damage)
            player_log += f",『{monster.name}』受到0(闪避)伤害."
            player.last_damage_dealt = "0(闪避)"
        player.last_action = player_log

        cls._save_encounter(player, monster)

        if monster.health <= 0:
            result = cls._handle_monster_defeat(player, monster)
            db.session.commit()
            return monster, None, result

        # Monster attacks, lieutenant absorbs if front
        cls._monster_attack_with_lt(monster, player, lt)
        # 回合结算：递减玩家状态 + 怪物状态/流血
        bleed_msgs = cls._tick_monster_status(player, monster)
        cls._tick_player_status(player)
        cls._tick_lt_status(player)
        if bleed_msgs and not player.item_effect:
            player.item_effect = "".join(bleed_msgs)
        elif bleed_msgs:
            player.item_effect += "".join(bleed_msgs)
        cls._save_encounter(player, monster)

        if player.health <= 0:
            player.health = 0
            player.in_battle = False
            player.last_battle_result = "你被击败了..."
            player.current_encounter = None
            player.need_revive = True
            # Lieutenant loses loyalty/lifespan when owner dies
            if lt and lt.is_alive:
                from services.lieutenant_service import LieutenantService
                LieutenantService.handle_death(lt, owner_died=True)
            db.session.commit()
            return monster, None, "你被击败了"

        # 普攻回合净生命变化 = 怪物伤害(扣血为正); 储备回血由 _apply_reserve_restore 抵减
        player.last_hp_delta = player.last_damage_taken or 0
        cls._apply_reserve_restore(player, monster)
        db.session.commit()
        return monster, None, None

    @classmethod
    def _apply_reserve_restore(cls, player, monster):
        """Auto-restore HP/MP from reserve during battle."""
        result_parts = []
        # HP reserve
        if player.blood_reserve_enabled and player.blood_reserve > 0:
            max_hp = player.effective_max_health
            missing_hp = max_hp - player.health
            if missing_hp > 0:
                restore = min(missing_hp, player.blood_reserve)
                player.health += restore
                player.blood_reserve -= restore
                result_parts.append(f"*『{player.name}』生命储备回复{restore}")
                # 回血抵减本回合净扣血(回血取负)
                player.last_hp_delta = (player.last_hp_delta or 0) - restore
        # MP reserve
        if player.mana_reserve_enabled and player.mana_reserve > 0:
            max_mp = player.effective_max_mana
            missing_mp = max_mp - player.mana
            if missing_mp > 0:
                restore = min(missing_mp, player.mana_reserve)
                player.mana += restore
                player.mana_reserve -= restore
                result_parts.append(f"*『{player.name}』魔法储备回复{restore}")
                player.last_mp_delta = (player.last_mp_delta or 0) - restore
        if result_parts:
            player.item_effect = "、".join(result_parts)

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

        # 封魔状态：无法使用技能（可普攻/撤退）
        if cls._player_is_silenced(player):
            return monster, "被封印法力，无法使用技能", None

        # 混乱状态：无法使用技能
        if cls._player_is_confused(player):
            return monster, "混乱中，无法使用技能", None

        skill_level = ps.skill_level
        base_mana = skill_data["base_mana_cost"]
        mana_per = skill_data.get("mana_cost_per_level", 0)
        mana_cost = int(round(base_mana + mana_per * (skill_level - 1)))

        if player.mana < mana_cost:
            return monster, "魔法值不足", None

        player.mana -= mana_cost
        player.last_mana_cost = mana_cost
        skill_name = skill_data["name"]
        player.last_skill = skill_name
        player.item_effect = ""
        player.last_hp_delta = 0
        player.last_mp_delta = mana_cost  # 技能耗蓝(扣蓝为正)

        encounter_data = player.get_current_encounter_data()

        base_rate = skill_data["base_damage_rate"]
        rate_per = skill_data.get("damage_rate_per_level", 0)
        damage_rate = base_rate + rate_per * (skill_level - 1)

        # 破甲刺：无视目标 10% 防御
        pierce_pct = skill_data.get('pierce_defense_pct', 0)
        effective_def = monster.defense
        if pierce_pct > 0:
            effective_def = int(monster.defense * (1 - pierce_pct))
        # 怪物被混乱时受击伤害减半
        m_status = cls._get_monster_status(player)
        monster_confused = m_status.get('confuse', 0) > 0

        hits = skill_data.get("hits", 1)
        total_damage = 0
        dodge_all = True
        is_crit_hit = False
        hit_any = False
        for _ in range(hits):
            if random.random() >= monster.dodge_rate:
                dodge_all = False
                hit_any = True
                player_atk = PlayerService.get_attack(player)
                damage = cls._compute_damage(player_atk, effective_def, coefficient=damage_rate)
                if monster_confused:
                    damage = int(damage * 0.5)
                if random.random() <= player.crit_rate:
                    damage = int(damage * 1.5)
                    is_crit_hit = True
                total_damage += damage
            else:
                total_damage += 0

        # Build battle log in reference format
        if dodge_all:
            dmg_text = "0(闪避)"
        elif hits > 1:
            dmg_text = f"{total_damage}({hits}连击)"
        elif is_crit_hit:
            dmg_text = f"{total_damage}(暴击)"
        else:
            dmg_text = str(total_damage)

        monster.health -= total_damage
        monster.last_damage_taken = total_damage

        if encounter_data.get('is_world_boss'):
            killed, killer_id = WorldBossService.damage_boss(
                monster.monster_id, player.id, total_damage)
            if killed:
                monster.health = 0

        # 技能特殊效果（命中后才触发）
        effect_msg = ""
        heal_amount = 0
        if hit_any and total_damage > 0:
            player_atk_for_effect = PlayerService.get_attack(player)
            effect_msg, heal_amount = cls._apply_skill_effect(
                skill_data, player_atk_for_effect, total_damage,
                target_monster=monster, player=player)
            if heal_amount > 0:
                max_hp = player.effective_max_health
                player.health = min(max_hp, player.health + heal_amount)

        # Lieutenant also attacks
        lt = cls._get_deployed_lt(player)
        lt_damage = 0
        player_log = f"*『{player.name}』使出[{skill_name}]"
        if lt and lt.is_alive:
            lt_damage, lt_skill = cls._lt_attack_monster(lt, monster, player)
            if lt_damage > 0:
                monster.health -= lt_damage
                monster.last_damage_taken += lt_damage
                player_log += f",『{lt.name}』使出[{lt_skill or '普攻'}]"
                dmg_text += f"＋{lt_damage}"
                if encounter_data.get('is_world_boss'):
                    WorldBossService.damage_boss(monster.monster_id, player.id, lt_damage)
        player_log += f",『{monster.name}』受到{dmg_text}伤害."
        if effect_msg:
            player_log += f"[{effect_msg}]"
        player.last_action = player_log
        player.last_damage_dealt = dmg_text

        cls._save_encounter(player, monster)

        if monster.health <= 0:
            result = cls._handle_monster_defeat(player, monster)
            db.session.commit()
            return monster, None, result

        # Monster attacks, lieutenant absorbs if front
        cls._monster_attack_with_lt(monster, player, lt)
        # 回合结算：递减玩家状态 + 怪物状态/流血
        bleed_msgs = cls._tick_monster_status(player, monster)
        cls._tick_player_status(player)
        cls._tick_lt_status(player)
        if bleed_msgs:
            player.item_effect = (player.item_effect or "") + "".join(bleed_msgs)
        cls._save_encounter(player, monster)

        if player.health <= 0:
            player.health = 0
            player.in_battle = False
            player.last_battle_result = "你被击败了..."
            player.current_encounter = None
            player.need_revive = True
            if lt and lt.is_alive:
                from services.lieutenant_service import LieutenantService
                LieutenantService.handle_death(lt, owner_died=True)
            db.session.commit()
            return monster, None, "你被击败了"

        # 技能回合净生命变化 = 怪物伤害(扣血为正); 储备回血由 _apply_reserve_restore 抵减
        player.last_hp_delta = player.last_damage_taken or 0
        cls._apply_reserve_restore(player, monster)
        db.session.commit()
        return monster, None, None

    @classmethod
    def use_potion(cls, player, item_id):
        """战斗中使用药品——算作一个完整回合(玩家用药+怪物反击+状态结算)。

        与 player_attack/use_skill 对齐的回合结构，区别在于玩家动作改为使用药品
        (不造成伤害)，随后怪物正常反击。
        """
        if not player.in_battle:
            return None, "你不在战斗中", None

        monster = cls.get_current_monster(player)
        if not monster:
            player.in_battle = False
            db.session.commit()
            return None, "没有怪物", None

        # 混乱/封魔状态下仍可用药(药品非技能，混乱只封锁行动；保留用药以自救)

        from services.item_service import ItemService
        item_data = DataService.get_item(item_id)
        if not item_data:
            return monster, "物品数据异常", None
        if not item_data.get("is_usable", True):
            return monster, "该物品不可使用", None

        # 生命/魔法已满时用药纯属浪费，提前拦截(不消耗药品、不推进回合)
        _ue = item_data.get("usage_effect", {}) or {}
        _sc = list(_ue.get("stat_changes", {}).keys()) + list(_ue.get("stat_changes_rng", {}).keys())
        _restores = [s for s in _sc if s in ("health", "mana")]
        _has_other = any(s not in ("health", "mana") for s in _sc)
        if _restores and not _has_other:
            _full = True
            _mh = player.effective_max_health
            if "health" in _restores and _mh and player.health < _mh:
                _full = False
            _mm = player.effective_max_mana
            if "mana" in _restores and _mm and player.mana < _mm:
                _full = False
            if _full:
                return monster, "生命/魔法已满，无需使用药品", None

        hp_before = player.health
        mp_before = player.mana

        player.last_skill = "用药"
        player.last_mana_cost = 0
        player.last_action = ""
        player.item_effect = ""
        player.last_hp_delta = 0
        player.last_mp_delta = 0

        lt = cls._get_deployed_lt(player)

        # 玩家动作：使用药品(实际回血/回蓝/增益)
        success, msg = ItemService.use_item(player, item_id)
        potion_name = item_data.get("name", item_id)

        # 记录用药造成的回血/回蓝(扣血为正约定下，回血取负)
        heal = player.health - hp_before
        mana_restore = player.mana - mp_before

        if not success:
            player.last_action = f"*『{player.name}』使用[{potion_name}]失败:{msg}"
            db.session.commit()
            return monster, msg, None

        player_log = f"*『{player.name}』使用[{potion_name}]"
        if heal > 0:
            player_log += f",回复{heal}生命"
        if mana_restore > 0:
            player_log += f",回复{mana_restore}魔法"
        player.last_action = player_log

        cls._save_encounter(player, monster)

        if monster.health <= 0:
            result = cls._handle_monster_defeat(player, monster)
            db.session.commit()
            return monster, None, result

        # 怪物反击(副将挡刀/护盾/触发技同普攻回合)
        cls._monster_attack_with_lt(monster, player, lt)
        # 回合结算：递减玩家状态 + 怪物状态/流血
        bleed_msgs = cls._tick_monster_status(player, monster)
        cls._tick_player_status(player)
        cls._tick_lt_status(player)
        if bleed_msgs:
            player.item_effect = (player.item_effect or "") + "".join(bleed_msgs)

        # 本回合净生命变化 = 怪物伤害 - 用药回血(扣血为正, 回血取负); 储备回血由 _apply_reserve_restore 抵减
        player.last_hp_delta = (player.last_damage_taken or 0) - heal
        # 净魔法变化 = 用药回蓝(回蓝取负); 储备回蓝由 _apply_reserve_restore 抵减
        player.last_mp_delta = -mana_restore
        cls._save_encounter(player, monster)

        if player.health <= 0:
            player.health = 0
            player.in_battle = False
            player.last_battle_result = "你被击败了..."
            player.current_encounter = None
            player.need_revive = True
            if lt and lt.is_alive:
                from services.lieutenant_service import LieutenantService
                LieutenantService.handle_death(lt, owner_died=True)
            db.session.commit()
            return monster, None, "你被击败了"

        cls._apply_reserve_restore(player, monster)
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
        # TempEffect exp bonus (e.g. double_exp_card)
        from models.player import TempEffect
        import time as _time
        exp_effects = TempEffect.query.filter_by(player_id=player.id, stat='exp_rate').all()
        for te in exp_effects:
            if te.expire_time > _time.time() and te.rate > 0:
                exp = int(exp * (1 + te.rate))
        player.gold += money
        player.gold_earned = (player.gold_earned or 0) + money
        PlayerService.gain_experience(player, exp)

        # Lieutenant also gains experience from battle
        lt = Lieutenant.query.filter_by(owner_id=player.id, is_deployed=True).first()
        if lt and lt.current_health > 0:
            lt_exp = exp // 2
            if lt_exp > 0:
                from models.player import TempEffect
                import time as _time2
                lt_exp_effects = TempEffect.query.filter_by(player_id=player.id, stat='lt_exp_rate').all()
                for te in lt_exp_effects:
                    if te.expire_time > _time2.time() and te.rate > 0:
                        lt_exp = int(lt_exp * (1 + te.rate))
                from services.lieutenant_service import LieutenantService
                LieutenantService.gain_experience(lt, lt_exp)

        # Track kill counts
        if monster.is_elite:
            player.elite_kill_count = (player.elite_kill_count or 0) + 1
        else:
            player.kill_count = (player.kill_count or 0) + 1

        # Update quest kill progress and drop quest items
        from services.quest_service import QuestService
        quest_drops = []
        active = QuestService.get_active_quests(player)
        for qid, prog in active.items():
            q = QuestService.get_quest(qid)
            if not q:
                continue
            obj = q.get('objective', {})
            if obj.get('type') == 'collect_item' and obj.get('monster_name') == monster.name:
                item_id = obj.get('item_id', '')
                if item_id and prog.get('progress', 0) < prog.get('target', 1):
                    DataService.add_item_to_inventory(player.id, item_id, 1)
                    quest_drops.append(obj.get('item_name', item_id))
        QuestService.update_kill_progress(player, monster.name, quest_drops)

        # Track daily kill count for diligence ranking
        from services.activity_service import ActivityService
        daily_kills = ActivityService.get_today_value(player, 'kill_count')
        ActivityService.set_today_value(player, 'kill_count', daily_kills + 1)

        # Track daily NPC task kills
        ActivityService.record_daily_task_kill(player, monster.name)

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

        # Guaranteed item drops (always drop, independent of random loot)
        guaranteed_items = getattr(monster, 'guaranteed_items', [])
        if guaranteed_items:
            # 统计物品数量
            item_counts = {}
            for g_item_id in guaranteed_items:
                DataService.add_item_to_inventory(player.id, g_item_id, is_bound=False)
                g_item_data = DataService.get_item(g_item_id)
                g_name = g_item_data.get("name", g_item_id) if g_item_data else g_item_id
                item_counts[g_name] = item_counts.get(g_name, 0) + 1

            # 合并显示：物品名*数量
            guaranteed_names = []
            for g_name, count in item_counts.items():
                if count > 1:
                    guaranteed_names.append(f"{g_name}*{count}")
                else:
                    guaranteed_names.append(g_name)

            guaranteed_text = "、".join(guaranteed_names)
            if loot_text:
                loot_text += f"；{guaranteed_text}"
            else:
                loot_text = guaranteed_text

        dungeon_note = CopyDungeonService.record_monster_defeat(player, monster)
        if dungeon_note:
            if loot_text:
                loot_text += f"；{dungeon_note}"
            else:
                loot_text = dungeon_note

        # One-time elite: mark permanently defeated for this player (vanishes, no respawn)
        if getattr(monster, 'is_one_time_elite', False):
            OneTimeEliteService.record_kill(player, monster.monster_id)

        player.in_battle = False
        player.last_battle_result = f"击败了『{monster.name}』！获得{money}银两、{exp}经验"
        if loot_text:
            player.last_battle_result += f"。{loot_text}"
        # Show quest drops
        quest_drops_final = []
        for qid, prog in QuestService.get_active_quests(player).items():
            q = QuestService.get_quest(qid)
            if q and q.get('objective', {}).get('type') == 'collect_item':
                if q['objective'].get('monster_name') == monster.name:
                    quest_drops_final.append(q['objective'].get('item_name', ''))
        if quest_drops_final:
            player.last_battle_result += f"。任务掉落: {'、'.join(set(quest_drops_final))}"
        player.current_encounter = None
        # 记录本次击杀是否为精英/世界boss，供结算界面决定是否隐藏“继续挑战”
        _is_special_kill = (monster.is_elite or monster.is_divine_beast) and not getattr(monster, 'is_copy', False)
        _ad = player.activity_data
        _ad['last_kill_special'] = _is_special_kill
        # 副本内常驻普通怪击杀后记录其id，供“继续遇怪”重打刚死那只；
        # 精英/最终boss/despawn怪击杀后清空（它们击杀后消失，不能重打）
        _md = DataService.get_monster(monster.monster_id) or {}
        _is_persistent_copy_mob = (
            getattr(monster, 'is_copy', False)
            and not monster.is_elite
            and not _md.get('copy_final_boss')
            and not _md.get('despawn_after_defeat')
        )
        _ad['last_copy_kill'] = monster.monster_id if _is_persistent_copy_mob else None
        player.activity_data = _ad
        monster.reset_health()

        # Finance bandit kill: record to city ranking + points reward (理财·劫匪, 世界BOSS)
        if monster.monster_id and monster.monster_id.startswith("bandit_"):
            from services.finance_service import FinanceService, BANDIT_POINTS_PER_JINZU
            info = FinanceService.record_bandit_kill(monster.monster_id, player)
            if info:
                pts_msg = f"积分+{info['points']}（{info['total_points']}/{BANDIT_POINTS_PER_JINZU}）"
                if info['jinzu'] > 0:
                    pts_msg += f"，兑换金珠{info['jinzu']}枚"
                player.last_battle_result += f"。救济富商，{pts_msg}"

        # World boss: broadcast defeat via last_battle_result (one-time & copy elites are personal, skip)
        if monster.is_elite and not getattr(monster, 'is_copy', False) and not getattr(monster, 'is_one_time_elite', False):
            boss = WorldBossService.get_boss(monster.monster_id)
            if boss:
                player.last_battle_result += f" [世界BOSS已被击败，{boss.respawn_time}秒后复活]"

        # Divine beast: global kill announcement
        if monster.is_divine_beast:
            DataService.broadcast_system(f"{player.nickname}率先击杀了{monster.description}，各位承让承让！")

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
        if not monster:
            player.in_battle = False
            player.current_encounter = None
            db.session.commit()
            return True, "战斗已结束"

        flee_rate = 0.5
        if monster.is_elite:
            flee_rate = 0.3

        if random.random() < flee_rate:
            player.in_battle = False
            player.last_battle_result = "成功逃离了战斗"
            player.current_encounter = None
            db.session.commit()
            return True, "成功逃离"
        else:
            monster.attack_player(player)
            cls._save_encounter(player, monster)
            if player.health <= 0:
                player.health = 0
                player.in_battle = False
                player.last_battle_result = "逃跑失败，被击败了"
                player.current_encounter = None
                player.need_revive = True
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

        # 攻击方被混乱：无法行动
        if cls._player_is_confused(attacker):
            attacker.last_action = "混乱中，无法行动"
            attacker.last_skill = "混乱"
            attacker.last_damage_dealt = "0(混乱)"
            defender.last_damage_taken = 0
            # 回合结算：双方流血扣血 + 状态递减
            cls._tick_pk_bleed(attacker, defender)
            cls._tick_player_status(attacker)
            cls._tick_player_status(defender)
            if defender.health <= 0:
                defender.health = 0
                result = cls._handle_pk_defeat(attacker, defender)
                return result, None
            db.session.commit()
            return None, "混乱中，无法行动"

        atk_power = PlayerService.get_attack(attacker)
        def_power = PlayerService.get_defense(defender)

        if random.random() >= defender.dodge_rate:
            damage = cls._compute_damage(atk_power, def_power, coefficient=1.0)
            # 防守方被混乱：受击伤害减半
            if cls._player_is_confused(defender):
                damage = int(damage * 0.5)
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

        # 回合结算：双方流血扣血 + 状态递减
        cls._tick_pk_bleed(attacker, defender)

        if defender.health <= 0:
            defender.health = 0
            result = cls._handle_pk_defeat(attacker, defender)
            return result, None

        cls._tick_player_status(attacker)
        cls._tick_player_status(defender)
        db.session.commit()
        return None, None

    @classmethod
    def pk_use_skill(cls, attacker, defender, skill_id):
        if not attacker.in_pk or attacker.pk_opponent != defender.username:
            return None, "PK状态异常"

        # 攻击方被混乱/封魔：无法使用技能
        if cls._player_is_confused(attacker):
            return None, "混乱中，无法使用技能"
        if cls._player_is_silenced(attacker):
            return None, "被封印法力，无法使用技能"

        skill_data = DataService.get_skill(skill_id)
        if not skill_data:
            return None, "技能不存在"

        if skill_data.get('skill_type') != 'active':
            return None, "被动技能无法在PK中使用"

        ps = PlayerSkill.query.filter_by(
            player_id=attacker.id, skill_id=skill_id).first()
        if not ps:
            return None, "未学习该技能"

        mana_cost = int(round(skill_data["base_mana_cost"] + skill_data.get("mana_cost_per_level", 0) * (ps.skill_level - 1)))
        if attacker.mana < mana_cost:
            return None, "魔法不足"

        attacker.mana -= mana_cost
        attacker.last_mana_cost = mana_cost
        attacker.last_action = f"使用了{skill_data['name']}"
        attacker.last_skill = skill_data["name"]

        damage_rate = skill_data["base_damage_rate"] + skill_data.get("damage_rate_per_level", 0) * (ps.skill_level - 1)
        # 破甲刺：无视目标 10% 防御
        pierce_pct = skill_data.get('pierce_defense_pct', 0)
        # 防守方被混乱：受击伤害减半
        defender_confused = cls._player_is_confused(defender)

        hits = skill_data.get("hits", 1)
        total_damage = 0
        hit_any = False

        for _ in range(hits):
            atk_power = PlayerService.get_attack(attacker)
            def_power = PlayerService.get_defense(defender)
            if pierce_pct > 0:
                def_power = int(def_power * (1 - pierce_pct))
            if random.random() >= defender.dodge_rate:
                hit_any = True
                damage = cls._compute_damage(atk_power, def_power, coefficient=damage_rate)
                if defender_confused:
                    damage = int(damage * 0.5)
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

        # 技能特殊效果（命中后才触发）
        if hit_any and total_damage > 0:
            atk_for_effect = PlayerService.get_attack(attacker)
            effect_msg, heal_amount = cls._apply_skill_effect(
                skill_data, atk_for_effect, total_damage, target_player=defender)
            if heal_amount > 0:
                max_hp = attacker.effective_max_health
                attacker.health = min(max_hp, attacker.health + heal_amount)
            if effect_msg:
                attacker.last_action += f"[{effect_msg}]"

        # 回合结算：双方流血扣血 + 状态递减
        cls._tick_pk_bleed(attacker, defender)

        if defender.health <= 0:
            defender.health = 0
            result = cls._handle_pk_defeat(attacker, defender)
            return result, None

        cls._tick_player_status(attacker)
        cls._tick_player_status(defender)
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
        defender.pk_loss_count = (defender.pk_loss_count or 0) + 1
        AchievementService.check(defender, 'pk_loss', defender.pk_loss_count)

        return attacker.last_battle_result

    @classmethod
    def _end_pk(cls, player1, player2):
        player1.in_pk = False
        player1.pk_opponent = None
        player2.in_pk = False
        player2.pk_opponent = None