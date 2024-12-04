from flask import Flask, render_template, redirect, url_for, request, session, flash
from models.player import Player
from models.monster import Monster
from models.item import Item
from models.skill import Skill
from models.equipment import Equipment
import json
import time
import random
from functools import wraps
from datetime import datetime
from models.location import Location
from pathlib import Path

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

app.static_folder = '.'

SAVE_DIR = Path("player_data")
SAVE_DIR.mkdir(exist_ok=True)

locations = Location.get_locations()
shop_items = Item.get_shop_items()
current_monster = None  # 保留这个全局变量用于战斗

def save_player_data(username, player):
    file_path = SAVE_DIR / f"{username}.json"
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(player.to_dict(), f, ensure_ascii=False, indent=2)

def load_player_data(username):
    file_path = SAVE_DIR / f"{username}.json"
    if file_path.exists():
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None

def get_current_player():
    if "username" not in session:
        return None
    player_data = load_player_data(session["username"])
    if not player_data:
        return None
    player = Player(player_data["name"], player_data["player_class"])
    if "equipment" in player_data:
        equipment_data = player_data["equipment"]
        player.equipment = {
            slot: Equipment.from_dict(equip_data) if equip_data else None
            for slot, equip_data in equipment_data.items()
        }
    player_data_copy = player_data.copy()
    player_data_copy.pop('equipment', None)
    player.__dict__.update(player_data_copy)
    player.update_stats()
    player.update_military_rank()  # 更新军衔
    player.get_avatar_path()  # 更新头像
    return player

def generate_new_monster(player):
    global current_monster
    current_monster = Monster.create_monster(locations[player.current_location].monster_type)

def handle_monster_defeat(player):
    loot = current_monster.get_loot()
    money = current_monster.get_money_drop()
    loot_name = None
    
    if isinstance(loot, Equipment):
        new_id = f"equipment_{int(time.time())}_{random.randint(1000, 9999)}"
        player.inventory[new_id] = loot.to_dict()
        loot_name = loot.name
    elif loot:  # Handle non-equipment items
        items = Item.load_items()
        if loot in items:
            player.add_item(loot)
            loot_name = items[loot].name
    
    player.money += money
    player.experience += 20
    player.last_battle_result = (
        f"你击败了{current_monster.name}！" +
        (f"获得了{loot_name}，" if loot_name else "这次什么也没掉落，") +
        f"经验增加了20，获得{money}银两。"
    )
    
    generate_new_monster(player)

def handle_pk_victory(winner, loser):
    # 计算金钱掠夺
    money_percent = random.uniform(0.003, 0.013)  # 0.3%-1.3%
    money_gained = int(loser.money * money_percent)
    winner.money += money_gained
    loser.money -= money_gained
    
    # 随机选择一个非绑定物品
    non_bound_items = [
        item_id for item_id, item_data in loser.inventory.items()
        if (item_id.startswith('equipment_') and 
            not Equipment.from_dict(item_data).is_bound)
    ]
    
    lost_item_name = None
    if non_bound_items:  # 移除概率判断,只要有非绑定物品就必定掉落
        item_id = random.choice(non_bound_items)
        lost_item_name = loser.inventory[item_id]["name"]  # 获取物品名称
        winner.inventory[item_id] = loser.inventory[item_id]  # 转移物品给胜利者
        del loser.inventory[item_id]  # 从失败者背包移除
        
    # 更新战斗结果
    winner.last_battle_result = f"你击败了{loser.name}！获得了{money_gained}银两"
    if lost_item_name:
        winner.last_battle_result += f"，获得了 {lost_item_name}"
    
    loser.last_battle_result = f"你被{winner.name}击败了，损失了{money_gained}银两"
    if lost_item_name:
        loser.last_battle_result += f"，失去了 {lost_item_name}"
    
    # 重置PK状态
    winner.in_pk = False
    winner.pk_opponent = None
    loser.in_pk = False
    loser.pk_opponent = None
    
    save_player_data(winner.username, winner)
    save_player_data(loser.username, loser)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated_function

