from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user

from services.forum_service import ForumService, PER_PAGE_DEFAULT
from models.player import PlayerModel

forum_bp = Blueprint('forum', __name__)


@forum_bp.app_context_processor
def inject_forum_unread():
    """向所有模板注入当前用户未读论坛互动通知数（用于场景论坛入口的感叹号提示）。"""
    from flask_login import current_user
    if current_user.is_authenticated:
        try:
            return {'forum_unread': ForumService.get_unread_count(current_user.id)}
        except Exception:
            return {'forum_unread': 0}
    return {'forum_unread': 0}


def _page():
    try:
        return max(1, int(request.args.get('page') or 1))
    except (TypeError, ValueError):
        return 1


@forum_bp.route('/')
@login_required
def index():
    tab = request.args.get('tab', 'new')
    if tab not in ('new', 'hot', 'pinned'):
        tab = 'new'
    posts, total, total_pages, page = ForumService.get_posts(
        tab=tab, page=_page(), per_page=PER_PAGE_DEFAULT)
    return render_template('forum_index.html', player=current_user,
                           posts=posts, tab=tab, total=total,
                           page=page, total_pages=total_pages,
                           is_admin=ForumService.is_admin(current_user),
                           mute=ForumService.get_active_mute(current_user.id))


@forum_bp.route('/post/new')
@login_required
def new_post():
    mute = ForumService.get_active_mute(current_user.id)
    return render_template('forum_edit.html', player=current_user,
                           post=None, mute=mute)


@forum_bp.route('/post/new', methods=['POST'])
@login_required
def create_post():
    ok, msg = ForumService.create_post(
        current_user, request.form.get('title'), request.form.get('content'))
    flash(msg)
    return redirect(url_for('forum.index') if ok else url_for('forum.new_post'))


@forum_bp.route('/post/<int:post_id>')
@login_required
def view_post(post_id):
    allow_deleted = ForumService.is_admin(current_user)
    post = ForumService.get_post(post_id, current_user, allow_deleted=allow_deleted)
    if not post:
        flash('帖子不存在')
        return redirect(url_for('forum.index'))
    comments = ForumService.get_comments(post.id, include_deleted=allow_deleted)
    state = ForumService.get_player_state(current_user.id, post.id)
    return render_template('forum_post.html', player=current_user, post=post,
                           comments=comments, state=state,
                           is_admin=ForumService.is_admin(current_user),
                           mute=ForumService.get_active_mute(current_user.id))


@forum_bp.route('/post/<int:post_id>/edit')
@login_required
def edit_post(post_id):
    post = ForumService.get_post(post_id, current_user, count_view=False,
                                 allow_deleted=ForumService.is_admin(current_user))
    if not post:
        flash('帖子不存在')
        return redirect(url_for('forum.index'))
    if post.author_id != current_user.id and not ForumService.is_admin(current_user):
        flash('无权编辑')
        return redirect(url_for('forum.view_post', post_id=post_id))
    return render_template('forum_edit.html', player=current_user,
                           post=post, mute=None)


@forum_bp.route('/post/<int:post_id>/edit', methods=['POST'])
@login_required
def update_post(post_id):
    ok, msg = ForumService.update_post(
        current_user, post_id, request.form.get('title'), request.form.get('content'))
    flash(msg)
    return redirect(url_for('forum.view_post', post_id=post_id))


@forum_bp.route('/post/<int:post_id>/delete', methods=['POST'])
@login_required
def delete_post(post_id):
    ok, msg = ForumService.delete_post(current_user, post_id)
    flash(msg)
    return redirect(url_for('forum.index'))


@forum_bp.route('/post/<int:post_id>/restore', methods=['POST'])
@login_required
def restore_post(post_id):
    ok, msg = ForumService.restore_post(current_user, post_id)
    flash(msg)
    return redirect(url_for('forum.view_post', post_id=post_id))


@forum_bp.route('/post/<int:post_id>/pin', methods=['POST'])
@login_required
def pin_post(post_id):
    ok, msg = ForumService.toggle_pin(current_user, post_id)
    flash(msg)
    return redirect(url_for('forum.view_post', post_id=post_id))


@forum_bp.route('/post/<int:post_id>/comment', methods=['POST'])
@login_required
def comment(post_id):
    ok, msg = ForumService.add_comment(current_user, post_id, request.form.get('content'))
    flash(msg)
    return redirect(url_for('forum.view_post', post_id=post_id))


