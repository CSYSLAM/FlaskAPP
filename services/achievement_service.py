from services import db
from services.data_service import DataService
from models.player import Achievement
from services.achievement_catalog import ALIGNED_CATEGORIES


class AchievementService:

    @classmethod
    def check_all(cls, player):
        for ctype in ['level', 'kill', 'elite_kill', 'elite_kill_area', 'elite_kill_monster', 'kill_monster',
                       'divine_beast_kill', 'pk_win', 'pk_loss', 'enhance', 'enhance_success', 'enhance_fail',
                       'enhance_50', 'forge', 'artifact_owned',
                       'visit', 'equip_full', 'gold_earned', 'gold_total', 'yuanbao_spent', 'jinzu_spent', 'gift', 'chat', 'vip_level',
                       'lieutenant_owned', 'item_use', 'dungeon_clear', 'dungeon_tower',
                       'boss_kill', 'quest', 'quest_done',
                       'flower_received', 'friend_count', 'bless_count',
                       'steal_skill_success', 'steal_medicine_success', 'steal_caught']:
            cls.check(player, ctype)

    @classmethod
    def check(cls, player, condition_type, current_value=None):
        achievements = DataService.get_achievements()
        for aid, adef in achievements.items():
            if adef['condition_type'] != condition_type:
                continue
            if cls.is_completed(player.id, aid):
                continue
            if current_value is not None:
                if current_value >= adef['condition_value']:
                    cls._complete(player, aid)
            elif cls._check_condition(player, adef):
                cls._complete(player, aid)

    @classmethod
    def _check_condition(cls, player, adef):
        ctype = adef['condition_type']
        val = adef['condition_value']
        if ctype == 'level':
            return player.level >= val
        elif ctype == 'kill':
            return player.kill_count >= val
        elif ctype == 'elite_kill':
            return player.elite_kill_count >= val
        elif ctype == 'pk_win':
            return player.pk_win_count >= val
        elif ctype == 'pk_loss':
            return (player.pk_loss_count or 0) >= val
        elif ctype == 'enhance':
            from models.player import EquipmentInstance
            max_enh = db.session.query(
                db.func.max(EquipmentInstance.enhance_level)).filter_by(
                player_id=player.id).scalar() or 0
            return max_enh >= val
        elif ctype == 'visit':
            return len(player.visited_locations) >= val
        elif ctype == 'equip_full':
            equipped = DataService.get_equipped(player.id)
            count = sum(1 for v in equipped.values() if v is not None)
            return count >= val
        elif ctype == 'gold_earned':
            return player.gold_earned >= val
        elif ctype == 'gold_total':
            return (player.gold + player.warehouse_gold) >= val
        elif ctype == 'yuanbao_spent':
            return (player.yuanbao_spent or 0) >= val
        elif ctype == 'jinzu_spent':
            return (player.jinzu_spent or 0) >= val
        elif ctype == 'gift':
            return player.gift_count >= val
        elif ctype == 'chat':
            return player.chat_count >= val
        elif ctype == 'flower_received':
            return (player.charm or 0) >= val
        elif ctype == 'friend_count':
            return cls._get_friend_count(player) >= val
        elif ctype == 'bless_count':
            return cls._get_social_stat(player, 'ach_bless_count') >= val
        elif ctype == 'steal_skill_success':
            return cls._get_social_stat(player, 'ach_steal_skill') >= val
        elif ctype == 'steal_medicine_success':
            return cls._get_social_stat(player, 'ach_steal_medicine') >= val
        elif ctype == 'steal_caught':
            return cls._get_social_stat(player, 'ach_steal_caught') >= val
        elif ctype == 'vip_level':
            return player.vip_level >= val
        elif ctype == 'lieutenant_owned':
            from models.lieutenant import Lieutenant
            name = adef.get('lt_name', '')
            return Lieutenant.query.filter_by(owner_id=player.id, name=name).first() is not None
        elif ctype == 'item_use':
            return cls._get_item_use_progress(player, adef) >= val
        elif ctype == 'dungeon_clear':
            return cls._get_dungeon_clear_progress(player, adef) >= val
        elif ctype == 'dungeon_tower':
            return cls._get_dungeon_tower_progress(player, adef) >= val
        elif ctype == 'boss_kill':
            return cls._get_boss_kill_progress(player, adef) >= val
        elif ctype == 'elite_kill_area':
            return cls._get_elite_kill_area_progress(player, adef) >= val
        elif ctype == 'elite_kill_monster':
            return cls._get_elite_kill_monster_progress(player, adef) >= val
        elif ctype == 'kill_monster':
            return cls._get_kill_monster_progress(player, adef) >= val
        elif ctype == 'divine_beast_kill':
            return cls._get_divine_beast_kill_progress(player, adef) >= val
        elif ctype == 'forge':
            return (player.forge_count or 0) >= val
        elif ctype == 'enhance_success':
            return (player.enhance_success_count or 0) >= val
        elif ctype == 'enhance_fail':
            return (player.enhance_fail_count or 0) >= val
        elif ctype == 'enhance_50':
            return (player.enhance_50_count or 0) >= val
        elif ctype == 'artifact_owned':
            return cls._get_artifact_owned_progress(player, adef) >= val
        elif ctype == 'quest':
            return cls._get_quest_progress(player, adef) >= val
        elif ctype == 'quest_done':
            return cls._get_quest_done_progress(player, adef) >= val
        return False

    @classmethod
    def _complete(cls, player, achievement_id):
        if cls.is_completed(player.id, achievement_id):
            return
        db.session.add(Achievement(
            player_id=player.id,
            achievement_id=achievement_id,
            claimed=False
        ))
        db.session.flush()

    @classmethod
    def claim(cls, player, achievement_id):
        from services.title_service import TitleService
        record = Achievement.query.filter_by(
            player_id=player.id, achievement_id=achievement_id).first()
        if not record:
            return False, "成就未完成"
        if record.claimed:
            return False, "已领取"
        adef = DataService.get_achievements().get(achievement_id)
        if not adef:
            return False, "成就不存在"
        record.claimed = True
        for stat, value in adef.get('reward', {}).items():
            if stat == 'title':
                # Grant a title
                TitleService.grant_title(player, value, 'prefix' if value.startswith('prefix') else 'suffix')
            elif hasattr(player, stat):
                current = getattr(player, stat) or 0
                setattr(player, stat, current + value)
        DataService.broadcast_system(f"{player.nickname}完成了{adef['name']}成就，太有实力了！")
        return True, "领取成功"

    @classmethod
    def is_completed(cls, player_id, achievement_id):
        return Achievement.query.filter_by(
            player_id=player_id, achievement_id=achievement_id).first() is not None

    @classmethod
    def is_claimed(cls, player_id, achievement_id):
        record = Achievement.query.filter_by(
            player_id=player_id, achievement_id=achievement_id).first()
        return record is not None and record.claimed

    @classmethod
    def get_all(cls, player):
        achievements = DataService.get_achievements()
        categories = DataService.get_achievement_categories()
        result = {cat: [] for cat in categories}
        records = Achievement.query.filter_by(player_id=player.id).all()
        completed_map = {a.achievement_id: a for a in records}

        for aid, adef in achievements.items():
            cat = cls._normalize_category(adef)
            progress = cls._get_progress(player, aid, adef)
            record = completed_map.get(aid)
            entry = {
                'id': aid,
                'name': adef['name'],
                'description': adef['description'],
                'reward': adef.get('reward', {}),
                'points': adef.get('points', 0),
                'completed': record is not None,
                'claimed': record.claimed if record else False,
                'progress': progress,
                'condition_value': adef['condition_value'],
            }
            if cat in result:
                result[cat].append(entry)
            else:
                result['成长'].append(entry)

        return result, categories

    @classmethod
    def _get_progress(cls, player, aid, adef):
        ctype = adef['condition_type']
        if ctype == 'level':
            return player.level
        elif ctype == 'kill':
            return player.kill_count or 0
        elif ctype == 'elite_kill':
            return player.elite_kill_count or 0
        elif ctype == 'pk_win':
            return player.pk_win_count or 0
        elif ctype == 'pk_loss':
            return player.pk_loss_count or 0
        elif ctype == 'enhance':
            from models.player import EquipmentInstance
            return db.session.query(
                db.func.max(EquipmentInstance.enhance_level)).filter_by(
                player_id=player.id).scalar() or 0
        elif ctype == 'visit':
            return len(player.visited_locations)
        elif ctype == 'equip_full':
            equipped = DataService.get_equipped(player.id)
            return sum(1 for v in equipped.values() if v is not None)
        elif ctype == 'gold_earned':
            return player.gold_earned or 0
        elif ctype == 'gold_total':
            return (player.gold or 0) + (player.warehouse_gold or 0)
        elif ctype == 'yuanbao_spent':
            return player.yuanbao_spent or 0
        elif ctype == 'jinzu_spent':
            return player.jinzu_spent or 0
        elif ctype == 'gift':
            return player.gift_count or 0
        elif ctype == 'chat':
            return player.chat_count or 0
        elif ctype == 'flower_received':
            return player.charm or 0
        elif ctype == 'friend_count':
            return cls._get_friend_count(player)
        elif ctype == 'bless_count':
            return cls._get_social_stat(player, 'ach_bless_count')
        elif ctype == 'steal_skill_success':
            return cls._get_social_stat(player, 'ach_steal_skill')
        elif ctype == 'steal_medicine_success':
            return cls._get_social_stat(player, 'ach_steal_medicine')
        elif ctype == 'steal_caught':
            return cls._get_social_stat(player, 'ach_steal_caught')
        elif ctype == 'lieutenant_owned':
            from models.lieutenant import Lieutenant
            name = adef.get('lt_name', '')
            return 1 if Lieutenant.query.filter_by(owner_id=player.id, name=name).first() else 0
        elif ctype == 'item_use':
            return cls._get_item_use_progress(player, adef)
        elif ctype == 'dungeon_clear':
            return cls._get_dungeon_clear_progress(player, adef)
        elif ctype == 'dungeon_tower':
            return cls._get_dungeon_tower_progress(player, adef)
        elif ctype == 'boss_kill':
            return cls._get_boss_kill_progress(player, adef)
        elif ctype == 'elite_kill_area':
            return cls._get_elite_kill_area_progress(player, adef)
        elif ctype == 'elite_kill_monster':
            return cls._get_elite_kill_monster_progress(player, adef)
        elif ctype == 'kill_monster':
            return cls._get_kill_monster_progress(player, adef)
        elif ctype == 'divine_beast_kill':
            return cls._get_divine_beast_kill_progress(player, adef)
        elif ctype == 'forge':
            return player.forge_count or 0
        elif ctype == 'enhance_success':
            return player.enhance_success_count or 0
        elif ctype == 'enhance_fail':
            return player.enhance_fail_count or 0
        elif ctype == 'enhance_50':
            return player.enhance_50_count or 0
        elif ctype == 'artifact_owned':
            return cls._get_artifact_owned_progress(player, adef)
        elif ctype == 'quest':
            return cls._get_quest_progress(player, adef)
        elif ctype == 'quest_done':
            return cls._get_quest_done_progress(player, adef)
        return 0

    @classmethod
    def get_bonuses(cls, player):
        claimed = Achievement.query.filter_by(player_id=player.id, claimed=True).all()
        achievements = DataService.get_achievements()
        bonuses = {}
        for a in claimed:
            adef = achievements.get(a.achievement_id)
            if adef:
                for stat, value in adef.get('reward', {}).items():
                    if stat == 'title':
                        continue
                    if isinstance(value, (int, float)):
                        bonuses[stat] = bonuses.get(stat, 0) + value
        return bonuses

    @classmethod
    def get_points(cls, player):
        try:
            records = Achievement.query.filter_by(player_id=player.id).all()
            achievements = DataService.get_achievements()
            points = 0
            for record in records:
                adef = achievements.get(record.achievement_id)
                if adef:
                    points += int(adef.get('points', 0) or 0)
            return points
        except Exception:
            return 0

    @classmethod
    def _get_friend_count(cls, player):
        """当前结交的好友数(红颜 + 知己)。"""
        from models.relationship import Relationship
        return (Relationship.count_relationships(player.id, 'hongyan')
                + Relationship.count_relationships(player.id, 'zhiji'))

    @classmethod
    def _get_social_stat(cls, player, key):
        """读取社交类成就累计计数(存于 activity_data JSON)。"""
        data = player.activity_data or {}
        value = data.get(key, 0)
        return value if isinstance(value, (int, float)) else 0

    @classmethod
    def incr_social_stat(cls, player, key, amount=1):
        """累加社交类成就计数并返回新值。调用方负责 commit。"""
        data = player.activity_data or {}
        current = data.get(key, 0)
        if not isinstance(current, (int, float)):
            current = 0
        data[key] = int(current) + amount
        player.activity_data = data
        return data[key]

    @classmethod
    def _get_item_use_progress(cls, player, adef):
        usage = player.item_usage
        tracking_keys = []
        tracking_key = adef.get('tracking_key')
        if tracking_key:
            tracking_keys.append(tracking_key)
        tracking_keys.extend(adef.get('tracking_keys', []))
        item_name = adef.get('item_name')
        if item_name:
            tracking_keys.append(f"name:{item_name}")
        item_id = adef.get('item_id')
        if item_id:
            tracking_keys.append(item_id)
        for key in tracking_keys:
            if key in usage:
                return usage.get(key, 0)
        return 0

    @classmethod
    def _get_dungeon_clear_progress(cls, player, adef):
        dungeon_id = adef.get('dungeon_id')
        if not dungeon_id:
            return 0
        clears = getattr(player, 'dungeon_clears', None)
        if clears is None:
            clears = player.dungeon_clears
        return clears.get(dungeon_id, 0) if isinstance(clears, dict) else 0

    @classmethod
    def _get_dungeon_tower_progress(cls, player, adef):
        return getattr(player, 'tower_max_floor', 0) or 0

    @classmethod
    def _get_boss_kill_progress(cls, player, adef):
        boss_name = adef.get('boss_name', '')
        if not boss_name:
            return 0
        kills = getattr(player, 'boss_kills', {})
        if not isinstance(kills, dict):
            return 0
        return kills.get(boss_name, 0)

    @classmethod
    def _get_elite_kill_area_progress(cls, player, adef):
        """按区域统计精英击杀数: player.elite_kills_by_area = {'kunlun': 5, ...}"""
        area = adef.get('area', '')
        if not area:
            return 0
        kills = getattr(player, 'elite_kills_by_area', {})
        if not isinstance(kills, dict):
            return 0
        return kills.get(area, 0)

    @classmethod
    def _get_elite_kill_monster_progress(cls, player, adef):
        """按monster_id统计精英击杀数: player.monster_kills = {monster_id: count}"""
        monster_id = adef.get('monster_id', '')
        if not monster_id:
            return 0
        kills = getattr(player, 'monster_kills', {})
        if not isinstance(kills, dict):
            return 0
        return kills.get(monster_id, 0)

    @classmethod
    def _get_kill_monster_progress(cls, player, adef):
        """按monster_id统计普通怪击杀数: player.monster_kills = {monster_id: count}"""
        monster_id = adef.get('monster_id', '')
        if not monster_id:
            return 0
        kills = getattr(player, 'monster_kills', {})
        if not isinstance(kills, dict):
            return 0
        return kills.get(monster_id, 0)

    @classmethod
    def _get_divine_beast_kill_progress(cls, player, adef):
        """神兽累计击杀数: player.divine_beast_kills (int)"""
        return getattr(player, 'divine_beast_kills', 0) or 0

    @classmethod
    def _get_artifact_owned_progress(cls, player, adef):
        """拥有绑定的神器装备: 查询EquipmentInstance中is_bound=True且rarity=神器且template_id匹配"""
        template_id = adef.get('template_id', '')
        if not template_id:
            return 0
        from models.player import EquipmentInstance
        return EquipmentInstance.query.filter_by(
            player_id=player.id, template_id=template_id,
            is_bound=True, rarity='神器'
        ).count()

    @classmethod
    def _get_quest_progress(cls, player, adef):
        import json
        try:
            completed = json.loads(player.completed_quests) if player.completed_quests else []
            return len(completed) if isinstance(completed, list) else 0
        except (json.JSONDecodeError, TypeError):
            return 0

    @classmethod
    def _get_quest_done_progress(cls, player, adef):
        import json
        try:
            completed = json.loads(player.completed_quests) if player.completed_quests else []
        except (json.JSONDecodeError, TypeError):
            return 0
        if not isinstance(completed, list):
            return 0
        targets = adef.get('condition_quests') or []
        return 1 if any(qid in completed for qid in targets) else 0

    @classmethod
    def _normalize_category(cls, adef):
        category = adef.get('category')
        if category in ALIGNED_CATEGORIES:
            return category

        condition_type = adef.get('condition_type')
        if condition_type == 'item_use':
            return '道具'
        if condition_type in ('level', 'enhance'):
            return '成长'
        if condition_type in ('kill', 'elite_kill', 'boss_kill', 'elite_kill_monster', 'kill_monster', 'divine_beast_kill'):
            return '杀怪'
        if condition_type in ('pk_win', 'pk_loss'):
            return 'P K'
        if condition_type == 'equip_full':
            return '装备'
        if condition_type in ('forge', 'enhance_success', 'enhance_fail', 'enhance_50', 'artifact_owned'):
            return '装备'
        if condition_type in ('gold_earned', 'gold_total', 'yuanbao_spent', 'jinzu_spent'):
            return '财富'
        if condition_type in ('gift', 'chat', 'flower_received', 'friend_count', 'bless_count',
                              'steal_skill_success', 'steal_medicine_success', 'steal_caught'):
            return '社交'
        if condition_type == 'lieutenant_owned':
            return '副将'
        if condition_type == 'vip_level':
            return '活动'
        if condition_type in ('dungeon_clear', 'dungeon_tower'):
            return '副本'
        if condition_type in ('quest', 'quest_done'):
            return '任务'
        return '其他'
