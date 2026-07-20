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
MARRIAGE_FATE_REQUIRED = 1000  # Min fate value to propose marriage


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

        cls.add_notification(target, f"{player.nickname}添加你为好友！", ntype='friend')

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
    def send_flower(cls, player, target_username, quantity=1):
        """Send roses to increase charm and fate. quantity: number of roses."""
        target = DataService.get_player_by_username(target_username)
        if not target:
            return False, "玩家不存在"

        if quantity < 1:
            return False, "数量无效"

        inv = DataService.get_inventory_item(player.id, 'flower_rose')
        if not inv or inv.quantity < quantity:
            have = inv.quantity if inv else 0
            return False, f"玫瑰花不足，当前{have}朵"

        DataService.remove_item_from_inventory(player.id, 'flower_rose', quantity)

        target.charm = (target.charm or 0) + quantity
        cls._increase_fate(player.id, target.id, quantity)

        cls.add_notification(target, f"{player.nickname}赠送给你{quantity}朵玫瑰花，增加{quantity}点缘分值", ntype='friend')

        db.session.commit()
        return True, f"赠送成功，{target.nickname}魅力+{quantity}，双方缘分+{quantity}"

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
        """Get attack bonus from online relationships + spouse online bonus."""
        bonus = 0
        rels = Relationship.get_relationships(player.id)
        for rel in rels:
            if rel.rel_type not in ('hongyan', 'zhiji'):
                continue
            other_id = rel.get_other_player_id(player.id)
            other = PlayerModel.query.get(other_id)
            if other and cls._is_online(other):
                bonus += 20
        # Spouse online bonus
        spouse = cls.get_spouse(player)
        if spouse and cls._is_online(spouse):
            bonus += 100
        return bonus

    # --- Marriage (结婚) ---

    @classmethod
    def get_spouse(cls, player):
        """Get player's spouse PlayerModel, or None."""
        rel = Relationship.query.filter(
            ((Relationship.player1_id == player.id) | (Relationship.player2_id == player.id)),
            Relationship.rel_type == 'spouse'
        ).first()
        if rel:
            other_id = rel.get_other_player_id(player.id)
            return PlayerModel.query.get(other_id)
        return None

    @classmethod
    def get_spouse_info(cls, player):
        """Get spouse info dict with username, nickname, online, ring info, or None."""
        spouse = cls.get_spouse(player)
        if not spouse:
            return None
        ring_info = cls._get_wedding_ring_info(player)
        return {
            'username': spouse.username,
            'nickname': spouse.nickname,
            'online': cls._is_online(spouse),
            'ring_info': ring_info,
        }

    @classmethod
    def _get_wedding_ring_info(cls, player):
        """Get player's equipped wedding ring info (name + stars)."""
        equipped = DataService.get_equipped(player.id)
        accessory = equipped.get('accessory')
        if accessory and accessory.template_id in ('wedding_grass_ring', 'wedding_diamond_ring'):
            ring_name = '新婚草戒' if accessory.template_id == 'wedding_grass_ring' else '新婚钻戒'
            return f"{ring_name}({accessory.stars}星)"
        return None

    @classmethod
    def _check_wedding_ring(cls, player):
        """Check if player has a wedding ring equipped."""
        equipped = DataService.get_equipped(player.id)
        accessory = equipped.get('accessory')
        return accessory and accessory.template_id in ('wedding_grass_ring', 'wedding_diamond_ring')

    @classmethod
    def propose_marriage(cls, player, target_username):
        """Propose marriage to target player."""
        target = DataService.get_player_by_username(target_username)
        if not target:
            return False, "玩家不存在"

        if target.id == player.id:
            return False, "不能和自己结婚"

        # Must be opposite gender
        if player.gender == target.gender:
            return False, "结婚需要双方性别互为异性"

        # Check both are not already married
        if cls.get_spouse(player):
            return False, "你已经结婚了"
        if cls.get_spouse(target):
            return False, f"{target.nickname}已经结婚了"

        # Check fate value
        fate = cls.get_fate_value(player.id, target.id)
        if fate < MARRIAGE_FATE_REQUIRED:
            return False, f"缘分值不足{MARRIAGE_FATE_REQUIRED}，当前{fate}"

        # Both must wear wedding rings
        if not cls._check_wedding_ring(player):
            return False, "你需要佩戴新婚草戒或新婚钻戒才能求婚"
        if not cls._check_wedding_ring(target):
            return False, f"{target.nickname}未佩戴新婚草戒或新婚钻戒，无法求婚"

        # Proposer consumes 2 bond_wine
        inv = DataService.get_inventory_item(player.id, 'bond_wine')
        if not inv or inv.quantity < 2:
            return False, "需要2杯结交酒才能求婚"

        # Check if already has pending marriage proposal from/to this player
        existing_requests = target.relation_requests
        for r in existing_requests:
            if r.get('from') == player.username and r.get('type') == 'marriage':
                return False, "已经向对方发送过求婚，等待回应"

        DataService.remove_item_from_inventory(player.id, 'bond_wine', 2)

        # Add proposal to target's relation_requests
        ring_info = cls._get_wedding_ring_info(player)
        requests = target.relation_requests
        requests.append({
            'from': player.username,
            'from_name': player.nickname,
            'type': 'marriage',
            'ring_info': ring_info or '未佩戴婚戒',
            'time': datetime.now().strftime('%Y-%m-%d %H:%M')
        })
        target.relation_requests = requests

        cls.add_notification(target, f"{player.nickname}向你求婚！佩戴{ring_info or '婚戒'}")

        db.session.commit()
        return True, f"已向{target.nickname}发送求婚"

    @classmethod
    def accept_marriage(cls, player, requester_username):
        """Accept a marriage proposal."""
        requests = player.relation_requests
        request = None
        for r in requests:
            if r.get('from') == requester_username and r.get('type') == 'marriage':
                request = r
                break

        if not request:
            return False, "没有该求婚邀请"

        requester = DataService.get_player_by_username(requester_username)
        if not requester:
            return False, "求婚者不存在"

        # Double-check conditions
        if player.gender == requester.gender:
            return False, "结婚需要双方性别互为异性"

        if cls.get_spouse(player):
            return False, "你已经结婚了"
        if cls.get_spouse(requester):
            return False, f"{requester.nickname}已经结婚了"

        # Both must wear wedding rings
        if not cls._check_wedding_ring(player):
            return False, "你需要佩戴新婚草戒或新婚钻戒才能接受求婚"
        if not cls._check_wedding_ring(requester):
            return False, f"{requester.nickname}未佩戴婚戒"

        # Remove the pending request
        new_requests = [r for r in requests if not (r.get('from') == requester_username and r.get('type') == 'marriage')]
        player.relation_requests = new_requests

        # Create or update relationship to 'spouse'
        existing = Relationship.get_relationship(player.id, requester.id)
        if existing:
            existing.rel_type = 'spouse'
            existing.initiator_id = requester.id
        else:
            rel = Relationship(
                player1_id=min(player.id, requester.id),
                player2_id=max(player.id, requester.id),
                rel_type='spouse',
                fate_value=cls.get_fate_value(player.id, requester.id),
                initiator_id=requester.id
            )
            db.session.add(rel)

        # System broadcast
        ring_info = request.get('ring_info', '婚戒')
        from services.public_chat import PublicChat
        if player.gender == '女':
            PublicChat.broadcast(f"不羡鸳鸯不羡仙，{player.nickname}与{requester.nickname}佩戴{ring_info}，结为夫妻让我们祝福新人吧！")
        else:
            PublicChat.broadcast(f"不羡鸳鸯不羡仙，{requester.nickname}与{player.nickname}佩戴{ring_info}，结为夫妻让我们祝福新人吧！")

        cls.add_notification(requester, f"{player.nickname}同意了你的求婚！你们已结为夫妻")

        db.session.commit()
        return True, f"已和{requester.nickname}结为夫妻"

    @classmethod
    def reject_marriage(cls, player, requester_username):
        """Reject a marriage proposal."""
        requests = player.relation_requests
        request = None
        for r in requests:
            if r.get('from') == requester_username and r.get('type') == 'marriage':
                request = r
                break

        if not request:
            return False, "没有该求婚邀请"

        new_requests = [r for r in requests if not (r.get('from') == requester_username and r.get('type') == 'marriage')]
        player.relation_requests = new_requests

        requester = DataService.get_player_by_username(requester_username)
        if requester:
            cls.add_notification(requester, f"{player.nickname}拒绝了你的求婚，你就是个大冤种，555~")

        db.session.commit()
        return True, "已拒绝求婚"

    @classmethod
    def divorce(cls, player):
        """Divorce - consumes 断肠草."""
        spouse = cls.get_spouse(player)
        if not spouse:
            return False, "你还没有结婚"

        inv = DataService.get_inventory_item(player.id, 'duanchang_cao')
        if not inv or inv.quantity <= 0:
            return False, "没有断肠草，离婚需要消耗1个断肠草"

        DataService.remove_item_from_inventory(player.id, 'duanchang_cao', 1)

        rel = Relationship.query.filter(
            ((Relationship.player1_id == player.id) | (Relationship.player2_id == player.id)),
            Relationship.rel_type == 'spouse'
        ).first()
        if rel:
            rel.rel_type = 'pending'

        cls.add_notification(spouse, f"{player.nickname}和你离婚了，斩断情丝，忘却因缘！")

        db.session.commit()
        return True, f"已和{spouse.nickname}离婚"

    @classmethod
    def spouse_teleport(cls, player):
        """Teleport to spouse's location (free, blocked in copy maps)."""
        spouse = cls.get_spouse(player)
        if not spouse:
            return False, "你还没有结婚"

        # Check if player is in copy map
        from services.map_service import MapService
        location = DataService.get_location(player.current_location)
        if location and location.get('is_copy_map'):
            return False, "副本内无法传送到配偶身边"

        # Check if spouse is in copy map
        spouse_location = DataService.get_location(spouse.current_location)
        if spouse_location and spouse_location.get('is_copy_map'):
            return False, "配偶当前在副本中，无法传送"

        player.current_location = spouse.current_location
        db.session.commit()
        return True, f"已传送到{spouse.nickname}身边"

    @classmethod
    def get_spouse_bonus(cls, player):
        """Get 5% bonus to max_health, max_mana, attack, defense from marriage."""
        if not cls.get_spouse(player):
            return {'max_health': 0, 'max_mana': 0, 'attack': 0, 'defense': 0}
        return {
            'max_health': int(player.max_health * 0.05),
            'max_mana': int(player.max_mana * 0.05),
            'attack': int(player.attack * 0.05),
            'defense': int(player.defense * 0.05),
        }

    @classmethod
    def notify_spouse_login(cls, player):
        """Send private message to spouse on first login after being offline."""
        spouse = cls.get_spouse(player)
        if not spouse:
            return
        label = '夫君' if spouse.gender == '女' else '妻子'
        cls.send_private_message(
            player, spouse,
            f"你的{label}{player.nickname}已经上线！"
        )

    # --- Helpers ---

    @classmethod
    def _is_online(cls, player):
        """Check if player is online (last_login within 30 minutes)."""
        if not player.last_login:
            return False
        return (datetime.utcnow() - player.last_login) < timedelta(minutes=30)

    @classmethod
    def add_notification(cls, player, message, ntype=None):
        """Add notification to player. ntype: optional type like 'friend' for styled display."""
        notifications = player.notifications
        notifications.insert(0, {
            'message': message,
            'time': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'type': ntype
        })
        player.notifications = notifications[:20]
