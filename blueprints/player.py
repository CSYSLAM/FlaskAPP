import random
import time
from flask import Blueprint, render_template, redirect, url_for, request, session, flash
from datetime import datetime
from models.player import Player
from models.equipment import Equipment
from models.skill import Skill
from services.data_service import DataService
from utils.decorators import login_required, check_health_status, check_pk_status
from services.public_chat import broadcast_system

player_bp = Blueprint('player', __name__)

@player_bp.route("/character")
@login_required
@check_health_status
@check_pk_status
def character():
    player = DataService.get_current_player(session)
    player.update_stats()
    can_level_up = player.experience >= player.exp_to_next_level
    return render_template("character.html", 
                         player=player, 
                         can_level_up=can_level_up,
                         Equipment=Equipment,
                         now=datetime.now())

@player_bp.route("/level_up")
@login_required
@check_health_status
@check_pk_status
def level_up():
    player = DataService.get_current_player(session)
    if player.level_up():
        DataService.save_player_data(session["username"], player)
    return redirect(url_for("player.character"))

@player_bp.route("/view/<username>")
@login_required
@check_health_status
@check_pk_status
def view_player(username):
    player = DataService.get_current_player(session)
    target_player_data = DataService.load_player_data(username)
    if not target_player_data:
        return redirect(url_for("game.scene"))
        
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
                         player=player,
                         target_player=target_player,
                         Equipment=Equipment)

@player_bp.route("/military_ranks")
@login_required
@check_health_status
def military_ranks():
    player = DataService.get_current_player(session)
    return render_template("military_ranks.html", player=player)

# 装备相关
@player_bp.route("/equipment_list")
@login_required
@check_health_status
@check_pk_status
def equipment_list():
    player = DataService.get_current_player(session)
    return render_template("equipment_list.html", 
                         player=player,
                         Equipment=Equipment)

@player_bp.route("/view_equipped/<slot>")
@login_required
@check_health_status
@check_pk_status
def view_equipped(slot):
    player = DataService.get_current_player(session)
    if slot in player.equipment and player.equipment[slot]:
        equipment = player.equipment[slot]
        return render_template('equipment_view.html', 
                             equipment=equipment, 
                             item_id=f'equipped_{slot}',
                             Equipment=Equipment)
    return redirect(url_for('player.equipment_list'))

@player_bp.route("/equip/<item_id>")
@login_required
@check_pk_status
@check_health_status
def equip_item(item_id):
    player = DataService.get_current_player(session)
    if item_id in player.inventory:
        equipment_dict = player.inventory[item_id]
        equipment = Equipment.from_dict(equipment_dict)
        
        # 检查职业要求
        if equipment.class_required and equipment.class_required != player.player_class:
            player.item_effect = f"需要{equipment.class_required}职业才能装备"
            DataService.save_player_data(session["username"], player)
            return redirect(url_for('player.inventory'))
            
        # 检查等级要求
        if equipment.level_required > player.level:
            player.item_effect = f"需要等级{equipment.level_required}才能装备"
            DataService.save_player_data(session["username"], player)
            return redirect(url_for('player.inventory'))
            
        # 如果通过检查才进行装备
        old_equipment = player.equip(equipment)
        del player.inventory[item_id]
        if old_equipment:
            new_id = f"equipment_{int(time.time())}_{random.randint(1000, 9999)}"
            player.inventory[new_id] = old_equipment.to_dict() if isinstance(old_equipment, Equipment) else old_equipment
        DataService.save_player_data(session["username"], player)
    return redirect(url_for('player.inventory'))

@player_bp.route("/unequip/<slot>")
@login_required
@check_health_status
@check_pk_status
def unequip(slot):
    player = DataService.get_current_player(session)
    equipment = player.unequip(slot)
    if equipment:
        new_id = f"equipment_{int(time.time())}_{random.randint(1000, 9999)}"
        player.inventory[new_id] = equipment
        DataService.save_player_data(session["username"], player)
    return redirect(url_for('player.character'))

# 背包相关
@player_bp.route("/inventory")
@login_required
@check_health_status
@check_pk_status
def inventory():
    player = DataService.get_current_player(session)
    return render_template("inventory.html", player=player)

@player_bp.route("/use_item/<item>")
@login_required
@check_health_status
@check_pk_status
def use_item(item):
    player = DataService.get_current_player(session)
    if item in player.inventory:
        player.use_item(item)
        DataService.save_player_data(session["username"], player)
    return redirect(url_for("player.inventory"))

