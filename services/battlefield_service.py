import random
import time
import json
from models.legion import Legion, LegionMember
from models.player import PlayerModel
from services import db
from services.data_service import DataService
from datetime import datetime, date


# --- City configuration ---

BATTLEFIELD_CITIES = {
    # Basic (低级) - country-restricted
    'chengdu':  {'name': '成都', 'tier': 'basic', 'country': '蜀'},
    'yongan':   {'name': '永安', 'tier': 'basic', 'country': '蜀'},
    'jianing':  {'name': '建宁', 'tier': 'basic', 'country': '蜀'},
    'beiping':  {'name': '北平', 'tier': 'basic', 'country': '魏'},
    'jinyang':  {'name': '晋阳', 'tier': 'basic', 'country': '魏'},
    'xuchang':  {'name': '许昌', 'tier': 'basic', 'country': '魏'},
    'jianye':   {'name': '建邺', 'tier': 'basic', 'country': '吴'},
    'wujun':    {'name': '吴郡', 'tier': 'basic', 'country': '吴'},
    'chaisang': {'name': '柴桑', 'tier': 'basic', 'country': '吴'},
    # Mid (中级) - neutral
    'jiangling': {'name': '江陵', 'tier': 'mid', 'country': None},
    'xiapi':     {'name': '下邳', 'tier': 'mid', 'country': None},
    'hanzhong':  {'name': '汉中', 'tier': 'mid', 'country': None},
    # High (高级) - neutral
    'luoyang':   {'name': '洛阳', 'tier': 'high', 'country': None},
}

TIER_POINTS = {'basic': 1, 'mid': 2, 'high': 3}
TIER_BONUS = {'basic': 1, 'mid': 2, 'high': 3}
TIER_TOKEN = {
    'basic': 'battle_flag_1',
    'mid': 'battle_flag_2',
    'high': 'battle_flag_3',
}
TIER_NAME = {'basic': '低级', 'mid': '中级', 'high': '高级'}


class CityState:
    __slots__ = ('city_key', 'players', 'legion_scores', 'player_scores',
                 'kill_log', 'war_date', 'winner_legion_id')

    def __init__(self, city_key):
        self.city_key = city_key
        self.players = set()
        self.legion_scores = {}
        self.player_scores = {}
        self.kill_log = []
        self.war_date = ''
        self.winner_legion_id = None


