from flask import Flask, render_template, redirect, url_for, request, session
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

current_player = None
current_location = None
current_monster = None
locations = Location.get_locations()
shop_items = Item.get_shop_items()

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
            global current_player
            current_player = Player(player_data["name"], player_data["player_class"])
            current_player.current_location = "村庄"
            
            # 转换装备数据
            if "equipment" in player_data:
                equipment_data = player_data["equipment"]
                current_player.equipment = {
                    slot: Equipment.from_dict(equip_data) if equip_data else None
                    for slot, equip_data in equipment_data.items()
                }
            
            # 更新其他数据
            player_data_copy = player_data.copy()
            player_data_copy.pop('equipment', None)  # 移除equipment数据避免覆盖
            current_player.__dict__.update(player_data_copy)
            
            # 更新玩家状态
            current_player.update_stats()
            
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
    
    global current_player
    current_player = Player(nickname, player_class)
    current_player.username = username
    current_player.password = password
    
    save_player_data(username, current_player)
    session["username"] = username
    return redirect(url_for("scene"))

@app.route("/equip/<item_id>")
@login_required
def equip_item(item_id):
    if item_id in current_player.inventory:
        equipment_dict = current_player.inventory[item_id]
        equipment = Equipment.from_dict(equipment_dict)
        
        # 检查职业要求
        if equipment.class_required and equipment.class_required != current_player.player_class:
            current_player.item_effect = f"需要{equipment.class_required}职业才能装备"
            save_player_data(session["username"], current_player)
            return redirect(url_for('inventory'))
            
        # 检查等级要求
        if equipment.level_required > current_player.level:
            current_player.item_effect = f"需要等级{equipment.level_required}才能装备"
            save_player_data(session["username"], current_player)
            return redirect(url_for('inventory'))
            
        # 如果通过检查才进行装备
        old_equipment = current_player.equip(equipment)
        del current_player.inventory[item_id]
        if old_equipment:
            new_id = f"equipment_{len(current_player.inventory)}"
            current_player.inventory[new_id] = old_equipment.to_dict() if isinstance(old_equipment, Equipment) else old_equipment
        save_player_data(session["username"], current_player)
    return redirect(url_for('inventory'))



@app.route("/unequip/<slot>")
@login_required
def unequip(slot):
    equipment = current_player.unequip(slot)
    if equipment:
        new_id = f"equipment_{len(current_player.inventory)}"
        current_player.inventory[new_id] = equipment
        save_player_data(session["username"], current_player)
    return redirect(url_for('character'))

@app.route("/logout")
def logout():
    if "username" in session:
        save_player_data(session["username"], current_player)
        session.pop("username", None)
    return redirect(url_for("login_page"))

@app.route("/shop")
@login_required
def shop():
    return render_template("shop.html", player=current_player, shop_items=shop_items)

@app.route("/buy_item", methods=["POST"])
@login_required
def buy_item():
    item_id = request.form.get("item_id")
    quantity = request.form.get("quantity", type=int)
    
    shop_items = Item.get_shop_items()
    if item_id not in shop_items:
        return render_template("shop.html", 
                             player=current_player, 
                             shop_items=shop_items,
                             message="物品不存在", 
                             success=False)
    
    item = shop_items[item_id]
    total_cost = item.price * quantity
    
    if quantity <= 0:
        return render_template("shop.html", 
                             player=current_player, 
                             shop_items=shop_items,
                             message="购买数量必须大于0", 
                             success=False)
    
    if current_player.money < total_cost:
        return render_template("shop.html", 
                             player=current_player, 
                             shop_items=shop_items,
                             message="余额不足", 
                             success=False)
    
    current_player.money -= total_cost
    for _ in range(quantity):
        current_player.add_item(item_id)
    
    save_player_data(session["username"], current_player)
    
    return render_template("shop.html", 
                         player=current_player, 
                         shop_items=shop_items,
                         message=f"成功购买{quantity}个{item.name}，花费{total_cost}银两", 
                         success=True)


@app.route("/pickup/<item_id>")
@login_required
def pickup_item(item_id):
    if item_id in current_location.ground_items:
        current_player.add_item(item_id)
        current_location.ground_items.remove(item_id)
        save_player_data(session["username"], current_player)
    return redirect(url_for("scene"))

