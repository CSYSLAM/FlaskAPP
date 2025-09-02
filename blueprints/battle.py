import time
from flask import Blueprint, render_template, redirect, url_for, request, session, flash
from datetime import datetime
from models.player import Player
from services.data_service import DataService
from services.game_service import GameService
from utils.decorators import login_required, check_health_status, check_pk_status

battle_bp = Blueprint('battle', __name__)

@battle_bp.route("/battle")
@login_required
@check_health_status
@check_pk_status
def battle():
    player = DataService.get_current_player(session)
    current_monster = GameService.get_current_monster()
    
    # 检查怪物是否可以战斗
    if not current_monster or not current_monster.killable:
        if current_monster:
            return redirect(url_for("game.view_npc", monster_id=current_monster.monster_id))
        return redirect(url_for("game.scene"))
    
    # Only reset battle information if coming from scene
    referrer = request.referrer
    if referrer and 'scene' in referrer:
        player.last_action = None
        player.last_damage_dealt = None
        player.last_damage_taken = None
        player.last_mana_cost = None
        player.last_skill = None
        
        current_monster.last_action = None
        current_monster.last_damage_dealt = None
        current_monster.last_damage_taken = None
        current_monster.last_skill = None
        
    # Set battle status
    player.in_battle = True
    DataService.save_player_data(session["username"], player)
    
    return render_template("battle.html", 
                         player=player, 
                         monster=current_monster,
                         now=datetime.now())

@battle_bp.route("/fight", methods=["POST"])
@login_required
@check_health_status
@check_pk_status
def fight():
    player = DataService.get_current_player(session)
    current_monster = GameService.get_current_monster()
    action = request.form.get("action")
    
    if action == "attack":
        player.attack_monster(current_monster)
    elif action.startswith("use:"):
        item_id = action.split(":")[1]
        if item_id:
            player.use_item(item_id)
    else:  # This is a skill action
        player.use_skill(current_monster, action)

    if current_monster.health <= 0:
        GameService.handle_monster_defeat(player)
        DataService.save_player_data(session["username"], player)
        return redirect(url_for("battle.battle_result"))
    
    current_monster.attack_player(player)
    
    if player.health <= 0:
        player.last_battle_result = f"你被{current_monster.name}打败了"
        DataService.save_player_data(session["username"], player)
        return redirect(url_for("battle.revive"))

    DataService.save_player_data(session["username"], player)
    return redirect(url_for("battle.battle"))

@battle_bp.route("/revive")
@login_required
def revive():
    player = DataService.get_current_player(session)
    has_revive_item = ("potion_revive" in player.inventory and 
                      player.inventory["potion_revive"]["quantity"] > 0)
    return render_template("revive.html", player=player, has_revive_item=has_revive_item)

@battle_bp.route("/revive_action/<method>")
@login_required
def revive_action(method):
    player = DataService.get_current_player(session)
    
    if method == "item":
        if ("potion_revive" in player.inventory and 
            player.inventory["potion_revive"]["quantity"] > 0):
            player.use_revive_item()
            DataService.save_player_data(session["username"], player)
            return render_template("revive_result.html", 
                                revive_message="使用续命灯复活成功，生命值已满！")
        else:
            return render_template("revive.html", 
                                player=player, 
                                revive_message="缺少一个续命灯，无法满血复活！")

    elif method == "weak":
        player.weak_revive()
        DataService.save_player_data(session["username"], player)
        return render_template("revive_result.html", 
                            revive_message="虚弱复活成功，生命值恢复到10%！")

@battle_bp.route("/battle_result")
@login_required
@check_health_status
def battle_result():
    player = DataService.get_current_player(session)
    result = player.last_battle_result
    lost_experience = 0
    
    if not player.pk_opponent and player.health <= 0 and player.experience > 0:
        lost_experience = max(0, int(player.experience * 0.1))
        player.experience -= lost_experience
    
    is_pk = player.pk_opponent is not None
    winner = None
    loser = None
    
    if is_pk:
        opponent_data = DataService.load_player_data(player.pk_opponent)
        if opponent_data:
            if player.health > 0:
                winner = player
                loser = Player.from_dict(opponent_data)
            else:
                winner = Player.from_dict(opponent_data)
                loser = player
    else:
        winner = player.health > 0

    DataService.save_player_data(session["username"], player)

    return render_template("battle_result.html", 
                       result=result, 
                       lost_experience=lost_experience,
                       is_pk=is_pk,
                       winner=winner,
                       loser=loser)

@battle_bp.route("/continue_battle")
@login_required
def continue_battle():
    player = DataService.get_current_player(session)
    GameService.generate_new_monster(player)
    return redirect(url_for("battle.battle"))

@battle_bp.route("/shortcuts")
@login_required
def shortcuts():
    player = DataService.get_current_player(session)
    return render_template("shortcuts.html", player=player)

