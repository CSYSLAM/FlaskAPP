from flask import Blueprint, render_template, redirect, url_for, request, session, flash
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from models.player import PlayerModel, EquipmentInstance
from models.relationship import Relationship
from services import db
from services.data_service import DataService
from services.social_service import SocialService
from services.legion_service import LegionService
from services.party_service import PartyService

social_bp = Blueprint('social', __name__)


@social_bp.route("/")
@social_bp.route("/social")
@login_required
def social_index():
    player = current_user
    return render_template("social_index.html", player=player)


@social_bp.route("/search_player")
@login_required
def search_player():
    uid = request.args.get("uid", "").strip()
    if not uid:
        flash("请输入玩家ID")
        return redirect(url_for('social.social_index'))
    target = DataService.get_player_by_uid(uid)
    if not target:
        flash("找不到该玩家")
        return redirect(url_for('social.social_index'))
    return redirect(url_for('player.view_player', username=target.username))


# --- Friends ---

@social_bp.route("/friends")
@login_required
def friends():
    player = current_user
    friends_list = SocialService.get_friend_list(player)
    return render_template("social_friends.html",
                         player=player,
                         friends_list=friends_list,
                         max_friends=30)


@social_bp.route("/add_friend/<username>")
@login_required
def add_friend(username):
    player = current_user
    success, msg = SocialService.add_friend(player, username)
    flash(msg)
    return redirect(url_for('player.view_player', username=username))


@social_bp.route("/remove_friend/<username>")
@login_required
def remove_friend(username):
    player = current_user
    success, msg = SocialService.remove_friend(player, username)
    flash(msg)
    return redirect(url_for('social.friends'))


# --- Blacklist ---

@social_bp.route("/blacklist")
@login_required
def blacklist():
    player = current_user
    blacklist_list = []
    for username in player.blacklist:
        target = DataService.get_player_by_username(username)
        if target:
            blacklist_list.append({
                'username': username,
                'nickname': target.nickname
            })
    return render_template("social_blacklist.html",
                         player=player,
                         blacklist_list=blacklist_list)


@social_bp.route("/add_blacklist/<username>")
@login_required
def add_blacklist(username):
    player = current_user
    success, msg = SocialService.add_to_blacklist(player, username)
    flash(msg)
    return redirect(url_for('player.view_player', username=username))


@social_bp.route("/remove_blacklist/<username>")
@login_required
def remove_blacklist(username):
    player = current_user
    success, msg = SocialService.remove_from_blacklist(player, username)
    flash(msg)
    return redirect(url_for('social.blacklist'))


# --- Enemies ---

@social_bp.route("/enemies")
@login_required
def enemies():
    player = current_user
    enemies_list = SocialService.get_enemy_list(player)
    return render_template("social_enemies.html",
                         player=player,
                         enemies_list=enemies_list)


@social_bp.route("/remove_enemy/<username>")
@login_required
def remove_enemy(username):
    player = current_user
    success, msg = SocialService.remove_enemy(player, username)
    flash(msg)
    return redirect(url_for('social.enemies'))


@social_bp.route("/hunt_enemy/<username>")
@login_required
def hunt_enemy(username):
    player = current_user
    success, msg = SocialService.hunt_enemy(player, username)
    flash(msg)
    if success:
        return redirect(url_for('game.scene'))
    return redirect(url_for('social.enemies'))


# --- Relationships (红颜/知己) ---

@social_bp.route("/hongyan")
@login_required
def hongyan():
    player = current_user
    rel_list = SocialService.get_relation_list(player, 'hongyan')
    pending_requests = [r for r in player.relation_requests if r.get('type') == 'hongyan']
    return render_template("social_hongyan.html",
                         player=player,
                         rel_list=rel_list,
                         pending_requests=pending_requests,
                         max_relations=5)


@social_bp.route("/zhiji")
@login_required
def zhiji():
    player = current_user
    rel_list = SocialService.get_relation_list(player, 'zhiji')
    pending_requests = [r for r in player.relation_requests if r.get('type') == 'zhiji']
    return render_template("social_zhiji.html",
                         player=player,
                         rel_list=rel_list,
                         pending_requests=pending_requests,
                         max_relations=5)


