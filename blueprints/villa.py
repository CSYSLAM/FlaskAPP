from flask import Blueprint, render_template, redirect, url_for, request, session, flash
from flask_login import login_required, current_user
from services import db
from services.villa_service import VillaService, SEEDS
from services.data_service import DataService
from models.villa import Villa
from models.lieutenant import Lieutenant

villa_bp = Blueprint('villa', __name__, url_prefix='/villa')


@villa_bp.route("/")
@login_required
def index():
    player = current_user
    villa = VillaService.get_or_create_villa(player)
    training_status = VillaService.get_training_status(villa)
    garden_plots = VillaService.get_garden_status(villa)

    # Get defender info
    defender = None
    if villa.defender_id:
        defender = Lieutenant.query.get(villa.defender_id)

    return render_template("villa_index.html",
                         player=player,
                         villa=villa,
                         training_status=training_status,
                         garden_plots=garden_plots,
                         defender=defender,
                         SEEDS=SEEDS)


@villa_bp.route("/rename", methods=["POST"])
@login_required
def rename():
    player = current_user
    new_name = request.form.get("name", "").strip()
    success, msg = VillaService.update_name(player, new_name)
    flash(msg)
    return redirect(url_for('villa.index'))


@villa_bp.route("/set_defender", methods=["POST"])
@login_required
def set_defender():
    player = current_user
    lt_id = request.form.get("lieutenant_id")
    if lt_id:
        success, msg = VillaService.set_defender(player, int(lt_id))
    else:
        success, msg = VillaService.remove_defender(player)
    flash(msg)
    return redirect(url_for('villa.index'))


@villa_bp.route("/remove_defender")
@login_required
def remove_defender():
    player = current_user
    success, msg = VillaService.remove_defender(player)
    flash(msg)
    return redirect(url_for('villa.index'))


# --- Training Ground ---

@villa_bp.route("/training")
@login_required
def training_page():
    player = current_user
    villa = VillaService.get_or_create_villa(player)
    training_status = VillaService.get_training_status(villa)
    return render_template("villa_training.html",
                         player=player,
                         villa=villa,
                         training_status=training_status)


@villa_bp.route("/start_training")
@login_required
def start_training():
    player = current_user
    success, msg = VillaService.start_training(player)
    flash(msg)
    return redirect(url_for('villa.training_page'))


@villa_bp.route("/finish_training")
@login_required
def finish_training():
    player = current_user
    success, msg = VillaService.finish_training(player)
    flash(msg)
    return redirect(url_for('villa.training_page'))


# --- Garden ---

@villa_bp.route("/garden")
@login_required
def garden_page():
    player = current_user
    villa = VillaService.get_or_create_villa(player)
    plots = VillaService.get_garden_status(villa)

    # Get seeds in inventory
    seeds_inv = {}
    for seed_id in SEEDS:
        inv = DataService.get_inventory_item(player.id, seed_id)
        if inv and inv.quantity > 0:
            seeds_inv[seed_id] = inv.quantity

    return render_template("villa_garden.html",
                         player=player,
                         villa=villa,
                         plots=plots,
                         SEEDS=SEEDS,
                         seeds_inv=seeds_inv)


@villa_bp.route("/plant/<int:plot_index>", methods=["POST"])
@login_required
def plant_seed(plot_index):
    player = current_user
    seed_id = request.form.get("seed_id")
    if not seed_id:
        flash("请选择种子")
        return redirect(url_for('villa.garden_page'))

    success, msg = VillaService.plant_seed(player, plot_index, seed_id)
    flash(msg)
    return redirect(url_for('villa.garden_page'))


@villa_bp.route("/harvest/<int:plot_index>")
@login_required
def harvest_plot(plot_index):
    player = current_user
    success, msg = VillaService.harvest_plot(player, plot_index)
    flash(msg)
    return redirect(url_for('villa.garden_page'))


# --- Friend's Villa ---

@villa_bp.route("/friend")
@login_required
def friend_villa():
    player = current_user
    result = VillaService.get_random_friend_villa(player)
    if not result:
        flash("暂无好友山庄")
        return redirect(url_for('villa.index'))

    target_villa, target_player = result
    training_status = VillaService.get_training_status(target_villa)
    garden_plots = VillaService.get_garden_status(target_villa)

    # Get defender info
    defender = None
    if target_villa.defender_id:
        defender = Lieutenant.query.get(target_villa.defender_id)

    return render_template("villa_friend.html",
                         player=player,
                         target_player=target_player,
                         villa=target_villa,
                         training_status=training_status,
                         garden_plots=garden_plots,
                         defender=defender)


@villa_bp.route("/steal_plant/<int:owner_id>/<int:plot_index>")
@login_required
def steal_plant(owner_id, plot_index):
    player = current_user
    target_villa = Villa.query.filter_by(owner_id=owner_id).first()
    if not target_villa:
        flash("目标山庄不存在")
        return redirect(url_for('villa.friend_villa'))

    success, msg = VillaService.steal_plant(player, target_villa, plot_index)
    flash(msg)
    return redirect(url_for('villa.friend_villa'))


@villa_bp.route("/steal_training/<int:owner_id>")
@login_required
def steal_training(owner_id):
    player = current_user
    target_villa = Villa.query.filter_by(owner_id=owner_id).first()
    if not target_villa:
        flash("目标山庄不存在")
        return redirect(url_for('villa.friend_villa'))

    success, msg = VillaService.steal_training(player, target_villa)
    flash(msg)
    return redirect(url_for('villa.friend_villa'))


@villa_bp.route("/bless/<int:owner_id>")
@login_required
def bless_villa(owner_id):
    player = current_user
    target_villa = Villa.query.filter_by(owner_id=owner_id).first()
    if not target_villa:
        flash("目标山庄不存在")
        return redirect(url_for('villa.friend_villa'))

    success, msg = VillaService.bless_villa(player, target_villa)
    flash(msg)
    return redirect(url_for('villa.friend_villa'))


@villa_bp.route("/claim_blessing")
@login_required
def claim_blessing():
    player = current_user
    success, msg = VillaService.claim_blessing_reward(player)
    flash(msg)
    return redirect(url_for('villa.index'))
