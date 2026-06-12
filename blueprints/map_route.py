from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from services import db
from services.data_service import DataService
from services.map_service import MapService

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
        flash("副本内无法使用传送，请先放弃副本再离开")
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

    return render_template("map_teleport.html", player=player, msg=msg, copy_dungeons=DataService.get_copy_dungeons())


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
    """区域地图"""
    player = current_user
    location_id = player.current_location
    location = DataService.get_location(location_id)
    area_id = location.get('area_id', '') if location else ''

    scenes = MapService.get_area_scenes(area_id)

    return render_template("map_area.html",
                         player=player,
                         location=location,
                         scenes=scenes,
                         area_id=area_id,
                         DataService=DataService)