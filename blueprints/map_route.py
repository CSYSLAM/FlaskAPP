from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from collections import OrderedDict
from services import db
from services.data_service import DataService
from services.map_service import MapService
from services.copy_dungeon_service import CopyDungeonService

map_bp = Blueprint('map', __name__, url_prefix='/map')


@map_bp.route("/")
@login_required
def index():
    """地图主页面 - 传送/回城/神行/快捷"""
    player = current_user
    location_id = player.current_location
    location = DataService.get_location(location_id)
    area_id = location.get('area_id', '') if location else ''
    return render_template("map_index.html",
                         player=player,
                         location=location,
                         location_id=location_id,
                         area_id=area_id)


@map_bp.route("/teleport")
@login_required
def teleport():
    """传送 - 两模式：分层选择 / 出口拓扑。

    参数:
      mode=zone|topo  (默认 zone)
      region=beiping  区域前缀
      zone=center     分区（仅 zone 模式）
    """
    player = current_user
    location = DataService.get_location(player.current_location)
    if location and location.get('is_copy_map'):
        flash("副本内无法使用传送，请先离开副本")
        return redirect(url_for('game.scene'))

    mode = request.args.get('mode') or 'zone'
    if mode not in ('zone', 'topo'):
        mode = 'zone'
    region = request.args.get('region') or ''
    zone = request.args.get('zone') or ''

    regions = MapService.list_accessible_regions(player)
    region_keys = {r['key'] for r in regions}
    if region and region not in region_keys:
        flash("无权访问该区域")
        region = ''

    country_entries = CopyDungeonService.get_country_dungeon_entries(player)
    location_id = player.current_location
    cur_area = (location or {}).get('area_id', '')
    cur_region = MapService.region_key_of(cur_area)

    zones = []
    scenes = []
    topo_scenes = []
    selected_region = next((r for r in regions if r['key'] == region), None)
    selected_zone = None
    selected_area_id = ''

    if region and selected_region:
        zones = selected_region.get('zones') or MapService.list_region_zones(region)
        if mode == 'zone':
            # 无分区（如昆仑）直接进场景列表
            if not selected_region.get('has_zones') and zones:
                selected_zone = zones[0]
                selected_area_id = selected_zone['area_id']
                scenes = MapService.get_area_scenes_sorted(selected_area_id, location_id)
            elif zone:
                selected_zone = next(
                    (z for z in zones if z['zone'] == zone or z['area_id'] == zone),
                    None,
                )
                if selected_zone:
                    selected_area_id = selected_zone['area_id']
                    scenes = MapService.get_area_scenes_sorted(selected_area_id, location_id)
                else:
                    flash("分区不存在")
                    zone = ''
        else:
            topo_scenes = MapService.get_region_topology_scenes(region, location_id)

    return render_template(
        "map_teleport.html",
        player=player,
        mode=mode,
        regions=regions,
        region=region,
        zone=zone,
        zones=zones,
        scenes=scenes,
        topo_scenes=topo_scenes,
        selected_region=selected_region,
        selected_zone=selected_zone,
        selected_area_id=selected_area_id,
        country_entries=country_entries,
        location_id=location_id,
        cur_region=cur_region,
        cur_area=cur_area,
        MapService=MapService,
    )


@map_bp.route("/goto_scene/<path:scene_id>")
@login_required
def goto_scene(scene_id):
    """传送到指定场景（分层选择 / 拓扑 / 副本入口）"""
    player = current_user
    location = DataService.get_location(player.current_location)
    if location and location.get('is_copy_map'):
        flash("副本内无法使用传送，请先离开副本")
        return redirect(url_for('game.scene'))
    result = MapService.teleport_to_scene_checked(player, scene_id)
    flash(result['msg'])
    if result['success']:
        return redirect(url_for('game.scene'))
    return redirect(url_for('map.teleport', mode=request.args.get('mode') or 'zone'))


@map_bp.route("/teleport_go/<target>")
@login_required
def teleport_go(target):
    """兼容旧链接：按城市名直传到广场"""
    player = current_user
    location = DataService.get_location(player.current_location)
    if location and location.get('is_copy_map'):
        flash("副本内无法使用传送，请先放弃副本再离开")
        return redirect(url_for('game.scene'))

    result = MapService.teleport(player, target)
    flash(result['msg'])
    if result['success']:
        return redirect(url_for('game.scene'))
    return redirect(url_for('map.teleport'))


@map_bp.route("/town")
@login_required
def town():
    """回城 - 前往所在区域驿站"""
    player = current_user
    location_id = player.current_location
    location = DataService.get_location(location_id)

    if location and location.get('is_copy_map'):
        flash("副本内无法使用回城，请先放弃副本再离开")
        return redirect(url_for('game.scene'))

    result = MapService.town(player)
    msg = result['msg']
    if result['success']:
        flash(msg)
        return redirect(url_for('game.scene'))

    return render_template("map_town.html", player=player, msg=msg, location=location)


@map_bp.route("/shenxing")
@login_required
def shenxing():
    """神行 - 区域功能、怪物传送点"""
    player = current_user
    location_id = player.current_location

    teleport_points = MapService.get_area_teleport_points_by_area(player)

    return render_template("map_shenxing.html",
                         player=player,
                         teleport_points=teleport_points,
                         location_id=location_id,
                         DataService=DataService)


@map_bp.route("/shenxing_go/<scene_id>")
@login_required
def shenxing_go(scene_id):
    """执行神行传送"""
    player = current_user
    location = DataService.get_location(player.current_location)
    if location and location.get('is_copy_map'):
        flash("副本内无法使用神行，请先放弃副本再离开")
        return redirect(url_for('game.scene'))

    result = MapService.shenxing(player, scene_id)
    if result['success']:
        flash(result['msg'])
        return redirect(url_for('game.scene'))
    flash(result['msg'])
    return redirect(url_for('map.shenxing'))


@map_bp.route("/world")
@login_required
def world():
    """世界地图"""
    return render_template("map_world.html")


@map_bp.route("/area")
@login_required
def area():
    """区域地图 - 各区域折叠，点击展开后选择进入场景"""
    player = current_user
    location_id = player.current_location
    location = DataService.get_location(location_id)
    cur_area = location.get('area_id', '') if location else ''

    locations = DataService.get_locations()
    area_map = OrderedDict()
    for lid, ldata in locations.items():
        a = ldata.get('area_id', '') or '(未分类)'
        if a not in area_map:
            area_map[a] = {
                'area_id': a,
                'area_name': ldata.get('area_name', a),
                'scenes': [],
                'is_current': (a == cur_area),
            }
        area_map[a]['scenes'].append({
            'id': lid,
            'name': ldata.get('name', ''),
            'north_exit': ldata.get('north_exit', ''),
            'south_exit': ldata.get('south_exit', ''),
            'east_exit': ldata.get('east_exit', ''),
            'west_exit': ldata.get('west_exit', ''),
        })

    areas = list(area_map.values())
    return render_template("map_area.html",
                         player=player,
                         location=location,
                         location_id=location_id,
                         areas=areas,
                         DataService=DataService)
