from models.legion import Legion, LegionMember, LegionApplication, LegionChat
from models.player import PlayerModel
from services import db
from datetime import datetime, date
from services.data_service import DataService


class LegionService:

    # --- Legion stat bonuses applied to player ---

    @classmethod
    def get_legion_skill_bonuses(cls, player):
        """Return flat stat bonuses from the player's legion skills."""
        member = LegionMember.query.filter_by(player_id=player.id).first()
        if not member:
            return {}
        legion = Legion.query.get(member.legion_id)
        if not legion:
            return {}
        return legion.get_skill_bonuses()

    @classmethod
    def get_vip_aura_bonuses(cls, player):
        """Return VIP aura bonuses (flat stats) from the player's legion."""
        member = LegionMember.query.filter_by(player_id=player.id).first()
        if not member:
            return {}
        legion = Legion.query.get(member.legion_id)
        if not legion:
            return {}
        cls._refresh_vip_aura(legion)
        return {
            'max_health': legion.vip_aura_hp,
            'attack': legion.vip_aura_atk,
            'defense': legion.vip_aura_def,
        }

    @classmethod
    def _refresh_vip_aura(cls, legion):
        """刷新军团 VIP 光环：仅统计「签到日期为今天」的 VIP 成员，避免跨天残留。"""
        today = date.today().isoformat()
        if legion.vip_aura_date != today:
            # 只统计今天签到(sign_date 为今天)的 VIP 成员，忽略昨天遗留的 signed_today
            signed_vip_count = 0
            members = LegionMember.query.filter_by(legion_id=legion.id, signed_today=True).all()
            for m in members:
                if m.sign_date != today:
                    continue
                p = PlayerModel.query.get(m.player_id)
                if p and p.is_vip:
                    signed_vip_count += 1
            legion.vip_aura_hp = signed_vip_count * 30
            legion.vip_aura_atk = signed_vip_count * 6
            legion.vip_aura_def = signed_vip_count * 30
            legion.vip_aura_date = today
            db.session.commit()

    # --- Legion creation ---

    @classmethod
    def create_legion(cls, player, name, declaration):
        """Create a new legion. Returns (success, message)."""
        if player.level < 30:
            return False, "创建军团需等级达到30级"

        member = LegionMember.query.filter_by(player_id=player.id).first()
        if member:
            return False, "你已经加入了一个军团"

        if Legion.query.filter_by(name=name).first():
            return False, "军团名称已存在"

        if player.gold < 500000:
            return False, "银两不足（需要50万银两）"

        # Check for 一级军团虎符
        tiger_tally = DataService.get_inventory_item(player.id, "legion_tiger_tally_1")
        if not tiger_tally or tiger_tally.quantity < 1:
            return False, "需要1个一级军团虎符"

        if len(name) > 12 or len(name) < 2:
            return False, "军团名称需2-12个字"

        # Deduct costs
        player.gold -= 500000
        DataService.remove_item_from_inventory(player.id, "legion_tiger_tally_1", 1)

        legion = Legion(
            name=name,
            country=player.country,
            leader_id=player.id,
            declaration=declaration or '',
        )
        db.session.add(legion)
        db.session.flush()

        lm = LegionMember(
            legion_id=legion.id,
            player_id=player.id,
            role='leader',
        )
        db.session.add(lm)
        db.session.commit()
        return True, f"军团【{name}】创建成功！"

    # --- Join / Apply ---

    @classmethod
    def apply_to_join(cls, player, legion_id):
        """Apply to join a legion. Returns (success, message)."""
        if player.level < 20:
            return False, "加入军团需等级达到20级"

        member = LegionMember.query.filter_by(player_id=player.id).first()
        if member:
            return False, "你已经加入了一个军团"

        legion = Legion.query.get(legion_id)
        if not legion:
            return False, "军团不存在"

        if legion.country != player.country:
            return False, "只能加入本国军团"

        # Check for existing application
        existing = LegionApplication.query.filter_by(
            legion_id=legion_id, player_id=player.id).first()
        if existing:
            return False, "你已经申请过了"

        if legion.members.count() >= legion.get_max_slots():
            return False, "该军团人数已满"

        app = LegionApplication(
            legion_id=legion_id,
            player_id=player.id,
            player_level=player.level,
        )
        db.session.add(app)
        db.session.commit()
        return True, "申请已提交，等待审批"

    @classmethod
    def approve_application(cls, approver, application_id):
        """Approve a join application. Returns (success, message)."""
        app = LegionApplication.query.get(application_id)
        if not app:
            return False, "申请不存在"

        # Check permission
        member = LegionMember.query.filter_by(player_id=approver.id).first()
        if not member or member.role not in ('leader', 'vice_leader'):
            return False, "权限不足"

        if member.legion_id != app.legion_id:
            return False, "申请不在你的军团"

        legion = Legion.query.get(app.legion_id)
        if legion.members.count() >= legion.get_max_slots():
            return False, "军团人数已满"

        # Check if applicant already in a legion
        existing = LegionMember.query.filter_by(player_id=app.player_id).first()
        if existing:
            db.session.delete(app)
            db.session.commit()
            return False, "该玩家已加入其他军团"

        new_member = LegionMember(
            legion_id=app.legion_id,
            player_id=app.player_id,
            role='member',
        )
        db.session.add(new_member)
        db.session.delete(app)
        db.session.commit()
        return True, "审批通过"

    @classmethod
    def reject_application(cls, rejecter, application_id):
        """Reject a join application. Returns (success, message)."""
        app = LegionApplication.query.get(application_id)
        if not app:
            return False, "申请不存在"

        member = LegionMember.query.filter_by(player_id=rejecter.id).first()
        if not member or member.role not in ('leader', 'vice_leader'):
            return False, "权限不足"

        if member.legion_id != app.legion_id:
            return False, "申请不在你的军团"

        db.session.delete(app)
        db.session.commit()
        return True, "已拒绝"

    # --- Leave ---

    @classmethod
    def leave_legion(cls, player):
        """Leave the current legion. Returns (success, message)."""
        member = LegionMember.query.filter_by(player_id=player.id).first()
        if not member:
            return False, "你不在任何军团中"

        legion = Legion.query.get(member.legion_id)

        if member.role == 'leader':
            # Leader cannot leave if there are other members
            other_members = LegionMember.query.filter(
                LegionMember.legion_id == legion.id,
                LegionMember.player_id != player.id
            ).count()
            if other_members > 0:
                # Promote vice leader or first member to leader
                vice = LegionMember.query.filter_by(
                    legion_id=legion.id, role='vice_leader').first()
                if vice:
                    vice.role = 'leader'
                    legion.leader_id = vice.player_id
                else:
                    first = LegionMember.query.filter(
                        LegionMember.legion_id == legion.id,
                        LegionMember.player_id != player.id
                    ).order_by(LegionMember.joined_at.asc()).first()
                    if first:
                        first.role = 'leader'
                        legion.leader_id = first.player_id
            else:
                # Last member, delete the legion
                db.session.delete(legion)

        if member.role == 'vice_leader':
            legion.vice_leader_id = None

        db.session.delete(member)
        db.session.commit()
        return True, "已退出军团"

    # --- Sign in ---

    @classmethod
    def sign_in(cls, player):
        """Daily sign in for legion. Returns (success, message)."""
        member = LegionMember.query.filter_by(player_id=player.id).first()
        if not member:
            return False, "你不在任何军团中"

        today = date.today().isoformat()
        if member.sign_date == today and member.signed_today:
            return False, "今日已签到"

        member.signed_today = True
        member.sign_date = today
        member.contribution += 10

        legion = Legion.query.get(member.legion_id)
        legion.total_contribution += 10

        # VIP 签到：清空光环日期缓存并基于今日签到人数重算，避免跨天累加残留
        if player.is_vip:
            legion.vip_aura_date = ''
            cls._refresh_vip_aura(legion)

        db.session.commit()
        return True, "签到成功，为军团增加军贡10点"

    # --- Donate ---

    @classmethod
    def donate_gold(cls, player):
        """Donate 5000 silver. Returns (success, message)."""
        member = LegionMember.query.filter_by(player_id=player.id).first()
        if not member:
            return False, "你不在任何军团中"

        today = date.today().isoformat()
        if member.gold_donate_date != today:
            member.gold_donate_count = 0
            member.gold_donate_date = today

        if member.gold_donate_count >= 10:
            return False, "今日银两捐献次数已用完"

        if player.gold < 5000:
            return False, "银两不足（需要5000银两）"

        player.gold -= 5000
        member.gold_donate_count += 1
        member.contribution += 10

        legion = Legion.query.get(member.legion_id)
        legion.total_contribution += 10
        db.session.commit()
        return True, "捐献成功，军团军贡+10 个人军贡+10"

    @classmethod
    def donate_jinzu(cls, player):
        """Donate 10 jinzu. Returns (success, message)."""
        member = LegionMember.query.filter_by(player_id=player.id).first()
        if not member:
            return False, "你不在任何军团中"

        if player.jinzu < 10:
            return False, "金珠不足（需要10金珠）"

        player.jinzu -= 10
        player.jinzu_spent = (player.jinzu_spent or 0) + 10
        member.contribution += 10

        legion = Legion.query.get(member.legion_id)
        legion.total_contribution += 10
        db.session.commit()
        from services.achievement_service import AchievementService
        AchievementService.check(player, 'jinzu_spent', player.jinzu_spent)
        return True, "捐献成功，军团军贡+10 个人军贡+10"

    @classmethod
    def donate_yuanbao(cls, player):
        """Donate 10 yuanbao. Returns (success, message)."""
        member = LegionMember.query.filter_by(player_id=player.id).first()
        if not member:
            return False, "你不在任何军团中"

        if player.yuanbao < 10:
            return False, "元宝不足（需要10元宝）"

        player.yuanbao -= 10
        player.yuanbao_spent = (player.yuanbao_spent or 0) + 10
        member.contribution += 10

        legion = Legion.query.get(member.legion_id)
        legion.total_contribution += 10
        db.session.commit()
        from services.achievement_service import AchievementService
        AchievementService.check(player, 'yuanbao_spent', player.yuanbao_spent)
        return True, "捐献成功，军团军贡+10 个人军贡+10"

    # --- Upgrade ---

    @classmethod
    def upgrade_legion(cls, player):
        """Upgrade legion level. Returns (success, message)."""
        member = LegionMember.query.filter_by(player_id=player.id).first()
        if not member:
            return False, "你不在任何军团中"

        if member.role != 'leader':
            return False, "只有军团长可以升级军团"

        legion = Legion.query.get(member.legion_id)
        if not legion.can_upgrade():
            return False, "军团已达最高等级"

        cost = legion.get_upgrade_cost()
        if legion.total_contribution < cost:
            return False, f"军团军贡不足（需要{cost}军贡）"

        legion.total_contribution -= cost
        legion.level += 1
        db.session.commit()
        return True, f"军团升级到{legion.level}级！"

    # --- Management ---

    @classmethod
    def set_vice_leader(cls, leader, target_player_id):
        """Set a member as vice leader. Returns (success, message)."""
        member = LegionMember.query.filter_by(player_id=leader.id).first()
        if not member or member.role != 'leader':
            return False, "只有军团长可以设置副团长"

        legion = Legion.query.get(member.legion_id)

        # Remove existing vice leader
        existing_vice = LegionMember.query.filter_by(
            legion_id=legion.id, role='vice_leader').first()
        if existing_vice:
            existing_vice.role = 'member'

        target = LegionMember.query.filter_by(
            legion_id=legion.id, player_id=target_player_id).first()
        if not target:
            return False, "该玩家不是军团成员"

        if target.role == 'leader':
            return False, "不能设置团长为副团长"

        target.role = 'vice_leader'
        legion.vice_leader_id = target_player_id
        db.session.commit()
        return True, "副团长设置成功"

    @classmethod
    def remove_vice_leader(cls, leader):
        """Remove vice leader role. Returns (success, message)."""
        member = LegionMember.query.filter_by(player_id=leader.id).first()
        if not member or member.role != 'leader':
            return False, "只有军团长可以撤销副团长"

        legion = Legion.query.get(member.legion_id)
        vice = LegionMember.query.filter_by(
            legion_id=legion.id, role='vice_leader').first()
        if not vice:
            return False, "没有副团长"

        vice.role = 'member'
        legion.vice_leader_id = None
        db.session.commit()
        return True, "已撤销副团长"

    @classmethod
    def kick_member(cls, kicker, target_player_id):
        """Kick a member from legion. Returns (success, message)."""
        member = LegionMember.query.filter_by(player_id=kicker.id).first()
        if not member or member.role not in ('leader', 'vice_leader'):
            return False, "权限不足"

        target = LegionMember.query.filter_by(player_id=target_player_id).first()
        if not target or target.legion_id != member.legion_id:
            return False, "该玩家不是本军团成员"

        if target.role == 'leader':
            return False, "不能踢出团长"

        if target.role == 'vice_leader' and member.role != 'leader':
            return False, "只有团长可以踢出副团长"

        legion = Legion.query.get(target.legion_id)
        db.session.delete(target)
        db.session.commit()
        return True, "已将该成员移出军团"

    # --- Chat ---

    @classmethod
    def send_message(cls, player, content):
        """Send a message in legion chat. Returns (success, message)."""
        member = LegionMember.query.filter_by(player_id=player.id).first()
        if not member:
            return False, "你不在任何军团中"

        content = content.strip()[:30]
        if not content:
            return False, "消息不能为空"

        msg = LegionChat(
            legion_id=member.legion_id,
            sender_id=player.id,
            sender_name=player.nickname,
            content=content,
        )
        db.session.add(msg)
        db.session.commit()
        return True, "发送成功"

    @classmethod
    def get_messages(cls, player, page=1, per_page=15):
        """Get legion chat messages."""
        member = LegionMember.query.filter_by(player_id=player.id).first()
        if not member:
            return [], 0

        query = LegionChat.query.filter_by(legion_id=member.legion_id)
        total = query.count()
        messages = query.order_by(LegionChat.created_at.desc()).offset(
            (page - 1) * per_page).limit(per_page).all()
        return messages, total

    # --- Contribution exchange ---

    CONTRIB_EXCHANGE = {
        'other': {
            'name': '其他',
            'items': {
                'bag_expand': {'name': '秘背包扩容卷', 'cost': 50, 'item_id': 'bag_expand'},
                'battle_revive_lamp': {'name': '战场续命灯', 'cost': 150, 'item_id': 'battle_revive_lamp'},
            }
        },
        'equip': {
            'name': '装备',
            'items': {
                'epic_ring_1': {'name': '【史诗】至尊一戒', 'cost': 250, 'item_id': 'epic_ring_1'},
                'epic_ring_2': {'name': '【史诗】至尊二戒', 'cost': 500, 'item_id': 'epic_ring_2'},
                'epic_ring_3': {'name': '【史诗】至尊三戒', 'cost': 750, 'item_id': 'epic_ring_3'},
                'epic_ring_4': {'name': '【史诗】至尊四戒', 'cost': 1500, 'item_id': 'epic_ring_4'},
                'epic_ring_5': {'name': '【史诗】至尊五戒', 'cost': 3000, 'item_id': 'epic_ring_5'},
            }
        },
        'assist': {
            'name': '辅助',
            'items': {
                'blood_stone_small': {'name': '小血石', 'cost': 20, 'item_id': 'blood_stone_small'},
                'mana_stone_small': {'name': '小魔石', 'cost': 20, 'item_id': 'mana_stone_small'},
            }
        },
    }

    # --- Battle points exchange ---

    BATTLE_EXCHANGE = {
        'other': {
            'name': '其他',
            'items': {
                'battle_flag_1': {'name': '战场令旗(低级)', 'cost': 3, 'item_id': 'battle_flag_1'},
                'battle_flag_2': {'name': '战场令旗(中级)', 'cost': 9, 'item_id': 'battle_flag_2'},
                'battle_flag_3': {'name': '战场令旗(高级)', 'cost': 27, 'item_id': 'battle_flag_3'},
                'strong_hp_potion': {'name': '强效生命秘药', 'cost': 3, 'item_id': 'strong_hp_potion'},
                'strong_mp_potion': {'name': '强效魔法秘药', 'cost': 1, 'item_id': 'strong_mp_potion'},
                'strong_atk_potion': {'name': '强效攻击秘药', 'cost': 5, 'item_id': 'strong_atk_potion'},
                'strong_def_potion': {'name': '强效防御秘药', 'cost': 5, 'item_id': 'strong_def_potion'},
                'strong_crit_potion': {'name': '强效暴击秘药', 'cost': 9, 'item_id': 'strong_crit_potion'},
                'strong_dodge_potion': {'name': '强效闪避秘药', 'cost': 9, 'item_id': 'strong_dodge_potion'},
            }
        },
        'equip': {
            'name': '装备',
            'items': {
                'yuanyang_sword_blueprint': {'name': '鸳鸯剑图纸', 'cost': 40, 'item_id': 'yuanyang_sword_blueprint'},
            }
        },
        'assist': {
            'name': '辅助',
            'items': {
                'strong_hp_potion_a': {'name': '强效生命秘药', 'cost': 3, 'item_id': 'strong_hp_potion'},
                'strong_mp_potion_a': {'name': '强效魔法秘药', 'cost': 1, 'item_id': 'strong_mp_potion'},
                'strong_atk_potion_a': {'name': '强效攻击秘药', 'cost': 5, 'item_id': 'strong_atk_potion'},
                'strong_def_potion_a': {'name': '强效防御秘药', 'cost': 5, 'item_id': 'strong_def_potion'},
                'strong_crit_potion_a': {'name': '强效暴击秘药', 'cost': 9, 'item_id': 'strong_crit_potion'},
                'strong_dodge_potion_a': {'name': '强效闪避秘药', 'cost': 9, 'item_id': 'strong_dodge_potion'},
            }
        },
    }

    @classmethod
    def exchange_contrib_item(cls, player, item_key, quantity=1):
        """Exchange personal contribution for items. Returns (success, message)."""
        member = LegionMember.query.filter_by(player_id=player.id).first()
        if not member:
            return False, "你不在任何军团中"

        item_info = None
        for cat in cls.CONTRIB_EXCHANGE.values():
            if item_key in cat['items']:
                item_info = cat['items'][item_key]
                break
        if not item_info:
            return False, "兑换物品不存在"

        total_cost = item_info['cost'] * quantity
        if member.contribution < total_cost:
            return False, f"个人军贡不足（需要{total_cost}军贡）"

        member.contribution -= total_cost
        DataService.add_item_to_inventory(player.id, item_info['item_id'], quantity)
        db.session.commit()
        return True, f"兑换成功：{item_info['name']}x{quantity}"

    @classmethod
    def exchange_battle_item(cls, player, item_key, quantity=1):
        """Exchange personal battle points for items. Returns (success, message)."""
        member = LegionMember.query.filter_by(player_id=player.id).first()
        if not member:
            return False, "你不在任何军团中"

        item_info = None
        for cat in cls.BATTLE_EXCHANGE.values():
            if item_key in cat['items']:
                item_info = cat['items'][item_key]
                break
        if not item_info:
            return False, "兑换物品不存在"

        total_cost = item_info['cost'] * quantity
        if member.personal_battle_points < total_cost:
            return False, f"军团积分不足（需要{total_cost}积分）"

        member.personal_battle_points -= total_cost
        DataService.add_item_to_inventory(player.id, item_info['item_id'], quantity)
        db.session.commit()
        return True, f"兑换成功：{item_info['name']}x{quantity}"

    # --- Legion quest tasks ---

    @classmethod
    def get_quest_count(cls, player):
        """Get remaining quest count for today."""
        member = LegionMember.query.filter_by(player_id=player.id).first()
        if not member:
            return 0
        today = date.today().isoformat()
        if member.quest_date != today:
            return 3
        return max(0, 3 - member.quest_count)

    @classmethod
    def do_quest(cls, player):
        """Complete a legion quest. Returns (success, message)."""
        member = LegionMember.query.filter_by(player_id=player.id).first()
        if not member:
            return False, "你不在任何军团中"

        today = date.today().isoformat()
        if member.quest_date != today:
            member.quest_count = 0
            member.quest_date = today

        if member.quest_count >= 3:
            return False, "今日任务次数已用完"

        member.quest_count += 1
        member.contribution += 10

        legion = Legion.query.get(member.legion_id)
        legion.total_contribution += 10
        db.session.commit()
        return True, "完成军团任务，获得军贡+10"

    # --- Daily reset ---

    @classmethod
    def check_daily_reset(cls, member):
        """Reset daily counters if day has changed."""
        today = date.today().isoformat()
        if member.sign_date != today:
            member.signed_today = False
            member.sign_date = today
        if member.gold_donate_date != today:
            member.gold_donate_count = 0
            member.gold_donate_date = today

    @classmethod
    def reset_all_daily_counters(cls):
        """后台批量重置所有军团成员每日签到/捐献/任务次数。"""
        today = date.today().isoformat()
        changed = False
        for member in LegionMember.query.all():
            if member.sign_date != today:
                member.signed_today = False
                member.sign_date = today
                changed = True
            if member.gold_donate_date != today:
                member.gold_donate_count = 0
                member.gold_donate_date = today
                changed = True
            if member.quest_date != today:
                member.quest_count = 0
                member.quest_date = today
                changed = True
        if changed:
            db.session.commit()
        return changed

    # --- Legion queries ---

    @classmethod
    def get_player_legion(cls, player):
        """Get the legion the player belongs to, or None."""
        member = LegionMember.query.filter_by(player_id=player.id).first()
        if not member:
            return None
        return Legion.query.get(member.legion_id)

    @classmethod
    def get_player_member(cls, player):
        """Get the player's LegionMember record."""
        return LegionMember.query.filter_by(player_id=player.id).first()

    @classmethod
    def get_legions_by_country(cls, country, page=1, per_page=12):
        """Get paginated legion list for a country."""
        query = Legion.query.filter_by(country=country).order_by(
            Legion.total_contribution.desc())
        total = query.count()
        legions = query.offset((page - 1) * per_page).limit(per_page).all()
        return legions, total

    @classmethod
    def get_all_legions(cls, page=1, per_page=12):
        """Get all legions sorted by contribution."""
        query = Legion.query.order_by(Legion.total_contribution.desc())
        total = query.count()
        legions = query.offset((page - 1) * per_page).limit(per_page).all()
        return legions, total

    @classmethod
    def get_member_list(cls, legion_id, page=1, per_page=15):
        """Get paginated member list for a legion."""
        query = LegionMember.query.filter_by(legion_id=legion_id)
        total = query.count()
        members = query.order_by(
            # leader first, then vice_leader, then members
            db.case(
                (LegionMember.role == 'leader', 0),
                (LegionMember.role == 'vice_leader', 1),
                else_=2
            ),
            LegionMember.joined_at.asc()
        ).offset((page - 1) * per_page).limit(per_page).all()
        return members, total

    @classmethod
    def get_applications(cls, legion_id):
        """Get pending applications for a legion."""
        return LegionApplication.query.filter_by(legion_id=legion_id).order_by(
            LegionApplication.created_at.desc()).all()

    @classmethod
    def get_vip_aura_text(cls, legion):
        """Get VIP aura display text."""
        cls._refresh_vip_aura(legion)
        parts = []
        if legion.vip_aura_atk > 0:
            parts.append(f"攻击力+{legion.vip_aura_atk}")
        else:
            parts.append("攻击力+0")
        if legion.vip_aura_def > 0:
            parts.append(f"防御力+{legion.vip_aura_def}")
        else:
            parts.append("防御力+0")
        if legion.vip_aura_hp > 0:
            parts.append(f"生命值+{legion.vip_aura_hp}")
        else:
            parts.append("生命值+0")
        parts.append("魔法值+0")
        parts.append("暴击率+0%")
        parts.append("闪避率+0%")
        return ' '.join(parts)
