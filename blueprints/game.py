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

        # Check if need revive (health <= 0 or need_revive flag)
        if player.need_revive or player.health <= 0:
            return redirect(url_for('battle.revive'))

        # Check if in battlefield
        if player.in_battlefield:
            return redirect(url_for('battlefield.city_view'))

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
        # 清除可能残留的“上次击杀为精英/世界boss”标记（正常流程已在结算界面消费）
        data.pop('last_kill_special', None)
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

        # Finance bandit: if a bandit is alive at this location, show it as a world boss (理财·劫匪)
        # 击杀后（复活中）不在场景显示，仅在金珠股市劫匪情报中显示复活倒计时
        from services.finance_service import FinanceService
        bandit_info = FinanceService.get_bandit_at_location(location_id)
        if bandit_info:
            bandit_mid, bandit_city, bandit_respawn = bandit_info
            if bandit_respawn <= 0:  # 在场才显示，复活中则跳过
                all_monsters = DataService.get_monsters()
                bdata = all_monsters.get(bandit_mid)
                if bdata:
                    from models.monster import Monster
                    bm = Monster.from_dict(bandit_mid, bdata)
                    bm.is_bandit = True
                    monsters_list.append(bm)

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

        # Quest data for scene
        from services.quest_service import QuestService
        active_quest_count = QuestService.get_active_quest_count(player)
        current_main = QuestService.get_current_main_quest(player)
        # Mark NPCs that have quests (single pass)
        active = QuestService.get_active_quests(player)
        for npc in npcs:
            npc_quests = QuestService.get_available_quests_for_npc(player, npc.monster_id)
            npc.has_quest = len(npc_quests) > 0
            npc.has_completable = False
            for q in npc_quests:
                if q['id'] not in active:
                    continue
                obj = q.get('objective', {})
                if obj.get('type') == 'talk_npc' and obj.get('npc_id') == npc.monster_id:
                    npc.has_completable = True
                    break
                if QuestService.is_quest_objective_met(player, q['id']):
                    npc.has_completable = True
                    break

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
                             active_quest_count=active_quest_count,
                             current_main=current_main,
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

    monster_id = request.args.get("mid") or None
    success, msg = BattleService.start_pve(player, monster_id=monster_id)
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

    # Finance popularity: count NPC visits for stock market (理财·人气)
    from services.finance_service import FinanceService
    FinanceService.record_npc_visit(monster_id, player.id)

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
        from services.quest_service import QuestService
        QuestService.update_talk_progress(player, monster_id)
        npc_quests = QuestService.get_available_quests_for_npc(player, monster_id)
        return render_template("skill_hall.html",
                             player=player,
                             monster=monster,
                             skills=skills,
                             player_skills=player_skills,
                             npc_id=monster_id,
                             npc_quests=npc_quests)

    if '铁匠' in monster_id:
        from services.quest_service import QuestService
        QuestService.update_talk_progress(player, monster_id)
        npc_quests = QuestService.get_available_quests_for_npc(player, monster_id)
        return render_template("blacksmith.html",
                             player=player,
                             monster=monster,
                             npc_id=monster_id,
                             npc_quests=npc_quests)

    if '军团使者' in monster_id or '战场使者' in monster_id:
        return redirect(url_for('battlefield.index'))

    if '大夫' in monster_id:
        from services.quest_service import QuestService
        QuestService.update_talk_progress(player, monster_id)
        npc_quests = QuestService.get_available_quests_for_npc(player, monster_id)
        # 与铁匠/副将/技能一致：任务进行中也能看到药铺功能入口
        return render_template("doctor.html",
                             player=player,
                             monster=monster,
                             npc_id=monster_id,
                             npc_quests=npc_quests)

    if '金掌柜' in monster_id or '仓库' in monster_id:
        from services.quest_service import QuestService
        QuestService.update_talk_progress(player, monster_id)
        npc_quests = QuestService.get_available_quests_for_npc(player, monster_id)
        # 金掌柜快捷入口：前往股市（理财）
        if request.args.get('to') == 'finance':
            return redirect(url_for('activity.finance_page'))
        if npc_quests:
            return render_template("view_npc.html", player=player, monster=monster,
                                 npc_quests=npc_quests, QuestService=QuestService)
        return redirect(url_for('warehouse.warehouse', npc_id=monster_id))

    if '驿站管理员' in monster_id:
        from services.quest_service import QuestService
        QuestService.update_talk_progress(player, monster_id)
        npc_quests = QuestService.get_available_quests_for_npc(player, monster_id)
        if npc_quests:
            return render_template("view_npc.html", player=player, monster=monster,
                                 npc_quests=npc_quests, QuestService=QuestService)
        return redirect(url_for('lost_found.lost_found'))

    if '副将统领' in monster_id:
        from services.quest_service import QuestService
        from services.lieutenant_service import LieutenantService
        from models.lieutenant import Lieutenant
        QuestService.update_talk_progress(player, monster_id)
        npc_quests = QuestService.get_available_quests_for_npc(player, monster_id)
        return render_template("commander.html",
                             player=player,
                             lt_count=Lieutenant.query.filter_by(owner_id=player.id).count(),
                             max_slots=LieutenantService.get_max_slots(player),
                             npc_id=monster_id,
                             npc_quests=npc_quests)

    if '王老板' in monster_id:
        from services.quest_service import QuestService
        QuestService.update_talk_progress(player, monster_id)
        npc_quests = QuestService.get_available_quests_for_npc(player, monster_id)
        cost = player.level * 10
        vip_free = player.is_vip
        max_hp = PlayerService.get_max_health(player)
        max_mp = PlayerService.get_max_mana(player)
        already_full = player.health >= max_hp and player.mana >= max_mp
        return render_template("inn.html",
                             player=player, npc_id=monster_id,
                             npc_name=monster_data.get('name', '王老板'),
                             cost=cost, vip_free=vip_free,
                             already_full=already_full,
                             npc_quests=npc_quests)

    if '任务使者' in monster_id:
        return redirect(url_for('activity.npc_daily_tasks'))

    # Check for quests from this NPC
    from services.quest_service import QuestService
    QuestService.update_talk_progress(player, monster_id)
    npc_quests = QuestService.get_available_quests_for_npc(player, monster_id)

    return render_template("view_npc.html",
                         player=player,
                         monster=monster,
                         npc_quests=npc_quests,
                         QuestService=QuestService)