@forum_bp.route('/comment/<int:comment_id>/delete', methods=['POST'])
@login_required
def delete_comment(comment_id):
    from models.player import ForumComment
    c = ForumComment.query.get(comment_id)
    post_id = c.post_id if c else 0
    ok, msg = ForumService.delete_comment(current_user, comment_id)
    flash(msg)
    return redirect(url_for('forum.view_post', post_id=post_id) if post_id else url_for('forum.index'))


@forum_bp.route('/post/<int:post_id>/like', methods=['POST'])
@login_required
def like(post_id):
    ok, msg = ForumService.toggle_reaction(current_user, post_id, 'like')
    flash(msg)
    return redirect(url_for('forum.view_post', post_id=post_id))


@forum_bp.route('/post/<int:post_id>/dislike', methods=['POST'])
@login_required
def dislike(post_id):
    ok, msg = ForumService.toggle_reaction(current_user, post_id, 'dislike')
    flash(msg)
    return redirect(url_for('forum.view_post', post_id=post_id))


@forum_bp.route('/post/<int:post_id>/favorite', methods=['POST'])
@login_required
def favorite(post_id):
    ok, msg = ForumService.toggle_favorite(current_user, post_id)
    flash(msg)
    return redirect(url_for('forum.view_post', post_id=post_id))


@forum_bp.route('/me')
@login_required
def me():
    posts, comments, favorites = ForumService.get_profile(current_user.id)
    return render_template('forum_me.html', player=current_user,
                           posts=posts, comments=comments, favorites=favorites)


@forum_bp.route('/admin')
@login_required
def admin():
    if not ForumService.is_admin(current_user):
        flash('无权访问')
        return redirect(url_for('forum.index'))
    deleted, _, _, _ = ForumService.get_posts(include_deleted=True, page=1, per_page=50)
    deleted = [p for p in deleted if p.status == 'deleted']
    mutes = ForumService.get_active_mutes()
    players = []
    q = (request.args.get('q') or '').strip()
    if q:
        players = PlayerModel.query.filter(
            PlayerModel.nickname.contains(q) | PlayerModel.username.contains(q)
        ).limit(10).all()
    return render_template('forum_admin.html', player=current_user,
                           deleted=deleted, mutes=mutes, players=players, q=q)


@forum_bp.route('/admin/player/<int:player_id>/mute', methods=['POST'])
@login_required
def mute_player(player_id):
    ok, msg = ForumService.mute_player(current_user, player_id,
                                       request.form.get('duration', '1d'),
                                       request.form.get('reason', ''))
    flash(msg)
    return redirect(url_for('forum.admin'))


@forum_bp.route('/admin/mute/<int:mute_id>/unmute', methods=['POST'])
@login_required
def unmute(mute_id):
    ok, msg = ForumService.unmute(current_user, mute_id)
    flash(msg)
    return redirect(url_for('forum.admin'))


@forum_bp.route('/notifications')
@login_required
def notifications():
    notifs = ForumService.get_notifications(current_user.id)
    unread = ForumService.get_unread_count(current_user.id)
    return render_template('forum_notifications.html', player=current_user,
                           notifications=notifs, unread=unread,
                           is_admin=ForumService.is_admin(current_user))


@forum_bp.route('/notification/<int:notif_id>/read')
@login_required
def read_notification(notif_id):
    n = ForumService.get_notification(notif_id, current_user.id)
    if n:
        ForumService.mark_read(notif_id, current_user.id)
        return redirect(url_for('forum.view_post', post_id=n.post_id))
    return redirect(url_for('forum.notifications'))


@forum_bp.route('/notifications/read-all', methods=['POST'])
@login_required
def read_all():
    ForumService.mark_all_read(current_user.id)
    flash('已全部标记为已读')
    return redirect(url_for('forum.notifications'))


@forum_bp.route('/notify-toggle', methods=['POST'])
@login_required
def notify_toggle():
    current_user.forum_interaction_notify = not bool(current_user.forum_interaction_notify)
    db.session.commit()
    flash('已' + ('关闭' if not current_user.forum_interaction_notify else '开启') + '互动消息提示')
    return redirect(request.referrer or url_for('forum.me'))
