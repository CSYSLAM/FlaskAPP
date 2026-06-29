from flask import Blueprint, render_template, redirect, url_for, request, session, flash
from flask_login import login_required, current_user
from services import db
from services.activity_service import ActivityService
from services.data_service import DataService

activity_bp = Blueprint('activity', __name__, url_prefix='/activity')


@activity_bp.route("/")
@login_required
def index():
    player = current_user
    daily_progress = ActivityService.get_daily_progress(player)
    total_points = ActivityService.get_total_activity_points(player)
    reward_tiers = ActivityService.get_reward_tiers_status(player)
    return render_template("activities.html",
                         player=player,
                         daily_progress=daily_progress,
                         total_points=total_points,
                         reward_tiers=reward_tiers)


# --- Daily Sign In ---

@activity_bp.route("/sign_in")
@login_required
def sign_in_page():
    player = current_user
    done = player.get_today_activity('sign_in_done')
    sign_total, claimed = ActivityService.get_sign_info(player)
    sign_rewards = ActivityService.SIGN_REWARDS
    return render_template("daily_sign.html",
                         player=player,
                         done=done,
                         sign_total=sign_total,
                         claimed=claimed,
                         sign_rewards=sign_rewards)


@activity_bp.route("/do_sign_in")
@login_required
def do_sign_in():
    player = current_user
    success, msg = ActivityService.sign_in(player)
    flash(msg)
    return redirect(url_for('activity.sign_in_page'))


@activity_bp.route("/claim_sign_reward/<int:days>")
@login_required
def claim_sign_reward(days):
    player = current_user
    success, msg = ActivityService.claim_sign_reward(player, days)
    flash(msg)
    return redirect(url_for('activity.sign_in_page'))


# --- Smash Egg ---

@activity_bp.route("/smash_egg")
@login_required
def smash_egg_page():
    player = current_user
    free_remaining = ActivityService.get_egg_free_remaining(player)
    done = player.get_today_activity('smash_egg_done')
    return render_template("smash_egg.html",
                         player=player,
                         free_remaining=free_remaining,
                         done=done)


@activity_bp.route("/do_smash_egg")
@login_required
def do_smash_egg():
    player = current_user
    use_free = request.args.get('free', '1') == '1'
    success, msg = ActivityService.smash_egg(player, use_free=use_free)
    flash(msg)
    return redirect(url_for('activity.smash_egg_page'))


# --- Rock Paper Scissors ---

@activity_bp.route("/rps")
@login_required
def rps_page():
    player = current_user
    done = player.get_today_activity('rps_done')
    return render_template("rps.html", player=player, done=done)


@activity_bp.route("/do_rps/<choice>")
@login_required
def do_rps(choice):
    player = current_user
    if choice not in ('rock', 'scissors', 'paper'):
        flash("无效选择")
        return redirect(url_for('activity.rps_page'))
    success, msg = ActivityService.play_rps(player, choice)
    flash(msg)
    return redirect(url_for('activity.rps_page'))


# --- Quiz ---

@activity_bp.route("/quiz")
@login_required
def quiz_page():
    player = current_user
    done = player.get_today_activity('quiz_done')
    can_play = done < 5
    question = None
    question_idx = 0
    if can_play:
        question = ActivityService.start_quiz(player)
        if question:
            question_idx = ActivityService.QUIZ_POOL.index(question)
        else:
            can_play = False
    return render_template("quiz.html",
                         player=player,
                         done=done,
                         can_play=can_play,
                         question=question,
                         question_idx=question_idx)


@activity_bp.route("/do_quiz", methods=["POST"])
@login_required
def do_quiz():
    player = current_user
    question_idx = int(request.form.get('question_idx', 0))
    answer = request.form.get('answer', '')
    success, msg = ActivityService.answer_quiz(player, question_idx, answer)
    flash(msg)
    return redirect(url_for('activity.quiz_page'))


# --- Study ---

@activity_bp.route("/study")
@login_required
def study_page():
    player = current_user
    status = ActivityService.get_study_status(player)
    return render_template("study.html", player=player, status=status)


@activity_bp.route("/start_study")
@login_required
def start_study():
    player = current_user
    success, msg = ActivityService.start_study(player)
    flash(msg)
    return redirect(url_for('activity.study_page'))


