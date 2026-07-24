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
    phase = FinanceService.get_market_phase()
    return render_template("finance.html",
                         player=player,
                         market=market,
                         summary=summary,
                         next_refresh=next_refresh,
                         bandits=bandits,
                         phase=phase)


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
    phase = FinanceService.get_market_phase()
    tradable = FinanceService.is_tradable()
    shows_price = FinanceService.shows_price()
    return render_template("finance_stock.html",
                         player=player,
                         stock=stock,
                         summary=summary,
                         holding=holding,
                         next_refresh=next_refresh,
                         phase=phase,
                         tradable=tradable,
                         shows_price=shows_price)


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


@activity_bp.route("/finance/order", methods=["POST"])
@login_required
def finance_place_order():
    """提交委托单（限价单，任何时段可挂单）。"""
    player = current_user
    stock_id = request.form.get('stock_id', '')
    side = request.form.get('side', 'buy')
    shares = request.form.get('shares', '0')
    limit_price = request.form.get('limit_price', '0')
    from services.finance_service import FinanceService
    success, msg = FinanceService.place_order(player, stock_id, side, shares, limit_price)
    flash(msg)
    return redirect(url_for('activity.finance_stock_page', stock_id=stock_id))


@activity_bp.route("/finance/orders")
@login_required
def finance_orders():
    """我的委托单列表。"""
    player = current_user
    from services.finance_service import FinanceService
    orders = FinanceService.get_player_orders(player)
    summary = FinanceService.get_player_summary(player)
    phase = FinanceService.get_market_phase()
    return render_template("finance_orders.html",
                         player=player,
                         orders=orders,
                         summary=summary,
                         phase=phase)


@activity_bp.route("/finance/order/cancel/<order_id>", methods=["POST"])
@login_required
def finance_cancel_order(order_id):
    player = current_user
    from services.finance_service import FinanceService
    success, msg = FinanceService.cancel_order(player, order_id)
    flash(msg)
    return redirect(url_for('activity.finance_orders'))


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
    all_entries = entries
    entries = all_entries[:30]
    my_val = round(FinanceService.get_player_profit(player), 2)
    my_rank = None
    for i, (p, v) in enumerate(all_entries):
        if p.id == player.id:
            my_rank = i + 1
            break
    if my_rank is None and my_val > 0:
        my_rank = sum(1 for p, v in all_entries if v > my_val) + 1
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


# --- 蛮夷入侵活动（南蛮 / 北夷） ---

@activity_bp.route("/barbarian")
@login_required
def barbarian_index():
    """蛮夷活动入口：南蛮 / 北夷 切换，凭证兑奖、公告。"""
    player = current_user
    side = request.args.get("side") or '南'
    if side not in ('南', '北'):
        side = '南'
    from services.barbarian_service import BarbarianService
    state = BarbarianService.get_state(player, side)
    return render_template("activity_barbarian.html",
                           player=player, side=side, state=state)


@activity_bp.route("/barbarian/<side>")
@login_required
def barbarian_invasion(side):
    """兼容旧链接：转发到入口（带 side 参数）。"""
    return redirect(url_for("activity.barbarian_index", side=side))


@activity_bp.route("/barbarian/guide")
@login_required
def barbarian_guide():
    """蛮夷入侵玩法公告（入口放在蛮夷活动内）。"""
    player = current_user
    import json as _json
    guide = {}
    try:
        with open("data/barbarian_guide.json", "r", encoding="utf-8") as _f:
            guide = _json.load(_f)
    except Exception:
        guide = {}
    return render_template("activity_barbarian_guide.html", player=player, n=guide)


@activity_bp.route("/redeem")
@login_required
def redeem():
    """兑奖中心：列出各类兑奖（当前仅凭证兑奖）。"""
    return render_template("activity_redeem_hub.html", player=current_user)


@activity_bp.route("/redeem/credentials")
@login_required
def redeem_credentials():
    """凭证兑奖：消耗 [活]来袭凭证 兑换奖励（其他/装备/辅助 分类切换）。"""
    player = current_user
    from services.barbarian_service import BarbarianService
    from services.data_service import DataService
    cat = request.args.get("cat") or '其他'
    full = BarbarianService.get_redeem_catalog()
    aux_ids = {'juhunfan_suipian'}
    def cat_of(e):
        if e.get('kind') == 'equip':
            return '装备'
        if e.get('item_id') in aux_ids:
            return '辅助'
        return '其他'
    cats = {'其他': [], '装备': [], '辅助': []}
    for e in full:
        cats[cat_of(e)].append(e)
    catalog = cats.get(cat, [])
    balance = BarbarianService.get_credit_balance(player)
    has_box = bool(DataService.get_inventory_item(player.id, 'manyi_baoxiang'))
    has_key = bool(DataService.get_inventory_item(player.id, 'chest_key'))
    return render_template("activity_redeem.html",
                           player=player,
                           catalog=catalog,
                           balance=balance,
                           has_box=has_box,
                           has_key=has_key,
                           cat=cat)