@game_bp.route("/rest")
@login_required
def rest():
    player = current_user
    PlayerService.rest(player)
    return redirect(url_for("game.scene"))


@game_bp.route("/inn/<npc_id>")
@login_required
def inn_view(npc_id):
    player = current_user
    monsters = DataService.get_monsters()
    npc_data = monsters.get(npc_id)
    if not npc_data:
        return redirect(url_for("game.scene"))
    cost = player.level * 10
    vip_free = player.is_vip
    max_hp = PlayerService.get_max_health(player)
    max_mp = PlayerService.get_max_mana(player)
    already_full = player.health >= max_hp and player.mana >= max_mp
    return render_template("inn.html",
                         player=player, npc_id=npc_id,
                         npc_name=npc_data.get('name', '王老板'),
                         cost=cost, vip_free=vip_free,
                         already_full=already_full)


@game_bp.route("/inn_rest/<npc_id>")
@login_required
def inn_rest(npc_id):
    player = current_user
    max_hp = PlayerService.get_max_health(player)
    max_mp = PlayerService.get_max_mana(player)
    if player.health >= max_hp and player.mana >= max_mp:
        flash("#你气血、魔法充盈，无需休息")
        return redirect(url_for("game.inn_view", npc_id=npc_id))

    cost = player.level * 10
    if not player.is_vip:
        if player.gold < cost:
            flash(f"银两不足（需要{cost}银两）")
            return redirect(url_for("game.inn_view", npc_id=npc_id))
        player.gold -= cost
        player.health = max_hp
        player.mana = max_mp
        flash(f"#休息成功，银两-{cost}\n生命值补满\n魔法值补满")
    else:
        player.health = max_hp
        player.mana = max_mp
        flash(f"#休息成功(VIP免费)\n生命值补满\n魔法值补满")
    db.session.commit()
    return redirect(url_for("game.inn_view", npc_id=npc_id))


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
