import json
from services import db
from models.player import PlayerModel


class PublicChat:

    @classmethod
    def add_message(cls, username, content, msg_type="public"):
        if msg_type == "system":
            from services.data_service import DataService
            DataService.broadcast_system(content)
        else:
            from services.data_service import DataService
            player = DataService.get_player_by_username(username) if username else None
            DataService.broadcast_player(player.id if player else None, content)

    @classmethod
    def broadcast(cls, content, msg_type="system"):
        cls.add_message("", content, msg_type=msg_type)

    @classmethod
    def _collect_new(cls, player):
        """Collect new messages since last seen and add to pending.
        Returns current pending list. Does NOT tick or save."""
        from services.data_service import DataService
        all_msgs = DataService.list_latest_messages(200)
        all_msgs_asc = list(reversed(all_msgs))

        last_seen_id = player.chat_refresh_count or 0
        new_msgs = [m for m in all_msgs_asc if m.id > last_seen_id]

        # Read raw column directly to avoid property auto-parse
        raw = player.notifications_raw
        pending = []
        try:
            pending = json.loads(raw) if raw else []
        except (json.JSONDecodeError, TypeError):
            pending = []

        if new_msgs:
            for msg in new_msgs:
                pending.append({
                    "type": msg.message_type,
                    "content": msg.content,
                    "username": msg.sender.nickname if msg.sender and msg.message_type == 'player' else "",
                    "refreshes": 0,
                })
            player.chat_refresh_count = new_msgs[-1].id
            player.notifications_raw = json.dumps(pending, ensure_ascii=False)
            db.session.commit()

        return pending

    @classmethod
    def get_display_messages(cls, player, tick=True):
        """Get messages to display for this player.
        tick=True: page refresh, increment refresh counters, remove expired
        tick=False: AJAX poll, just return current pending without ticking"""
        pending = cls._collect_new(player)

        if tick:
            display = []
            kept = []
            for m in pending:
                m["refreshes"] += 1
                if m["refreshes"] <= 3:
                    display.append(m)
                    kept.append(m)
            player.notifications_raw = json.dumps(kept, ensure_ascii=False)
            db.session.commit()
        else:
            display = list(pending)

        system_msgs = [m for m in display if m["type"] == "system"]
        public_msgs = [m for m in display if m["type"] != "system"]
        return system_msgs, public_msgs