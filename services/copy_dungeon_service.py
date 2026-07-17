from services import db
from services.data_service import DataService


class CopyDungeonService:
    STATE_KEY = 'copy_dungeons'
    # 入口NPC → 离开时返回的世界位置（例如黄巾起义不同国家入口对应不同出口）
    _ENTRY_RETURN_MAP = {
        'npc_beiping_east_左慈副本': 'beiping_east.箭楼',
        'npc_jianing_center_左慈副本': 'jianing_center.广场',
        'npc_wujun_center_左慈副本': 'wujun_center.广场',
    }

    # 城市→国家 映射（用于过滤本国副本入口）
    _CITY_TO_COUNTRY = {
        'beiping': '魏', 'jinyang': '魏', 'xuchang': '魏',
        'jianing': '蜀', 'yong_an': '蜀', 'chengdu': '蜀', 'jiangling': '蜀',
        'wujun': '吴', 'jianye': '吴', 'chaisang': '吴',
        'luoyang': '魏',  # 洛阳为中立城,下方特殊处理让三国都可见
    }
    _NEUTRAL_CITIES = {'luoyang'}  # 中立城市: 三国通用副本入口

    @classmethod
    def get_country_dungeon_entries(cls, player):
        """返回玩家本国的副本入口列表 [(dungeon_id, dungeon_name, entry_scene_id, scene_name), ...]"""
        country = getattr(player, 'country', None) or '魏'
        entries = []
        for did, dv in cls.get_definitions().items():
            eid = dv.get('entry_npc_id', '')
            if not eid:
                continue
            scene_id = cls._find_npc_scene(eid)
            if not scene_id:
                continue
            # 提取场景所在城市的 stem（如 yong_an_center.广场 → yong_an_center）
            stem = scene_id.rsplit('.', 1)[0] if '.' in scene_id else scene_id
            # 匹配城市→国家（支持 yong_an 等含下划线的城市名）
            matched_country = None
            is_neutral = False
            for city_key, city_country in cls._CITY_TO_COUNTRY.items():
                if stem.startswith(city_key):
                    matched_country = city_country
                    break
            for nc in cls._NEUTRAL_CITIES:
                if stem.startswith(nc):
                    is_neutral = True
                    break
            if matched_country == country or is_neutral:
                scene_name = scene_id.rsplit('.', 1)[-1] if '.' in scene_id else scene_id
                entries.append((did, dv.get('name', did), scene_id, scene_name))
        return entries

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
        in_dungeon = cls._is_in_dungeon(player, dungeon_id)

        # entry_npc outside dungeon: show "can enter" marker with cost info
        if monster_data.get('copy_role') == 'entry_npc' and not in_dungeon:
            daily = cls._get_daily_state(player)
            free = not daily.get('free_used', True)
            dg_level = cls._dungeon_level(definition)
            if free:
                label = '可进入副本(今日免费)'
            elif dg_level >= 40:
                label = '可进入副本(需2神游果)'
            else:
                label = '可进入副本'
            return {'icon': 'gt.gif', 'label': label}

        # entry_npc inside dungeon: treat as quest_giver
        if monster_data.get('copy_role') == 'entry_npc' and in_dungeon:
            pass  # fall through to quest_giver logic below

        # quest_giver: 仅当该 NPC 是当前阶段的任务授予者才显示标记
        # （未配置 quest_giver_npc_id 的阶段不亮任何标记，避免误亮——需在数据中补全配置）
        stage = cls.get_current_stage(definition, state)
        if stage and stage.get('quest_giver_npc_id'):
            if npc_id != stage.get('quest_giver_npc_id'):
                return None
        else:
            # 当前阶段未配置任务授予者 NPC：副本内 quest_giver/entry_npc 一律不亮
            if monster_data.get('copy_role') in ('quest_giver', 'entry_npc'):
                return None

        if state.get('accepted') and state.get('ready_to_complete'):
            return {'icon': 'wh.gif', 'label': '可交任务'}

        if state.get('accepted'):
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
        steps = definition.get('steps') or definition.get('stages', [])
        index = min(state.get('stage_index', 0), max(0, len(steps) - 1))
        return steps[index] if steps else None

    @classmethod
    def get_current_stage_quest(cls, player):
        """玩家位于副本地图内时，把当前副本阶段包装成类主线任务的 dict，
        供『可接任务』列表与任务详情页展示，并支持传送/快速前往目的地。
        玩家不在副本地图内或无副本定义时返回 None。"""
        loc = DataService.get_location(player.current_location)
        if not loc or not loc.get('is_copy_map'):
            return None
        dungeon_id = loc.get('copy_dungeon_id')
        definition = cls.get_definition(dungeon_id) if dungeon_id else None
        if not definition:
            return None
        state = cls.get_state(player, dungeon_id)
        stage_index = int(state.get('stage_index', 0))
        return cls._stage_quest_dict(definition, dungeon_id, stage_index, state, player)

    @classmethod
    def _is_in_dungeon(cls, player, dungeon_id):
        """Check if player is currently inside the dungeon's map area."""
        definition = cls.get_definition(dungeon_id)
        if not definition:
            return False
        current_loc = player.current_location
        if not current_loc:
            return False
        entry_location = definition.get('entry_location', '')
        if not entry_location:
            return False
        area_key = entry_location.split('.')[0] if '.' in entry_location else entry_location
        return current_loc.startswith(area_key + '.')

    @classmethod
    def build_npc_context(cls, player, npc_id):
        dungeon_id = cls.get_dungeon_id_by_npc(npc_id)
        definition = cls.get_definition(dungeon_id) if dungeon_id else None
        if not definition:
            return None

        monster_data = DataService.get_monster(npc_id) or {}
        in_dungeon = cls._is_in_dungeon(player, dungeon_id)

        # entry_npc outside dungeon: always show "enter dungeon" page, reset state
        if monster_data.get('copy_role') == 'entry_npc' and not in_dungeon:
            cls.clear_state(player, dungeon_id)
            state = cls.get_state(player, dungeon_id)
            entry_item_id = definition.get('entry_item_id')
            entry_item = DataService.get_item(entry_item_id) if entry_item_id else None
            return {
                'dungeon_id': dungeon_id,
                'dungeon': definition,
                'state': state,
                'stage': None,
                'next_stage': None,
                'npc_id': npc_id,
                'entry_location': definition.get('entry_location'),
                'quest_giver_location': definition.get('entry_location'),
                'return_location': definition.get('return_location'),
                'entry_item_id': entry_item_id,
                'entry_item_name': entry_item.get('name', entry_item_id) if entry_item else entry_item_id,
                'entry_item_count': definition.get('entry_item_count', 1),
                'current_location': player.current_location,
                'current_scene_name': '',
                'is_current_quest_giver': False,
            }

        state = cls.get_state(player, dungeon_id)
        # 新模型下副本阶段不再使用 completed/reward_claimed 标志位（完成即清 state 或推进 stage_index），
        # 此处仅读取当前阶段，不清理，以免误清 active_quests 中仍在途的任务记录。

        stage = cls.get_current_stage(definition, state)
        next_stage = None
        steps = definition.get('steps') or definition.get('stages', [])
        if stage and state.get('stage_index', 0) + 1 < len(steps):
            next_stage = steps[state.get('stage_index', 0) + 1]

        # Check if this NPC is the current stage's quest giver
        is_current_quest_giver = True
        if stage and stage.get('quest_giver_npc_id'):
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
            'in_dungeon': in_dungeon,
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
    def _save_entry_npc(cls, player, dungeon_id, current_location):
        """在进入副本前记录玩家是从哪个入口NPC进入的，用于退出时回到正确位置。"""
        loc_data = DataService.get_location(current_location)
        if not loc_data:
            return
        for npc_id in loc_data.get('npcs', []):
            if cls.get_dungeon_id_by_npc(npc_id) == dungeon_id:
                state = cls.get_state(player, dungeon_id)
                state['_entry_npc'] = npc_id
                cls.save_state(player, dungeon_id, state)
                return

    @classmethod
    def _resolve_return_location(cls, player, dungeon_id):
        """根据玩家进入时使用的入口NPC，解析正确的返回位置。
        优先级：_ENTRY_RETURN_MAP > 入口NPC所在场景 > definition.return_location"""
        state = cls.get_state(player, dungeon_id)
        entry_npc = state.get('_entry_npc', '')
        # 1) 显式映射（如左慈副本三国不同入口）
        if entry_npc and entry_npc in cls._ENTRY_RETURN_MAP:
            return cls._ENTRY_RETURN_MAP[entry_npc]
        # 2) 反查入口NPC所在的世界场景（任意副本通用）
        if entry_npc:
            scene_id = cls._find_npc_scene(entry_npc)
            if scene_id:
                return scene_id
        # 3) 兜底：副本定义的 return_location
        definition = cls.get_definition(dungeon_id)
        return definition.get('return_location') if definition else None

    @classmethod
    def _find_npc_scene(cls, npc_id):
        """扫描所有非副本场景，找出放置了该 NPC 的场景 id。"""
        locations = DataService.get_locations()
        for loc_id, loc in locations.items():
            if loc.get('is_copy_map'):
                continue
            npcs = loc.get('npcs', []) or []
            if npc_id in npcs:
                return loc_id
        return None

    @classmethod
    def _get_daily_state(cls, player):
        """获取本日副本进入记录（每日首次免费，之后需消耗神游果）。
        仅在首次初始化或跨天时写入数据库。"""
        from datetime import date
        data = player.activity_data
        if not isinstance(data, dict):
            data = {}
        daily = data.get('copy_dungeon_daily', {})
        today = date.today().isoformat()
        changed = False
        if not isinstance(daily, dict):
            daily = {'date': today, 'free_used': False}
            changed = True
        elif daily.get('date') != today:
            daily = {'date': today, 'free_used': False}
            changed = True
        if changed:
            data['copy_dungeon_daily'] = daily
            player.activity_data = data
            db.session.commit()
        return daily

    @classmethod
    def _use_daily_free(cls, player):
        """消耗本日免费次数。"""
        daily = cls._get_daily_state(player)
        daily['free_used'] = True
        data = player.activity_data
        if not isinstance(data, dict):
            data = {}
        data['copy_dungeon_daily'] = daily
        player.activity_data = data
        db.session.commit()

    @classmethod
    def _dungeon_level(cls, definition):
        """从副本名称中解析等级，如 '火烧博望(16级副本)' -> 16。"""
        import re
        m = re.search(r'\((\d+)级', definition.get('name', ''))
        return int(m.group(1)) if m else 0

    # ===== 阶段任务 id 编码（每个阶段=独立任务，可进 active_quests）=====
    # id 形如 copy_<dungeon_id>_<stage_index>，前缀 copy_ 让 quest_detail 走副本分支

    @classmethod
    def stage_quest_id(cls, dungeon_id, stage_index):
        return f'copy_{dungeon_id}_{stage_index}'

    @classmethod
    def parse_stage_quest_id(cls, quest_id):
        """解析 copy_<dungeon_id>_<stage_index>，返回 (dungeon_id, stage_index) 或 None。"""
        if not quest_id or not quest_id.startswith('copy_'):
            return None
        body = quest_id[len('copy_'):]
        # dungeon_id 自身可能含下划线，末段为 stage_index
        if '_' not in body:
            return None
        dungeon_id, _, idx_str = body.rpartition('_')
        if not idx_str.isdigit():
            return None
        return dungeon_id, int(idx_str)

    @classmethod
    def _stage_quest_dict(cls, definition, dungeon_id, stage_index, state, player=None):
        """把指定阶段包装成类主线任务的 dict（供任务列表/详情/传送）。"""
        steps = definition.get('steps') or definition.get('stages', [])
        if stage_index < 0 or stage_index >= len(steps):
            return None
        stage = steps[stage_index]
        accepted = bool(state.get('accepted')) and int(state.get('stage_index', 0)) == stage_index
        ready = bool(state.get('ready_to_complete')) and accepted

        giver_loc = stage.get('quest_giver_location') or definition.get('entry_location')
        giver_loc_data = DataService.get_location(giver_loc) if giver_loc else None
        giver_loc_name = giver_loc_data.get('name', giver_loc) if giver_loc_data else (giver_loc or '')
        target_loc = stage.get('scene_id') or ''

        npc_name = ''
        npc_id = stage.get('quest_giver_npc_id')
        if npc_id:
            nd = DataService.get_monster(npc_id)
            if nd:
                npc_name = nd.get('name', '')

        reward = stage.get('reward') or {}
        required_count = stage.get('required_count', 0) or 0
        return {
            'id': cls.stage_quest_id(dungeon_id, stage_index),
            'name': f"副·{stage.get('name', definition.get('name', dungeon_id))}",
            'level_required': cls._dungeon_level(definition),
            'npc_name': npc_name or definition.get('name', ''),
            'npc_id': npc_id or '',
            'npc_location': giver_loc or '',
            'npc_location_name': giver_loc_name,
            'target_location': target_loc,
            'description': stage.get('objective', ''),
            'progress': state.get('progress', 0) if accepted else 0,
            'target': required_count,
            'is_ready': ready,
            'rewards': reward,
            'is_copy_quest': True,
            'dungeon_id': dungeon_id,
            'stage_index': stage_index,
            'accepted': accepted,
            'required_items': stage.get('required_items', {}) or {},
            'story': stage.get('story', ''),
            'complete_story': stage.get('complete_story', ''),
        }

    @classmethod
    def get_stage_quest(cls, player, quest_id):
        """根据阶段任务 id 构造 quest dict（供任务详情页/列表统一渲染）。"""
        parsed = cls.parse_stage_quest_id(quest_id)
        if not parsed:
            return None
        dungeon_id, stage_index = parsed
        definition = cls.get_definition(dungeon_id)
        if not definition:
            return None
        state = cls.get_state(player, dungeon_id)
        return cls._stage_quest_dict(definition, dungeon_id, stage_index, state, player)

    @classmethod
    def enter_dungeon(cls, player, dungeon_id):
        definition = cls.get_definition(dungeon_id)
        if not definition:
            return False, '副本不存在'

        entry_location = definition.get('entry_location')
        locations = DataService.get_locations()
        if entry_location not in locations:
            return False, '副本入口未配置'

        # 每日免费 + 神游果消耗系统
        entry_item_id = definition.get('entry_item_id', 'shenyou_guo')
        daily = cls._get_daily_state(player)
        free = not daily.get('free_used', True)

        if free:
            # 本日首次副本：免费
            cls._use_daily_free(player)
        else:
            # 非首次：需消耗神游果（40级+副本消耗2个）
            dg_level = cls._dungeon_level(definition)
            required = 2 if dg_level >= 40 else 1
            if entry_item_id:
                entry_item = DataService.get_item(entry_item_id)
                entry_item_name = entry_item.get('name', entry_item_id) if entry_item else entry_item_id
                inv = DataService.get_inventory_item(player.id, entry_item_id)
                if not inv or inv.quantity < required:
                    free_hint = '（每日首次副本免费，今日已用）'
                    return False, f'进入副本需要消耗{required}个{entry_item_name}{free_hint}'
                DataService.remove_item_from_inventory(player.id, entry_item_id, required)

        state = cls.get_state(player, dungeon_id)
        if state.get('completed') or state.get('reward_claimed'):
            cls.clear_state(player, dungeon_id)
            state = cls.get_state(player, dungeon_id)

        # 进入副本时校准阶段：若有在途副本阶段任务(active_quests)，恢复到该阶段；
        # 否则从第一个阶段开始（副本支持重复刷：清掉该副本旧的阶段 completed 记录）
        resumed = cls._resume_stage_from_active(player, dungeon_id, state)
        if not resumed:
            # 无在途任务 → 从头开始；若该副本阶段已全部 completed(上次通关未清的残留)也重置
            state['stage_index'] = 0
            state['accepted'] = False
            state['progress'] = 0
            state['ready_to_complete'] = False
            state['defeated_monsters'] = []
            cls._clear_dungeon_completed(player, dungeon_id)
            cls.save_state(player, dungeon_id, state)

        # 记录入口NPC，用于退出时返回正确城市（三国不同起始城）
        cls._save_entry_npc(player, dungeon_id, player.current_location)

        player.current_location = entry_location
        db.session.commit()
        return True, f"已进入【{definition.get('name', dungeon_id)}】"

    @classmethod
    def _resume_stage_from_active(cls, player, dungeon_id, state):
        """若 active_quests 中有该副本的在途阶段任务，把副本 state 校准到该阶段。返回是否恢复。"""
        from services.quest_service import QuestService
        active = QuestService.get_active_quests(player)
        parsed = None
        for qid in active:
            p = cls.parse_stage_quest_id(qid)
            if p and p[0] == dungeon_id:
                parsed = p
                qprogress = active[qid]
                break
        if not parsed:
            return False
        _, stage_index = parsed
        state['stage_index'] = stage_index
        state['accepted'] = True
        state['progress'] = qprogress.get('progress', 0)
        state['ready_to_complete'] = state['progress'] >= qprogress.get('target', state.get('progress', 0) + 1) and qprogress.get('target', 0) > 0
        cls.save_state(player, dungeon_id, state)
        return True

    @classmethod
    def leave_dungeon(cls, player, dungeon_id):
        definition = cls.get_definition(dungeon_id)
        if not definition:
            return False, '副本不存在'

        # 先解析返回位置（此时 state 还在，_entry_npc 可读）
        return_location = cls._resolve_return_location(player, dungeon_id)

        # 再清空 state（副本进度，但消耗的神游果/免费次数不返还）
        data, root = cls._ensure_state_root(player)
        if dungeon_id in root:
            root.pop(dungeon_id, None)
            data[cls.STATE_KEY] = root
            player.activity_data = data

        # 同步清除该副本在 active_quests / completed_quests 中的阶段任务，
        # 让玩家下次进入从第一个阶段重新接取（副本可重复刷）
        cls._clear_dungeon_active(player, dungeon_id)
        cls._clear_dungeon_completed(player, dungeon_id)

        if return_location:
            player.current_location = return_location

        db.session.commit()
        return True, f"已离开【{definition.get('name', dungeon_id)}】，副本进度已清空"

    @classmethod
    def accept_task(cls, player, dungeon_id):
        """接受副本当前阶段任务（写作独立任务写入 active_quests，任务列表可见）。
        完成一个阶段后 accepted 复位为 False，下一阶段需玩家再次点『接受任务』，不自动接取。"""
        definition = cls.get_definition(dungeon_id)
        if not definition:
            return False, '副本不存在', None

        state = cls.get_state(player, dungeon_id)
        stage = cls.get_current_stage(definition, state)
        if not stage:
            return False, '副本阶段异常', None

        # 已接受当前阶段且在途 → 不重复接
        if state.get('accepted'):
            return False, '当前阶段任务已接受', None

        quest_giver_location = stage.get('quest_giver_location') or definition.get('entry_location')
        if player.current_location != quest_giver_location:
            location_data = DataService.get_location(quest_giver_location)
            location_name = location_data.get('name', quest_giver_location) if location_data else quest_giver_location
            return False, f'请先前往{location_name}接受任务', None

        stage_index = int(state.get('stage_index', 0))
        state['accepted'] = True
        state['progress'] = 0
        state['ready_to_complete'] = False

        # 交付物型阶段（无 target_monsters 且 required_count==0），接受时若已持有物品则直接可交
        if not stage.get('target_monsters') and stage.get('required_count', 1) == 0:
            required_items = stage.get('required_items', {})
            if required_items:
                has_items, _ = cls._has_required_items(player, required_items)
                if has_items:
                    state['ready_to_complete'] = True

        cls.save_state(player, dungeon_id, state)

        # 写入主线任务体系 active_quests，使任务列表可见
        cls._register_active_stage(player, dungeon_id, stage_index, stage)

        db.session.commit()
        return True, f"已接受【副·{stage.get('name', definition.get('name', dungeon_id))}】", {
            'dungeon': definition,
            'stage': stage,
            'stage_index': stage_index,
        }

    @classmethod
    def _register_active_stage(cls, player, dungeon_id, stage_index, stage):
        """把阶段任务写入 player.active_quests（与主线任务共存）。"""
        from services.quest_service import QuestService
        active = QuestService.get_active_quests(player)
        qid = cls.stage_quest_id(dungeon_id, stage_index)
        active[qid] = {
            'progress': 0,
            'target': stage.get('required_count', 0) or 0,
        }
        QuestService.set_active_quests(player, active)

    @classmethod
    def _unregister_active_stage(cls, player, qid):
        from services.quest_service import QuestService
        active = QuestService.get_active_quests(player)
        if qid in active:
            del active[qid]
            QuestService.set_active_quests(player, active)

    @classmethod
    def abandon_copy_quest(cls, player, quest_id):
        """放弃某阶段副本任务（从 active 移除；副本内进度清零，可再次接取）。"""
        parsed = cls.parse_stage_quest_id(quest_id)
        if not parsed:
            return False, '任务不存在'
        dungeon_id, stage_index = parsed
        definition = cls.get_definition(dungeon_id)
        if not definition:
            return False, '副本不存在'
        cls._unregister_active_stage(player, quest_id)
        state = cls.get_state(player, dungeon_id)
        if int(state.get('stage_index', 0)) == stage_index:
            state['accepted'] = False
            state['progress'] = 0
            state['ready_to_complete'] = False
            cls.save_state(player, dungeon_id, state)
        db.session.commit()
        return True, '已放弃'

    @classmethod
    def complete_stage(cls, player, dungeon_id):
        """完成当前阶段：发奖励、移除 active 任务、记 completed。
        非末阶段：stage_index+=1 且 accepted=False（下一阶段需手动接受，不自动接取）。
        末阶段：发通关奖励、清进度、返回入口、副本通关计数+1。"""
        definition = cls.get_definition(dungeon_id)
        if not definition:
            return False, '副本不存在', False, None

        state = cls.get_state(player, dungeon_id)
        stage = cls.get_current_stage(definition, state)
        if not stage:
            return False, '副本阶段异常', False, None
        if not state.get('accepted'):
            return False, '请先接受副本任务', False, None
        if not state.get('ready_to_complete'):
            return False, '当前阶段目标尚未完成', False, None

        quest_giver_location = stage.get('quest_giver_location') or definition.get('entry_location')
        if player.current_location != quest_giver_location:
            location_data = DataService.get_location(quest_giver_location)
            location_name = location_data.get('name', quest_giver_location) if location_data else quest_giver_location
            return False, f'请先返回{location_name}完成任务', False, None

        required_items = stage.get('required_items', {})
        has_required_items, missing_message = cls._has_required_items(player, required_items)
        if not has_required_items:
            return False, missing_message, False, None

        # Consume required items
        for item_id, count in required_items.items():
            DataService.remove_item_from_inventory(player.id, item_id, count)

        cls._grant_reward(player, stage.get('reward', {}))

        stage_index = int(state.get('stage_index', 0))
        qid = cls.stage_quest_id(dungeon_id, stage_index)
        # 从 active 移除、记 completed（仅用于阶段顺序，进入副本时会按需清除以支持重刷）
        cls._unregister_active_stage(player, qid)
        from services.quest_service import QuestService
        completed = QuestService.get_completed_quests(player)
        if qid not in completed:
            completed.append(qid)
            QuestService.set_completed_quests(player, completed)

        steps = definition.get('steps') or definition.get('stages', [])
        is_last = stage_index >= len(steps) - 1
        if is_last:
            final_reward = definition.get('reward', {})
            cls._grant_reward(player, final_reward)
            return_location = cls._resolve_return_location(player, dungeon_id) or definition.get('return_location', player.current_location)
            return_location_data = DataService.get_location(return_location) if return_location else None
            player.current_location = return_location
            cls.clear_state(player, dungeon_id)
            # 副本可重刷： cleared 该副本各阶段 completed 记录，玩家下次可从首阶段重新接取
            cls._clear_dungeon_completed(player, dungeon_id)
            # Track dungeon clear count
            clears = player.dungeon_clears
            clears[dungeon_id] = clears.get(dungeon_id, 0) + 1
            player.dungeon_clears = clears
            # Track tower floor progress
            if dungeon_id == 'ice_tower':
                player.tower_max_floor = max(player.tower_max_floor or 0, definition.get('max_floor', 0))
            from services.achievement_service import AchievementService
            AchievementService.check(player, 'dungeon_clear')
            AchievementService.check(player, 'dungeon_tower')
            db.session.commit()
            return True, '副本已通关', True, {
                'dungeon': definition,
                'story_outro': definition.get('story_outro', []),
                'reward': final_reward,
                'return_location': return_location,
                'return_location_name': return_location_data.get('name') if return_location_data else return_location,
                'reward_items': final_reward.get('items', []),
            }

        # 非末阶段：推进到下一阶段但不自动接受（accepted=False，下一阶段进入『可接任务』）
        state['stage_index'] = stage_index + 1
        state['accepted'] = False
        state['progress'] = 0
        state['ready_to_complete'] = False
        state['defeated_monsters'] = []
        cls.save_state(player, dungeon_id, state)
        db.session.commit()
        next_stage = cls.get_current_stage(definition, state)
        next_name = next_stage.get('name', '下一阶段') if next_stage else '下一阶段'
        next_qid = cls.stage_quest_id(dungeon_id, state['stage_index']) if next_stage else None
        return True, f"阶段已完成，已开启【{next_name}】", False, {
            'dungeon': definition,
            'completed_stage': stage,
            'next_stage': next_stage,
            'stage': stage,
            'reward': stage.get('reward', {}),
            'next_quest_id': next_qid,
        }

    @classmethod
    def _clear_dungeon_completed(cls, player, dungeon_id):
        """从 completed_quests 中清除某副本的全部阶段记录，支持副本重复刷。"""
        from services.quest_service import QuestService
        completed = QuestService.get_completed_quests(player)
        prefix = f'copy_{dungeon_id}_'
        completed = [qid for qid in completed if not qid.startswith(prefix)]
        QuestService.set_completed_quests(player, completed)

    @classmethod
    def _clear_dungeon_active(cls, player, dungeon_id):
        """从 active_quests 中清除某副本的全部在途阶段任务。"""
        from services.quest_service import QuestService
        active = QuestService.get_active_quests(player)
        prefix = f'copy_{dungeon_id}_'
        active = {qid: v for qid, v in active.items() if not qid.startswith(prefix)}
        QuestService.set_active_quests(player, active)

    @classmethod
    def clear_all_dungeon_quests(cls, player):
        """玩家离开副本场景（进入非副本场景）时调用：清除全部副本阶段任务
        （active + completed + copy state），下次进入任意副本均从首阶段开始。"""
        from services.quest_service import QuestService
        active = QuestService.get_active_quests(player)
        active = {qid: v for qid, v in active.items() if not qid.startswith('copy_')}
        QuestService.set_active_quests(player, active)
        completed = QuestService.get_completed_quests(player)
        completed = [qid for qid in completed if not qid.startswith('copy_')]
        QuestService.set_completed_quests(player, completed)

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
        return_location = cls._resolve_return_location(player, dungeon_id)
        player.current_location = return_location or player.current_location
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
            # 同步主线任务体系 active_quests 进度，使任务列表进度实时可见
            cls._sync_active_progress(player, dungeon_id, int(state.get('stage_index', 0)), progress, required_count)
            return note

        return None

    @classmethod
    def _sync_active_progress(cls, player, dungeon_id, stage_index, progress, target):
        """把副本阶段击杀进度同步到 active_quests 中对应阶段任务。"""
        from services.quest_service import QuestService
        active = QuestService.get_active_quests(player)
        qid = cls.stage_quest_id(dungeon_id, stage_index)
        if qid in active:
            active[qid]['progress'] = progress
            active[qid]['target'] = target
            QuestService.set_active_quests(player, active)
