from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from services import db
from services.vip_service import VipService
from services.data_service import DataService

vip_bp = Blueprint('vip', __name__, url_prefix='/vip')


@vip_bp.route('/')
@login_required
def index():
    """VIP main page showing current status and privileges."""
    player = current_user
    vip_level = VipService.get_active_vip_level(player)
    remaining = VipService.get_vip_remaining_time(player)

    # Check if can upgrade
    can_upgrade, upgrade_err = VipService.can_upgrade_vip(player)
    next_exp_cost = None
    if player.vip_level < 5:
        next_config = VipService.get_vip_level_config(player.vip_level + 1)
        if next_config:
            next_exp_cost = next_config['required_exp']

    # Check daily claims
    from datetime import datetime
    today = datetime.utcnow().strftime('%Y-%m-%d')
    claimed = player.vip_daily_claimed
    can_claim_daily_exp = claimed.get('exp') != today
    can_claim_gift = vip_level > 0 and claimed.get('gift') != today
    has_free_teleport = VipService.has_free_teleport(player)

    privileges = []
    if vip_level > 0:
        privileges = VipService.get_vip_privilege_list(vip_level)

    return render_template('vip.html',
        player=player,
        vip_level=vip_level,
        vip_exp=player.vip_exp,
        remaining=remaining,
        privileges=privileges,
        can_claim_daily_exp=can_claim_daily_exp,
        can_claim_gift=can_claim_gift,
        can_upgrade=can_upgrade,
        next_exp_cost=next_exp_cost,
        has_free_teleport=has_free_teleport)


@vip_bp.route('/intro')
@login_required
def intro():
    """VIP introduction page showing all level details."""
    config = VipService._load_config()
    level_configs = config['vip_levels']
    all_levels = {}
    gift_names = {}
    for lv in range(1, 6):
        all_levels[lv] = VipService.get_vip_privilege_list(lv)
        gift_parts = []
        lv_config = level_configs.get(str(lv))
        if lv_config and lv_config.get('daily_gift'):
            for gift in lv_config['daily_gift']:
                item_data = DataService.get_item(gift['item_id'])
                name = item_data.get('name', gift['item_id']) if item_data else gift['item_id']
                gift_parts.append(f"{name}x{gift['quantity']}")
        gift_names[lv] = ' '.join(gift_parts) if gift_parts else ''

    return render_template('vip_intro.html',
        all_levels=all_levels,
        level_configs=level_configs,
        gift_names=gift_names)


@vip_bp.route('/use/<item_id>')
@login_required
def use_zhuhouling_page(item_id):
    """Show zhuhouling use confirmation page."""
    item_data = DataService.get_item(item_id)
    if not item_data or item_data.get('type') != 'vip':
        flash("不是诸侯令")
        return redirect(url_for('player.inventory'))

    inv_item = DataService.get_inventory_item(current_user.id, item_id)
    if not inv_item or inv_item.quantity <= 0:
        flash("没有该物品")
        return redirect(url_for('player.inventory'))

    return render_template('vip_use.html',
        player=current_user,
        item_id=item_id,
        item_data=item_data,
        quantity=inv_item.quantity)


@vip_bp.route('/use/<item_id>', methods=['POST'])
@login_required
def use_zhuhouling(item_id):
    """Actually use a zhuhouling."""
    inv_bound = DataService.get_inventory_item(current_user.id, item_id, is_bound=True)
    inv_unbound = DataService.get_inventory_item(current_user.id, item_id, is_bound=False)
    is_bound = True if (inv_bound and inv_bound.quantity > 0) else False
    success, msg = VipService.use_zhuhouling(current_user, item_id, is_bound=is_bound)
    flash(msg)
    if success:
        return redirect(url_for('vip.index'))
    return redirect(url_for('player.inventory'))


@vip_bp.route('/upgrade')
@login_required
def upgrade_vip():
    """Upgrade VIP level by consuming exp."""
    success, msg = VipService.upgrade_vip(current_user)
    flash(msg)
    return redirect(url_for('vip.index'))


@vip_bp.route('/convert_exp/<int:count>')
@login_required
def convert_exp(count):
    """Convert VIP days to exp (1 day = 10 exp)."""
    success, msg = VipService.convert_days_to_exp(current_user, count)
    flash(msg)
    return redirect(url_for('vip.index'))


@vip_bp.route('/claim_exp')
@login_required
def claim_daily_exp():
    """Claim daily 5 VIP exp."""
    success, msg = VipService.claim_daily_exp(current_user)
    flash(msg)
    return redirect(url_for('vip.index'))


@vip_bp.route('/claim_daily')
@login_required
def claim_daily():
    """Claim VIP daily gift."""
    success, msg = VipService.claim_daily_gift(current_user)
    flash(msg)
    return redirect(url_for('vip.index'))


@vip_bp.route('/teleport')
@login_required
def teleport_page():
    """VIP free teleport page."""
    player = current_user
    if not VipService.has_free_teleport(player):
        flash("VIP未生效，无法使用特权传送")
        return redirect(url_for('vip.index'))

    locations = DataService.get_locations()
    # Group by area
    areas = {}
    for loc_id, loc in locations.items():
        area = loc.get('area_name', '未知')
        if area not in areas:
            areas[area] = []
        areas[area].append((loc_id, loc.get('name', loc_id)))

    return render_template('vip_teleport.html',
        player=player,
        areas=areas)


@vip_bp.route('/teleport/<path:location_id>')
@login_required
def do_teleport(location_id):
    """Execute VIP free teleport."""
    player = current_user
    if not VipService.has_free_teleport(player):
        flash("VIP未生效，无法使用特权传送")
        return redirect(url_for('vip.index'))

    current_loc = DataService.get_location(player.current_location)
    if current_loc and current_loc.get('is_copy_map'):
        flash("副本内无法使用传送，请先放弃副本再离开")
        return redirect(url_for('game.scene'))

    locations = DataService.get_locations()
    if location_id not in locations:
        flash("目标地点不存在")
        return redirect(url_for('vip.teleport_page'))

    player.current_location = location_id
    db.session.commit()
    flash(f"已传送到{locations[location_id].get('name', location_id)}")
    return redirect(url_for('game.scene'))