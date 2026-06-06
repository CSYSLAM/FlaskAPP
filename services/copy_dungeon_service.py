from services import db
from services.data_service import DataService


class CopyDungeonService:
    STATE_KEY = 'copy_dungeons'

    @classmethod
    def _grant_reward(cls, player, reward):
        if not reward:
            return

        player.gold += reward.get('gold', 0)
        player.experience += reward.get('experience', 0)
        for reward_item in reward.get('items', []):
            item_id = reward_item.get('item_id')
            count = reward_item.get('count', 1)
            if item_id:
                DataService.add_item_to_inventory(player.id, item_id, count)

    @classmethod
    def get_definitions(cls):
        return DataService.get_copy_dungeons()

    @classmethod
    def get_definition(cls, dungeon_id):
        return cls.get_definitions().get(dungeon_id)

    @classmethod
    def get_dungeon_id_by_npc(cls, npc_id):
        monster_data = DataService.get_monster(npc_id)
        if monster_data and monster_data.get('copy_dungeon_id'):
            return monster_data.get('copy_dungeon_id')

        definitions = cls.get_definitions()
        for dungeon_id, definition in definitions.items():
            if definition.get('entry_npc_id') == npc_id:
                return dungeon_id
        return None

    @classmethod
    def _ensure_state_root(cls, player):
        data = player.activity_data
        root = data.get(cls.STATE_KEY, {})
        if not isinstance(root, dict):
            root = {}
        data[cls.STATE_KEY] = root
        return data, root

    @classmethod
    def _default_state(cls):
        return {
            'accepted': False,
            'stage_index': 0,
            'progress': 0,
            'ready_to_complete': False,
            'completed': False,
            'reward_claimed': False,
            'defeated_monsters': [],
        }

    @classmethod
    def _fresh_run_state(cls):
        return cls._default_state().copy()

    @classmethod
    def _normalize_defeated_monsters(cls, state):
        defeated = state.get('defeated_monsters', [])
        if not isinstance(defeated, list):
            defeated = []
        state['defeated_monsters'] = defeated
        return state

    @classmethod
    def get_state(cls, player, dungeon_id):
        data, root = cls._ensure_state_root(player)
        state = root.get(dungeon_id, {})
        merged = cls._default_state()
        merged.update(state if isinstance(state, dict) else {})
        cls._normalize_defeated_monsters(merged)
        root[dungeon_id] = merged
        data[cls.STATE_KEY] = root
        player.activity_data = data
        return merged

    @classmethod
    def save_state(cls, player, dungeon_id, state):
        data, root = cls._ensure_state_root(player)
        cls._normalize_defeated_monsters(state)
        root[dungeon_id] = state
        data[cls.STATE_KEY] = root
        player.activity_data = data

    @classmethod
    def clear_state(cls, player, dungeon_id):
        data, root = cls._ensure_state_root(player)
        root.pop(dungeon_id, None)
        data[cls.STATE_KEY] = root
        player.activity_data = data

    @classmethod
    def is_monster_defeated(cls, player, monster_id, dungeon_id=None):
        data = player.activity_data
        root = data.get(cls.STATE_KEY, {})
        if not isinstance(root, dict):
            return False

        if dungeon_id:
            state = root.get(dungeon_id, {})
            defeated = state.get('defeated_monsters', []) if isinstance(state, dict) else []
            return monster_id in defeated

        for state in root.values():
            if isinstance(state, dict) and monster_id in state.get('defeated_monsters', []):
                return True
        return False

    @classmethod
    def mark_monster_defeated(cls, player, dungeon_id, monster_id):
        state = cls.get_state(player, dungeon_id)
        defeated = state.get('defeated_monsters', [])
        if monster_id not in defeated:
            defeated.append(monster_id)
            state['defeated_monsters'] = defeated
            cls.save_state(player, dungeon_id, state)

    @classmethod
    def _is_copy_monster(cls, monster_data):
        if not monster_data:
            return False
        return bool(monster_data.get('is_copy') or monster_data.get('copy_only'))

    @classmethod
    def _should_despawn_copy_monster(cls, monster_data):
        if not cls._is_copy_monster(monster_data):
            return False
        return bool(monster_data.get('despawn_after_defeat', monster_data.get('is_elite', False) or monster_data.get('copy_final_boss', False)))

    @classmethod
    def _has_required_items(cls, player, required_items):
        if not required_items:
            return True, None

        for item_id, required_count in required_items.items():
            inv = DataService.get_inventory_item(player.id, item_id)
            if not inv or inv.quantity < required_count:
                item_data = DataService.get_item(item_id)
                item_name = item_data.get('name', item_id) if item_data else item_id
                return False, f'需要{required_count}个{item_name}'

        return True, None

    @classmethod
    def should_show_monster_in_scene(cls, player, monster_id):
        monster_data = DataService.get_monster(monster_id)
        if not monster_data:
            return True

        if not cls._is_copy_monster(monster_data):
            return True

        dungeon_id = monster_data.get('copy_dungeon_id')
        if not dungeon_id:
            return False

        definition = cls.get_definition(dungeon_id)
        if not definition:
            return False

        state = cls.get_state(player, dungeon_id)
        if not state.get('accepted') or state.get('reward_claimed'):
            return False

        stage = cls.get_current_stage(definition, state)
        if not stage:
            return False

        stage_id = stage.get('id')
        monster_stage = monster_data.get('copy_stage')
        if monster_stage and stage_id and monster_stage != stage_id:
            return False

        if cls._should_despawn_copy_monster(monster_data) and cls.is_monster_defeated(player, monster_id, dungeon_id):
            return False

        return True

    @classmethod
    def get_npc_marker(cls, player, npc_id):
        dungeon_id = cls.get_dungeon_id_by_npc(npc_id)
        if not dungeon_id:
            return None

        definition = cls.get_definition(dungeon_id)
        if not definition:
            return None

        data = player.activity_data
        root = data.get(cls.STATE_KEY, {})
        state = root.get(dungeon_id, {}) if isinstance(root, dict) else {}
        if not isinstance(state, dict):
            state = {}

        monster_data = DataService.get_monster(npc_id) or {}

        # entry_npc: handles enter/re-enter
        if monster_data.get('copy_role') == 'entry_npc':
            if state.get('completed') or state.get('reward_claimed'):
                return {'icon': 'gt.gif', 'label': '可再次进入'}
            if not state.get('accepted'):
                return {'icon': 'gt.gif', 'label': '可接任务'}
            return None

        # quest_giver: only show markers if this NPC is the current stage's quest giver
        stage = cls.get_current_stage(definition, state)
        if stage and stage.get('quest_giver_npc_id'):
            if npc_id != stage.get('quest_giver_npc_id'):
                return None
        else:
            # fallback: if no quest_giver_npc_id configured, allow all quest_givers
            pass

        if state.get('accepted') and state.get('ready_to_complete') and not state.get('reward_claimed'):
            return {'icon': 'wh.gif', 'label': '可交任务'}

        if state.get('accepted') and not state.get('completed') and not state.get('reward_claimed'):
            return {'icon': 'gt.gif', 'label': '进行中'}

        if not state.get('accepted'):
            return {'icon': 'gt.gif', 'label': '可接任务'}

        return None

    @classmethod
    def _get_quest_giver_location(cls, definition, state):
        """Get the location where the player should be to accept/complete the current stage."""
        stage = cls.get_current_stage(definition, state)
        if stage and stage.get('quest_giver_location'):
            return stage.get('quest_giver_location')
        return definition.get('entry_location')

    @classmethod
    def get_current_stage(cls, definition, state):
        steps = definition.get('steps', [])
        index = min(state.get('stage_index', 0), max(0, len(steps) - 1))
        return steps[index] if steps else None

    @classmethod
    def build_npc_context(cls, player, npc_id):
        dungeon_id = cls.get_dungeon_id_by_npc(npc_id)
        definition = cls.get_definition(dungeon_id) if dungeon_id else None
        if not definition:
            return None

        state = cls.get_state(player, dungeon_id)
        monster_data = DataService.get_monster(npc_id) or {}
        if monster_data.get('copy_role') == 'quest_giver' and (state.get('completed') or state.get('reward_claimed')):
            cls.clear_state(player, dungeon_id)
            state = cls.get_state(player, dungeon_id)

        stage = cls.get_current_stage(definition, state)
        next_stage = None
        steps = definition.get('steps', [])
        if stage and state.get('stage_index', 0) + 1 < len(steps):
            next_stage = steps[state.get('stage_index', 0) + 1]

        # Check if this NPC is the current stage's quest giver
        is_current_quest_giver = True
        if monster_data.get('copy_role') == 'quest_giver' and stage and stage.get('quest_giver_npc_id'):
            is_current_quest_giver = (npc_id == stage.get('quest_giver_npc_id'))

        current_scene = DataService.get_location(player.current_location)
        entry_item_id = definition.get('entry_item_id')
        entry_item = DataService.get_item(entry_item_id) if entry_item_id else None
        quest_giver_location = cls._get_quest_giver_location(definition, state)

        return {
            'dungeon_id': dungeon_id,
            'dungeon': definition,
            'state': state,
            'stage': stage,
            'next_stage': next_stage,
            'npc_id': npc_id,
            'entry_location': definition.get('entry_location'),
            'quest_giver_location': quest_giver_location,
            'return_location': definition.get('return_location'),
            'entry_item_id': entry_item_id,
            'entry_item_name': entry_item.get('name', entry_item_id) if entry_item else entry_item_id,
            'entry_item_count': definition.get('entry_item_count', 1),
            'current_location': player.current_location,
            'current_scene_name': current_scene.get('name') if current_scene else player.current_location,
            'is_current_quest_giver': is_current_quest_giver,
        }

    @classmethod
    def jump_to_entry(cls, player, dungeon_id):
        definition = cls.get_definition(dungeon_id)
        if not definition:
            return False, '副本不存在'

        state = cls.get_state(player, dungeon_id)
        target_location = cls._get_quest_giver_location(definition, state)
        if not target_location:
            return False, '副本入口未配置'

        player.current_location = target_location
        location_data = DataService.get_location(target_location)
        location_name = location_data.get('name', target_location) if location_data else target_location
        db.session.commit()
        return True, f'已传送回{location_name}'

    @classmethod
    def jump_to_current_stage(cls, player, dungeon_id):
        definition = cls.get_definition(dungeon_id)
        if not definition:
            return False, '副本不存在'

        state = cls.get_state(player, dungeon_id)
        if not state.get('accepted'):
            return False, '请先接受副本任务'

        stage = cls.get_current_stage(definition, state)
        if not stage:
            return False, '当前阶段不存在'

        scene_id = stage.get('scene_id')
        if not scene_id:
            return False, '当前阶段未配置目标场景'

        player.current_location = scene_id
        db.session.commit()
        return True, f"已前往【{stage.get('scene_id', scene_id).split('.')[-1]}】"

    @classmethod
    def enter_dungeon(cls, player, dungeon_id):
        definition = cls.get_definition(dungeon_id)
        if not definition:
            return False, '副本不存在'

        entry_location = definition.get('entry_location')
        locations = DataService.get_locations()
        if entry_location not in locations:
            return False, '副本入口未配置'

        entry_item_id = definition.get('entry_item_id')
        entry_item_count = definition.get('entry_item_count', 1)
        if entry_item_id:
            entry_item = DataService.get_item(entry_item_id)
            entry_item_name = entry_item.get('name', entry_item_id) if entry_item else entry_item_id
            inv = DataService.get_inventory_item(player.id, entry_item_id)
            if not inv or inv.quantity < entry_item_count:
                return False, f'进入副本需要消耗{entry_item_count}个{entry_item_name}'
            DataService.remove_item_from_inventory(player.id, entry_item_id, entry_item_count)

        state = cls.get_state(player, dungeon_id)
        if state.get('completed') or state.get('reward_claimed'):
            cls.clear_state(player, dungeon_id)

        player.current_location = entry_location
        db.session.commit()
        return True, f"已进入【{definition.get('name', dungeon_id)}】"

    @classmethod
    def leave_dungeon(cls, player, dungeon_id):
        definition = cls.get_definition(dungeon_id)
        if not definition:
            return False, '副本不存在'

        data, root = cls._ensure_state_root(player)
        if dungeon_id in root:
            root.pop(dungeon_id, None)
            data[cls.STATE_KEY] = root
            player.activity_data = data

        return_location = definition.get('return_location')
        if return_location:
            player.current_location = return_location

        db.session.commit()
        return True, f"已离开【{definition.get('name', dungeon_id)}】，副本进度已清空"

    @classmethod
    def accept_task(cls, player, dungeon_id):
        definition = cls.get_definition(dungeon_id)
        if not definition:
            return False, '副本不存在', None

        state = cls.get_state(player, dungeon_id)

        quest_giver_location = cls._get_quest_giver_location(definition, state)

        if player.current_location != quest_giver_location:
            location_data = DataService.get_location(quest_giver_location)
            location_name = location_data.get('name', quest_giver_location) if location_data else quest_giver_location
            return False, f'请先前往{location_name}接受任务', None

        if state.get('accepted') and not state.get('completed') and not state.get('reward_claimed'):
            return False, '副本任务进行中', None

        state = cls._fresh_run_state()
        state['accepted'] = True

        # For delivery-type first stage, auto-check required items
        first_stage = cls.get_current_stage(definition, state)
        if first_stage and not first_stage.get('target_monsters') and first_stage.get('required_count', 1) == 0:
            required_items = first_stage.get('required_items', {})
            if required_items:
                has_items, _ = cls._has_required_items(player, required_items)
                if has_items:
                    state['ready_to_complete'] = True

        cls.save_state(player, dungeon_id, state)
        db.session.commit()
        stage = cls.get_current_stage(definition, state)
        return True, f"已接受【{definition.get('name', dungeon_id)}】", {
            'dungeon': definition,
            'stage': stage,
        }

    @classmethod
    def complete_stage(cls, player, dungeon_id):
        definition = cls.get_definition(dungeon_id)
        if not definition:
            return False, '副本不存在', False, None

        state = cls.get_state(player, dungeon_id)
        quest_giver_location = cls._get_quest_giver_location(definition, state)

        if player.current_location != quest_giver_location:
            location_data = DataService.get_location(quest_giver_location)
            location_name = location_data.get('name', quest_giver_location) if location_data else quest_giver_location
            return False, f'请先返回{location_name}完成任务', False, None

        stage = cls.get_current_stage(definition, state)
        if not state.get('accepted'):
            return False, '请先接受副本任务', False, None
        if not stage:
            return False, '副本阶段异常', False, None
        if not state.get('ready_to_complete'):
            return False, '当前阶段目标尚未完成', False, None

        required_items = stage.get('required_items', {})
        has_required_items, missing_message = cls._has_required_items(player, required_items)
        if not has_required_items:
            return False, missing_message, False, None

        # Consume required items
        for item_id, count in required_items.items():
            DataService.remove_item_from_inventory(player.id, item_id, count)

        cls._grant_reward(player, stage.get('reward', {}))
        steps = definition.get('steps', [])
        is_last = state.get('stage_index', 0) >= len(steps) - 1
        if is_last:
            final_reward = definition.get('reward', {})
            cls._grant_reward(player, final_reward)
            return_location = definition.get('return_location', player.current_location)
            return_location_data = DataService.get_location(return_location) if return_location else None
            player.current_location = return_location
            cls.clear_state(player, dungeon_id)
            db.session.commit()
            return True, '副本已通关', True, {
                'dungeon': definition,
                'story_outro': definition.get('story_outro', []),
                'reward': final_reward,
                'return_location': return_location,
                'return_location_name': return_location_data.get('name') if return_location_data else return_location,
                'reward_items': final_reward.get('items', []),
            }

        state['stage_index'] += 1
        state['progress'] = 0
        state['ready_to_complete'] = False

        # For delivery-type stages (no target monsters), auto-check required items
        next_stage = cls.get_current_stage(definition, state)
        if next_stage and not next_stage.get('target_monsters') and next_stage.get('required_count', 1) == 0:
            required_items = next_stage.get('required_items', {})
            if required_items:
                has_items, _ = cls._has_required_items(player, required_items)
                if has_items:
                    state['ready_to_complete'] = True

        cls.save_state(player, dungeon_id, state)
        db.session.commit()
        next_name = next_stage.get('name', '下一阶段') if next_stage else '下一阶段'
        return True, f"阶段已完成，已开启【{next_name}】", False, {
            'dungeon': definition,
            'completed_stage': stage,
            'next_stage': next_stage,
            'reward': stage.get('reward', {}),
        }

    @classmethod
    def claim_reward(cls, player, dungeon_id):
        definition = cls.get_definition(dungeon_id)
        if not definition:
            return False, '副本不存在', None

        if player.current_location != definition.get('entry_location'):
            location_data = DataService.get_location(definition.get('entry_location'))
            location_name = location_data.get('name', definition.get('entry_location')) if location_data else definition.get('entry_location')
            return False, f'请先返回{location_name}领取奖励', None

        state = cls.get_state(player, dungeon_id)
        if not state.get('completed'):
            return False, '请先完成副本', None
        if state.get('reward_claimed'):
            return False, '通关奖励已领取', None

        reward = definition.get('reward', {})
        cls._grant_reward(player, reward)

        state['reward_claimed'] = True
        cls.save_state(player, dungeon_id, state)
        player.current_location = definition.get('return_location', player.current_location)
        return_location = definition.get('return_location')
        return_location_data = DataService.get_location(return_location) if return_location else None
        return True, '通关奖励领取成功', {
            'dungeon': definition,
            'story_outro': definition.get('story_outro', []),
            'reward': reward,
            'return_location': definition.get('return_location'),
            'return_location_name': return_location_data.get('name') if return_location_data else return_location,
            'reward_items': reward.get('items', []),
        }

    @classmethod
    def record_monster_defeat(cls, player, monster):
        definitions = cls.get_definitions()
        if not definitions:
            return None

        data = player.activity_data
        root = data.get(cls.STATE_KEY, {})
        if not isinstance(root, dict):
            return None

        for dungeon_id, definition in definitions.items():
            state = root.get(dungeon_id)
            if not state or not state.get('accepted') or state.get('reward_claimed'):
                continue

            stage = cls.get_current_stage(definition, state)
            if not stage:
                continue

            if monster.monster_id in state.get('defeated_monsters', []):
                return None

            target_monsters = stage.get('target_monsters', [])
            monster_data = DataService.get_monster(monster.monster_id) or {}
            should_despawn = cls._should_despawn_copy_monster(monster_data)

            if monster.monster_id not in target_monsters:
                if should_despawn:
                    cls.mark_monster_defeated(player, dungeon_id, monster.monster_id)
                continue

            required_count = stage.get('required_count', 1)
            progress = min(required_count, state.get('progress', 0) + 1)
            state['progress'] = progress
            if should_despawn:
                defeated = state.get('defeated_monsters', [])
                if monster.monster_id not in defeated:
                    defeated.append(monster.monster_id)
                state['defeated_monsters'] = defeated
            progress_label = stage.get('progress_label') or f"任务[{definition.get('name', dungeon_id)}]-【{stage.get('name', stage.get('id', '阶段'))}】"
            if progress >= required_count:
                state['ready_to_complete'] = True
                note = f"{progress_label}({progress}/{required_count})-达成目标"
            else:
                note = f"{progress_label}({progress}/{required_count})"
            cls.save_state(player, dungeon_id, state)
            return note

        return None
