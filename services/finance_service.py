import time
import random
from datetime import date, datetime
from services.data_service import DataService


# ---- 交易时段 ----
MARKET_OPEN_HOUR = 9          # 9:00 开始实时变动（盘前可挂委托单）
MARKET_TRADE_HOUR = 9         # 9:00 起可成交（盘前委托单按9点价撮合）
MARKET_OPEN_MIN = 30          # 9:30 开盘（之前不显示股价，可挂单）
MARKET_CLOSE_HOUR = 18        # 18:00 休市
# 时段判定：
#   00:00~09:00  盘前（不显示股价，可挂委托单）
#   09:00~09:30  集合竞价（不显示股价，9点前委托单按开盘价=昨收撮合）
#   09:30~18:00  连续交易（显示实时股价，可即时买卖+委托单按实时价逐tick撮合）
#   18:00~24:00  盘后（休市，可挂委托单，不可即时交易）

# ---- Tunable constants ----
TICK_INTERVAL = 300          # 实时股价刷新间隔（秒），5分钟
DAILY_MAX_CHANGE = 0.10      # 每日累计涨跌幅上限 ±10%
TICK_DRIFT = 0.01            # 单次实时tick波动上限 ±1%
FEE_RATE = 0.0005            # 万五手续费
ORDER_BUY_TOLERANCE = 0.95   # 委托买单成交容忍度：委托价≥当前价*95%即成交
POP_THRESHOLD = 20           # 人气满档所需当日NPC访问次数
BANDIT_THRESHOLD = 10        # 劫匪满档所需当日击杀次数
BANDIT_RESPAWN = 300         # 劫匪击杀后5分钟复活
BANDIT_POINTS_PER_JINZU = 100  # 击杀劫匪积分：每100点兑1金珠（等效每次0.01金珠）
HISTORY_LEN = 48             # 每只股票保留的历史价条数
# 排名制涨跌区间：人气/劫匪各自按全市场排名，最高者区间上偏，最低者下偏
RANK_BEST_LO = -0.005        # 排名最高股票：区间下界 -0.5%
RANK_BEST_HI = 0.01          # 排名最高股票：区间上界 +1%
RANK_WORST_LO = -0.01        # 排名最低股票：区间下界 -1%
RANK_WORST_HI = 0.005        # 排名最低股票：区间上界 +0.5%


# ===================================================================
#  50 种 K 线走势策略
#  每种策略接收 (final_change, rng) 返回一条「关键拐点路径」:
#  [(t_ratio, price_ratio), ...]，t_ratio∈[0,1] 为当日时间比例，
#  price_ratio 为相对开盘价的累计涨跌比例。首点 (0,0)，末点 (1,final_change)。
#  tick 时按当前时间在路径上分段线性插值得到目标价。
# ===================================================================
def _path_points(final_change, rng):
    """统一入口：随机选 50 种策略之一生成当日路径。"""
    strategy = rng.choice(_STRATEGIES)
    return strategy(final_change, rng)


def _linear(final, rng):
    # 1 单边慢涨/慢跌（直线）
    return [(0.0, 0.0), (1.0, final)]


def _fast_then_flat_up(final, rng):
    # 2 开盘快速冲高后横盘
    peak = final * rng.uniform(1.1, 1.4) if final > 0 else final * rng.uniform(0.6, 0.9)
    return [(0.0, 0.0), (0.2, peak), (1.0, final)]


def _flat_then_fast(final, rng):
    # 3 横盘后尾盘拉升/下挫
    return [(0.0, 0.0), (0.7, final * rng.uniform(0.1, 0.3)), (1.0, final)]


def _v_shape(final, rng):
    # 4 先跌后涨（V型）
    low = -abs(final) * rng.uniform(0.8, 1.5) - rng.uniform(0, 0.02)
    if final >= 0:
        low = min(low, -0.005)
    return [(0.0, 0.0), (0.4, low), (1.0, final)]


def _inv_v_shape(final, rng):
    # 5 先涨后跌（倒V型）
    high = abs(final) * rng.uniform(0.8, 1.5) + rng.uniform(0, 0.02) if final > 0 else rng.uniform(0.005, 0.02)
    if final <= 0:
        high = max(high, 0.005)
    return [(0.0, 0.0), (0.4, high), (1.0, final)]


def _double_dip(final, rng):
    # 6 双底（W型）：跌-涨-跌-涨
    d1 = -abs(final) * rng.uniform(0.5, 0.9) - 0.005
    d2 = -abs(final) * rng.uniform(0.7, 1.1) - 0.005
    mid = final * rng.uniform(0.2, 0.4)
    return [(0.0, 0.0), (0.25, d1), (0.5, mid), (0.75, d2), (1.0, final)]


def _double_top(final, rng):
    # 7 双顶（M型）：涨-跌-涨-跌
    t1 = abs(final) * rng.uniform(0.5, 0.9) + 0.005 if final > 0 else 0.005
    t2 = abs(final) * rng.uniform(0.7, 1.1) + 0.005 if final > 0 else 0.008
    mid = final * rng.uniform(0.2, 0.4)
    return [(0.0, 0.0), (0.25, t1), (0.5, mid), (0.75, t2), (1.0, final)]


def _step_up(final, rng):
    # 8 阶梯上涨
    if final <= 0:
        return _step_down(final, rng)
    n = rng.randint(3, 5)
    pts = [(0.0, 0.0)]
    for i in range(1, n):
        pts.append((i / n, final * (i / n) * rng.uniform(0.9, 1.1)))
    pts.append((1.0, final))
    return pts


def _step_down(final, rng):
    # 9 阶梯下跌
    if final >= 0:
        final = -abs(rng.uniform(-0.03, -0.01))
    n = rng.randint(3, 5)
    pts = [(0.0, 0.0)]
    for i in range(1, n):
        pts.append((i / n, final * (i / n) * rng.uniform(0.9, 1.1)))
    pts.append((1.0, final))
    return pts


def _spike_up(final, rng):
    # 10 开盘拉满后回落
    high = max(abs(final), 0.03) * rng.uniform(1.2, 1.8)
    return [(0.0, 0.0), (0.05, high), (0.3, high * 0.6), (1.0, final)]


def _spike_down(final, rng):
    # 11 开盘砸盘后回升
    low = -max(abs(final), 0.03) * rng.uniform(1.2, 1.8)
    return [(0.0, 0.0), (0.05, low), (0.3, low * 0.6), (1.0, final)]


def _floor_pullback(final, rng):
    # 12 开盘地板后慢慢拉回
    low = -rng.uniform(0.04, 0.08)
    return [(0.0, 0.0), (0.15, low), (0.5, low * 0.5), (1.0, final)]


