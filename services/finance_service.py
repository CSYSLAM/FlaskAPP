import time
import random
from datetime import date
from services.data_service import DataService


# ---- Tunable constants ----
TICK_INTERVAL = 300          # 实时股价刷新间隔（秒），5分钟
DAILY_MAX_CHANGE = 0.10      # 每日累计涨跌幅上限 ±10%
RANDOM_PART = 0.08           # A: 纯随机部分 ±8%
POP_PART_UP = 0.01           # B: 人气最多涨 +1%
POP_PART_DOWN = 0.005        # B: 人气最多跌 -0.5%
BANDIT_PART_UP = 0.01        # C: 劫匪最多涨 +1%
BANDIT_PART_DOWN = 0.004     # C: 劫匪最多跌 -0.4%
TICK_DRIFT = 0.01            # 单次实时tick波动上限 ±1%
FEE_RATE = 0.0005            # 万五手续费
POP_THRESHOLD = 20           # 人气满档所需当日NPC访问次数
BANDIT_THRESHOLD = 10        # 劫匪满档所需当日击杀次数
BANDIT_ENCOUNTER_RATE = 0.30 # 该城市劫匪在场时遇敌概率
BANDIT_RESPAWN = 300         # 劫匪击杀后5分钟复活
BANDIT_POINTS_PER_JINZU = 100  # 击杀劫匪积分：每100点兑1金珠（等效每次0.01金珠）
HISTORY_LEN = 48             # 每只股票保留的历史价条数


class BanditState:
    __slots__ = ('city', 'spawned', 'defeated_at', 'killer_today', 'location_id')

    def __init__(self, city):
        self.city = city
        self.spawned = True          # 未击杀则持续存在
        self.defeated_at = 0
        self.killer_today = None
        self.location_id = ''        # 当前出没的具体场景 location_id（随机）


