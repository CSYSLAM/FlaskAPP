"""Mountain Villa service."""
import time
import random
from datetime import date, datetime
from services import db
from services.data_service import DataService
from models.villa import Villa
from models.lieutenant import Lieutenant


# Seed definitions for garden - base seeds with hardcoded config
_BASE_SEEDS = {
    'seed_herb': {'name': '草药种子', 'grow_time': 3600, 'harvest': 'herb', 'harvest_name': '草药', 'count': 3, 'ap_cost': 2},
    'seed_flower': {'name': '玫瑰花种子', 'grow_time': 7200, 'harvest': 'flower', 'harvest_name': '玫瑰花', 'count': 2, 'ap_cost': 2},
    'seed_ginseng': {'name': '人参种子', 'grow_time': 14400, 'harvest': 'ginseng', 'harvest_name': '人参', 'count': 2, 'ap_cost': 2},
    # 药品种子
    'seed_jinchuangyao': {'name': '金疮药种子', 'grow_time': 3600, 'harvest': 'potion_heal_100', 'harvest_name': '金疮药', 'count': 1, 'ap_cost': 2, 'min_level': 1},
    'seed_jumosan': {'name': '凝魔散种子', 'grow_time': 3600, 'harvest': 'potion_mana_100', 'harvest_name': '聚魔散', 'count': 1, 'ap_cost': 2, 'min_level': 1},
    'seed_yangshengwan': {'name': '养生丸种子', 'grow_time': 7200, 'harvest': 'potion_heal_200', 'harvest_name': '养生丸', 'count': 1, 'ap_cost': 2, 'min_level': 2},
    'seed_xingshenshui': {'name': '醒神水种子', 'grow_time': 7200, 'harvest': 'potion_mana_200', 'harvest_name': '醒神水', 'count': 1, 'ap_cost': 2, 'min_level': 2},
    'seed_dabuwan': {'name': '大补丸种子', 'grow_time': 14400, 'harvest': 'potion_heal_400', 'harvest_name': '大补丸', 'count': 1, 'ap_cost': 3, 'min_level': 3},
    'seed_yeshanshen': {'name': '野山参种子', 'grow_time': 28800, 'harvest': 'potion_heal_800', 'harvest_name': '野山参', 'count': 1, 'ap_cost': 3, 'min_level': 4},
    'seed_xuelianlu': {'name': '雪莲露种子', 'grow_time': 28800, 'harvest': 'potion_mana_800', 'harvest_name': '雪莲露', 'count': 1, 'ap_cost': 3, 'min_level': 4},
    'seed_zhenzhubei': {'name': '珍珠贝种子', 'grow_time': 43200, 'harvest': 'potion_heal_950', 'harvest_name': '珍珠贝', 'count': 1, 'ap_cost': 4, 'min_level': 5},
    'seed_huanyangdan': {'name': '还阳丹种子', 'grow_time': 43200, 'harvest': 'potion_heal_1150', 'harvest_name': '还阳丹', 'count': 1, 'ap_cost': 4, 'min_level': 5},
    'seed_guanyinshui': {'name': '观音水种子', 'grow_time': 43200, 'harvest': 'potion_mana_1150', 'harvest_name': '观音水', 'count': 1, 'ap_cost': 4, 'min_level': 5},
    'seed_tiancandan': {'name': '天蚕丹种子', 'grow_time': 57600, 'harvest': 'potion_heal_2000', 'harvest_name': '天蚕丹', 'count': 1, 'ap_cost': 5, 'min_level': 6},
    'seed_huashenshui': {'name': '化神水种子', 'grow_time': 57600, 'harvest': 'potion_mana_2000', 'harvest_name': '化神水', 'count': 1, 'ap_cost': 5, 'min_level': 6},
    'seed_shenxuedan': {'name': '神血丹种子', 'grow_time': 57600, 'harvest': 'potion_heal_2250', 'harvest_name': '神血丹', 'count': 1, 'ap_cost': 5, 'min_level': 7},
    'seed_qinglinglu': {'name': '清灵露种子', 'grow_time': 57600, 'harvest': 'potion_mana_2250', 'harvest_name': '清灵露', 'count': 1, 'ap_cost': 5, 'min_level': 7},
    # 经验丹种子
    'exp_seed': {'name': '经验丹种子', 'grow_time': 86400, 'harvest': 'exp_small', 'harvest_name': '小经验丹', 'count': 1, 'ap_cost': 5, 'min_level': 2},
    'seed_big_exp': {'name': '大经验丹种子', 'grow_time': 86400, 'harvest': 'exp_large', 'harvest_name': '大经验丹', 'count': 1, 'ap_cost': 10, 'min_level': 4},
}

