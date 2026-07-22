"""集市（玩家间自由交易）服务。

玩家将背包中非绑定的物品/装备挂到集市售卖，自定单价与数量：
- 上架时收取「上架费（总价1%最低100，不退）+ 广告费（0/1000/3000）」抑制刷屏；
- 买方付总价 +5% 手续费，卖家实收 95%；
- 装备挂单期间归属置空(player_id=None)锁定，买入/取消/过期时转移归属
  （参考 lost_found grant_lost_item 模式，到手/退回均未绑定）；
- 7 天自动下架退回（惰性状态机，由蓝图查询前调用 expire_listings）；
- 挂单上限 20 + VIP等级×2（VIP0=20 … VIP5=30）。
"""

from datetime import datetime, timedelta

from services import db
from services.data_service import DataService
from services.vip_service import VipService
from models.player import (MarketListing, MarketTransaction,
                             InventoryItem, EquipmentInstance, EquipmentSlot)

# 挂单有效期（天）
LISTING_DURATION = timedelta(days=7)
# 置顶时长（小时）
PIN_DURATION = timedelta(hours=3)

# 广告档位：0无 / 1基础(1000,全服通知) / 2置顶(3000,通知+置顶3h)
AD_TIER_NONE = 0
AD_TIER_BASIC = 1
AD_TIER_PREMIUM = 2
AD_FEES = {AD_TIER_NONE: 0, AD_TIER_BASIC: 1000, AD_TIER_PREMIUM: 3000}

# 手续费：买方付总价 +5%，卖家实收 95%
BUYER_FEE_RATE = 0.05
SELLER_RECEIVE_RATE = 0.95

# 挂单上限
BASE_LISTING_CAP = 20
VIP_CAP_BONUS_PER_LEVEL = 2

# 分页
PER_PAGE_DEFAULT = 20

# items.json type -> 中文分类（用于 tab 筛选）
TYPE_CATEGORY = {
    'material': '材料',
    'potion': '药品',
    'consumable': '消耗品',
    'chest': '宝箱',
    'equipment': '装备',
    'vip': '特权',
    'quest': '任务',
    'other': '其他',
}

# 不允许上架的物品 type（装备模板/任务/VIP 令牌等，应走专门入口）
NON_LISTABLE_TYPES = {'equipment', 'quest', 'vip'}

# 稀有度排序权重（高到低）
RARITY_ORDER = {"神器": 5, "史诗": 4, "卓越": 3, "精良": 2, "普通": 1}