@social_bp.route("/send_flower/<username>", methods=["GET", "POST"])
@login_required
def send_flower(username):
    player = current_user
    if request.method == "POST":
        quantity = int(request.form.get("quantity", 1))
    else:
        quantity = 1
    success, msg = SocialService.send_flower(player, username, quantity)
    flash(msg)
    return redirect(url_for('player.view_player', username=username))


@social_bp.route("/request_relation/<username>/<rel_type>")
@login_required
def request_relation(username, rel_type):
    player = current_user
    success, msg = SocialService.request_relationship(player, username, rel_type)
    flash(msg)
    return redirect(url_for('player.view_player', username=username))


@social_bp.route("/accept_relation/<username>")
@login_required
def accept_relation(username):
    player = current_user
    success, msg = SocialService.accept_relationship(player, username)
    flash(msg)
    rel_type = 'hongyan'
    for r in player.relation_requests:
        if r.get('from') == username:
            rel_type = r.get('type', 'hongyan')
            break
    return redirect(url_for(f'social.{rel_type}'))


@social_bp.route("/reject_relation/<username>")
@login_required
def reject_relation(username):
    player = current_user
    success, msg = SocialService.reject_relationship(player, username)
    flash(msg)
    return redirect(url_for('social.social_index'))


@social_bp.route("/break_relation/<username>")
@login_required
def break_relation(username):
    player = current_user
    success, msg = SocialService.break_relationship(player, username)
    flash(msg)
    return redirect(url_for('social.social_index'))


# --- Marriage (结婚) ---

@social_bp.route("/propose_marriage/<username>")
@login_required
def propose_marriage(username):
    player = current_user
    success, msg = SocialService.propose_marriage(player, username)
    flash(msg)
    return redirect(url_for('player.view_player', username=username))


@social_bp.route("/accept_marriage/<username>")
@login_required
def accept_marriage(username):
    player = current_user
    success, msg = SocialService.accept_marriage(player, username)
    flash(msg)
    return redirect(url_for('player.marriage'))


@social_bp.route("/reject_marriage/<username>")
@login_required
def reject_marriage(username):
    player = current_user
    success, msg = SocialService.reject_marriage(player, username)
    flash(msg)
    return redirect(url_for('social.social_index'))


@social_bp.route("/divorce")
@login_required
def divorce():
    player = current_user
    success, msg = SocialService.divorce(player)
    flash(msg)
    return redirect(url_for('player.marriage'))


@social_bp.route("/spouse_teleport")
@login_required
def spouse_teleport():
    player = current_user
    success, msg = SocialService.spouse_teleport(player)
    flash(msg)
    if success:
        return redirect(url_for('game.scene'))
    return redirect(url_for('player.character'))


# --- Chat ---

def _fmt_notif_time(t):
    """把通知存储的时间字符串 'YYYY-MM-DD HH:MM' 格式化为 'H:MM'(去前导零)。"""
    try:
        dt = datetime.strptime(t, '%Y-%m-%d %H:%M')
        return f"{dt.hour}:{dt.minute}"
    except (ValueError, TypeError):
        return ''


@social_bp.route("/chat")
@login_required
def chat():
    player = current_user
    tab = request.args.get('tab', 'public')
    page = request.args.get('page', 1, type=int)
    per_page = 20

    messages = []
    total = 0
    context = {}

    if tab == 'country':
        messages = SocialService.get_country_messages(player.country, per_page)
        total = len(messages)
    elif tab == 'system':
        # 仅全局系统播报(receiver_id 为 NULL)，个人通知不再混入系统频道
        messages = SocialService.get_system_messages(None, per_page)
        total = len(messages)
    elif tab == 'private':
        messages = SocialService.get_private_messages(player.id, None, per_page)
        total = len(messages)
    elif tab == 'legion':
        context['in_legion'] = LegionService.get_player_member(player) is not None
        messages, total = LegionService.get_messages(player, page=page, per_page=per_page)
    elif tab == 'team':
        context['in_party'] = PartyService.get_player_party(player) is not None
        messages, total = PartyService.get_party_messages(player, page=page, per_page=per_page)
    elif tab == 'notification':
        # 通知频道：展示后刷新即清空
        all_notifs = player.notifications
        total = len(all_notifs)
        start = (page - 1) * per_page
        paged = all_notifs[start:start + per_page]
        messages = [{
            'content': n.get('message', ''),
            'time': _fmt_notif_time(n.get('time', '')),
        } for n in paged]
        # 刷新即取消：第1页读取后清空通知（翻页时已清空则跳过）
        if page == 1 and all_notifs:
            player.notifications = []
            db.session.commit()
    else:
        messages = SocialService.get_public_messages(per_page)
        total = len(messages)

    total_pages = (total + per_page - 1) // per_page if total else 1

    return render_template("chat.html",
                         player=player,
                         messages=messages,
                         tab=tab,
                         page=page,
                         per_page=per_page,
                         total=total,
                         total_pages=total_pages,
                         now=datetime.now(),
                         timedelta=timedelta,
                         **context)


