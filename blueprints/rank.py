from flask import Blueprint, render_template
from flask_login import login_required, current_user
from models.player import PlayerModel, Achievement
from services.data_service import DataService
from services.social_service import SocialService
from services import db

rank_bp = Blueprint('rank', __name__, url_prefix='/rank')

RANK_TYPES = {
    'wealth': {'name': '财富榜', 'desc': '根据银两数量的排行', 'unit': '银'},
    'honor': {'name': '荣誉榜', 'desc': '根据荣誉点数的排行', 'unit': '荣'},
    'level': {'name': '等级榜', 'desc': '根据玩家等级的排行', 'unit': '级'},
    'achievement': {'name': '成就榜', 'desc': '根据成就数量的排行', 'unit': '个'},
    'charm': {'name': '魅力榜', 'desc': '根据魅力值的排行', 'unit': '魅'},
    'diligence': {'name': '勤奋榜', 'desc': '根据每日击杀怪物次数的排行', 'unit': '次'},
}


@rank_bp.route('/')
@login_required
def index():
    """Rank main page - list all rank types."""
    player = current_user
    return render_template('rank_index.html',
        player=player,
        rank_types=RANK_TYPES)


@rank_bp.route('/<rank_type>')
@login_required
def show(rank_type):
    """Show a specific ranking."""
    if rank_type not in RANK_TYPES:
        return render_template('rank_index.html',
            player=current_user,
            rank_types=RANK_TYPES)

    player = current_user
    rdef = RANK_TYPES[rank_type]

    if rank_type == 'wealth':
        rows = PlayerModel.query.order_by(PlayerModel.gold.desc()).limit(30).all()
        entries = [(p, p.gold) for p in rows]
        my_val = player.gold
    elif rank_type == 'honor':
        rows = PlayerModel.query.order_by(PlayerModel.honor.desc()).limit(30).all()
        entries = [(p, p.honor) for p in rows]
        my_val = player.honor
    elif rank_type == 'level':
        rows = PlayerModel.query.order_by(
            PlayerModel.level.desc(), PlayerModel.experience.desc()).limit(30).all()
        entries = [(p, p.level) for p in rows]
        my_val = player.level
    elif rank_type == 'achievement':
        rows = PlayerModel.query.all()
        entries = []
        for p in rows:
            cnt = Achievement.query.filter_by(player_id=p.id, claimed=True).count()
            entries.append((p, cnt))
        entries.sort(key=lambda x: x[1], reverse=True)
        entries = entries[:30]
        my_val = Achievement.query.filter_by(player_id=player.id, claimed=True).count()
    elif rank_type == 'charm':
        rows = PlayerModel.query.order_by(PlayerModel.charm.desc()).limit(30).all()
        entries = [(p, p.charm or 0) for p in rows]
        my_val = player.charm or 0
    elif rank_type == 'diligence':
        from services.activity_service import ActivityService
        rows = PlayerModel.query.all()
        entries = []
        for p in rows:
            kills = ActivityService.get_today_value(p, 'kill_count') or 0
            entries.append((p, kills))
        entries.sort(key=lambda x: x[1], reverse=True)
        entries = entries[:30]
        from services.activity_service import ActivityService as AS
        my_val = AS.get_today_value(player, 'kill_count') or 0
    else:
        entries = []
        my_val = 0

    # Find my rank
    my_rank = None
    for i, (p, v) in enumerate(entries):
        if p.id == player.id:
            my_rank = i + 1
            break
    if my_rank is None and my_val > 0:
        if rank_type == 'wealth':
            my_rank = PlayerModel.query.filter(PlayerModel.gold > player.gold).count() + 1
        elif rank_type == 'honor':
            my_rank = PlayerModel.query.filter(PlayerModel.honor > player.honor).count() + 1
        elif rank_type == 'level':
            my_rank = PlayerModel.query.filter(
                (PlayerModel.level > player.level) |
                ((PlayerModel.level == player.level) & (PlayerModel.experience > player.experience))
            ).count() + 1
        elif rank_type == 'achievement':
            my_ach = Achievement.query.filter_by(player_id=player.id, claimed=True).count()
            my_rank = sum(1 for p, v in entries if v > my_ach) + 1
        elif rank_type == 'charm':
            my_rank = PlayerModel.query.filter(PlayerModel.charm > (player.charm or 0)).count() + 1

    return render_template('rank_show.html',
        player=player,
        rank_type=rank_type,
        rdef=rdef,
        entries=entries,
        my_val=my_val,
        my_rank=my_rank,
        is_online=SocialService._is_online)