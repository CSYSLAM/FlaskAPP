from flask import Blueprint, render_template, request, session
from models.item import Item
from services.data_service import DataService
from utils.decorators import login_required, check_health_status, check_pk_status

shop_bp = Blueprint('shop', __name__)

@shop_bp.route("/")
@login_required
@check_health_status
@check_pk_status
def shop():
    player = DataService.get_current_player(session)
    shop_items = Item.get_shop_items()
    return render_template("shop.html", player=player, shop_items=shop_items)

@shop_bp.route("/buy_item", methods=["POST"])
@login_required
@check_health_status
@check_pk_status
def buy_item():
    player = DataService.get_current_player(session)
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
    
    DataService.save_player_data(session["username"], player)
    
    return render_template("shop.html", 
                         player=player, 
                         shop_items=shop_items,
                         message=f"成功购买{quantity}个{item.name}，花费{total_cost}银两", 
                         success=True)