def _ceiling_drop(final, rng):
    # 13 开盘拉满后慢慢回落
    high = rng.uniform(0.04, 0.08)
    return [(0.0, 0.0), (0.15, high), (0.5, high * 0.5), (1.0, final)]


def _sawtooth_up(final, rng):
    # 14 锯齿震荡上行
    pts = [(0.0, 0.0)]
    n = rng.randint(4, 6)
    for i in range(1, n):
        base = final * (i / n)
        pts.append((i / n, base + rng.uniform(-0.015, 0.015)))
    pts.append((1.0, final))
    return pts


def _sawtooth_down(final, rng):
    # 15 锯齿震荡下行
    if final >= 0:
        final = -abs(rng.uniform(-0.03, -0.01))
    pts = [(0.0, 0.0)]
    n = rng.randint(4, 6)
    for i in range(1, n):
        base = final * (i / n)
        pts.append((i / n, base + rng.uniform(-0.015, 0.015)))
    pts.append((1.0, final))
    return pts


def _three_waves(final, rng):
    # 16 三浪上涨
    pts = [(0.0, 0.0)]
    for i in range(1, 4):
        pts.append((i / 3, final * (i / 3) + rng.uniform(-0.01, 0.01)))
    pts.append((1.0, final))
    return pts


def _rounding_bottom(final, rng):
    # 17 圆弧底
    pts = [(0.0, 0.0)]
    n = 6
    for i in range(1, n):
        t = i / n
        # 下凹圆弧：中段最低
        y = -0.04 * (1 - (2 * t - 1) ** 2) + final * t
        pts.append((t, y))
    pts.append((1.0, final))
    return pts


def _rounding_top(final, rng):
    # 18 圆弧顶
    pts = [(0.0, 0.0)]
    n = 6
    for i in range(1, n):
        t = i / n
        y = 0.04 * (1 - (2 * t - 1) ** 2) + final * t
        pts.append((t, y))
    pts.append((1.0, final))
    return pts


def _dead_cat(final, rng):
    # 19 死猫跳：暴跌后小幅反弹再跌
    low = -rng.uniform(0.05, 0.09)
    bounce = low * rng.uniform(-0.4, -0.2)
    return [(0.0, 0.0), (0.3, low), (0.5, bounce), (1.0, final)]


def _morning_star(final, rng):
    # 20 晨星：深跌后强势拉回收阳
    low = -rng.uniform(0.05, 0.08)
    return [(0.0, 0.0), (0.2, low), (0.5, low * 0.3), (1.0, final)]


def _evening_star(final, rng):
    # 21 黄昏星：冲高后回落收阴
    high = rng.uniform(0.05, 0.08)
    return [(0.0, 0.0), (0.2, high), (0.5, high * 0.3), (1.0, final)]


def _slow_grind_up(final, rng):
    # 22 慢牛磨底上行
    pts = [(0.0, 0.0)]
    n = 5
    for i in range(1, n):
        pts.append((i / n, final * (i / n) ** 1.5))
    pts.append((1.0, final))
    return pts


def _slow_bleed(final, rng):
    # 23 阴跌（温水煮青蛙）
    if final >= 0:
        final = -abs(rng.uniform(-0.03, -0.01))
    pts = [(0.0, 0.0)]
    n = 5
    for i in range(1, n):
        pts.append((i / n, final * (i / n) ** 1.5))
    pts.append((1.0, final))
    return pts


def _gap_up_fill(final, rng):
    # 24 高开回落补缺口
    high = rng.uniform(0.03, 0.06)
    return [(0.0, 0.0), (0.1, high), (0.4, high * 0.2), (1.0, final)]


def _gap_down_fill(final, rng):
    # 25 低开反弹补缺口
    low = -rng.uniform(0.03, 0.06)
    return [(0.0, 0.0), (0.1, low), (0.4, low * 0.2), (1.0, final)]


def _whipsaw(final, rng):
    # 26 剧烈震荡（多空拉锯）
    pts = [(0.0, 0.0)]
    n = rng.randint(5, 7)
    for i in range(1, n):
        pts.append((i / n, rng.uniform(-0.03, 0.03)))
    pts.append((1.0, final))
    return pts


def _plateau_breakout(final, rng):
    # 27 长时间横盘后突破
    side = final * rng.uniform(0.05, 0.15)
    return [(0.0, 0.0), (0.6, side), (0.7, side), (1.0, final)]


def _head_and_shoulders(final, rng):
    # 28 头肩顶
    ls = rng.uniform(0.02, 0.03)
    head = rng.uniform(0.04, 0.06)
    rs = rng.uniform(0.02, 0.03)
    return [(0.0, 0.0), (0.25, ls), (0.5, head), (0.75, rs), (1.0, final)]


def _inv_head_and_shoulders(final, rng):
    # 29 头肩底
    ls = -rng.uniform(0.02, 0.03)
    head = -rng.uniform(0.04, 0.06)
    rs = -rng.uniform(0.02, 0.03)
    return [(0.0, 0.0), (0.25, ls), (0.5, head), (0.75, rs), (1.0, final)]


def _rally_fade(final, rng):
    # 30 早盘拉升后全天阴跌
    high = rng.uniform(0.03, 0.05)
    return [(0.0, 0.0), (0.15, high), (1.0, final)]


def _dump_recover(final, rng):
    # 31 早盘跳水后全天回升
    low = -rng.uniform(0.03, 0.05)
    return [(0.0, 0.0), (0.15, low), (1.0, final)]


def _zigzag_up(final, rng):
    # 32 之字上行
    pts = [(0.0, 0.0)]
    n = 4
    for i in range(1, n):
        base = final * (i / n)
        pts.append((i / n, base - 0.01 if i % 2 else base + 0.01))
    pts.append((1.0, final))
    return pts


def _zigzag_down(final, rng):
    # 33 之字下行
    if final >= 0:
        final = -abs(rng.uniform(-0.03, -0.01))
    pts = [(0.0, 0.0)]
    n = 4
    for i in range(1, n):
        base = final * (i / n)
        pts.append((i / n, base + 0.01 if i % 2 else base - 0.01))
    pts.append((1.0, final))
    return pts


def _lunch_dump(final, rng):
    # 34 午盘跳水
    return [(0.0, 0.0), (0.4, final * 0.3), (0.5, -0.03), (1.0, final)]


def _lunch_rally(final, rng):
    # 35 午盘拉升
    return [(0.0, 0.0), (0.4, final * 0.3), (0.5, 0.03), (1.0, final)]


def _late_surge(final, rng):
    # 36 尾盘急拉
    return [(0.0, 0.0), (0.75, final * rng.uniform(0.1, 0.3)), (0.9, final * 0.6), (1.0, final)]


def _late_dump(final, rng):
    # 37 尾盘跳水
    return [(0.0, 0.0), (0.75, final * rng.uniform(0.3, 0.5)), (0.9, final * 0.7), (1.0, final)]


