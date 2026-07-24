from collections import deque, OrderedDict
from services.data_service import DataService
from services import db


class MapService:

    # 各城市广场对应的location_id
    CITY_SQUARES = {
        '北平': 'beiping_center.广场',
        '晋阳': 'jinyang_center.广场',
        '许昌': 'xuchang_center.广场',
        '下邳': 'xiapi_center.广场',
        '汉中': 'hanzhong_center.广场',
        '江陵': 'jiangling_center.广场',
        '洛阳': 'luoyang_center.广场',
        '建邺': 'jianye_center.广场',
        '柴桑': 'chaisang_center.广场',
        '吴郡': 'wujun_center.广场',
        '成都': 'chengdu_center.广场',
        '建宁': 'jianing_center.广场',
        '永安': 'yong_an_center.广场',
        '昆仑': 'kunlun.镇中街',
        '神农架': 'shennong.碎石广场',
        '倭寇岛': 'wokou.倭岛码头',
    }

    # 城市前缀 → 国家（与 copy_dungeon_service 对齐）；未列入的为中立/开放
    CITY_TO_COUNTRY = {
        'beiping': '魏', 'jinyang': '魏', 'xuchang': '魏',
        'jianing': '蜀', 'yong_an': '蜀', 'chengdu': '蜀', 'jiangling': '蜀',
        'wujun': '吴', 'jianye': '吴', 'chaisang': '吴',
    }
    # 中立/开放区域（三国皆可传送）
    NEUTRAL_REGIONS = {
        'luoyang', 'xiapi', 'hanzhong',
        'kunlun', 'shennong', 'wokou',
        'ice_tower',
    }
    REGION_NAMES = {
        'beiping': '北平', 'jinyang': '晋阳', 'xuchang': '许昌',
        'jianing': '建宁', 'yong_an': '永安', 'chengdu': '成都', 'jiangling': '江陵',
        'wujun': '吴郡', 'jianye': '建邺', 'chaisang': '柴桑',
        'luoyang': '洛阳', 'xiapi': '下邳', 'hanzhong': '汉中',
        'kunlun': '昆仑山脉', 'shennong': '神农架', 'wokou': '倭寇岛',
        'ice_tower': '寒冰塔',
    }
    ZONE_ORDER = ('center', 'east', 'west', 'south', 'north')
    ZONE_LABELS = {
        'center': '中区', 'east': '东区', 'west': '西区',
        'south': '南区', 'north': '北区',
    }

    # 各区域驿站
    AREA_STATIONS = {
        'beiping_center': 'beiping_center.驿站',
        'jinyang_center': 'jinyang_center.驿站',
        'xuchang_center': 'xuchang_center.驿站',
        'xiapi_center': 'xiapi_center.驿站',
        'hanzhong_center': 'hanzhong_center.驿站',
        'jiangling_center': 'jiangling_center.驿站',
        'luoyang_center': 'luoyang_center.驿站',
        'jianye_center': 'jianye_center.驿站',
        'chaisang_center': 'chaisang_center.驿站',
        'wujun_center': 'wujun_center.驿站',
        'jianing_center': 'jianing_center.驿站',
        'yong_an_center': 'yong_an_center.驿站',
        'chengdu_center': 'chengdu_center.驿站',
        'kunlun': 'kunlun.太平村',
    }

    @classmethod
    def teleport(cls, player, target):
        """
        传送至目标城市广场
        VIP免费，非VIP消耗孔明灯1个
        """
        target_location = cls.CITY_SQUARES.get(target)
        if not target_location:
            return {'success': False, 'msg': '目标城市不存在'}

        locations = DataService.get_locations()
        if target_location not in locations:
            return {'success': False, 'msg': '目标城市暂未开放'}

        # 检查VIP
        if not player.is_vip:
            # 非VIP消耗孔明灯
            inv = DataService.get_inventory_item(player.id, 'kongming_lantern')
            if not inv or inv.quantity < 1:
                return {'success': False, 'msg': '非VIP传送需要消耗1个孔明灯，您没有孔明灯'}
            DataService.remove_item_from_inventory(player.id, 'kongming_lantern', 1)

        # 执行传送
        player.current_location = target_location
        db.session.commit()
        return {'success': True, 'msg': f'已传送至【{target}】广场'}

    @classmethod
    def teleport_to_scene(cls, player, scene_id, scene_name=''):
        """传送至指定场景ID（用于副本入口等）。VIP免费，非VIP消耗孔明灯。"""
        locations = DataService.get_locations()
        if scene_id not in locations:
            return {'success': False, 'msg': '目标场景不存在'}

        if not player.is_vip:
            inv = DataService.get_inventory_item(player.id, 'kongming_lantern')
            if not inv or inv.quantity < 1:
                return {'success': False, 'msg': '非VIP传送需要消耗1个孔明灯'}
            DataService.remove_item_from_inventory(player.id, 'kongming_lantern', 1)

        player.current_location = scene_id
        db.session.commit()
        return {'success': True, 'msg': f'已传送至【{scene_name or scene_id}】'}

    @classmethod
    def town(cls, player):
        """
        回城 - 快速前往所在区域驿站，消耗回城符1个
        """
        location_id = player.current_location
        location = DataService.get_location(location_id)
        if not location:
            return {'success': False, 'msg': '当前位置异常'}

        area_id = location.get('area_id', '')
        station_id = cls.AREA_STATIONS.get(area_id)

        if not station_id:
            return {'success': False, 'msg': '当前区域没有驿站'}

        # 检查回城符
        inv = DataService.get_inventory_item(player.id, 'return_scroll')
        if not inv or inv.quantity < 1:
            return {'success': False, 'msg': '回城需要消耗1个回城符，您没有回城符'}

        # 消耗回城符
        DataService.remove_item_from_inventory(player.id, 'return_scroll', 1)

        # 执行回城
        player.current_location = station_id
        db.session.commit()
        return {'success': True, 'msg': '已回城至驿站'}

    @classmethod
    def shenxing(cls, player, scene_id):
        """
        神行 - 快速传送到区域功能/怪物传送点，消耗神行符1个
        """
        locations = DataService.get_locations()
        if scene_id not in locations:
            return {'success': False, 'msg': '目标场景不存在'}

        # 检查神行符
        inv = DataService.get_inventory_item(player.id, 'speed_scroll')
        if not inv or inv.quantity < 1:
            return {'success': False, 'msg': '神行需要消耗1个神行符，您没有神行符'}

        # 消耗神行符
        DataService.remove_item_from_inventory(player.id, 'speed_scroll', 1)

        # 执行传送
        player.current_location = scene_id
        db.session.commit()
        return {'success': True, 'msg': '神行成功'}

    @classmethod
    def get_area_teleport_points(cls, area_id):
        """获取区域内的传送点（有怪物或NPC的场景）"""
        if not area_id:
            return []

        locations = DataService.get_locations()
        points = []
        for loc_id, loc_data in locations.items():
            if loc_data.get('area_id') == area_id:
                monsters = loc_data.get('monsters', [])
                npcs = loc_data.get('npcs', [])
                if monsters or npcs:
                    name = loc_data.get('name', '')
                    points.append({
                        'id': loc_id,
                        'name': name,
                        'monsters': monsters,
                        'npcs': npcs
                    })
        return points

    @classmethod
    def get_area_teleport_points_by_area(cls, player):
        """获取玩家当前区域的传送点列表"""
        location_id = player.current_location
        loc = DataService.get_location(location_id)
        if not loc:
            return []

        area_id = loc.get('area_id', '')
        all_locs = DataService.get_locations()

        # 按场景名称分组（同区域其他场景）
        scenes = []
        for lid, ldata in all_locs.items():
            if ldata.get('area_id') == area_id:
                scenes.append({
                    'id': lid,
                    'name': ldata.get('name', ''),
                    'monsters': ldata.get('monsters', []),
                    'npcs': ldata.get('npcs', []),
                })
        return scenes

    @classmethod
    def get_area_scenes(cls, area_id):
        """获取区域内的所有场景"""
        if not area_id:
            return []

        locations = DataService.get_locations()
        scenes = []
        for loc_id, loc_data in locations.items():
            if loc_data.get('area_id') == area_id:
                scenes.append({
                    'id': loc_id,
                    'name': loc_data.get('name', ''),
                    'monsters': loc_data.get('monsters', []),
                    'npcs': loc_data.get('npcs', []),
                    'north_exit': loc_data.get('north_exit', ''),
                    'south_exit': loc_data.get('south_exit', ''),
                    'east_exit': loc_data.get('east_exit', ''),
                    'west_exit': loc_data.get('west_exit', ''),
                })
        return scenes

    # ---------- 传送导航（区域/分区/场景 + 出口拓扑） ----------
    @classmethod
    def _known_region_prefixes(cls):
        """可作为 *_center/*_east 前缀的区域名集合。"""
        return set(cls.CITY_TO_COUNTRY) | set(cls.NEUTRAL_REGIONS) | set(cls.REGION_NAMES)

    @classmethod
    def region_key_of(cls, area_id):
        """area_id（beiping_east / kunlun）→ 区域前缀 beiping / kunlun。

        仅当去掉 _center/_east 等后缀后仍是已知区域前缀时才拆分，
        避免把 ice_tower 误拆成 ice + tower。
        """
        if not area_id:
            return ''
        known = cls._known_region_prefixes()
        for zone in cls.ZONE_ORDER:
            suffix = '_' + zone
            if area_id.endswith(suffix):
                prefix = area_id[: -len(suffix)]
                if prefix in known:
                    return prefix
        return area_id

    @classmethod
    def zone_key_of(cls, area_id):
        """area_id → center/east/...；无分区时返回 ''。"""
        if not area_id:
            return ''
        known = cls._known_region_prefixes()
        for zone in cls.ZONE_ORDER:
            suffix = '_' + zone
            if area_id.endswith(suffix):
                prefix = area_id[: -len(suffix)]
                if prefix in known:
                    return zone
        return ''

    @classmethod
    def region_name(cls, region_key):
        return cls.REGION_NAMES.get(region_key, region_key)

    @classmethod
    def player_can_access_region(cls, player, region_key):
        """本国城市 / 中立开放区域 可访问。"""
        if not region_key:
            return False
        if region_key in cls.NEUTRAL_REGIONS:
            return True
        country = getattr(player, 'country', None) or '魏'
        owner = cls.CITY_TO_COUNTRY.get(region_key)
        if owner is None:
            # 未登记国家归属的野外图默认开放
            return True
        return owner == country

    @classmethod
    def list_accessible_regions(cls, player):
        """本国 + 中立区域列表（按国家/中立分组排序）。"""
        locations = DataService.get_locations()
        region_areas = OrderedDict()
        for lid, loc in locations.items():
            if loc.get('is_copy_map'):
                continue
            area_id = loc.get('area_id') or ''
            if not area_id:
                continue
            rk = cls.region_key_of(area_id)
            if not rk or not cls.player_can_access_region(player, rk):
                continue
            region_areas.setdefault(rk, set()).add(area_id)

        def sort_key(rk):
            owner = cls.CITY_TO_COUNTRY.get(rk)
            country = getattr(player, 'country', None) or '魏'
            # 本国优先，再中立，再其它
            if owner == country:
                group = 0
            elif rk in cls.NEUTRAL_REGIONS or owner is None:
                group = 1
            else:
                group = 2
            return (group, cls.region_name(rk))

        result = []
        for rk in sorted(region_areas.keys(), key=sort_key):
            zones = cls.list_region_zones(rk)
            owner = cls.CITY_TO_COUNTRY.get(rk)
            if rk in cls.NEUTRAL_REGIONS or owner is None:
                tag = '中立'
            else:
                tag = owner
            has_zones = len(zones) > 1 or (len(zones) == 1 and bool(zones[0].get('zone')))
            result.append({
                'key': rk,
                'name': cls.region_name(rk),
                'tag': tag,
                'has_zones': bool(has_zones),
                'zones': zones,
                'default_area_id': zones[0]['area_id'] if zones else '',
            })
        return result

    @classmethod
    def list_region_zones(cls, region_key):
        """返回某区域下的分区列表（中/东/西/南/北），无分区则返回自身。"""
        locations = DataService.get_locations()
        found = {}  # zone_key or '' -> area_id / name
        for lid, loc in locations.items():
            if loc.get('is_copy_map'):
                continue
            area_id = loc.get('area_id') or ''
            if cls.region_key_of(area_id) != region_key:
                continue
            zk = cls.zone_key_of(area_id)
            if area_id not in found.values():
                found[zk or area_id] = {
                    'zone': zk,
                    'area_id': area_id,
                    'name': loc.get('area_name') or (
                        cls.region_name(region_key) + cls.ZONE_LABELS.get(zk, '')
                        if zk else cls.region_name(region_key)
                    ),
                }
        # 去重 by area_id
        by_area = {}
        for item in found.values():
            by_area[item['area_id']] = item
        items = list(by_area.values())
        def zsort(it):
            z = it['zone']
            return (cls.ZONE_ORDER.index(z) if z in cls.ZONE_ORDER else 99, it['name'])
        items.sort(key=zsort)
        return items

    @classmethod
    def get_area_scenes_sorted(cls, area_id, current_location_id=None):
        """分区内场景列表；若给 current，优先把当前场景置顶。"""
        scenes = cls.get_area_scenes(area_id)
        scenes.sort(key=lambda s: (0 if s['id'] == current_location_id else 1, s['name']))
        return scenes

    @classmethod
    def get_region_topology_scenes(cls, region_key, start_location_id=None):
        """模式二：按出口连通关系列出该区域可达场景（BFS 序）。

        只包含 region_key 内的场景；若 start 不在该区域，取该区域中心/首个场景作起点。
        """
        locations = DataService.get_locations()
        region_scene_ids = [
            lid for lid, loc in locations.items()
            if not loc.get('is_copy_map')
            and cls.region_key_of(loc.get('area_id') or '') == region_key
        ]
        if not region_scene_ids:
            return []

        region_set = set(region_scene_ids)
        start = start_location_id if start_location_id in region_set else None
        if not start:
            # 优先中区广场，否则任意
            for lid in region_scene_ids:
                if lid.endswith('.广场') or lid.endswith('.镇中街') or lid.endswith('.倭岛码头'):
                    start = lid
                    break
            if not start:
                start = region_scene_ids[0]

        dirs = (
            ('north_exit', '北'),
            ('south_exit', '南'),
            ('east_exit', '东'),
            ('west_exit', '西'),
        )
        ordered = []
        seen = set()
        q = deque([start])
        while q:
            cur = q.popleft()
            if cur in seen or cur not in region_set:
                continue
            seen.add(cur)
            loc = locations.get(cur) or {}
            exits = []
            for key, label in dirs:
                dest = loc.get(key) or (loc.get('exits') or {}).get(key.replace('_exit', ''))
                if dest and dest in region_set:
                    dloc = locations.get(dest) or {}
                    exits.append({
                        'dir': label,
                        'id': dest,
                        'name': dloc.get('name', dest),
                    })
                    if dest not in seen:
                        q.append(dest)
            ordered.append({
                'id': cur,
                'name': loc.get('name', cur),
                'area_id': loc.get('area_id', ''),
                'area_name': loc.get('area_name', ''),
                'exits': exits,
                'is_start': cur == start,
            })

        # 补上未连通的孤立场景
        for lid in region_scene_ids:
            if lid in seen:
                continue
            loc = locations.get(lid) or {}
            ordered.append({
                'id': lid,
                'name': loc.get('name', lid),
                'area_id': loc.get('area_id', ''),
                'area_name': loc.get('area_name', ''),
                'exits': [],
                'is_start': False,
            })
        return ordered

    @classmethod
    def teleport_to_scene_checked(cls, player, scene_id):
        """传送到场景：校验目标非副本、且属于可访问区域。"""
        locations = DataService.get_locations()
        loc = locations.get(scene_id)
        if not loc:
            return {'success': False, 'msg': '目标场景不存在'}
        if loc.get('is_copy_map'):
            return {'success': False, 'msg': '不能直接传送到副本内'}
        rk = cls.region_key_of(loc.get('area_id') or '')
        if not cls.player_can_access_region(player, rk):
            return {'success': False, 'msg': '该区域不属于本国或中立开放区'}
        return cls.teleport_to_scene(player, scene_id, scene_name=loc.get('name', ''))