class MarketService:
    # ------------------------------------------------------------------
    # 挂单上限
    # ------------------------------------------------------------------
    @classmethod
    def get_listing_cap(cls, player):
        """挂单上限 = 20 + VIP等级×2（VIP0=20 … VIP5=30）。"""
        level = VipService.get_active_vip_level(player)  # 0 if 无VIP
        return BASE_LISTING_CAP + (level or 0) * VIP_CAP_BONUS_PER_LEVEL

    @classmethod
    def get_active_count(cls, player_id):
        return MarketListing.query.filter(
            MarketListing.seller_id == player_id,
            MarketListing.status.in_(['active', 'partial']),
        ).count()

    # ------------------------------------------------------------------
    # 列表查询（筛选 + 排序 + 分页）
    # ------------------------------------------------------------------
    @classmethod
    def get_listings(cls, category=None, search=None, sort='new',
                     page=1, per_page=PER_PAGE_DEFAULT):
        """首页列表查询。返回 (rows, total, total_pages, page, per_page, pinned)。

        注：本系统改用 SQLAlchemy .filter().order_by().offset().limit() 而非
        代码库惯用的内存切片——集市挂单会持续增长，DB 层分页更高效。
        """
        cls.expire_listings()
        now = datetime.utcnow()

        q = MarketListing.query.filter(
            MarketListing.status.in_(['active', 'partial']),
            MarketListing.expires_at > now,
        )
        if category and category != '全部':
            q = q.filter(MarketListing.category == category)
        if search:
            q = q.filter(MarketListing.item_name.like(f'%{search}%'))

        if sort == 'price_asc':
            q = q.order_by(MarketListing.unit_price.asc())
        elif sort == 'price_desc':
            q = q.order_by(MarketListing.unit_price.desc())
        elif sort == 'rarity':
            q = q.filter(MarketListing.item_type == 'equipment')
            q = q.order_by(
                db.case(
                    (MarketListing.rarity == '神器', 5),
                    (MarketListing.rarity == '史诗', 4),
                    (MarketListing.rarity == '卓越', 3),
                    (MarketListing.rarity == '精良', 2),
                    else_=1,
                ).desc(),
                MarketListing.unit_price.asc(),
            )
        else:  # new
            q = q.order_by(MarketListing.created_at.desc())

        total = q.count()
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = max(1, min(page, total_pages))
        rows = q.offset((page - 1) * per_page).limit(per_page).all()

        # 置顶区：ad_tier==2 且 pin_until>now，最多 5 条
        pinned = MarketListing.query.filter(
            MarketListing.ad_tier == AD_TIER_PREMIUM,
            MarketListing.pin_until > now,
            MarketListing.status.in_(['active', 'partial']),
            MarketListing.expires_at > now,
        ).order_by(MarketListing.pin_until.desc()).limit(5).all()

        return rows, total, total_pages, page, per_page, pinned

    @classmethod
    def get_listing(cls, listing_id):
        return MarketListing.query.get(listing_id)

    @classmethod
    def get_player_listings(cls, player_id):
        return MarketListing.query.filter(
            MarketListing.seller_id == player_id,
            MarketListing.status.in_(['active', 'partial']),
        ).order_by(MarketListing.created_at.desc()).all()

    # ------------------------------------------------------------------
    # 上架数据源
    # ------------------------------------------------------------------
    @classmethod
    def get_listable_items(cls, player):
        """可上架的可堆叠物品：非绑定 + type 不在排除集。返回 [(item_id, name, qty, type, category), ...]。"""
        result = []
        for inv in DataService.get_inventory(player.id):
            if inv.is_bound:
                continue
            item_def = DataService.get_item(inv.item_id)
            if not item_def:
                continue
            itype = item_def.get('type', 'other')
            if itype in NON_LISTABLE_TYPES:
                continue
            result.append((
                inv.item_id,
                item_def.get('name', inv.item_id),
                inv.quantity or 0,
                itype,
                cls._type_to_category(itype),
            ))
        return result

    @classmethod
    def get_listable_equipment(cls, player):
        """可上架的装备：非绑定且未装备。返回 [(instance_id, name, rarity, slot, stars, sell_price), ...]。"""
        result = []
        for equip in DataService.get_unequipped_equipment(player.id):
            if equip.is_bound:
                continue
            result.append((
                equip.instance_id,
                equip.name,
                equip.rarity,
                equip.slot,
                equip.stars,
                equip.get_sell_price(),
            ))
        return result

    # ------------------------------------------------------------------
    # 上架
    # ------------------------------------------------------------------
    @classmethod
    def create_listing(cls, player, item_id=None, equipment_instance_id=None,
                       quantity=1, unit_price=0, ad_tier=AD_TIER_NONE):
        """创建挂单。返回 (ok: bool, msg: str)。"""
        try:
            quantity = int(quantity)
            unit_price = int(unit_price)
            ad_tier = int(ad_tier)
        except (TypeError, ValueError):
            return False, "参数无效"
        if quantity < 1:
            return False, "数量必须≥1"
        if unit_price < 1:
            return False, "单价必须≥1"
        if ad_tier not in AD_FEES:
            return False, "广告档位无效"

        # 挂单上限
        cap = cls.get_listing_cap(player)
        if cls.get_active_count(player.id) >= cap:
            return False, f"挂单已满（{cap}单），请先取消或售罄现有挂单"

        # 费用
        listing_fee = max(100, unit_price * quantity // 100)  # 总价1%最低100，不退
        ad_fee = AD_FEES[ad_tier]
        total_fee = listing_fee + ad_fee
        if player.gold < total_fee:
            return False, f"银两不足，需{total_fee}（上架费{listing_fee}+广告费{ad_fee}）"

        now = datetime.utcnow()
        item_name = item_type = category = rarity = None
        is_equipment = False

        if equipment_instance_id:
            # --- 装备 ---
            is_equipment = True
            equip = EquipmentInstance.query.filter_by(
                instance_id=equipment_instance_id, player_id=player.id).first()
            if not equip:
                return False, "装备不存在或不属于你"
            if equip.is_bound:
                return False, "绑定装备不可上架"
            # 未装备检查（equipment_instance_id 列为整型 id，非 UUID）
            slot = EquipmentSlot.query.filter_by(
                equipment_instance_id=equip.id).first()
            if slot:
                return False, "请先卸下装备"
            # 重复上架检查
            existing = MarketListing.query.filter_by(
                equipment_instance_id=equipment_instance_id,
                status='active').first()
            if existing:
                return False, "该装备已上架"
            # 锁定：归属置空（中立）
            equip.player_id = None
            item_name = equip.name
            item_type = 'equipment'
            category = '装备'
            rarity = equip.rarity
            quantity = 1  # 装备恒为1
        elif item_id:
            # --- 可堆叠物品 ---
            item_def = DataService.get_item(item_id)
            if not item_def:
                return False, "物品不存在"
            itype = item_def.get('type', 'other')
            if itype in NON_LISTABLE_TYPES:
                return False, "该类物品不可上架（请走专门入口）"
            inv = DataService.get_inventory_item(player.id, item_id, is_bound=False)
            if not inv or (inv.quantity or 0) < quantity:
                return False, "非绑物品数量不足"
            DataService.remove_item_from_inventory(
                player.id, item_id, quantity, is_bound=False)
            item_name = item_def.get('name', item_id)
            item_type = itype
            category = cls._type_to_category(itype)
            rarity = None
        else:
            return False, "未选择上架物品"

        # 扣费
        player.gold -= total_fee

        listing = MarketListing(
            seller_id=player.id,
            item_id=item_id if not is_equipment else None,
            equipment_instance_id=equipment_instance_id if is_equipment else None,
            item_name=item_name,
            item_type=item_type,
            category=category,
            rarity=rarity,
            quantity=quantity,
            unit_price=unit_price,
            is_bound=False,
            status='active',
            ad_tier=ad_tier,
            pin_until=(now + PIN_DURATION if ad_tier == AD_TIER_PREMIUM else None),
            created_at=now,
            expires_at=now + LISTING_DURATION,
        )
        db.session.add(listing)
        db.session.flush()  # 取 listing.id
        db.session.commit()

        # 广播（commit 后发，避免事务回滚后仍残留通知）
        if ad_tier > 0:
            cls._broadcast(listing, player.nickname)

        fee_desc = f"扣除手续费{total_fee}银两"
        return True, f"上架成功，{fee_desc}"

    # ------------------------------------------------------------------
    # 购买
    # ------------------------------------------------------------------
    @classmethod
    def buy_listing(cls, player, listing_id, buy_quantity=1):
        """购买挂单（可部分购买可堆叠物品）。返回 (ok, msg)。"""
        try:
            buy_quantity = int(buy_quantity)
        except (TypeError, ValueError):
            buy_quantity = 1
        if buy_quantity < 1:
            buy_quantity = 1

        listing = cls.get_listing(listing_id)
        if not listing:
            return False, "挂单不存在"
        if listing.status not in ('active', 'partial'):
            return False, "挂单已结束"
        if listing.seller_id == player.id:
            return False, "不能购买自己的挂单"

        # 装备恒为1
        if listing.equipment_instance_id:
            buy_quantity = 1
        buy_quantity = min(buy_quantity, listing.quantity)
        if buy_quantity < 1:
            return False, "库存不足"

        total_price = listing.unit_price * buy_quantity
        buyer_fee = max(1, int(total_price * BUYER_FEE_RATE))
        buyer_pays = total_price + buyer_fee
        if player.gold < buyer_pays:
            return False, f"银两不足，需{buyer_pays}（含5%手续费{buyer_fee}）"

        now = datetime.utcnow()

        # 转移物品/装备给买家（到手未绑定）
        if listing.equipment_instance_id:
            equip = EquipmentInstance.query.filter_by(
                instance_id=listing.equipment_instance_id).first()
            if not equip:
                return False, "装备实例丢失，请联系管理员"
            equip.player_id = player.id
            equip.is_bound = False
        else:
            DataService.add_item_to_inventory(
                player.id, listing.item_id, buy_quantity, is_bound=False)

        # 结算银两：卖家实收95%，买家扣全额
        seller = DataService.get_player_by_id(listing.seller_id)
        seller_receive = int(total_price * SELLER_RECEIVE_RATE)
        if seller:
            seller.gold += seller_receive
        player.gold -= buyer_pays

        # 更新挂单
        listing.quantity -= buy_quantity
        if listing.quantity <= 0:
            listing.status = 'sold'
            listing.sold_at = now
            listing.buyer_id = player.id
        else:
            listing.status = 'partial'

        # 通知卖家：有人买了你的挂单
        if seller:
            from services.social_service import SocialService
            qty_str = f'×{buy_quantity}' if buy_quantity > 1 else ''
            sold_out = '（已售罄）' if listing.status == 'sold' else ''
            SocialService.add_notification(
                seller,
                f"【集市】{player.nickname}购买了你的{listing.item_name}{qty_str}，"
                f"实收{seller_receive}银两{sold_out}",
                ntype='market')

        # 落成交记录（买家购买 = 卖家出售，同一笔双方各见一条视角）
        cls.record_transaction(listing, player, seller, buy_quantity,
                               total_price, buyer_fee, seller_receive)

        db.session.commit()
        return True, f"购买成功，花费{buyer_pays}银两"

    # ------------------------------------------------------------------
    # 成交流水
    # ------------------------------------------------------------------
    @classmethod
    def record_transaction(cls, listing, buyer, seller, buy_quantity,
                           total_price, buyer_fee, seller_receive):
        """记录一笔成交（随 buy_listing 的统一 commit 落库，这里只 add）。"""
        if not seller:
            return
        tx = MarketTransaction(
            listing_id=listing.id,
            buyer_id=buyer.id,
            seller_id=seller.id,
            item_name=listing.item_name,
            item_type=listing.item_type,
            category=listing.category,
            rarity=listing.rarity,
            quantity=buy_quantity,
            unit_price=listing.unit_price,
            total_price=total_price,
            buyer_fee=buyer_fee,
            seller_receive=seller_receive,
            is_equipment=bool(listing.equipment_instance_id),
        )
        db.session.add(tx)

    @classmethod
    def get_my_purchases(cls, player_id, limit=50):
        """我的购买（成交视角）。"""
        return (MarketTransaction.query
                .filter_by(buyer_id=player_id)
                .order_by(MarketTransaction.created_at.desc())
                .limit(limit).all())

    @classmethod
    def get_my_sales(cls, player_id, limit=50):
        """我的出售（成交视角，仅已成交）。"""
        return (MarketTransaction.query
                .filter_by(seller_id=player_id)
                .order_by(MarketTransaction.created_at.desc())
                .limit(limit).all())

    # ------------------------------------------------------------------
    # 取消挂单
    # ------------------------------------------------------------------
    @classmethod
    def cancel_listing(cls, player, listing_id):
        """取消挂单，剩余物品/装备退回卖家背包（不退费）。返回 (ok, msg)。"""
        listing = MarketListing.query.filter_by(
            id=listing_id, seller_id=player.id).first()
        if not listing:
            return False, "挂单不存在或不属于你"
        if listing.status not in ('active', 'partial'):
            return False, "挂单已结束，无法取消"

        cls._return_to_seller(listing)
        listing.status = 'cancelled'
        db.session.commit()
        return True, "挂单已取消，物品退回背包（手续费不退）"

    # ------------------------------------------------------------------
    # 过期（惰性状态机，由蓝图查询前调用）
    # ------------------------------------------------------------------
    @classmethod
    def expire_listings(cls):
        """过期挂单退回卖家。无返回，静默推进。"""
        now = datetime.utcnow()
        expired = MarketListing.query.filter(
            MarketListing.expires_at <= now,
            MarketListing.status.in_(['active', 'partial']),
        ).all()
        if not expired:
            return
        for listing in expired:
            cls._return_to_seller(listing)
            listing.status = 'expired'
        db.session.commit()

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------
    @classmethod
    def _return_to_seller(cls, listing):
        """把挂单剩余数量退回卖家（force-add 不查容量，同 grant_lost_item）。"""
        if listing.equipment_instance_id:
            equip = EquipmentInstance.query.filter_by(
                instance_id=listing.equipment_instance_id).first()
            if equip:
                equip.player_id = listing.seller_id
                equip.is_bound = False
        else:
            DataService.add_item_to_inventory(
                listing.seller_id, listing.item_id,
                listing.quantity, is_bound=False)

    @classmethod
    def _type_to_category(cls, itype):
        return TYPE_CATEGORY.get(itype, '其他')

    @classmethod
    def _format_listing(cls, listing):
        """挂单行 → 模板用 dict。"""
        seller = DataService.get_player_by_id(listing.seller_id)
        is_equipment = listing.equipment_instance_id is not None
        return {
            'id': listing.id,
            'item_name': listing.item_name,
            'item_type': listing.item_type,
            'category': listing.category,
            'rarity': listing.rarity,
            'quantity': listing.quantity,
            'unit_price': listing.unit_price,
            'total_price': listing.unit_price * listing.quantity,
            'is_equipment': is_equipment,
            'ad_tier': listing.ad_tier,
            'pin_until': listing.pin_until,
            'created_at': listing.created_at,
            'expires_at': listing.expires_at,
            'status': listing.status,
            'seller_id': listing.seller_id,
            'seller_name': seller.nickname if seller else '未知',
        }

    @classmethod
    def _broadcast(cls, listing, seller_name):
        """全服通知上架（内容 <512 字符，含购买链接）。"""
        try:
            url = f'/market/view/{listing.id}'
            prefix = '【置顶集市】' if listing.ad_tier == AD_TIER_PREMIUM else '【集市】'
            qty_str = f'×{listing.quantity}' if listing.quantity > 1 else ''
            # 截断保证总长 <512（预留链接后缀）
            max_name = 200
            name = listing.item_name
            if len(name) > max_name:
                name = name[:max_name] + '…'
            max_seller = 30
            if len(seller_name) > max_seller:
                seller_name = seller_name[:max_seller] + '…'
            content = (
                f'{prefix}{seller_name}上架了{name}{qty_str}，'
                f'单价{listing.unit_price}银两 '
                f'<a href="{url}">前往购买</a>'
            )
            if len(content) > 500:
                content = content[:500]
            DataService.broadcast_system(content)
        except Exception:
            # 广播失败不影响上架
            db.session.rollback()
