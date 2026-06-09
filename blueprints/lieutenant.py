from flask import Blueprint, render_template, redirect, url_for, request, session, flash
from flask_login import login_required, current_user
from services import db
from services.data_service import DataService
from services.lieutenant_service import LieutenantService, LIEUTENANT_SKILLS, LIEUTENANT_DATA, TIER_NAMES
from models.lieutenant import Lieutenant

lieutenant_bp = Blueprint('lieutenant', __name__, url_prefix='/lieutenant')


@lieutenant_bp.route("/")
@login_required
def index():
    player = current_user
    lieutenants = LieutenantService.get_lieutenants(player)
    max_slots = LieutenantService.get_max_slots(player)
    return render_template("lieutenant_list.html",
                         player=player,
                         lieutenants=lieutenants,
                         max_slots=max_slots,
                         TIER_NAMES=TIER_NAMES)


@lieutenant_bp.route("/recruit")
@login_required
def recruit_page():
    return redirect(url_for('commander.recruit_page'))


@lieutenant_bp.route("/detail/<int:lt_id>")
@login_required
def detail(lt_id):
    player = current_user
    lt = Lieutenant.query.filter_by(id=lt_id, owner_id=player.id).first()
    if not lt:
        flash("副将不存在")
        return redirect(url_for('lieutenant.index'))
    return render_template("lieutenant_detail.html",
                         player=player,
                         lieutenant=lt,
                         LieutenantService=LieutenantService)


@lieutenant_bp.route("/wash_quality/<int:lt_id>")
@login_required
def wash_quality(lt_id):
    player = current_user
    lt = Lieutenant.query.filter_by(id=lt_id, owner_id=player.id).first()
    if not lt:
        flash("副将不存在")
        return redirect(url_for('lieutenant.index'))
    success, msg = LieutenantService.wash_quality(lt)
    flash(msg)
    return redirect(url_for('lieutenant.detail', lt_id=lt_id))


@lieutenant_bp.route("/enlighten/<int:lt_id>")
@login_required
def enlighten(lt_id):
    player = current_user
    lt = Lieutenant.query.filter_by(id=lt_id, owner_id=player.id).first()
    if not lt:
        flash("副将不存在")
        return redirect(url_for('lieutenant.index'))
    success, msg = LieutenantService.enlighten(lt)
    flash(msg)
    return redirect(url_for('lieutenant.detail', lt_id=lt_id))


@lieutenant_bp.route("/reinforce/<int:lt_id>")
@login_required
def reinforce(lt_id):
    player = current_user
    lt = Lieutenant.query.filter_by(id=lt_id, owner_id=player.id).first()
    if not lt:
        flash("副将不存在")
        return redirect(url_for('lieutenant.index'))
    success, msg = LieutenantService.reinforce(lt)
    flash(msg)
    return redirect(url_for('lieutenant.detail', lt_id=lt_id))


@lieutenant_bp.route("/restore_loyalty/<int:lt_id>")
@login_required
def restore_loyalty(lt_id):
    player = current_user
    lt = Lieutenant.query.filter_by(id=lt_id, owner_id=player.id).first()
    if not lt:
        flash("副将不存在")
        return redirect(url_for('lieutenant.index'))
    success, msg = LieutenantService.restore_loyalty(lt)
    flash(msg)
    return redirect(url_for('lieutenant.detail', lt_id=lt_id))


@lieutenant_bp.route("/restore_lifespan/<int:lt_id>")
@login_required
def restore_lifespan(lt_id):
    player = current_user
    lt = Lieutenant.query.filter_by(id=lt_id, owner_id=player.id).first()
    if not lt:
        flash("副将不存在")
        return redirect(url_for('lieutenant.index'))
    success, msg = LieutenantService.restore_lifespan(lt)
    flash(msg)
    return redirect(url_for('lieutenant.detail', lt_id=lt_id))


@lieutenant_bp.route("/deploy/<int:lt_id>")
@login_required
def deploy(lt_id):
    player = current_user
    lt = Lieutenant.query.filter_by(id=lt_id, owner_id=player.id).first()
    if not lt:
        flash("副将不存在")
        return redirect(url_for('lieutenant.index'))
    success, msg = LieutenantService.deploy(lt)
    flash(msg)
    return redirect(url_for('lieutenant.index'))


@lieutenant_bp.route("/recall/<int:lt_id>")
@login_required
def recall(lt_id):
    player = current_user
    lt = Lieutenant.query.filter_by(id=lt_id, owner_id=player.id).first()
    if not lt:
        flash("副将不存在")
        return redirect(url_for('lieutenant.index'))
    success, msg = LieutenantService.recall(lt)
    flash(msg)
    return redirect(url_for('lieutenant.index'))


