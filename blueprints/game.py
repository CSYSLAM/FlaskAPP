from flask import Blueprint, render_template, redirect, url_for, request, session, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime
from models.player import PlayerModel, EquipmentInstance, PlayerSkill
from services import db
from services.data_service import DataService
from services.battle_service import BattleService
from services.player_service import PlayerService
import traceback as _tb

game_bp = Blueprint('game', __name__)


def pk_check(func):
    """Decorator to check if player is in PK and redirect."""
    def wrapper(*args, **kwargs):
        player = current_user
        if player.in_pk and player.pk_opponent:
            return redirect(url_for('battle.pk_battle', opponent=player.pk_opponent))
        return func(*args, **kwargs)
    wrapper.__name__ = func.__name__
    return wrapper


@game_bp.route("/")
@game_bp.route("/scene")
@login_required
@pk_check
def scene():
    try:
        player = current_user

        # Check if need revive
        if player.need_revive:
            return redirect(url_for('battle.revive'))

        DataService.clear_expired_effects(player.id)

        # Auto-revive dead lieutenant
        from models.lieutenant import Lieutenant
        dead_lt = Lieutenant.query.filter_by(owner_id=player.id, is_alive=False).first()
        if dead_lt:
            from services.lieutenant_service import LieutenantService
            LieutenantService.revive(dead_lt)

        location_id = player.current_location
        locations = DataService.get_locations()
        location = locations.get(location_id) if location_id else None

        if not location:
            player.current_location = "beiping_center.广场"
            location = locations.get("beiping_center.广场")
            if not location:
                return "No starting location found", 500

        # Get other players in the same location
        other_players = PlayerModel.query.filter(
            PlayerModel.current_location == location_id,
            PlayerModel.id != player.id
        ).all()

        # Get monsters for this location (support both monster_type and monsters array)
        monsters_list = []
        location_monsters = location.get("monsters", [])
        if location_monsters:
            all_monsters = DataService.get_monsters()
            for monster_id in location_monsters:
                monster_data = all_monsters.get(monster_id)
                if monster_data:
                    from models.monster import Monster
                    monsters_list.append(Monster.from_dict(monster_id, monster_data))

        # Get NPCs in this location
        npcs = []
        npc_ids = location.get("npcs", [])
        if npc_ids:
            all_monsters = DataService.get_monsters()
            for nid in npc_ids:
                ndata = all_monsters.get(nid)
                if ndata:
                    from models.monster import Monster
                    npcs.append(Monster.from_dict(nid, ndata))

        # Get recent public messages
        public_messages = DataService.list_latest_messages(3)

        # Get ground items
        ground_items = DataService.get_ground_items(location_id)

        return render_template("scene.html",
                             player=player,
                             location=location,
                             locations=locations,
                             other_players=other_players,
                             monsters=monsters_list,
                             npcs=npcs,
                             public_messages=public_messages,
                             ground_items=ground_items,
                             DataService=DataService,
                             now=datetime.now())
    except Exception as e:
        error_detail = _tb.format_exc()
        print(f"=== SCENE ERROR ===\n{error_detail}")
        return f"<h1>Scene Error</h1><pre>{error_detail}</pre>", 500


@game_bp.route("/move/<direction>")
@login_required
def move(direction):
    player = current_user
    if player.in_battle:
        flash("战斗中无法移动")
        return redirect(url_for("battle.battle"))

    if player.in_pk:
        flash("PK中无法移动")
        return redirect(url_for("battle.pk_battle",
                               opponent=player.pk_opponent))

    locations = DataService.get_locations()
    location = locations.get(player.current_location)
    if not location:
        return redirect(url_for("game.scene"))

    exit_id = None
    if direction == 'north':
        exit_id = location.get("north_exit")
    elif direction == 'south':
        exit_id = location.get("south_exit")
    elif direction == 'east':
        exit_id = location.get("east_exit")
    elif direction == 'west':
        exit_id = location.get("west_exit")

    if exit_id and exit_id in locations:
        player.current_location = exit_id
        visited = player.visited_locations
        if exit_id not in visited:
            visited.append(exit_id)
            player.visited_locations = visited
            from services.achievement_service import AchievementService
            AchievementService.check(player, 'visit', len(visited))
        db.session.commit()
    else:
        flash("无法朝该方向移动")

    return redirect(url_for("game.scene"))


@game_bp.route("/pickup/<item_id>")
@login_required
def pickup_item(item_id):
    player = current_user
    DataService.add_item_to_inventory(player.id, item_id)
    db.session.commit()
    flash(f"拾取了物品")
    return redirect(url_for("game.scene"))


@game_bp.route("/encounter")
@login_required
def encounter():
    player = current_user
    if player.in_battle:
        return redirect(url_for("battle.battle"))

    success, msg = BattleService.start_pve(player)
    if not success:
        flash(msg)
        return redirect(url_for("game.scene"))

    return redirect(url_for("battle.battle"))


@game_bp.route("/view_npc/<monster_id>")
@login_required
def view_npc(monster_id):
    player = current_user
    monsters = DataService.get_monsters()
    monster_data = monsters.get(monster_id)
    if not monster_data:
        return redirect(url_for("game.scene"))

    from models.monster import Monster
    monster = Monster.from_dict(monster_id, monster_data)

    if '技能教官' in monster_id:
        skills = DataService.get_skills()
        player_skills = {
            ps.skill_id: ps
            for ps in PlayerSkill.query.filter_by(player_id=player.id).all()
        }
        return render_template("skill_hall.html",
                             player=player,
                             monster=monster,
                             skills=skills,
                             player_skills=player_skills,
                             npc_id=monster_id)

    return render_template("view_npc.html",
                         player=player,
                         monster=monster)


@game_bp.route("/rest")
@login_required
def rest():
    player = current_user
    PlayerService.rest(player)
    return redirect(url_for("game.scene"))


@game_bp.route("/pickup_ground/<item_id>")
@login_required
def pickup_ground(item_id):
    player = current_user
    location_id = player.current_location
    item = DataService.pickup_ground_item(location_id, item_id)
    if not item:
        flash("物品已被拾取")
        return redirect(url_for("game.scene"))

    if item['type'] == 'item':
        DataService.add_item_to_inventory(player.id, item['item_id'])
        item_data = DataService.get_item(item['item_id'])
        name = item_data.get('name', item['item_id']) if item_data else item['item_id']
        flash(f"拾取了 {name}")
    else:
        flash("物品数据异常")

    db.session.commit()
    return redirect(url_for("game.scene"))