def _flat_mostly(final, rng):
    # 38 全天窄幅横盘
    pts = [(0.0, 0.0)]
    for t in (0.25, 0.5, 0.75):
        pts.append((t, rng.uniform(-0.005, 0.005)))
    pts.append((1.0, final))
    return pts


def _cup_handle(final, rng):
    # 39 杯柄形态
    low = -rng.uniform(0.03, 0.05)
    return [(0.0, 0.0), (0.3, low), (0.6, 0.01), (0.75, -0.005), (1.0, final)]


def _ascending_triangle(final, rng):
    # 40 上升三角形
    pts = [(0.0, 0.0)]
    for i in range(1, 4):
        pts.append((i / 4, rng.uniform(0.01, 0.025)))
    pts.append((1.0, final))
    return pts


def _descending_triangle(final, rng):
    # 41 下降三角形
    pts = [(0.0, 0.0)]
    for i in range(1, 4):
        pts.append((i / 4, rng.uniform(-0.025, -0.01)))
    pts.append((1.0, final))
    return pts


def _pin_bar(final, rng):
    # 42 长下影线（探底回升）
    low = -rng.uniform(0.04, 0.07)
    return [(0.0, 0.0), (0.1, low), (0.2, final * 0.2), (1.0, final)]


def _shooting_star(final, rng):
    # 43 长上影线（冲高回落）
    high = rng.uniform(0.04, 0.07)
    return [(0.0, 0.0), (0.1, high), (0.2, final * 0.2), (1.0, final)]


def _triple_top(final, rng):
    # 44 三重顶
    t = rng.uniform(0.03, 0.05)
    return [(0.0, 0.0), (0.2, t), (0.35, t * 0.3), (0.5, t), (0.65, t * 0.3), (0.8, t), (1.0, final)]


def _triple_bottom(final, rng):
    # 45 三重底
    b = -rng.uniform(0.03, 0.05)
    return [(0.0, 0.0), (0.2, b), (0.35, b * 0.3), (0.5, b), (0.65, b * 0.3), (0.8, b), (1.0, final)]


def _gentle_wave(final, rng):
    # 46 温和波浪
    pts = [(0.0, 0.0)]
    n = 5
    for i in range(1, n):
        t = i / n
        pts.append((t, final * t + 0.008 * (1 if i % 2 else -1)))
    pts.append((1.0, final))
    return pts


def _volcano(final, rng):
    # 47 火山喷发：横盘后暴涨再回落
    high = rng.uniform(0.05, 0.09)
    return [(0.0, 0.0), (0.5, 0.005), (0.65, high), (1.0, final)]


def _avalanche(final, rng):
    # 48 雪崩：横盘后暴跌再企稳
    low = -rng.uniform(0.05, 0.09)
    return [(0.0, 0.0), (0.5, -0.005), (0.65, low), (1.0, final)]


def _staircase_mixed(final, rng):
    # 49 混合阶梯（涨跌交替台阶）
    pts = [(0.0, 0.0)]
    n = rng.randint(4, 6)
    acc = 0.0
    for i in range(1, n):
        acc += final / n + rng.choice([-1, 1]) * rng.uniform(0.005, 0.012)
        pts.append((i / n, acc))
    pts.append((1.0, final))
    return pts


def _random_walk_constrained(final, rng):
    # 50 约束随机游走：多段随机，末段拉回 final
    pts = [(0.0, 0.0)]
    n = rng.randint(5, 8)
    for i in range(1, n):
        t = i / n
        # 越接近末尾越向 final 收敛
        target = final * t
        pts.append((t, target + rng.uniform(-0.012, 0.012) * (1 - t)))
    pts.append((1.0, final))
    return pts


_STRATEGIES = [
    _linear, _fast_then_flat_up, _flat_then_fast, _v_shape, _inv_v_shape,
    _double_dip, _double_top, _step_up, _step_down, _spike_up,
    _spike_down, _floor_pullback, _ceiling_drop, _sawtooth_up, _sawtooth_down,
    _three_waves, _rounding_bottom, _rounding_top, _dead_cat, _morning_star,
    _evening_star, _slow_grind_up, _slow_bleed, _gap_up_fill, _gap_down_fill,
    _whipsaw, _plateau_breakout, _head_and_shoulders, _inv_head_and_shoulders, _rally_fade,
    _dump_recover, _zigzag_up, _zigzag_down, _lunch_dump, _lunch_rally,
    _late_surge, _late_dump, _flat_mostly, _cup_handle, _ascending_triangle,
    _descending_triangle, _pin_bar, _shooting_star, _triple_top, _triple_bottom,
    _gentle_wave, _volcano, _avalanche, _staircase_mixed, _random_walk_constrained,
]
assert len(_STRATEGIES) == 50


def _interp_path(path, t_ratio):
    """在路径上按 t_ratio∈[0,1] 分段线性插值，返回 price_ratio。"""
    if t_ratio <= path[0][0]:
        return path[0][1]
    if t_ratio >= path[-1][0]:
        return path[-1][1]
    for i in range(len(path) - 1):
        t0, y0 = path[i]
        t1, y1 = path[i + 1]
        if t0 <= t_ratio <= t1:
            if t1 == t0:
                return y1
            return y0 + (y1 - y0) * (t_ratio - t0) / (t1 - t0)
    return path[-1][1]


class BanditState:
    __slots__ = ('city', 'spawned', 'defeated_at', 'killer_today', 'location_id')

    def __init__(self, city):
        self.city = city
        self.spawned = True          # 未击杀则持续存在
        self.defeated_at = 0
        self.killer_today = None
        self.location_id = ''        # 当前出没的具体场景 location_id（随机）


