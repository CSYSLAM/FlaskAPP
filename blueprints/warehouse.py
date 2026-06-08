from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from services.data_service import DataService
from services import db
from models.player import WarehouseItem

warehouse_bp = Blueprint('warehouse', __name__)


@warehouse_bp.route("/<npc_id>")
@login_required
def warehouse(npc_id):
    player = current_user
    monsters = DataService.get_monsters()
    monster_data = monsters.get(npc_id) or {}
    npc_name = monster_data.get('name', '金掌柜')
    return render_template("warehouse.html",
                         player=player,
                         npc_id=npc_id,
                         npc_name=npc_name)


@warehouse_bp.route("/silver/<npc_id>")
@login_required
def silver(npc_id):
    player = current_user
    monsters = DataService.get_monsters()
    monster_data = monsters.get(npc_id) or {}
    npc_name = monster_data.get('name', '金掌柜')
    return render_template("warehouse_silver.html",
                         player=player,
                         npc_id=npc_id,
                         npc_name=npc_name)


@warehouse_bp.route("/deposit_silver/<npc_id>", methods=["POST"])
@login_required
def deposit_silver(npc_id):
    player = current_user
    amount = int(request.form.get('amount', 0))
    if amount <= 0:
        flash("请输入有效的存入数量")
        return redirect(url_for('warehouse.silver', npc_id=npc_id))

    if player.gold < amount:
        flash("银两不足")
        return redirect(url_for('warehouse.silver', npc_id=npc_id))

    player.gold -= amount
    player.warehouse_gold += amount
    db.session.commit()
    flash(f"成功存入{amount}银两")
    return redirect(url_for('warehouse.silver', npc_id=npc_id))


@warehouse_bp.route("/withdraw_silver/<npc_id>", methods=["POST"])
@login_required
def withdraw_silver(npc_id):
    player = current_user
    amount = int(request.form.get('amount', 0))
    if amount <= 0:
        flash("请输入有效的取出数量")
        return redirect(url_for('warehouse.silver', npc_id=npc_id))

    if player.warehouse_gold < amount:
        flash("仓库银两不足")
        return redirect(url_for('warehouse.silver', npc_id=npc_id))

    player.warehouse_gold -= amount
    player.gold += amount
    db.session.commit()
    flash(f"成功取出{amount}银两")
    return redirect(url_for('warehouse.silver', npc_id=npc_id))


