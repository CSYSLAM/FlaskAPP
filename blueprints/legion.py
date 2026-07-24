from flask import Blueprint, render_template, redirect, url_for, request, session, flash
from flask_login import login_required, current_user
from models.legion import Legion, LegionMember, LegionApplication, LegionChat
from models.player import PlayerModel
from services import db
from services.legion_service import LegionService
from services.battlefield_service import BattlefieldService, BATTLEFIELD_CITIES, TIER_BONUS, TIER_NAME
from datetime import date

legion_bp = Blueprint('legion', __name__)


@legion_bp.route("/")
@login_required
def index():
    player = current_user
    member = LegionService.get_player_member(player)
    if member:
        return redirect(url_for('legion.hall'))
    return redirect(url_for('legion.list_legions'))


@legion_bp.route("/list")
@login_required
def list_legions():
    player = current_user
    page = request.args.get('page', 1, type=int)
    legions, total = LegionService.get_all_legions(page=page, per_page=12)
    for lg in legions:
        lg.territory_names = [BATTLEFIELD_CITIES[c]['name']
                              for c in lg.occupied_cities
                              if c in BATTLEFIELD_CITIES]
    total_pages = (total + 11) // 12
    return render_template("legion_list.html",
                         player=player,
                         legions=legions,
                         page=page,
                         total_pages=total_pages)


@legion_bp.route("/detail/<int:legion_id>")
@login_required
def detail(legion_id):
    player = current_user
    legion = Legion.query.get_or_404(legion_id)
    member = LegionService.get_player_member(player)

    vice_name = None
    if legion.vice_leader_id:
        vice = PlayerModel.query.get(legion.vice_leader_id)
        vice_name = vice.nickname if vice else None

    leader = PlayerModel.query.get(legion.leader_id)
    leader_name = leader.nickname if leader else '未知'

    aura_text = LegionService.get_vip_aura_text(legion)

    already_applied = LegionApplication.query.filter_by(
        legion_id=legion_id, player_id=player.id).first() is not None

    # 领地：本军团已占领的城池（按军团战场排名第一获得），无则显示无
    legion.territory_names = [BATTLEFIELD_CITIES[c]['name']
                              for c in legion.occupied_cities
                              if c in BATTLEFIELD_CITIES]

    return render_template("legion_detail.html",
                         player=player,
                         legion=legion,
                         leader_name=leader_name,
                         vice_name=vice_name,
                         aura_text=aura_text,
                         already_in_legion=member is not None,
                         already_applied=already_applied)


@legion_bp.route("/create", methods=['GET', 'POST'])
@login_required
def create():
    player = current_user
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        declaration = request.form.get('declaration', '').strip()
        success, msg = LegionService.create_legion(player, name, declaration)
        flash(msg)
        if success:
            return redirect(url_for('legion.hall'))
        return redirect(url_for('legion.create'))
    return render_template("legion_create.html", player=player)


@legion_bp.route("/apply/<int:legion_id>")
@login_required
def apply_join(legion_id):
    player = current_user
    success, msg = LegionService.apply_to_join(player, legion_id)
    flash(msg)
    return redirect(url_for('legion.detail', legion_id=legion_id))


@legion_bp.route("/hall")
@login_required
def hall():
    player = current_user
    member = LegionService.get_player_member(player)
    if not member:
        return redirect(url_for('legion.list'))

    LegionService.check_daily_reset(member)

    legion = Legion.query.get(member.legion_id)
    leader = PlayerModel.query.get(legion.leader_id)
    leader_name = leader.nickname if leader else '未知'
    aura_text = LegionService.get_vip_aura_text(legion)

    # 领地：本军团已占领的城池（按军团战场排名第一获得），无则显示无
    legion.territory_names = [BATTLEFIELD_CITIES[c]['name']
                              for c in legion.occupied_cities
                              if c in BATTLEFIELD_CITIES]

    return render_template("legion_hall.html",
                         player=player,
                         legion=legion,
                         member=member,
                         leader_name=leader_name,
                         aura_text=aura_text,
                         signed_today=member.signed_today)


@legion_bp.route("/sign_in")
@login_required
def sign_in():
    player = current_user
    success, msg = LegionService.sign_in(player)
    flash(f"#{msg}" if success else msg)
    return redirect(url_for('legion.hall'))


@legion_bp.route("/skill")
@login_required
def skill():
    player = current_user
    member = LegionService.get_player_member(player)
    if not member:
        return redirect(url_for('legion.list'))

    legion = Legion.query.get(member.legion_id)
    bonuses = legion.get_skill_bonuses()
    return render_template("legion_skill.html",
                         player=player,
                         legion=legion,
                         bonuses=bonuses,
                         is_leader=member.role == 'leader')