@activity_bp.route("/finish_study")
@login_required
def finish_study():
    player = current_user
    success, msg = ActivityService.finish_study(player)
    flash(msg)
    return redirect(url_for('activity.study_page'))


# --- Card Flip ---

@activity_bp.route("/card_flip")
@login_required
def card_flip_page():
    player = current_user
    done = player.get_today_activity('card_flip_done')
    return render_template("card_flip.html", player=player, done=done)


@activity_bp.route("/do_card_flip")
@login_required
def do_card_flip():
    player = current_user
    success, msg = ActivityService.card_flip(player)
    flash(msg)
    return redirect(url_for('activity.card_flip_page'))


# --- Lucky Coin Exchange ---

@activity_bp.route("/lucky_exchange")
@login_required
def lucky_exchange():
    player = current_user
    exchange_items = ActivityService.LUCKY_COIN_EXCHANGE
    coin_item = DataService.get_inventory_item(player.id, 'lucky_coin')
    coin_count = coin_item.quantity if coin_item else 0
    return render_template("lucky_exchange.html",
                         player=player,
                         exchange_items=exchange_items,
                         coin_count=coin_count)


@activity_bp.route("/do_lucky_exchange/<item_id>")
@login_required
def do_lucky_exchange(item_id):
    player = current_user
    success, msg = ActivityService.exchange_lucky_coin(player, item_id)
    flash(msg)
    return redirect(url_for('activity.lucky_exchange'))


# --- Activity Points Reward Claim ---

@activity_bp.route("/claim_activity_reward/<int:tier_points>")
@login_required
def claim_activity_reward(tier_points):
    player = current_user
    success, msg = ActivityService.claim_activity_reward(player, tier_points)
    flash(msg)
    return redirect(url_for('activity.index'))


# --- Daily NPC Tasks (任务使者) ---

# Activity page entry: shows task list with teleport links
@activity_bp.route("/daily_tasks")
@login_required
def daily_tasks():
    player = current_user
    tasks = ActivityService.get_daily_tasks_status(player)
    return render_template("daily_tasks.html", player=player, tasks=tasks)


# NPC task envoy page: shows tasks with accept/progress/complete
@activity_bp.route("/npc_daily_tasks")
@login_required
def npc_daily_tasks():
    player = current_user
    tasks = ActivityService.get_daily_tasks_status(player)
    return render_template("npc_daily_tasks.html", player=player, tasks=tasks)


# Task detail page: accept/progress/complete a single task
@activity_bp.route("/daily_task_detail/<task_id>")
@login_required
def daily_task_detail(task_id):
    player = current_user
    tasks = ActivityService.get_daily_tasks_status(player)
    task = None
    for t in tasks:
        if t['id'] == task_id:
            task = t
            break
    if not task:
        flash("无效的任务")
        return redirect(url_for('activity.npc_daily_tasks'))
    return render_template("daily_task_detail.html", player=player, task=task)


@activity_bp.route("/accept_daily_task/<task_id>")
@login_required
def accept_daily_task(task_id):
    player = current_user
    success, msg = ActivityService.accept_daily_task(player, task_id)
    flash(msg)
    return redirect(url_for('activity.daily_task_detail', task_id=task_id))


@activity_bp.route("/complete_daily_task/<task_id>")
@login_required
def complete_daily_task(task_id):
    player = current_user
    success, msg = ActivityService.complete_daily_task(player, task_id)
    flash(msg)
    return redirect(url_for('activity.daily_task_detail', task_id=task_id))


# Teleport to task NPC (任务使者 in player's country center)
@activity_bp.route("/teleport_to_task_npc/<task_id>")
@login_required
def teleport_to_task_npc(task_id):
    player = current_user
    location = ActivityService.get_task_npc_location(player)
    player.current_location = location
    from services import db
    db.session.commit()
    return redirect(url_for('game.scene'))


# Teleport to task target location (where target monsters are)
@activity_bp.route("/teleport_to_target/<task_id>")
@login_required
def teleport_to_target(task_id):
    player = current_user
    location = ActivityService.get_task_target_location(player)
    player.current_location = location
    from services import db
    db.session.commit()
    return redirect(url_for('game.scene'))


# --- Finance (三国理财·股市) ---

