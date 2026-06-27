import random
from datetime import datetime, timedelta
from services import db
from services.data_service import DataService
from models.player import ChatMessage, InventoryItem, EquipmentInstance, PlayerModel
from models.relationship import Relationship


MAX_FRIENDS = 30
MAX_BLACKLIST = 30
MAX_ENEMIES = 30
MAX_RELATIONS = 5  # Max 5 hongyan or 5 zhiji
FATE_REQUIRED = 100  # Min fate value to request relationship


class SocialService:

    @classmethod
    def get_social_bonus(cls, player):
        """Calculate social bonuses from hongyan/zhiji counts."""
        from sqlalchemy import or_
        hongyan = Relationship.query.filter(
            or_(Relationship.player1_id == player.id, Relationship.player2_id == player.id),
            Relationship.rel_type == 'hongyan').count()
        zhiji = Relationship.query.filter(
            or_(Relationship.player1_id == player.id, Relationship.player2_id == player.id),
            Relationship.rel_type == 'zhiji').count()
        total = hongyan * 2 + zhiji * 3
        return total * 2, total * 1

    @classmethod
    def send_public_message(cls, player, content):
        """Public chat - consumes 小喇叭 (horn_small)."""
        inv = DataService.get_inventory_item(player.id, 'horn_small')
        if not inv or inv.quantity <= 0:
            return False, "需要一个小喇叭才能在公共频道发言"

        DataService.remove_item_from_inventory(player.id, 'horn_small', 1)

        msg = ChatMessage(
            sender_id=player.id,
            content=content,
            message_type='public'
        )
        db.session.add(msg)

        player.chat_count = (player.chat_count or 0) + 1
        db.session.commit()

        from services.achievement_service import AchievementService
        AchievementService.check(player, 'chat', player.chat_count)
        return True, None

    @classmethod
    def send_country_message(cls, player, content):
        """Country chat - only visible to same country, free."""
        msg = ChatMessage(
            sender_id=player.id,
            content=content,
            message_type='country'
        )
        db.session.add(msg)

        player.chat_count = (player.chat_count or 0) + 1
        db.session.commit()

        from services.achievement_service import AchievementService
        AchievementService.check(player, 'chat', player.chat_count)
        return True, None

    @classmethod
    def send_private_message(cls, sender, receiver, content):
        msg = ChatMessage(
            sender_id=sender.id,
            receiver_id=receiver.id,
            content=content,
            message_type='private'
        )
        db.session.add(msg)
        db.session.commit()

    @classmethod
    def send_gift(cls, sender, receiver, gift_type, gift_id, quantity=1):
        if gift_type == "item":
            inv = DataService.get_inventory_item(sender.id, gift_id)
            if not inv or inv.quantity < quantity:
                return False, "物品不足"

            if inv.is_bound:
                return False, "绑定物品不可赠送"

            item_data = DataService.get_item(gift_id)
            if not item_data:
                return False, "物品不存在"

            DataService.remove_item_from_inventory(sender.id, gift_id, quantity, is_bound=False)
            DataService.add_item_to_inventory(receiver.id, gift_id, quantity, is_bound=False)
            item_name = item_data.get("name", gift_id)
            cls.send_private_message(
                sender, receiver,
                f"赠送了 {item_name}x{quantity}")

        elif gift_type == "equipment":
            equip = EquipmentInstance.query.filter_by(
                instance_id=gift_id, player_id=sender.id).first()
            if not equip:
                return False, "装备不存在"

            if equip.is_bound:
                return False, "已绑定装备不可赠送"

            DataService.add_item_to_inventory(receiver.id, equip.instance_id)
            equip.player_id = receiver.id
            cls.send_private_message(
                sender, receiver,
                f"赠送了 {equip.name}")

        elif gift_type == "gold":
            amount = int(gift_id)
            if sender.gold < amount:
                return False, "银两不足"
            sender.gold -= amount
            receiver.gold += amount
            cls.send_private_message(
                sender, receiver,
                f"赠送了 {amount} 银两")

        else:
            return False, "无效的礼物类型"

        sender.gift_count = (sender.gift_count or 0) + 1

        db.session.commit()

        from services.achievement_service import AchievementService
        AchievementService.check(sender, 'gift', sender.gift_count)

        return True, "赠送成功"

    @classmethod
    def get_public_messages(cls, limit=20):
        return ChatMessage.query.filter_by(
            message_type='public',
            receiver_id=None
        ).order_by(ChatMessage.created_at.desc()).limit(limit).all()

    @classmethod
    def get_country_messages(cls, country, limit=20):
        """Get country chat messages for a specific country."""
        players = PlayerModel.query.filter_by(country=country).all()
        player_ids = [p.id for p in players]
        if not player_ids:
            return []
        return ChatMessage.query.filter(
            ChatMessage.message_type == 'country',
            ChatMessage.sender_id.in_(player_ids)
        ).order_by(ChatMessage.created_at.desc()).limit(limit).all()

    @classmethod
    def get_system_messages(cls, limit=20):
        return ChatMessage.query.filter_by(
            message_type='system'
        ).order_by(ChatMessage.created_at.desc()).limit(limit).all()

    @classmethod
    def get_notification_messages(cls, player_id, limit=20):
        """Get personal notifications (system broadcasts + private messages)."""
        return ChatMessage.query.filter(
            db.or_(
                ChatMessage.message_type == 'system',
                db.and_(ChatMessage.message_type == 'private',
                        ChatMessage.receiver_id == player_id)
            )
        ).order_by(ChatMessage.created_at.desc()).limit(limit).all()

    @classmethod
    def get_private_messages(cls, player1_id, player2_id=None, limit=20):
        if player2_id:
            return ChatMessage.query.filter(
                ChatMessage.message_type == 'private',
                db.or_(
                    db.and_(ChatMessage.sender_id == player1_id,
                            ChatMessage.receiver_id == player2_id),
                    db.and_(ChatMessage.sender_id == player2_id,
                            ChatMessage.receiver_id == player1_id)
                )
            ).order_by(ChatMessage.created_at.desc()).limit(limit).all()
        else:
            # All private messages for this player (sent or received)
            return ChatMessage.query.filter(
                ChatMessage.message_type == 'private',
                db.or_(
                    ChatMessage.sender_id == player1_id,
                    ChatMessage.receiver_id == player1_id
                )
            ).order_by(ChatMessage.created_at.desc()).limit(limit).all()

    # --- Friends ---

    @classmethod
    def add_friend(cls, player, target_username):
        """Add a friend."""
        target = DataService.get_player_by_username(target_username)
        if not target:
            return False, "玩家不存在"

        if target.id == player.id:
            return False, "不能添加自己为好友"

        friends = player.friends
        if len(friends) >= MAX_FRIENDS:
            return False, "好友列表已满"

        if target_username in friends:
            return False, "已经是好友"

        friends.append(target_username)
        player.friends = friends

        cls.add_notification(target, f"{player.nickname}把你加为好友了")

        db.session.commit()
        return True, f"已添加{target.nickname}为好友"

    @classmethod
    def remove_friend(cls, player, target_username):
        """Remove a friend."""
        friends = player.friends
        if target_username not in friends:
            return False, "该玩家不是你的好友"

        friends.remove(target_username)
        player.friends = friends
        db.session.commit()
        return True, "已删除好友"

    @classmethod
    def get_friend_list(cls, player):
        """Get detailed friend list."""
        friends = []
        for username in player.friends:
            target = DataService.get_player_by_username(username)
            if target:
                friends.append({
                    'username': username,
                    'nickname': target.nickname,
                    'level': target.level,
                    'online': cls._is_online(target)
                })
        return friends

    # --- Blacklist ---

    @classmethod
    def add_to_blacklist(cls, player, target_username):
        """Add player to blacklist."""
        target = DataService.get_player_by_username(target_username)
        if not target:
            return False, "玩家不存在"

        if target.id == player.id:
            return False, "不能拉黑自己"

        blacklist = player.blacklist
        if len(blacklist) >= MAX_BLACKLIST:
            return False, "黑名单已满"

        if target_username in blacklist:
            return False, "已经在黑名单中"

        blacklist.append(target_username)
        player.blacklist = blacklist
        db.session.commit()
        return True, f"已将{target.nickname}加入黑名单"

    @classmethod
    def remove_from_blacklist(cls, player, target_username):
        """Remove player from blacklist."""
        blacklist = player.blacklist
        if target_username not in blacklist:
            return False, "该玩家不在黑名单中"

        blacklist.remove(target_username)
        player.blacklist = blacklist
        db.session.commit()
        return True, "已移出黑名单"

    @classmethod
    def is_blocked(cls, player, target_username):
        """Check if target is in player's blacklist."""
        return target_username in player.blacklist

    # --- Enemies ---

    @classmethod
    def remove_enemy(cls, player, target_username):
        """Remove player from enemy list."""
        enemies = player.enemies
        if target_username not in enemies:
            return False, "该玩家不在仇人列表中"

        enemies.remove(target_username)
        player.enemies = enemies
        db.session.commit()
        return True, "已删除仇人"

    @classmethod
    def hunt_enemy(cls, player, target_username):
        """Use hunt token to teleport to enemy location."""
        inv = DataService.get_inventory_item(player.id, 'hunt_order')
        if not inv or inv.quantity <= 0:
            return False, "没有追杀令"

        target = DataService.get_player_by_username(target_username)
        if not target:
            return False, "玩家不存在"

        if target_username not in player.enemies:
            return False, "该玩家不在仇人列表中"

        DataService.remove_item_from_inventory(player.id, 'hunt_order', 1)
        player.current_location = target.current_location
        db.session.commit()
        return True, f"已传送到{target.nickname}所在位置"

    @classmethod
    def get_enemy_list(cls, player):
        """Get detailed enemy list."""
        enemies = []
        for username in player.enemies:
            target = DataService.get_player_by_username(username)
            if target:
                enemies.append({
                    'username': username,
                    'nickname': target.nickname,
                    'level': target.level,
                    'location': target.current_location,
                    'online': cls._is_online(target)
                })
        return enemies

    # --- Charm and Fate ---

    @classmethod
    def send_flower(cls, player, target_username):
        """Send rose to increase charm and fate."""
        target = DataService.get_player_by_username(target_username)
        if not target:
            return False, "玩家不存在"

        inv = DataService.get_inventory_item(player.id, 'flower_rose')
        if not inv or inv.quantity <= 0:
            return False, "没有玫瑰花"

        DataService.remove_item_from_inventory(player.id, 'flower_rose', 1)

        target.charm = (target.charm or 0) + 1
        cls._increase_fate(player.id, target.id, 1)

        cls.add_notification(target, f"{player.nickname}送了你一朵玫瑰花，魅力+1")

        db.session.commit()
        return True, f"送花成功，{target.nickname}魅力+1，双方缘分+1"

    @classmethod
    def _increase_fate(cls, player_id, target_id, amount):
        """Increase fate value between two players."""
        rel = Relationship.get_relationship(player_id, target_id)
        if rel:
            rel.fate_value += amount
        else:
            rel = Relationship(
                player1_id=min(player_id, target_id),
                player2_id=max(player_id, target_id),
                rel_type='pending',
                fate_value=amount,
                initiator_id=player_id
            )
            db.session.add(rel)
        db.session.commit()

    @classmethod
    def get_fate_value(cls, player_id, target_id):
        """Get fate value between two players."""
        rel = Relationship.get_relationship(player_id, target_id)
        if rel:
            return rel.fate_value
        return 0

    # --- Relationships (红颜/知己) ---

    @classmethod
    def request_relationship(cls, player, target_username, rel_type):
        """Request to establish relationship (红颜/知己)."""
        target = DataService.get_player_by_username(target_username)
        if not target:
            return False, "玩家不存在"

        if target.id == player.id:
            return False, "不能和自己结交"

        if rel_type == 'hongyan':
            if player.gender == target.gender:
                return False, "红颜需要异性之间才能结交"
        elif rel_type == 'zhiji':
            if player.gender != target.gender:
                return False, "知己需要同性之间才能结交"
        else:
            return False, "无效的关系类型"

        fate = cls.get_fate_value(player.id, target.id)
        if fate < FATE_REQUIRED:
            return False, f"缘分值不足{FATE_REQUIRED}"

        existing = Relationship.get_relationship(player.id, target.id)
        if existing and existing.rel_type in ('hongyan', 'zhiji'):
            return False, f"已经和{target.nickname}结为{existing.type_name}"

        count = Relationship.count_relationships(player.id, rel_type)
        if count >= MAX_RELATIONS:
            return False, f"{'红颜' if rel_type=='hongyan' else '知己'}数量已达上限"

        count2 = Relationship.count_relationships(target.id, rel_type)
        if count2 >= MAX_RELATIONS:
            return False, f"{target.nickname}的{'红颜' if rel_type=='hongyan' else '知己'}数量已达上限"

        inv = DataService.get_inventory_item(player.id, 'bond_wine')
        if not inv or inv.quantity <= 0:
            return False, "没有结交酒"

        # Check if already has pending request from this player
        existing_requests = target.relation_requests
        for r in existing_requests:
            if r.get('from') == player.username and r.get('type') == rel_type:
                return False, "已经发送过结交邀请，等待对方回应"

        DataService.remove_item_from_inventory(player.id, 'bond_wine', 1)

        requests = target.relation_requests
        requests.append({
            'from': player.username,
            'from_name': player.nickname,
            'type': rel_type,
            'time': datetime.now().strftime('%Y-%m-%d %H:%M')
        })
        target.relation_requests = requests

        cls.add_notification(target, f"{player.nickname}想和你结为{'红颜' if rel_type=='hongyan' else '知己'}")

        db.session.commit()
        return True, f"已向{target.nickname}发送{'红颜' if rel_type=='hongyan' else '知己'}结交邀请"

    @classmethod
    def accept_relationship(cls, player, requester_username):
        """Accept a relationship request."""
        requests = player.relation_requests
        request = None
        for r in requests:
            if r.get('from') == requester_username:
                request = r
                break

        if not request:
            return False, "没有该结交邀请"

        requester = DataService.get_player_by_username(requester_username)
        if not requester:
            return False, "邀请者不存在"

        rel_type = request.get('type')

        inv = DataService.get_inventory_item(player.id, 'bond_wine')
        if not inv or inv.quantity <= 0:
            return False, "没有结交酒"

        DataService.remove_item_from_inventory(player.id, 'bond_wine', 1)

        new_requests = [r for r in requests if r.get('from') != requester_username]
        player.relation_requests = new_requests

        existing = Relationship.get_relationship(player.id, requester.id)
        if existing:
            existing.rel_type = rel_type
            existing.initiator_id = requester.id
        else:
            rel = Relationship(
                player1_id=min(player.id, requester.id),
                player2_id=max(player.id, requester.id),
                rel_type=rel_type,
                fate_value=cls.get_fate_value(player.id, requester.id),
                initiator_id=requester.id
            )
            db.session.add(rel)

        cls.add_notification(requester, f"{player.nickname}同意和你结为{'红颜' if rel_type=='hongyan' else '知己'}")

        db.session.commit()
        return True, f"已和{requester.nickname}结为{'红颜' if rel_type=='hongyan' else '知己'}"

    @classmethod
    def reject_relationship(cls, player, requester_username):
        """Reject a relationship request."""
        requests = player.relation_requests
        request = None
        for r in requests:
            if r.get('from') == requester_username:
                request = r
                break

        if not request:
            return False, "没有该结交邀请"

        requester = DataService.get_player_by_username(requester_username)

        new_requests = [r for r in requests if r.get('from') != requester_username]
        player.relation_requests = new_requests

        if requester:
            cls.add_notification(requester, f"{player.nickname}拒绝了你的结交邀请")

        db.session.commit()
        return True, "已拒绝结交邀请"

    @classmethod
    def break_relationship(cls, player, target_username):
        """Break relationship with target."""
        target = DataService.get_player_by_username(target_username)
        if not target:
            return False, "玩家不存在"

        rel = Relationship.get_relationship(player.id, target.id)
        if not rel or rel.rel_type not in ('hongyan', 'zhiji'):
            return False, "没有该关系"

        inv = DataService.get_inventory_item(player.id, 'break_wine')
        if not inv or inv.quantity <= 0:
            return False, "没有断交酒"

        DataService.remove_item_from_inventory(player.id, 'break_wine', 1)

        rel.rel_type = 'pending'
        db.session.commit()

        cls.add_notification(target, f"{player.nickname}和你断交了")

        return True, f"已和{target.nickname}断交"

    @classmethod
    def get_relation_list(cls, player, rel_type):
        """Get relationship list (hongyan or zhiji)."""
        rels = Relationship.get_relationships(player.id, rel_type)
        result = []
        for rel in rels:
            other_id = rel.get_other_player_id(player.id)
            other = PlayerModel.query.get(other_id)
            if other:
                result.append({
                    'username': other.username,
                    'nickname': other.nickname,
                    'fate': rel.fate_value,
                    'online': cls._is_online(other)
                })
        return result

    @classmethod
    def get_online_relation_attack_bonus(cls, player):
        """Get attack bonus from online relationships."""
        bonus = 0
        rels = Relationship.get_relationships(player.id)
        for rel in rels:
            if rel.rel_type not in ('hongyan', 'zhiji'):
                continue
            other_id = rel.get_other_player_id(player.id)
            other = PlayerModel.query.get(other_id)
            if other and cls._is_online(other):
                bonus += 20
        return bonus

    # --- Helpers ---

    @classmethod
    def _is_online(cls, player):
        """Check if player is online (last_login within 30 minutes)."""
        if not player.last_login:
            return False
        return (datetime.utcnow() - player.last_login) < timedelta(minutes=30)

    @classmethod
    def add_notification(cls, player, message):
        """Add notification to player."""
        notifications = player.notifications
        notifications.insert(0, {
            'message': message,
            'time': datetime.now().strftime('%Y-%m-%d %H:%M')
        })
        player.notifications = notifications[:20]