class FinanceService:
    """理财·股市服务。股价、劫匪状态、委托单均为类级内存（惰性时间戳刷新，仿 WorldBossService）。"""

    _stocks = {}          # {stock_id: {...}}
    _bandits = {}         # {city: BanditState}
    _daily_stats = {}     # {stock_id: {"npc_visits": int, "bandit_kills": int, "npc_visitors": set}}
    _orders = {}          # 委托单 {order_id: {...}}，类级内存
    _day_key = None
    _last_tick = 0.0
    _initialized = False

    # ===================================================================
    #  初始化
    # ===================================================================
    @classmethod
    def _ensure_init(cls):
        if cls._initialized:
            cls._ensure_day()
            cls._maybe_tick()
            return
        stocks_def = DataService.get_finance_stocks()
        for sd in stocks_def:
            base = float(sd.get('base_price', 100.0))
            cls._stocks[sd['stock_id']] = {
                'stock_id': sd['stock_id'],
                'name': sd.get('name', sd['stock_id']),
                'city': sd.get('city', ''),
                'npc_keyword': sd.get('npc_keyword', ''),
                'area_id': sd.get('area_id', ''),
                'base_price': base,
                'open_price': base,     # 当日开盘价（=昨收）
                'price': base,          # 当前实时价
                'last_price': base,     # 上次tick价（用于显示涨跌）
                'pre_open_price': base, # 9:00 参考价（盘前委托单撮合用）
                'day_change': 0.0,      # 当日累计涨跌幅（最终目标）
                'pop_part': 0.0,        # B 人气部分
                'bandit_part': 0.0,     # C 劫匪部分
                'strategy_idx': 0,      # 当日所用策略序号
                'path': [(0.0, 0.0), (1.0, 0.0)],  # 当日走势路径
                'total_shares': int(sd.get('total_shares', 5000)),
                'outstanding': 0,       # 流通在外（玩家持有总量）
                'history': [base],
            }
            cls._daily_stats[sd['stock_id']] = {
                'npc_visits': 0, 'bandit_kills': 0, 'npc_visitors': set()}
            city = sd.get('city', '')
            if city and city not in cls._bandits:
                b = BanditState(city)
                cls._randomize_bandit_location(b)
                cls._bandits[city] = b
        cls._orders = {}
        cls._day_key = str(date.today())
        cls._last_tick = time.time()
        cls._rebuild_outstanding()
        cls._settle_day_change()   # 开盘随机A+排名B/C+选路径
        cls._initialized = True

    @classmethod
    def _rebuild_outstanding(cls):
        """启动时从所有玩家持仓聚合流通股数（内存重启后恢复）。"""
        try:
            from models.player import PlayerModel
            totals = {}
            for p in PlayerModel.query.all():
                fd = p.finance_data or {}
                for sid, h in (fd.get('holdings') or {}).items():
                    totals[sid] = totals.get(sid, 0) + int(h.get('shares', 0))
            for sid, cnt in totals.items():
                if sid in cls._stocks:
                    cls._stocks[sid]['outstanding'] = cnt
        except Exception:
            pass

    # ===================================================================
    #  交易时段
    # ===================================================================
    @classmethod
    def _now(cls):
        return datetime.now()

    @classmethod
    def get_market_phase(cls):
        """返回当前时段: 'pre_open'(盘前,9点前) / 'auction'(集合竞价9-9:30) /
        'open'(连续交易9:30-18:00) / 'closed'(盘后18点后)。"""
        now = cls._now()
        t = now.hour * 60 + now.minute
        open_trade = MARKET_OPEN_HOUR * 60           # 9:00
        open_min = MARKET_OPEN_HOUR * 60 + MARKET_OPEN_MIN  # 9:30
        close = MARKET_CLOSE_HOUR * 60               # 18:00
        if t < open_trade:
            return 'pre_open'
        if t < open_min:
            return 'auction'
        if t < close:
            return 'open'
        return 'closed'

    @classmethod
    def is_tradable(cls):
        """连续交易时段可即时买卖（9:30-18:00）。"""
        return cls.get_market_phase() == 'open'

    @classmethod
    def can_place_order(cls):
        """任何时段都可提交委托单（盘前/盘后/盘中均可挂单）。"""
        return True

    @classmethod
    def shows_price(cls):
        """9:30 开盘后才显示实时股价；盘前(9点前)与集合竞价(9-9:30)均不显示。"""
        return cls.get_market_phase() == 'open'

    @classmethod
    def _match_price(cls, s):
        """撮合委托单所用的「当前价」：
        集合竞价段(9-9:30)用开盘价(=昨收)；连续交易段(9:30后)用实时价。"""
        phase = cls.get_market_phase()
        if phase == 'auction':
            return s['open_price']
        return s['price']

    # ===================================================================
    #  跨天与实时tick
    # ===================================================================
    @classmethod
    def _ensure_day(cls):
        today = str(date.today())
        if today == cls._day_key:
            return
        # 跨天：昨收为今开，重置统计，重算A/B/C与路径
        for sid, s in cls._stocks.items():
            s['open_price'] = s['price']
            s['last_price'] = s['price']
            s['pre_open_price'] = s['price']
            s['history'] = [s['price']]
        for sid in cls._daily_stats:
            cls._daily_stats[sid] = {
                'npc_visits': 0, 'bandit_kills': 0, 'npc_visitors': set()}
        # 委托单跨天清空（未成交的隔日作废）
        cls._orders = {}
        # 劫匪跨天重新生成（随机刷新到新场景）
        for city, b in cls._bandits.items():
            b.spawned = True
            b.defeated_at = 0
            b.killer_today = None
            cls._randomize_bandit_location(b)
        cls._day_key = today
        cls._settle_day_change()

    @classmethod
    def _randomize_bandit_location(cls, b):
        """把劫匪随机刷新到该城市区域内的某个场景。"""
        area_id = ''
        for sid, s in cls._stocks.items():
            if s['city'] == b.city:
                area_id = s['area_id']
                break
        if not area_id:
            b.location_id = ''
            return
        locations = DataService.get_locations()
        candidates = [lid for lid, loc in locations.items()
                      if loc.get('area_id') == area_id
                      and not loc.get('is_copy_map')]
        if candidates:
            b.location_id = random.choice(candidates)
        else:
            b.location_id = ''

    @classmethod
    def _settle_day_change(cls):
        """结算当日各股票涨跌：A纯随机 + B人气(排名制) + C劫匪(排名制)，
        并为每只股票随机选定一种 K 线走势策略生成当日路径。"""
        rng = random.Random()
        # A 纯随机 ±8%（开盘一次性，自己也不知道涨跌多少）
        a_map = {}
        for sid in cls._stocks:
            a_map[sid] = random.uniform(-0.08, 0.08)

        # B 人气排名：按当日 npc_visits 排名分配涨跌区间
        pop_rank = cls._ranked_change(random, 'npc_visits',
                                      RANK_BEST_LO, RANK_BEST_HI,
                                      RANK_WORST_LO, RANK_WORST_HI)
        # C 劫匪排名：按当日 bandit_kills 排名分配涨跌区间
        bandit_rank = cls._ranked_change(random, 'bandit_kills',
                                         RANK_BEST_LO, RANK_BEST_HI,
                                         RANK_WORST_LO, RANK_WORST_HI)

        for sid, s in cls._stocks.items():
            stats = cls._daily_stats.get(sid, {})
            a = a_map[sid]
            b = pop_rank.get(sid, 0.0)
            c = bandit_rank.get(sid, 0.0)
            s['pop_part'] = round(b, 4)
            s['bandit_part'] = round(c, 4)
            change = max(-DAILY_MAX_CHANGE, min(DAILY_MAX_CHANGE, a + b + c))
            s['day_change'] = round(change, 4)
            # 选定 K 线策略并生成路径
            idx = rng.randint(0, len(_STRATEGIES) - 1)
            s['strategy_idx'] = idx
            s['path'] = _STRATEGIES[idx](change, rng)

    @classmethod
    def _ranked_change(cls, rng, stat_key, best_lo, best_hi, worst_lo, worst_hi):
        """按全市场 stat_key(人气或劫匪) 排名，分配当日涨跌区间并随机取值。
        排名最高者∈[best_lo,best_hi]，最低者∈[worst_lo,worst_hi]，中间线性插值。"""
        items = []
        for sid, stats in cls._daily_stats.items():
            val = stats.get(stat_key, 0)
            items.append((sid, val))
        if not items:
            return {}
        items.sort(key=lambda x: x[1], reverse=True)  # 高→低
        n = len(items)
        result = {}
        for rank, (sid, val) in enumerate(items):
            if n == 1:
                frac = 0.5
            else:
                frac = rank / (n - 1)  # 0=最高, 1=最低
            lo = best_lo + (worst_lo - best_lo) * frac
            hi = best_hi + (worst_hi - best_hi) * frac
            result[sid] = rng.uniform(lo, hi)
        return result

    @classmethod
    def _day_progress(cls):
        """当日时间进度 [0,1]：9:00→0，18:00→1。盘前返回0，盘后返回1。"""
        now = cls._now()
        t = now.hour * 60 + now.minute
        start = MARKET_OPEN_HOUR * 60       # 540
        end = MARKET_CLOSE_HOUR * 60        # 1080
        if t <= start:
            return 0.0
        if t >= end:
            return 1.0
        return (t - start) / (end - start)

    @classmethod
    def _maybe_tick(cls):
        """惰性实时tick：距上次>=5分钟则按当日路径插值推进，相邻差≤1%。
        集合竞价段(9-9:30)不刷新股价（用开盘价=昨收撮合委托单），9:30后才实时变动。"""
        now = time.time()
        if now - cls._last_tick < TICK_INTERVAL:
            return
        cls._last_tick = now
        phase = cls.get_market_phase()
        # 盘前(9点前)与集合竞价(9-9:30)都不刷新股价
        if phase in ('pre_open', 'auction'):
            # 集合竞价段：用开盘价撮合9点前/盘中的委托单
            if phase == 'auction':
                cls._match_orders()
            return
        progress = cls._day_progress()
        for sid, s in cls._stocks.items():
            # 路径目标价
            target_ratio = _interp_path(s['path'], progress)
            target = s['open_price'] * (1 + target_ratio)
            # 微小随机抖动
            drift = random.uniform(-TICK_DRIFT * 0.5, TICK_DRIFT * 0.5)
            new_price = target * (1 + drift)
            # 与上次差不超过1%
            lo = s['price'] * (1 - TICK_DRIFT)
            hi = s['price'] * (1 + TICK_DRIFT)
            new_price = max(lo, min(hi, new_price))
            new_price = round(max(0.01, new_price), 2)
            s['last_price'] = s['price']
            s['price'] = new_price
            s['history'].append(new_price)
            if len(s['history']) > HISTORY_LEN:
                s['history'] = s['history'][-HISTORY_LEN:]
        # 连续交易时段逐tick撮合委托单（按实时价）
        if phase == 'open':
            cls._match_orders()

    # ===================================================================
    #  公开查询
    # ===================================================================
    @classmethod
    def get_market(cls):
        """返回行情列表（触发刷新）。"""
        cls._ensure_init()
        return [cls._public_view(s) for s in cls._stocks.values()]

    @classmethod
    def get_stock(cls, stock_id):
        cls._ensure_init()
        s = cls._stocks.get(stock_id)
        return cls._public_view(s) if s else None

    @classmethod
    def get_next_refresh_in(cls):
        """距下次实时刷新的秒数（前端倒计时用）。"""
        cls._ensure_init()
        return max(0, int(TICK_INTERVAL - (time.time() - cls._last_tick)))

    @classmethod
    def _public_view(cls, s):
        change_pct = ((s['price'] - s['open_price']) / s['open_price'] * 100) if s['open_price'] else 0
        tick_pct = ((s['price'] - s['last_price']) / s['last_price'] * 100) if s['last_price'] else 0
        stats = cls._daily_stats.get(s['stock_id'], {})
        return {
            'stock_id': s['stock_id'],
            'name': s['name'],
            'city': s['city'],
            'price': s['price'],
            'open_price': s['open_price'],
            'last_price': s['last_price'],
            'day_change': s['day_change'],
            'change_pct': round(change_pct, 2),
            'tick_pct': round(tick_pct, 2),
            'total_shares': s['total_shares'],
            'outstanding': s['outstanding'],
            'available': max(0, s['total_shares'] - s['outstanding']),
            'npc_visits': stats.get('npc_visits', 0),
            'bandit_kills': stats.get('bandit_kills', 0),
            'pop_factor': round(min(1.0, stats.get('npc_visits', 0) / POP_THRESHOLD), 2) if POP_THRESHOLD else 0,
            'bandit_factor': round(min(1.0, stats.get('bandit_kills', 0) / BANDIT_THRESHOLD), 2) if BANDIT_THRESHOLD else 0,
            'strategy_idx': s['strategy_idx'],
            'history': list(s['history']),
        }

    @classmethod
    def get_player_holdings(cls, player):
        cls._ensure_init()
        fd = player.finance_data or {}
        holdings = fd.get('holdings') or {}
        rows = []
        for sid, h in holdings.items():
            s = cls._stocks.get(sid)
            if not s or h.get('shares', 0) <= 0:
                continue
            shares = int(h['shares'])
            avg = float(h.get('avg_cost', 0))
            cost = shares * avg
            value = shares * s['price']
            rows.append({
                'stock_id': sid,
                'name': s['name'],
                'city': s['city'],
                'shares': shares,
                'avg_cost': round(avg, 2),
                'price': s['price'],
                'cost': round(cost, 2),
                'value': round(value, 2),
                'profit': round(value - cost, 2),
                'profit_pct': round((value - cost) / cost * 100, 2) if cost else 0,
            })
        return rows

    @classmethod
    def get_player_summary(cls, player):
        cls._ensure_init()
        fd = player.finance_data or {}
        rows = cls.get_player_holdings(player)
        market_value = sum(r['value'] for r in rows)
        total_cost = sum(r['cost'] for r in rows)
        floating = market_value - total_cost
        return {
            'jinzu': player.jinzu,
            'market_value': round(market_value, 2),
            'total_cost': round(total_cost, 2),
            'floating_profit': round(floating, 2),
            'realized_profit': round(float(fd.get('realized_profit', 0)), 2),
            'total_traded': round(float(fd.get('total_traded', 0)), 2),
            'frozen': round(float(fd.get('frozen', 0)), 2),
            'holdings_count': len(rows),
            'bandit_points': int(fd.get('bandit_points', 0)),
            'bandit_points_per_jinzu': BANDIT_POINTS_PER_JINZU,
        }

    # ===================================================================
    #  交易（即时买卖，仅连续交易时段 9:30-18:00）
    # ===================================================================
    @classmethod
    def buy(cls, player, stock_id, shares):
        cls._ensure_init()
        if not cls.is_tradable():
            return False, "非交易时段（9:30-18:00），可改用委托单挂单"
        s = cls._stocks.get(stock_id)
        if not s:
            return False, "无此股票"
        try:
            shares = int(shares)
        except (TypeError, ValueError):
            return False, "数量无效"
        if shares <= 0:
            return False, "数量必须大于0"
        available = s['total_shares'] - s['outstanding']
        if shares > available:
            return False, f"发行量不足，仅剩{available}股可买"

        cost = shares * s['price']
        fee = cost * FEE_RATE
        total = cost + fee
        if player.jinzu < total:
            return False, f"金珠不足，需{round(total,2)}金珠（含手续费{round(fee,2)}）"

        player.jinzu -= int(round(total))
        fd = player.finance_data
        cur = holdings.get(stock_id) or {'shares': 0, 'avg_cost': 0.0}
        old_shares = cur['shares']
        old_avg = cur['avg_cost']
        new_shares = old_shares + shares
        new_avg = (old_shares * old_avg + cost) / new_shares if new_shares else 0
        holdings[stock_id] = {'shares': new_shares, 'avg_cost': round(new_avg, 4)}
        fd['holdings'] = holdings
        fd['total_traded'] = round(float(fd.get('total_traded', 0)) + total, 2)
        player.finance_data = fd
        s['outstanding'] += shares

        from services import db
        db.session.commit()
        return True, (f"买入{s['name']}{shares}股，单价{s['price']}金珠，"
                      f"手续费{round(fee,2)}，共耗{round(total,2)}金珠")

    @classmethod
    def sell(cls, player, stock_id, shares):
        cls._ensure_init()
        if not cls.is_tradable():
            return False, "非交易时段（9:30-18:00），可改用委托单挂单"
        s = cls._stocks.get(stock_id)
        if not s:
            return False, "无此股票"
        try:
            shares = int(shares)
        except (TypeError, ValueError):
            return False, "数量无效"
        if shares <= 0:
            return False, "数量必须大于0"
        fd = player.finance_data
        holdings = fd.get('holdings') or {}
        cur = holdings.get(stock_id)
        if not cur or cur.get('shares', 0) < shares:
            hold = cur['shares'] if cur else 0
            return False, f"持仓不足，仅持有{hold}股"

        income = shares * s['price']
        fee = income * FEE_RATE
        net = income - fee
        player.jinzu += int(round(net))

        old_shares = cur['shares']
        old_avg = cur['avg_cost']
        realized = (shares * s['price']) - (shares * old_avg) - fee
        fd['realized_profit'] = round(float(fd.get('realized_profit', 0)) + realized, 2)
        fd['total_traded'] = round(float(fd.get('total_traded', 0)) + net + fee, 2)
        new_shares = old_shares - shares
        if new_shares > 0:
            holdings[stock_id] = {'shares': new_shares, 'avg_cost': old_avg}
        else:
            holdings.pop(stock_id, None)
        fd['holdings'] = holdings
        player.finance_data = fd
        s['outstanding'] -= shares

        from services import db
        db.session.commit()
        return True, (f"卖出{s['name']}{shares}股，单价{s['price']}金珠，"
                      f"手续费{round(fee,2)}，到账{round(net,2)}金珠，本次盈亏{round(realized,2)}")

    @classmethod
    def get_player_profit(cls, player):
        """股神榜用：已实现盈亏 + 浮动盈亏。"""
        cls._ensure_init()
        fd = player.finance_data or {}
        realized = float(fd.get('realized_profit', 0))
        floating = 0.0
        for sid, h in (fd.get('holdings') or {}).items():
            s = cls._stocks.get(sid)
            if s:
                floating += int(h.get('shares', 0)) * (s['price'] - float(h.get('avg_cost', 0)))
        return round(realized + floating, 2)

    # ===================================================================
    #  委托单系统（限价单，统一按委托价成交）
    # ===================================================================
    @classmethod
    def place_order(cls, player, stock_id, side, shares, limit_price):
        """提交委托单。side: 'buy'/'sell'。任何时段可挂单。
        限价单语义：买单委托价≥市价则成交，卖单委托价≤市价则成交；统一按委托价成交。"""
        cls._ensure_init()
        s = cls._stocks.get(stock_id)
        if not s:
            return False, "无此股票"
        try:
            shares = int(shares)
            limit_price = float(limit_price)
        except (TypeError, ValueError):
            return False, "数量或价格无效"
        if shares <= 0:
            return False, "数量必须大于0"
        if limit_price <= 0:
            return False, "委托价格必须大于0"
        if side not in ('buy', 'sell'):
            return False, "方向无效"

        fd = player.finance_data
        # 买单：预冻结金珠（按委托价+手续费）
        if side == 'buy':
            cost = shares * limit_price
            fee = cost * FEE_RATE
            total = cost + fee
            if player.jinzu < total:
                return False, f"金珠不足，需{round(total,2)}金珠冻结"
            player.jinzu -= int(round(total))
            fd['frozen'] = round(float(fd.get('frozen', 0)) + total, 2)
            holdings = fd.get('holdings') or {}
            cur = holdings.get(stock_id)
            if not cur or cur.get('shares', 0) < shares:
                hold = cur['shares'] if cur else 0
                return False, f"持仓不足，仅持有{hold}股"
            cur['shares'] -= shares
            cur['locked'] = cur.get('locked', 0) + shares
            if cur['shares'] <= 0 and cur.get('locked', 0) <= 0:
                holdings.pop(stock_id, None)
            fd['holdings'] = holdings

        order_id = f"o{int(time.time()*1000)}{random.randint(100,999)}"
        cls._orders[order_id] = {
            'order_id': order_id,
            'player_id': player.id,
            'stock_id': stock_id,
            'side': side,
            'shares': shares,
            'limit_price': round(limit_price, 2),
            'frozen_total': round(total, 2) if side == 'buy' else 0,
            'status': 'pending',   # pending / filled / rejected
            'created_at': time.time(),
        }
        player.finance_data = fd
        from services import db
        db.session.commit()
        return True, f"委托单已提交：{side=='buy' and '买入' or '卖出'}{s['name']}{shares}股@{round(limit_price,2)}金珠"

    @classmethod
    def _match_orders(cls):
        """逐tick撮合待成交委托单。
        成交判定（限价单，统一按委托价结算）：
          买单：委托价 >= 当前价*95% → 成交
          卖单：委托价 <= 当前价 → 成交
        流通量限制：买单本次成交股数 = min(委托股数, 可流通量)，超额部分继续挂单。"""
        pending = [o for o in cls._orders.values() if o['status'] == 'pending']
        if not pending:
            return
        for o in pending:
            s = cls._stocks.get(o['stock_id'])
            if not s:
                o['status'] = 'rejected'
                cls._refund_order(o)
                continue
            market = cls._match_price(s)
            fill = False
            if o['side'] == 'buy' and o['limit_price'] >= market * ORDER_BUY_TOLERANCE:
                fill = True
            elif o['side'] == 'sell' and o['limit_price'] <= market:
                fill = True
            if not fill:
                continue
            cls._fill_order(o, s)

    @classmethod
    def _fill_order(cls, o, s):
        """以委托价成交一单（支持部分成交+流通量限制）。
        买单：成交股数 = min(委托股数, 可流通量)，超额部分继续挂单。
        卖单：按委托股数成交（持仓已预冻结）。"""
        from models.player import PlayerModel
        p = PlayerModel.query.get(o['player_id'])
        if not p:
            o['status'] = 'rejected'
            return
        fd = p.finance_data
        price = o['limit_price']
        order_shares = o['shares']
        if o['side'] == 'buy':
            # 流通量限制：本次最多成交可流通量
            available = s['total_shares'] - s['outstanding']
            fill_shares = min(order_shares, available)
            if fill_shares <= 0:
                return  # 无可流通量，继续挂单等待
            actual_cost = fill_shares * price
            fee = actual_cost * FEE_RATE
            total = actual_cost + fee
            # 按本次成交比例解冻金珠（冻结是按委托股数算的）
            ratio = fill_shares / order_shares
            frozen_release = round(o['frozen_total'] * ratio, 2)
            fd['frozen'] = round(float(fd.get('frozen', 0)) - frozen_release, 2)
            # 入账持仓
            holdings = fd.get('holdings') or {}
            cur = holdings.get(o['stock_id']) or {'shares': 0, 'avg_cost': 0.0}
            old_shares = cur['shares']
            old_avg = cur.get('avg_cost', 0.0)
            new_shares = old_shares + fill_shares
            new_avg = (old_shares * old_avg + actual_cost) / new_shares if new_shares else 0
            holdings[o['stock_id']] = {'shares': new_shares, 'avg_cost': round(new_avg, 4)}
            fd['holdings'] = holdings
            fd['total_traded'] = round(float(fd.get('total_traded', 0)) + total, 2)
            s['outstanding'] += fill_shares
            if fill_shares < order_shares:
                # 部分成交：剩余股数继续挂单，减少冻结基数
                remaining = order_shares - fill_shares
                o['shares'] = remaining
                o['frozen_total'] = round(o['frozen_total'] - frozen_release, 2)
                msg = f"委托买入{s['name']}部分成交{fill_shares}股@{price}（剩{remaining}股挂单中，流通量不足）"
            else:
                o['status'] = 'filled'
                msg = f"委托买入{s['name']}{fill_shares}股@{price}成交，耗{round(total,2)}金珠"
        else:
            # 卖出：按委托股数成交（持仓已预冻结）
            holdings = fd.get('holdings') or {}
            cur = holdings.get(o['stock_id'])
            if not cur:
                o['status'] = 'rejected'
                return
            locked = cur.get('locked', 0)
            fill_shares = order_shares
            income = fill_shares * price
            fee = income * FEE_RATE
            net = income - fee
            p.jinzu += int(round(net))
            avg = cur.get('avg_cost', 0.0)
            realized = (fill_shares * price) - (fill_shares * avg) - fee
            fd['realized_profit'] = round(float(fd.get('realized_profit', 0)) + realized, 2)
            fd['total_traded'] = round(float(fd.get('total_traded', 0)) + net + fee, 2)
            cur['locked'] = locked - fill_shares
            if cur['shares'] <= 0 and cur.get('locked', 0) <= 0:
                holdings.pop(o['stock_id'], None)
            fd['holdings'] = holdings
            s['outstanding'] -= fill_shares
            o['status'] = 'filled'
            msg = f"委托卖出{s['name']}{fill_shares}股@{price}成交，到账{round(net,2)}金珠，盈亏{round(realized,2)}"
        p.finance_data = fd
        from services import db
        db.session.commit()
        return msg

    @classmethod
    def _refund_order(cls, o):
        """委托单作废时退回冻结资金/持仓。"""
        from models.player import PlayerModel
        p = PlayerModel.query.get(o['player_id'])
        if not p:
            return
        fd = p.finance_data
        if o['side'] == 'buy':
            fd['frozen'] = round(float(fd.get('frozen', 0)) - o['frozen_total'], 2)
            p.jinzu += int(round(o['frozen_total']))
        else:
            holdings = fd.get('holdings') or {}
            cur = holdings.get(o['stock_id'])
            if cur:
                cur['locked'] = cur.get('locked', 0) - o['shares']
                cur['shares'] = cur.get('shares', 0) + o['shares']
        p.finance_data = fd
        from services import db
        db.session.commit()

    @classmethod
    def get_player_orders(cls, player):
        """玩家委托单列表。"""
        cls._ensure_init()
        rows = []
        for o in cls._orders.values():
            if o['player_id'] != player.id:
                continue
            s = cls._stocks.get(o['stock_id'])
            rows.append({
                'order_id': o['order_id'],
                'stock_id': o['stock_id'],
                'name': s['name'] if s else o['stock_id'],
                'side': o['side'],
                'shares': o['shares'],
                'limit_price': o['limit_price'],
                'status': o['status'],
                'market_price': s['price'] if s else 0,
            })
        rows.sort(key=lambda x: x['order_id'], reverse=True)
        return rows

    @classmethod
    def cancel_order(cls, player, order_id):
        """撤销未成交委托单。"""
        cls._ensure_init()
        o = cls._orders.get(order_id)
        if not o or o['player_id'] != player.id:
            return False, "委托单不存在"
        if o['status'] != 'pending':
            return False, f"委托单已{o['status']=='filled' and '成交' or '作废'}，不可撤销"
        cls._refund_order(o)
        o['status'] = 'rejected'
        from services import db
        db.session.commit()
        return True, "委托单已撤销，冻结资金/持仓已退回"

    # ===================================================================
    #  增股接口（后续活动扩容）
    # ===================================================================
    @classmethod
    def increase_total_shares(cls, stock_id, amount):
        cls._ensure_init()
        s = cls._stocks.get(stock_id)
        if not s:
            return False, "无此股票"
        try:
            amount = int(amount)
        except (TypeError, ValueError):
            return False, "增股数量无效"
        if amount <= 0:
            return False, "增股数量必须大于0"
        s['total_shares'] += amount
        return True, f"{s['name']}增发{amount}股，新发行总量{s['total_shares']}股"

    # ===================================================================
    #  人气（NPC对话计数）
    # ===================================================================
    @classmethod
    def record_npc_visit(cls, monster_id, player_id):
        """玩家点击NPC时调用，按npc_keyword匹配股票累加当日人气。每人每日每股票计1次。"""
        cls._ensure_init()
        for sid, s in cls._stocks.items():
            kw = s['npc_keyword']
            if kw and kw in monster_id:
                stats = cls._daily_stats.setdefault(sid, {
                    'npc_visits': 0, 'bandit_kills': 0, 'npc_visitors': set()})
                if player_id in stats['npc_visitors']:
                    return
                stats['npc_visitors'].add(player_id)
                stats['npc_visits'] += 1
                return

    # ===================================================================
    #  劫匪系统
    # ===================================================================
    @classmethod
    def get_bandit_for_area(cls, area_id):
        cls._ensure_init()
        for sid, s in cls._stocks.items():
            if s['area_id'] == area_id:
                b = cls._bandits.get(s['city'])
                if b:
                    cls._check_bandit_respawn(b)
                    return b, s
        return None, None

    @classmethod
    def _check_bandit_respawn(cls, b):
        """劫匪击杀后5分钟重新生成（随机刷新到新场景）。"""
        if b.spawned:
            return
        if b.defeated_at and time.time() - b.defeated_at >= BANDIT_RESPAWN:
            b.spawned = True
            b.defeated_at = 0
            b.killer_today = None
            cls._randomize_bandit_location(b)

    @classmethod
    def _bandit_monster_id(cls, city):
        return f"bandit_{city}"

    @classmethod
    def get_bandit_monster_data(cls, city):
        cls._ensure_init()
        return {
            "name": f"{city}劫匪",
            "level": 15,
            "is_elite": False,
            "is_divine_beast": False,
            "killable": True,
            "immortal": False,
            "description": f"在{city}劫掠富商的匪徒，击杀可救济富商并提振{city}股市人气",
            "base_stats": {
                "health": 300,
                "max_health": 300,
                "mana": 100,
                "attack": 40,
                "defense": 15,
                "crit_rate": 0.05,
                "dodge_rate": 0.05,
            },
            "skills": [],
            "drops": {
                "money": {"min": 50, "max": 150},
                "experience": 80,
                "items": {},
                "equipment_drop": {},
            },
            "guaranteed_items": [],
        }

    @classmethod
    def register_bandit_monster(cls, monsters_cache):
        cls._ensure_init()
        for sid, s in cls._stocks.items():
            mid = cls._bandit_monster_id(s['city'])
            if mid not in monsters_cache:
                monsters_cache[mid] = cls.get_bandit_monster_data(s['city'])

    @classmethod
    def record_bandit_kill(cls, monster_id, player):
        """击杀劫匪时调用：该城市所有股票 bandit_kills+1 + 积分制奖励。
        返回 dict {points, jinzu, total_points, city} 供提示。"""
        cls._ensure_init()
        if not monster_id or not monster_id.startswith("bandit_"):
            return None
        city = monster_id[len("bandit_"):]
        b = cls._bandits.get(city)
        if not b:
            return None
        # 标记击杀，启动5分钟复活（复活时随机刷新到新场景）
        b.spawned = False
        b.defeated_at = time.time()
        b.killer_today = player.id
        # 该城市所有关联股票的当日击杀统计 +1（击杀北平劫匪→北平所有股票+1）
        affected = 0
        for sid, s in cls._stocks.items():
            if s['city'] == city:
                stats = cls._daily_stats.setdefault(sid, {
                    'npc_visits': 0, 'bandit_kills': 0, 'npc_visitors': set()})
                stats['bandit_kills'] += 1
                affected += 1
        # 积分制：每次+1点，满100点自动兑换1金珠
        fd = player.finance_data
        bandit_points = int(fd.get('bandit_points', 0)) + 1
        jinzu_gain = bandit_points // BANDIT_POINTS_PER_JINZU
        bandit_points = bandit_points % BANDIT_POINTS_PER_JINZU
        fd['bandit_points'] = bandit_points
        player.finance_data = fd
        if jinzu_gain > 0:
            player.jinzu += jinzu_gain
        from services import db
        db.session.commit()
        if jinzu_gain > 0:
            DataService.broadcast_system(
                f"{player.nickname}在{city}多次击杀劫匪，救济富商，获答谢金珠{jinzu_gain}枚！")
        return {'points': 1, 'jinzu': jinzu_gain, 'total_points': bandit_points, 'city': city}

    @classmethod
    def get_bandit_at_location(cls, location_id):
        """若该场景有劫匪出没且在场，返回 (monster_id, city, respawn_remaining)，否则 None。
        击杀后（复活中）不在场景显示，仅在金珠股市劫匪情报显示复活倒计时。"""
        cls._ensure_init()
        if not location_id:
            return None
        for city, b in cls._bandits.items():
            cls._check_bandit_respawn(b)
            if b.location_id == location_id and b.spawned:
                return (cls._bandit_monster_id(city), city, 0)
        return None

    @classmethod
    def get_bandit_status(cls):
        cls._ensure_init()
        from services.map_service import MapService
        result = []
        for city, b in cls._bandits.items():
            cls._check_bandit_respawn(b)
            respawn = 0
            if not b.spawned and b.defeated_at:
                respawn = max(0, int(BANDIT_RESPAWN - (time.time() - b.defeated_at)))
            area_id = ''
            kills = 0
            for sid, s in cls._stocks.items():
                if s['city'] == city:
                    area_id = s['area_id']
                    kills = cls._daily_stats.get(sid, {}).get('bandit_kills', 0)
                    break
            location_id = b.location_id
            loc_name = ''
            area_name = ''
            if location_id:
                loc = DataService.get_locations().get(location_id, {})
                loc_name = loc.get('name', location_id)
                area_name = loc.get('area_name', '')
            teleport_target = city if MapService.CITY_SQUARES.get(city) else ''
            result.append({
                'city': city,
                'spawned': b.spawned,
                'respawn_in': respawn,
                'kills_today': kills,
                'area_id': area_id,
                'location_id': location_id,
                'location_name': loc_name,
                'area_name': area_name,
                'teleport_target': teleport_target,
            })
        return result

    @classmethod
    def get_city_kill_rank(cls, limit=30):
        cls._ensure_init()
        rows = []
        for city, b in cls._bandits.items():
            kills = 0
            for sid, s in cls._stocks.items():
                if s['city'] == city:
                    kills = cls._daily_stats.get(sid, {}).get('bandit_kills', 0)
                    break
            rows.append({'city': city, 'kills': kills})
        rows.sort(key=lambda x: x['kills'], reverse=True)
        return rows[:limit]
