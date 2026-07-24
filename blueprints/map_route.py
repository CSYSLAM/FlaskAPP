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


@map_bp.route("/teleport", methods=["GET", "POST"])
@login_required
def teleport():
    """传送 - 前往各城市广场"""
    player = current_user
    msg = None

    location = DataService.get_location(player.current_location)
    if location and location.get('is_copy_map'):
        flash("副本内无法使用传送，请先离开副本")
        return redirect(url_for('game.scene'))

    if request.method == "POST":
        target = request.form.get("target")
        if not target:
            msg = "请选择传送目标"
        else:
            result = MapService.teleport(player, target)
            msg = result['msg']
            if result['success']:
                flash(msg)
                return redirect(url_for('game.scene'))

    # 获取本国副本入口列表
    country_entries = CopyDungeonService.get_country_dungeon_entries(player)

    # 城镇区域（折叠后展开对应区域地图，可传送到区域内任意地点）
    location_id = player.current_location
    regions = []
    for key, loc_id in MapService.CITY_SQUARES.items():
        loc = DataService.get_location(loc_id)
        if not loc:
            continue
        area_id = loc.get('area_id', '')
        label = loc.get('area_name') or key
        scenes = MapService.get_area_scenes(area_id)
        regions.append({
            'key': key,
            'label': label,
            'square_id': loc_id,
            'scenes': scenes,
            'is_current': location_id in [s['id'] for s in scenes],
        })

    # 职业地图
    prof_list = [
        {'target': '神农架', 'label': '神农架(战士)'},
        {'target': '昆仑', 'label': '昆仑山(术士)'},
        {'target': '倭寇岛', 'label': '倭寇岛(刺客)'},
    ]

    return render_template("map_teleport.html", player=player, msg=msg,
                         regions=regions,
                         prof_list=prof_list,
                         country_entries=country_entries,
                         location_id=location_id)


@map_bp.route("/goto_scene/<path:scene_id>")
@login_required
def goto_scene(scene_id):
    """传送到指定场景（用于副本入口传送）"""
    player = current_user
    location = DataService.get_location(player.current_location)
    if location and location.get('is_copy_map'):
        flash("副本内无法使用传送，请先离开副本")
        return redirect(url_for('game.scene'))
    result = MapService.teleport_to_scene(player, scene_id)
    flash(result['msg'])
    if result['success']:
        return redirect(url_for('game.scene'))
    return redirect(url_for('map.teleport'))


@map_bp.route("/teleport_go/<target>")
@login_required
def teleport_go(target):
    """传送链接点击 - 直接传送"""
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

    # 失败时留在回城界面显示消息
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