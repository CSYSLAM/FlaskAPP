from flask import Blueprint, render_template, redirect, url_for, request, session, flash
from flask_login import login_required, current_user
from models.player import PlayerModel
from services.battlefield_service import BattlefieldService, BATTLEFIELD_CITIES, TIER_TOKEN, TIER_NAME
from services.data_service import DataService
import time

battlefield_bp = Blueprint('battlefield', __name__)


@battlefield_bp.route("/")
@login_required
def index():
    player = current_user
    BattlefieldService.tick()
    if player.in_battlefield:
        return redirect(url_for('battlefield.city_view'))
    return render_template("battlefield_index.html",
                         player=player,
                         cities=BATTLEFIELD_CITIES,
                         tier_token=TIER_TOKEN,
                         tier_name=TIER_NAME,
                         is_war_time=BattlefieldService.is_war_time(),
                         is_entry_allowed=BattlefieldService.is_entry_allowed(),
                         test_war=BattlefieldService.get_test_war_status())


@battlefield_bp.route("/enter/<city_key>")
@login_required
def enter(city_key):
    player = current_user
    success, msg = BattlefieldService.enter_battlefield(player, city_key)
    flash(msg)
    if success:
        return redirect(url_for('battlefield.city_view'))
    return redirect(url_for('battlefield.index'))


@battlefield_bp.route("/city")
@login_required
def city_view():
    player = current_user
    if not player.in_battlefield:
        return redirect(url_for('battlefield.index'))

    BattlefieldService.tick()
    if BattlefieldService.should_force_exit():
        BattlefieldService.exit_battlefield(player)
        flash("战场已结束，你被传送出战场")
        return redirect(url_for('game.scene'))

    if player.battlefield_death_time > 0:
        if BattlefieldService.can_revive_in_battlefield(player):
            return redirect(url_for('battlefield.revive'))
        else:
            return redirect(url_for('battlefield.death'))

    city_key = player.battlefield_city
    city = BATTLEFIELD_CITIES.get(city_key)

    other_players = BattlefieldService.get_city_players(city_key)
    other_players = [p for p in other_players if p.id != player.id]

    player_ranking, legion_ranking = BattlefieldService.get_city_rankings(city_key)
    kill_log = BattlefieldService.get_kill_log(city_key)

    from models.player import PlayerSkill
    from services.data_service import DataService as DS
    skills = DS.get_skills()
    player_skills = {ps.skill_id: ps for ps in PlayerSkill.query.filter_by(player_id=player.id).all()}

    # 战场专用药品（背包中带 battlefield_item 标记的药品）
    battle_potions = []
    for inv in DS.get_inventory(player.id):
        it = DS.get_item(inv.item_id)
        if it and it.get('battlefield_item') and inv.quantity > 0:
            battle_potions.append({'item_id': inv.item_id,
                                   'name': it.get('name', inv.item_id),
                                   'quantity': inv.quantity})

    return render_template("battlefield_city.html",
                         player=player,
                         city=city,
                         city_key=city_key,
                         other_players=other_players,
                         player_ranking=player_ranking,
                         legion_ranking=legion_ranking,
                         kill_log=kill_log,
                         skills=skills,
                         player_skills=player_skills,
                         battle_potions=battle_potions)


@battlefield_bp.route("/attack/<int:target_id>", methods=["POST"])
@login_required
def attack(target_id):
    player = current_user
    if not player.in_battlefield:
        return redirect(url_for('battlefield.index'))

    target = PlayerModel.query.get(target_id)
    if not target:
        flash("目标不存在")
        return redirect(url_for('battlefield.city_view'))

    current_time = time.time()
    if current_time - player.last_attack_time < 2:
        flash("攻击冷却中")
        return redirect(url_for('battlefield.city_view'))
    player.last_attack_time = current_time

    result, error = BattlefieldService.battlefield_strike(player, target)
    if result:
        flash(result)
    elif error:
        flash(error)
    else:
        flash(f"你攻击了{target.nickname}，造成{player.last_damage_dealt}伤害")
    return redirect(url_for('battlefield.city_view'))