@battle_bp.route("/set_shortcut", methods=["POST"])
@login_required
def set_shortcut():
    player = DataService.get_current_player(session)
    # Initialize shortcuts if not exists
    if not hasattr(player, 'shortcuts'):
        player.shortcuts = {
            'skill1': 'attack',
            'skill2': 'attack',
            'skill3': 'attack',
            'skill4': 'attack',
            'potion1': None,
            'potion2': None
        }
    
    # Update shortcuts from form data
    player.shortcuts['skill1'] = request.form.get('skill1', 'attack')
    player.shortcuts['skill2'] = request.form.get('skill2', 'attack')
    player.shortcuts['skill3'] = request.form.get('skill3', 'attack')
    player.shortcuts['skill4'] = request.form.get('skill4', 'attack')
    
    # Check if potions still exist in inventory before setting shortcuts
    potion1 = request.form.get('potion1')
    potion2 = request.form.get('potion2')
    
    if potion1 and potion1 in player.inventory:
        player.shortcuts['potion1'] = potion1
    else:
        player.shortcuts['potion1'] = None
        
    if potion2 and potion2 in player.inventory:
        player.shortcuts['potion2'] = potion2
    else:
        player.shortcuts['potion2'] = None
    
    DataService.save_player_data(session["username"], player)
    return redirect(url_for('battle.battle'))

# PK相关路由
@battle_bp.route("/start_pk/<username>", methods=["POST"])
@login_required
@check_health_status
@check_pk_status
def start_pk(username):
    player = DataService.get_current_player(session)
    target_player_data = DataService.load_player_data(username)
    
    if not target_player_data:
        flash("找不到目标玩家")
        return redirect(url_for('game.scene'))
        
    target_player = Player.from_dict(target_player_data)
    
    # Check conditions
    if target_player.health <= 0:
        flash("对方处于死亡状态，无法发起PK")
        return redirect(url_for('player.view_player', username=username))
        
    if hasattr(target_player, 'in_battle') and target_player.in_battle:
        flash("对方正在战斗中，无法发起PK")
        return redirect(url_for('player.view_player', username=username))
        
    if target_player.in_pk:
        flash("对方正在PK中，无法发起PK")
        return redirect(url_for('player.view_player', username=username))
    
    if player.current_location != target_player.current_location:
        flash("需要在同一场景才能PK")
        return redirect(url_for('player.view_player', username=username))
    
    # Start PK if all conditions are met
    player.in_pk = True
    player.pk_opponent = username
    target_player.in_pk = True
    target_player.pk_opponent = player.username
    
    DataService.save_player_data(session["username"], player)
    DataService.save_player_data(username, target_player)
    
    return redirect(url_for('battle.pk_battle', opponent=username))

@battle_bp.route("/pk_battle/<opponent>")
@login_required
@check_health_status
def pk_battle(opponent):
    player = DataService.get_current_player(session)
    opponent_data = DataService.load_player_data(opponent)
    
    if not opponent_data:
        flash("对方玩家数据未找到")
        return redirect(url_for('game.scene'))
        
    opponent_player = Player.from_dict(opponent_data)
    
    # Check if the opponent is in PK mode
    if not opponent_player.in_pk or not player.in_pk:
        flash("对方已退出PK状态")
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
    player = DataService.get_current_player(session)
    
    # Check if player is actually in PK
    if not player.in_pk or not player.pk_opponent:
        return redirect(url_for('game.scene'))
        
    opponent_data = DataService.load_player_data(player.pk_opponent)
    if not opponent_data:
        player.in_pk = False
        player.pk_opponent = None
        DataService.save_player_data(session["username"], player)
        flash("对方玩家数据未找到，无法继续战斗。")
        return redirect(url_for('game.scene'))
        
    opponent_player = Player.from_dict(opponent_data)
    
    # Check if the player is dead
    if player.health <= 0:
        flash("你已被击败，无法继续战斗。")
        return redirect(url_for('battle.revive'))

    # Check if the opponent is dead
    if opponent_player.health <= 0:
        GameService.handle_pk_victory(player, opponent_player)
        DataService.save_player_data(session["username"], player)
        DataService.save_player_data(opponent_player.username, opponent_player)
        return redirect(url_for('battle.battle_result'))

    current_time = time.time()
    
    # Check if the player is within the cooldown period
    if current_time - player.last_attack_time < 2:
        remaining = 2 - (current_time - player.last_attack_time)
        return redirect(url_for('battle.pk_battle', 
                               opponent=opponent_player.username, 
                               remaining=remaining))
    
    action = request.form.get("action")
    player.last_attack_time = current_time
    
    # Perform the attack
    if action == "attack":
        player.attack_monster(opponent_player)
    else:
        player.use_skill(opponent_player, action)

    # Save the states immediately after attack
    DataService.save_player_data(session["username"], player)
    DataService.save_player_data(opponent_player.username, opponent_player)

    # Check if the opponent died from this attack
    if opponent_player.health <= 0:
        GameService.handle_pk_victory(player, opponent_player)
        DataService.save_player_data(session["username"], player)
        DataService.save_player_data(opponent_player.username, opponent_player)
        return redirect(url_for('battle.battle_result'))

    # Continue battle if opponent is still alive
    return redirect(url_for('battle.pk_battle', opponent=opponent_player.username))