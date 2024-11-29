from flask import Flask, render_template, redirect, url_for, request, session, flash
from models.player import Player
from models.monster import Monster
from models.item import Item
from models.location import Location
from models.equipment import Equipment
from pathlib import Path
import json
from functools import wraps
import time
import random
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

SAVE_DIR = Path("player_data")
SAVE_DIR.mkdir(exist_ok=True)

locations = Location.get_locations()
shop_items = Item.get_shop_items()
current_monster = None  # 保留这个全局变量用于战斗

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated_function

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
    return player

@app.route("/")
def index():
    if "username" in session:
        return redirect(url_for("scene"))
    return redirect(url_for("login_page"))

@app.route("/login", methods=["GET", "POST"])
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
    
    player = Player(nickname, player_class)
    player.username = username
    player.password = password
    player.current_location = "outdoor.village"
    
    save_player_data(username, player)
    session["username"] = username
    return redirect(url_for("scene"))

@app.route("/equip/<item_id>")
@login_required
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

@app.route("/pickup/<item_id>")
@login_required
def pickup_item(item_id):
    player = get_current_player()
    current_location = locations[player.current_location]
    if item_id in current_location.ground_items:
        player.add_item(item_id)
        current_location.ground_items.remove(item_id)
        save_player_data(session["username"], player)
    return redirect(url_for("scene"))

@app.route("/logout")
def logout():
    if "username" in session:
        session.pop("username", None)
    return redirect(url_for("login_page"))

@app.route("/shop")
@login_required
def shop():
    player = get_current_player()
    return render_template("shop.html", player=player, shop_items=shop_items)

@app.route("/buy_item", methods=["POST"])
@login_required
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


@app.route("/unequip/<slot>")
@login_required
def unequip(slot):
    player = get_current_player()
    equipment = player.unequip(slot)
    if equipment:
        new_id = f"equipment_{int(time.time())}_{random.randint(1000, 9999)}"
        player.inventory[new_id] = equipment
        save_player_data(session["username"], player)
    return redirect(url_for('character'))

@app.route("/scene")
@login_required
def scene():
    global current_monster
    player = get_current_player()
    if not player:
        return redirect(url_for("login_page"))
    
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
    
    return render_template("scene.html", 
                         player=player, 
                         monster=current_monster,
                         location=current_location,
                         locations=locations,
                         other_players=other_players,
                         Item=Item,
                         now=datetime.now())

@app.route("/character")
@login_required
def character():
    player = get_current_player()
    player.update_stats()  # 添加这行来更新属性
    can_level_up = player.experience >= player.exp_to_next_level
    return render_template("character.html", 
                         player=player, 
                         can_level_up=can_level_up,
                         Equipment=Equipment)


@app.route("/level_up")
@login_required
def level_up():
    player = get_current_player()
    if player.level_up():
        save_player_data(session["username"], player)
    return redirect(url_for("character"))

@app.route("/battle")
@login_required
def battle():
    player = get_current_player()
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
    
    return render_template("battle.html", 
                         player=player, 
                         monster=current_monster,
                         now=datetime.now())

@app.route("/fight", methods=["POST"])
@login_required
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


@app.route("/learn_skill/<skill>")
@login_required
def learn_skill(skill):
    player = get_current_player()
    if player.learn_skill(skill):
        save_player_data(session["username"], player)
        return redirect(url_for("scene"))
    return "无法学习该技能"

@app.route("/skill_hall")
@login_required
def skill_hall():
    player = get_current_player()
    return render_template("skill_hall.html", player=player)

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


@app.route("/battle_result")
@login_required
def battle_result():
    player = get_current_player()
    result = player.last_battle_result
    lost_experience = 0
    if player.health <= 0 and player.experience > 0:
        lost_experience = max(0, int(player.experience * 0.1))
        player.experience -= lost_experience
    return render_template("battle_result.html", result=result, lost_experience=lost_experience)

@app.route("/revive")
@login_required
def revive():
    player = get_current_player()
    has_revive_item = "续命灯" in player.inventory
    return render_template("revive.html", player=player, has_revive_item=has_revive_item)

@app.route("/revive_action/<method>")
@login_required
def revive_action(method):
    player = get_current_player()
    if method == "item":
        if player.use_revive_item():
            save_player_data(session["username"], player)
            return redirect(url_for("scene"))
        return "没有续命灯，无法复活！"
    elif method == "weak":
        player.weak_revive()
        save_player_data(session["username"], player)
        return redirect(url_for("scene"))

@app.route("/inventory")
@login_required
def inventory():
    player = get_current_player()
    return render_template("inventory.html", player=player)

@app.route("/use_item/<item>")
@login_required
def use_item(item):
    player = get_current_player()
    if item in player.inventory:
        player.use_item(item)
        save_player_data(session["username"], player)
    return redirect(url_for("inventory"))


@app.route("/move/<direction>")
@login_required
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


@app.route("/equipment/<item_id>")
@login_required
def view_equipment(item_id):
    player = get_current_player()
    if item_id in player.inventory:
        equipment = player.inventory[item_id]
        return render_template('equipment_view.html', 
                             equipment=equipment, 
                             item_id=item_id,
                             Equipment=Equipment)
    return redirect(url_for('inventory'))

def generate_new_monster(player):
    global current_monster
    current_monster = Monster.create_monster(locations[player.current_location].monster_type)

@app.route("/continue_battle")
@login_required
def continue_battle():
    player = get_current_player()
    generate_new_monster(player)
    return redirect(url_for("battle"))

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
def destroy_item(item_id):
    player = get_current_player()
    if item_id in player.inventory:
        del player.inventory[item_id]
        save_player_data(session["username"], player)
    return redirect(url_for('inventory'))

@app.route("/view_player/<username>")
@login_required
def view_player(username):
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
                         target_player=target_player,
                         Equipment=Equipment)

@app.route("/send_message/<to_username>", methods=["POST"])
@login_required
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
def chat():
    player = get_current_player()
    return render_template("chat.html", player=player)


if __name__ == "__main__":
    app.run(debug=True)
