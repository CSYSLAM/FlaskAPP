import time
from flask import Blueprint, render_template, redirect, url_for, request, session, flash
from flask_login import login_required, current_user
from datetime import datetime
from models.monster import Monster
from models.player import PlayerSkill
from models.lieutenant import Lieutenant
from services import db
from services.data_service import DataService
from services.battle_service import BattleService
from services.player_service import PlayerService
from services.item_service import ItemService

from services.world_boss_service import WorldBossService

battle_bp = Blueprint('battle', __name__)


@battle_bp.route("/battle")
@login_required
def battle():
    player = current_user
    if not player.in_battle:
        return redirect(url_for("game.scene"))

    monster = BattleService.get_current_monster(player)
    if not monster or not monster.killable:
        player.in_battle = False
        player.current_encounter = None
        db.session.commit()
        return redirect(url_for("game.scene"))

    # World boss: check if still alive (shared-HP elites only; one-time & copy elites are personal)
    from services.world_boss_service import WorldBossService
    if monster.is_elite and not getattr(monster, 'is_one_time_elite', False) and not getattr(monster, 'is_copy', False):
        boss = WorldBossService.get_boss(monster.monster_id)
        if boss and boss.current_health <= 0 and not boss.is_alive:
            player.in_battle = False
            player.current_encounter = None
            db.session.commit()
            flash("该怪物已被击杀，正在复活中")
            return redirect(url_for("game.scene"))
        if boss:
            monster.health = boss.current_health

    referrer = request.referrer
    if referrer and 'scene' in referrer:
        player.last_action = ""
        player.last_damage_dealt = ""
        player.last_damage_taken = 0
        player.last_mana_cost = 0
        player.last_skill = ""
        # Don't clear monster.last_action - it contains the first-strike log

    return render_template("battle.html",
                         player=player,
                         monster=monster,
                         lieutenant=Lieutenant.query.filter_by(owner_id=player.id, is_deployed=True).first(),
                         DataService=DataService,
                         participants=WorldBossService.get_participant_count(monster.monster_id, player.id) if monster.is_elite else 0,
                         now=datetime.now())


@battle_bp.route("/fight", methods=["POST"])
@login_required
def fight():
    player = current_user
    if not player.in_battle:
        return redirect(url_for("game.scene"))

    action = request.form.get("action")
    monster = BattleService.get_current_monster(player)
    if not monster:
        player.in_battle = False
        db.session.commit()
        return redirect(url_for("game.scene"))

    if action == "attack":
        result_monster, error, result = BattleService.player_attack(player)
    elif action.startswith("use:"):
        item_id = action.split(":")[1]
        if item_id:
            result_monster, error, result = BattleService.use_potion(player, item_id)
        else:
            result_monster, error, result = monster, None, None
    else:
        result_monster, error, result = BattleService.use_skill(player, action)

    if result == "你被击败了":
        return redirect(url_for("battle.revive"))

    if result:
        # monster defeated - go to battle result
        return redirect(url_for("battle.battle_result"))

    return redirect(url_for("battle.battle"))


@battle_bp.route("/revive")
@login_required
def revive():
    player = current_user
    has_revive = DataService.get_inventory_item(player.id, "potion_revive") is not None
    if has_revive:
        inv = DataService.get_inventory_item(player.id, "potion_revive")
        has_revive = inv and inv.quantity > 0
    return render_template("revive.html", player=player, has_revive_item=has_revive)


