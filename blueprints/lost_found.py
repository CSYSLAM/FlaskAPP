from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from services.data_service import DataService
from services import db
from services.lost_found_service import (
    LostItemLifecycle, grant_lost_item, _resolve_item_name, get_redeem_price)
from models.player import LostItem
from datetime import datetime, timedelta

lost_found_bp = Blueprint('lost_found', __name__)


@lost_found_bp.route("/")
@login_required
def lost_found():
    player = current_user
    now = datetime.now()

    # 惰性推进失物状态机（持有->拍卖->结算），无需独立定时任务
    LostItemLifecycle.run()

    # Get player's lost items in holding stage
    holding_items = LostItem.query.filter_by(
        player_id=player.id, stage='holding').all()

    # Get auction items (stage='auction')
    auction_items = LostItem.query.filter_by(stage='auction').all()

    # Format holding items
    holding = []
    for item in holding_items:
        days_left = 30 - (now - item.lost_at).days
        if days_left > 0:
            holding.append({
                'id': item.id,
                'item_id': item.item_id,
                'name': _resolve_item_name(item.item_id),
                'quantity': item.quantity,
                'is_bound': item.is_bound,
                'days_left': days_left,
                'lost_at': item.lost_at,
                'redeem_price': get_redeem_price(item)
            })

    # Format auction items
    auctions = []
    for item in auction_items:
        if item.auction_started_at:
            days_left = 7 - (now - item.auction_started_at).days
            if days_left > 0:
                auctions.append({
                    'id': item.id,
                    'item_id': item.item_id,
                    'name': _resolve_item_name(item.item_id),
                    'quantity': item.quantity,
                    'is_bound': item.is_bound,
                    'current_bid': item.current_bid,
                    'days_left': days_left
                })

    ticket = DataService.get_inventory_item(player.id, 'redemption_ticket')
    ticket_count = ticket.quantity if ticket else 0

    return render_template("lost_found.html",
                         player=player,
                         holding=holding,
                         auctions=auctions,
                         ticket_count=ticket_count)


@lost_found_bp.route("/redeem/<int:item_id>", methods=["POST"])
@login_required
def redeem(item_id):
    player = current_user
    lost_item = LostItem.query.filter_by(
        id=item_id, player_id=player.id, stage='holding').first()

    if not lost_item:
        flash("物品不存在或已过期")
        return redirect(url_for('lost_found.lost_found'))

    # Check if player has redemption ticket
    has_ticket = False
    inventory = DataService.get_inventory(player.id)
    for inv in inventory:
        if inv.item_id == 'redemption_ticket' and inv.quantity >= 1:
            has_ticket = True
            break

    if not has_ticket:
        flash("需要赎金券才能取回物品")
        return redirect(url_for('lost_found.lost_found'))

    # Check backpack capacity
    item_def = DataService.get_item(lost_item.item_id)
    item_capacity = item_def.get('capacity', 0.5) if item_def else 0.5
    current_bp_capacity = DataService.get_backpack_used_capacity(player.id)
    new_capacity = current_bp_capacity + item_capacity * lost_item.quantity
    if new_capacity > player.backpack_capacity:
        flash("背包容量不足")
        return redirect(url_for('lost_found.lost_found'))

    # 赎回价：物品卖出价 1:1
    redeem_price = get_redeem_price(lost_item)
    if player.gold < redeem_price:
        flash(f"银两不足，赎回需{redeem_price}银两")
        return redirect(url_for('lost_found.lost_found'))

    # Consume redemption ticket + 扣银两
    DataService.remove_item_from_inventory(player.id, 'redemption_ticket', 1)
    player.gold -= redeem_price

    # Add item to inventory (装备同步转移实例归属)
    grant_lost_item(player.id, lost_item)

    # Delete lost item record
    db.session.delete(lost_item)
    db.session.commit()

    flash(f"成功取回{_resolve_item_name(lost_item.item_id)}（花费{redeem_price}银两）")
    return redirect(url_for('lost_found.lost_found'))


@lost_found_bp.route("/buy_ticket", methods=["POST"])
@login_required
def buy_ticket():
    player = current_user
    if player.gold < 5:
        flash("银两不足，赎金券需5银两")
        return redirect(url_for('lost_found.lost_found'))
    player.gold -= 5
    DataService.add_item_to_inventory(player.id, 'redemption_ticket', 1)
    db.session.commit()
    flash("购买赎金券x1（花费5银两）")
    return redirect(url_for('lost_found.lost_found'))


@lost_found_bp.route("/bid/<int:item_id>", methods=["POST"])
@login_required
def bid(item_id):
    player = current_user
    bid_amount = int(request.form.get('bid', 0))

    if bid_amount <= 0:
        flash("出价无效")
        return redirect(url_for('lost_found.lost_found'))

    lost_item = LostItem.query.filter_by(id=item_id, stage='auction').first()
    if not lost_item:
        flash("物品不存在或拍卖已结束")
        return redirect(url_for('lost_found.lost_found'))

    if player.gold < bid_amount:
        flash("银两不足")
        return redirect(url_for('lost_found.lost_found'))

    if bid_amount <= lost_item.current_bid:
        flash("出价必须高于当前最高价")
        return redirect(url_for('lost_found.lost_found'))

    # Refund previous bidder if exists
    if lost_item.current_bidder_id:
        prev_bidder = DataService.get_player_by_id(lost_item.current_bidder_id)
        if prev_bidder:
            prev_bidder.gold += lost_item.current_bid

    # Deduct gold from current bidder
    player.gold -= bid_amount
    lost_item.current_bid = bid_amount
    lost_item.current_bidder_id = player.id
    db.session.commit()

    flash(f"出价成功：{bid_amount}银两")
    return redirect(url_for('lost_found.lost_found'))
