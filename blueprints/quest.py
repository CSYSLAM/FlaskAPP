from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import login_required, current_user
from services.data_service import DataService
from services.quest_service import QuestService
from services.copy_dungeon_service import CopyDungeonService
from services import db

quest_bp = Blueprint('quest', __name__, url_prefix='/quest')


@quest_bp.route("/")
@login_required
def quest_list():
    player = current_user
    active = QuestService.get_active_quests(player)
    completed = QuestService.get_completed_quests(player)
    all_quests = QuestService.get_country_quests(player)

    active_list = []
    for qid, progress in active.items():
        # 副本阶段任务：用 CopyDungeonService 构造 quest dict
        if qid.startswith('copy_'):
            cq = CopyDungeonService.get_stage_quest(player, qid)
            if cq:
                active_list.append(cq)
            continue
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
    all_quests = QuestService.get_country_quests(player)
    completed = QuestService.get_completed_quests(player)
    active = QuestService.get_active_quests(player)

    available = []
    for qid, q in all_quests.items():
        if qid in completed or qid in active:
            continue
        ok, _ = QuestService.can_accept_quest(player, qid)
        if ok:
            available.append(q)
            continue
        # 展示前置已满足但暂因等级不足不可接取的任务(仅本国)
        prereq = q.get('prerequisite')
        if (not prereq) or (prereq in completed):
            available.append(q)

    # 玩家位于副本地图内时，把当前副本阶段任务列入可接任务（未接受才显示为可接）
    copy_quest = CopyDungeonService.get_current_stage_quest(player)
    if copy_quest and not copy_quest.get('accepted'):
        available.append(copy_quest)

    return render_template("quest_available.html", player=player,
                         available=available)


@quest_bp.route("/detail/<quest_id>")
@login_required
def quest_detail(quest_id):
    player = current_user

    # 副本阶段任务（id 前缀 copy_）：渲染副本任务详情页
    if quest_id.startswith('copy_'):
        cq = CopyDungeonService.get_stage_quest(player, quest_id)
        if not cq:
            return redirect(url_for('quest.quest_list'))
        return render_template("copy_quest_detail.html", player=player,
                             quest=cq, is_active=cq.get('accepted', False),
                             is_ready=cq.get('is_ready', False),
                             can_accept=not cq.get('accepted', False),
                             reason='', is_completed=False,
                             from_npc=request.args.get('from_npc') == '1',
                             DataService=DataService)

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
    completed = QuestService.get_completed_quests(player)
    is_completed = quest_id in completed

    from_npc = request.args.get('from_npc') == '1'
    return render_template("quest_detail.html", player=player, quest=q_copy,
                         is_active=is_active, is_ready=is_ready,
                         can_accept=can_accept, reason=reason,
                         is_completed=is_completed, from_npc=from_npc)


