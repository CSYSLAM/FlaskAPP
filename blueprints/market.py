"""集市蓝图：玩家间自由交易。

入口在场景界面「副将」后。路由列表：
- GET  /            集市首页（筛选/排序/分页 + 置顶区）
- GET  /my          我的挂单
- GET  /list        上架表单
- POST /list        创建挂单
- GET  /view/<id>   挂单详情 + 购买
- POST /buy/<id>    购买
- POST /cancel/<id> 取消挂单
"""

from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user

from services.market_service import MarketService, PER_PAGE_DEFAULT
from models.player import PlayerModel

market_bp = Blueprint('market', __name__)


@market_bp.route("/")
@login_required
def index():
    MarketService.expire_listings()
    category = request.args.get('category', '全部')
    search = (request.args.get('search') or '').strip()
    sort = request.args.get('sort', 'new')
    try:
        page = max(1, int(request.args.get('page') or 1))
    except (TypeError, ValueError):
        page = 1

    rows, total, total_pages, page, per_page, pinned = MarketService.get_listings(
        category=category, search=search, sort=sort,
        page=page, per_page=PER_PAGE_DEFAULT)

    listings = [MarketService._format_listing(r) for r in rows]
    pinned_fmt = [MarketService._format_listing(r) for r in pinned]

    return render_template("market.html", player=current_user,
                           listings=listings, pinned=pinned_fmt,
                           category=category, search=search, sort=sort,
                           page=page, total_pages=total_pages,
                           per_page=per_page, total=total)


@market_bp.route("/my")
@login_required
def my():
    MarketService.expire_listings()
    mine = MarketService.get_player_listings(current_user.id)
    listings = [MarketService._format_listing(r) for r in mine]
    cap = MarketService.get_listing_cap(current_user)
    return render_template("market_my.html", player=current_user,
                           listings=listings, cap=cap,
                           active_count=len(listings))


@market_bp.route("/history")
@login_required
def history():
    tab = request.args.get('tab', 'buy')  # buy=我的购买, sell=我的出售
    purchases = MarketService.get_my_purchases(current_user.id)
    sales = MarketService.get_my_sales(current_user.id)

    # 解析交易对手昵称：购买看卖家，出售看买家
    ids = (set(t.buyer_id for t in purchases) | set(t.seller_id for t in purchases) |
           set(t.buyer_id for t in sales) | set(t.seller_id for t in sales))
    names = {p.id: p.nickname for p in
             PlayerModel.query.filter(PlayerModel.id.in_(ids)).all()} if ids else {}

    return render_template("market_history.html", player=current_user,
                           tab=tab, purchases=purchases, sales=sales, names=names)


@market_bp.route("/list")
@login_required
def list_form():
    items = MarketService.get_listable_items(current_user)
    equipment = MarketService.get_listable_equipment(current_user)
    cap = MarketService.get_listing_cap(current_user)
    active_count = MarketService.get_active_count(current_user.id)
    return render_template("market_list.html", player=current_user,
                           items=items, equipment=equipment,
                           cap=cap, active_count=active_count)


@market_bp.route("/list", methods=["POST"])
@login_required
def create():
    item_id = request.form.get('item_id') or None
    equip_id = request.form.get('equipment_instance_id') or None
    quantity = request.form.get('quantity', 1)
    unit_price = request.form.get('unit_price', 0)
    ad_tier = request.form.get('ad_tier', 0)

    ok, msg = MarketService.create_listing(
        current_user,
        item_id=item_id,
        equipment_instance_id=equip_id,
        quantity=quantity,
        unit_price=unit_price,
        ad_tier=ad_tier,
    )
    flash(msg)
    return redirect(url_for('market.my') if ok else url_for('market.list_form'))


@market_bp.route("/view/<int:listing_id>")
@login_required
def view(listing_id):
    MarketService.expire_listings()
    listing = MarketService.get_listing(listing_id)
    if not listing:
        flash("挂单不存在或已结束")
        return redirect(url_for('market.index'))
    fmt = MarketService._format_listing(listing)
    return render_template("market_view.html", player=current_user, listing=fmt)


@market_bp.route("/buy/<int:listing_id>", methods=["POST"])
@login_required
def buy(listing_id):
    buy_quantity = request.form.get('quantity', 1)
    ok, msg = MarketService.buy_listing(current_user, listing_id, buy_quantity)
    flash(msg)
    if ok:
        return redirect(url_for('market.index'))
    return redirect(url_for('market.view', listing_id=listing_id))


@market_bp.route("/cancel/<int:listing_id>", methods=["POST"])
@login_required
def cancel(listing_id):
    ok, msg = MarketService.cancel_listing(current_user, listing_id)
    flash(msg)
    return redirect(url_for('market.my'))
