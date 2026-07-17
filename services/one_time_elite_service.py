# -*- coding: utf-8 -*-
"""一次性精英怪（one-time elite）机制。

与「世界BOSS/精英怪」和「副本怪」并列的第三类怪物可见性/生命周期模型：

- 仅在该玩家拥有指定主线任务（quest_gate）且处于进行中状态时，才在场景里出现。
- 击杀一次后永久消失，不复活、无全服共享血池、无倒计时。
- 仅玩家自己可见；其他玩家无论任务进度如何，都看不到这只怪。
- 标记方式：怪物数据里 is_one_time_elite: true，可选 quest_gate: "<quest_id>"。

存储：player.activity_data['one_time_elite_kills'] = [monster_id, ...]
（与 copy_dungeon 的 defeated_monsters 一样，落在持久的 activity_data JSON 里。）
"""
from services.data_service import DataService


class OneTimeEliteService:
    """一次性精英怪：单玩家可见、击杀一次后永久消失、不复活。"""

    _KILLS_KEY = 'one_time_elite_kills'

    # ---- 读取/写入玩家击杀集合 ----

    @classmethod
    def _get_killed_set(cls, player):
        data = player.activity_data or {}
        killed = data.get(cls._KILLS_KEY, [])
        if not isinstance(killed, list):
            killed = []
        return set(killed), data

    @classmethod
    def is_killed(cls, player, monster_id):
        killed, _ = cls._get_killed_set(player)
        return monster_id in killed

    @classmethod
    def record_kill(cls, player, monster_id):
        """记录一次性精英怪被该玩家击杀（永久从场景消失）。"""
        killed, data = cls._get_killed_set(player)
        if monster_id in killed:
            return
        killed.add(monster_id)
        data[cls._KILLS_KEY] = sorted(killed)
        player.activity_data = data

    # ---- 场景可见性门控 ----

    @classmethod
    def is_one_time_elite(cls, monster_data):
        return bool(monster_data and monster_data.get('is_one_time_elite'))

    @classmethod
    def should_show_in_scene(cls, player, monster_id):
        """一次性精英怪的可见性判定。

        返回 True 表示场景里应展示这只怪；返回 False 表示对当前玩家隐藏。
        规则：
        1. 必须是 is_one_time_elite 的怪物；
        2. 若配置了 quest_gate，玩家必须已接取该任务且未完成；
        3. 该玩家尚未击杀过这只怪。
        """
        monster_data = DataService.get_monster(monster_id)
        if not cls.is_one_time_elite(monster_data):
            return True  # 非一次性精英，交回原有逻辑

        # 已击杀 → 永久消失
        if cls.is_killed(player, monster_id):
            return False

        quest_gate = monster_data.get('quest_gate')
        if quest_gate:
            from services.quest_service import QuestService
            active = QuestService.get_active_quests(player)
            if quest_gate not in active:
                # 未接取该任务 → 不出现
                return False
        return True

    @classmethod
    def can_start_battle(cls, player, monster_id):
        """战斗开始前的二次校验：可见即可打。"""
        return cls.should_show_in_scene(player, monster_id)
