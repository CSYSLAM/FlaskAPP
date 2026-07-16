import json
import re
from services import db
from services.data_service import DataService


class QuestService:
    _quests = None

    # 国家 -> 主线任务id前缀。主线任务按国家隔离,玩家只走本国任务链。
    # 魏=main_wei_xx, 吴=main_wu_xx, 蜀=main_shu_xx
    _COUNTRY_PREFIX = {'魏': 'main_wei_', '吴': 'main_wu_', '蜀': 'main_shu_'}

    @classmethod
    def _country_prefix(cls, player):
        """玩家所属国家的主线任务id前缀。无国家/未知国家默认魏。"""
        c = getattr(player, 'country', None) or '魏'
        return cls._COUNTRY_PREFIX.get(c, 'main_wei_')

    @classmethod
    def _is_own_country_quest(cls, player, qid):
        """该任务是否属于玩家本国(按id前缀判断)。非main_开头(如支线)不限制。"""
        if not qid or not qid.startswith('main_'):
            return True
        return qid.startswith(cls._country_prefix(player))

    @classmethod
    def get_country_quests(cls, player):
        """返回玩家本国的所有主线任务(按country前缀过滤),供任务列表/可接任务页展示。"""
        prefix = cls._country_prefix(player)
        return {qid: q for qid, q in cls._load().items() if qid.startswith(prefix)}

    @classmethod
    def _load(cls):
        if cls._quests is None:
            import os
            path = 'data/quests.json'
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    cls._quests = json.load(f)
            else:
                cls._quests = {}
        return cls._quests

    @classmethod
    def get_quest(cls, quest_id):
        return cls._load().get(quest_id)

    @classmethod
    def get_all_quests(cls):
        return cls._load()

    @classmethod
    def get_active_quests(cls, player):
        try:
            return json.loads(player.active_quests) if player.active_quests else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    @classmethod
    def set_active_quests(cls, player, data):
        player.active_quests = json.dumps(data, ensure_ascii=False)

    @classmethod
    def get_completed_quests(cls, player):
        try:
            return json.loads(player.completed_quests) if player.completed_quests else []
        except (json.JSONDecodeError, TypeError):
            return []

    @classmethod
    def set_completed_quests(cls, player, data):
        player.completed_quests = json.dumps(data, ensure_ascii=False)

    @classmethod
    def get_current_main_quest(cls, player):
        """Get the player's current main quest or the next available one."""
        completed = cls.get_completed_quests(player)
        active = cls.get_active_quests(player)
        all_quests = cls._load()
        prefix = cls._country_prefix(player)
        # Find active main quest (仅本国主线)
        for qid in active:
            if not qid.startswith(prefix):
                continue
            q = all_quests.get(qid)
            if q and q.get('type') == 'main':
                return q
        # Find next uncompleted main quest (仅本国主线)
        for qid, q in all_quests.items():
            if not qid.startswith(prefix):
                continue
            if q.get('type') == 'main' and qid not in completed:
                prereq = q.get('prerequisite')
                if not prereq or prereq in completed:
                    return q
        return None

    @classmethod
    def can_accept_quest(cls, player, quest_id):
        q = cls.get_quest(quest_id)
        if not q:
            return False, "任务不存在"
        # 国家隔离: 主线任务只能接本国的
        if not cls._is_own_country_quest(player, quest_id):
            return False, "这不是你本国的任务"
        if player.level < q.get('level_required', 1):
            return False, f"需要等级{q['level_required']}"
        completed = cls.get_completed_quests(player)
        if quest_id in completed:
            return False, "任务已完成"
        active = cls.get_active_quests(player)
        if quest_id in active:
            return False, "任务已接受"
        prereq = q.get('prerequisite')
        if prereq and prereq not in completed:
            pq = cls.get_quest(prereq)
            return False, f"需要先完成前置任务：{pq['name'] if pq else prereq}"
        return True, ""

    @classmethod
    def accept_quest(cls, player, quest_id):
        ok, msg = cls.can_accept_quest(player, quest_id)
        if not ok:
            return False, msg
        active = cls.get_active_quests(player)
        # Initialize progress based on objective type
        q = cls.get_quest(quest_id)
        obj = q.get('objective', {})
        progress = {'progress': 0, 'target': obj.get('count', 1)}

        # For deliver_item: check if player has the required item
        if obj.get('type') == 'deliver_item':
            item_id = obj.get('item_id', '')
            inv = DataService.get_inventory_item(player.id, item_id)
            if inv and inv.quantity >= obj.get('count', 1):
                progress['progress'] = obj.get('count', 1)  # Already have it

        active[quest_id] = progress
        cls.set_active_quests(player, active)

        db.session.commit()
        return True, q['name']

    @classmethod
    def complete_quest(cls, player, quest_id):
        q = cls.get_quest(quest_id)
        if not q:
            return False, "任务不存在"
        active = cls.get_active_quests(player)
        if quest_id not in active:
            return False, "未接受此任务"
        # Check objective completion
        progress = active[quest_id]
        if progress.get('progress', 0) < progress.get('target', 1):
            return False, "任务目标未完成"
        # For deliver_item: consume item from inventory
        obj = q.get('objective', {})
        if obj.get('type') == 'deliver_item':
            item_id = obj.get('item_id', '')
            DataService.remove_item_from_inventory(player.id, item_id, obj.get('count', 1))

        # Apply rewards
        rewards = q.get('rewards', {})
        if rewards.get('experience'):
            from services.player_service import PlayerService
            PlayerService.gain_experience(player, rewards['experience'])
        if rewards.get('gold'):
            player.gold += rewards['gold']
            player.gold_earned = (player.gold_earned or 0) + rewards['gold']
        if rewards.get('honor'):
            player.honor = (player.honor or 0) + rewards['honor']
        # Move from active to completed
        del active[quest_id]
        cls.set_active_quests(player, active)
        # Grant item if quest has one (for next quest chain)
        grant = q.get('grant_item')
        if grant:
            item_id = grant['item_id']
            if item_id.startswith('equipment_'):
                # Generate equipment from template
                from services.equipment_service import EquipmentService
                tid = item_id[len('equipment_'):]
                equip = EquipmentService.generate_random_equipment(player.id, tid, rarity="普通", stars=1)
                if equip:
                    DataService.add_item_to_inventory(player.id, equip.instance_id)
            else:
                DataService.add_item_to_inventory(player.id, item_id, grant.get('count', 1))

        completed = cls.get_completed_quests(player)
        completed.append(quest_id)
        cls.set_completed_quests(player, completed)
        db.session.commit()
        return True, q['name']

    @classmethod
    def abandon_quest(cls, player, quest_id):
        active = cls.get_active_quests(player)
        if quest_id not in active:
            return False, "未接受此任务"
        del active[quest_id]
        cls.set_active_quests(player, active)
        db.session.commit()
        return True, "已放弃"

    @classmethod
    def update_kill_progress(cls, player, monster_name, dropped_items=None):
        """Called after monster defeat to update kill/collect quests."""
        active = cls.get_active_quests(player)
        updated = False
        dropped = dropped_items or []
        for qid, progress in active.items():
            q = cls.get_quest(qid)
            if not q:
                continue
            obj = q.get('objective', {})
            if obj.get('type') == 'kill_monster' and obj.get('monster_name') == monster_name:
                progress['progress'] = progress.get('progress', 0) + 1
                progress['target'] = obj.get('count', 1)
                updated = True
            elif obj.get('type') == 'collect_item' and obj.get('monster_name') == monster_name:
                # Check if required item dropped
                item_name = obj.get('item_name', '')
                if item_name in dropped:
                    progress['progress'] = progress.get('progress', 0) + 1
                    progress['target'] = obj.get('count', 1)
                    updated = True
        if updated:
            cls.set_active_quests(player, active)
            db.session.commit()

    @classmethod
    def update_buy_item_progress(cls, player, item_id):
        """Called after player buys an item."""
        active = cls.get_active_quests(player)
        updated = False
        for qid, progress in active.items():
            q = cls.get_quest(qid)
            if not q: continue
            obj = q.get('objective', {})
            if obj.get('type') == 'buy_item' and obj.get('item_id') == item_id:
                progress['progress'] = progress.get('progress', 0) + 1
                progress['target'] = obj.get('count', 1)
                updated = True
        if updated:
            cls.set_active_quests(player, active)
            db.session.commit()

    @classmethod
    def update_learn_skill_progress(cls, player):
        """Called after player learns any skill."""
        active = cls.get_active_quests(player)
        updated = False
        for qid, progress in active.items():
            q = cls.get_quest(qid)
            if not q:
                continue
            obj = q.get('objective', {})
            if obj.get('type') == 'learn_skill':
                progress['progress'] = obj.get('count', 1)
                progress['target'] = obj.get('count', 1)
                updated = True
        if updated:
            cls.set_active_quests(player, active)
            db.session.commit()

    @classmethod
    def update_talk_progress(cls, player, npc_id):
        """Called when talking to NPC to update talk quests."""
        active = cls.get_active_quests(player)
        updated = False
        for qid, progress in active.items():
            q = cls.get_quest(qid)
            if not q:
                continue
            obj = q.get('objective', {})
            if obj.get('type') == 'talk_npc' and obj.get('npc_id') == npc_id:
                progress['progress'] = obj.get('count', 1)  # Mark complete
                progress['target'] = obj.get('count', 1)
                updated = True
        if updated:
            cls.set_active_quests(player, active)
            db.session.commit()

    @classmethod
    def is_quest_objective_met(cls, player, quest_id):
        active = cls.get_active_quests(player)
        if quest_id not in active:
            return True  # Not active, so no objective to meet
        progress = active[quest_id]
        return progress.get('progress', 0) >= progress.get('target', 1)

    @classmethod
    def get_available_quests_for_npc(cls, player, npc_id):
        """Get quests available from an NPC for this player."""
        all_quests = cls._load()
        available = []
        seen = set()
        active = cls.get_active_quests(player)
        # Fast path using pre-built NPC index
        npc_map = getattr(cls, '_npc_quest_map', None)
        if npc_map is None:
            npc_map = {}
            for qid, q in all_quests.items():
                nid = q.get('npc_id', '')
                if nid not in npc_map:
                    npc_map[nid] = []
                npc_map[nid].append(qid)
            cls._npc_quest_map = npc_map
        completed = cls.get_completed_quests(player)
        candidate_ids = npc_map.get(npc_id, [])
        for qid in candidate_ids:
            q = all_quests.get(qid)
            if not q or qid in seen:
                continue
            if qid in active:
                available.append(q)
                seen.add(qid)
                continue
            ok, _ = cls.can_accept_quest(player, qid)
            if ok:
                available.append(q)
                seen.add(qid)
                continue
            # 前置已满足、尚未完成，但因等级不足暂不可接取的任务也要展示，
            # 让玩家知道任务存在；quest_detail 会显示“需要等级X”并阻止接取。
            if qid not in completed:
                prereq = q.get('prerequisite')
                if (not prereq) or (prereq in completed):
                    available.append(q)
                    seen.add(qid)
        return available

    @classmethod
    def get_active_quest_count(cls, player):
        return len(cls.get_active_quests(player))
