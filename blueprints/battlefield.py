from flask import Blueprint, render_template, redirect, url_for, request, session, flash
from flask_login import login_required, current_user
from models.player import PlayerModel
from services.battlefield_service import BattlefieldService, BATTLEFIELD_CITIES, TIER_TOKEN, TIER_NAME
from services.data_service import DataService
from services import db
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

    # 副将
    from models.lieutenant import Lieutenant
    lieutenant = Lieutenant.query.filter_by(owner_id=player.id, is_deployed=True).first()

    # 1v1锁定对手
    target = None
    target_lieutenant = None
    if player.battlefield_target_id:
        target = PlayerModel.query.get(player.battlefield_target_id)
        # 对手已不在同一战场或已死亡 → 自动解除锁定并清理双方“战斗中”状态
        if not target or not target.in_battlefield or target.battlefield_city != city_key:
            player.battlefield_target_id = None
            player.in_pk = False
            if target and target.in_battlefield:
                target.in_pk = False
            target = None
            db.session.commit()
        else:
            target_lieutenant = Lieutenant.query.filter_by(owner_id=target.id, is_deployed=True, is_alive=True).first()
            # 注意：此处不再清空一次性战斗记录（last_hp_delta/last_mp_delta/
            # last_damage_taken/last_action/item_effect），否则攻击后的扣血/扣蓝
            # 提示会在重定向回来的这一刻被清零、前端永远看不到。
            # 这些字段在 lock_target（锁定瞬间）与每次 strike 开始时清零。

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
                         battle_potions=battle_potions,
                         lieutenant=lieutenant,
                         target=target,
                         target_lieutenant=target_lieutenant)


@battlefield_bp.route("/lock_target/<int:target_id>")
@login_required
def lock_target(target_id):
    """锁定1v1对手（点对点决斗：锁定后双方均进入战斗状态，其他人无法介入）。"""
    player = current_user
    if not player.in_battlefield:
        return redirect(url_for('battlefield.index'))

    # 自己已处于决斗中：需先解除当前锁定才能锁定他人
    if player.in_pk:
        flash("你正在战斗中，无法锁定其他玩家")
        return redirect(url_for('battlefield.city_view'))

    target = PlayerModel.query.get(target_id)
    if not target or not target.in_battlefield or target.battlefield_city != player.battlefield_city:
        flash("目标不在同一战场")
        return redirect(url_for('battlefield.city_view'))

    if target.battlefield_death_time > 0:
        flash("对方已阵亡")
        return redirect(url_for('battlefield.city_view'))

    # 对方已在与他人决斗中：不可介入
    if target.in_pk:
        flash("对方正在战斗中，无法锁定")
        return redirect(url_for('battlefield.city_view'))

    player.battlefield_target_id = target_id
    player.in_pk = True          # 攻击方进入决斗
    target.in_pk = True          # 被攻击方也进入决斗，第三方无法再攻击任一方
    target.battlefield_target_id = player.id   # 互锁：被攻击方也锁定攻击方，双方都能看到战斗页并反击
    # 锁定瞬间清空双方一次性战斗记录，避免上一次战斗的残留提示带到新决斗
    for _p in (player, target):
        _p.last_hp_delta = 0
        _p.last_mp_delta = 0
        _p.last_damage_taken = 0
        _p.last_action = ""
        _p.last_skill = ""
        _p.item_effect = ""
    from services import db; db.session.commit()
    return redirect(url_for('battlefield.city_view'))


@battlefield_bp.route("/unlock_target")
@login_required
def unlock_target():
    """解除1v1锁定，结束点对点决斗，双方恢复可被攻击状态。"""
    player = current_user
    # 解除锁定即视为决斗结束：清理双方“战斗中”状态
    old_target_id = player.battlefield_target_id
    player.battlefield_target_id = None
    player.in_pk = False
    if old_target_id:
        old_target = PlayerModel.query.get(old_target_id)
        if old_target:
            old_target.in_pk = False
            old_target.battlefield_target_id = None  # 解除互锁
    from services import db; db.session.commit()
    return redirect(url_for('battlefield.city_view'))


@battlefield_bp.route("/attack/<int:target_id>")
@login_required
def attack(target_id):
    """普通攻击（GET，1v1锁定后直接链接调用）。"""
    player = current_user
    if not player.in_battlefield:
        return redirect(url_for('battlefield.index'))

    target = PlayerModel.query.get(target_id)
    if not target:
        flash("目标不存在")
        return redirect(url_for('battlefield.city_view'))

    # 点对点：只能攻击已锁定的对手
    if player.battlefield_target_id != target_id:
        flash("只能攻击已锁定的对手")
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
    # 不再flash普通攻击结果——1v1页面直接显示伤害变化量
    return redirect(url_for('battlefield.city_view'))


@battlefield_bp.route("/skill_attack/<int:target_id>/<skill_id>")
@login_required
def skill_attack(target_id, skill_id):
    """技能攻击（GET，1v1锁定后直接链接调用）。"""
    player = current_user
    if not player.in_battlefield:
        return redirect(url_for('battlefield.index'))

    target = PlayerModel.query.get(target_id)
    if not target:
        flash("目标不存在")
        return redirect(url_for('battlefield.city_view'))

    # 点对点：只能攻击已锁定的对手
    if player.battlefield_target_id != target_id:
        flash("只能攻击已锁定的对手")
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
    # 决斗中主动离开：逃跑方判负，对手直接获胜并获得积分，双方决斗结束
    if player.battlefield_target_id:
        # 攻击方主动逃跑
        BattlefieldService.resolve_flee(player)
    elif player.in_pk:
        # 被锁定方主动逃跑：反查锁定自己的人作为获胜方
        opp = PlayerModel.query.filter_by(battlefield_target_id=player.id, in_battlefield=True).first()
        if opp:
            BattlefieldService.resolve_flee(player, opp)
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
                         all_rankings=all_rankings,
                         tier_name=TIER_NAME)