class FinanceService:
    """理财·股市服务。股价与劫匪状态均为类级内存（惰性时间戳刷新，仿 WorldBossService）。"""

    _stocks = {}          # {stock_id: {...}}
    _bandits = {}         # {city: BanditState}
    _daily_stats = {}     # {stock_id: {"npc_visits": int, "bandit_kills": int, "npc_visitors": set}}
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
                'open_price': base,     # 当日开盘价
                'price': base,          # 当前实时价
                'last_price': base,     # 上次tick价（用于显示涨跌）
                'day_change': 0.0,      # 当日累计涨跌幅
                'random_part': 0.0,     # A
                'pop_part': 0.0,        # B
                'bandit_part': 0.0,     # C
                'total_shares': int(sd.get('total_shares', 100000)),
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
        cls._day_key = str(date.today())
        cls._last_tick = time.time()
        cls._rebuild_outstanding()
        cls._settle_day_change()   # 开盘随机A
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
    #  跨天与实时tick
    # ===================================================================
    @classmethod
    def _ensure_day(cls):
        today = str(date.today())
        if today == cls._day_key:
            return
        # 跨天：昨收为今开，重置统计，重算A
        for sid, s in cls._stocks.items():
            s['open_price'] = s['price']
            s['last_price'] = s['price']
            s['history'] = [s['price']]
        for sid in cls._daily_stats:
            cls._daily_stats[sid] = {
                'npc_visits': 0, 'bandit_kills': 0, 'npc_visitors': set()}
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
        # 收集该 area 的所有场景 location_id
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
        """结算当日各股票的三部分涨跌（A随机、B人气、C劫匪）。在开盘/跨天时调用。"""
        for sid, s in cls._stocks.items():
            stats = cls._daily_stats.get(sid, {})
            # A 纯随机 ±8%
            a = random.uniform(-RANDOM_PART, RANDOM_PART)
            # B 人气：pop_factor∈[0,1]，B = pop_factor * uniform(-0.5%, +1%)
            pop = min(1.0, stats.get('npc_visits', 0) / POP_THRESHOLD) if POP_THRESHOLD else 0
            b = pop * random.uniform(-POP_PART_DOWN, POP_PART_UP)
            # C 劫匪：bandit_factor∈[0,1]，C = bandit_factor * uniform(-0.4%, +1%)
            bf = min(1.0, stats.get('bandit_kills', 0) / BANDIT_THRESHOLD) if BANDIT_THRESHOLD else 0
            c = bf * random.uniform(-BANDIT_PART_DOWN, BANDIT_PART_UP)
            s['random_part'] = round(a, 4)
            s['pop_part'] = round(b, 4)
            s['bandit_part'] = round(c, 4)
            change = max(-DAILY_MAX_CHANGE, min(DAILY_MAX_CHANGE, a + b + c))
            s['day_change'] = round(change, 4)

    @classmethod
    def _maybe_tick(cls):
        """惰性实时tick：距上次>=5分钟则在趋势线附近游走，相邻差≤1%。"""
        now = time.time()
        if now - cls._last_tick < TICK_INTERVAL:
            return
        cls._last_tick = now
        for sid, s in cls._stocks.items():
            target = s['open_price'] * (1 + s['day_change'])
            drift = random.uniform(-TICK_DRIFT, TICK_DRIFT)
            new_price = s['price'] * (1 + drift)
            # 收敛到当日目标价，避免长期偏离趋势
            new_price = new_price * 0.8 + target * 0.2
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

    # ===================================================================
    #  公开查询
    # ===================================================================
    @classmethod
    def get_market(cls):
        """返回行情列表（触发刷新）。"""
        cls._ensure_init()
        result = []
        for sid, s in cls._stocks.items():
            result.append(cls._public_view(s))
        return result

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
            'history': list(s['history']),
        }

    @classmethod
    def get_player_holdings(cls, player):
        """返回玩家持仓明细（含浮盈亏）。"""
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
        """玩家理财汇总：金珠、持仓市值、浮盈亏、已实现盈亏、累计成交。"""
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
            'holdings_count': len(rows),
            'bandit_points': int(fd.get('bandit_points', 0)),
            'bandit_points_per_jinzu': BANDIT_POINTS_PER_JINZU,
        }

    # ===================================================================
    #  交易
    # ===================================================================
    @classmethod
    def buy(cls, player, stock_id, shares):
        cls._ensure_init()
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
        holdings = fd.get('holdings') or {}
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
    #  增股接口（后续活动扩容）
    # ===================================================================
    @classmethod
    def increase_total_shares(cls, stock_id, amount):
        """增股：提升发行总量上限，不影响已流通股数。"""
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
        """根据区域area_id找对应城市劫匪状态。返回 (BanditState, stock) 或 (None, None)。"""
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
    def try_bandit_encounter(cls, player):
        """start_pve时调用：若该城市劫匪在场，按概率返回劫匪monster_id，否则返回None。
        返回 (monster_id or None, city)。"""
        cls._ensure_init()
        loc = DataService.get_locations().get(player.current_location, {})
        area_id = loc.get('area_id', '')
        b, s = cls.get_bandit_for_area(area_id)
        if not b or not s:
            return None, None
        if not b.spawned:
            return None, None
        if random.random() < BANDIT_ENCOUNTER_RATE:
            return cls._bandit_monster_id(s['city']), s['city']
        return None, None

    @classmethod
    def _bandit_monster_id(cls, city):
        return f"bandit_{city}"

    @classmethod
    def get_bandit_monster_data(cls, city):
        """构造劫匪怪物数据dict（供Monster.from_dict使用）。击杀计入城市榜。"""
        cls._ensure_init()
        # 劫匪强度参考普通怪，掉落少量金珠（富商答谢）
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
        """把劫匪怪物注入monsters缓存，使Monster.create_monster能找到。"""
        cls._ensure_init()
        for sid, s in cls._stocks.items():
            mid = cls._bandit_monster_id(s['city'])
            if mid not in monsters_cache:
                monsters_cache[mid] = cls.get_bandit_monster_data(s['city'])

    @classmethod
    def record_bandit_kill(cls, monster_id, player):
        """击杀劫匪时调用：计入城市榜单 + 积分制奖励（每100点兑1金珠，等效每次0.01金珠）。
        返回 dict {points, jinzu, total_points} 供提示。"""
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
        # 计入该城市关联股票的当日击杀统计
        for sid, s in cls._stocks.items():
            if s['city'] == city:
                stats = cls._daily_stats.setdefault(sid, {
                    'npc_visits': 0, 'bandit_kills': 0, 'npc_visitors': set()})
                stats['bandit_kills'] += 1
                break
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
        return {'points': 1, 'jinzu': jinzu_gain, 'total_points': bandit_points}

    @classmethod
    def get_bandit_at_location(cls, location_id):
        """若该场景有劫匪出没且在场，返回 (monster_id, city, respawn_remaining)，否则 None。
        供 scene 渲染把劫匪加入怪物列表。"""
        cls._ensure_init()
        if not location_id:
            return None
        for city, b in cls._bandits.items():
            cls._check_bandit_respawn(b)
            if b.location_id == location_id and b.spawned:
                return (cls._bandit_monster_id(city), city, 0)
            if b.location_id == location_id and not b.spawned and b.defeated_at:
                rem = max(0, int(BANDIT_RESPAWN - (time.time() - b.defeated_at)))
                return (cls._bandit_monster_id(city), city, rem)
        return None

    @classmethod
    def get_bandit_status(cls):
        """各城市劫匪状态（供义士榜/页面展示）。含当前坐标与传送目标。"""
        cls._ensure_init()
        from services.map_service import MapService
        result = []
        for city, b in cls._bandits.items():
            cls._check_bandit_respawn(b)
            respawn = 0
            if not b.spawned and b.defeated_at:
                respawn = max(0, int(BANDIT_RESPAWN - (time.time() - b.defeated_at)))
            # 该城市关联股票的 area_id 与当日击杀数
            area_id = ''
            kills = 0
            for sid, s in cls._stocks.items():
                if s['city'] == city:
                    area_id = s['area_id']
                    kills = cls._daily_stats.get(sid, {}).get('bandit_kills', 0)
                    break
            # 当前坐标：劫匪随机出没的具体场景
            location_id = b.location_id
            loc_name = ''
            area_name = ''
            if location_id:
                loc = DataService.get_locations().get(location_id, {})
                loc_name = loc.get('name', location_id)
                area_name = loc.get('area_name', '')
            # 传送目标仍为城市广场（玩家到广场后步行至劫匪场景）
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
        """义士榜：按当日各城市击杀劫匪总数排行（城市维度）。"""
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
