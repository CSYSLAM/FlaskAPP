from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from services import db
from services.shop_service import ShopService
from services.data_service import DataService

shop_bp = Blueprint('shop', __name__)


@shop_bp.route("/")
@shop_bp.route("/<shop_id>")
@login_required
def shop(shop_id='jinzu'):
    player = current_user
    tab = request.args.get('tab', None)
    page = request.args.get('page', 1)
    search = request.args.get('search', '')
    shop_data = ShopService.get_shop_data(shop_id, tab=tab, page=page, search=search)
    if not shop_data:
        flash("商店不存在")
        return redirect(url_for("game.scene"))

    # Build list of all shops for navigation
    all_shops = ShopService.get_all_shops()

    return render_template("shop.html",
                         player=player,
                         shop_data=shop_data,
                         shop_id=shop_id,
                         all_shops=all_shops,
                         DataService=DataService)


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

    success, msg = ShopService.buy_item(player, shop_id, item_id, quantity)
    flash(msg)

    # Redirect back to same shop/tab. The test shop is paginated + searchable,
    # so preserve those params; other shops only need the tab.
    tab = request.args.get('tab', '')
    if shop_id == 'test':
        return redirect(url_for('shop.shop', shop_id=shop_id, tab=tab,
                                search=request.args.get('search', ''),
                                page=request.args.get('page', 1)))
    if tab:
        return redirect(url_for('shop.shop', shop_id=shop_id, tab=tab))
    return redirect(url_for('shop.shop', shop_id=shop_id))
