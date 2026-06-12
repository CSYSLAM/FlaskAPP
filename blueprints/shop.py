from flask import Blueprint, render_template, redirect, url_for, request, session, flash
from flask_login import login_required, current_user
from models.player import EquipmentInstance
from services import db
from services.data_service import DataService
from services.shop_service import ShopService
from services.equipment_service import EquipmentService

shop_bp = Blueprint('shop', __name__)


@shop_bp.route("/")
@shop_bp.route("/<shop_id>")
@login_required
def shop(shop_id='default'):
    player = current_user
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 10))
    shop_data = ShopService.get_shop_data(shop_id, page=page, per_page=per_page)
    if not shop_data:
        flash("商店不存在")
        return redirect(url_for("game.scene"))
    return render_template("shop.html",
                         player=player,
                         shop_data=shop_data,
                         shop_type=shop_id,
                         shop_id=shop_id)


@shop_bp.route("/buy/<shop_id>/<item_id>", methods=["POST"])
@login_required
def buy_item(shop_id, item_id):
    player = current_user
    try:
        quantity = int(request.form.get('quantity', 1))
    except (ValueError, TypeError):
        quantity = 1
    if quantity <= 0:
        quantity = 1
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 10))
    success, msg = ShopService.buy_item(player, shop_id, item_id, quantity)
    flash(msg)
    return redirect(url_for('shop.shop', shop_id=shop_id, page=page, per_page=per_page))


@shop_bp.route("/buy_equipment/<shop_id>/<template_id>", methods=["POST"])
@login_required
def buy_equipment(shop_id, template_id):
    player = current_user
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 10))
    success, msg = ShopService.buy_equipment(player, shop_id, template_id)
    flash(msg)
    return redirect(url_for('shop.shop', shop_id=shop_id, page=page, per_page=per_page))


@shop_bp.route("/sell/<item_id>", methods=["POST"])
@login_required
def sell_item(item_id):
    player = current_user
    quantity = int(request.form.get('quantity', 1))
    success, msg, price = ShopService.sell_item(player, item_id, quantity)
    flash(msg)
    return redirect(request.referrer or url_for('player.inventory'))