@quest_bp.route("/accept/<quest_id>")
@login_required
def accept_quest(quest_id):
    player = current_user
    # 副本阶段任务：走 CopyDungeonService
    if quest_id.startswith('copy_'):
        parsed = CopyDungeonService.parse_stage_quest_id(quest_id)
        if not parsed:
            return render_template("quest_error.html", player=player, error='任务不存在')
        dungeon_id, stage_index = parsed
        # 校验当前阶段匹配，避免接受非当前阶段
        state = CopyDungeonService.get_state(player, dungeon_id)
        if int(state.get('stage_index', 0)) != stage_index:
            return render_template("quest_error.html", player=player, error='请按顺序接受副本任务')
        success, msg, result = CopyDungeonService.accept_task(player, dungeon_id)
        if success:
            stage = (result or {}).get('stage') or {}
            story_lines = []
            if stage.get('story'):
                story_lines.append(f"{(result or {}).get('npc_name') or CopyDungeonService.get_definition(dungeon_id).get('name','')}: {stage.get('story')}")
            if stage.get('objective'):
                story_lines.append(f"目标: {stage.get('objective')}")
            return render_template("quest_dialog.html", player=player,
                                 quest={'id': quest_id, 'name': f"副·{stage.get('name','任务')}"},
                                 dialogs=[{'speaker': '', 'text': line} for line in story_lines] or [{'speaker':'','text':msg}],
                                 phase='accept')
        return render_template("quest_error.html", player=player, error=msg)

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
    # 副本阶段任务：走 CopyDungeonService
    if quest_id.startswith('copy_'):
        parsed = CopyDungeonService.parse_stage_quest_id(quest_id)
        if not parsed:
            return render_template("quest_error.html", player=player, error='任务不存在')
        dungeon_id, stage_index = parsed
        success, msg, finished, result = CopyDungeonService.complete_stage(player, dungeon_id)
        if success:
            if finished and result:
                return render_template(
                    "copy_dungeon_result.html", player=player,
                    dungeon=result['dungeon'],
                    story_outro=result.get('story_outro', []),
                    reward=result.get('reward', {}),
                    reward_items=result.get('reward_items', []),
                    return_location=result.get('return_location'),
                    return_location_name=result.get('return_location_name'),
                )
            # 非末阶段完成：展示奖励 + 下一阶段提示，引导玩家去接下一阶段
            stage = (result or {}).get('stage') or {}
            next_stage = (result or {}).get('next_stage') or {}
            story_lines = []
            for ri in (stage.get('reward') or {}).get('items', []):
                item_data = DataService.get_item(ri.get('item_id'))
                item_name = item_data.get('name', ri.get('item_id')) if item_data else ri.get('item_id')
                story_lines.append(f"获得 {item_name} x{ri.get('count', 1)}")
            if (stage.get('reward') or {}).get('experience'):
                story_lines.append(f"经验+{stage['reward']['experience']}")
            if (stage.get('reward') or {}).get('gold'):
                story_lines.append(f"银两+{stage['reward']['gold']}")
            if stage.get('complete_story'):
                story_lines.append(stage.get('complete_story'))
            if next_stage:
                next_loc = next_stage.get('quest_giver_location', '')
                next_loc_data = DataService.get_location(next_loc) if next_loc else None
                next_loc_name = next_loc_data.get('name', next_loc.split('.')[-1] if next_loc else '未知') if next_loc_data else (next_loc.split('.')[-1] if next_loc else '未知')
                next_npc_id = next_stage.get('quest_giver_npc_id')
                next_npc = DataService.get_monster(next_npc_id) if next_npc_id else None
                next_npc_name = next_npc.get('name', 'NPC') if next_npc else 'NPC'
                story_lines.append(f"提示:前往「{next_loc_name}」与『{next_npc_name}』对话接取下一阶段")
            return render_template("quest_complete.html", player=player,
                                 quest={'id': quest_id, 'name': f"副·{stage.get('name','任务')}"},
                                 rewards=stage.get('reward') or {},
                                 dialogs=[{'speaker': '', 'text': line} for line in story_lines],
                                 next_hint='下一阶段可在『可接任务』中查看并接受')
        return render_template("quest_error.html", player=player, error=msg)

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
    if quest_id.startswith('copy_'):
        success, msg = CopyDungeonService.abandon_copy_quest(player, quest_id)
        if success:
            return redirect(url_for('quest.quest_list'))
        return render_template("quest_error.html", player=player, error=msg)
    success, msg = QuestService.abandon_quest(player, quest_id)
    if success:
        return redirect(url_for('quest.quest_list'))
    return render_template("quest_error.html", player=player, error=msg)


@quest_bp.route("/go/<quest_id>")
@login_required
def go_to_quest(quest_id):
    """Quick travel to quest NPC location."""
    player = current_user
    if quest_id.startswith('copy_'):
        cq = CopyDungeonService.get_stage_quest(player, quest_id)
        if not cq:
            return redirect(url_for('quest.quest_list'))
        loc = cq.get('npc_location') or player.current_location
        player.current_location = loc
        db.session.commit()
        return redirect(url_for('game.scene'))
    q = QuestService.get_quest(quest_id)
    if not q:
        return redirect(url_for('quest.quest_list'))
    loc = q.get('npc_location', player.current_location)
    player.current_location = loc
    db.session.commit()
    return redirect(url_for('game.scene'))


@quest_bp.route("/go_target/<quest_id>")
@login_required
def go_to_target(quest_id):
    """Quick travel to quest target location (where monsters/objectives are)."""
    player = current_user
    if quest_id.startswith('copy_'):
        cq = CopyDungeonService.get_stage_quest(player, quest_id)
        if not cq:
            return redirect(url_for('quest.quest_list'))
        loc = cq.get('target_location') or cq.get('npc_location') or player.current_location
        player.current_location = loc
        db.session.commit()
        return redirect(url_for('game.scene'))
    q = QuestService.get_quest(quest_id)
    if not q:
        return redirect(url_for('quest.quest_list'))
    # 目的地优先 target_location；未配置则回退到发起人位置
    loc = q.get('target_location') or q.get('npc_location', player.current_location)
    player.current_location = loc
    db.session.commit()
    return redirect(url_for('game.scene'))