def check_pk_status(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        player = get_current_player()
        if player.in_pk:
            return redirect(url_for('pk_battle', opponent=player.pk_opponent))
        return f(*args, **kwargs)
    return decorated_function

def check_health_status(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        player = get_current_player()
        if player and player.health <= 0:
            return redirect(url_for("revive"))
        return f(*args, **kwargs)
    return decorated_function

#####  auth start 处理登录和注册相关功能#####
@app.route("/")
def index():
    if "username" in session:
        return redirect(url_for("scene"))
    return redirect(url_for("login_page"))

@app.route("/login", methods=["GET", "POST"])
@check_health_status
def login_page():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        
        player_data = load_player_data(username)
        if player_data and player_data.get("password") == password:
            session["username"] = username
            return redirect(url_for("scene"))
        return render_template("login.html", message="账号或密码错误")
    return render_template("login.html")

@app.route("/register", methods=["POST"])
def register():
    username = request.form.get("username")
    password = request.form.get("password")
    nickname = request.form.get("nickname")
    player_class = request.form.get("player_class")
    
    if load_player_data(username):
        return render_template("login.html", message="账号已存在")
    
    if player_class not in Player.CLASSES:
        return render_template("login.html", message="无效的职业选择")
    
    gender = request.form.get("gender")
    player = Player(nickname, player_class)
    player.username = username
    player.password = password
    player.gender = gender
    player.current_location = "outdoor.village"
    
    save_player_data(username, player)
    session["username"] = username
    return redirect(url_for("scene"))

@app.route("/logout")
def logout():
    if "username" in session:
        session.pop("username", None)
    return redirect(url_for("login_page"))

####   NPC相关逻辑#####
@app.route("/npc/<monster_id>")
@login_required
@check_health_status
@check_pk_status
def view_npc(monster_id):
    player = get_current_player()
    monster = Monster.create_monster(monster_id)
    
    if not monster or monster.killable:
        return redirect(url_for("scene"))
        
    # 如果是技能教官,显示技能学习界面
    if monster_id == "monster_village_trainer":
        skills = Skill.load_skills()  # 加载所有技能
        return render_template("skill_hall.html", 
                             player=player,
                             monster=monster,
                             skills=skills)  # 传入skills变量
                             
    # 其他NPC的查看界面
    return render_template("view_npc.html",
                         player=player, 
                         monster=monster)

#####  battle start 战斗相关逻辑#####
@app.route("/battle")
@login_required
@check_health_status
@check_pk_status
def battle():
    player = get_current_player()
    # 检查怪物是否可以战斗
    if not current_monster.killable:
        return redirect(url_for("view_npc", monster_id=current_monster.monster_id))
    # Only reset battle information if coming from scene (not during battle)
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
    save_player_data(session["username"], player)
    
    return render_template("battle.html", 
                         player=player, 
                         monster=current_monster,
                         now=datetime.now())

@app.route("/fight", methods=["POST"])
@login_required
@check_health_status
@check_pk_status
def fight():
    player = get_current_player()
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
        handle_monster_defeat(player)
        save_player_data(session["username"], player)
        return redirect(url_for("battle_result"))
    
    current_monster.attack_player(player)
    
    if player.health <= 0:
        player.last_battle_result = f"你被{current_monster.name}打败了"
        save_player_data(session["username"], player)
        return redirect(url_for("revive"))

    save_player_data(session["username"], player)
    return redirect(url_for("battle"))

@app.route("/revive")
@login_required
def revive():
    player = get_current_player()
    has_revive_item = "续命灯" in player.inventory and player.inventory["续命灯"]["quantity"] > 0
    return render_template("revive.html", player=player, has_revive_item=has_revive_item)

@app.route("/revive_action/<method>")
@login_required
def revive_action(method):
    player = get_current_player()
    
    if method == "item":
        # Check if the player has the revive item
        if "potion_revive" in player.inventory and player.inventory["potion_revive"]["quantity"] > 0:
            player.use_revive_item()  # This method should handle the revival logic
            save_player_data(session["username"], player)
            return render_template("revive_result.html", 
                                revive_message="使用续命灯复活成功，生命值已满！")
        else:
            return render_template("revive.html", 
                                player=player, 
                                revive_message="缺少一个续命灯，无法满血复活！")

    elif method == "weak":
        player.weak_revive()
        save_player_data(session["username"], player)
        return render_template("revive_result.html", 
                            revive_message="虚弱复活成功，生命值恢复到10%！")

@app.route("/shortcuts")
@login_required
def shortcuts():
    player = get_current_player()
    return render_template("shortcuts.html", player=player)

@app.route("/set_shortcut", methods=["POST"])
@login_required
def set_shortcut():
    player = get_current_player()
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
    
    save_player_data(session["username"], player)
    return redirect(url_for('battle'))

@app.route("/continue_battle")
@login_required
def continue_battle():
    player = get_current_player()
    generate_new_monster(player)
    return redirect(url_for("battle"))

#####  PK start 战斗相关逻辑#####
@app.route("/battle_result")
@login_required
@check_health_status
def battle_result():
    player = get_current_player()
    result = player.last_battle_result
    lost_experience = 0
    
    if not player.pk_opponent and player.health <= 0 and player.experience > 0:
        lost_experience = max(0, int(player.experience * 0.1))
        player.experience -= lost_experience
    
    is_pk = player.pk_opponent is not None
    winner = None
    loser = None
    
    if is_pk:
        opponent_data = load_player_data(player.pk_opponent)
        if opponent_data:
            if player.health > 0:
                winner = player
                loser = Player.from_dict(opponent_data)
            else:
                winner = Player.from_dict(opponent_data)
                loser = player
    else:
        winner = player.health > 0

    save_player_data(session["username"], player)

    return render_template("battle_result.html", 
                       result=result, 
                       lost_experience=lost_experience,
                       is_pk=is_pk,
                       winner=winner,
                       loser=loser)

@app.route("/start_pk/<username>", methods=["POST"])
@login_required
@check_health_status
@check_pk_status
def start_pk(username):
    player = get_current_player()
    target_player = Player.from_dict(load_player_data(username))
    
    # Check conditions
    if not target_player:
        flash("找不到目标玩家")
        return redirect(url_for('scene'))
        
    # Check if target player is alive
    if target_player.health <= 0:
        flash("对方处于死亡状态，无法发起PK")
        return redirect(url_for('view_player', username=username))
        
    # Check if target player is in battle
    if hasattr(target_player, 'in_battle') and target_player.in_battle:
        flash("对方正在战斗中，无法发起PK")
        return redirect(url_for('view_player', username=username))
        
    # Check if target player is already in PK
    if target_player.in_pk:
        flash("对方正在PK中，无法发起PK")
        return redirect(url_for('view_player', username=username))
    
    # Check if players are in the same location
    if player.current_location != target_player.current_location:
        flash("需要在同一场景才能PK")
        return redirect(url_for('view_player', username=username))
    
    # Start PK if all conditions are met
    player.in_pk = True
    player.pk_opponent = username
    target_player.in_pk = True
    target_player.pk_opponent = player.username
    
    save_player_data(session["username"], player)
    save_player_data(username, target_player)
    
    return redirect(url_for('pk_battle', opponent=username))

@app.route("/pk_battle/<opponent>")
@login_required
@check_health_status
def pk_battle(opponent):
    player = get_current_player()
    opponent_player = Player.from_dict(load_player_data(opponent))
    
    # Check if the opponent is in PK mode
    if not opponent_player.in_pk or not player.in_pk:
        flash("对方已退出PK状态")
        return redirect(url_for('scene'))
    
    remaining = request.args.get('remaining', None)  # Get remaining time if exists
    return render_template("battle.html", 
                         player=player, 
                         monster=opponent_player,  # Use opponent as monster
                         is_pk=True,
                         remaining=remaining,  # Pass remaining time
                         now=datetime.now())

@app.route("/pk_fight", methods=["POST"])
@login_required
def pk_fight():
    player = get_current_player()
    
    # Check if player is actually in PK
    if not player.in_pk or not player.pk_opponent:
        return redirect(url_for('scene'))
        
    opponent_data = load_player_data(player.pk_opponent)
    if not opponent_data:
        # Reset player's PK state if opponent data is not found
        player.in_pk = False
        player.pk_opponent = None
        save_player_data(session["username"], player)
        flash("对方玩家数据未找到，无法继续战斗。")
        return redirect(url_for('scene'))
        
    opponent = Player.from_dict(opponent_data)
    
    # Check if the player is dead
    if player.health <= 0:
        flash("你已被击败，无法继续战斗。")
        return redirect(url_for('revive'))

    # Check if the opponent is dead
    if opponent.health <= 0:
        handle_pk_victory(player, opponent)
        save_player_data(session["username"], player)
        save_player_data(opponent.username, opponent)
        return redirect(url_for('battle_result'))

    current_time = time.time()
    
    # Check if the player is within the cooldown period
    if current_time - player.last_attack_time < 2:
        remaining = 2 - (current_time - player.last_attack_time)
        return redirect(url_for('pk_battle', opponent=opponent.username, remaining=remaining))
    
    action = request.form.get("action")
    player.last_attack_time = current_time
    
    # Perform the attack
    if action == "attack":
        player.attack_monster(opponent)
    else:
        player.use_skill(opponent, action)

    # Save the states immediately after attack
    save_player_data(session["username"], player)
    save_player_data(opponent.username, opponent)

    # Check if the opponent died from this attack
    if opponent.health <= 0:
        handle_pk_victory(player, opponent)
        save_player_data(session["username"], player)
        save_player_data(opponent.username, opponent)
        return redirect(url_for('battle_result'))

    # Continue battle if opponent is still alive
    return redirect(url_for('pk_battle', opponent=opponent.username))

#####  player start  玩家功能（查看角色、物品管理等）#####
@app.route("/bulk_use/<item_id>", methods=["POST"])
@login_required
@check_health_status
def bulk_use_item(item_id):
    player = get_current_player()
    if item_id not in player.inventory:
        return redirect(url_for('inventory'))
        
    quantity = int(request.form.get('quantity', 1))
    item_data = player.inventory[item_id]
    
    if quantity > item_data["quantity"]:
        quantity = item_data["quantity"]
    
    # 批量使用物品
    success_count = 0
    for _ in range(quantity):
        if player.use_item(item_id):
            success_count += 1
    
    # 确保更新军衔
    player.update_military_rank()
    save_player_data(session["username"], player)
    
    flash(f"成功使用{success_count}个{item_data['item']['name']}")
    
    if item_id in player.inventory:
        return redirect(url_for('view_item', item_id=item_id))
    return redirect(url_for('inventory'))


@app.route("/equip/<item_id>")
@login_required
@check_pk_status
@check_health_status
def equip_item(item_id):
    player = get_current_player()
    if item_id in player.inventory:
        equipment_dict = player.inventory[item_id]
        equipment = Equipment.from_dict(equipment_dict)
        
        # 检查职业要求
        if equipment.class_required and equipment.class_required != player.player_class:
            player.item_effect = f"需要{equipment.class_required}职业才能装备"
            save_player_data(session["username"], player)
            return redirect(url_for('inventory'))
            
        # 检查等级要求
        if equipment.level_required > player.level:
            player.item_effect = f"需要等级{equipment.level_required}才能装备"
            save_player_data(session["username"], player)
            return redirect(url_for('inventory'))
            
        # 如果通过检查才进行装备
        old_equipment = player.equip(equipment)
        del player.inventory[item_id]
        if old_equipment:
            # 使用时间戳和随机数生成唯一ID
            new_id = f"equipment_{int(time.time())}_{random.randint(1000, 9999)}"
            player.inventory[new_id] = old_equipment.to_dict() if isinstance(old_equipment, Equipment) else old_equipment
        save_player_data(session["username"], player)
    return redirect(url_for('inventory'))

@app.route("/unequip/<slot>")
@login_required
@check_health_status
@check_pk_status
def unequip(slot):
    player = get_current_player()
    equipment = player.unequip(slot)
    if equipment:
        new_id = f"equipment_{int(time.time())}_{random.randint(1000, 9999)}"
        player.inventory[new_id] = equipment
        save_player_data(session["username"], player)
    return redirect(url_for('character'))

@app.route("/character")
@login_required
@check_health_status
@check_pk_status
def character():
    player = get_current_player()
    player.update_stats()  # 添加这行来更新属性
    can_level_up = player.experience >= player.exp_to_next_level
    return render_template("character.html", 
                         player=player, 
                         can_level_up=can_level_up,
                         Equipment=Equipment)

@app.route("/equipment_list")
@login_required
@check_health_status
@check_pk_status
def equipment_list():
    player = get_current_player()
    return render_template("equipment_list.html", 
                         player=player,
                         Equipment=Equipment)

@app.route("/view_equipped/<slot>")
@login_required
@check_health_status
@check_pk_status
def view_equipped(slot):
    player = get_current_player()
    if slot in player.equipment and player.equipment[slot]:
        equipment = player.equipment[slot]
        return render_template('equipment_view.html', 
                             equipment=equipment, 
                             item_id=f'equipped_{slot}',
                             Equipment=Equipment)
    return redirect(url_for('equipment_list'))

@app.route("/military_ranks")
@login_required
@check_health_status
def military_ranks():
    player = get_current_player()
    return render_template("military_ranks.html", player=player)

@app.route("/level_up")
@login_required
@check_health_status
@check_pk_status
def level_up():
    player = get_current_player()
    if player.level_up():
        save_player_data(session["username"], player)
    return redirect(url_for("character"))

@app.route("/view_player/<username>")
@login_required
@check_health_status
@check_pk_status
def view_player(username):
    player = get_current_player()  # Get current player
    target_player_data = load_player_data(username)
    if not target_player_data:
        return redirect(url_for("scene"))
        
    target_player = Player(target_player_data["name"], target_player_data["player_class"])
    if "equipment" in target_player_data:
        equipment_data = target_player_data["equipment"]
        target_player.equipment = {
            slot: Equipment.from_dict(equip_data) if equip_data else None
            for slot, equip_data in equipment_data.items()
        }
    target_player_data_copy = target_player_data.copy()
    target_player_data_copy.pop('equipment', None)
    target_player.__dict__.update(target_player_data_copy)
    target_player.update_stats()
    
    return render_template("view_player.html", 
                         player=player,  # Add this line
                         target_player=target_player,
                         Equipment=Equipment)

#####  shop start # 商店功能#####
@app.route("/shop")
@login_required
@check_health_status
@check_pk_status
def shop():
    player = get_current_player()
    return render_template("shop.html", player=player, shop_items=shop_items)

@app.route("/buy_item", methods=["POST"])
@login_required
@check_health_status
@check_pk_status
def buy_item():
    player = get_current_player()
    item_id = request.form.get("item_id")
    quantity = request.form.get("quantity", type=int)
    
    shop_items = Item.get_shop_items()
    if item_id not in shop_items:
        return render_template("shop.html", 
                             player=player, 
                             shop_items=shop_items,
                             message="物品不存在", 
                             success=False)
    
    item = shop_items[item_id]
    total_cost = item.price * quantity
    
    if quantity <= 0:
        return render_template("shop.html", 
                             player=player, 
                             shop_items=shop_items,
                             message="购买数量必须大于0", 
                             success=False)
    
    if player.money < total_cost:
        return render_template("shop.html", 
                             player=player, 
                             shop_items=shop_items,
                             message="余额不足", 
                             success=False)
    
    player.money -= total_cost
    for _ in range(quantity):
        player.add_item(item_id)
    
    save_player_data(session["username"], player)
    
    return render_template("shop.html", 
                         player=player, 
                         shop_items=shop_items,
                         message=f"成功购买{quantity}个{item.name}，花费{total_cost}银两", 
                         success=True)

#####  inventory start 背包管理#####
@app.route("/inventory")
@login_required
@check_health_status
@check_pk_status
def inventory():
    player = get_current_player()
    return render_template("inventory.html", player=player)

@app.route("/use_item/<item>")
@login_required
@check_health_status
@check_pk_status
def use_item(item):
    player = get_current_player()
    if item in player.inventory:
        player.use_item(item)
        save_player_data(session["username"], player)
    return redirect(url_for("inventory"))

@app.route("/sell/<item_id>")
@login_required
def sell_item(item_id):
    player = get_current_player()
    if item_id in player.inventory:
        equipment_data = player.inventory[item_id]
        if isinstance(equipment_data, dict):
            equipment = Equipment.from_dict(equipment_data)
            rarity_values = {
                "普通": 100,
                "精良": 300,
                "卓越": 600,
                "史诗": 1000,
                "神器": 2000
            }
            sell_price = rarity_values[equipment.rarity] * equipment.stars
            player.money += sell_price
            del player.inventory[item_id]
            save_player_data(session["username"], player)
    return redirect(url_for('inventory'))

@app.route("/view_item/<item_id>")
@login_required
@check_health_status
@check_pk_status
def view_item(item_id):
    player = get_current_player()
    if item_id in player.inventory:
        item_data = player.inventory[item_id]
        if item_id.startswith('equipment_'):
            return render_template('equipment_view.html', 
                                 equipment=item_data,
                                 item_id=item_id,
                                 Equipment=Equipment)
        else:
            return render_template('item_view.html', 
                                 item=item_data["item"],
                                 item_id=item_id)
    return redirect(url_for('inventory'))

@app.route("/destroy_item/<item_id>")
@login_required
@check_health_status
@check_pk_status
def destroy_item(item_id):
    player = get_current_player()
    if item_id in player.inventory:
        del player.inventory[item_id]
        save_player_data(session["username"], player)
    return redirect(url_for('inventory'))

#####  skill start 技能相关逻辑#####
@app.route("/learn_skill/<skill>")
@login_required
def learn_skill(skill):
    player = get_current_player()
    success, message = player.learn_skill(skill)
    if success:
        save_player_data(session["username"], player)
        flash(message, "success")
    else:
        flash(message, "error")
    return redirect(url_for("view_npc", monster_id="monster_village_trainer"))

@app.route("/upgrade_skill/<skill>")
@login_required
def upgrade_skill(skill):
    player = get_current_player()
    success, message = player.upgrade_skill(skill)
    if success:
        save_player_data(session["username"], player)
        flash(message, "success")
    else:
        flash(message, "error")
    return redirect(url_for("view_npc", monster_id="monster_village_trainer"))

@app.route("/skill_hall")
@login_required
def skill_hall():
    player = get_current_player()
    return render_template("skill_hall.html", player=player)

#####  social start 社交赠送、聊天逻辑#####
@app.route("/send_message/<to_username>", methods=["POST"])
@login_required
@check_health_status
@check_pk_status
def send_message(to_username):
    player = get_current_player()
    message = request.form.get("message")
    receiver_data = load_player_data(to_username)
    
    # 保存消息到发送者的聊天历史
    if to_username not in player.chat_history:
        player.chat_history[to_username] = []
    player.chat_history[to_username].append({
        "sender": player.username,
        "sender_name": player.name,
        "receiver_name": receiver_data["name"],
        "content": message,
        "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })
    save_player_data(session["username"], player)
    
    # 保存消息到接收者
    if receiver_data:
        receiver = Player.from_dict(receiver_data)
        if player.username not in receiver.chat_history:
            receiver.chat_history[player.username] = []
        receiver.chat_history[player.username].append({
            "sender": player.username,
            "sender_name": player.name,
            "receiver_name": receiver_data["name"],
            "content": message,
            "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
        receiver.last_chat_message = {
            "sender": player.name,
            "content": message,
            "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        receiver.chat_refresh_count = 0
        save_player_data(to_username, receiver)
    
    flash(f"你对{receiver_data['name']}说：{message}")
    return redirect(url_for('view_player', username=to_username))

@app.route("/chat")
@login_required
@check_health_status
@check_pk_status
def chat():
    player = get_current_player()
    return render_template("chat.html", player=player)

@app.route("/gift/<username>")
@login_required
@check_health_status
@check_pk_status
def gift_page(username):
    player = get_current_player()
    target_player_data = load_player_data(username)
    if not target_player_data:
        return redirect(url_for("scene"))
    
    # Filter non-bound items
    giftable_items = {}
    for item_id, item_data in player.inventory.items():
        if item_id.startswith('equipment_'):
            equipment = Equipment.from_dict(item_data)
            if not equipment.is_bound:
                giftable_items[item_id] = item_data
        else:
            giftable_items[item_id] = item_data
            
    return render_template("gift.html", 
                         player=player,
                         target_player=target_player_data,
                         giftable_items=giftable_items)

@app.route("/send_gift/<username>", methods=["POST"])
@login_required
@check_health_status
@check_pk_status
def send_gift(username):
    player = get_current_player()
    target_player_data = load_player_data(username)
    if not target_player_data:
        return redirect(url_for("scene"))
        
    item_id = request.form.get("item_id")
    quantity = int(request.form.get("quantity", 1))
    
    if item_id not in player.inventory:
        flash("物品不存在")
        return redirect(url_for("gift_page", username=username))
        
    item_data = player.inventory[item_id]
    
    # Get item name for notification
    if item_id.startswith('equipment_'):
        item_name = item_data["name"]
    else:
        item_name = item_data["item"]["name"]
    
    # Handle equipment
    if item_id.startswith('equipment_'):
        equipment = Equipment.from_dict(item_data)
        if equipment.is_bound:
            flash("绑定装备无法赠送")
            return redirect(url_for("gift_page", username=username))
        
        # 重新加载接收者最新数据
        target_player_data = load_player_data(username)
        target_player = Player.from_dict(target_player_data)
        
        # 生成新ID并添加装备
        new_id = f"equipment_{int(time.time())}_{random.randint(1000, 9999)}"
        target_player.inventory[new_id] = equipment.to_dict()
        
        # 从赠送者背包中删除装备
        del player.inventory[item_id]

    # Handle stackable items
    else:
        if quantity > item_data["quantity"]:
            flash("数量不足")
            return redirect(url_for("gift_page", username=username))
            
        item_data["quantity"] -= quantity
        if item_data["quantity"] <= 0:
            del player.inventory[item_id]
            
        target_player = Player.from_dict(target_player_data)
        if item_id in target_player.inventory:
            target_player.inventory[item_id]["quantity"] += quantity
        else:
            target_player.inventory[item_id] = {
                "item": item_data["item"],
                "quantity": quantity
            }

    # Add notification for sender
    player.notifications.append({
        "type": "gift_sent",
        "content": f"【赠送成功】你成功赠送{item_name} x{quantity}给{target_player_data['name']}",
        "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "item_name": item_name,
        "quantity": quantity,
        "receiver_name": target_player_data['name'],
        "receiver_username": target_player_data['username']
    })
    
    # Add notification for receiver
    target_player.last_chat_message = {
        "sender": player.name,
        "content": f"赠送给你{item_name} x{quantity}",
        "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "is_gift": True
    }
    target_player.chat_refresh_count = 0
    
    target_player.notifications.append({
        "type": "gift_received",
        "content": f"【通知】{player.name}赠送给你{item_name} x{quantity}",
        "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "item_name": item_name,
        "quantity": quantity,
        "sender_name": player.name,
        "sender_username": player.username
    })
    
    save_player_data(username, target_player)
    save_player_data(session["username"], player)
    flash(f"【赠送成功】你成功赠送{item_name} x{quantity}给{target_player_data['name']}")
    return redirect(url_for("view_player", username=username))

@app.route("/toggle_view/<view_type>")
@login_required
@check_health_status
@check_pk_status
def toggle_view(view_type):
    player = get_current_player()
    player.current_view = view_type
    save_player_data(session["username"], player)
    return redirect(url_for("chat"))

#####  enhance start 装备强化逻辑#####
@app.route("/equipment/<item_id>")
@login_required
@check_health_status
@check_pk_status
def view_equipment(item_id):
    player = get_current_player()
    if item_id in player.inventory:
        equipment_data = player.inventory[item_id]
        equipment = Equipment.from_dict(equipment_data)  # Convert dict to Equipment object
        return render_template('equipment_view.html', 
                             equipment=equipment, 
                             item_id=item_id,
                             Equipment=Equipment)
    return redirect(url_for('inventory'))

@app.route("/enhance/<item_id>")
@login_required
@check_health_status
@check_pk_status
def enhance_page(item_id):
    player = get_current_player()
    if item_id not in player.inventory:
        return redirect(url_for('inventory'))
        
    equipment = Equipment.from_dict(player.inventory[item_id])
    
    # 检查是否可以强化
    can_enhance = (
        player.money >= 5000 and
        equipment.enhance_level < 50 and
        'enhance_gem' in player.inventory and
        player.inventory['enhance_gem']['quantity'] > 0
    )
    
    return render_template('enhance.html',
                         player=player,
                         equipment=equipment,
                         item_id=item_id,
                         can_enhance=can_enhance,
                         Equipment=Equipment)

@app.route("/enhance/<item_id>", methods=["POST"])
@login_required
@check_health_status
@check_pk_status
def enhance_equipment(item_id):
    player = get_current_player()
    if item_id not in player.inventory:
        return redirect(url_for('inventory'))
        
    equipment = Equipment.from_dict(player.inventory[item_id])
    
    # 检查条件
    if (equipment.enhance_level >= 50 or
        player.money < 5000 or
        'enhance_gem' not in player.inventory or
        player.inventory['enhance_gem']['quantity'] < 1):
        return render_template('enhance.html',
                             player=player,
                             equipment=equipment,
                             item_id=item_id,
                             message="强化条件不足",
                             success=False,
                             Equipment=Equipment)
    
    # 扣除材料
    player.money -= 5000
    player.inventory['enhance_gem']['quantity'] -= 1
    if player.inventory['enhance_gem']['quantity'] <= 0:
        del player.inventory['enhance_gem']
    
    # 尝试强化
    success_rate = equipment.get_enhance_success_rate(player.enhance_bonus_rate)
    if random.random() < success_rate:
        equipment.enhance_level += 1
        player.enhance_bonus_rate = 0
        
        # 计算总强化加成基于初始属性
        for stat, initial_value in equipment.initial_stats.items():
            total_bonus = int(initial_value * 0.1 * equipment.enhance_level)
            equipment.base_stats[stat] = initial_value + total_bonus
        
        base_name = f"【{equipment.rarity}】{equipment.template['name']}({equipment.stars}星)({equipment.level_required}级)"
        equipment.name = f"{base_name}+{equipment.enhance_level}"
        
        message = f"强化成功!装备等级提升至+{equipment.enhance_level}"
        success = True
    else:
        equipment.enhance_level = max(0, equipment.enhance_level - 1)
        player.enhance_bonus_rate += 0.05
        
        # 失败后重新计算总强化加成
        for stat, initial_value in equipment.initial_stats.items():
            total_bonus = int(initial_value * 0.1 * equipment.enhance_level)
            equipment.base_stats[stat] = initial_value + total_bonus
        
        base_name = f"【{equipment.rarity}】{equipment.template['name']}({equipment.stars}星)({equipment.level_required}级)"
        equipment.name = f"{base_name}+{equipment.enhance_level}" if equipment.enhance_level > 0 else base_name
        
        message = f"强化失败!装备等级降至+{equipment.enhance_level},下次强化成功率+5%"
        success = False

    # 更新装备数据
    player.inventory[item_id] = equipment.to_dict()
    save_player_data(session["username"], player)
    
    return render_template('enhance.html',
                         player=player,
                         equipment=equipment,
                         item_id=item_id,
                         message=message,
                         success=success,
                         Equipment=Equipment)

#####  scene start 场景移动及互动#####
@app.route("/pickup/<item_id>")
@login_required
@check_health_status
@check_pk_status
def pickup_item(item_id):
    player = get_current_player()
    current_location = locations[player.current_location]
    if item_id in current_location.ground_items:
        player.add_item(item_id)
        current_location.ground_items.remove(item_id)
        save_player_data(session["username"], player)
    return redirect(url_for("scene"))

@app.route("/scene")
@login_required
@check_health_status
@check_pk_status
def scene():
    global current_monster
    player = get_current_player()
    if not player:
        return redirect(url_for("login_page"))
    
    # Reset battle status
    player.in_battle = False
    player.in_pk = False
    player.pk_opponent = None
    
    if player.last_chat_message:
        player.chat_refresh_count += 1
        if player.chat_refresh_count >= 3:  # 3次刷新后清除消息
            player.last_chat_message = None
            player.chat_refresh_count = 0
        save_player_data(session["username"], player)
        
    current_location = locations[player.current_location]
    current_location.refresh_ground_items()

    if not current_monster or current_monster.monster_id != current_location.monster_type:
        current_monster = Monster.create_monster(current_location.monster_type)
    
    if current_monster and current_monster.immortal:
        current_monster.reset_health()
    
    other_players = []
    for file in SAVE_DIR.glob("*.json"):
        if file.stem != session["username"]:
            with open(file, 'r', encoding='utf-8') as f:
                other_player = json.load(f)
                if other_player["current_location"] == player.current_location:
                    other_players.append(other_player)
    
    save_player_data(session["username"], player)
    
    return render_template("scene.html", 
                         player=player, 
                         monster=current_monster,
                         location=current_location,
                         locations=locations,
                         other_players=other_players,
                         Item=Item,
                         now=datetime.now())

@app.route("/move/<direction>")
@login_required
@check_health_status
@check_pk_status
def move(direction):
    player = get_current_player()
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
        generate_new_monster(player)
        save_player_data(session["username"], player)
    return redirect(url_for("scene"))

if __name__ == "__main__":
    app.run(debug=True)