@battlefield_bp.route("/skill_attack/<int:target_id>/<skill_id>", methods=["POST"])
@login_required
def skill_attack(target_id, skill_id):
    player = current_user
    if not player.in_battlefield:
        return redirect(url_for('battlefield.index'))

    target = PlayerModel.query.get(target_id)
    if not target:
        flash("目标不存在")
        return redirect(url_for('battlefield.city_view'))

    current_time = time.time()
    if current_time - player.last_attack_time < 2:
        flash("攻击冷却中")
        return redirect(url_for('battlefield.city_view'))
    player.last_attack_time = current_time

    result, error = BattlefieldService.battlefield_skill_strike(player, target, skill_id)
    if result:
        flash(result)
    elif error:
        flash(error)
    else:
        flash(f"对{target.nickname}使用技能，造成{player.last_damage_dealt}伤害")
    return redirect(url_for('battlefield.city_view'))


@battlefield_bp.route("/use_potion/<item_id>")
@login_required
def use_potion(item_id):
    """战场中使用战场专用药品（普通药品在战场无效）。"""
    player = current_user
    if not player.in_battlefield:
        return redirect(url_for('battlefield.index'))

    item_data = DataService.get_item(item_id)
    if not item_data or not item_data.get('battlefield_item'):
        flash("战场中只能使用战场专用药品")
        return redirect(url_for('battlefield.city_view'))

    # 生命/魔法已满时拦截，避免浪费药品
    ue = item_data.get('usage_effect', {}) or {}
    sc = list(ue.get('stat_changes', {}).keys()) + list(ue.get('stat_changes_rng', {}).keys())
    restores = [s for s in sc if s in ('health', 'mana')]
    has_other = any(s not in ('health', 'mana') for s in sc)
    if restores and not has_other:
        full = True
        mh = player.effective_max_health
        if 'health' in restores and mh and player.health < mh:
            full = False
        mm = player.effective_max_mana
        if 'mana' in restores and mm and player.mana < mm:
            full = False
        if full:
            flash("生命/魔法已满，无需使用药品")
            return redirect(url_for('battlefield.city_view'))

    current_time = time.time()
    if current_time - player.last_attack_time < 2:
        flash("使用冷却中")
        return redirect(url_for('battlefield.city_view'))
    player.last_attack_time = current_time

    from services.item_service import ItemService
    success, msg = ItemService.use_item(player, item_id)
    flash(msg)
    return redirect(url_for('battlefield.city_view'))


@battlefield_bp.route("/revive")
@login_required
def revive():
    player = current_user
    if not player.in_battlefield or player.battlefield_death_time <= 0:
        return redirect(url_for('battlefield.city_view'))

    elapsed = time.time() - player.battlefield_death_time
    remaining = max(0, 15 - elapsed)
    if remaining <= 0:
        return redirect(url_for('battlefield.death'))

    inv = DataService.get_inventory_item(player.id, "battle_revive_lamp")
    has_lamp = inv is not None and inv.quantity > 0

    return render_template("battlefield_revive.html",
                         player=player,
                         remaining=int(remaining),
                         has_lamp=has_lamp)


@battlefield_bp.route("/revive_action")
@login_required
def revive_action():
    player = current_user
    success, msg = BattlefieldService.revive_in_battlefield(player)
    flash(msg)
    if success:
        return redirect(url_for('battlefield.city_view'))
    return redirect(url_for('battlefield.death'))


@battlefield_bp.route("/death")
@login_required
def death():
    player = current_user
    if player.in_battlefield and player.battlefield_death_time > 0:
        if not BattlefieldService.can_revive_in_battlefield(player):
            BattlefieldService.force_death_exit(player)
    return render_template("battlefield_death.html", player=player)


@battlefield_bp.route("/exit")
@login_required
def exit_battlefield():
    player = current_user
    BattlefieldService.exit_battlefield(player)
    flash("你离开了战场")
    return redirect(url_for('game.scene'))


@battlefield_bp.route("/rankings")
@login_required
def rankings():
    player = current_user
    all_rankings = {}
    for city_key in BATTLEFIELD_CITIES:
        p_rank, l_rank = BattlefieldService.get_city_rankings(city_key)
        all_rankings[city_key] = {
            'city': BATTLEFIELD_CITIES[city_key],
            'player_ranking': p_rank,
            'legion_ranking': l_rank,
        }
    return render_template("battlefield_rankings.html",
                         player=player,
                         all_rankings=all_rankings)