# Update the scene route
@app.route("/scene")
@login_required
def scene():
    global current_location, current_monster, current_player
    
    if not current_player:
        return redirect(url_for("login_page"))
        
    current_location = locations[current_player.current_location]
    current_location.refresh_ground_items()

    if not current_monster or current_monster.monster_id != current_location.monster_type:
        current_monster = Monster.create_monster(current_location.monster_type)
    
    # Reset monster health if immortal
    if current_monster and current_monster.immortal:
        current_monster.reset_health()
    
    other_players = []
    for file in SAVE_DIR.glob("*.json"):
        if file.stem != session["username"]:
            with open(file, 'r', encoding='utf-8') as f:
                other_player = json.load(f)
                if other_player["current_location"] == current_player.current_location:
                    other_players.append(other_player)
    
    return render_template("scene.html", 
                         player=current_player, 
                         monster=current_monster,
                         location=current_location,
                         locations=locations,
                         other_players=other_players,
                         Item=Item)  # Pass Item class to template

@app.route("/character")
@login_required
def character():
    current_player.update_stats()  # 添加这行来更新属性
    can_level_up = current_player.experience >= current_player.exp_to_next_level
    return render_template("character.html", 
                         player=current_player, 
                         can_level_up=can_level_up,
                         Equipment=Equipment)


@app.route("/level_up")
@login_required
def level_up():
    if current_player.level_up():
        save_player_data(session["username"], current_player)
    return redirect(url_for("character"))

@app.route("/battle")
@login_required
def battle():
    # Only reset battle information if coming from scene (not during battle)
    referrer = request.referrer
    if referrer and 'scene' in referrer:
        current_player.last_action = None
        current_player.last_damage_dealt = None
        current_player.last_damage_taken = None
        current_player.last_mana_cost = None
        current_player.last_skill = None
        
        current_monster.last_action = None
        current_monster.last_damage_dealt = None
        current_monster.last_damage_taken = None
        current_monster.last_skill = None
    
    return render_template("battle.html", 
                         player=current_player, 
                         monster=current_monster,
                         now=datetime.now())

@app.route("/fight", methods=["POST"])
@login_required
def fight():
    action = request.form.get("action")
    
    if action == "attack":
        current_player.attack_monster(current_monster)
    elif action.startswith("use:"):
        item_id = action.split(":")[1]
        if item_id:
            current_player.use_item(item_id)
    else:  # This is a skill action
        current_player.use_skill(current_monster, action)

    if current_monster.health <= 0:
        handle_monster_defeat()
        save_player_data(session["username"], current_player)
        return redirect(url_for("battle_result"))
    
    current_monster.attack_player(current_player)
    
    if current_player.health <= 0:
        current_player.last_battle_result = f"你被{current_monster.name}打败了"
        save_player_data(session["username"], current_player)
        return redirect(url_for("revive"))

    save_player_data(session["username"], current_player)
    return redirect(url_for("battle"))


@app.route("/learn_skill/<skill>")
@login_required
def learn_skill(skill):
    if current_player.learn_skill(skill):
        save_player_data(session["username"], current_player)
        return redirect(url_for("scene"))
    return "无法学习该技能"

@app.route("/skill_hall")
@login_required
def skill_hall():
    return render_template("skill_hall.html", player=current_player)

def handle_monster_defeat():
    loot = current_monster.get_loot()
    money = current_monster.get_money_drop()
    loot_name = None
    
    if isinstance(loot, Equipment):
        new_id = f"equipment_{int(time.time())}_{random.randint(1000, 9999)}"
        current_player.inventory[new_id] = loot.to_dict()
        loot_name = loot.name
    elif loot:  # Handle non-equipment items
        items = Item.load_items()
        if loot in items:
            current_player.add_item(loot)
            loot_name = items[loot].name
    
    current_player.money += money
    current_player.experience += 20
    current_player.last_battle_result = (
        f"你击败了{current_monster.name}！" +
        (f"获得了{loot_name}，" if loot_name else "这次什么也没掉落，") +
        f"经验增加了20，获得{money}银两。"
    )
    
    generate_new_monster()


@app.route("/battle_result")
@login_required
def battle_result():
    result = current_player.last_battle_result
    lost_experience = 0
    if current_player.health <= 0 and current_player.experience > 0:
        lost_experience = max(0, int(current_player.experience * 0.1))
        current_player.experience -= lost_experience
    return render_template("battle_result.html", result=result, lost_experience=lost_experience)