@player_bp.route("/bulk_use/<item_id>", methods=["POST"])
@login_required
@check_health_status
def bulk_use_item(item_id):
    player = DataService.get_current_player(session)
    if item_id not in player.inventory:
        return redirect(url_for('player.inventory'))
        
    quantity = int(request.form.get('quantity', 1))
    item_data = player.inventory[item_id]
    
    if quantity > item_data["quantity"]:
        quantity = item_data["quantity"]
    
    # 批量使用物品
    success_count = 0
    for _ in range(quantity):
        if player.use_item(item_id):
            success_count += 1
    
    player.update_military_rank()
    DataService.save_player_data(session["username"], player)
    
    flash(f"成功使用{success_count}个{item_data['item']['name']}")
    
    if item_id in player.inventory:
        return redirect(url_for('player.view_item', item_id=item_id))
    return redirect(url_for('player.inventory'))

@player_bp.route("/view_item/<item_id>")
@login_required
@check_health_status
@check_pk_status
def view_item(item_id):
    player = DataService.get_current_player(session)
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
    return redirect(url_for('player.inventory'))

@player_bp.route("/sell/<item_id>")
@login_required
def sell_item(item_id):
    player = DataService.get_current_player(session)
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
            DataService.save_player_data(session["username"], player)
    return redirect(url_for('player.inventory'))

@player_bp.route("/destroy_item/<item_id>")
@login_required
@check_health_status
@check_pk_status
def destroy_item(item_id):
    player = DataService.get_current_player(session)
    if item_id in player.inventory:
        del player.inventory[item_id]
        DataService.save_player_data(session["username"], player)
    return redirect(url_for('player.inventory'))

@player_bp.route("/equipment/<item_id>")
@login_required
@check_health_status
@check_pk_status
def view_equipment(item_id):
    player = DataService.get_current_player(session)
    if item_id in player.inventory:
        equipment_data = player.inventory[item_id]
        equipment = Equipment.from_dict(equipment_data)
        return render_template('equipment_view.html', 
                             equipment=equipment, 
                             item_id=item_id,
                             Equipment=Equipment)
    return redirect(url_for('player.inventory'))

# 强化相关
@player_bp.route("/enhance/<item_id>")
@login_required
@check_health_status
@check_pk_status
def enhance_page(item_id):
    player = DataService.get_current_player(session)
    if item_id not in player.inventory:
        return redirect(url_for('player.inventory'))
        
    equipment = Equipment.from_dict(player.inventory[item_id])
    
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

@player_bp.route("/enhance/<item_id>", methods=["POST"])
@login_required
@check_health_status
@check_pk_status
def enhance_equipment(item_id):
    player = DataService.get_current_player(session)
    if item_id not in player.inventory:
        return redirect(url_for('player.inventory'))
        
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
        # 公共广播：强化成功
        broadcast_system(f"{player.name}成功将{equipment.template['name']}强化至+{equipment.enhance_level}")
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
    DataService.save_player_data(session["username"], player)
    
    return render_template('enhance.html',
                         player=player,
                         equipment=equipment,
                         item_id=item_id,
                         message=message,
                         success=success,
                         Equipment=Equipment)

# 技能相关
@player_bp.route("/learn_skill/<skill>")
@login_required
def learn_skill(skill):
    player = DataService.get_current_player(session)
    success, message = player.learn_skill(skill)
    if success:
        DataService.save_player_data(session["username"], player)
        flash(message, "success")
    else:
        flash(message, "error")
    return redirect(url_for("game.view_npc", monster_id="monster_village_trainer"))

@player_bp.route("/upgrade_skill/<skill>")
@login_required
def upgrade_skill(skill):
    player = DataService.get_current_player(session)
    success, message = player.upgrade_skill(skill)
    if success:
        DataService.save_player_data(session["username"], player)
        flash(message, "success")
    else:
        flash(message, "error")
    return redirect(url_for("game.view_npc", monster_id="monster_village_trainer"))

@player_bp.route("/skill_hall")
@login_required
def skill_hall():
    player = DataService.get_current_player(session)
    return render_template("skill_hall.html", player=player)

@player_bp.route("/temp_effects")
@login_required
def temp_effects():
    player = DataService.get_current_player(session)
    return render_template("temp_effects.html", player=player)