@activity_bp.route("/finance")
@login_required
def finance_page():
    player = current_user
    from services.finance_service import FinanceService
    market = FinanceService.get_market()
    summary = FinanceService.get_player_summary(player)
    next_refresh = FinanceService.get_next_refresh_in()
    bandits = FinanceService.get_bandit_status()
    return render_template("finance.html",
                         player=player,
                         market=market,
                         summary=summary,
                         next_refresh=next_refresh,
                         bandits=bandits)


@activity_bp.route("/finance/rules")
@login_required
def finance_rules():
    player = current_user
    return render_template("finance_rules.html", player=player)


@activity_bp.route("/finance/stock/<stock_id>")
@login_required
def finance_stock_page(stock_id):
    player = current_user
    from services.finance_service import FinanceService
    stock = FinanceService.get_stock(stock_id)
    if not stock:
        flash("无此股票")
        return redirect(url_for('activity.finance_page'))
    summary = FinanceService.get_player_summary(player)
    holding = None
    fd = player.finance_data or {}
    h = (fd.get('holdings') or {}).get(stock_id)
    if h and h.get('shares', 0) > 0:
        holding = {
            'shares': int(h['shares']),
            'avg_cost': round(float(h.get('avg_cost', 0)), 2),
        }
    next_refresh = FinanceService.get_next_refresh_in()
    return render_template("finance_stock.html",
                         player=player,
                         stock=stock,
                         summary=summary,
                         holding=holding,
                         next_refresh=next_refresh)


@activity_bp.route("/finance/buy", methods=["POST"])
@login_required
def finance_buy():
    player = current_user
    stock_id = request.form.get('stock_id', '')
    shares = request.form.get('shares', '0')
    from services.finance_service import FinanceService
    success, msg = FinanceService.buy(player, stock_id, shares)
    flash(msg)
    return redirect(url_for('activity.finance_stock_page', stock_id=stock_id))


@activity_bp.route("/finance/sell", methods=["POST"])
@login_required
def finance_sell():
    player = current_user
    stock_id = request.form.get('stock_id', '')
    shares = request.form.get('shares', '0')
    from services.finance_service import FinanceService
    success, msg = FinanceService.sell(player, stock_id, shares)
    flash(msg)
    return redirect(url_for('activity.finance_stock_page', stock_id=stock_id))


@activity_bp.route("/finance/holdings")
@login_required
def finance_holdings():
    player = current_user
    from services.finance_service import FinanceService
    holdings = FinanceService.get_player_holdings(player)
    summary = FinanceService.get_player_summary(player)
    return render_template("finance_holdings.html",
                         player=player,
                         holdings=holdings,
                         summary=summary)


@activity_bp.route("/finance/rank/finance")
@login_required
def finance_rank_finance():
    """股神榜：按股市总盈亏排行（仅在金珠理财界面显示）。"""
    player = current_user
    from services.finance_service import FinanceService
    from models.player import PlayerModel
    rows = PlayerModel.query.all()
    entries = []
    for p in rows:
        profit = FinanceService.get_player_profit(p)
        if abs(profit) > 0.001 or (p.finance_data or {}).get('holdings'):
            entries.append((p, round(profit, 2)))
    entries.sort(key=lambda x: x[1], reverse=True)
    entries = entries[:30]
    my_val = round(FinanceService.get_player_profit(player), 2)
    my_rank = None
    for i, (p, v) in enumerate(entries):
        if p.id == player.id:
            my_rank = i + 1
            break
    if my_rank is None and my_val > 0:
        my_rank = sum(1 for p, v in entries if v > my_val) + 1
    from services.social_service import SocialService
    return render_template("finance_rank.html",
                         player=player,
                         rank_type='finance',
                         title='股神榜',
                         unit='珠',
                         entries=entries,
                         my_val=my_val,
                         my_rank=my_rank,
                         is_online=SocialService._is_online)


@activity_bp.route("/finance/rank/bandit")
@login_required
def finance_rank_bandit():
    """义士榜：按各城市击杀劫匪总数排行（城市维度，仅在金珠理财界面显示）。"""
    player = current_user
    from services.finance_service import FinanceService
    city_rows = FinanceService.get_city_kill_rank(30)
    return render_template("finance_rank.html",
                         player=player,
                         rank_type='bandit',
                         title='义士榜',
                         unit='次',
                         entries=city_rows,
                         my_val=0,
                         my_rank=None,
                         is_online=None)


