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

    # Smash egg prize pool (weighted random) - 52 items matching reference server
    EGG_PRIZES = [
        {'name': '哥姐徽章', 'item_id': 'badge_gejie', 'weight': 1},             # 0.001%
        {'name': '秘药礼包', 'item_id': 'mi_yao_pack', 'weight': 5000},          # 5%
        {'name': '双倍经验卡', 'item_id': 'double_exp_card', 'weight': 5000},     # 5%
        {'name': '神游果', 'item_id': 'shen_you_guo', 'weight': 2000},           # 2%
        {'name': '背包扩容卷', 'item_id': 'bag_expand', 'weight': 5000},          # 5%
        {'name': '玫瑰花', 'item_id': 'rose', 'weight': 5000},                   # 5%
        {'name': '小喇叭', 'item_id': 'small_horn', 'weight': 2000},             # 2%
        {'name': '续命灯', 'item_id': 'potion_revive', 'weight': 5000},          # 5%
        {'name': '强化宝玉', 'item_id': 'enhance_gem', 'weight': 5000},           # 5%
        {'name': '宝匣钥匙', 'item_id': 'chest_key', 'weight': 2000},            # 2%
        {'name': '追杀令', 'item_id': 'hunt_order', 'weight': 1000},             # 1%
        {'name': '新婚草戒包', 'item_id': 'wedding_ring_pack', 'weight': 1000},  # 1%
        {'name': '诸侯令1天', 'item_id': 'duke_token_1d', 'weight': 2000},      # 2%
        {'name': '诸侯令7天', 'item_id': 'duke_token_7d', 'weight': 500},       # 0.5%
        {'name': '小银两包', 'item_id': 'money_small', 'weight': 100},           # 0.1%
        {'name': '玫瑰花种子', 'item_id': 'rose_seed', 'weight': 5000},          # 5%
        {'name': '经验丹种子', 'item_id': 'exp_seed', 'weight': 2000},           # 2%
        {'name': '大经验丹种子', 'item_id': 'seed_big_exp', 'weight': 1000},     # 1%
        {'name': '催熟剂', 'item_id': 'ripening_agent', 'weight': 3000},         # 3%
        {'name': '大血石', 'item_id': 'big_hp_stone', 'weight': 2000},           # 2%
        {'name': '大魔石', 'item_id': 'big_mp_stone', 'weight': 2000},           # 2%
        {'name': '活力卡', 'item_id': 'vitality_card', 'weight': 3000},          # 3%
        {'name': '聚魂幡碎片', 'item_id': 'soul_flag_shard', 'weight': 3000},    # 3%
        {'name': '副将招募令', 'item_id': 'lt_recruit', 'weight': 3000},          # 3%
        {'name': '副将经验丹(低)', 'item_id': 'lt_exp_low', 'weight': 3000},     # 3%
        {'name': '副将经验丹(中)', 'item_id': 'lt_exp_mid', 'weight': 3000},     # 3%
        {'name': '副将经验丹(高)', 'item_id': 'lt_exp_high', 'weight': 3000},    # 3%
        {'name': '副将资质丹', 'item_id': 'lt_aptitude', 'weight': 3000},         # 3%
        {'name': '副将增寿丹', 'item_id': 'lt_life', 'weight': 3000},            # 3%
        {'name': '副将忠诚丹', 'item_id': 'lt_loyalty', 'weight': 3000},         # 3%
        {'name': '副将强化丹', 'item_id': 'lt_enhance', 'weight': 3000},         # 3%
        {'name': '副将悟性丹', 'item_id': 'lt_wuxing', 'weight': 3000},          # 3%
        {'name': '碎皮', 'item_id': 'sui_pi', 'weight': 700},                    # 0.7%
        {'name': '黄杨木', 'item_id': 'huangyang_mu', 'weight': 700},            # 0.7%
        {'name': '麻布', 'item_id': 'ma_bu', 'weight': 700},                     # 0.7%
        {'name': '黄铜矿', 'item_id': 'huangtong_kuang', 'weight': 700},         # 0.7%
        {'name': '硬皮', 'item_id': 'ying_pi', 'weight': 500},                   # 0.5%
        {'name': '沉香木', 'item_id': 'chenxiang_mu', 'weight': 500},            # 0.5%
        {'name': '棉布', 'item_id': 'mian_bu', 'weight': 500},                   # 0.5%
        {'name': '黑铁矿', 'item_id': 'heitie_kuang', 'weight': 500},            # 0.5%
        {'name': '厚皮', 'item_id': 'craft_houpi', 'weight': 300},               # 0.3%
        {'name': '紫檀木', 'item_id': 'zitan_mu', 'weight': 300},                # 0.3%
        {'name': '呢绒', 'item_id': 'craft_nirong', 'weight': 300},              # 0.3%
        {'name': '精金矿', 'item_id': 'jingjin_kuang', 'weight': 300},           # 0.3%
        {'name': '技能残页·入门·吸收', 'item_id': 'skill_page_absorb_0', 'weight': 500},
        {'name': '技能残页·入门·护佑', 'item_id': 'skill_page_protect_0', 'weight': 500},
        {'name': '技能残页·入门·嗜血', 'item_id': 'skill_page_blood_0', 'weight': 500},
        {'name': '技能残页·入门·狂雷', 'item_id': 'skill_page_thunder_0', 'weight': 500},
        {'name': '技能残页·入门·火神', 'item_id': 'skill_page_fire_0', 'weight': 500},
        {'name': '技能残页·入门·冰封', 'item_id': 'skill_page_ice_0', 'weight': 500},
        {'name': '技能残页·入门·风行', 'item_id': 'skill_page_wind_0', 'weight': 500},
        {'name': '技能残页·入门·磐石', 'item_id': 'skill_page_rock_0', 'weight': 500},
        {'name': '技能残页·入门·驱散', 'item_id': 'skill_page_dispel_0', 'weight': 500},
        {'name': '技能残页·进阶·吸收', 'item_id': 'skill_page_absorb_1', 'weight': 300},
        {'name': '技能残页·进阶·护佑', 'item_id': 'skill_page_protect_1', 'weight': 300},
        {'name': '技能残页·进阶·嗜血', 'item_id': 'skill_page_blood_1', 'weight': 300},
    ]

    # Card flip prize pool - 72 items matching reference server
    CARD_PRIZES = [
        {'name': '哥姐徽章', 'item_id': 'badge_gejie', 'weight': 1},             # 0.001%
        {'name': '副将扩技符', 'item_id': 'lt_skill_expand', 'weight': 1},       # 0.001%
        {'name': '装备重塑符', 'item_id': 'equip_reshape_talisman', 'weight': 1},# 0.001%
        {'name': '秘药礼包', 'item_id': 'mi_yao_pack', 'weight': 5000},          # 5%
        {'name': '双倍经验卡', 'item_id': 'double_exp_card', 'weight': 5000},     # 5%
        {'name': '神游果', 'item_id': 'shen_you_guo', 'weight': 2000},           # 2%
        {'name': '背包扩容卷', 'item_id': 'bag_expand', 'weight': 5000},          # 5%
        {'name': '玫瑰花x2', 'item_id': 'rose', 'count': 2, 'weight': 5000},     # 5%
        {'name': '小喇叭', 'item_id': 'small_horn', 'weight': 2000},             # 2%
        {'name': '续命灯', 'item_id': 'potion_revive', 'weight': 5000},          # 5%
        {'name': '强化宝玉', 'item_id': 'enhance_gem', 'weight': 5000},           # 5%
        {'name': '宝匣钥匙', 'item_id': 'chest_key', 'weight': 2000},            # 2%
        {'name': '追杀令', 'item_id': 'hunt_order', 'weight': 1000},             # 1%
        {'name': '新婚草戒包', 'item_id': 'wedding_ring_pack', 'weight': 1000},  # 1%
        {'name': '新婚钻戒包', 'item_id': 'wedding_diamond_pack', 'weight': 130},# 0.13%
        {'name': '诸侯令1天', 'item_id': 'duke_token_1d', 'weight': 2000},      # 2%
        {'name': '诸侯令7天', 'item_id': 'duke_token_7d', 'weight': 500},       # 0.5%
        {'name': '诸侯令30天', 'item_id': 'duke_token_30d', 'weight': 50},      # 0.05%
        {'name': '小银两包', 'item_id': 'money_small', 'weight': 100},           # 0.1%
        {'name': '大银两包', 'item_id': 'money_large', 'weight': 50},            # 0.05%
        {'name': '玫瑰花种子', 'item_id': 'rose_seed', 'weight': 5000},          # 5%
        {'name': '经验丹种子', 'item_id': 'exp_seed', 'weight': 2000},           # 2%
        {'name': '大经验丹种子', 'item_id': 'seed_big_exp', 'weight': 1000},     # 1%
        {'name': '催熟剂', 'item_id': 'ripening_agent', 'weight': 3000},         # 3%
        {'name': '大血石', 'item_id': 'big_hp_stone', 'weight': 2000},           # 2%
        {'name': '大魔石', 'item_id': 'big_mp_stone', 'weight': 2000},           # 2%
        {'name': '活力卡', 'item_id': 'vitality_card', 'weight': 3000},          # 3%
        {'name': '聚魂幡碎片', 'item_id': 'soul_flag_shard', 'weight': 3000},    # 3%
        {'name': '副将招募令', 'item_id': 'lt_recruit', 'weight': 3000},          # 3%
        {'name': '副将经验丹(低)', 'item_id': 'lt_exp_low', 'weight': 3000},     # 3%
        {'name': '副将经验丹(中)', 'item_id': 'lt_exp_mid', 'weight': 3000},     # 3%
        {'name': '副将经验丹(高)', 'item_id': 'lt_exp_high', 'weight': 3000},    # 3%
        {'name': '副将资质丹', 'item_id': 'lt_aptitude', 'weight': 3000},         # 3%
        {'name': '副将增寿丹', 'item_id': 'lt_life', 'weight': 3000},            # 3%
        {'name': '副将忠诚丹', 'item_id': 'lt_loyalty', 'weight': 3000},         # 3%
        {'name': '副将强化丹', 'item_id': 'lt_enhance', 'weight': 3000},         # 3%
        {'name': '副将悟性丹', 'item_id': 'lt_wuxing', 'weight': 3000},          # 3%
        {'name': '死亡替身符', 'item_id': 'death_substitute', 'weight': 5000},   # 5%
        {'name': '碎皮包', 'item_id': 'sui_pi_pack', 'weight': 700},             # 0.7%
        {'name': '黄杨木包', 'item_id': 'huangyang_mu_pack', 'weight': 700},     # 0.7%
        {'name': '麻布包', 'item_id': 'ma_bu_pack', 'weight': 700},              # 0.7%
        {'name': '黄铜矿包', 'item_id': 'huangtong_kuang_pack', 'weight': 700},  # 0.7%
        {'name': '硬皮包', 'item_id': 'ying_pi_pack', 'weight': 500},            # 0.5%
        {'name': '沉香木包', 'item_id': 'chenxiang_mu_pack', 'weight': 500},     # 0.5%
        {'name': '棉布包', 'item_id': 'mian_bu_pack', 'weight': 500},            # 0.5%
        {'name': '黑铁矿包', 'item_id': 'heitie_kuang_pack', 'weight': 500},     # 0.5%
        {'name': '厚皮包', 'item_id': 'hou_pi_pack', 'weight': 300},             # 0.3%
        {'name': '紫檀木包', 'item_id': 'zitan_mu_pack', 'weight': 300},         # 0.3%
        {'name': '呢绒包', 'item_id': 'nirong_pack', 'weight': 300},             # 0.3%
        {'name': '精金矿包', 'item_id': 'jingjin_kuang_pack', 'weight': 300},    # 0.3%
        {'name': '技能残页·入门·吸收', 'item_id': 'skill_page_absorb_0', 'weight': 500},
        {'name': '技能残页·入门·护佑', 'item_id': 'skill_page_protect_0', 'weight': 500},
        {'name': '技能残页·入门·嗜血', 'item_id': 'skill_page_blood_0', 'weight': 500},
        {'name': '技能残页·入门·狂雷', 'item_id': 'skill_page_thunder_0', 'weight': 500},
        {'name': '技能残页·入门·火神', 'item_id': 'skill_page_fire_0', 'weight': 500},
        {'name': '技能残页·入门·冰封', 'item_id': 'skill_page_ice_0', 'weight': 500},
        {'name': '技能残页·入门·风行', 'item_id': 'skill_page_wind_0', 'weight': 500},
        {'name': '技能残页·入门·磐石', 'item_id': 'skill_page_rock_0', 'weight': 500},
        {'name': '技能残页·入门·驱散', 'item_id': 'skill_page_dispel_0', 'weight': 500},
        {'name': '技能残页·进阶·吸收', 'item_id': 'skill_page_absorb_1', 'weight': 500},
        {'name': '技能残页·进阶·护佑', 'item_id': 'skill_page_protect_1', 'weight': 500},
        {'name': '技能残页·进阶·嗜血', 'item_id': 'skill_page_blood_1', 'weight': 500},
        {'name': '技能残页·精通·吸收', 'item_id': 'skill_page_absorb_2', 'weight': 200},
        {'name': '技能残页·精通·护佑', 'item_id': 'skill_page_protect_2', 'weight': 200},
        {'name': '技能残页·精通·嗜血', 'item_id': 'skill_page_blood_2', 'weight': 100},
        {'name': '技能残页·精通·狂雷', 'item_id': 'skill_page_thunder_2', 'weight': 100},
        {'name': '技能残页·精通·火神', 'item_id': 'skill_page_fire_2', 'weight': 100},
        {'name': '技能残页·精通·冰封', 'item_id': 'skill_page_ice_2', 'weight': 100},
        {'name': '技能残页·精通·风行', 'item_id': 'skill_page_wind_2', 'weight': 100},
        {'name': '技能残页·精通·磐石', 'item_id': 'skill_page_rock_2', 'weight': 100},
        {'name': '技能残页·精通·驱散', 'item_id': 'skill_page_dispel_2', 'weight': 100},
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
        """Flip a card. Costs 50 jinzu or uses a flip token."""
        done = cls.get_today_value(player, 'card_flip_done')

        # Check for free flip token in inventory
        flip_token = DataService.get_inventory_item(player.id, 'card_flip_token')
        if flip_token and flip_token.quantity > 0:
            DataService.remove_item_from_inventory(player.id, 'card_flip_token', 1)
        elif player.jinzu < 50:
            return False, "金珠不足，需要50金珠"
        else:
            player.jinzu -= 50

        prize = cls._weighted_random(cls.CARD_PRIZES)
        reward_msg = cls._grant_prize(player, prize)
        cls.set_today_value(player, 'card_flip_done', done + 1)

        # Give lucky coin for each flip
        DataService.add_item_to_inventory(player.id, 'lucky_coin', 1)

        db.session.commit()
        return True, reward_msg + "，获得幸运币x1"

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

    # Lucky coin exchange shop
    LUCKY_COIN_EXCHANGE = [
        {'name': '哥姐徽章', 'item_id': 'badge_gejie', 'cost': 500},
        {'name': '装备重塑符', 'item_id': 'equip_reshape_talisman', 'cost': 300},
        {'name': '诸侯令30天', 'item_id': 'duke_token_30d', 'cost': 200},
        {'name': '大银两包', 'item_id': 'money_large', 'cost': 100},
        {'name': '秘药礼包', 'item_id': 'mi_yao_pack', 'cost': 50},
        {'name': '双倍经验卡', 'item_id': 'double_exp_card', 'cost': 50},
        {'name': '副将扩技符', 'item_id': 'lt_skill_expand', 'cost': 80},
        {'name': '副将招募令', 'item_id': 'lt_recruit', 'cost': 30},
        {'name': '强化宝玉', 'item_id': 'enhance_gem', 'cost': 10},
        {'name': '续命灯', 'item_id': 'potion_revive', 'cost': 5},
        {'name': '宝匣钥匙', 'item_id': 'chest_key', 'cost': 15},
        {'name': '活力卡', 'item_id': 'vitality_card', 'cost': 20},
    ]

    @classmethod
    def exchange_lucky_coin(cls, player, item_id):
        """Exchange lucky coins for items."""
        for entry in cls.LUCKY_COIN_EXCHANGE:
            if entry['item_id'] == item_id:
                break
        else:
            return False, "无效的兑换物品"

        coin_item = DataService.get_inventory_item(player.id, 'lucky_coin')
        if not coin_item or coin_item.quantity < entry['cost']:
            return False, f"幸运币不足，需要{entry['cost']}个"

        DataService.remove_item_from_inventory(player.id, 'lucky_coin', entry['cost'])
        DataService.add_item_to_inventory(player.id, item_id, 1)
        db.session.commit()
        return True, f"兑换成功！获得{entry['name']}"