@app.route("/revive")
@login_required
def revive():
    has_revive_item = "续命灯" in current_player.inventory
    return render_template("revive.html", player=current_player, has_revive_item=has_revive_item)

@app.route("/revive_action/<method>")
@login_required
def revive_action(method):
    if method == "item":
        if current_player.use_revive_item():
            save_player_data(session["username"], current_player)
            return redirect(url_for("scene"))
        return "没有续命灯，无法复活！"
    elif method == "weak":
        current_player.weak_revive()
        save_player_data(session["username"], current_player)
        return redirect(url_for("scene"))

@app.route("/inventory")
@login_required
def inventory():
    return render_template("inventory.html", player=current_player)

@app.route("/use_item/<item>")
@login_required
def use_item(item):
    if item in current_player.inventory:
        current_player.use_item(item)
        save_player_data(session["username"], current_player)
    return redirect(url_for("inventory"))


@app.route("/move/<direction>")
@login_required
def move(direction):
    current_loc = locations[current_player.current_location]
    direction_mapping = {
        "north": "north_exit",
        "south": "south_exit",
        "east": "east_exit",
        "west": "west_exit"
    }
    
    exit_attr = direction_mapping.get(direction)
    if exit_attr and getattr(current_loc, exit_attr):
        new_location = getattr(current_loc, exit_attr)
        current_player.current_location = new_location
        generate_new_monster()
        save_player_data(session["username"], current_player)
    return redirect(url_for("scene"))

@app.route("/shortcuts")
@login_required
def shortcuts():
    return render_template("shortcuts.html", player=current_player)


@app.route("/set_shortcut", methods=["POST"])
@login_required
def set_shortcut():
    # Initialize shortcuts if not exists
    if not hasattr(current_player, 'shortcuts'):
        current_player.shortcuts = {
            'skill1': 'attack',
            'skill2': 'attack',
            'skill3': 'attack',
            'skill4': 'attack',
            'potion1': None,
            'potion2': None
        }
    
    # Update shortcuts from form data
    current_player.shortcuts['skill1'] = request.form.get('skill1', 'attack')
    current_player.shortcuts['skill2'] = request.form.get('skill2', 'attack')
    current_player.shortcuts['skill3'] = request.form.get('skill3', 'attack')
    current_player.shortcuts['skill4'] = request.form.get('skill4', 'attack')
    
    # Check if potions still exist in inventory before setting shortcuts
    potion1 = request.form.get('potion1')
    potion2 = request.form.get('potion2')
    
    if potion1 and potion1 in current_player.inventory:
        current_player.shortcuts['potion1'] = potion1
    else:
        current_player.shortcuts['potion1'] = None
        
    if potion2 and potion2 in current_player.inventory:
        current_player.shortcuts['potion2'] = potion2
    else:
        current_player.shortcuts['potion2'] = None
    
    save_player_data(session["username"], current_player)
    return redirect(url_for('battle'))


@app.route("/equipment/<item_id>")
@login_required
def view_equipment(item_id):
    if item_id in current_player.inventory:
        equipment = current_player.inventory[item_id]
        return render_template('equipment_view.html', 
                             equipment=equipment, 
                             item_id=item_id,
                             Equipment=Equipment)
    return redirect(url_for('inventory'))

def generate_new_monster():
    global current_monster
    current_monster = Monster.create_monster(locations[current_player.current_location].monster_type)

@app.route("/continue_battle")
@login_required
def continue_battle():
    generate_new_monster()
    return redirect(url_for("battle"))

@app.route("/sell/<item_id>")
@login_required
def sell_item(item_id):
    if item_id in current_player.inventory:
        equipment_data = current_player.inventory[item_id]
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
            current_player.money += sell_price
            del current_player.inventory[item_id]
            save_player_data(session["username"], current_player)
    return redirect(url_for('inventory'))

@app.route("/view_item/<item_id>")
@login_required
def view_item(item_id):
    if item_id in current_player.inventory:
        item_data = current_player.inventory[item_id]
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
    if item_id in current_player.inventory:
        del current_player.inventory[item_id]
        save_player_data(session["username"], current_player)
    return redirect(url_for('inventory'))




if __name__ == "__main__":
    app.run(debug=True)
