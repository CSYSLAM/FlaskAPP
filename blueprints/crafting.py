from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import login_required, current_user
from services.data_service import DataService
from services.crafting_service import CraftingService

crafting_bp = Blueprint('crafting', __name__, url_prefix='/crafting')


@crafting_bp.route("/")
@login_required
def crafting_main():
    player = current_user
    sets = CraftingService.get_sets_by_class(player.player_class)
    craft_info = _build_craft_info(sets)
    return render_template("crafting.html", player=player, sets=sets,
                           active_class=player.player_class, craft_info=craft_info)


@crafting_bp.route("/class/<class_name>")
@login_required
def crafting_by_class(class_name):
    player = current_user
    if class_name not in ("战士", "术士", "刺客"):
        class_name = player.player_class
    sets = CraftingService.get_sets_by_class(class_name)
    craft_info = _build_craft_info(sets)
    return render_template("crafting.html", player=player, sets=sets,
                           active_class=class_name, craft_info=craft_info)


def _build_craft_info(sets):
    info = {}
    for s in sets:
        for tid in s["templates"]:
            info[tid] = CraftingService.get_template_info(tid)
    return info


@crafting_bp.route("/forge/<template_id>", methods=["POST"])
@login_required
def forge_equipment(template_id):
    player = current_user
    success, result = CraftingService.forge_equipment(player, template_id)

    sets = CraftingService.get_sets_by_class(player.player_class)
    craft_info = _build_craft_info(sets)

    if not success:
        return render_template("crafting.html", player=player, sets=sets,
                               active_class=player.player_class,
                               craft_info=craft_info, error=result)

    cost_info = CraftingService.get_template_info(template_id)
    return render_template("forge_result.html", player=player, equipment=result,
                           cost_info=cost_info)