# Public SEEDS dict (backward compatible)
SEEDS = _BASE_SEEDS

HARVEST_ITEMS = {
    'herb': 'potion_heal',
    'flower': 'flower_rose',
    'ginseng': 'ginseng',
}


class VillaService:

    TRAINING_DURATION = 8 * 3600  # 8 hours in seconds

    @classmethod
    def get_or_create_villa(cls, player):
        """Get or create villa for player."""
        villa = Villa.query.filter_by(owner_id=player.id).first()
        if not villa:
            villa = Villa(owner_id=player.id, name=f"{player.nickname}的山庄")
            db.session.add(villa)
            db.session.commit()
        cls._check_daily_reset(villa)
        return villa

    @classmethod
    def _check_daily_reset(cls, villa):
        """Check and perform daily reset."""
        today = str(date.today())
        if villa.last_reset_date != today:
            villa.action_points = villa.max_action_points
            villa.blessing_count = 0
            villa.last_reset_date = today
            db.session.commit()

    @classmethod
    def update_name(cls, player, new_name):
        """Update villa name."""
        villa = cls.get_or_create_villa(player)
        if not new_name or len(new_name) > 20:
            return False, "山庄名字长度需在1-20字之间"
        villa.name = new_name
        db.session.commit()
        return True, f"山庄名字已改为【{new_name}】"

    @classmethod
    def set_defender(cls, player, lieutenant_id):
        """Set defender lieutenant for villa."""
        villa = cls.get_or_create_villa(player)
        lt = Lieutenant.query.filter_by(id=lieutenant_id, owner_id=player.id).first()
        if not lt:
            return False, "副将不存在"
        if not lt.is_alive:
            return False, "该副将已阵亡"
        villa.defender_id = lieutenant_id
        db.session.commit()
        return True, f"已安排{lt.name}镇守山庄"

    @classmethod
    def remove_defender(cls, player):
        """Remove defender from villa."""
        villa = cls.get_or_create_villa(player)
        villa.defender_id = None
        db.session.commit()
        return True, "已撤下镇守副将"

    # --- Training (演武场) ---

    @classmethod
    def start_training(cls, player):
        """Start training in training ground."""
        villa = cls.get_or_create_villa(player)

        if villa.action_points < 5:
            return False, "行动力不足，需要5点行动力"

        cost = villa.get_training_cost()
        if player.gold < cost:
            return False, f"银两不足，需要{cost}银两"

        training = villa.training_data
        if training.get('start_time'):
            return False, "正在演武中"

        player.gold -= cost
        villa.action_points -= 5
        training['start_time'] = time.time()
        training['level'] = player.level  # Record level at start
        villa.training_data = training
        db.session.commit()
        return True, f"开始演武，消耗{cost}银两，8小时后可领取奖励"

    @classmethod
    def finish_training(cls, player):
        """Finish training and get reward."""
        villa = cls.get_or_create_villa(player)
        training = villa.training_data

        if not training.get('start_time'):
            return False, "未在演武中"

        elapsed = time.time() - training['start_time']

        if elapsed < 2 * 3600:  # Less than 2 hours
            # No reward, just cancel
            villa.training_data = {}
            db.session.commit()
            return True, "演武不足2小时，无经验奖励"

        # Calculate reward based on time (max 8 hours)
        hours = min(8, elapsed / 3600)
        # If less than 8 hours, get hours/16 of full reward
        if hours < 8:
            exp_reward = int(villa.get_training_exp(hours) * hours / 16)
        else:
            exp_reward = villa.get_training_exp(8)

        # 扣除被其他玩家偷师偷走的经验(最多被偷30%)
        stolen = int(training.get('stolen_exp') or 0)
        if stolen > 0:
            exp_reward = max(0, exp_reward - stolen)

        player.experience += exp_reward

        # Add villa experience
        villa_exp = int(hours * 10)
        villa.experience += villa_exp
        cls._check_level_up(villa)

        villa.training_data = {}
        db.session.commit()
        stolen_tip = f"，其中{stolen}经验被人偷师偷走" if stolen > 0 else ""
        return True, f"演武完成！获得{exp_reward}经验{stolen_tip}，山庄经验+{villa_exp}"

    @classmethod
    def get_training_status(cls, villa):
        """Get training status."""
        training = villa.training_data
        if not training.get('start_time'):
            return {'status': 'idle', 'remaining': 0}

        elapsed = time.time() - training['start_time']
        if elapsed >= cls.TRAINING_DURATION:
            return {'status': 'finished', 'remaining': 0}

        remaining = int(cls.TRAINING_DURATION - elapsed)
        return {'status': 'training', 'remaining': remaining, 'elapsed_hours': elapsed / 3600}

    # --- Garden (百草园) ---

    @classmethod
    def get_garden_status(cls, villa):
        """Get garden status with all plots."""
        garden = villa.garden_data
        slots = villa.get_garden_slots()
        plots = []

        for i in range(slots):
            plot = garden.get(str(i), {'status': 'empty'})
            if plot.get('status') == 'growing':
                seed_id = plot.get('seed_id')
                start_time = plot.get('start_time', 0)
                seed_info = SEEDS.get(seed_id, {})
                grow_time = seed_info.get('grow_time', 3600)
                elapsed = time.time() - start_time

                if elapsed >= grow_time:
                    plot['status'] = 'ready'
                    plot['ready_count'] = seed_info.get('count', 1)
                    garden[str(i)] = plot
                    villa.garden_data = garden
                else:
                    plot['remaining'] = int(grow_time - elapsed)

            plots.append({
                'index': i,
                'status': plot.get('status', 'empty'),
                'seed_id': plot.get('seed_id'),
                'seed_name': SEEDS.get(plot.get('seed_id', ''), {}).get('name', ''),
                'harvest_name': SEEDS.get(plot.get('seed_id', ''), {}).get('harvest_name', ''),
                'ready_count': plot.get('ready_count', 0),
                'remaining': plot.get('remaining', 0)
            })

        db.session.commit()
        return plots

    @classmethod
    def plant_seed(cls, player, plot_index, seed_id):
        """Plant a seed in a plot."""
        villa = cls.get_or_create_villa(player)

        if seed_id not in SEEDS:
            return False, "无效的种子"

        seed_info = SEEDS[seed_id]
        ap_cost = seed_info.get('ap_cost', 2)

        if villa.action_points < ap_cost:
            return False, f"行动力不足，需要{ap_cost}点行动力"

        # Check garden level requirement
        min_level = seed_info.get('min_level', 1)
        if villa.level < min_level:
            return False, f"需要百草园{min_level}级"

        slots = villa.get_garden_slots()
        if plot_index < 0 or plot_index >= slots:
            return False, "无效的土地编号"

        garden = villa.garden_data
        plot = garden.get(str(plot_index), {'status': 'empty'})

        if plot.get('status') not in ('empty', 'harvested'):
            return False, "该土地正在使用中"

        # Check if player has the seed
        inv = DataService.get_inventory_item(player.id, seed_id)
        if not inv or inv.quantity <= 0:
            return False, "没有该种子"

        DataService.remove_item_from_inventory(player.id, seed_id, 1)
        villa.action_points -= ap_cost

        garden[str(plot_index)] = {
            'status': 'growing',
            'seed_id': seed_id,
            'start_time': time.time()
        }
        villa.garden_data = garden
        db.session.commit()
        return True, f"已种植{seed_info['name']}"

    @classmethod
    def harvest_plot(cls, player, plot_index):
        """Harvest a ready plot."""
        villa = cls.get_or_create_villa(player)
        garden = villa.garden_data
        plot = garden.get(str(plot_index), {})

        if plot.get('status') != 'ready':
            return False, "该土地没有可收获的作物"

        seed_id = plot.get('seed_id')
        seed_info = SEEDS.get(seed_id, {})
        harvest_key = seed_info.get('harvest', '')
        # New seeds store item_id directly; old seeds use HARVEST_ITEMS mapping
        harvest_id = HARVEST_ITEMS.get(harvest_key, harvest_key)
        count = seed_info.get('count', 1)
        if plot.get('stolen'):
            count = max(0, count - 1)  # 被偷走过1个

        if harvest_id and count > 0:
            DataService.add_item_to_inventory(player.id, harvest_id, count)

        # Add villa experience
        villa.experience += 5
        cls._check_level_up(villa)

        garden[str(plot_index)] = {'status': 'empty'}
        villa.garden_data = garden
        db.session.commit()
        return True, f"收获了{count}个{seed_info.get('harvest_name', '作物')}"

    @classmethod
    def ripen_plot(cls, player, plot_index):
        """Use a ripening agent to instantly mature a growing crop."""
        villa = cls.get_or_create_villa(player)
        garden = villa.garden_data
        plot = garden.get(str(plot_index), {})

        if plot.get('status') != 'growing':
            return False, "该土地没有正在生长的作物"

        # Check ripening agent
        inv = DataService.get_inventory_item(player.id, 'ripening_agent')
        if not inv or inv.quantity <= 0:
            return False, "没有催熟剂"

        seed_id = plot.get('seed_id')
        seed_info = SEEDS.get(seed_id, {})

        DataService.remove_item_from_inventory(player.id, 'ripening_agent', 1)
        garden[str(plot_index)] = {
            'status': 'ready',
            'seed_id': seed_id,
            'start_time': plot.get('start_time', time.time()),
            'ready_count': seed_info.get('count', 1)
        }
        villa.garden_data = garden
        db.session.commit()
        return True, f"催熟成功，{seed_info.get('harvest_name', '作物')}已成熟"

    # --- Stealing (偷取) ---

    @classmethod
    def get_random_friend_villa(cls, player):
        """Get a random friend's villa for visiting."""
        from models.player import PlayerModel
        # Get friends (simplified: random from all players except self)
        friends = PlayerModel.query.filter(PlayerModel.id != player.id).limit(20).all()
        if not friends:
            return None

        friend = random.choice(friends)
        villa = Villa.query.filter_by(owner_id=friend.id).first()
        if not villa:
            villa = Villa(owner_id=friend.id, name=f"{friend.nickname}的山庄")
            db.session.add(villa)
            db.session.commit()
        return villa, friend

    @classmethod
    def steal_plant(cls, player, target_villa, plot_index):
        """Steal a plant from target villa's garden (偷药)."""
        from models.player import PlayerModel
        from services.achievement_service import AchievementService

        if target_villa.owner_id == player.id:
            return False, "不能偷自己山庄的作物"

        # 确保目标山庄计数(祈福/行动力)为当日最新值
        cls._check_daily_reset(target_villa)

        # 行动力在玩家自己的山庄上
        my_villa = cls.get_or_create_villa(player)
        if my_villa.action_points < 5:
            return False, "行动力不足，需要5点行动力"

        target_player = PlayerModel.query.get(target_villa.owner_id)

        garden = target_villa.garden_data
        plot = garden.get(str(plot_index), {})

        if plot.get('status') != 'ready':
            return False, "该土地没有可偷取的作物"

        # 只出一个果实的作物不给偷；每块地最多被偷一次
        seed_id = plot.get('seed_id')
        seed_info = SEEDS.get(seed_id, {})
        if seed_info.get('count', 1) <= 1:
            return False, "这作物只结一个果实，不给偷"
        if plot.get('stolen'):
            return False, "给主人留一点吧"

        # Check if caught by defender
        defense_power = target_villa.get_defense_power()
        catch_rate = min(0.8, defense_power / 200)  # Max 80% catch rate

        if random.random() < catch_rate:
            # Caught! Pay penalty
            penalty = player.level * 100 + 500
            player.gold = max(0, player.gold - penalty)
            if target_player:
                target_player.gold += penalty

            defender = Lieutenant.query.get(target_villa.defender_id) if target_villa.defender_id else None
            defender_name = defender.name if defender else '守卫'
            target_villa.add_visitor_log(player.nickname, '偷取被抓', f'罚款{penalty}银两')
            caught_count = AchievementService.incr_social_stat(player, 'ach_steal_caught')
            AchievementService.check(player, 'steal_caught', caught_count)
            db.session.commit()
            return False, f"被{defender_name}抓住了！损失{penalty}银两"

        # Success! Steal 1 fruit, plot stays for the owner (每块地最多偷1个)
        harvest_key = seed_info.get('harvest', '')
        # 新种子的 harvest 直接是 item_id，旧种子走 HARVEST_ITEMS 映射
        harvest_id = HARVEST_ITEMS.get(harvest_key, harvest_key)

        if harvest_id:
            DataService.add_item_to_inventory(player.id, harvest_id, 1)

        plot['stolen'] = True
        if plot.get('ready_count'):
            plot['ready_count'] = max(0, plot['ready_count'] - 1)
        garden[str(plot_index)] = plot
        target_villa.garden_data = garden
        target_villa.add_visitor_log(player.nickname, '偷摘', f'{seed_info.get("harvest_name", "作物")}x1')

        my_villa.action_points -= 5
        steal_count = AchievementService.incr_social_stat(player, 'ach_steal_medicine')
        AchievementService.check(player, 'steal_medicine_success', steal_count)
        db.session.commit()
        return True, f"成功偷取了1个{seed_info.get('harvest_name', '作物')}"

    @classmethod
    def steal_training(cls, player, target_villa):
        """Steal training exp from target villa (偷师)."""
        from models.player import PlayerModel
        from services.achievement_service import AchievementService

        if target_villa.owner_id == player.id:
            return False, "不能偷自己山庄的演武"

        # 确保目标山庄计数(祈福/行动力)为当日最新值
        cls._check_daily_reset(target_villa)

        # 行动力在玩家自己的山庄上
        my_villa = cls.get_or_create_villa(player)
        if my_villa.action_points < 5:
            return False, "行动力不足，需要5点行动力"

        target_player = PlayerModel.query.get(target_villa.owner_id)

        training = target_villa.training_data
        if not training.get('start_time'):
            return False, "目标未在演武"

        # 只有演武完成(8小时)才能被偷师，演武过程中无法偷师
        elapsed = time.time() - training['start_time']
        if elapsed < cls.TRAINING_DURATION:
            return False, "目标演武尚未完成，无法偷师"

        # 每场演武最多被偷30%经验，主人至少能领70%
        full_exp = target_villa.get_training_exp(8)
        stolen_so_far = int(training.get('stolen_exp') or 0)
        max_stealable = int(full_exp * 0.3)
        if stolen_so_far >= max_stealable:
            return False, "演武经验已经被偷光了，给主人留一点吧"

        # Check if caught by defender
        defense_power = target_villa.get_defense_power()
        catch_rate = min(0.8, defense_power / 200)

        if random.random() < catch_rate:
            penalty = player.level * 100 + 500
            player.gold = max(0, player.gold - penalty)
            if target_player:
                target_player.gold += penalty

            defender = Lieutenant.query.get(target_villa.defender_id) if target_villa.defender_id else None
            defender_name = defender.name if defender else '守卫'
            target_villa.add_visitor_log(player.nickname, '偷演武被抓', f'罚款{penalty}银两')
            caught_count = AchievementService.incr_social_stat(player, 'ach_steal_caught')
            AchievementService.check(player, 'steal_caught', caught_count)
            db.session.commit()
            return False, f"被{defender_name}抓住了！损失{penalty}银两"

        # Success! 每次偷当前演武经验的1%~5%，累计不超过30%
        pct = random.uniform(0.01, 0.05)
        stolen_exp = min(int(full_exp * pct), max_stealable - stolen_so_far)
        if stolen_exp < 1:
            stolen_exp = 1

        player.experience += stolen_exp
        my_villa.action_points -= 5

        # 从目标演武扣除被偷经验，主人领取时相应减少
        training['stolen_exp'] = stolen_so_far + stolen_exp
        target_villa.training_data = training

        target_villa.add_visitor_log(player.nickname, '偷演武', f'偷取{stolen_exp}经验')
        steal_count = AchievementService.incr_social_stat(player, 'ach_steal_skill')
        AchievementService.check(player, 'steal_skill_success', steal_count)
        db.session.commit()
        return True, f"成功偷取了{stolen_exp}经验"

    # --- Blessing (祈福) ---

    @classmethod
    def bless_villa(cls, player, target_villa):
        """Bless a villa (祈福)."""
        from services.achievement_service import AchievementService

        if target_villa.owner_id == player.id:
            return False, "不能给自己的山庄祈福，去好友的山庄祈福吧"

        # 确保目标山庄祈福计数为当日最新值(跨天清零)
        cls._check_daily_reset(target_villa)

        if player.gold < 100:
            return False, "银两不足，需要100银两"

        if target_villa.blessing_count >= 10:
            return False, "祈福次数已满"

        player.gold -= 100
        target_villa.blessing_count += 1

        # Give player some exp for blessing
        player.experience += 50

        bless_count = AchievementService.incr_social_stat(player, 'ach_bless_count')
        AchievementService.check(player, 'bless_count', bless_count)

        db.session.commit()
        return True, "祈福成功，获得50经验"

    # 祈福礼包抽奖池: 打造材料50% / 孔明灯30% / 强化宝玉10% / 宝匣钥匙5% / 神游果5%
    BLESS_CRAFT_MATERIALS = {
        'craft_suipi': '碎皮', 'craft_mabu': '麻布', 'craft_huangyangmu': '黄杨木', 'craft_huangtongkuang': '黄铜矿',
        'craft_yingpi': '硬皮', 'craft_mianbu': '棉布', 'craft_chenxiangmu': '沉香木', 'craft_heitiekuang': '黑铁矿',
        'craft_houpi': '厚皮', 'craft_nirong': '呢绒', 'craft_zitanmu': '紫檀木', 'craft_jingjinkuang': '精金矿',
    }

    @classmethod
    def claim_blessing_reward(cls, player):
        """Claim blessing gift pack when count reaches 10. 每日限领一次，祈福次数次日重置。"""
        villa = cls.get_or_create_villa(player)

        if villa.blessing_count < 10:
            return False, "祈福次数不足10次"

        data = player.activity_data or {}
        today = str(date.today())
        if data.get('bless_claim_date') == today:
            return False, "今日已领取过祈福礼包，祈福次数次日更新"

        roll = random.random()
        if roll < 0.50:
            mat_id = random.choice(list(cls.BLESS_CRAFT_MATERIALS.keys()))
            DataService.add_item_to_inventory(player.id, mat_id, 3)
            reward_name = f"{cls.BLESS_CRAFT_MATERIALS[mat_id]}×3"
        elif roll < 0.80:
            DataService.add_item_to_inventory(player.id, 'kongming_lantern', 1)
            reward_name = "孔明灯×1"
        elif roll < 0.90:
            DataService.add_item_to_inventory(player.id, 'enhance_gem', 1)
            reward_name = "强化宝玉×1"
        elif roll < 0.95:
            DataService.add_item_to_inventory(player.id, 'chest_key', 1)
            reward_name = "宝匣钥匙×1"
        else:
            DataService.add_item_to_inventory(player.id, 'shenyou_guo', 1)
            reward_name = "神游果×1"

        data['bless_claim_date'] = today
        player.activity_data = data
        # 当天领完不清零，次日由 _check_daily_reset 重置祈福次数
        db.session.commit()
        return True, f"领取祈福礼包：{reward_name}"

    # --- Level up ---

    @classmethod
    def _check_level_up(cls, villa):
        """Check and perform level up."""
        while villa.level < 100 and villa.experience >= villa.get_exp_to_next_level():
            villa.experience -= villa.get_exp_to_next_level()
            villa.level += 1
            villa.max_action_points = 120 + (villa.level - 1) * 2
            villa.action_points = min(villa.action_points + 20, villa.max_action_points)