@legion_bp.route("/upgrade")
@login_required
def upgrade():
    player = current_user
    success, msg = LegionService.upgrade_legion(player)
    flash(msg)
    return redirect(url_for('legion.skill'))


@legion_bp.route("/members")
@login_required
def members():
    player = current_user
    member = LegionService.get_player_member(player)
    if not member:
        return redirect(url_for('legion.list'))

    page = request.args.get('page', 1, type=int)
    member_list, total = LegionService.get_member_list(member.legion_id, page=page, per_page=15)
    total_pages = (total + 14) // 15

    # Enrich member list with player info
    enriched = []
    for m in member_list:
        p = PlayerModel.query.get(m.player_id)
        if p:
            today = date.today().isoformat()
            is_signed = m.signed_today and m.sign_date == today
            enriched.append({
                'member': m,
                'player': p,
                'signed': is_signed,
                'role_name': {'leader': '军团长', 'vice_leader': '副军团长', 'member': '成员'}.get(m.role, '团员'),
            })

    return render_template("legion_members.html",
                         player=player,
                         members=enriched,
                         page=page,
                         total_pages=total_pages,
                         can_manage=member.role in ('leader', 'vice_leader'))


@legion_bp.route("/manage")
@login_required
def manage():
    player = current_user
    member = LegionService.get_player_member(player)
    if not member or member.role not in ('leader', 'vice_leader'):
        flash("权限不足")
        return redirect(url_for('legion.hall'))

    applications = LegionService.get_applications(member.legion_id)
    # Enrich with player info
    app_list = []
    for app in applications:
        p = PlayerModel.query.get(app.player_id)
        if p:
            app_list.append({'app': app, 'player': p})

    # Get member list for vice leader management
    member_list = LegionMember.query.filter_by(legion_id=member.legion_id).all()
    members_info = []
    for m in member_list:
        p = PlayerModel.query.get(m.player_id)
        if p:
            members_info.append({'member': m, 'player': p})

    return render_template("legion_manage.html",
                         player=player,
                         applications=app_list,
                         members=members_info,
                         is_leader=member.role == 'leader',
                         legion_id=member.legion_id)


@legion_bp.route("/approve/<int:app_id>")
@login_required
def approve(app_id):
    player = current_user
    success, msg = LegionService.approve_application(player, app_id)
    flash(msg)
    return redirect(url_for('legion.manage'))


@legion_bp.route("/reject/<int:app_id>")
@login_required
def reject(app_id):
    player = current_user
    success, msg = LegionService.reject_application(player, app_id)
    flash(msg)
    return redirect(url_for('legion.manage'))


@legion_bp.route("/set_vice/<int:player_id>")
@login_required
def set_vice(player_id):
    player = current_user
    success, msg = LegionService.set_vice_leader(player, player_id)
    flash(msg)
    return redirect(url_for('legion.manage'))


@legion_bp.route("/remove_vice")
@login_required
def remove_vice():
    player = current_user
    success, msg = LegionService.remove_vice_leader(player)
    flash(msg)
    return redirect(url_for('legion.manage'))


@legion_bp.route("/kick/<int:player_id>")
@login_required
def kick(player_id):
    player = current_user
    success, msg = LegionService.kick_member(player, player_id)
    flash(msg)
    return redirect(url_for('legion.manage'))


@legion_bp.route("/leave")
@login_required
def leave():
    player = current_user
    success, msg = LegionService.leave_legion(player)
    flash(msg)
    return redirect(url_for('legion.list'))


@legion_bp.route("/chat")
@login_required
def chat():
    player = current_user
    member = LegionService.get_player_member(player)
    if not member:
        return redirect(url_for('legion.list'))

    page = request.args.get('page', 1, type=int)
    messages, total = LegionService.get_messages(player, page=page, per_page=15)
    total_pages = (total + 14) // 15

    legion = Legion.query.get(member.legion_id)

    return render_template("legion_chat.html",
                         player=player,
                         legion=legion,
                         messages=messages,
                         page=page,
                         total_pages=total_pages)


@legion_bp.route("/chat/send", methods=['POST'])
@login_required
def chat_send():
    player = current_user
    content = request.form.get('content', '').strip()
    success, msg = LegionService.send_message(player, content)
    if not success:
        flash(msg)
    return redirect(url_for('legion.chat'))


@legion_bp.route("/contribute")
@login_required
def contribute():
    player = current_user
    member = LegionService.get_player_member(player)
    if not member:
        return redirect(url_for('legion.list'))

    LegionService.check_daily_reset(member)

    legion = Legion.query.get(member.legion_id)
    return render_template("legion_contribute.html",
                         player=player,
                         legion=legion,
                         member=member)


