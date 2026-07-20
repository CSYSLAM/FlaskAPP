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
        'daily_tasks': {'name': '每日任务', 'max': 10, 'points': 10},
    }

    # Daily NPC task definitions (任务使者)
    DAILY_NPC_TASKS = [
        {
            'id': 'daily_money',
            'name': '日·金钱任务',
            'min_level': 30,
            'reward_type': 'gold',
            'reward_amount': 2000,
            'reward_text': '银两+2000',
        },
        {
            'id': 'daily_exp',
            'name': '日·经验任务',
            'min_level': 30,
            'reward_type': 'exp',
            'reward_amount': 20000,
            'reward_text': '经验+20000',
        },
    ]

    # Country -> city info for task NPC and target monsters
    COUNTRY_CITY = {
        '魏': {'name': '北平', 'center': 'beiping_center.广场', 'north': 'beiping_north',
               'target_monster': '冀州步兵', 'target_count': 10, 'scene': '燕山'},
        '蜀': {'name': '建宁', 'center': 'jianing_center.广场', 'north': 'jianing_north',
               'target_monster': '流民', 'target_count': 10, 'scene': '金雁塔'},
        '吴': {'name': '吴郡', 'center': 'wujun_center.广场', 'north': 'wujun_north',
               'target_monster': '淘金者', 'target_count': 10, 'scene': '涌金洞'},
    }

    # Activity points reward tiers (活跃度领奖)
    ACTIVITY_REWARD_TIERS = {
        30: {'name': '活跃度30奖励', 'items': [('potion_heal', 10), ('potion_mana', 10)], 'yuanbao': 3},
        50: {'name': '活跃度50奖励', 'items': [('enhance_gem', 2), ('money_small', 1)], 'yuanbao': 5},
        80: {'name': '活跃度80奖励', 'items': [('enhance_gem', 3), ('potion_revive', 2), ('money_large', 1)], 'yuanbao': 10},
        100: {'name': '活跃度100奖励', 'items': [('potion_package', 1), ('double_exp_card', 1), ('bag_expand', 1)], 'yuanbao': 20},
    }

    # Smash egg prize pool (weighted random) - 52 items matching reference server
    EGG_PRIZES = [
        {'name': '哥姐徽章', 'item_id': 'badge_gejie', 'weight': 1},             # 0.001%
        {'name': '秘药礼包', 'item_id': 'potion_package', 'weight': 5000},          # 5%
        {'name': '双倍经验卡', 'item_id': 'double_exp_card', 'weight': 5000},     # 5%
        {'name': '神游果', 'item_id': 'shenyou_guo', 'weight': 2000},           # 2%
        {'name': '背包扩容卷', 'item_id': 'bag_expand', 'weight': 5000},          # 5%
        {'name': '玫瑰花', 'item_id': 'flower_rose', 'weight': 5000},                   # 5%
        {'name': '小喇叭', 'item_id': 'horn_small', 'weight': 2000},             # 2%
        {'name': '续命灯', 'item_id': 'potion_revive', 'weight': 5000},          # 5%
        {'name': '强化宝玉', 'item_id': 'enhance_gem', 'weight': 5000},           # 5%
        {'name': '宝匣钥匙', 'item_id': 'chest_key', 'weight': 2000},            # 2%
        {'name': '追杀令', 'item_id': 'hunt_order', 'weight': 1000},             # 1%
        {'name': '新婚草戒包', 'item_id': 'wedding_ring_pack', 'weight': 1000},  # 1%
        {'name': '诸侯令1天', 'item_id': 'duke_token_1d', 'weight': 2000},      # 2%
        {'name': '诸侯令7天', 'item_id': 'duke_token_7d', 'weight': 500},       # 0.5%
        {'name': '小银两包', 'item_id': 'money_small', 'weight': 100},           # 0.1%
        {'name': '玫瑰花种子', 'item_id': 'seed_flower', 'weight': 5000},          # 5%
        {'name': '经验丹种子', 'item_id': 'exp_seed', 'weight': 2000},           # 2%
        {'name': '大经验丹种子', 'item_id': 'seed_big_exp', 'weight': 1000},     # 1%
        {'name': '催熟剂', 'item_id': 'ripening_agent', 'weight': 3000},         # 3%
        {'name': '大血石', 'item_id': 'blood_stone_large', 'weight': 2000},           # 2%
        {'name': '大魔石', 'item_id': 'mana_stone_large', 'weight': 2000},           # 2%
        {'name': '活力卡', 'item_id': 'vitality_card', 'weight': 3000},          # 3%
        {'name': '聚魂幡碎片', 'item_id': 'soul_flag_shard', 'weight': 3000},    # 3%
        {'name': '副将招募令', 'item_id': 'lt_recruit', 'weight': 3000},          # 3%
        {'name': '副将低级经验丹', 'item_id': 'lt_exp_low', 'weight': 3000},     # 3%
        {'name': '副将中级经验丹', 'item_id': 'lt_exp_mid', 'weight': 3000},     # 3%
        {'name': '副将高级经验丹', 'item_id': 'lt_exp_high', 'weight': 3000},    # 3%
        {'name': '副将资质丹', 'item_id': 'lt_aptitude', 'weight': 3000},         # 3%
        {'name': '副将增寿丹', 'item_id': 'lt_life', 'weight': 3000},            # 3%
        {'name': '副将忠诚丹', 'item_id': 'lt_loyalty', 'weight': 3000},         # 3%
        {'name': '副将强化丹', 'item_id': 'lt_enhance', 'weight': 3000},         # 3%
        {'name': '副将悟性丹', 'item_id': 'lt_wuxing', 'weight': 3000},          # 3%
        {'name': '碎皮', 'item_id': 'craft_suipi', 'weight': 700},                    # 0.7%
        {'name': '黄杨木', 'item_id': 'craft_huangyangmu', 'weight': 700},            # 0.7%
        {'name': '麻布', 'item_id': 'craft_mabu', 'weight': 700},                     # 0.7%
        {'name': '黄铜矿', 'item_id': 'craft_huangtongkuang', 'weight': 700},         # 0.7%
        {'name': '硬皮', 'item_id': 'craft_yingpi', 'weight': 500},                   # 0.5%
        {'name': '沉香木', 'item_id': 'craft_chenxiangmu', 'weight': 500},            # 0.5%
        {'name': '棉布', 'item_id': 'craft_mianbu', 'weight': 500},                   # 0.5%
        {'name': '黑铁矿', 'item_id': 'craft_heitiekuang', 'weight': 500},            # 0.5%
        {'name': '厚皮', 'item_id': 'craft_houpi', 'weight': 300},               # 0.3%
        {'name': '紫檀木', 'item_id': 'craft_zitanmu', 'weight': 300},                # 0.3%
        {'name': '呢绒', 'item_id': 'craft_nirong', 'weight': 300},              # 0.3%
        {'name': '精金矿', 'item_id': 'craft_jingjinkuang', 'weight': 300},           # 0.3%
        {'name': '技能残页', 'item_id': 'skill_page', 'weight': 5400},
    ]

    # Card flip prize pool - 72 items matching reference server
    CARD_PRIZES = [
        {'name': '哥姐徽章', 'item_id': 'badge_gejie', 'weight': 1},             # 0.001%
        {'name': '副将扩技符', 'item_id': 'lt_skill_expand', 'weight': 1},       # 0.001%
        {'name': '装备重塑符', 'item_id': 'equip_reshape_talisman', 'weight': 1},# 0.001%
        {'name': '秘药礼包', 'item_id': 'potion_package', 'weight': 5000},          # 5%
        {'name': '双倍经验卡', 'item_id': 'double_exp_card', 'weight': 5000},     # 5%
        {'name': '神游果', 'item_id': 'shenyou_guo', 'weight': 2000},           # 2%
        {'name': '背包扩容卷', 'item_id': 'bag_expand', 'weight': 5000},          # 5%
        {'name': '玫瑰花x2', 'item_id': 'flower_rose', 'count': 2, 'weight': 5000},     # 5%
        {'name': '小喇叭', 'item_id': 'horn_small', 'weight': 2000},             # 2%
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
        {'name': '玫瑰花种子', 'item_id': 'seed_flower', 'weight': 5000},          # 5%
        {'name': '经验丹种子', 'item_id': 'exp_seed', 'weight': 2000},           # 2%
        {'name': '大经验丹种子', 'item_id': 'seed_big_exp', 'weight': 1000},     # 1%
        {'name': '催熟剂', 'item_id': 'ripening_agent', 'weight': 3000},         # 3%
        {'name': '大血石', 'item_id': 'blood_stone_large', 'weight': 2000},           # 2%
        {'name': '大魔石', 'item_id': 'mana_stone_large', 'weight': 2000},           # 2%
        {'name': '活力卡', 'item_id': 'vitality_card', 'weight': 3000},          # 3%
        {'name': '聚魂幡碎片', 'item_id': 'soul_flag_shard', 'weight': 3000},    # 3%
        {'name': '副将招募令', 'item_id': 'lt_recruit', 'weight': 3000},          # 3%
        {'name': '副将低级经验丹', 'item_id': 'lt_exp_low', 'weight': 3000},     # 3%
        {'name': '副将中级经验丹', 'item_id': 'lt_exp_mid', 'weight': 3000},     # 3%
        {'name': '副将高级经验丹', 'item_id': 'lt_exp_high', 'weight': 3000},    # 3%
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
        {'name': '技能残页', 'item_id': 'skill_page', 'weight': 7100},
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
        data = player.activity_data
        today = str(date.today())
        daily = data.get('daily', {})
        if daily.get('_date') != today:
            return 0
        for key, info in cls.DAILY_ACTIVITIES.items():
            if key == 'daily_tasks':
                tasks = daily.get('npc_tasks', {})
                done = sum(1 for t in tasks.values() if t.get('accepted'))
            else:
                done = daily.get(f'{key}_done', 0)
            max_val = info['max']
            if done >= max_val:
                total += info['points']
        return total

    @classmethod
    def get_daily_progress(cls, player):
        """Get all daily activity progress."""
        result = []
        data = player.activity_data
        today = str(date.today())
        daily = data.get('daily', {})
        if daily.get('_date') != today:
            daily = {}
        for key, info in cls.DAILY_ACTIVITIES.items():
            if key == 'daily_tasks':
                # Count accepted tasks (including completed/claimed)
                tasks = daily.get('npc_tasks', {})
                done = sum(1 for t in tasks.values() if t.get('accepted'))
            else:
                done = daily.get(f'{key}_done', 0)
            result.append({
                'key': key,
                'name': info['name'],
                'done': done,
                'max': info['max'],
                'points': info['points'],
                'completed': done >= info['max'],
            })
        return result

    @classmethod
    def get_claimed_tiers(cls, player):
        """Get list of already-claimed reward tier thresholds for today."""
        data = player.activity_data
        today = str(date.today())
        daily = data.get('daily', {})
        if daily.get('_date') != today:
            return []
        return daily.get('claimed_tiers', [])

    @classmethod
    def get_reward_tiers_status(cls, player):
        """Get status of all reward tiers for display."""
        current_points = cls.get_total_activity_points(player)
        claimed = cls.get_claimed_tiers(player)
        result = []
        for tier_points, reward in cls.ACTIVITY_REWARD_TIERS.items():
            claimable = current_points >= tier_points and tier_points not in claimed
            result.append({
                'tier_points': tier_points,
                'name': reward['name'],
                'claimed': tier_points in claimed,
                'claimable': claimable,
                'locked': current_points < tier_points,
                'items': reward['items'],
                'yuanbao': reward['yuanbao'],
            })
        return result

    @classmethod
    def claim_activity_reward(cls, player, tier_points):
        """Claim a reward at the given activity points tier."""
        if tier_points not in cls.ACTIVITY_REWARD_TIERS:
            return False, "无效的奖励档位"

        current_points = cls.get_total_activity_points(player)
        if current_points < tier_points:
            return False, f"活跃度不足{tier_points}，当前{current_points}"

        claimed = cls.get_claimed_tiers(player)
        if tier_points in claimed:
            return False, "该奖励今日已领取"

        reward = cls.ACTIVITY_REWARD_TIERS[tier_points]

        for item_id, count in reward.get('items', []):
            DataService.add_item_to_inventory(player.id, item_id, count)

        player.yuanbao += reward.get('yuanbao', 0)

        data = player.activity_data
        today = str(date.today())
        daily = data.get('daily', {})
        if daily.get('_date') != today:
            daily = {'_date': today}
        claimed_list = daily.get('claimed_tiers', [])
        claimed_list.append(tier_points)
        daily['claimed_tiers'] = claimed_list
        data['daily'] = daily
        player.activity_data = data

        db.session.commit()
        return True, f"领取【{reward['name']}】成功！"

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
            player.yuanbao_spent = (player.yuanbao_spent or 0) + 50
        prize = cls._weighted_random(cls.EGG_PRIZES)
        reward_msg = cls._grant_prize(player, prize)

        # 系统公告
        prize_name = prize.get('name', '奖励')
        DataService.broadcast_system(f"{player.nickname}参与砸蛋活动：拿下了{prize_name}，太有实力啦！")

        db.session.commit()
        from services.achievement_service import AchievementService
        AchievementService.check(player, 'yuanbao_spent', player.yuanbao_spent)
        return True, reward_msg
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
            player.jinzu_spent = (player.jinzu_spent or 0) + 50
        reward_msg = cls._grant_prize(player, prize)
        cls.set_today_value(player, 'card_flip_done', done + 1)

        # Give lucky coin for each flip
        DataService.add_item_to_inventory(player.id, 'lucky_coin', 1)

        # 系统公告
        prize_name = prize.get('name', '奖励')
        DataService.broadcast_system(f"{player.nickname}参与翻牌活动：拿下了{prize_name}，太有实力啦！")

        db.session.commit()
        from services.achievement_service import AchievementService
        AchievementService.check(player, 'jinzu_spent', player.jinzu_spent)
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
        {'name': '秘药礼包', 'item_id': 'potion_package', 'cost': 50},
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

    # --- Daily NPC Tasks (任务使者) ---

    @classmethod
    def get_daily_task_progress(cls, player, task_id):
        """Get progress for a daily NPC task. Returns dict with accepted, killed, completed, claimed."""
        data = player.activity_data
        today = str(date.today())
        daily = data.get('daily', {})
        if daily.get('_date') != today:
            return {'accepted': False, 'killed': 0, 'completed': False, 'claimed': False}
        tasks = daily.get('npc_tasks', {})
        t = tasks.get(task_id, {})
        return {
            'accepted': t.get('accepted', False),
            'killed': t.get('killed', 0),
            'completed': t.get('completed', False),
            'claimed': t.get('claimed', False),
        }

    @classmethod
    def accept_daily_task(cls, player, task_id):
        """Accept a daily NPC task."""
        task_def = None
        for t in cls.DAILY_NPC_TASKS:
            if t['id'] == task_id:
                task_def = t
                break
        if not task_def:
            return False, "无效的任务"

        if player.level < task_def['min_level']:
            return False, f"需要{task_def['min_level']}级才能接受此任务"

        progress = cls.get_daily_task_progress(player, task_id)
        if progress['accepted']:
            return False, "今日已接受此任务"

        if progress['claimed']:
            return False, "今日已完成此任务"

        data = player.activity_data
        today = str(date.today())
        daily = data.get('daily', {})
        if daily.get('_date') != today:
            daily = {'_date': today}
        tasks = daily.get('npc_tasks', {})
        tasks[task_id] = {'accepted': True, 'killed': 0, 'completed': False, 'claimed': False}
        daily['npc_tasks'] = tasks
        data['daily'] = daily
        player.activity_data = data
        db.session.commit()
        return True, f"接受任务【{task_def['name']}】成功！"

    @classmethod
    def record_daily_task_kill(cls, player, monster_name):
        """Record a kill for active daily NPC tasks. Call after defeating a monster."""
        city_info = cls.COUNTRY_CITY.get(player.country, cls.COUNTRY_CITY['魏'])
        target_monster = city_info['target_monster']
        target_count = city_info['target_count']
        if monster_name != target_monster:
            return

        data = player.activity_data
        today = str(date.today())
        daily = data.get('daily', {})
        if daily.get('_date') != today:
            return
        tasks = daily.get('npc_tasks', {})
        updated = False
        for task_def in cls.DAILY_NPC_TASKS:
            tid = task_def['id']
            t = tasks.get(tid)
            if not t or not t.get('accepted') or t.get('claimed'):
                continue
            t['killed'] = t.get('killed', 0) + 1
            if t['killed'] >= target_count:
                t['completed'] = True
            updated = True
        if updated:
            daily['npc_tasks'] = tasks
            data['daily'] = daily
            player.activity_data = data

    @classmethod
    def complete_daily_task(cls, player, task_id):
        """Complete a daily NPC task and claim reward."""
        task_def = None
        for t in cls.DAILY_NPC_TASKS:
            if t['id'] == task_id:
                task_def = t
                break
        if not task_def:
            return False, "无效的任务"

        progress = cls.get_daily_task_progress(player, task_id)
        if not progress['accepted']:
            return False, "请先接受任务"
        if progress['claimed']:
            return False, "今日已领取此任务奖励"
        city_info = cls.COUNTRY_CITY.get(player.country, cls.COUNTRY_CITY['魏'])
        target_count = city_info['target_count']
        if not progress['completed']:
            return False, f"任务未完成（{progress['killed']}/{target_count}）"

        # Grant reward
        if task_def['reward_type'] == 'gold':
            player.gold += task_def['reward_amount']
        elif task_def['reward_type'] == 'exp':
            player.experience += task_def['reward_amount']

        # Mark claimed
        data = player.activity_data
        daily = data.get('daily', {})
        tasks = daily.get('npc_tasks', {})
        tasks[task_id] = {'accepted': True, 'killed': target_count, 'completed': True, 'claimed': True}
        daily['npc_tasks'] = tasks

        # Increment daily tasks done count for activity points
        daily_tasks_done = daily.get('daily_tasks_done', 0) + 1
        daily['daily_tasks_done'] = daily_tasks_done

        data['daily'] = daily
        player.activity_data = data
        db.session.commit()
        return True, f"任务完成！获得{task_def['reward_text']}"

    @classmethod
    def get_daily_tasks_status(cls, player):
        """Get status of all daily NPC tasks for display."""
        city_info = cls.COUNTRY_CITY.get(player.country, cls.COUNTRY_CITY['魏'])
        result = []
        for task_def in cls.DAILY_NPC_TASKS:
            progress = cls.get_daily_task_progress(player, task_def['id'])
            level_ok = player.level >= task_def['min_level']
            result.append({
                'id': task_def['id'],
                'name': task_def['name'],
                'min_level': task_def['min_level'],
                'level_ok': level_ok,
                'description': f'前往「{city_info["scene"]}」({city_info["name"]}北区)收拾{city_info["target_count"]}只『{city_info["target_monster"]}』',
                'killed': progress['killed'],
                'target_count': city_info['target_count'],
                'accepted': progress['accepted'],
                'completed': progress['completed'],
                'claimed': progress['claimed'],
                'reward_text': task_def['reward_text'],
                'city_name': city_info['name'],
            })
        return result

    @classmethod
    def get_task_npc_location(cls, player):
        """Get the location of the task NPC for the player's country."""
        city_info = cls.COUNTRY_CITY.get(player.country, cls.COUNTRY_CITY['魏'])
        return city_info['center']

    @classmethod
    def get_task_target_location(cls, player):
        """Get the location where task target monsters are."""
        city_info = cls.COUNTRY_CITY.get(player.country, cls.COUNTRY_CITY['魏'])
        return city_info['north'] + '.' + city_info['scene']