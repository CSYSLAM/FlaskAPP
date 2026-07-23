# -*- coding: utf-8 -*-
"""蛮夷入侵活动（南蛮 / 北夷）服务层。

时间规则（参照 ref，并支持常驻+管理触发）：
- 南蛮士卒：12:00 刷新为 300 只，13:00 清零；活动界面仅显示本国数量。
- 南蛮首领：13:00 刷新（alive）；被击杀后置 recovering，直到下次 13:00 刷新。
- 北夷士卒：18:00 刷新为 300 只，19:00 清零。
- 北夷首领：19:00 刷新。
- 非安全区（can_pk）移动按几率遭遇士卒（10-29 级）或铁骑（30+ 级）。

所有时间跃迁在 tick() 内幂等完成，由访问活动页 / 移动 / 结算时触发。
默认 active=True（常驻可玩，管理员可手动刷新/清零）；active=False 时按真实时钟窗口启停。
"""
import random
import datetime

from services import db
from models.barbarian import BarbarianInvasion, BarbarianLeader


# ---- 配置常量 ----
SIDES = ('南', '北')
SOLDIER_REFRESH_HOUR = {'南': 12, '北': 18}   # 士卒刷新小时
SOLDIER_CLEAR_HOUR = {'南': 13, '北': 19}     # 士卒清零小时
LEADER_REFRESH_HOUR = {'南': 13, '北': 19}    # 首领刷新小时
SOLDIER_POOL = 300                           # 每次刷新数量
BARBARIAN_ENCOUNTER_RATE = 0.20              # 非安全区移动遭遇几率

# 怪物 id（monsters.json）
SOLDIER_ID = {
    '南': {'士卒': 'monster_南蛮士卒', '铁骑': 'monster_南蛮铁骑'},
    '北': {'士卒': 'monster_北夷士卒', '铁骑': 'monster_北夷铁骑'},
}
LEADER_MONSTER = {
    '南': {'老三': 'monster_南蛮老三', '老二': 'monster_南蛮老二', '老大': 'monster_南蛮老大'},
    '北': {'老三': 'monster_北夷老三', '老二': 'monster_北夷老二', '老大': 'monster_北夷老大'},
}
# 反向：monster_id -> (side, kind, key)
_MONSTER_INDEX = {}
for _s in SIDES:
    for _k, _mid in SOLDIER_ID[_s].items():
        _MONSTER_INDEX[_mid] = (_s, 'soldier', _k)
    for _k, _mid in LEADER_MONSTER[_s].items():
        _MONSTER_INDEX[_mid] = (_s, 'leader', _k)

# 首领按城市刷新（scene id 列表）
LEADER_CITIES = {
    '老三': ['beiping_center.广场', 'jianing_center.广场', 'wujun_center.广场'],
    '老二': ['jinyang_center.广场', 'yong_an_center.广场', 'chaisang_center.广场'],
    '老大': ['xuchang_center.广场', 'chengdu_center.广场', 'jianye_center.广场'],
}
LEADERS_CFG = [
    {'key': '老三', 'level': 10, 'tier': 'basic'},
    {'key': '老二', 'level': 20, 'tier': 'mid'},
    {'key': '老大', 'level': 30, 'tier': 'high'},
]
# 首领几率掉落的神器（两边同级相同）
LEADER_SHENQI = {'老三': 'shenqi_duanhungou', '老二': 'shenqi_shixiegou', '老大': 'shenqi_libiegou'}
# 铁骑（40 级）几率掉落的神器（南北通用：连月钩/催命钩）
TIEQI_SHENQI = ['shenqi_lianyuegou', 'shenqi_cuiminggou']
TIEQI_SHENQI_RATE = 0.15     # 铁骑神器掉落几率
LEADER_SHENQI_RATE = 0.30    # 首领神器掉落几率

