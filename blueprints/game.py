from flask import Blueprint, render_template, redirect, url_for, session
from datetime import datetime
from models.location import Location
from models.item import Item
from models.monster import Monster
from services.data_service import DataService
from services.game_service import GameService
from utils.decorators import login_required, check_health_status, check_pk_status
from services.public_chat import list_latest

game_bp = Blueprint('game', __name__)

@game_bp.route("/scene")
@login_required
@check_health_status
@check_pk_status
def scene():
    player = DataService.get_current_player(session)
    if not player:
        return redirect(url_for("auth.login_page"))
    
    # Reset battle status
    player.in_battle = False
    player.in_pk = False
    player.pk_opponent = None
    
    # Handle chat message refresh
    if player.last_chat_message:
        player.chat_refresh_count += 1
        if player.chat_refresh_count >= 3:
            player.last_chat_message = None
            player.chat_refresh_count = 0
        DataService.save_player_data(session["username"], player)
        
    locations = Location.get_locations()
    current_location = locations[player.current_location]
    current_location.refresh_ground_items()

    current_monster = GameService.get_current_monster()
    if not current_monster or current_monster.monster_id != current_location.monster_type:
        GameService.generate_new_monster(player)
        current_monster = GameService.get_current_monster()
    
    if current_monster and current_monster.immortal:
        current_monster.reset_health()
    
    other_players = DataService.get_all_players_in_location(
        player.current_location, 
        session["username"]
    )
    
    DataService.save_player_data(session["username"], player)
    
    public_messages = list_latest(10)
    return render_template("scene.html", 
                         player=player, 
                         monster=current_monster,
                         location=current_location,
                         locations=locations,
                         other_players=other_players,
                         Item=Item,
                         public_messages=public_messages,
                         now=datetime.now())

@game_bp.route("/move/<direction>")
@login_required
@check_health_status
@check_pk_status
def move(direction):
    player = DataService.get_current_player(session)
    locations = Location.get_locations()
    current_loc = locations[player.current_location]
    
    direction_mapping = {
        "north": "north_exit",
        "south": "south_exit",
        "east": "east_exit",
        "west": "west_exit"
    }
    
    exit_attr = direction_mapping.get(direction)
    if exit_attr and getattr(current_loc, exit_attr):
        new_location = getattr(current_loc, exit_attr)
        player.current_location = new_location
        GameService.generate_new_monster(player)
        DataService.save_player_data(session["username"], player)
    return redirect(url_for("game.scene"))

@game_bp.route("/pickup/<item_id>")
@login_required
@check_health_status
@check_pk_status
def pickup_item(item_id):
    player = DataService.get_current_player(session)
    locations = Location.get_locations()
    current_location = locations[player.current_location]
    
    if item_id in current_location.ground_items:
        player.add_item(item_id)
        current_location.ground_items.remove(item_id)
        DataService.save_player_data(session["username"], player)
    return redirect(url_for("game.scene"))

@game_bp.route("/npc/<monster_id>")
@login_required
@check_health_status
@check_pk_status
def view_npc(monster_id):
    player = DataService.get_current_player(session)
    monster = Monster.create_monster(monster_id)
    
    if not monster or monster.killable:
        return redirect(url_for("game.scene"))
        
    # 如果是技能教官,显示技能学习界面
    if monster_id == "monster_village_trainer":
        from models.skill import Skill
        skills = Skill.load_skills()
        return render_template("skill_hall.html", 
                             player=player,
                             monster=monster,
                             skills=skills)
                             
    # 其他NPC的查看界面
    return render_template("view_npc.html",
                         player=player, 
                         monster=monster)