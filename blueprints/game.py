from flask import Blueprint, render_template, redirect, url_for, request, session, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from models.player import PlayerModel, EquipmentInstance, PlayerSkill, ChatMessage
from services import db
from services.data_service import DataService
from services.battle_service import BattleService
from services.copy_dungeon_service import CopyDungeonService
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

        # If player left a copy dungeon map, reset their dungeon state
        data = player.activity_data
        if location and not location.get('is_copy_map'):
            copy_states = data.get('copy_dungeons', {})
            if copy_states:
                data['copy_dungeons'] = {}
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
            from services.world_boss_service import WorldBossService
            for monster_id in location_monsters:
                monster_data = all_monsters.get(monster_id)
                if monster_data and CopyDungeonService.should_show_monster_in_scene(player, monster_id):
                    from models.monster import Monster
                    m = Monster.from_dict(monster_id, monster_data)
                    if monster_data.get("is_elite") and not monster_data.get("is_copy"):
                        remaining = WorldBossService.get_respawn_remaining(monster_id)
                        if remaining > 0:
                            m.respawning = True
                            m.respawn_remaining = remaining
                    monsters_list.append(m)

        # Get NPCs in this location
        npcs = []
        npc_ids = location.get("npcs", [])
        if npc_ids:
            all_monsters = DataService.get_monsters()
            for nid in npc_ids:
                ndata = all_monsters.get(nid)
                if ndata:
                    from models.monster import Monster
                    npc = Monster.from_dict(nid, ndata)
                    marker = CopyDungeonService.get_npc_marker(player, nid)
                    npc.task_icon = marker['icon'] if marker else None
                    npcs.append(npc)

        # Get messages from last 3 minutes
        cutoff = datetime.utcnow() - timedelta(minutes=3)
        from sqlalchemy import or_

        # Channel 1: single unread public/system message, consumed on each refresh
        last_c1_id = data.get('last_read_c1_id', 0)
        next_c1 = ChatMessage.query.filter(
            ChatMessage.message_type.in_(['public', 'system']),
            ChatMessage.id > last_c1_id,
            ChatMessage.created_at >= cutoff
        ).order_by(ChatMessage.id.asc()).first()
        channel1_msg = next_c1
        if next_c1:
            data['last_read_c1_id'] = next_c1.id
        player.activity_data = data
        db.session.commit()

        # Channel 2: country messages (same country) + private messages (to/from player)
        same_country_ids = [p.id for p in PlayerModel.query.filter_by(country=player.country).all()]
        channel2 = ChatMessage.query.filter(
            or_(
                db.and_(
                    ChatMessage.message_type == 'country',
                    ChatMessage.sender_id.in_(same_country_ids)
                ),
                db.and_(
                    ChatMessage.message_type == 'private',
                    or_(
                        ChatMessage.sender_id == player.id,
                        ChatMessage.receiver_id == player.id
                    )
                )
            ),
            ChatMessage.created_at >= cutoff
        ).order_by(ChatMessage.created_at.desc()).limit(10).all()

        # Player notifications (JSON field)
        notifications = player.notifications or []
        recent_notifications = [n for n in notifications[:5]]
        # Check notification time
        filtered_notifications = []
        for n in recent_notifications:
            try:
                n_time = datetime.strptime(n.get('time', ''), '%Y-%m-%d %H:%M')
                if n_time >= cutoff:
                    filtered_notifications.append(n)
            except (ValueError, TypeError):
                pass

        # Get ground items
        ground_items = DataService.get_ground_items(location_id)

        return render_template("scene.html",
                             player=player,
                             location=location,
                             locations=locations,
                             other_players=other_players,
                             monsters=monsters_list,
                             npcs=npcs,
                             channel1_msg=channel1_msg,
                             channel2=channel2,
                             notifications=filtered_notifications,
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
        current_name = location.get("name")
        target_name = locations[exit_id].get("name")
        is_huangjin_river_crossing = (
            location.get("copy_dungeon_id") == "huangjin_trial"
            and {current_name, target_name} == {"黄河岸边", "兖州"}
        )
        if is_huangjin_river_crossing:
            raft = DataService.get_inventory_item(player.id, "wood_raft")
            if not raft or raft.quantity < 1:
                flash("需要先前往小渔村击杀偷伐人，夺取木筏后才能渡河")
                return redirect(url_for("game.scene"))

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

    if monster_data.get('copy_dungeon_id') or monster_data.get('is_copy'):
        context = CopyDungeonService.build_npc_context(player, monster_id)
        if context:
            view_mode = request.args.get('mode', 'npc')
            context.update({
                'player': player,
                'monster': monster,
                'view_mode': view_mode,
            })
            return render_template("copy_dungeon.html", **context)

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

    if '铁匠' in monster_id:
        return render_template("blacksmith.html",
                             player=player,
                             monster=monster,
                             npc_id=monster_id)

    if '大夫' in monster_id:
        return redirect(url_for('medicine.shop', npc_id=monster_id))

    if '金掌柜' in monster_id or '仓库' in monster_id:
        return redirect(url_for('warehouse.warehouse', npc_id=monster_id))

    if '驿站管理员' in monster_id:
        return redirect(url_for('lost_found.lost_found'))

    if '副将统领' in monster_id:
        return redirect(url_for('commander.index'))

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
