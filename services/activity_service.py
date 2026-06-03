"""Activity service for daily activities, sign-in, smash egg, etc."""
import random
import time
from datetime import datetime, date
from services import db
from services.data_service import DataService


class ActivityService:
    # Daily activity definitions with their max counts and activity points
    DAILY_ACTIVITIES = {
        'rps': {'name': '每日猜拳', 'max': 3, 'points': 15},
        'sign_in': {'name': '每日签到', 'max': 1, 'points': 10},
        'smash_egg': {'name': '每日砸蛋', 'max': 1, 'points': 10},
        'study': {'name': '陪太子读书', 'max': 5, 'points': 10},
        'quiz': {'name': '每日答题拿奖励', 'max': 5, 'points': 10},
        'card_flip': {'name': '幸运金珠翻牌', 'max': 1, 'points': 25},
    }

    # Smash egg prize pool (weighted random)
    EGG_PRIZES = [
        {'name': '续命灯', 'item_id': 'potion_revive', 'weight': 15},
        {'name': '止血草x5', 'item_id': 'potion_heal', 'count': 5, 'weight': 25},
        {'name': '凝魔草x5', 'item_id': 'potion_mana', 'count': 5, 'weight': 25},
        {'name': '强化宝玉', 'item_id': 'enhance_gem', 'weight': 10},
        {'name': '500银两', 'type': 'gold', 'value': 500, 'weight': 15},
        {'name': '200经验', 'type': 'exp', 'value': 200, 'weight': 10},
        {'name': '1元宝', 'type': 'yuanbao', 'value': 1, 'weight': 5},
    ]

    # Card flip prize pool
    CARD_PRIZES = [
        {'name': '续命灯', 'item_id': 'potion_revive', 'weight': 15},
        {'name': '止血草x5', 'item_id': 'potion_heal', 'count': 5, 'weight': 25},
        {'name': '凝魔草x5', 'item_id': 'potion_mana', 'count': 5, 'weight': 25},
        {'name': '强化宝玉', 'item_id': 'enhance_gem', 'weight': 10},
        {'name': '1000银两', 'type': 'gold', 'value': 1000, 'weight': 10},
        {'name': '500经验', 'type': 'exp', 'value': 500, 'weight': 10},
        {'name': '2金珠', 'type': 'jinzu', 'value': 2, 'weight': 5},
    ]

    # Quiz questions pool
    QUIZ_POOL = [
        {'q': '三国中被称为"卧龙"的是谁？', 'a': 'A', 'options': ['诸葛亮', '司马懿', '周瑜']},
        {'q': '蜀国五虎上将中谁最年长？', 'a': 'B', 'options': ['关羽', '黄忠', '赵云']},
        {'q': '赤壁之战中谁提出了火攻之计？', 'a': 'C', 'options': ['诸葛亮', '周瑜', '黄盖']},
        {'q': '三国中"凤雏"指的是谁？', 'a': 'A', 'options': ['庞统', '徐庶', '鲁肃']},
        {'q': '曹操的字是什么？', 'a': 'B', 'options': ['孟德', '孟德', '玄德']},
        {'q': '关羽被谁所杀？', 'a': 'C', 'options': ['张辽', '吕蒙', '孙权部下']},
        {'q': '刘备在哪个地方建立了蜀国？', 'a': 'A', 'options': ['成都', '荆州', '益州']},
        {'q': '赵云长坂坡救了谁？', 'a': 'B', 'options': ['刘备', '阿斗', '甘夫人']},
        {'q': '孙权的国号是什么？', 'a': 'A', 'options': ['吴', '蜀', '魏']},
        {'q': '三国中谁的武器是青龙偃月刀？', 'a': 'C', 'options': ['张飞', '赵云', '关羽']},
        {'q': '张飞的武器是什么？', 'a': 'A', 'options': ['丈八蛇矛', '青龙偃月刀', '双股剑']},
        {'q': '孙策的外号是什么？', 'a': 'B', 'options': ['小霸王', '江东猛虎', '卧龙']},
        {'q': '马超是哪个国家的人？', 'a': 'C', 'options': ['魏', '吴', '蜀']},
        {'q': '三国时期魏国的建立者是谁？', 'a': 'A', 'options': ['曹丕', '曹操', '司马懿']},
    ]

    # Sign-in milestone rewards
    SIGN_REWARDS = {
        2: {'name': '签到2次奖励', 'items': [('potion_heal', 10)], 'yuanbao': 1},
        5: {'name': '签到5次奖励', 'items': [('potion_heal', 20), ('potion_mana', 20)], 'yuanbao': 2},
        10: {'name': '签到10次奖励', 'items': [('enhance_gem', 2), ('potion_heal', 30)], 'yuanbao': 5},
        17: {'name': '签到17次奖励', 'items': [('enhance_gem', 5), ('potion_revive', 3)], 'yuanbao': 10},
        28: {'name': '签到28次奖励', 'items': [('enhance_gem', 10), ('potion_revive', 5)], 'yuanbao': 20},
    }

    @classmethod
    def get_today_value(cls, player, key):
        """Get a daily activity value, auto-resets if day changed."""
        data = player.activity_data
        today = str(date.today())
        daily = data.get('daily', {})
        if daily.get('_date') != today:
            daily = {'_date': today}
            data['daily'] = daily
            player.activity_data = data
            db.session.commit()
        return daily.get(key, 0)

    @classmethod
    def set_today_value(cls, player, key, value):
        """Set a daily activity value."""
        data = player.activity_data
        today = str(date.today())
        daily = data.get('daily', {})
        if daily.get('_date') != today:
            daily = {'_date': today}
        daily[key] = value
        data['daily'] = daily
        player.activity_data = data

    @classmethod
    def get_total_activity_points(cls, player):
        """Get total earned activity points today."""
        total = 0
        for key, info in cls.DAILY_ACTIVITIES.items():
            done = cls.get_today_value(player, f'{key}_done')
            max_val = info['max']
            if done >= max_val:
                total += info['points']
        return total

    @classmethod
    def get_daily_progress(cls, player):
        """Get all daily activity progress."""
        result = []
        for key, info in cls.DAILY_ACTIVITIES.items():
            done = cls.get_today_value(player, f'{key}_done')
            result.append({
                'key': key,
                'name': info['name'],
                'done': done,
                'max': info['max'],
                'points': info['points'],
                'completed': done >= info['max'],
            })
        return result

    # --- Sign In ---
    @classmethod
    def sign_in(cls, player):
        """Perform daily sign in."""
        done = cls.get_today_value(player, 'sign_in_done')
        if done >= 1:
            return False, "今日已签到"

        cls.set_today_value(player, 'sign_in_done', 1)

        # Track cumulative sign-in days
        data = player.activity_data
        sign_days = data.get('sign_total', 0) + 1
        data['sign_total'] = sign_days
        player.activity_data = data

        # Random reward: 10-50 gold value item
        reward_gold = random.randint(10, 50)
        player.gold += reward_gold

        db.session.commit()
        return True, f"签到成功！第{sign_days}天，获得{reward_gold}银两"

    @classmethod
    def get_sign_info(cls, player):
        data = player.activity_data
        sign_total = data.get('sign_total', 0)
        claimed = data.get('sign_claimed', [])
        return sign_total, claimed

    @classmethod
    def claim_sign_reward(cls, player, days):
        """Claim milestone sign-in reward."""
        data = player.activity_data
        sign_total = data.get('sign_total', 0)
        claimed = data.get('sign_claimed', [])

        if sign_total < days:
            return False, f"签到次数不足{days}次"
        if days in claimed:
            return False, "已领取该奖励"

        reward = cls.SIGN_REWARDS.get(days)
        if not reward:
            return False, "无此奖励"

        for item_id, count in reward.get('items', []):
            DataService.add_item_to_inventory(player.id, item_id, count)
        player.yuanbao += reward.get('yuanbao', 0)

        claimed.append(days)
        data['sign_claimed'] = claimed
        player.activity_data = data
        db.session.commit()
        return True, f"领取【{reward['name']}】成功"

    # --- Smash Egg ---
    @classmethod
    def smash_egg(cls, player, use_free=True):
        """Smash an egg. Free once per day, then 50 yuanbao each."""
        free_used = cls.get_today_value(player, 'smash_egg_free')
        if use_free:
            if free_used >= 1:
                return False, "今日免费砸蛋机会已用完"
            cls.set_today_value(player, 'smash_egg_free', 1)
            cls.set_today_value(player, 'smash_egg_done', 1)
        else:
            if player.yuanbao < 50:
                return False, "元宝不足，需要50元宝"
            player.yuanbao -= 50

        # Pick prize
        prize = cls._weighted_random(cls.EGG_PRIZES)
        reward_msg = cls._grant_prize(player, prize)
        db.session.commit()
        return True, reward_msg

    @classmethod
    def get_egg_free_remaining(cls, player):
        return 1 - cls.get_today_value(player, 'smash_egg_free')

    # --- Rock Paper Scissors ---
    @classmethod
    def start_rps(cls, player):
        """Start a RPS round."""
        done = cls.get_today_value(player, 'rps_done')
        if done >= 3:
            return False, "今日猜拳次数已用完"
        return True, None

    @classmethod
    def play_rps(cls, player, choice):
        """Play RPS: choice is 'rock', 'scissors', 'paper'."""
        done = cls.get_today_value(player, 'rps_done')
        if done >= 3:
            return False, "今日猜拳次数已用完"

        npc_choices = ['rock', 'scissors', 'paper']
        npc_choice = random.choice(npc_choices)

        choice_map = {'rock': '石头', 'scissors': '剪刀', 'paper': '布'}
        result = cls._rps_result(choice, npc_choice)

        if result == 'win':
            exp_reward = player.level * 100 + 500
            gold_reward = player.level * 50 + 200
            player.experience += exp_reward
            player.gold += gold_reward
            msg = f"你出{choice_map[choice]}，对方出{choice_map[npc_choice]}，你赢了！经验+{exp_reward} 银两+{gold_reward}"
        elif result == 'lose':
            exp_reward = player.level * 50 + 100
            gold_reward = player.level * 10 + 50
            player.experience += exp_reward
            player.gold += gold_reward
            msg = f"你出{choice_map[choice]}，对方出{choice_map[npc_choice]}，你输了！经验+{exp_reward} 银两+{gold_reward}"
        else:
            exp_reward = player.level * 80 + 300
            gold_reward = player.level * 30 + 100
            player.experience += exp_reward
            player.gold += gold_reward
            msg = f"你出{choice_map[choice]}，对方出{choice_map[npc_choice]}，平局！经验+{exp_reward} 银两+{gold_reward}"

        cls.set_today_value(player, 'rps_done', done + 1)
        db.session.commit()
        return True, msg

    @classmethod
    def _rps_result(cls, player_choice, npc_choice):
        wins = {'rock': 'scissors', 'scissors': 'paper', 'paper': 'rock'}
        if player_choice == npc_choice:
            return 'draw'
        if wins[player_choice] == npc_choice:
            return 'win'
        return 'lose'

    # --- Quiz ---
    @classmethod
    def start_quiz(cls, player):
        """Start a quiz round. Returns question dict or None."""
        done = cls.get_today_value(player, 'quiz_done')
        if done >= 5:
            return None
        return random.choice(cls.QUIZ_POOL)

    @classmethod
    def answer_quiz(cls, player, question_idx, answer):
        """Answer a quiz question."""
        done = cls.get_today_value(player, 'quiz_done')
        if done >= 5:
            return False, "今日答题次数已用完"

        question = cls.QUIZ_POOL[question_idx]
        is_correct = answer == question['a']

        if is_correct:
            exp_reward = player.level * 200 + 1000
            gold_reward = player.level * 100 + 500
            player.experience += exp_reward
            player.gold += gold_reward
            msg = f"回答正确！经验+{exp_reward} 银两+{gold_reward}"
        else:
            exp_reward = player.level * 50 + 100
            gold_reward = player.level * 10 + 50
            player.experience += exp_reward
            player.gold += gold_reward
            correct_text = question['options'][ord(question['a']) - ord('A')]
            msg = f"回答错误，正确答案是{correct_text}。经验+{exp_reward} 银两+{gold_reward}"

        cls.set_today_value(player, 'quiz_done', done + 1)
        db.session.commit()
        return True, msg

    # --- Study (陪太子读书) ---
    STUDY_DURATION = 600  # 10 minutes in seconds

    @classmethod
    def start_study(cls, player):
        """开始陪太子读书，需要等待10分钟。"""
        done = cls.get_today_value(player, 'study_done')
        if done >= 5:
            return False, "今日陪读次数已用完"

        # Check if already studying
        data = player.activity_data
        study_data = data.get('study', {})
        if study_data.get('start_time'):
            start_time = study_data.get('start_time')
            elapsed = time.time() - start_time
            if elapsed < cls.STUDY_DURATION:
                remaining = int(cls.STUDY_DURATION - elapsed)
                return False, f"正在陪读中，还需等待{remaining}秒"

        # Start new study session
        study_data['start_time'] = time.time()
        data['study'] = study_data
        player.activity_data = data
        db.session.commit()
        return True, "开始陪太子读书，10分钟后可领取奖励"

    @classmethod
    def finish_study(cls, player):
        """完成陪读，领取奖励。"""
        done = cls.get_today_value(player, 'study_done')
        if done >= 5:
            return False, "今日陪读次数已用完"

        data = player.activity_data
        study_data = data.get('study', {})
        start_time = study_data.get('start_time')

        if not start_time:
            return False, "请先开始陪读"

        elapsed = time.time() - start_time
        if elapsed < cls.STUDY_DURATION:
            remaining = int(cls.STUDY_DURATION - elapsed)
            return False, f"陪读未完成，还需等待{remaining}秒"

        # Give rewards
        exp_reward = player.level * 500 + 1000
        player.experience += exp_reward

        # Add activity points
        activity_points = 2
        cls._add_activity_points(player, activity_points)

        # Clear study session and increment done count
        data['study'] = {}
        player.activity_data = data
        cls.set_today_value(player, 'study_done', done + 1)

        db.session.commit()
        return True, f"陪读完成！经验+{exp_reward}，活跃度+{activity_points}"

    @classmethod
    def get_study_status(cls, player):
        """获取陪读状态。"""
        done = cls.get_today_value(player, 'study_done')
        data = player.activity_data
        study_data = data.get('study', {})
        start_time = study_data.get('start_time')

        if start_time:
            elapsed = time.time() - start_time
            if elapsed < cls.STUDY_DURATION:
                remaining = int(cls.STUDY_DURATION - elapsed)
                return {'status': 'studying', 'remaining': remaining, 'done': done}

        return {'status': 'idle', 'remaining': 0, 'done': done}

    @classmethod
    def _add_activity_points(cls, player, points):
        """Add daily activity points."""
        data = player.activity_data
        today = str(date.today())
        daily = data.get('daily', {})
        if daily.get('_date') != today:
            daily = {'_date': today}
        current = daily.get('activity_points', 0)
        daily['activity_points'] = current + points
        data['daily'] = daily
        player.activity_data = data

    # --- Card Flip (金珠翻牌) ---
    @classmethod
    def card_flip(cls, player, use_jinzu=True):
        """Flip a card. Costs 50 jinzu or 1 yuanbao."""
        done = cls.get_today_value(player, 'card_flip_done')

        # Check for free flip token in inventory
        flip_token = DataService.get_inventory_item(player.id, 'card_flip_token')
        if flip_token and flip_token.quantity > 0:
            DataService.remove_item_from_inventory(player.id, 'card_flip_token', 1)
        elif use_jinzu:
            if player.jinzu < 50:
                return False, "金珠不足，需要50金珠"
            player.jinzu -= 50
        else:
            if player.yuanbao < 1:
                return False, "元宝不足，需要1元宝"
            player.yuanbao -= 1

        prize = cls._weighted_random(cls.CARD_PRIZES)
        reward_msg = cls._grant_prize(player, prize)
        cls.set_today_value(player, 'card_flip_done', done + 1)
        db.session.commit()
        return True, reward_msg

    # --- Helpers ---
    @classmethod
    def _weighted_random(cls, pool):
        total = sum(p['weight'] for p in pool)
        r = random.uniform(0, total)
        cum = 0
        for p in pool:
            cum += p['weight']
            if r <= cum:
                return p
        return pool[-1]

    @classmethod
    def _grant_prize(cls, player, prize):
        if 'item_id' in prize:
            count = prize.get('count', 1)
            DataService.add_item_to_inventory(player.id, prize['item_id'], count)
            return f"获得{prize['name']}"
        elif prize.get('type') == 'gold':
            player.gold += prize['value']
            return f"获得{prize['value']}银两"
        elif prize.get('type') == 'exp':
            player.experience += prize['value']
            return f"获得{prize['value']}经验"
        elif prize.get('type') == 'yuanbao':
            player.yuanbao += prize['value']
            return f"获得{prize['value']}元宝"
        elif prize.get('type') == 'jinzu':
            player.jinzu += prize['value']
            return f"获得{prize['value']}金珠"
        return "获得奖励"