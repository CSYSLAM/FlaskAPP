from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from services import db
from services.data_service import DataService
from services.copy_dungeon_service import CopyDungeonService


dungeon_bp = Blueprint('dungeon', __name__)


@dungeon_bp.route('/enter/<dungeon_id>')
@login_required
def enter(dungeon_id):
    player = current_user
    definition = CopyDungeonService.get_definition(dungeon_id)
    success, msg = CopyDungeonService.enter_dungeon(player, dungeon_id)
    if success:
        entry_item_id = definition.get('entry_item_id') if definition else None
        entry_item = DataService.get_item(entry_item_id) if entry_item_id else None
        entry_item_name = entry_item.get('name', entry_item_id) if entry_item else (definition.get('name', dungeon_id) if definition else dungeon_id)
        return render_template(
            'story.html',
            story_title=f"{entry_item_name}-{definition.get('entry_item_count', 1) if definition else 1}",
            story_lines=definition.get('story_intro', []) if definition else [],
            continue_url=url_for('game.scene'),
            player=player,
        )
    flash(msg)
    if definition and definition.get('entry_npc_id'):
        return redirect(url_for('game.view_npc', monster_id=definition.get('entry_npc_id')))
    return redirect(url_for('game.scene'))


@dungeon_bp.route('/action/<npc_id>', methods=['POST'])
@login_required
def action(npc_id):
    player = current_user
    action_name = request.form.get('action', '')
    dungeon_id = CopyDungeonService.get_dungeon_id_by_npc(npc_id)
    if not dungeon_id:
        flash('副本任务不存在')
        return redirect(url_for('game.scene'))

    if action_name == 'accept':
        success, msg, result = CopyDungeonService.accept_task(player, dungeon_id)
        if success:
            stage = result.get('stage') if result else None
            stage_name = stage.get('name', '任务') if stage else '任务'
            story_lines = []
            if stage and stage.get('story'):
                story_lines.append(f"灵帝: {stage.get('story')}")
            if stage and stage.get('objective'):
                story_lines.append(f"目标: {stage.get('objective')}")
            return render_template(
                'story.html',
                story_title=f"『接受任务-副·{stage_name}』",
                story_lines=story_lines or [msg],
                continue_url=url_for('game.scene'),
                player=player,
            )
        flash(msg)
        return redirect(url_for('game.view_npc', monster_id=npc_id))

    if action_name == 'complete':
        success, msg, finished, result = CopyDungeonService.complete_stage(player, dungeon_id)
        if success:
            if finished and result:
                return render_template(
                    'copy_dungeon_result.html',
                    player=player,
                    dungeon=result['dungeon'],
                    story_outro=result.get('story_outro', []),
                    reward=result.get('reward', {}),
                    reward_items=result.get('reward_items', []),
                    return_location=result.get('return_location'),
                    return_location_name=result.get('return_location_name'),
                )
            if result:
                completed_stage = result.get('completed_stage') or {}
                next_stage = result.get('next_stage') or {}
                reward = result.get('reward', {})
                consumed_items = completed_stage.get('required_items', {})
                story_lines = []

                # Show consumed items
                for item_id, count in consumed_items.items():
                    item_data = DataService.get_item(item_id)
                    item_name = item_data.get('name', item_id) if item_data else item_id
                    story_lines.append(f"失去[{item_name}]{count}个")

                # Show reward items (stage reward)
                for ri in reward.get('items', []):
                    item_data = DataService.get_item(ri.get('item_id'))
                    item_name = item_data.get('name', ri.get('item_id')) if item_data else ri.get('item_id')
                    story_lines.append(f"获得 {item_name} x{ri.get('count', 1)}")

                if reward.get('experience'):
                    story_lines.append(f"经验+{reward.get('experience')}")
                if reward.get('gold'):
                    story_lines.append(f"银两+{reward.get('gold')}")

                # NPC completion dialogue
                stage = result.get('stage')
                if stage and stage.get('complete_story'):
                    stage_npc_id = stage.get('quest_giver_npc_id')
                    npc_name = 'NPC'
                    if stage_npc_id:
                        npc_data = DataService.get_monster(stage_npc_id) or {}
                        npc_name = npc_data.get('name', 'NPC')
                    story_lines.append(f"{npc_name}: {stage.get('complete_story')}")

                if next_stage:
                    # Hint about next NPC/location
                    if completed_stage.get('complete_hint'):
                        story_lines.append(completed_stage.get('complete_hint'))
                    elif next_stage.get('quest_giver_npc_id'):
                        next_npc_id = next_stage.get('quest_giver_npc_id')
                        next_npc = DataService.get_monster(next_npc_id) or {}
                        next_npc_name = next_npc.get('name', 'NPC')
                        next_loc_id = next_stage.get('quest_giver_location', '')
                        next_loc = DataService.get_location(next_loc_id) if next_loc_id else None
                        next_loc_name = next_loc.get('name', next_loc_id.split('.')[-1] if next_loc_id else '未知')
                        story_lines.append(f"提示:前往「{next_loc_name}」与『{next_npc_name}』对话")
                    story_lines.append(f"已开启任务: 副·{next_stage.get('name', '下一阶段')}")
                return render_template(
                    'story.html',
                    story_title=f"『完成任务-副·{completed_stage.get('name', '任务')}』",
                    story_lines=story_lines or [msg],
                    continue_url=url_for('game.view_npc', monster_id=npc_id),
                    player=player,
                )
        flash(msg)
        return redirect(url_for('game.view_npc', monster_id=npc_id))

    if action_name == 'claim_reward':
        success, msg, result = CopyDungeonService.claim_reward(player, dungeon_id)
        flash(msg)
        if success and result:
            db.session.commit()
            return render_template(
                'copy_dungeon_result.html',
                player=player,
                dungeon=result['dungeon'],
                story_outro=result.get('story_outro', []),
                reward=result.get('reward', {}),
                reward_items=result.get('reward_items', []),
                return_location=result.get('return_location'),
                return_location_name=result.get('return_location_name'),
            )
        return redirect(url_for('game.view_npc', monster_id=npc_id))

    if action_name == 'leave':
        success, msg = CopyDungeonService.leave_dungeon(player, dungeon_id)
        flash(msg)
        if success:
            db.session.commit()
            return redirect(url_for('game.scene'))
        return redirect(url_for('game.view_npc', monster_id=npc_id))

    flash('未知操作')
    return redirect(url_for('game.view_npc', monster_id=npc_id))


@dungeon_bp.route('/jump/<npc_id>/<target>')
@login_required
def jump(npc_id, target):
    player = current_user
    dungeon_id = CopyDungeonService.get_dungeon_id_by_npc(npc_id)
    if not dungeon_id:
        flash('副本任务不存在')
        return redirect(url_for('game.scene'))

    if target == 'entry':
        success, msg = CopyDungeonService.jump_to_entry(player, dungeon_id)
    elif target == 'stage':
        success, msg = CopyDungeonService.jump_to_current_stage(player, dungeon_id)
    else:
        success, msg = False, '未知跳转'

    if not success:
        flash(msg)
        return redirect(url_for('game.view_npc', monster_id=npc_id))
    return redirect(url_for('game.scene'))