@legion_bp.route("/donate_gold")
@login_required
def donate_gold():
    player = current_user
    success, msg = LegionService.donate_gold(player)
    flash(msg)
    return redirect(url_for('legion.contribute'))


@legion_bp.route("/donate_jinzu")
@login_required
def donate_jinzu():
    player = current_user
    success, msg = LegionService.donate_jinzu(player)
    flash(msg)
    return redirect(url_for('legion.contribute'))


@legion_bp.route("/donate_yuanbao")
@login_required
def donate_yuanbao():
    player = current_user
    success, msg = LegionService.donate_yuanbao(player)
    flash(msg)
    return redirect(url_for('legion.contribute'))


@legion_bp.route("/quest")
@login_required
def quest():
    player = current_user
    member = LegionService.get_player_member(player)
    if not member:
        return redirect(url_for('legion.list'))

    LegionService.check_daily_reset(member)

    legion = Legion.query.get(member.legion_id)
    remaining = LegionService.get_quest_count(player)
    return render_template("legion_quest.html",
                         player=player,
                         legion=legion,
                         member=member,
                         remaining=remaining)


@legion_bp.route("/quest/do")
@login_required
def quest_do():
    player = current_user
    success, msg = LegionService.do_quest(player)
    flash(msg)
    return redirect(url_for('legion.quest'))


@legion_bp.route("/exchange")
@login_required
def exchange():
    player = current_user
    member = LegionService.get_player_member(player)
    if not member:
        return redirect(url_for('legion.list'))

    category = request.args.get('cat', 'other')
    categories = LegionService.CONTRIB_EXCHANGE
    items = categories.get(category, categories['other'])['items']
    return render_template("legion_exchange.html",
                         player=player,
                         member=member,
                         categories=categories,
                         current_cat=category,
                         items=items)


@legion_bp.route("/exchange/<item_key>", methods=['POST'])
@login_required
def exchange_item(item_key):
    player = current_user
    quantity = request.form.get('quantity', 1, type=int)
    if quantity < 1:
        quantity = 1
    cat = request.form.get('cat', 'other')
    success, msg = LegionService.exchange_contrib_item(player, item_key, quantity)
    flash(msg)
    return redirect(url_for('legion.exchange', cat=cat))


@legion_bp.route("/battle_exchange")
@login_required
def battle_exchange():
    player = current_user
    member = LegionService.get_player_member(player)
    if not member:
        return redirect(url_for('legion.list'))

    category = request.args.get('cat', 'other')
    categories = LegionService.BATTLE_EXCHANGE
    items = categories.get(category, categories['other'])['items']
    legion = Legion.query.get(member.legion_id)
    return render_template("legion_battle_exchange.html",
                         player=player,
                         member=member,
                         legion=legion,
                         categories=categories,
                         current_cat=category,
                         items=items)


@legion_bp.route("/battle_exchange/<item_key>", methods=['POST'])
@login_required
def battle_exchange_item(item_key):
    player = current_user
    quantity = request.form.get('quantity', 1, type=int)
    if quantity < 1:
        quantity = 1
    cat = request.form.get('cat', 'other')
    success, msg = LegionService.exchange_battle_item(player, item_key, quantity)
    flash(msg)
    return redirect(url_for('legion.battle_exchange', cat=cat))


@legion_bp.route("/territory")
@login_required
def territory():
    player = current_user
    member = LegionService.get_player_member(player)
    if not member:
        return redirect(url_for('legion.list'))

    legion = Legion.query.get(member.legion_id)
    territory_info = []
    for city_key in legion.occupied_cities:
        city = BATTLEFIELD_CITIES.get(city_key)
        if city:
            territory_info.append({
                'city_key': city_key,
                'name': city['name'],
                'tier': city['tier'],
                'tier_name': TIER_NAME[city['tier']],
                'bonus': TIER_BONUS[city['tier']],
            })

    claimable = []
    for city_key in BattlefieldService.get_claimable_cities(member.legion_id):
        city = BATTLEFIELD_CITIES.get(city_key)
        if city:
            claimable.append({
                'city_key': city_key,
                'name': city['name'],
                'tier': city['tier'],
                'tier_name': TIER_NAME[city['tier']],
            })

    is_leader = member.role == 'leader'
    return render_template("legion_territory.html",
                         player=player,
                         legion=legion,
                         territory_info=territory_info,
                         claimable=claimable,
                         is_leader=is_leader)


@legion_bp.route("/occupy/<city_key>")
@login_required
def occupy_city(city_key):
    player = current_user
    success, msg = BattlefieldService.occupy_city(player, city_key)
    flash(msg)
    return redirect(url_for('legion.territory'))