@battle_bp.route("/revive_action/<method>")
@login_required
def revive_action(method):
    player = current_user
    if method == "item":
        inv = DataService.get_inventory_item(player.id, "potion_revive")
        if inv and inv.quantity > 0:
            DataService.remove_item_from_inventory(player.id, "potion_revive", 1)
            player.health = PlayerService.get_max_health(player)
            player.mana = PlayerService.get_max_mana(player)
            player.in_battle = False
            player.current_encounter = None
            player.need_revive = False
            killed_by = player.killed_by
            player.killed_by = None
            db.session.commit()
            msg = "使用续命灯复活成功，生命值已满！"
            if killed_by:
                msg += f" 你被{killed_by}击杀了。"
            return render_template("revive_result.html", revive_message=msg)

    # 回城疗伤：消耗300银两，虚弱复活 + 传送至当前所在城市客栈
    if method == "city_heal":
        if player.gold < 300:
            return render_template("revive_result.html", revive_message="回城疗伤需要300银两，银两不足")
        player.gold -= 300
        player.health = max(10, PlayerService.get_max_health(player) // 10)
        player.mana = max(5, PlayerService.get_max_mana(player) // 10)
        player.in_battle = False
        player.current_encounter = None
        player.need_revive = False
        player.killed_by = None
        locations = DataService.get_locations()
        city = (player.current_location or '').split('.')[0].split('_')[0]
        for cand in (f"{city}_center.客栈", f"{city}_center.广场"):
            if cand in locations:
                player.current_location = cand
                break
        db.session.commit()
        return render_template("revive_result.html", revive_message="回城疗伤成功，生命值恢复到10%，已传送至本城客栈！")

    # Weak revive: 恢复10%血/蓝（经验已在死亡时扣除，此处不再扣）
    player.health = max(10, PlayerService.get_max_health(player) // 10)
    player.mana = max(5, PlayerService.get_max_mana(player) // 10)
    player.in_battle = False
    player.current_encounter = None
    player.need_revive = False
    killed_by = player.killed_by
    player.killed_by = None
    db.session.commit()
    msg = "虚弱复活成功，生命值恢复到10%！"
    if killed_by:
        msg += f" 你被{killed_by}击杀了。"
    return render_template("revive_result.html", revive_message=msg)


@battle_bp.route("/battle_result")
@login_required
def battle_result():
    player = current_user
    result = player.last_battle_result
    lost_exp = 0

    is_pk = player.in_pk
    last_action = player.last_action or ""
    # 读取并清除“上次击杀是否为精英/世界boss”标记（精英/世界boss击杀后隐藏“继续挑战”）
    _ad = player.activity_data
    hide_continue = _ad.pop('last_kill_special', False)
    player.activity_data = _ad
    db.session.commit()
    return render_template("battle_result.html",
                       result=result,
                       lost_experience=lost_exp,
                       is_pk=is_pk,
                       last_action=last_action,
                       hide_continue=hide_continue)


@battle_bp.route("/continue_battle")
@login_required
def continue_battle():
    player = current_user
    monster, error = BattleService.start_pve(player)
    if not monster:
        if error and "被击败" in error:
            flash(error)
            return redirect(url_for("battle.revive"))
        flash(error or "这里没有怪物")
        return redirect(url_for("game.scene"))
    return redirect(url_for("battle.battle"))


@battle_bp.route("/use_skill/<skill_id>")
@login_required
def use_skill(skill_id):
    """GET 版技能释放（供战斗界面技键链接调用）。"""
    player = current_user
    if not player.in_battle:
        return redirect(url_for("game.scene"))

    action = skill_id if skill_id != "attack" else "attack"
    if action == "attack":
        result_monster, error, result = BattleService.player_attack(player)
    else:
        result_monster, error, result = BattleService.use_skill(player, action)

    if result == "你被击败了":
        return redirect(url_for("battle.revive"))

    if result:
        return redirect(url_for("battle.battle_result"))

    if error:
        flash(error)
    return redirect(url_for("battle.battle"))


@battle_bp.route("/use_potion/<item_id>")
@login_required
def use_potion(item_id):
    """GET 版战斗中使用药品（供药键链接调用，算作一个完整回合：用药+怪物反击）。"""
    player = current_user
    if not player.in_battle:
        return redirect(url_for("game.scene"))

    result_monster, error, result = BattleService.use_potion(player, item_id)

    if result == "你被击败了":
        return redirect(url_for("battle.revive"))

    if result:
        return redirect(url_for("battle.battle_result"))

    if error:
        flash(error)
    return redirect(url_for("battle.battle"))


@battle_bp.route("/flee")
@login_required
def flee():
    player = current_user
    # PK 中撤退：直接结束 PK（双方解除状态）
    if player.in_pk and player.pk_opponent:
        opponent = DataService.get_player_by_username(player.pk_opponent)
        if opponent:
            BattleService._end_pk(player, opponent)
        else:
            player.in_pk = False
            player.pk_opponent = None
        db.session.commit()
        flash("你退出了PK")
        return redirect(url_for("game.scene"))
    success, msg = BattleService.flee(player)
    if not success and "被击败" in msg:
        return redirect(url_for("battle.revive"))
    if success:
        return redirect(url_for("game.scene"))
    return redirect(url_for("battle.battle"))


# --- Shortcuts ---

@battle_bp.route("/shortcuts")
@battle_bp.route("/shortcuts/")
@login_required
def shortcuts():
    player = current_user
    is_pk = bool(player.in_pk and player.pk_opponent)
    return render_template("shortcuts.html",
                         player=player,
                         DataService=DataService,
                         is_pk=is_pk,
                         opponent=player.pk_opponent if is_pk else None)


@battle_bp.route("/set_shortcut", methods=["POST"])
@login_required
def set_shortcut():
    player = current_user
    shortcuts = player.get_shortcuts()

    # 技能技键校验：只允许 普攻(attack) 或 本职业已学习的主动技能
    learned = set(player.learned_skills)
    def _valid_skill(skill_id):
        if skill_id == 'attack':
            return True
        if skill_id not in learned:
            return False
        sd = DataService.get_skill(skill_id)
        if not sd or sd.get('skill_type') != 'active':
            return False
        cls_req = sd.get('class_required')
        if cls_req and cls_req != player.player_class:
            return False
        return True

    for slot in ['skill1', 'skill2', 'skill3', 'skill4']:
        sid = request.form.get(slot, 'attack')
        shortcuts[slot] = sid if _valid_skill(sid) else 'attack'

    potion1 = request.form.get('potion1')
    potion2 = request.form.get('potion2')
    shortcuts['potion1'] = potion1 if (potion1 and DataService.get_inventory_item(player.id, potion1)) else None
    shortcuts['potion2'] = potion2 if (potion2 and DataService.get_inventory_item(player.id, potion2)) else None

    player.set_shortcuts(shortcuts)
    db.session.commit()
    if player.in_battlefield:
        return redirect(url_for('battlefield.city_view'))
    if player.in_pk and player.pk_opponent:
        return redirect(url_for('battle.pk_battle', opponent=player.pk_opponent))
    return redirect(url_for('battle.battle'))


# --- PK ---

@battle_bp.route("/start_pk/<username>", methods=["GET", "POST"])
@login_required
def start_pk(username):
    player = current_user
    target = DataService.get_player_by_username(username)
    if not target:
        flash("找不到目标玩家")
        return redirect(url_for('game.scene'))

    if target.health <= 0:
        flash("对方处于死亡状态")
        return redirect(url_for('player.view_player', username=username))

    if target.in_battle or target.in_pk:
        flash("对方正在战斗中")
        return redirect(url_for('player.view_player', username=username))

    if player.current_location != target.current_location:
        flash("需要同一场景才能PK")
        return redirect(url_for('player.view_player', username=username))

    success, error = BattleService.start_pk(player, target)
    if not success:
        flash(error)
        return redirect(url_for('player.view_player', username=username))

    return redirect(url_for('battle.pk_battle', opponent=username))


@battle_bp.route("/pk_battle/<opponent>")
@login_required
def pk_battle(opponent):
    player = current_user
    opponent_player = DataService.get_player_by_username(opponent)
    if not opponent_player:
        flash("对方玩家未找到")
        return redirect(url_for('game.scene'))

    if not opponent_player.in_pk or not player.in_pk:
        flash("PK已结束")
        return redirect(url_for('game.scene'))

    # PK可用药品：背包中可使用的回血/回蓝药品（非战场专用）
    pk_potions = []
    for inv in DataService.get_inventory(player.id):
        it = DataService.get_item(inv.item_id)
        if (it and it.get('is_usable', True) and not it.get('battlefield_item')
                and it.get('type') == 'potion' and inv.quantity > 0):
            pk_potions.append({'item_id': inv.item_id,
                               'name': it.get('name', inv.item_id),
                               'quantity': inv.quantity})

    # 技能数据（供技能按钮使用）
    from models.player import PlayerSkill
    skills = DataService.get_skills()
    player_skills = {ps.skill_id: ps for ps in PlayerSkill.query.filter_by(player_id=player.id).all()}

    # 副将
    from models.lieutenant import Lieutenant
    lieutenant = Lieutenant.query.filter_by(owner_id=player.id, is_deployed=True).first()
    target_lieutenant = Lieutenant.query.filter_by(owner_id=opponent_player.id, is_deployed=True, is_alive=True).first()

    remaining = request.args.get('remaining', None)
    return render_template("battle.html",
                         player=player,
                         monster=opponent_player,
                         is_pk=True,
                         remaining=remaining,
                         lieutenant=lieutenant,
                         DataService=DataService,
                         participants=0,
                         now=datetime.now(),
                         pk_potions=pk_potions,
                         skills=skills,
                         player_skills=player_skills,
                         target_lieutenant=target_lieutenant)


@battle_bp.route("/pk_fight", methods=["POST"])
@login_required
def pk_fight():
    player = current_user
    if not player.in_pk or not player.pk_opponent:
        return redirect(url_for('game.scene'))

    opponent = DataService.get_player_by_username(player.pk_opponent)
    if not opponent:
        player.in_pk = False
        player.pk_opponent = None
        db.session.commit()
        flash("对方玩家数据未找到")
        return redirect(url_for('game.scene'))

    if player.health <= 1:
        flash("你已被击败")
        return redirect(url_for('battle.revive'))

    if opponent.health <= 1:
        result = f"你击败了{opponent.nickname}！"
        player.last_battle_result = result
        BattleService._end_pk(player, opponent)
        db.session.commit()
        return redirect(url_for('battle.battle_result'))

    current_time = time.time()
    if current_time - player.last_attack_time < 2:
        remaining = 2 - (current_time - player.last_attack_time)
        return redirect(url_for('battle.pk_battle',
                               opponent=opponent.username,
                               remaining=remaining))

    action = request.form.get("action")
    player.last_attack_time = current_time

    if action == "attack":
        result, error = BattleService.pk_attack(player, opponent)
    else:
        result, error = BattleService.pk_use_skill(player, opponent, action)

    if result:
        player.last_battle_result = result
        return redirect(url_for('battle.battle_result'))

    if error:
        flash(error)
        return redirect(url_for('battle.pk_battle', opponent=opponent.username))

    return redirect(url_for('battle.pk_battle', opponent=opponent.username))


@battle_bp.route("/pk_use_skill/<opponent>/<skill_id>")
@login_required
def pk_use_skill(opponent, skill_id):
    """GET 版 PK 技能释放（供战斗界面技键链接调用）。"""
    player = current_user
    if not player.in_pk or player.pk_opponent != opponent:
        return redirect(url_for('game.scene'))

    target = DataService.get_player_by_username(opponent)
    if not target:
        player.in_pk = False
        player.pk_opponent = None
        db.session.commit()
        flash("对方玩家数据未找到")
        return redirect(url_for('game.scene'))

    if player.health <= 1:
        flash("你已被击败")
        return redirect(url_for('battle.revive'))

    if target.health <= 1:
        result = f"你击败了{target.nickname}！"
        player.last_battle_result = result
        BattleService._end_pk(player, target)
        db.session.commit()
        return redirect(url_for('battle.battle_result'))

    current_time = time.time()
    if current_time - player.last_attack_time < 2:
        remaining = 2 - (current_time - player.last_attack_time)
        return redirect(url_for('battle.pk_battle',
                               opponent=opponent, remaining=remaining))

    player.last_attack_time = current_time

    if skill_id == "attack":
        result, error = BattleService.pk_attack(player, target)
    else:
        result, error = BattleService.pk_use_skill(player, target, skill_id)

    if result:
        player.last_battle_result = result
        return redirect(url_for('battle.battle_result'))

    if error:
        flash(error)
    return redirect(url_for('battle.pk_battle', opponent=opponent))


@battle_bp.route("/pk_use_potion/<opponent>/<item_id>")
@login_required
def pk_use_potion(opponent, item_id):
    """GET 版 PK 使用药品（供战斗界面药键链接调用）。"""
    player = current_user
    if not player.in_pk or player.pk_opponent != opponent:
        return redirect(url_for('game.scene'))

    target = DataService.get_player_by_username(opponent)
    if not target:
        player.in_pk = False
        player.pk_opponent = None
        db.session.commit()
        flash("对方玩家数据未找到")
        return redirect(url_for('game.scene'))

    current_time = time.time()
    if current_time - player.last_attack_time < 2:
        remaining = 2 - (current_time - player.last_attack_time)
        return redirect(url_for('battle.pk_battle',
                               opponent=opponent, remaining=remaining))

    player.last_attack_time = current_time
    result, error = BattleService.pk_use_potion(player, item_id)

    if result:
        player.last_battle_result = result
        return redirect(url_for('battle.battle_result'))

    if error:
        flash(error)
    return redirect(url_for('battle.pk_battle', opponent=opponent))