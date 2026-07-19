from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import login_required, current_user
from services.data_service import DataService
from services.crafting_service import CraftingService

crafting_bp = Blueprint('crafting', __name__, url_prefix='/crafting')


@crafting_bp.route("/")
@login_required
def crafting_main():
    """Blacksmith main page (redirect to epic forge)"""
    return redirect(url_for('crafting.epic_forge'))


@crafting_bp.route("/class/<class_name>")
@login_required
def crafting_by_class(class_name):
    """Legacy route - redirect to epic forge."""
    return redirect(url_for('crafting.epic_forge'))


@crafting_bp.route("/epic_forge")
@login_required
def epic_forge():
    """Epic crafting category list page."""
    player = current_user
    sets = CraftingService.get_sets_by_class(player.player_class)
    return render_template("crafting_epic_forge.html", player=player,
                           sets=sets, active_class=player.player_class)


@crafting_bp.route("/epic_forge/weapons")
@crafting_bp.route("/epic_forge/weapons/<class_name>")
@login_required
def epic_forge_weapons(class_name=None):
    """Epic weapon crafting page with class tabs."""
    player = current_user
    if class_name is None:
        class_name = player.player_class
    if class_name not in ("战士", "术士", "刺客"):
        class_name = player.player_class

    template_ids = CraftingService.get_weapon_templates_by_class(class_name)
    templates = []
    for tid in template_ids:
        t = DataService.get_equipment_template(tid)
        if t:
            info = CraftingService.get_template_info(tid)
            templates.append(info)

    return render_template("crafting_forge_items.html", player=player,
                           items=templates, active_class=class_name,
                           page_type="weapons", title="打造史诗级武器")


@crafting_bp.route("/epic_forge/accessories")
@login_required
def epic_forge_accessories():
    """Epic accessory crafting page (no class restriction)."""
    player = current_user
    template_ids = CraftingService.get_accessory_templates()
    templates = []
    for tid in template_ids:
        t = DataService.get_equipment_template(tid)
        if t:
            info = CraftingService.get_template_info(tid)
            templates.append(info)

    return render_template("crafting_forge_items.html", player=player,
                           items=templates, active_class=None,
                           page_type="accessories", title="打造史诗级饰品")


@crafting_bp.route("/epic_forge/set/<set_id>")
@crafting_bp.route("/epic_forge/set/<set_id>/<class_name>")
@login_required
def epic_forge_set(set_id, class_name=None):
    """Epic armor set crafting page.

    Sets that share a ``group`` (e.g. 青龙/朱雀/白虎 55-59) render in-page class
    tabs so the player can switch between the three classes' sets from one entry.
    """
    player = current_user
    target_set = CraftingService.get_set_by_id(set_id)
    if not target_set:
        return redirect(url_for('crafting.epic_forge'))

    # Resolve which class to display
    class_tabs = CraftingService.get_set_class_tabs(target_set)
    if class_tabs:
        # Grouped set: honour the requested class tab, default to player's class
        if class_name not in class_tabs:
            class_name = player.player_class if player.player_class in class_tabs else class_tabs[0]
        display_set = CraftingService.get_set_in_group_by_class(target_set, class_name)
    else:
        class_name = target_set["class_name"]
        display_set = target_set

    templates = []
    for tid in display_set["templates"]:
        info = CraftingService.get_template_info(tid)
        if info:
            templates.append(info)

    return render_template("crafting_forge_items.html", player=player,
                           items=templates, active_class=class_name,
                           page_type="set", title=display_set["name"] + "打造",
                           set_name=display_set["name"],
                           set_id=set_id, class_tabs=class_tabs)


@crafting_bp.route("/forge/<template_id>", methods=["POST"])
@login_required
def forge_equipment(template_id):
    """Handle forging of an equipment piece."""
    player = current_user
    success, result = CraftingService.forge_equipment(player, template_id)

    # Compute back URL based on slot type (always, for both success and failure)
    template = DataService.get_equipment_template(template_id)
    slot = template.get("slot", "") if template else ""

    if slot == "weapon":
        back_url = url_for('crafting.epic_forge_weapons', class_name=player.player_class)
    elif slot == "accessory":
        back_url = url_for('crafting.epic_forge_accessories')
    else:
        # Armor set - find which set this template belongs to
        found_set_id = None
        found_class = None
        for s in CraftingService.SET_DEFINITIONS:
            if template_id in s["templates"]:
                found_set_id = s["set_id"]
                found_class = s["class_name"]
                break
        if found_set_id:
            set_def = CraftingService.get_set_by_id(found_set_id)
            back_class = found_class if (set_def and set_def.get("group")) else player.player_class
            back_url = url_for('crafting.epic_forge_set', set_id=found_set_id, class_name=back_class)
        else:
            back_url = url_for('crafting.epic_forge')

    if not success:
        return render_template("crafting_error.html", player=player, error=result,
                              back_url=back_url)

    cost_info = CraftingService.get_template_info(template_id)
    return render_template("forge_result.html", player=player, equipment=result,
                           cost_info=cost_info, back_url=back_url)


@crafting_bp.route("/sell_equipment")
@crafting_bp.route("/sell_equipment/<rarity>")
@login_required
def sell_equipment(rarity="普通"):
    """Sell equipment page with rarity tabs."""
    player = current_user
    if rarity not in ("普通", "精良", "卓越", "史诗", "神器"):
        rarity = "普通"

    groups = CraftingService.get_sell_equipment_groups(player, rarity)
    return render_template("blacksmith_sell_equipment.html", player=player,
                           groups=groups, active_rarity=rarity)


@crafting_bp.route("/sell_equipment/do", methods=["POST"])
@login_required
def sell_equipment_do():
    """Execute batch sell of equipment."""
    player = current_user
    level_ranges = request.form.getlist("level_ranges")
    if not level_ranges:
        return redirect(url_for('crafting.sell_equipment'))

    gold, count = CraftingService.sell_equipment_batch(player, level_ranges)
    return render_template("blacksmith_sell_result.html", player=player,
                           gold=gold, count=count, item_type="装备")


@crafting_bp.route("/sell_item")
@crafting_bp.route("/sell_item/<category>")
@login_required
def sell_item(category="药品"):
    """Sell items page with category tabs."""
    player = current_user
    if category not in ("药品", "种子", "材料", "技能"):
        category = "药品"

    groups = CraftingService.get_sell_item_groups(player, category)
    return render_template("blacksmith_sell_item.html", player=player,
                           groups=groups, active_category=category)


@crafting_bp.route("/sell_item/do", methods=["POST"])
@login_required
def sell_item_do():
    """Execute batch sell of items."""
    player = current_user
    item_names = request.form.getlist("item_names")
    if not item_names:
        return redirect(url_for('crafting.sell_item'))

    gold, count = CraftingService.sell_item_batch(player, item_names)
    return render_template("blacksmith_sell_result.html", player=player,
                           gold=gold, count=count, item_type="道具")