@social_bp.route("/send_message", methods=["POST"])
@login_required
def send_message():
    player = current_user
    content = request.form.get("content", "").strip()
    tab = request.form.get("tab", "public")
    if not content:
        flash("内容不能为空")
        return redirect(url_for("social.chat", tab=tab))

    if tab == 'public':
        success, err = SocialService.send_public_message(player, content)
        if not success:
            flash(err)
        else:
            flash("发言成功")
    elif tab == 'country':
        SocialService.send_country_message(player, content)
        flash("发言成功")
    elif tab == 'legion':
        success, err = LegionService.send_message(player, content)
        if not success:
            flash(err)
        else:
            flash("发言成功")
    elif tab == 'team':
        success, err = PartyService.send_party_message(player, content)
        if not success:
            flash(err)
        else:
            flash("发言成功")
    return redirect(url_for("social.chat", tab=tab))


@social_bp.route("/private/<username>")
@login_required
def private_chat(username):
    player = current_user
    target = DataService.get_player_by_username(username)
    if not target:
        flash("玩家不存在")
        return redirect(url_for("social.chat"))

    # Check blacklist
    if SocialService.is_blocked(target, player.username):
        flash("对方已把你拉入黑名单")
        return redirect(url_for("social.chat"))

    messages = SocialService.get_private_messages(player.id, target.id, 20)
    return render_template("private_chat.html",
                         player=player,
                         target=target,
                         messages=messages)


@social_bp.route("/send_private/<username>", methods=["POST"])
@login_required
def send_private_message(username):
    player = current_user
    target = DataService.get_player_by_username(username)
    if not target:
        flash("玩家不存在")
        return redirect(url_for("social.chat"))

    # Check blacklist
    if SocialService.is_blocked(target, player.username):
        flash("对方已把你拉入黑名单，无法发送消息")
        return redirect(url_for("social.chat"))

    content = request.form.get("content", "").strip()
    if content:
        SocialService.send_private_message(player, target, content)
    return redirect(url_for("social.private_chat", username=username))


@social_bp.route("/gift", methods=["POST"])
@login_required
def send_gift():
    player = current_user
    target_username = request.form.get("target")
    gift_type = request.form.get("gift_type")
    gift_id = request.form.get("gift_id")
    quantity = int(request.form.get("quantity", 1))

    target = DataService.get_player_by_username(target_username)
    if not target:
        flash("玩家不存在")
        return redirect(request.referrer)

    success, msg = SocialService.send_gift(
        player, target, gift_type, gift_id, quantity)
    flash(msg)
    return redirect(url_for("social.private_chat", username=target_username))


@social_bp.route("/toggle_view/<view_type>")
@login_required
def toggle_view(view_type):
    player = current_user
    player.current_view = view_type
    db.session.commit()
    return redirect(url_for("social.chat"))


@social_bp.route("/gift_page/<username>")
@login_required
def gift_page(username):
    player = current_user
    target = DataService.get_player_by_username(username)
    if not target:
        return redirect(url_for("game.scene"))

    giftable_items = []
    for inv in DataService.get_inventory(player.id):
        if inv.quantity <= 0:
            continue
        item_data = DataService.get_item(inv.item_id)
        giftable_items.append({
            'item_id': inv.item_id,
            'quantity': inv.quantity,
            'is_bound': inv.is_bound,
            'item_data': item_data,
        })

    giftable_equipment = DataService.get_unequipped_equipment(player.id)

    return render_template("gift.html",
                         player=player,
                         target_player=target,
                         giftable_items=giftable_items,
                         giftable_equipment=giftable_equipment)