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

TIER_HONOR = {'basic': 1, 'mid': 2, 'high': 3}
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

    @classmethod
    def is_war_time(cls):
        if cls.TESTING_MODE:
            return True
        now = datetime.now()
        return now.weekday() == 5 and now.hour == 20 and now.minute < 30

    @classmethod
    def is_entry_allowed(cls):
        if cls.TESTING_MODE:
            return True
        now = datetime.now()
        return now.weekday() == 5 and now.hour == 20 and now.minute < 30

    @classmethod
    def should_force_exit(cls):
        if cls.TESTING_MODE:
            return False
        now = datetime.now()
        if now.weekday() != 5:
            return False
        if now.hour > 20 or (now.hour == 20 and now.minute >= 30):
            return True
        return False

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
        if attacker.country == defender.country:
            return False, "不能攻击本国玩家"
        atk_member = LegionMember.query.filter_by(player_id=attacker.id).first()
        def_member = LegionMember.query.filter_by(player_id=defender.id).first()
        if atk_member and def_member and atk_member.legion_id == def_member.legion_id:
            return False, "不能攻击同军团成员"
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
        atk_power = PlayerService.get_attack(attacker)
        def_power = PlayerService.get_defense(defender)

        if random.random() < defender.dodge_rate:
            attacker.last_damage_dealt = "闪避"
            attacker.last_action = f"在战场攻击了{defender.nickname}(闪避)"
            attacker.last_skill = "普通攻击"
            db.session.commit()
            return None, None

        damage = max(1, atk_power - def_power)
        is_crit = random.random() <= attacker.crit_rate
        if is_crit:
            damage = int(damage * 1.5)

        defender.health -= damage
        defender.last_damage_taken = damage

        dmg_str = f"{damage}" + ("(暴击!)" if is_crit else "")
        attacker.last_damage_dealt = dmg_str
        attacker.last_action = f"在战场攻击了{defender.nickname}"
        attacker.last_skill = "普通攻击"

        if defender.health <= 0:
            defender.health = 0
            result = cls._handle_battlefield_kill(attacker, defender)
            return result, None

        db.session.commit()
        return None, None

    @classmethod
    def battlefield_skill_strike(cls, attacker, defender, skill_id):
        can, error = cls.can_attack_in_battlefield(attacker, defender)
        if not can:
            return None, error

        from services.player_service import PlayerService
        from services.data_service import DataService as DS
        skills = DS.get_skills()
        skill = skills.get(skill_id)
        if not skill:
            return None, "技能不存在"
        player_skills = DS.get_player_skills(attacker.id)
        if skill_id not in player_skills:
            return None, "未学习该技能"
        mana_cost = skill.get('mana_cost', 0)
        if attacker.mana < mana_cost:
            return None, "魔法不足"
        attacker.mana -= mana_cost
        attacker.last_mana_cost = mana_cost

        atk_power = PlayerService.get_attack(attacker)
        def_power = PlayerService.get_defense(defender)
        damage_rate = skill.get('damage_rate', 1.0)
        hits = skill.get('hits', 1)

        total_damage = 0
        for _ in range(hits):
            if random.random() < defender.dodge_rate:
                continue
            d = max(1, int(atk_power * damage_rate) - def_power)
            if random.random() <= attacker.crit_rate:
                d = int(d * 1.5)
            total_damage += d

        if total_damage == 0:
            attacker.last_damage_dealt = "闪避"
            attacker.last_action = f"在战场对{defender.nickname}使用{skill.get('name', '')}"
            attacker.last_skill = skill_id
            db.session.commit()
            return None, None

        defender.health -= total_damage
        defender.last_damage_taken = total_damage
        attacker.last_damage_dealt = str(total_damage)
        attacker.last_action = f"在战场对{defender.nickname}使用{skill.get('name', '')}"
        attacker.last_skill = skill_id

        if defender.health <= 0:
            defender.health = 0
            result = cls._handle_battlefield_kill(attacker, defender)
            return result, None

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

        # 2. Honor transfer
        honor_gained = 0
        if defender.honor > 0:
            honor_gained = min(TIER_HONOR[tier], defender.honor)
            attacker.honor += honor_gained
            defender.honor -= honor_gained

        # Update military ranks
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

        result_msg = f"你在{city['name']}战场击杀了{defender.nickname}！"
        if honor_gained > 0:
            result_msg += f" 荣誉+{honor_gained}"
        result_msg += f" 个人团战积分+{TIER_POINTS[tier]} 军团积分+{TIER_POINTS[tier]}"
        attacker.last_battle_result = result_msg
        defender.last_battle_result = f"你在{city['name']}战场被{attacker.nickname}击杀！荣誉-{honor_gained}" if honor_gained > 0 else f"你在{city['name']}战场被{attacker.nickname}击杀！"

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
        领土战没有独立的结束触发器,占领/领取时按需惰性结算,使 /legion/occupy 可用。"""
        cls._ensure_city(city_key)
        state = cls._cities[city_key]
        if state.legion_scores:
            state.winner_legion_id = max(state.legion_scores, key=state.legion_scores.get)
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

        legion = Legion.query.get(member.legion_id)
        occupied = legion.occupied_cities
        if city_key in occupied:
            return False, "该城市已被占领"
        occupied.append(city_key)
        legion.occupied_cities = occupied
        db.session.commit()
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

    # --- Territory bonuses ---

    @classmethod
    def get_territory_bonuses(cls, player):
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
