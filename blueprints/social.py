from flask import Blueprint, render_template, redirect, url_for, request, session, flash
from datetime import datetime
from models.player import Player
from models.equipment import Equipment
from services.data_service import DataService
from utils.decorators import login_required, check_health_status, check_pk_status
from services.public_chat import broadcast_player, list_latest
import random
import time

social_bp = Blueprint('social', __name__)

@social_bp.route("/send_message/<to_username>", methods=["POST"])
@login_required
@check_health_status
@check_pk_status
def send_message(to_username):
    player = DataService.get_current_player(session)
    message = request.form.get("message")
    receiver_data = DataService.load_player_data(to_username)
    
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
    DataService.save_player_data(session["username"], player)
    
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
        DataService.save_player_data(to_username, receiver)
    
    flash(f"你对{receiver_data['name']}说：{message}")
    return redirect(url_for('player.view_player', username=to_username))

@social_bp.route("/chat")
@login_required
@check_health_status
@check_pk_status
def chat():
    player = DataService.get_current_player(session)
    public_messages = list_latest(50)
    return render_template("chat.html", player=player, public_messages=public_messages)

@social_bp.route("/shout", methods=["POST"])
@login_required
@check_health_status
@check_pk_status
def shout():
    player = DataService.get_current_player(session)
    content = request.form.get("content", "").strip()
    if not content:
        flash("内容不能为空")
        return redirect(url_for("social.chat"))
    # 消耗大喇叭
    if 'megaphone' not in player.inventory or player.inventory['megaphone']['quantity'] <= 0:
        flash("需要一个大喇叭道具")
        return redirect(url_for("social.chat"))
    player.inventory['megaphone']['quantity'] -= 1
    if player.inventory['megaphone']['quantity'] <= 0:
        del player.inventory['megaphone']
    DataService.save_player_data(session["username"], player)
    broadcast_player(player.username, player.name, content)
    flash("已在公共频道发言")
    return redirect(url_for("social.chat"))

@social_bp.route("/toggle_view/<view_type>")
@login_required
@check_health_status
@check_pk_status
def toggle_view(view_type):
    player = DataService.get_current_player(session)
    player.current_view = view_type
    DataService.save_player_data(session["username"], player)
    return redirect(url_for("social.chat"))

@social_bp.route("/gift/<username>")
@login_required
@check_health_status
@check_pk_status
def gift_page(username):
    player = DataService.get_current_player(session)
    target_player_data = DataService.load_player_data(username)
    if not target_player_data:
        return redirect(url_for("game.scene"))
    
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

@social_bp.route("/send_gift/<username>", methods=["POST"])
@login_required
@check_health_status
@check_pk_status
def send_gift(username):
    player = DataService.get_current_player(session)
    target_player_data = DataService.load_player_data(username)
    if not target_player_data:
        return redirect(url_for("game.scene"))
        
    item_id = request.form.get("item_id")
    quantity = int(request.form.get("quantity", 1))
    
    if item_id not in player.inventory:
        flash("物品不存在")
        return redirect(url_for("social.gift_page", username=username))
        
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
            return redirect(url_for("social.gift_page", username=username))
        
        # 重新加载接收者最新数据
        target_player_data = DataService.load_player_data(username)
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
            return redirect(url_for("social.gift_page", username=username))
            
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

    # Add notifications
    player.notifications.append({
        "type": "gift_sent",
        "content": f"【赠送成功】你成功赠送{item_name} x{quantity}给{target_player_data['name']}",
        "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "item_name": item_name,
        "quantity": quantity,
        "receiver_name": target_player_data['name'],
        "receiver_username": target_player_data['username']
    })
    
    target_player.last_chat_message = {
        "sender": player.name,
        "content": f"赠送给你 {item_name} x{quantity}",
        "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "is_gift": True
    }
    target_player.chat_refresh_count = 0
    
    target_player.notifications.append({
        "type": "gift_received",
        "content": f"【通知】{player.name}赠送给你 {item_name} x{quantity}",
        "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "item_name": item_name,
        "quantity": quantity,
        "sender_name": player.name,
        "sender_username": player.username
    })
    
    DataService.save_player_data(username, target_player)
    DataService.save_player_data(session["username"], player)
    flash(f"【赠送成功】你成功赠送{item_name} x{quantity}给{target_player_data['name']}")
    return redirect(url_for("player.view_player", username=username))