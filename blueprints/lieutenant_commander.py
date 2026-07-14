from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from services.data_service import DataService
from services.lieutenant_service import LieutenantService, LIEUTENANT_DATA, TIER_NAMES, TIER_FRAGMENTS, DECOMPOSE_GOLD_COST, SYNTHESIZE_FRAGMENTS, RECRUIT_GOLD_COST, NORMAL_LIEUTENANT_NAMES
from models.lieutenant import Lieutenant

commander_bp = Blueprint('commander', __name__, url_prefix='/commander')


@commander_bp.route("/")
@login_required
def index():
    player = current_user
    lt_count = Lieutenant.query.filter_by(owner_id=player.id).count()
    max_slots = LieutenantService.get_max_slots(player)
    return render_template("commander.html",
                         player=player,
                         lt_count=lt_count,
                         max_slots=max_slots)


@commander_bp.route("/recruit")
@login_required
def recruit_page():
    player = current_user
    lt_count = Lieutenant.query.filter_by(owner_id=player.id).count()
    max_slots = LieutenantService.get_max_slots(player)
    token_inv = DataService.get_inventory_item(player.id, 'lt_recruit')
    token_count = token_inv.quantity if token_inv else 0
    return render_template("commander_recruit.html",
                         player=player,
                         lt_count=lt_count,
                         max_slots=max_slots,
                         token_count=token_count)


@commander_bp.route("/do_recruit/<method>")
@login_required
def do_recruit(method):
    player = current_user
    lt, msg = LieutenantService.recruit(player, method=method)
    flash(msg)
    return redirect(url_for('commander.recruit_page'))


@commander_bp.route("/decompose")
@login_required
def decompose():
    player = current_user
    tier = int(request.args.get('tier', 3))
    if tier not in (1, 2, 3):
        tier = 3

    all_souls = LieutenantService.get_player_souls(player)
    souls = all_souls.get(tier, [])

    # Pagination
    per_page = 12
    page = int(request.args.get('page', 1))
    total_items = len(souls)
    total_pages = max(1, (total_items + per_page - 1) // per_page)
    if page < 1:
        page = 1
    if page > total_pages:
        page = total_pages

    start = (page - 1) * per_page
    page_souls = souls[start:start + per_page]

    return render_template("commander_decompose.html",
                         player=player,
                         tier=tier,
                         souls=page_souls,
                         page=page,
                         total_pages=total_pages,
                         fragment_value=TIER_FRAGMENTS[tier],
                         decompose_cost=DECOMPOSE_GOLD_COST)


@commander_bp.route("/do_decompose/<soul_item_id>")
@login_required
def do_decompose(soul_item_id):
    player = current_user
    success, msg = LieutenantService.decompose_soul(player, soul_item_id)
    flash(msg)
    # Determine tier from soul_item_id
    from services.lieutenant_service import SOUL_TO_LT
    tier = 3
    if soul_item_id in SOUL_TO_LT:
        tier = SOUL_TO_LT[soul_item_id][0]
    return redirect(url_for('commander.decompose', tier=tier))


@commander_bp.route("/synthesize")
@login_required
def synthesize():
    player = current_user
    frag_inv = DataService.get_inventory_item(player.id, 'soul_flag_shard')
    frag_count = frag_inv.quantity if frag_inv else 0
    banner_inv = DataService.get_inventory_item(player.id, 'soul_banner')
    banner_count = banner_inv.quantity if banner_inv else 0
    return render_template("commander_synthesize.html",
                         player=player,
                         frag_count=frag_count,
                         banner_count=banner_count,
                         required_frags=SYNTHESIZE_FRAGMENTS)


@commander_bp.route("/do_synthesize")
@login_required
def do_synthesize():
    player = current_user
    success, msg = LieutenantService.synthesize_banner(player)
    flash(msg)
    return redirect(url_for('commander.synthesize'))


@commander_bp.route("/use_banner")
@login_required
def use_banner():
    player = current_user
    success, msg = LieutenantService.use_soul_banner(player)
    flash(msg)
    return redirect(url_for('commander.synthesize'))