@activity_bp.route("/do_redeem/<item_id>", methods=["POST"])
@login_required
def do_redeem(item_id):
    player = current_user
    from services.barbarian_service import BarbarianService
    qty = request.form.get("qty") or request.args.get("qty") or 1
    try:
        qty = int(qty)
    except (TypeError, ValueError):
        qty = 1
    cat = request.form.get("cat") or request.args.get("cat") or '其他'
    ok, msg = BarbarianService.redeem(player, item_id, qty)
    flash(msg)
    return redirect(url_for("activity.redeem_credentials", cat=cat))


@activity_bp.route("/open_box", methods=["POST"])
@login_required
def open_box():
    """开启 [活]蛮夷宝箱 / 蛮夷宝匣（需宝匣钥匙）。"""
    player = current_user
    from services.barbarian_service import BarbarianService
    ok, msg = BarbarianService.open_chest(player)
    flash(msg)
    return redirect(url_for("activity.redeem_credentials", cat=request.form.get("cat") or request.args.get("cat") or '其他'))


@activity_bp.route("/barbarian/admin_refresh", methods=["POST"])
@login_required
def barbarian_admin_refresh():
    """管理员手动刷新蛮夷入侵（士卒补满、首领复活）。"""
    player = current_user
    if not getattr(player, "is_designer", False):
        flash("无权限")
        return redirect(url_for("activity.barbarian_index"))
    from services.barbarian_service import BarbarianService
    side = request.form.get("side") or request.args.get("side")
    BarbarianService.admin_refresh(side)
    if side in ('南', '北'):
        flash(("北夷" if side == "北" else "南蛮") + "入侵已刷新")
        return redirect(url_for("activity.barbarian_invasion", side=side))
    flash("蛮夷入侵已刷新")
    return redirect(url_for("activity.barbarian_index"))


@activity_bp.route("/barbarian/admin_clear", methods=["POST"])
@login_required
def barbarian_admin_clear():
    """管理员手动清零蛮夷入侵（士卒清零、首领复苏中）。"""
    player = current_user
    if not getattr(player, "is_designer", False):
        flash("无权限")
        return redirect(url_for("activity.barbarian_index"))
    from services.barbarian_service import BarbarianService
    side = request.form.get("side") or request.args.get("side")
    BarbarianService.admin_clear(side)
    if side in ('南', '北'):
        flash(("北夷" if side == "北" else "南蛮") + "入侵已清零")
        return redirect(url_for("activity.barbarian_invasion", side=side))
    flash("蛮夷入侵已清零")
    return redirect(url_for("activity.barbarian_index"))


@activity_bp.route("/announce")
@login_required
def announce():
    """公告栏：列出公告条目，点击查看详情。"""
    player = current_user
    import json as _json
    notices = []
    try:
        with open("data/announcements.json", "r", encoding="utf-8") as _f:
            notices = _json.load(_f)
    except Exception:
        notices = []
    return render_template("activity_announce.html", player=player, notices=notices)


@activity_bp.route("/announce/<int:idx>")
@login_required
def announce_detail(idx):
    """公告详情：单条公告。"""
    player = current_user
    import json as _json
    notices = []
    try:
        with open("data/announcements.json", "r", encoding="utf-8") as _f:
            notices = _json.load(_f)
    except Exception:
        notices = []
    if idx < 0 or idx >= len(notices):
        flash("公告不存在")
        return redirect(url_for("activity.announce"))
    return render_template("activity_announce_detail.html",
                           player=player, n=notices[idx], idx=idx)


@activity_bp.route("/barbarian_forge", methods=["GET", "POST"])
@login_required
def barbarian_forge():
    """铁匠铺·菊香神炉：消耗对应部位图纸 + 25级装备材料 + 银两，50% 打造成功。"""
    player = current_user
    from services.barbarian_service import BarbarianService, JUXIANG_BLUEPRINT
    from services.data_service import DataService
    from services.crafting_service import CraftingService
    msg = None
    if request.method == "POST":
        template_id = request.form.get("template_id") or request.args.get("template_id")
        ok, msg = BarbarianService.forge_juxiang(player, template_id)
        flash(msg)
        return redirect(url_for("activity.barbarian_forge"))
    # 玩家持有的菊香图纸（按部位）
    owned = []
    for tmpl, bp in JUXIANG_BLUEPRINT.items():
        inv = DataService.get_inventory_item(player.id, bp)
        qty = inv.quantity if inv else 0
        if qty > 0:
            owned.append({
                'template_id': tmpl,
                'bp_name': (DataService.get_item(bp) or {}).get('name', bp),
                'equip_name': (DataService.get_equipment_template(tmpl) or {}).get('name', tmpl),
                'qty': qty,
            })
    # 25 级装备打造材料需求（与任一菊香部件一致）
    rep = DataService.get_equipment_template('juxiang_hue') or {'level_required': 25, 'slot': 'helmet'}
    cost = CraftingService.get_material_cost(rep) or {"items": {}, "silver": 0}
    mats = []
    for item_id, need in cost.get("items", {}).items():
        inv = DataService.get_inventory_item(player.id, item_id)
        mats.append({
            'name': (DataService.get_item(item_id) or {}).get('name', item_id),
            'need': need,
            'have': inv.quantity if inv else 0,
        })
    silver_need = cost.get("silver", 0)
    return render_template("activity_barbarian_forge.html", player=player, owned=owned,
                           mats=mats, silver_need=silver_need, silver_have=player.gold, msg=msg)


