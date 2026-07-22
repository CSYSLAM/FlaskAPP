import time
from services import db
from models.player import PartyChat


MAX_PARTY_SIZE = 5
BONUS_PER_MEMBER = 0.01  # 1% per online member

# Track logged-in user IDs for online detection
_online_players = set()


def mark_online(player_id):
    _online_players.add(player_id)


def mark_offline(player_id):
    _online_players.discard(player_id)


def is_player_online(player_id):
    return player_id in _online_players


def get_online_player_ids():
    """返回当前在线的 player_id 列表（副本）。"""
    return list(_online_players)


class PartyState:
    __slots__ = ('party_id', 'leader_id', 'members', 'created_at', 'invites', 'applications')

    def __init__(self, party_id, leader_id):
        self.party_id = party_id
        self.leader_id = leader_id
        self.members = {leader_id}  # set of player_id
        self.created_at = time.time()
        self.invites = {}  # {player_id: expire_time}
        self.applications = {}  # {player_id: apply_time}


class PartyService:
    _parties = {}  # {party_id: PartyState}
    _player_party = {}  # {player_id: party_id}
    _next_id = 1

    @classmethod
    def create_party(cls, player):
        if player.id in cls._player_party:
            return None, "你已在队伍中"
        party_id = cls._next_id
        cls._next_id += 1
        party = PartyState(party_id, player.id)
        cls._parties[party_id] = party
        cls._player_party[player.id] = party_id
        player.party_id = party_id
        db.session.commit()
        return party, None

    @classmethod
    def get_party(cls, party_id):
        return cls._parties.get(party_id)

    @classmethod
    def get_player_party(cls, player):
        party_id = cls._player_party.get(player.id)
        if party_id:
            party = cls._parties.get(party_id)
            if party and player.id in party.members:
                return party
            # Stale mapping, clean up
            cls._player_party.pop(player.id, None)
        # Check DB party_id
        if player.party_id:
            party = cls._parties.get(player.party_id)
            if party and player.id in party.members:
                # Re-sync mapping
                cls._player_party[player.id] = player.party_id
                return party
            # DB party_id is stale, clean up
            player.party_id = None
            db.session.commit()
        return None

    # --- Party chat (队伍聊天) ---

    @classmethod
    def send_party_message(cls, player, content):
        """Send a message in the player's current party chat."""
        party = cls.get_player_party(player)
        if not party:
            return False, "你不在任何队伍中"

        content = content.strip()[:30]
        if not content:
            return False, "消息不能为空"

        msg = PartyChat(
            party_id=party.party_id,
            sender_id=player.id,
            sender_name=player.nickname,
            content=content,
        )
        db.session.add(msg)
        db.session.commit()
        return True, "发送成功"

    @classmethod
    def get_party_messages(cls, player, page=1, per_page=20):
        """Get party chat messages for the player's current party."""
        party = cls.get_player_party(player)
        if not party:
            return [], 0

        query = PartyChat.query.filter_by(party_id=party.party_id)
        total = query.count()
        messages = query.order_by(PartyChat.created_at.desc()).offset(
            (page - 1) * per_page).limit(per_page).all()
        return messages, total

    @classmethod
    def leave_party(cls, player):
        party_id = cls._player_party.get(player.id)
        if not party_id:
            return False, "你不在队伍中"
        party = cls._parties.get(party_id)
        if not party:
            cls._player_party.pop(player.id, None)
            player.party_id = None
            db.session.commit()
            return True, "已离开队伍"
        party.members.discard(player.id)
        cls._player_party.pop(player.id, None)
        player.party_id = None
        db.session.commit()

        if player.id == party.leader_id:
            cls._dissolve_party(party_id)
            return True, "队伍已解散"
        else:
            if not party.members:
                cls._dissolve_party(party_id)
            return True, "已离开队伍"

    @classmethod
    def kick_member(cls, leader, target_id):
        party = cls.get_player_party(leader)
        if not party:
            return False, "你不在队伍中"
        if party.leader_id != leader.id:
            return False, "只有队长可以踢人"
        if target_id not in party.members:
            return False, "该玩家不在队伍中"
        if target_id == party.leader_id:
            return False, "不能踢出自己"
        party.members.discard(target_id)
        cls._player_party.pop(target_id, None)
        from models.player import PlayerModel
        target = PlayerModel.query.get(target_id)
        if target:
            target.party_id = None
            db.session.commit()
        return True, "已将玩家踢出队伍"

    @classmethod
    def invite_player(cls, leader, target_id):
        party = cls.get_player_party(leader)
        if not party:
            return False, "你不在队伍中"
        if party.leader_id != leader.id:
            return False, "只有队长可以邀请"
        if target_id in cls._player_party:
            return False, "对方已在其他队伍中"
        if target_id in party.members:
            return False, "对方已在本队伍中"
        if len(party.members) >= MAX_PARTY_SIZE:
            return False, "队伍已满"
        party.invites[target_id] = time.time() + 60  # 60s expiry
        return True, "已发送邀请"

    @classmethod
    def accept_invite(cls, player, party_id):
        if player.id in cls._player_party:
            return False, "你已在队伍中"
        party = cls._parties.get(party_id)
        if not party:
            return False, "队伍不存在"
        if player.id not in party.invites:
            return False, "没有收到该队伍的邀请"
        if party.invites[player.id] < time.time():
            party.invites.pop(player.id, None)
            return False, "邀请已过期"
        if len(party.members) >= MAX_PARTY_SIZE:
            party.invites.pop(player.id, None)
            return False, "队伍已满"
        party.members.add(player.id)
        party.invites.pop(player.id, None)
        cls._player_party[player.id] = party_id
        player.party_id = party_id
        db.session.commit()
        return True, None

    @classmethod
    def apply_to_party(cls, player, party_id):
        if player.id in cls._player_party:
            return False, "你已在队伍中"
        party = cls._parties.get(party_id)
        if not party:
            return False, "队伍不存在"
        party.applications[player.id] = time.time()
        return True, "已发送申请"

    @classmethod
    def accept_application(cls, leader, applicant_id):
        party = cls.get_player_party(leader)
        if not party:
            return False, "你不在队伍中"
        if party.leader_id != leader.id:
            return False, "只有队长可以审批申请"
        if applicant_id not in party.applications:
            return False, "没有该玩家的申请"
        if applicant_id in cls._player_party:
            party.applications.pop(applicant_id, None)
            return False, "对方已加入其他队伍"
        if len(party.members) >= MAX_PARTY_SIZE:
            party.applications.pop(applicant_id, None)
            return False, "队伍已满"
        party.members.add(applicant_id)
        party.applications.pop(applicant_id, None)
        cls._player_party[applicant_id] = party.party_id
        from models.player import PlayerModel
        applicant = PlayerModel.query.get(applicant_id)
        if applicant:
            applicant.party_id = party.party_id
            db.session.commit()
        return True, None

    @classmethod
    def reject_application(cls, leader, applicant_id):
        party = cls.get_player_party(leader)
        if not party:
            return False, "你不在队伍中"
        if party.leader_id != leader.id:
            return False, "只有队长可以审批申请"
        party.applications.pop(applicant_id, None)
        return True, "已拒绝申请"

    @classmethod
    def get_pending_invites(cls, player):
        result = []
        for party_id, party in cls._parties.items():
            if player.id in party.invites and party.invites[player.id] > time.time():
                result.append(party)
            else:
                party.invites.pop(player.id, None)
        return result

    @classmethod
    def get_online_member_count(cls, party):
        count = 0
        for mid in party.members:
            if is_player_online(mid):
                count += 1
        return count

    @classmethod
    def get_party_bonus_rate(cls, player):
        party = cls.get_player_party(player)
        if not party:
            return 0.0
        online_count = cls.get_online_member_count(party)
        return online_count * BONUS_PER_MEMBER

    @classmethod
    def _dissolve_party(cls, party_id):
        party = cls._parties.pop(party_id, None)
        if not party:
            return
        from models.player import PlayerModel
        for mid in party.members:
            cls._player_party.pop(mid, None)
            p = PlayerModel.query.get(mid)
            if p:
                p.party_id = None
        db.session.commit()

    @classmethod
    def remove_offline_members(cls):
        from models.player import PlayerModel
        to_remove = []
        for party_id, party in list(cls._parties.items()):
            for mid in list(party.members):
                if not is_player_online(mid):
                    if mid != party.leader_id:
                        to_remove.append((party_id, mid))
            for pid, mid in to_remove:
                pty = cls._parties.get(pid)
                if pty:
                    pty.members.discard(mid)
                    cls._player_party.pop(mid, None)
                    p = PlayerModel.query.get(mid)
                    if p:
                        p.party_id = None
            if to_remove:
                db.session.commit()

    @classmethod
    def on_player_disconnect(cls, player):
        party = cls.get_player_party(player)
        if not party:
            return
        if party.leader_id == player.id:
            cls._dissolve_party(party.party_id)
        else:
            party.members.discard(player.id)
            cls._player_party.pop(player.id, None)
            player.party_id = None
            db.session.commit()
