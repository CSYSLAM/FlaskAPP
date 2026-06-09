from services import db
from services.data_service import DataService
from models.player import Achievement


class AchievementService:

    @classmethod
    def check_all(cls, player):
        for ctype in ['level', 'kill', 'elite_kill', 'pk_win', 'enhance',
                       'visit', 'equip_full', 'gold_earned', 'gift', 'chat', 'vip_level',
                       'lieutenant_owned']:
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
        elif ctype == 'gift':
            return player.gift_count >= val
        elif ctype == 'chat':
            return player.chat_count >= val
        elif ctype == 'vip_level':
            return player.vip_level >= val
        elif ctype == 'lieutenant_owned':
            from models.lieutenant import Lieutenant
            name = adef.get('lt_name', '')
            return Lieutenant.query.filter_by(owner_id=player.id, name=name).first() is not None
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
            cat = adef.get('category', '成长')
            progress = cls._get_progress(player, aid, adef)
            record = completed_map.get(aid)
            entry = {
                'id': aid,
                'name': adef['name'],
                'description': adef['description'],
                'reward': adef.get('reward', {}),
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
        elif ctype == 'gift':
            return player.gift_count or 0
        elif ctype == 'chat':
            return player.chat_count or 0
        elif ctype == 'lieutenant_owned':
            from models.lieutenant import Lieutenant
            name = adef.get('lt_name', '')
            return 1 if Lieutenant.query.filter_by(owner_id=player.id, name=name).first() else 0
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