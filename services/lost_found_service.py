"""失物招领 / 掉落物品生命周期。

PK 战败时，败方背包里每一堆「未绑定药品或未绑定装备」各有 20% 概率掉落 1 个，
转为 LostItem：
- 阶段 `holding`（持有期，默认 30 天）：原主可凭赎金券赎回；
- 阶段 `auction`（拍卖期，默认 7 天）：全员可出价，最高价者得；
- 拍卖结束后：有最高出价者则发放给中标人，否则物品永久消失。

掉落的装备会把实例归属置空（中立），赎回/拍卖发放时再转移给新主人（grant_lost_item），
保证 EquipmentInstance.player_id 与持有人一致（否则无法穿戴/强化）。

LostItemLifecycle.run() 负责惰性推进状态机，由 lost_found 蓝图路由在查询前调用，
无需独立定时任务。
"""

import random
from datetime import datetime, timedelta

from services import db
from services.data_service import DataService
from models.player import LostItem, InventoryItem, EquipmentInstance

# 持有期（天）：超过后转入拍卖
HOLDING_DAYS = 30
# 拍卖期（天）：超过后结算给最高出价者或删除
AUCTION_DAYS = 7
# 单堆物品掉落概率（未绑定药品/装备）
DROP_CHANCE = 0.2
# 单堆物品掉落数量
DROP_QTY = 1
# 不参与掉落的物品（白名单排除，避免卡死赎回循环）
PROTECTED_ITEMS = {'redemption_ticket'}


def _resolve_item_name(item_id):
    """解析物品名：普通物品读 items.json；装备读装备实例名。"""
    item_def = DataService.get_item(item_id)
    if item_def:
        return item_def.get('name', item_id)
    equip = EquipmentInstance.query.filter_by(instance_id=item_id).first()
    return equip.name if equip else item_id


def _is_potion(inv):
    """药品：items.json 中 type=='potion' 的物品（回血/回蓝药剂）。"""
    item_def = DataService.get_item(inv.item_id)
    return bool(item_def) and item_def.get('type') == 'potion'


def _get_equipment(inv):
    """若该背包条目是装备，返回其装备实例；否则返回 None。"""
    if DataService.get_item(inv.item_id):
        return None  # 普通物品，非装备
    return EquipmentInstance.query.filter_by(instance_id=inv.item_id).first()


def create_lost_items_for_defeat(loser):
    """PK 战败掉落：败方背包每堆未绑定药品/装备各 20% 概率掉落 1 个，转为 LostItem。

    返回掉落明细列表 [(item_id, quantity), ...]，便于上层拼装结算消息。
    仅处理 is_bound=False；调用方自行决定何时触发（通常为异国战败）。
    掉落的装备实例归属置空（中立），赎回/拍卖时经 grant_lost_item 转移归属。
    """
    dropped = []
    unbound = InventoryItem.query.filter_by(
        player_id=loser.id, is_bound=False).all()
    for inv in unbound:
        if inv.item_id in PROTECTED_ITEMS:
            continue
        is_potion = _is_potion(inv)
        equip = None if is_potion else _get_equipment(inv)
        if not (is_potion or equip):
            continue
        if (inv.quantity or 0) < DROP_QTY:
            continue
        if random.random() >= DROP_CHANCE:
            continue
        lost = LostItem(
            player_id=loser.id,
            item_id=inv.item_id,
            quantity=DROP_QTY,
            is_bound=False,
            lost_at=datetime.now(),
            stage='holding',
        )
        db.session.add(lost)
        DataService.remove_item_from_inventory(
            loser.id, inv.item_id, DROP_QTY, is_bound=False)
        if equip:
            equip.player_id = None  # 失落期间中立
        dropped.append((inv.item_id, DROP_QTY))
    return dropped


def grant_lost_item(player_id, lost_item):
    """把失物发放给 player_id（赎回/拍卖结算）；若为装备，同步转移实例归属。"""
    DataService.add_item_to_inventory(
        player_id, lost_item.item_id, lost_item.quantity,
        is_bound=lost_item.is_bound)
    equip = EquipmentInstance.query.filter_by(instance_id=lost_item.item_id).first()
    if equip:
        equip.player_id = player_id
        equip.is_bound = lost_item.is_bound


def get_redeem_price(lost_item):
    """赎回价 = 物品卖出价 × 数量（1:1）。装备用实例卖出价，普通物品用 items.json 的 sell_price。"""
    equip = EquipmentInstance.query.filter_by(instance_id=lost_item.item_id).first()
    if equip:
        return equip.get_sell_price() * lost_item.quantity
    item_def = DataService.get_item(lost_item.item_id)
    unit = item_def.get('sell_price', 10) if item_def else 10
    return unit * lost_item.quantity


def _format_dropped(dropped):
    """把掉落明细转成可读文本，例如 '玄铁x2、回生丸'（数量为1不显示数量）。"""
    if not dropped:
        return ''
    parts = []
    for item_id, qty in dropped:
        name = _resolve_item_name(item_id)
        parts.append(f"{name}x{qty}" if qty > 1 else name)
    return "、".join(parts)


class LostItemLifecycle:
    """推进 LostItem 状态机，由蓝图路由惰性调用。"""

    @classmethod
    def run(cls):
        now = datetime.now()
        cls._holding_to_auction(now)
        cls._finalize_auction(now)

    @classmethod
    def _holding_to_auction(cls, now):
        """持有期超过 HOLDING_DAYS 的物品转入拍卖。"""
        holding = LostItem.query.filter_by(stage='holding').all()
        promoted = 0
        for item in holding:
            if (now - item.lost_at).days >= HOLDING_DAYS:
                item.stage = 'auction'
                item.auction_started_at = now
                item.current_bid = 0
                item.current_bidder_id = None
                promoted += 1
        if promoted:
            db.session.commit()

    @classmethod
    def _finalize_auction(cls, now):
        """拍卖期超过 AUCTION_DAYS 的物品结算：有中标人则发放，否则删除。"""
        auctions = LostItem.query.filter(
            LostItem.stage == 'auction',
            LostItem.auction_started_at.isnot(None),
        ).all()
        finalized = 0
        for item in auctions:
            if (now - item.auction_started_at).days < AUCTION_DAYS:
                continue
            if item.current_bidder_id:
                bidder = DataService.get_player_by_id(item.current_bidder_id)
                if bidder:
                    # 出价银两在 bid 时已扣除，此处发放物品（装备同步转移归属）
                    grant_lost_item(bidder.id, item)
            db.session.delete(item)
            finalized += 1
        if finalized:
            db.session.commit()