class BattlefieldService:

    TESTING_MODE = True

    _cities = {}

    # --- Time control ---

    # --- Test war (workbench-triggered, non-Saturday) ---
    TEST_WAR_ACTIVE = False
    TEST_WAR_START = 0.0
    TEST_WAR_DURATION = 600  # 10 minutes

    @classmethod
    def _in_saturday_window(cls):
        now = datetime.now()
        return now.weekday() == 5 and now.hour == 20 and now.minute < 30

    @classmethod
    def is_war_time(cls):
        if cls.TEST_WAR_ACTIVE:
            return time.time() - cls.TEST_WAR_START < cls.TEST_WAR_DURATION
        if cls.TESTING_MODE:
            return True
        return cls._in_saturday_window()

    @classmethod
    def is_entry_allowed(cls):
        if cls.TEST_WAR_ACTIVE:
            return time.time() - cls.TEST_WAR_START < cls.TEST_WAR_DURATION
        if cls.TESTING_MODE:
            return True
        return cls._in_saturday_window()

    @classmethod
    def should_force_exit(cls):
        if cls.TEST_WAR_ACTIVE:
            return time.time() - cls.TEST_WAR_START >= cls.TEST_WAR_DURATION
        if cls.TESTING_MODE:
            return False
        now = datetime.now()
        if now.weekday() != 5:
            return False
        if now.hour > 20 or (now.hour == 20 and now.minute >= 30):
            return True
        return False

    @classmethod
    def get_test_war_status(cls):
        if not cls.TEST_WAR_ACTIVE:
            return {'active': False, 'remaining': 0}
        remaining = max(0, int(cls.TEST_WAR_DURATION - (time.time() - cls.TEST_WAR_START)))
        return {'active': True, 'remaining': remaining}

    # --- Weekly territory reset & war tick ---
    _last_reset_date = ''

    @classmethod
    def ensure_weekly_territory_reset(cls):
        """周六0点清空所有城池属性加成(占领)与军团/个人积分状态，待本周团战后再占领。"""
        today = date.today()
        if today.weekday() == 5:  # Saturday
            if cls._last_reset_date != today.isoformat():
                cls._last_reset_date = today.isoformat()
                cls.reset_territories()
                cls.reset_weekly_points()

    @classmethod
    def _end_test_war(cls):
        """测试战结束：关闭入口、强制清场、按积分自动占领。"""
        cls.TEST_WAR_ACTIVE = False
        for p in PlayerModel.query.filter_by(in_battlefield=True).all():
            cls.exit_battlefield(p)
        cls._auto_settle_territories()

    @classmethod
    def tick(cls):
        """战场相关页面加载时调用：处理周重置、测试战结束、强制清场。"""
        cls.ensure_weekly_territory_reset()
        if cls.TEST_WAR_ACTIVE and cls.should_force_exit():
            cls._end_test_war()
        # 死亡超时清扫：续命窗口(15秒)已过的阵亡玩家强制传出战场，
        # 避免有灯不复活/离线玩家永久滞留 in_battlefield=True。
        now = time.time()
        for state in cls._cities.values():
            for pid in list(state.players):
                p = PlayerModel.query.get(pid)
                if p and p.in_battlefield and p.battlefield_death_time > 0 \
                        and now - p.battlefield_death_time > 15:
                    cls.force_death_exit(p)

    @classmethod
    def _auto_settle_territories(cls):
        """测试战结束后，按各城当日积分榜最高军团自动占领。"""
        for city_key in BATTLEFIELD_CITIES:
            state = cls._settle_city(city_key)
            winner = getattr(state, 'winner_legion_id', None)
            if winner:
                cls._set_city_owner(winner, city_key)

    # --- City state management ---

    @classmethod
    def _ensure_city(cls, city_key):
        today = date.today().isoformat()
        if city_key not in cls._cities:
            cls._cities[city_key] = CityState(city_key)
        if cls._cities[city_key].war_date != today:
            cls._cities[city_key] = CityState(city_key)
            cls._cities[city_key].war_date = today

    # --- Enter / Exit ---

    @classmethod
    def can_enter_city(cls, player, city_key):
        city = BATTLEFIELD_CITIES.get(city_key)
        if not city:
            return False, "城市不存在"
        if city['country'] and player.country != city['country']:
            return False, f"{city['name']}仅限{city['country']}国玩家进入"
        if player.in_battle or player.in_pk:
            return False, "你正在战斗中"
        if player.in_battlefield:
            return False, "需先离开当前战场才能进入其它城市"
        if not cls.is_entry_allowed():
            return False, "战场未开放或已结束"
        token_id = TIER_TOKEN[city['tier']]
        inv = DataService.get_inventory_item(player.id, token_id)
        if not inv or inv.quantity < 1:
            token_name = {'battle_flag_1': '战场令旗(低级)', 'battle_flag_2': '战场令旗(中级)', 'battle_flag_3': '战场令旗(高级)'}[token_id]
            return False, f"需要{token_name}才能进入"
        member = LegionMember.query.filter_by(player_id=player.id).first()
        if not member:
            return False, "需要加入军团才能进入战场"
        return True, None

    @classmethod
    def enter_battlefield(cls, player, city_key):
        can, error = cls.can_enter_city(player, city_key)
        if not can:
            return False, error
        city = BATTLEFIELD_CITIES[city_key]
        token_id = TIER_TOKEN[city['tier']]
        DataService.remove_item_from_inventory(player.id, token_id, 1)

        player.in_battlefield = True
        player.battlefield_city = city_key
        player.battlefield_death_time = 0.0
        player.in_pk = False
        player.pk_opponent = None

        from services.player_service import PlayerService
        player.health = PlayerService.get_max_health(player)
        player.mana = PlayerService.get_max_mana(player)

        cls._ensure_city(city_key)
        cls._cities[city_key].players.add(player.id)
        if player.id not in cls._cities[city_key].player_scores:
            cls._cities[city_key].player_scores[player.id] = 0

        db.session.commit()
        return True, f"进入了{city['name']}战场！"

    @classmethod
    def exit_battlefield(cls, player):
        city_key = player.battlefield_city
        if city_key and city_key in cls._cities:
            cls._cities[city_key].players.discard(player.id)
        player.in_battlefield = False
        player.battlefield_city = None
        player.battlefield_death_time = 0.0
        player.in_pk = False
        player.pk_opponent = None
        db.session.commit()

    # --- Attack ---

    @classmethod
    def can_attack_in_battlefield(cls, attacker, defender):
        if not attacker.in_battlefield or not defender.in_battlefield:
            return False, "不在战场中"
        if attacker.battlefield_city != defender.battlefield_city:
            return False, "不在同一战场"
        if attacker.health <= 0 or attacker.battlefield_death_time > 0:
            return False, "你已阵亡，无法攻击"
        if attacker.country == defender.country:
            return False, "不能攻击本国玩家"
        atk_member = LegionMember.query.filter_by(player_id=attacker.id).first()
        def_member = LegionMember.query.filter_by(player_id=defender.id).first()
        if atk_member and def_member and atk_member.legion_id == def_member.legion_id:
            return False, "不能攻击同军团成员"
        if defender.in_pk or defender.in_battle:
            return False, '对方正在战斗中，无法攻击'
        if defender.health <= 0:
            return False, "对方已阵亡"
        if defender.battlefield_death_time > 0:
            return False, "对方已阵亡"
        return True, None

    @classmethod
    def battlefield_strike(cls, attacker, defender):
        can, error = cls.can_attack_in_battlefield(attacker, defender)
        if not can:
            return None, error

        from services.player_service import PlayerService
        from services.battle_service import BattleService

        # 攻击方被混乱：无法行动（与外部PK一致）
        if BattleService._player_is_confused(attacker):
            attacker.last_action = "混乱中，无法行动"
            attacker.last_skill = "混乱"
            attacker.last_damage_dealt = "0(混乱)"
            defender.last_damage_taken = 0
            BattleService._tick_pk_bleed(attacker, defender)
            BattleService._tick_player_status(attacker)
            BattleService._tick_player_status(defender)
            if defender.health <= 0:
                defender.health = 0
                result = cls._handle_battlefield_kill(attacker, defender)
                return result, None
            db.session.commit()
            return None, "混乱中，无法行动"

        atk_power = PlayerService.get_attack(attacker)
        def_power = PlayerService.get_defense(defender)

        if random.random() >= defender.dodge_rate:
            # 统一乘法伤害公式（与外部PK一致）
            damage = BattleService._compute_damage(atk_power, def_power, coefficient=1.0)
            # 防守方被混乱：受击伤害减半
            if BattleService._player_is_confused(defender):
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

        attacker.last_action = f"在战场攻击了{defender.nickname}"
        attacker.last_skill = "普通攻击"

        # 回合结算：双方流血扣血 + 状态递减
        BattleService._tick_pk_bleed(attacker, defender)

        if defender.health <= 0:
            defender.health = 0
            result = cls._handle_battlefield_kill(attacker, defender)
            return result, None

        BattleService._tick_player_status(attacker)
        BattleService._tick_player_status(defender)
        db.session.commit()
        return None, None

    @classmethod
    def battlefield_skill_strike(cls, attacker, defender, skill_id):
        can, error = cls.can_attack_in_battlefield(attacker, defender)
        if not can:
            return None, error

        from services.player_service import PlayerService
        from services.battle_service import BattleService
        from models.player import PlayerSkill

        # 攻击方被混乱/封魔：无法使用技能（与外部PK一致）
        if BattleService._player_is_confused(attacker):
            return None, "混乱中，无法使用技能"
        if BattleService._player_is_silenced(attacker):
            return None, "被封印法力，无法使用技能"

        skill_data = DataService.get_skill(skill_id)
        if not skill_data:
            return None, "技能不存在"
        if skill_data.get('skill_type') != 'active':
            return None, "被动技能无法使用"

        ps = PlayerSkill.query.filter_by(
            player_id=attacker.id, skill_id=skill_id).first()
        if not ps:
            return None, "未学习该技能"

        # 技能数值按等级成长（与外部PK一致）
        mana_cost = int(round(skill_data["base_mana_cost"] + skill_data.get("mana_cost_per_level", 0) * (ps.skill_level - 1)))
        if attacker.mana < mana_cost:
            return None, "魔法不足"
        attacker.mana -= mana_cost
        attacker.last_mana_cost = mana_cost
        attacker.last_action = f"在战场对{defender.nickname}使用{skill_data['name']}"
        attacker.last_skill = skill_data["name"]

        damage_rate = skill_data["base_damage_rate"] + skill_data.get("damage_rate_per_level", 0) * (ps.skill_level - 1)
        # 破甲刺：无视目标部分防御
        pierce_pct = skill_data.get('pierce_defense_pct', 0)
        # 防守方被混乱：受击伤害减半
        defender_confused = BattleService._player_is_confused(defender)

        hits = skill_data.get("hits", 1)
        total_damage = 0
        hit_any = False
        hit_results = []  # 逐段(damage, crit, dodged)，多段技能拆分展示

        for _ in range(hits):
            atk_power = PlayerService.get_attack(attacker)
            def_power = PlayerService.get_defense(defender)
            if pierce_pct > 0:
                def_power = int(def_power * (1 - pierce_pct))
            if random.random() >= defender.dodge_rate:
                hit_any = True
                damage = BattleService._compute_damage(atk_power, def_power, coefficient=damage_rate)
                crit = False
                if defender_confused:
                    damage = int(damage * 0.5)
                if random.random() <= attacker.crit_rate:
                    damage = int(damage * 1.5)
                    crit = True
                total_damage += damage
                hit_results.append((damage, crit, False))
            else:
                total_damage += 0
                hit_results.append((0, False, True))

        if hits > 1:
            attacker.last_damage_dealt = BattleService._format_hit_list(hit_results)
        else:
            attacker.last_damage_dealt = str(total_damage)

        defender.health -= total_damage
        defender.last_damage_taken = total_damage

        # 技能特殊效果（命中后才触发：吸血/混乱/封魔/流血等，与外部PK一致）
        if hit_any and total_damage > 0:
            atk_for_effect = PlayerService.get_attack(attacker)
            effect_msg, heal_amount = BattleService._apply_skill_effect(
                skill_data, atk_for_effect, total_damage, target_player=defender)
            if heal_amount > 0:
                max_hp = attacker.effective_max_health
                attacker.health = min(max_hp, attacker.health + heal_amount)
            if effect_msg:
                attacker.last_action += f"[{effect_msg}]"

        # 回合结算：双方流血扣血 + 状态递减
        BattleService._tick_pk_bleed(attacker, defender)

        if defender.health <= 0:
            defender.health = 0
            result = cls._handle_battlefield_kill(attacker, defender)
            return result, None

        BattleService._tick_player_status(attacker)
        BattleService._tick_player_status(defender)
        db.session.commit()
        return None, None

    # --- Kill handling ---

    @classmethod
    def _handle_battlefield_kill(cls, attacker, defender):
        city_key = attacker.battlefield_city
        city = BATTLEFIELD_CITIES.get(city_key)
        tier = city['tier']

        # 1. Personal battle points
        attacker_member = LegionMember.query.filter_by(player_id=attacker.id).first()
        if attacker_member:
            attacker_member.personal_battle_points += TIER_POINTS[tier]

        # 2. 荣誉不转移（有意设计）：战场击杀仅结算积分，不转移荣誉/银两/经验，
        #    与野外 PK 的荣誉零和分档无关。

        # Update military ranks (honor 未变化，通常不触发军衔变动)
        from services.player_service import PlayerService
        PlayerService.update_military_rank(attacker)
        PlayerService.update_military_rank(defender)

        # 3. Legion battle points (in-memory + persistent)
        cls._ensure_city(city_key)
        if attacker_member:
            lid = attacker_member.legion_id
            cls._cities[city_key].legion_scores[lid] = \
                cls._cities[city_key].legion_scores.get(lid, 0) + TIER_POINTS[tier]
            legion = Legion.query.get(lid)
            if legion:
                legion.battle_points += TIER_POINTS[tier]

        cls._cities[city_key].player_scores[attacker.id] = \
            cls._cities[city_key].player_scores.get(attacker.id, 0) + TIER_POINTS[tier]

        # Kill log
        log_entry = f"{attacker.nickname}击杀了{defender.nickname}"
        city_state = cls._cities[city_key]
        city_state.kill_log.append(log_entry)
        if len(city_state.kill_log) > 20:
            city_state.kill_log = city_state.kill_log[-20:]

        # Set defender death state
        defender.battlefield_death_time = time.time()
        defender.in_pk = False
        defender.pk_opponent = None
        attacker.in_pk = False
        attacker.pk_opponent = None

        result_msg = f"{city['name']}战场：你击杀了{defender.nickname} 个人军团积分+{TIER_POINTS[tier]} 军团积分+{TIER_POINTS[tier]}"
        attacker.last_battle_result = result_msg
        defender.last_battle_result = f"{city['name']}战场：你被{attacker.nickname}击杀"

        # 被击杀立即传出战场：无续命灯则直接传送出战场；有灯可原地复活
        lamp = DataService.get_inventory_item(defender.id, "battle_revive_lamp")
        if not lamp or lamp.quantity < 1:
            cls.force_death_exit(defender)

        db.session.commit()
        return result_msg

    # --- Death & Revive ---

    @classmethod
    def can_revive_in_battlefield(cls, player):
        if not player.in_battlefield or player.battlefield_death_time <= 0:
            return False
        elapsed = time.time() - player.battlefield_death_time
        return elapsed <= 15

    @classmethod
    def revive_in_battlefield(cls, player):
        if not cls.can_revive_in_battlefield(player):
            return False, "复活时间已过"
        inv = DataService.get_inventory_item(player.id, "battle_revive_lamp")
        if not inv or inv.quantity < 1:
            return False, "没有战场续命灯"
        DataService.remove_item_from_inventory(player.id, "battle_revive_lamp", 1)
        from services.player_service import PlayerService
        player.health = PlayerService.get_max_health(player)
        player.mana = PlayerService.get_max_mana(player)
        player.battlefield_death_time = 0.0
        db.session.commit()
        return True, "使用战场续命灯复活成功！"

    @classmethod
    def force_death_exit(cls, player):
        cls.exit_battlefield(player)
        return True, "你被传送出战场"

    # --- Rankings ---

    @classmethod
    def get_city_rankings(cls, city_key):
        cls._ensure_city(city_key)
        state = cls._cities[city_key]

        sorted_players = sorted(state.player_scores.items(), key=lambda x: x[1], reverse=True)[:10]
        player_ranking = []
        for pid, score in sorted_players:
            if score <= 0:
                continue
            p = PlayerModel.query.get(pid)
            if p:
                player_ranking.append({'name': p.nickname, 'country': p.country, 'score': score})

        sorted_legions = sorted(state.legion_scores.items(), key=lambda x: x[1], reverse=True)[:5]
        legion_ranking = []
        for lid, score in sorted_legions:
            if score <= 0:
                continue
            legion = Legion.query.get(lid)
            if legion:
                legion_ranking.append({'name': legion.name, 'country': legion.country, 'score': score})

        return player_ranking, legion_ranking

    # --- War settlement & Territory ---

    @classmethod
    def _settle_city(cls, city_key):
        """根据已累积的军团积分结算该城市当前胜者(写入 winner_legion_id)。
        领土战没有独立的结束触发器,占领/领取时按需惰性结算,使 /legion/occupy 可用。
        内存态 legion_scores 为空(跨天/重启清零)时,回退到持久化的 Legion.battle_points 取首,
        使占领不依赖易失内存。"""
        cls._ensure_city(city_key)
        state = cls._cities[city_key]
        if state.legion_scores:
            state.winner_legion_id = max(state.legion_scores, key=state.legion_scores.get)
        else:
            top = Legion.query.filter(Legion.battle_points > 0) \
                .order_by(Legion.battle_points.desc()).first()
            state.winner_legion_id = top.id if top else None
        return state

    @classmethod
    def settle_war(cls):
        for city_key in BATTLEFIELD_CITIES:
            cls._settle_city(city_key)

    @classmethod
    def occupy_city(cls, player, city_key):
        member = LegionMember.query.filter_by(player_id=player.id).first()
        if not member or member.role != 'leader':
            return False, "只有军团长可以占领城市"

        if city_key not in BATTLEFIELD_CITIES:
            return False, "城市不存在"

        # 占领时按当前积分惰性结算胜者,无需等待独立结束事件
        state = cls._settle_city(city_key)
        winner_id = getattr(state, 'winner_legion_id', None)
        if winner_id != member.legion_id:
            return False, "你的军团未赢得该城市"

        # 同城仅允许积分最高的军团占领（清除其它军团的同名占领）
        if city_key in Legion.query.get(member.legion_id).occupied_cities:
            return False, "该城市已被你的军团占领"
        cls._set_city_owner(member.legion_id, city_key)  # 内部已 commit
        return True, f"成功占领{BATTLEFIELD_CITIES[city_key]['name']}！"

    @classmethod
    def get_claimable_cities(cls, legion_id):
        claimable = []
        for city_key in BATTLEFIELD_CITIES:
            # 同样惰性结算,保证领取列表能正确填充
            state = cls._settle_city(city_key)
            if getattr(state, 'winner_legion_id', None) == legion_id:
                legion = Legion.query.get(legion_id)
                if legion and city_key not in legion.occupied_cities:
                    claimable.append(city_key)
        return claimable

    @classmethod
    def _set_city_owner(cls, legion_id, city_key):
        """同城仅允许一个军团占领（积分最高者）。清除其它军团的同名占领。"""
        for legion in Legion.query.all():
            occ = legion.occupied_cities
            if city_key in occ:
                if legion.id == legion_id:
                    continue
                occ.remove(city_key)
                legion.occupied_cities = occ
        owner = Legion.query.get(legion_id)
        if owner:
            occ = owner.occupied_cities
            if city_key not in occ:
                occ.append(city_key)
                owner.occupied_cities = occ
        db.session.commit()

    @classmethod
    def get_city_owner(cls, city_key):
        for legion in Legion.query.all():
            if city_key in legion.occupied_cities:
                return legion.id
        return None

    # --- Territory bonuses ---

    @classmethod
    def get_territory_bonuses(cls, player):
        cls.ensure_weekly_territory_reset()
        member = LegionMember.query.filter_by(player_id=player.id).first()
        if not member:
            return {}
        legion = Legion.query.get(member.legion_id)
        if not legion:
            return {}
        bonuses = {'attack': 0, 'defense': 0, 'max_health': 0, 'max_mana': 0}
        for city_key in legion.occupied_cities:
            city = BATTLEFIELD_CITIES.get(city_key)
            if city:
                val = TIER_BONUS[city['tier']]
                bonuses['attack'] += val
                bonuses['defense'] += val
                bonuses['max_health'] += val
                bonuses['max_mana'] += val
        return bonuses

    @classmethod
    def reset_territories(cls):
        legions = Legion.query.all()
        for legion in legions:
            legion.occupied_cities = []
        db.session.commit()

    @classmethod
    def reset_weekly_points(cls):
        """清空军团战场积分与个人积分，并重置内存中各城积分状态。"""
        for legion in Legion.query.all():
            legion.battle_points = 0
        for m in LegionMember.query.all():
            m.personal_battle_points = 0
        db.session.commit()
        # 重置内存中 CityState 积分（下次访问会按当天重建空状态）
        for city_key in BATTLEFIELD_CITIES:
            cls._cities.pop(city_key, None)

    # --- Get battlefield players ---

    @classmethod
    def get_city_players(cls, city_key):
        cls._ensure_city(city_key)
        state = cls._cities[city_key]
        players = []
        for pid in state.players:
            p = PlayerModel.query.get(pid)
            if p and p.in_battlefield and p.battlefield_city == city_key and p.battlefield_death_time == 0:
                players.append(p)
        return players

    @classmethod
    def get_kill_log(cls, city_key):
        cls._ensure_city(city_key)
        return cls._cities[city_key].kill_log[-10:]
