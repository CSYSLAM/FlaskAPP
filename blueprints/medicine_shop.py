from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from services.data_service import DataService
from services.player_service import PlayerService
import json
import os

medicine_bp = Blueprint('medicine', __name__)

# Cache for shop catalog
_shop_catalog = None


def _load_catalog():
    global _shop_catalog
    if _shop_catalog is None:
        path = os.path.join(os.path.dirname(__file__), '..', 'data', 'medicine_shop.json')
        with open(path, 'r', encoding='utf-8') as f:
            _shop_catalog = json.load(f)
    return _shop_catalog


@medicine_bp.route("/<npc_id>")
@login_required
def shop(npc_id):
    player = current_user
    catalog = _load_catalog()
    tab = request.args.get('tab', 'medicine')

    monster_data = DataService.get_monster(npc_id) or {}
    doctor_name = monster_data.get('name', '大夫')

    medicines = catalog.get('medicines', [])
    seeds = catalog.get('seeds', [])

    # Paginate: 12 per page
    per_page = 12
    page = int(request.args.get('page', 1))
    if tab == 'seed':
        items_list = seeds
    else:
        items_list = medicines

    total_items = len(items_list)
    total_pages = max(1, (total_items + per_page - 1) // per_page)
    if page < 1:
        page = 1
    if page > total_pages:
        page = total_pages

    start = (page - 1) * per_page
    page_items = items_list[start:start + per_page]

    return render_template("medicine_shop.html",
                           player=player,
                           doctor_name=doctor_name,
                           npc_id=npc_id,
                           tab=tab,
                           items=page_items,
                           page=page,
                           total_pages=total_pages,
                           per_page=per_page)


@medicine_bp.route("/buy/<npc_id>/<item_id>", methods=["POST"])
@login_required
def buy(npc_id, item_id):
    player = current_user
    catalog = _load_catalog()

    quantity = int(request.form.get('quantity', 1))
    if quantity < 1:
        quantity = 1

    # Find item in catalog
    item_entry = None
    for item in catalog.get('medicines', []):
        if item['item_id'] == item_id:
            item_entry = item
            break
    if not item_entry:
        for item in catalog.get('seeds', []):
            if item['item_id'] == item_id:
                item_entry = item
                break

    if not item_entry:
        flash("物品不存在")
        tab = request.args.get('tab', 'medicine')
        page = request.args.get('page', 1)
        return redirect(url_for('medicine.shop', npc_id=npc_id, tab=tab, page=page))

    # Check item definition exists
    item_def = DataService.get_item(item_id)
    if not item_def:
        flash("物品未定义")
        tab = request.args.get('tab', 'medicine')
        page = request.args.get('page', 1)
        return redirect(url_for('medicine.shop', npc_id=npc_id, tab=tab, page=page))

    total_price = item_entry['price'] * quantity

    # Check if player has enough money (bind gold + gold)
    from services.player_service import PlayerService as ps
    available_gold = player.gold
    if available_gold < total_price:
        flash(f"银两不足，需要{total_price}银两")
        tab = request.args.get('tab', 'medicine')
        page = request.args.get('page', 1)
        return redirect(url_for('medicine.shop', npc_id=npc_id, tab=tab, page=page))

    # Deduct gold and add item
    player.gold -= total_price
    DataService.add_item_to_inventory(player.id, item_id, quantity, is_bound=False)

    # 购买类任务进度（如主·购买金疮药）：买完即推进任务目标
    from services.quest_service import QuestService
    QuestService.update_buy_item_progress(player, item_id)

    from services import db
    db.session.commit()

    item_name = item_entry.get('name', item_def.get('name', '物品'))
    flash(f"成功花费{total_price}银两购买{quantity}个{item_name}")
    tab = request.args.get('tab', 'medicine')
    page = request.args.get('page', 1)
    return redirect(url_for('medicine.shop', npc_id=npc_id, tab=tab, page=page))