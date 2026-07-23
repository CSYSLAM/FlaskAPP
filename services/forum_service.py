from datetime import datetime, timedelta

from services import db
from models.player import (
    PlayerModel, ForumPost, ForumComment, ForumReaction, ForumFavorite, ForumMute
)

PER_PAGE_DEFAULT = 15


class ForumService:
    """论坛业务逻辑：帖子、评论、互动、收藏、禁言与管理员操作。"""

    @staticmethod
    def is_admin(player):
        return bool(getattr(player, 'is_designer', False))

    @classmethod
    def get_active_mute(cls, player_id):
        now = datetime.utcnow()
        mute = ForumMute.query.filter_by(player_id=player_id, is_active=True).order_by(
            ForumMute.created_at.desc()).first()
        if not mute:
            return None
        if mute.muted_until and mute.muted_until <= now:
            mute.is_active = False
            db.session.commit()
            return None
        return mute

    @classmethod
    def is_muted(cls, player):
        return cls.get_active_mute(player.id) is not None

    @classmethod
    def _blocked_if_muted(cls, player):
        mute = cls.get_active_mute(player.id)
        if mute:
            return cls._mute_text(mute)
        return None

    @classmethod
    def _validate_post(cls, title, content):
        title = (title or '').strip()
        content = (content or '').strip()
        if len(title) < 2 or len(title) > 40:
            return None, None, "标题需2-40字"
        if len(content) < 5 or len(content) > 2000:
            return None, None, "正文需5-2000字"
        return title, content, None

    @classmethod
    def create_post(cls, player, title, content):
        muted_msg = cls._blocked_if_muted(player)
        if muted_msg:
            return False, muted_msg
        title, content, err = cls._validate_post(title, content)
        if err:
            return False, err
        post = ForumPost(author_id=player.id, title=title, content=content)
        db.session.add(post)
        db.session.commit()
        return True, "发帖成功"

    @classmethod
    def update_post(cls, player, post_id, title, content):
        post = ForumPost.query.get(post_id)
        if not post or post.status != 'active':
            return False, "帖子不存在"
        if post.author_id != player.id and not cls.is_admin(player):
            return False, "无权编辑"
        title, content, err = cls._validate_post(title, content)
        if err:
            return False, err
        post.title = title
        post.content = content
        post.updated_at = datetime.utcnow()
        db.session.commit()
        return True, "帖子已更新"

    @classmethod
    def delete_post(cls, player, post_id):
        post = ForumPost.query.get(post_id)
        if not post or post.status != 'active':
            return False, "帖子不存在或已删除"
        if post.author_id != player.id and not cls.is_admin(player):
            return False, "无权删除"
        post.status = 'deleted'
        post.deleted_at = datetime.utcnow()
        post.deleted_by = player.id
        post.is_pinned = False
        db.session.commit()
        return True, "帖子已删除"

    @classmethod
    def restore_post(cls, admin, post_id):
        if not cls.is_admin(admin):
            return False, "无权操作"
        post = ForumPost.query.get(post_id)
        if not post:
            return False, "帖子不存在"
        post.status = 'active'
        post.deleted_at = None
        post.deleted_by = None
        db.session.commit()
        return True, "帖子已恢复"

    @classmethod
    def toggle_pin(cls, admin, post_id):
        if not cls.is_admin(admin):
            return False, "无权操作"
        post = ForumPost.query.get(post_id)
        if not post or post.status != 'active':
            return False, "帖子不存在"
        post.is_pinned = not post.is_pinned
        post.pinned_at = datetime.utcnow() if post.is_pinned else None
        post.pinned_by = admin.id if post.is_pinned else None
        db.session.commit()
        return True, "已置顶" if post.is_pinned else "已取消置顶"

    @classmethod
    def get_posts(cls, tab='new', page=1, per_page=PER_PAGE_DEFAULT, include_deleted=False):
        q = ForumPost.query
        if not include_deleted:
            q = q.filter_by(status='active')
        if tab == 'hot':
            q = q.order_by(
                ForumPost.is_pinned.desc(),
                (ForumPost.like_count * 3 + ForumPost.favorite_count * 2 +
                 ForumPost.comment_count * 2 - ForumPost.dislike_count + ForumPost.view_count).desc(),
                ForumPost.created_at.desc())
        elif tab == 'pinned':
            q = q.filter_by(is_pinned=True).order_by(ForumPost.pinned_at.desc())
        else:
            q = q.order_by(ForumPost.is_pinned.desc(), ForumPost.created_at.desc())
        total = q.count()
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = min(max(1, page), total_pages)
        rows = q.offset((page - 1) * per_page).limit(per_page).all()
        return rows, total, total_pages, page

    @classmethod
    def get_post(cls, post_id, viewer=None, count_view=True, allow_deleted=False):
        post = ForumPost.query.get(post_id)
        if not post:
            return None
        if post.status != 'active' and not allow_deleted:
            return None
        if count_view and post.status == 'active':
            post.view_count = (post.view_count or 0) + 1
            db.session.commit()
        return post

    @classmethod
    def get_comments(cls, post_id, include_deleted=False):
        q = ForumComment.query.filter_by(post_id=post_id)
        if not include_deleted:
            q = q.filter_by(status='active')
        return q.order_by(ForumComment.created_at.asc()).all()

    @classmethod
    def add_comment(cls, player, post_id, content):
        muted_msg = cls._blocked_if_muted(player)
        if muted_msg:
            return False, muted_msg
        post = ForumPost.query.get(post_id)
        if not post or post.status != 'active':
            return False, "帖子不存在"
        content = (content or '').strip()
        if len(content) < 1 or len(content) > 500:
            return False, "评论需1-500字"
        c = ForumComment(post_id=post_id, author_id=player.id, content=content)
        post.comment_count = (post.comment_count or 0) + 1
        db.session.add(c)
        db.session.commit()
        return True, "评论成功"

    @classmethod
    def delete_comment(cls, player, comment_id):
        c = ForumComment.query.get(comment_id)
        if not c or c.status != 'active':
            return False, "评论不存在"
        if c.author_id != player.id and not cls.is_admin(player):
            return False, "无权删除"
        c.status = 'deleted'
        c.deleted_at = datetime.utcnow()
        c.deleted_by = player.id
        post = ForumPost.query.get(c.post_id)
        if post and post.comment_count > 0:
            post.comment_count -= 1
        db.session.commit()
        return True, "评论已删除"

    @classmethod
    def toggle_reaction(cls, player, post_id, reaction):
        muted_msg = cls._blocked_if_muted(player)
        if muted_msg:
            return False, muted_msg
        if reaction not in ('like', 'dislike'):
            return False, "操作无效"
        post = ForumPost.query.get(post_id)
        if not post or post.status != 'active':
            return False, "帖子不存在"
        r = ForumReaction.query.filter_by(post_id=post_id, player_id=player.id).first()
        if r and r.reaction == reaction:
            cls._apply_reaction_delta(post, reaction, -1)
            db.session.delete(r)
            db.session.commit()
            return True, "已取消"
        if r:
            cls._apply_reaction_delta(post, r.reaction, -1)
            r.reaction = reaction
            r.created_at = datetime.utcnow()
        else:
            r = ForumReaction(post_id=post_id, player_id=player.id, reaction=reaction)
            db.session.add(r)
        cls._apply_reaction_delta(post, reaction, 1)
        db.session.commit()
        return True, "操作成功"

    @staticmethod
    def _apply_reaction_delta(post, reaction, delta):
        if reaction == 'like':
            post.like_count = max(0, (post.like_count or 0) + delta)
        else:
            post.dislike_count = max(0, (post.dislike_count or 0) + delta)

    @classmethod
    def toggle_favorite(cls, player, post_id):
        muted_msg = cls._blocked_if_muted(player)
        if muted_msg:
            return False, muted_msg
        post = ForumPost.query.get(post_id)
        if not post or post.status != 'active':
            return False, "帖子不存在"
        fav = ForumFavorite.query.filter_by(post_id=post_id, player_id=player.id).first()
        if fav:
            post.favorite_count = max(0, (post.favorite_count or 0) - 1)
            db.session.delete(fav)
            db.session.commit()
            return True, "已取消收藏"
        fav = ForumFavorite(post_id=post_id, player_id=player.id)
        post.favorite_count = (post.favorite_count or 0) + 1
        db.session.add(fav)
        db.session.commit()
        return True, "已收藏"

    @classmethod
    def get_player_state(cls, player_id, post_id):
        r = ForumReaction.query.filter_by(post_id=post_id, player_id=player_id).first()
        fav = ForumFavorite.query.filter_by(post_id=post_id, player_id=player_id).first()
        return {'reaction': r.reaction if r else None, 'favorited': fav is not None}

    @classmethod
    def get_profile(cls, player_id):
        posts = ForumPost.query.filter_by(author_id=player_id).order_by(ForumPost.created_at.desc()).limit(30).all()
        comments = ForumComment.query.filter_by(author_id=player_id).order_by(ForumComment.created_at.desc()).limit(30).all()
        favorites = ForumFavorite.query.filter_by(player_id=player_id).order_by(ForumFavorite.created_at.desc()).limit(30).all()
        return posts, comments, favorites

    @classmethod
    def mute_player(cls, admin, player_id, duration, reason):
        if not cls.is_admin(admin):
            return False, "无权操作"
        target = PlayerModel.query.get(player_id)
        if not target:
            return False, "玩家不存在"
        if target.id == admin.id:
            return False, "不能禁言自己"
        for m in ForumMute.query.filter_by(player_id=player_id, is_active=True).all():
            m.is_active = False
        until = cls._duration_to_until(duration)
        mute = ForumMute(player_id=player_id, muted_by=admin.id,
                         reason=(reason or '').strip()[:200], muted_until=until)
        db.session.add(mute)
        db.session.commit()
        return True, "已禁言"

    @classmethod
    def unmute(cls, admin, mute_id):
        if not cls.is_admin(admin):
            return False, "无权操作"
        mute = ForumMute.query.get(mute_id)
        if not mute:
            return False, "记录不存在"
        mute.is_active = False
        db.session.commit()
        return True, "已解除禁言"

    @staticmethod
    def _duration_to_until(duration):
        now = datetime.utcnow()
        if duration == '1h':
            return now + timedelta(hours=1)
        if duration == '1d':
            return now + timedelta(days=1)
        if duration == '7d':
            return now + timedelta(days=7)
        return None

    @staticmethod
    def _mute_text(mute):
        if mute.muted_until:
            return f"你已被禁言，至{mute.muted_until.strftime('%m-%d %H:%M')}"
        return "你已被永久禁言"

    @classmethod
    def get_active_mutes(cls):
        return ForumMute.query.filter_by(is_active=True).order_by(ForumMute.created_at.desc()).all()
