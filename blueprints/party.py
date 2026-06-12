from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from services.party_service import PartyService, is_player_online
from services.data_service import DataService
from models.player import PlayerModel
from services import db

party_bp = Blueprint('party', __name__)


@party_bp.route("/")
@login_required
def index():
    player = current_user
    party = PartyService.get_player_party(player)
    pending_invites = PartyService.get_pending_invites(player)

    if party:
        members = []
        online_member_ids = set()
        for mid in party.members:
            p = PlayerModel.query.get(mid)
            if p:
                members.append(p)
                if is_player_online(mid):
                    online_member_ids.add(mid)
        online_count = len(online_member_ids)
        bonus_pct = online_count
        return render_template("party.html",
                             player=player,
                             party=party,
                             members=members,
                             online_count=online_count,
                             online_member_ids=online_member_ids,
                             bonus_pct=bonus_pct,
                             pending_invites=pending_invites,
                             max_size=5,
                             DataService=DataService)

    return render_template("party.html",
                         player=player,
                         party=None,
                         members=[],
                         online_count=0,
                         online_member_ids=set(),
                         bonus_pct=0,
                         pending_invites=pending_invites,
                         max_size=5,
                         DataService=DataService)


@party_bp.route("/create")
@login_required
def create():
    player = current_user
    party, error = PartyService.create_party(player)
    if error:
        flash(error)
    else:
        flash("队伍创建成功")
    return redirect(url_for('party.index'))


@party_bp.route("/leave")
@login_required
def leave():
    player = current_user
    success, msg = PartyService.leave_party(player)
    flash(msg)
    return redirect(url_for('party.index'))


@party_bp.route("/invite/<int:target_id>")
@login_required
def invite(target_id):
    player = current_user
    success, msg = PartyService.invite_player(player, target_id)
    flash(msg)
    target = PlayerModel.query.get(target_id)
    if target:
        return redirect(url_for('player.view_player', username=target.username))
    return redirect(url_for('party.index'))


@party_bp.route("/apply/<int:party_id>")
@login_required
def apply(party_id):
    player = current_user
    success, msg = PartyService.apply_to_party(player, party_id)
    flash(msg)
    return redirect(url_for('party.index'))


@party_bp.route("/accept_invite/<int:party_id>")
@login_required
def accept_invite(party_id):
    player = current_user
    success, msg = PartyService.accept_invite(player, party_id)
    if success:
        flash("已加入队伍")
    else:
        flash(msg)
    return redirect(url_for('party.index'))


@party_bp.route("/accept_application/<int:applicant_id>")
@login_required
def accept_application(applicant_id):
    player = current_user
    success, msg = PartyService.accept_application(player, applicant_id)
    if msg:
        flash(msg)
    elif success:
        flash("已同意申请")
    return redirect(url_for('party.index'))


@party_bp.route("/reject_application/<int:applicant_id>")
@login_required
def reject_application(applicant_id):
    player = current_user
    success, msg = PartyService.reject_application(player, applicant_id)
    flash(msg)
    return redirect(url_for('party.index'))


@party_bp.route("/kick/<int:target_id>")
@login_required
def kick(target_id):
    player = current_user
    success, msg = PartyService.kick_member(player, target_id)
    flash(msg)
    return redirect(url_for('party.index'))
