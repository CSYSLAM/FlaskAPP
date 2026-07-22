# -*- coding: utf-8 -*-
"""验证集市售出通知:
   1) 新建一个买家测试号
   2) 让 777 上架 2 件背包装备
   3) 买家买下这 2 单
   4) 打印 777 的通知列表,确认收到售出提醒
用法: PYTHONPATH=/mnt/FlaskAPP venv/bin/python scripts/_test_market_notify.py
"""
import io, sys, time, uuid
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from app import create_app
from services import db
from services.player_service import PlayerService
from services.market_service import MarketService
from services.data_service import DataService
from models.player import PlayerModel, EquipmentInstance, EquipmentSlot, MarketListing

app = create_app()
with app.app_context():
    # ---- 卖家:777 ----
    seller = PlayerModel.query.filter_by(player_uid='5tqy7kpgom').first()
    if not seller:
        print("找不到 777 玩家"); sys.exit(1)
    print(f"卖家: {seller.nickname} (id={seller.id})")

    # ---- 买家:新测试号 ----
    uname = f"tb_{int(time.time())}"
    buyer, err = PlayerService.register(uname, "test1234", "测试买家", "术士", "男", "吴")
    if not buyer:
        print(f"买家创建失败: {err}"); sys.exit(1)
    buyer.gold = 2000000          # 充值以便购买
    db.session.commit()
    print(f"买家: {buyer.nickname} (id={buyer.id}, gold={buyer.gold})")

    # ---- 选 2 件可上架的背包装备(未绑定、未装备) ----
    equipped_ids = {s.equipment_instance_id for s in
                    EquipmentSlot.query.filter_by(player_id=seller.id).all()}
    bag_eq = (EquipmentInstance.query
              .filter_by(player_id=seller.id)
              .filter(EquipmentInstance.is_bound.is_(False))
              .all())
    candidates = [e for e in bag_eq if e.id not in equipped_ids]
    if len(candidates) < 2:
        print(f"777 可上架装备不足 2 件(仅 {len(candidates)} 件)"); sys.exit(1)

    chosen = candidates[:2]
    print(f"准备上架 777 的装备:")
    for e in chosen:
        print(f"   id={e.id} instance_id={e.instance_id} 名={e.name} rarity={e.rarity}")

    # ---- 上架 ----
    listings = []
    for e in chosen:
        ok, msg = MarketService.create_listing(
            seller, equipment_instance_id=e.instance_id, quantity=1, unit_price=1000)
        print(f"上架 {e.name}: ok={ok} msg={msg}")
        if ok:
            lst = MarketListing.query.filter_by(
                equipment_instance_id=e.instance_id, status='active').first()
            if lst:
                listings.append(lst.id)

    # ---- 买家逐一购买 ----
    for lid in listings:
        ok, msg = MarketService.buy_listing(buyer, lid)
        print(f"买家购买挂单#{lid}: ok={ok} msg={msg}")

    # ---- 复验 777 通知 ----
    seller2 = PlayerModel.query.filter_by(id=seller.id).first()
    notifs = seller2.notifications
    print(f"\n=== 777 当前通知({len(notifs)} 条) ===")
    for n in notifs:
        print(f"  [{n.get('type')}] {n.get('time')}  {n.get('message')}")

    market_notifs = [n for n in notifs if '集市' in (n.get('message') or '')]
    print(f"\n集市售出通知数量: {len(market_notifs)}")
    if len(market_notifs) >= 2:
        print("✅ 验证通过:777 已收到 2 条集市售出通知")
    else:
        print("❌ 验证失败:777 未收到预期的 2 条售出通知")
