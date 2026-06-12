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
            inv = DataService.get_inventory_item(player.id, 'kongming_light')
            if not inv or inv.quantity < 1:
                return {'success': False, 'msg': '非VIP传送需要消耗1个孔明灯，您没有孔明灯'}
            DataService.remove_item_from_inventory(player.id, 'kongming_light', 1)

        # 执行传送
        player.current_location = target_location
        db.session.commit()
        return {'success': True, 'msg': f'已传送至【{target}】广场'}

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
        inv = DataService.get_inventory_item(player.id, 'town_scroll')
        if not inv or inv.quantity < 1:
            return {'success': False, 'msg': '回城需要消耗1个回城符，您没有回城符'}

        # 消耗回城符
        DataService.remove_item_from_inventory(player.id, 'town_scroll', 1)

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
        inv = DataService.get_inventory_item(player.id, 'shenxing_scroll')
        if not inv or inv.quantity < 1:
            return {'success': False, 'msg': '神行需要消耗1个神行符，您没有神行符'}

        # 消耗神行符
        DataService.remove_item_from_inventory(player.id, 'shenxing_scroll', 1)

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