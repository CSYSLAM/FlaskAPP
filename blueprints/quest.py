from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import login_required, current_user
from services.data_service import DataService
from services.quest_service import QuestService
from services import db

quest_bp = Blueprint('quest', __name__, url_prefix='/quest')


@quest_bp.route("/")
@login_required
def quest_list():
    player = current_user
    active = QuestService.get_active_quests(player)
    completed = QuestService.get_completed_quests(player)
    all_quests = QuestService.get_all_quests()

    active_list = []
    for qid, progress in active.items():
        q = all_quests.get(qid)
        if q:
            q_copy = dict(q)
            q_copy['progress'] = progress.get('progress', 0)
            q_copy['target'] = progress.get('target', 1)
            q_copy['is_ready'] = q_copy['progress'] >= q_copy['target']
            active_list.append(q_copy)

    return render_template("quest_list.html", player=player,
                         active_list=active_list, completed=completed,
                         all_quests=all_quests)


@quest_bp.route("/available")
@login_required
def available_quests():
    player = current_user
    all_quests = QuestService.get_all_quests()
    completed = QuestService.get_completed_quests(player)
    active = QuestService.get_active_quests(player)

    available = []
    for qid, q in all_quests.items():
        if qid not in completed and qid not in active:
            ok, _ = QuestService.can_accept_quest(player, qid)
            if ok:
                available.append(q)

    return render_template("quest_available.html", player=player,
                         available=available)


@quest_bp.route("/detail/<quest_id>")
@login_required
def quest_detail(quest_id):
    player = current_user
    q = QuestService.get_quest(quest_id)
    if not q:
        return redirect(url_for('quest.quest_list'))

    active = QuestService.get_active_quests(player)
    is_active = quest_id in active
    progress = active.get(quest_id, {})
    is_ready = progress.get('progress', 0) >= progress.get('target', 1) if progress else False
    q_copy = dict(q)
    if is_active:
        q_copy['progress'] = progress.get('progress', 0)
        q_copy['target'] = progress.get('target', 1)
        q_copy['is_ready'] = is_ready
    can_accept, reason = QuestService.can_accept_quest(player, quest_id)

    from_npc = request.args.get('from_npc') == '1'
    return render_template("quest_detail.html", player=player, quest=q_copy,
                         is_active=is_active, is_ready=is_ready,
                         can_accept=can_accept, reason=reason,
                         from_npc=from_npc)


@quest_bp.route("/accept/<quest_id>")
@login_required
def accept_quest(quest_id):
    player = current_user
    success, msg = QuestService.accept_quest(player, quest_id)
    if success:
        q = QuestService.get_quest(quest_id)
        dialogs = q.get('dialogs', {}).get('accept', [])
        if dialogs:
            return render_template("quest_dialog.html", player=player,
                                 quest=q, dialogs=dialogs, phase='accept')
        return redirect(url_for('quest.quest_detail', quest_id=quest_id))
    return render_template("quest_error.html", player=player, error=msg)


@quest_bp.route("/complete/<quest_id>")
@login_required
def complete_quest(quest_id):
    player = current_user
    q = QuestService.get_quest(quest_id)
    success, msg = QuestService.complete_quest(player, quest_id)
    if success:
        rewards = q.get('rewards', {})
        dialogs = q.get('dialogs', {}).get('complete', [])
        next_hint = q.get('next_hint', '')
        return render_template("quest_complete.html", player=player,
                             quest=q, rewards=rewards, dialogs=dialogs,
                             next_hint=next_hint)
    return render_template("quest_error.html", player=player, error=msg)


@quest_bp.route("/abandon/<quest_id>")
@login_required
def abandon_quest(quest_id):
    player = current_user
    success, msg = QuestService.abandon_quest(player, quest_id)
    if success:
        return redirect(url_for('quest.quest_list'))
    return render_template("quest_error.html", player=player, error=msg)


@quest_bp.route("/go/<quest_id>")
@login_required
def go_to_quest(quest_id):
    """Quick travel to quest NPC location."""
    player = current_user
    q = QuestService.get_quest(quest_id)
    if not q:
        return redirect(url_for('quest.quest_list'))
    loc = q.get('npc_location', player.current_location)
    player.current_location = loc
    db.session.commit()
    return redirect(url_for('game.scene'))