@warehouse_bp.route("/deposit/<npc_id>")
@login_required
def deposit(npc_id):
    player = current_user
    monsters = DataService.get_monsters()
    monster_data = monsters.get(npc_id) or {}
    npc_name = monster_data.get('name', '金掌柜')

    # Get player's backpack items
    inventory = DataService.get_inventory(player.id)
    items = []
    for inv_item in inventory:
        item_def = DataService.get_item(inv_item.item_id)
        if item_def:
            items.append({
                'item_id': inv_item.item_id,
                'name': item_def.get('name', inv_item.item_id),
                'quantity': inv_item.quantity,
                'is_bound': inv_item.is_bound,
                'capacity': item_def.get('capacity', 0.5)
            })

    # Pagination
    per_page = 20
    page = int(request.args.get('page', 1))
    total_items = len(items)
    total_pages = max(1, (total_items + per_page - 1) // per_page)
    if page < 1:
        page = 1
    if page > total_pages:
        page = total_pages

    start = (page - 1) * per_page
    page_items = items[start:start + per_page]

    # Calculate used capacity
    bp_used = DataService.get_backpack_used_capacity(player.id)
    bp_max = player.backpack_capacity
    wh_used = DataService.get_warehouse_used_capacity(player.id)
    wh_max = player.warehouse_capacity

    return render_template("warehouse_deposit.html",
                         player=player,
                         npc_id=npc_id,
                         npc_name=npc_name,
                         items=page_items,
                         page=page,
                         total_pages=total_pages,
                         per_page=per_page,
                         bp_used=bp_used,
                         bp_max=bp_max,
                         wh_used=wh_used,
                         wh_max=wh_max)


@warehouse_bp.route("/withdraw/<npc_id>")
@login_required
def withdraw(npc_id):
    player = current_user
    monsters = DataService.get_monsters()
    monster_data = monsters.get(npc_id) or {}
    npc_name = monster_data.get('name', '金掌柜')

    # Get player's warehouse items
    warehouse_items = WarehouseItem.query.filter_by(player_id=player.id).all()
    items = []
    for wh_item in warehouse_items:
        item_def = DataService.get_item(wh_item.item_id)
        if item_def:
            items.append({
                'item_id': wh_item.item_id,
                'name': item_def.get('name', wh_item.item_id),
                'quantity': wh_item.quantity,
                'is_bound': wh_item.is_bound,
                'capacity': item_def.get('capacity', 0.5)
            })

    # Pagination
    per_page = 20
    page = int(request.args.get('page', 1))
    total_items = len(items)
    total_pages = max(1, (total_items + per_page - 1) // per_page)
    if page < 1:
        page = 1
    if page > total_pages:
        page = total_pages

    start = (page - 1) * per_page
    page_items = items[start:start + per_page]

    # Calculate capacities
    bp_used = DataService.get_backpack_used_capacity(player.id)
    bp_max = player.backpack_capacity
    wh_used = DataService.get_warehouse_used_capacity(player.id)
    wh_max = player.warehouse_capacity

    return render_template("warehouse_withdraw.html",
                         player=player,
                         npc_id=npc_id,
                         npc_name=npc_name,
                         items=page_items,
                         page=page,
                         total_pages=total_pages,
                         per_page=per_page,
                         bp_used=bp_used,
                         bp_max=bp_max,
                         wh_used=wh_used,
                         wh_max=wh_max)


@warehouse_bp.route("/do_deposit/<npc_id>/<item_id>", methods=["POST"])
@login_required
def do_deposit(npc_id, item_id):
    player = current_user
    quantity = int(request.form.get('quantity', 1))
    if quantity < 1:
        flash("数量无效")
        return redirect(url_for('warehouse.deposit', npc_id=npc_id))

    # Find the item in player's inventory
    inv_item = DataService.get_inventory_item(player.id, item_id)
    if not inv_item or inv_item.quantity < quantity:
        flash("背包中物品数量不足")
        return redirect(url_for('warehouse.deposit', npc_id=npc_id))

    # Check warehouse capacity
    item_def = DataService.get_item(item_id)
    item_capacity = item_def.get('capacity', 0.5) if item_def else 0.5
    current_wh_capacity = DataService.get_warehouse_used_capacity(player.id)
    new_capacity = current_wh_capacity + item_capacity * quantity
    if new_capacity > player.warehouse_capacity:
        flash("仓库容量不足")
        return redirect(url_for('warehouse.deposit', npc_id=npc_id))

    # Remove from inventory and add to warehouse
    DataService.remove_item_from_inventory(player.id, item_id, quantity)

    # Add or update warehouse item
    wh_item = WarehouseItem.query.filter_by(
        player_id=player.id, item_id=item_id, is_bound=inv_item.is_bound).first()
    if wh_item:
        wh_item.quantity += quantity
    else:
        wh_item = WarehouseItem(
            player_id=player.id,
            item_id=item_id,
            quantity=quantity,
            is_bound=inv_item.is_bound)
        db.session.add(wh_item)

    db.session.commit()
    flash(f"成功存入{quantity}个{item_def.get('name', item_id)}")
    return redirect(url_for('warehouse.deposit', npc_id=npc_id))


@warehouse_bp.route("/do_withdraw/<npc_id>/<item_id>", methods=["POST"])
@login_required
def do_withdraw(npc_id, item_id):
    player = current_user
    quantity = int(request.form.get('quantity', 1))
    if quantity < 1:
        flash("数量无效")
        return redirect(url_for('warehouse.withdraw', npc_id=npc_id))

    # Find the item in warehouse
    wh_item = WarehouseItem.query.filter_by(player_id=player.id, item_id=item_id).first()
    if not wh_item or wh_item.quantity < quantity:
        flash("仓库中物品数量不足")
        return redirect(url_for('warehouse.withdraw', npc_id=npc_id))

    # Check backpack capacity
    item_def = DataService.get_item(item_id)
    item_capacity = item_def.get('capacity', 0.5) if item_def else 0.5
    current_bp_capacity = DataService.get_backpack_used_capacity(player.id)
    new_capacity = current_bp_capacity + item_capacity * quantity
    if new_capacity > player.backpack_capacity:
        flash("背包容量不足")
        return redirect(url_for('warehouse.withdraw', npc_id=npc_id))

    # Remove from warehouse and add to inventory
    wh_item.quantity -= quantity
    if wh_item.quantity <= 0:
        db.session.delete(wh_item)

    DataService.add_item_to_inventory(player.id, item_id, quantity, is_bound=wh_item.is_bound)

    db.session.commit()
    flash(f"成功取出{quantity}个{item_def.get('name', item_id)}")
    return redirect(url_for('warehouse.withdraw', npc_id=npc_id))