# 首领掉落说明（活动页 tooltip）
LEADER_DROP_TEXT = {
    '老三': '必定掉落:[活]来袭凭证×1、蛮夷宝匣×1、聚魂幡碎片×1、强化宝玉×1、[活]图鉴×1；几率掉落:【神器】断魂钩(20级)',
    '老二': '必定掉落:[活]来袭凭证×1、蛮夷宝匣×1、聚魂幡碎片×1、强化宝玉×1、[活]图鉴×1；几率掉落:【神器】嗜血钩(25级)',
    '老大': '必定掉落:[活]来袭凭证×1、蛮夷宝匣×1、聚魂幡碎片×1、强化宝玉×1、[活]图鉴×1；几率掉落:【神器】离别钩(30级)',
}

# 凭证兑奖目录（消耗 [活]来袭凭证）
CREDIT_ITEM_ID = 'laiqin_pingzheng'
REDEEM_CATALOG = [
    {'item_id': 'title_prefix_dasha', 'name': '称号卷轴-大杀四方的', 'price': 800, 'kind': 'item'},
    {'item_id': 'title_prefix_minzu', 'name': '称号卷轴-民族义士', 'price': 800, 'kind': 'item'},
    {'item_id': 'qianghua_baoyu',     'name': '强化宝玉',            'price': 100, 'kind': 'item'},
    {'item_id': 'juhunfan_suipian',   'name': '聚魂幡碎片',          'price': 150, 'kind': 'item'},
    {'item_id': 'manyi_baoxia',       'name': '[活]蛮夷宝箱',        'price': 30,  'kind': 'item'},
    {'item_id': 'shenqi_lianyuegou',  'name': '【神器】连月钩', 'price': 1000, 'kind': 'equip', 'template_id': 'shenqi_lianyuegou',  'star_min': 1, 'star_max': 5},
    {'item_id': 'shenqi_cuiminggou',  'name': '【神器】催命钩', 'price': 1200, 'kind': 'equip', 'template_id': 'shenqi_cuiminggou', 'star_min': 1, 'star_max': 5},
    {'item_id': 'shenqi_duanhungou',  'name': '【神器】断魂钩', 'price': 1200, 'kind': 'equip', 'template_id': 'shenqi_duanhungou', 'star_min': 1, 'star_max': 5},
    {'item_id': 'shenqi_shixiegou',   'name': '【神器】嗜血钩', 'price': 1400, 'kind': 'equip', 'template_id': 'shenqi_shixiegou',  'star_min': 1, 'star_max': 5},
    {'item_id': 'shenqi_libiegou',    'name': '【神器】离别钩', 'price': 1600, 'kind': 'equip', 'template_id': 'shenqi_libiegou',   'star_min': 1, 'star_max': 5},
    # 菊香神套（25 级，神器品质，非武器/饰品）
    {'item_id': 'juxiang_hue',      'name': '【神器】菊香护额', 'price': 1500, 'kind': 'equip', 'template_id': 'juxiang_hue',      'star_min': 1, 'star_max': 5},
    {'item_id': 'juxiang_changju',  'name': '【神器】菊香长袍', 'price': 1500, 'kind': 'equip', 'template_id': 'juxiang_changju',  'star_min': 1, 'star_max': 5},
    {'item_id': 'juxiang_changmao', 'name': '【神器】菊香长裤', 'price': 1500, 'kind': 'equip', 'template_id': 'juxiang_changmao', 'star_min': 1, 'star_max': 5},
    {'item_id': 'juxiang_huwan',    'name': '【神器】菊香护手', 'price': 1600, 'kind': 'equip', 'template_id': 'juxiang_huwan',    'star_min': 1, 'star_max': 5},
    {'item_id': 'juxiang_duanyue',  'name': '【神器】菊香短靴', 'price': 1600, 'kind': 'equip', 'template_id': 'juxiang_duanyue',  'star_min': 1, 'star_max': 5},
]