@lieutenant_bp.route("/set_position/<int:lt_id>/<position>")
@login_required
def set_position(lt_id, position):
    player = current_user
    lt = Lieutenant.query.filter_by(id=lt_id, owner_id=player.id).first()
    if not lt:
        flash("副将不存在")
        return redirect(url_for('lieutenant.index'))
    success, msg = LieutenantService.set_position(lt, position)
    flash(msg)
    return redirect(url_for('lieutenant.detail', lt_id=lt_id))


@lieutenant_bp.route("/skills/<int:lt_id>")
@login_required
def skills_page(lt_id):
    player = current_user
    lt = Lieutenant.query.filter_by(id=lt_id, owner_id=player.id).first()
    if not lt:
        flash("副将不存在")
        return redirect(url_for('lieutenant.index'))
    available = LieutenantService.get_available_skills(lt)
    return render_template("lieutenant_skills.html",
                         player=player,
                         lieutenant=lt,
                         available_skills=available,
                         skill_defs=LIEUTENANT_SKILLS,
                         LieutenantService=LieutenantService)


@lieutenant_bp.route("/learn_skill/<int:lt_id>/<skill_id>")
@login_required
def learn_skill(lt_id, skill_id):
    player = current_user
    lt = Lieutenant.query.filter_by(id=lt_id, owner_id=player.id).first()
    if not lt:
        flash("副将不存在")
        return redirect(url_for('lieutenant.index'))
    success, msg = LieutenantService.learn_skill(lt, skill_id, level=1)
    flash(msg)
    return redirect(url_for('lieutenant.skills_page', lt_id=lt_id))


@lieutenant_bp.route("/upgrade_skill/<int:lt_id>/<skill_id>")
@login_required
def upgrade_skill(lt_id, skill_id):
    player = current_user
    lt = Lieutenant.query.filter_by(id=lt_id, owner_id=player.id).first()
    if not lt:
        flash("副将不存在")
        return redirect(url_for('lieutenant.index'))
    success, msg = LieutenantService.upgrade_skill(lt, skill_id)
    flash(msg)
    return redirect(url_for('lieutenant.skills_page', lt_id=lt_id))


@lieutenant_bp.route("/forget_skill/<int:lt_id>/<skill_id>")
@login_required
def forget_skill(lt_id, skill_id):
    player = current_user
    lt = Lieutenant.query.filter_by(id=lt_id, owner_id=player.id).first()
    if not lt:
        flash("副将不存在")
        return redirect(url_for('lieutenant.index'))
    success, msg = LieutenantService.forget_skill(lt, skill_id)
    flash(msg)
    return redirect(url_for('lieutenant.skills_page', lt_id=lt_id))


@lieutenant_bp.route("/skill_detail/<int:lt_id>/<skill_id>")
@login_required
def skill_detail(lt_id, skill_id):
    player = current_user
    lt = Lieutenant.query.filter_by(id=lt_id, owner_id=player.id).first()
    if not lt:
        flash("副将不存在")
        return redirect(url_for('lieutenant.index'))
    sdef = LieutenantService.get_lt_skill_def(skill_id)
    if not sdef:
        flash("技能不存在")
        return redirect(url_for('lieutenant.skills_page', lt_id=lt_id))

    # Find current skill level
    current_level = 0
    for sk in lt.skills:
        if sk.get('id') == skill_id:
            current_level = sk.get('level', 1)
            break

    return render_template("lieutenant_skill_detail.html",
                         player=player,
                         lieutenant=lt,
                         skill_id=skill_id,
                         skill_def=sdef,
                         current_level=current_level,
                         LieutenantService=LieutenantService)


@lieutenant_bp.route("/expand_skill_slots/<int:lt_id>")
@login_required
def expand_skill_slots(lt_id):
    player = current_user
    lt = Lieutenant.query.filter_by(id=lt_id, owner_id=player.id).first()
    if not lt:
        flash("副将不存在")
        return redirect(url_for('lieutenant.index'))
    success, msg = LieutenantService.expand_skill_slots(lt)
    flash(msg)
    return redirect(url_for('lieutenant.skills_page', lt_id=lt_id))


@lieutenant_bp.route("/expand_slots")
@login_required
def expand_slots():
    player = current_user
    success, msg = LieutenantService.expand_slots(player)
    flash(msg)
    return redirect(url_for('lieutenant.index'))


@lieutenant_bp.route("/banish/<int:lt_id>")
@login_required
def banish(lt_id):
    player = current_user
    lt = Lieutenant.query.filter_by(id=lt_id, owner_id=player.id).first()
    if not lt:
        flash("副将不存在")
        return redirect(url_for('lieutenant.index'))
    success, msg = LieutenantService.banish(lt)
    flash(msg)
    return redirect(url_for('lieutenant.index'))


@lieutenant_bp.route("/use_soul/<soul_item_id>")
@login_required
def use_soul(soul_item_id):
    player = current_user
    success, msg = LieutenantService.use_soul(player, soul_item_id)
    flash(msg)
    return redirect(url_for('lieutenant.index'))