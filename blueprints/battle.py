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

    referrer = request.referrer
    if referrer and 'scene' in referrer:
        player.last_action = ""
        player.last_damage_dealt = ""
        player.last_damage_taken = 0
        player.last_mana_cost = 0
        player.last_skill = ""
        monster.last_action = ""
        monster.last_damage_dealt = ""
        monster.last_damage_taken = 0
        monster.last_skill = ""

    return render_template("battle.html",
                         player=player,
                         monster=monster,
                         lieutenant=Lieutenant.query.filter_by(owner_id=player.id, is_deployed=True).first(),
                         DataService=DataService,
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
            ItemService.use_item(player, item_id)
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

    # Weak revive - lose 10% experience
    lost_exp = 0
    if player.experience > 0:
        lost_exp = max(0, int(player.experience * 0.1))
        player.experience -= lost_exp
    player.health = max(10, PlayerService.get_max_health(player) // 10)
    player.mana = max(5, PlayerService.get_max_mana(player) // 10)
    player.in_battle = False
    player.current_encounter = None
    player.need_revive = False
    killed_by = player.killed_by
    player.killed_by = None
    db.session.commit()
    msg = "虚弱复活成功，生命值恢复到10%！"
    if lost_exp > 0:
        msg += f" 损失了 {lost_exp} 经验"
    if killed_by:
        msg += f" 你被{killed_by}击杀了。"
    return render_template("revive_result.html", revive_message=msg)


@battle_bp.route("/battle_result")
@login_required
def battle_result():
    player = current_user
    result = player.last_battle_result
    lost_exp = 0

    if not player.in_pk and player.health <= 1 and player.experience > 0:
        lost_exp = max(0, int(player.experience * 0.1))
        player.experience -= lost_exp

    is_pk = player.in_pk
    db.session.commit()
    return render_template("battle_result.html",
                       result=result,
                       lost_experience=lost_exp,
                       is_pk=is_pk)


@battle_bp.route("/continue_battle")
@login_required
def continue_battle():
    player = current_user
    monster, error = BattleService.start_pve(player)
    if not monster:
        flash(error or "这里没有怪物")
        return redirect(url_for("game.scene"))
    return redirect(url_for("battle.battle"))


@battle_bp.route("/flee")
@login_required
def flee():
    player = current_user
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
    return render_template("shortcuts.html",
                         player=current_user,
                         DataService=DataService)


@battle_bp.route("/set_shortcut", methods=["POST"])
@login_required
def set_shortcut():
    player = current_user
    shortcuts = player.get_shortcuts()
    shortcuts['skill1'] = request.form.get('skill1', 'attack')
    shortcuts['skill2'] = request.form.get('skill2', 'attack')
    shortcuts['skill3'] = request.form.get('skill3', 'attack')
    shortcuts['skill4'] = request.form.get('skill4', 'attack')

    potion1 = request.form.get('potion1')
    potion2 = request.form.get('potion2')
    shortcuts['potion1'] = potion1 if (potion1 and DataService.get_inventory_item(player.id, potion1)) else None
    shortcuts['potion2'] = potion2 if (potion2 and DataService.get_inventory_item(player.id, potion2)) else None

    player.set_shortcuts(shortcuts)
    db.session.commit()
    return redirect(url_for('battle.battle'))


# --- PK ---

@battle_bp.route("/start_pk/<username>", methods=["POST"])
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

    remaining = request.args.get('remaining', None)
    return render_template("battle.html",
                         player=player,
                         monster=opponent_player,
                         is_pk=True,
                         remaining=remaining,
                         now=datetime.now())


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