# 蛮夷宝箱开启：神武 / 菊香神套 池
SHENQI_POOL = ['shenqi_lianyuegou', 'shenqi_cuiminggou', 'shenqi_duanhungou', 'shenqi_shixiegou', 'shenqi_libiegou']
JUXIANG_POOL = ['juxiang_hue', 'juxiang_changju', 'juxiang_changmao', 'juxiang_huwan', 'juxiang_duanyue']
BOX_ITEM_ID = 'manyi_baoxia'            # [活]蛮夷宝箱（由凭证兑奖兑换）
CHEST_KEY_ITEM = 'manyi_baoxiang_key'  # [活]宝箱钥匙（由蛮夷怪物掉落）
# 菊香神炉打造消耗
FORGE_COST = {'juxiang_forge_blueprint': 1, 'juhunfan_suipian': 5, 'qianghua_baoyu': 5}
FORGE_SUCCESS_RATE = 0.50


class BarbarianService:

    # ---------- 初始化 / 时间跃迁 ----------
    @classmethod
    def get_or_create_state(cls, side):
        state = BarbarianInvasion.query.filter_by(side=side).first()
        if not state:
            state = BarbarianInvasion(
                side=side, active=True,
                wei_soldiers=SOLDIER_POOL, shu_soldiers=SOLDIER_POOL, wu_soldiers=SOLDIER_POOL)
            db.session.add(state)
            db.session.commit()
            cls.seed_leaders(side)
        return state

    @classmethod
    def seed_leaders(cls, side):
        """确保某方三名首领存在（默认 alive，常驻可玩）。"""
        for cfg in LEADERS_CFG:
            if not BarbarianLeader.query.filter_by(side=side, key=cfg['key']).first():
                db.session.add(BarbarianLeader(
                    side=side, key=cfg['key'],
                    name=f"【活】{('南蛮' if side == '南' else '北夷')}{cfg['key']}",
                    level=cfg['level'], tier=cfg['tier'],
                    monster_id=LEADER_MONSTER[side][cfg['key']], status='alive'))
        db.session.commit()

    @classmethod
    def _side_available(cls, side, now=None):
        now = now or datetime.datetime.now()
        state = cls.get_or_create_state(side)
        if state.active:
            return True
        return SOLDIER_REFRESH_HOUR[side] <= now.hour < SOLDIER_CLEAR_HOUR[side]

    @classmethod
    def tick(cls, side, now=None):
        """幂等时间跃迁（仅 active=False 的定时模式生效）。"""
        now = now or datetime.datetime.now()
        state = cls.get_or_create_state(side)
        if state.active:
            return state

        # 士卒
        if SOLDIER_REFRESH_HOUR[side] <= now.hour < SOLDIER_CLEAR_HOUR[side]:
            if not state.last_soldier_tick or state.last_soldier_tick.date() != now.date():
                for c in BarbarianInvasion.COUNTRIES:
                    state.set_soldier(c, SOLDIER_POOL)
                state.last_soldier_tick = now
        else:
            if any(state.soldier_count(c) for c in BarbarianInvasion.COUNTRIES):
                for c in BarbarianInvasion.COUNTRIES:
                    state.set_soldier(c, 0)

        # 首领：>=刷新小时 当日未刷新则全部 alive
        if now.hour >= LEADER_REFRESH_HOUR[side]:
            if not state.last_leader_tick or state.last_leader_tick.date() != now.date():
                for leader in BarbarianLeader.query.filter_by(side=side).all():
                    leader.status = 'alive'
                    leader.killed_at = None
                state.last_leader_tick = now

        db.session.commit()
        return state

    # ---------- 查询 ----------
    @classmethod
    def get_state(cls, player, side):
        cls.tick(side)
        state = cls.get_or_create_state(side)
        leaders = []
        for cfg in LEADERS_CFG:
            leader = BarbarianLeader.query.filter_by(side=side, key=cfg['key']).first()
            leaders.append({
                'key': cfg['key'],
                'name': leader.name if leader else '',
                'level': cfg['level'],
                'status': leader.status if leader else 'alive',
                'drop_text': LEADER_DROP_TEXT.get(cfg['key'], ''),
                'monster_id': LEADER_MONSTER[side][cfg['key']],
            })
        return {
            'side': side,
            'country': player.country,
            'soldiers': state.soldier_count(player.country),
            'leaders': leaders,
        }

    @classmethod
    def soldier_window_open(cls, side, now=None):
        now = now or datetime.datetime.now()
        state = cls.get_or_create_state(side)
        return cls._side_available(side, now) and \
            any(state.soldier_count(c) for c in BarbarianInvasion.COUNTRIES)

    # ---------- 遭遇 ----------
    @classmethod
    def maybe_encounter(cls, player, location):
        """非安全区（can_pk）移动时按几率返回蛮夷怪物 id，否则 None。"""
        if not location or not location.get('can_pk'):
            return None  # 仅非安全区
        if player.level < 10:
            return None
        candidates = [s for s in SIDES if cls._side_available(s)]
        if not candidates:
            return None
        side = random.choice(candidates)
        state = cls.get_or_create_state(side)
        if state.soldier_count(player.country) <= 0:
            return None
        if random.random() >= BARBARIAN_ENCOUNTER_RATE:
            return None
        # 10-29 级遇士卒，30+ 级遇铁骑
        return SOLDIER_ID[side]['铁骑' if player.level >= 30 else '士卒']

    # ---------- 击杀回调 ----------
    @classmethod
    def is_barbarian_monster(cls, monster_id):
        """判断某怪物是否为南蛮/北夷入侵怪物（供 battle_service 放行挑战）。"""
        return monster_id in _MONSTER_INDEX

    @classmethod
    def on_kill(cls, player, monster_id):
        """战斗胜利后由 battle_service 调用：扣减士卒 / 首领置复苏中 + 几率神器。"""
        info = _MONSTER_INDEX.get(monster_id)
        if not info:
            return ""
        side, kind, key = info
        msgs = []
        if kind == 'soldier':
            cls.decrement_soldier(side, player.country)
            cls._bump(player, 'soldier', side)
            # 铁骑（40 级）几率掉落神器（连月钩/催命钩）
            if key == '铁骑' and random.random() < TIEQI_SHENQI_RATE:
                tmpl = random.choice(TIEQI_SHENQI)
                name = cls._grant_bound_shenqi(player, tmpl)
                if name:
                    msgs.append(f"获得{name}")
        else:
            cls.kill_leader(side, key)
            cls._bump(player, 'leader', side)
            # 首领几率掉落对应神器
            if random.random() < LEADER_SHENQI_RATE:
                tmpl = LEADER_SHENQI.get(key)
                if tmpl:
                    name = cls._grant_bound_shenqi(player, tmpl)
                    if name:
                        msgs.append(f"获得{name}")
        cls._trigger_achievements(player)
        return "；".join(msgs)

    @classmethod
    def _grant_bound_shenqi(cls, player, template_id):
        """生成一件绑定的神器并加入背包，返回其名称（失败返回 None）。"""
        from services.data_service import DataService
        from services.equipment_service import EquipmentService
        equip = EquipmentService.generate_random_equipment(player.id, template_id, rarity='神器')
        if not equip:
            return None
        equip.is_bound = True
        db.session.add(equip)
        db.session.flush()
        DataService.add_item_to_inventory(player.id, equip.instance_id)
        return equip.name

    @classmethod
    def _bump(cls, player, kind, side):
        """累计击杀计数（存于 activity_data，供成就使用，无需迁移表结构）。"""
        data = player.activity_data or {}
        b = data.setdefault('barbarian', {})
        if kind == 'soldier':
            b['soldier_total'] = b.get('soldier_total', 0) + 1
        else:
            b['leader_total'] = b.get('leader_total', 0) + 1
            b[side + '_leader'] = b.get(side + '_leader', 0) + 1
        player.activity_data = data

    @classmethod
    def _trigger_achievements(cls, player):
        """检查蛮夷相关成就（击杀 / 神器持有）。"""
        try:
            from services.achievement_service import AchievementService
            AchievementService.check(player, 'barbarian_soldier_kill')
            AchievementService.check(player, 'barbarian_leader_kill')
            AchievementService.check(player, 'artifact_owned')
        except Exception:
            pass

    @classmethod
    def decrement_soldier(cls, side, country, n=1):
        state = cls.get_or_create_state(side)
        cur = state.soldier_count(country)
        if cur <= 0:
            return
        state.set_soldier(country, cur - n)
        db.session.commit()

    @classmethod
    def kill_leader(cls, side, key):
        leader = BarbarianLeader.query.filter_by(side=side, key=key).first()
        if not leader:
            return
        leader.status = 'recovering'
        leader.killed_at = datetime.datetime.now()
        db.session.commit()

    # ---------- 首领在领地城市的注入 ----------
    @classmethod
    def active_leader_monster_ids_at(cls, location_id):
        """返回当前城市应注入的存活首领怪物 id 列表（用于场景显示，两方均含）。"""
        result = []
        for side in SIDES:
            cls.tick(side)
            for key, cities in LEADER_CITIES.items():
                if location_id in cities:
                    leader = BarbarianLeader.query.filter_by(side=side, key=key).first()
                    if leader and leader.status == 'alive':
                        result.append(leader.monster_id)
        return result

    # ---------- 凭证兑奖 ----------
    @classmethod
    def get_redeem_catalog(cls):
        return REDEEM_CATALOG

    @classmethod
    def get_credit_balance(cls, player):
        from services.data_service import DataService
        inv = DataService.get_inventory_item(player.id, CREDIT_ITEM_ID)
        return inv.quantity if inv else 0

    @classmethod
    def redeem(cls, player, item_id, qty=1):
        from services.data_service import DataService
        from services.equipment_service import EquipmentService
        qty = max(1, int(qty))
        entry = next((e for e in REDEEM_CATALOG if e['item_id'] == item_id), None)
        if not entry:
            return False, "无此兑换项"
        cost = entry['price'] * qty
        balance = cls.get_credit_balance(player)
        if balance < cost:
            return False, f"来袭凭证不足（需 {cost}，现有 {balance}）"

        DataService.remove_item_from_inventory(player.id, CREDIT_ITEM_ID, quantity=cost)
        if entry['kind'] == 'item':
            for _ in range(qty):
                DataService.add_item_to_inventory(player.id, entry['item_id'])
        else:  # equip：生成神器（绑定）
            for _ in range(qty):
                stars = random.randint(entry.get('star_min', 1), entry.get('star_max', 5))
                equip = EquipmentService.generate_random_equipment(
                    player.id, entry['template_id'], rarity='神器', stars=stars)
                if equip:
                    equip.is_bound = True
                    db.session.add(equip)
                    db.session.flush()
                    DataService.add_item_to_inventory(player.id, equip.instance_id)
        db.session.commit()
        cls._trigger_achievements(player)
        return True, f"已兑换 {entry['name']}×{qty}"

    # ---------- 蛮夷宝箱开启 ----------
    @classmethod
    def open_chest(cls, player):
        from services.data_service import DataService
        from services.equipment_service import EquipmentService
        box = DataService.get_inventory_item(player.id, BOX_ITEM_ID)
        if not box or box.quantity < 1:
            return False, "没有可用的[活]蛮夷宝箱（请到凭证兑奖处兑换）"
        key = DataService.get_inventory_item(player.id, CHEST_KEY_ITEM)
        if not key or key.quantity < 1:
            return False, "开启[活]蛮夷宝箱需要1个[活]宝箱钥匙（蛮夷怪物掉落）"
        DataService.remove_item_from_inventory(player.id, BOX_ITEM_ID, 1)
        DataService.remove_item_from_inventory(player.id, CHEST_KEY_ITEM, 1)

        gold = random.randint(500, 3000)
        exp = random.randint(200, 1000)
        player.gold = (player.gold or 0) + gold
        player.experience = (player.experience or 0) + exp
        msgs = [f"获得银两{gold}、经验{exp}"]

        # 必得 南/北 图鉴之一
        tujian = random.choice(['nanman_tujian', 'beiye_tujian'])
        DataService.add_item_to_inventory(player.id, tujian, 1)
        name = (DataService.get_item(tujian) or {}).get('name', tujian)
        msgs.append(f"获得{name}")

        # 几率获得 神武 / 菊香神套
        roll = random.random()
        if roll < 0.3:
            tmpl = random.choice(SHENQI_POOL)
            equip = EquipmentService.generate_random_equipment(player.id, tmpl, rarity='神器')
            if equip:
                equip.is_bound = True
                db.session.add(equip)
                db.session.flush()
                DataService.add_item_to_inventory(player.id, equip.instance_id)
                msgs.append(f"获得{equip.name}")
        elif roll < 0.6:
            tmpl = random.choice(JUXIANG_POOL)
            equip = EquipmentService.generate_random_equipment(player.id, tmpl, rarity='神器')
            if equip:
                equip.is_bound = True
                db.session.add(equip)
                db.session.flush()
                DataService.add_item_to_inventory(player.id, equip.instance_id)
                msgs.append("获得菊香神套部件")

        db.session.commit()
        cls._trigger_achievements(player)
        return True, "；".join(msgs)

    # 兼容旧路由名
    open_box = open_chest

    # ---------- 菊香神炉打造 ----------
    @classmethod
    def forge_juxiang(cls, player):
        """铁砧铺·菊香神炉：消耗 图纸×1 + 聚魂幡碎片×5 + 强化宝玉×5，50% 成功。"""
        from services.data_service import DataService
        from services.equipment_service import EquipmentService
        for item_id, need in FORGE_COST.items():
            inv = DataService.get_inventory_item(player.id, item_id)
            have = inv.quantity if inv else 0
            if have < need:
                item_name = (DataService.get_item(item_id) or {}).get('name', item_id)
                return False, f"材料不足：{item_name} 需 {need}，现有 {have}"
        # 扣除材料
        for item_id, need in FORGE_COST.items():
            DataService.remove_item_from_inventory(player.id, item_id, need)

        if random.random() >= FORGE_SUCCESS_RATE:
            db.session.commit()
            return False, "菊香神炉打造失败，材料已消耗"

        tmpl = random.choice(JUXIANG_POOL)
        equip = EquipmentService.generate_random_equipment(player.id, tmpl, rarity='神器')
        if equip:
            equip.is_bound = True
            db.session.add(equip)
            db.session.flush()
            DataService.add_item_to_inventory(player.id, equip.instance_id)
            db.session.commit()
            cls._trigger_achievements(player)
            return True, f"菊香神炉打造成功，获得{equip.name}"
        db.session.commit()
        return False, "菊香神炉打造失败，材料已消耗"

    # ---------- 管理：手动刷新 / 清零 ----------
    @classmethod
    def admin_refresh(cls, side=None):
        for s in (SIDES if side is None else [side]):
            state = cls.get_or_create_state(s)
            for c in BarbarianInvasion.COUNTRIES:
                state.set_soldier(c, SOLDIER_POOL)
            state.last_soldier_tick = datetime.datetime.now()
            for leader in BarbarianLeader.query.filter_by(side=s).all():
                leader.status = 'alive'
                leader.killed_at = None
            state.last_leader_tick = datetime.datetime.now()
            db.session.commit()
        return True

    @classmethod
    def admin_clear(cls, side=None):
        for s in (SIDES if side is None else [side]):
            state = cls.get_or_create_state(s)
            for c in BarbarianInvasion.COUNTRIES:
                state.set_soldier(c, 0)
            now = datetime.datetime.now()
            state.last_soldier_tick = now
            for leader in BarbarianLeader.query.filter_by(side=s).all():
                leader.status = 'recovering'
                leader.killed_at = now
            state.last_leader_tick = now
            db.session.commit()
        return True
