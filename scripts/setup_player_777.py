# -*- coding: utf-8 -*-
"""一次性配置玩家 777 (UID 5tqy7kpgom, 术士/吴)：
- 升到 60 级，按术士公式重算 6 项基础属性
- 荣誉拉到 60 级最高军衔档(大都督 200000)，更新军衔与 rank_attack
- VIP5 + 长期有效
- 装备：武器 + 饰品为 60 级神器(5星,强化+50)；5 件防具为 zhuque 套史诗(5星,强化+50)
- 满级满技能一级名将副将(太史慈,60级,3个技能各满级3)
- 设为设计号(is_designer=True)
- 银两拉满

可重复运行（覆盖式重置）。
"""
import sys
import io
from datetime import datetime, timedelta

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from app import create_app
from services import db
from services.data_service import DataService
from services.player_service import PlayerService
from services.lieutenant_service import LieutenantService, LIEUTENANT_SKILLS
from models.player import PlayerModel, EquipmentInstance, EquipmentSlot
from models.lieutenant import Lieutenant

TARGET_UID = '5tqy7kpgom'
TARGET_LEVEL = 60
TARGET_HONOR = 200000  # 大都督
ENHANCE_MAX = 50

# 术士 60 级神器装备模板（必须用 is_artifact: true 的模板，否则会违规把非神器模板强行标成神器）
WEAPON_TPL = 'chengying_jian'   # 承影剑(术士60级, is_artifact: true) —— 合法神器武器
ACCESSORY_TPL = 'heshi_bi'      # 和氏璧(60级, is_artifact: true) —— 合法神器饰品
# 朱雀套(术士60级防具)
SET_TEMPLATES = {
    'helmet': 'zhuque_helmet_59',
    'armor':  'zhuque_armor_58',
    'pants':  'zhuque_pants_57',
    'gloves': 'zhuque_gloves_56',
    'shoes':  'zhuque_shoes_55',
}

# 一级名将(最强档)：太史慈(术士职业，与玩家同职业便于技能学习)
NAMED_TIER = 1
NAMED_PINYIN = 'taishici'


def reset_player_stats(player, level):
    class_data = PlayerModel.CLASSES[player.player_class]
    b = class_data["base_stats"]
    lu = class_data["level_up_stats"]
    player.level = level
    player.max_health = b["max_health"] + lu["max_health"] * (level - 1)
    player.max_mana = b["max_mana"] + lu["max_mana"] * (level - 1)
    player.attack = b["attack"] + lu["attack"] * (level - 1)
    player.defense = b["defense"] + lu["defense"] * (level - 1)
    player.crit_rate = b["crit_rate"] + lu["crit_rate"] * (level - 1)
    player.dodge_rate = b["dodge_rate"] + lu["dodge_rate"] * (level - 1)
    player.health = player.max_health
    player.mana = player.max_mana
    player.experience = 0
    exp_table = DataService.get_game_config().get("level_exp_table", [])
    if level - 1 < len(exp_table):
        player.exp_to_next_level = exp_table[level - 1]


def make_equipment(player, template_id, slot, rarity):
    """生成指定品质 5 星装备并直接强化到 +50（按 enhance 公式重算 base_stats）。"""
    equip = DataService.create_equipment_instance(
        player.id, template_id, rarity, 5)
    if not equip:
        raise RuntimeError(f"装备模板生成失败: {template_id} ({rarity})")
    # 强制 5 星（_generate_extra_stats 每条附加属性独立随机，会反推出 4-5 星，这里统一拉满）
    equip.stars = 5
    equip.enhance_level = ENHANCE_MAX
    initial = equip.get_initial_stats()
    new_base = {}
    for stat, initial_value in initial.items():
        total_bonus = int(initial_value * 0.1 * ENHANCE_MAX)
        new_base[stat] = initial_value + total_bonus
    equip.set_base_stats(new_base)
    equip.is_bound = True
    equip.update_name()
    db.session.add(equip)
    db.session.flush()
    return equip


def equip_to_slot(player, slot_name, equip):
    slot = EquipmentSlot.query.filter_by(
        player_id=player.id, slot_name=slot_name).first()
    if not slot:
        return
    slot.equipment_instance_id = equip.id


def build_maxed_named_lieutenant(player):
    """创建满级满技能一级名将副将(太史慈)，绕过道具消耗直接构造。"""
    # 清掉该玩家已有的同名名将(便于重跑)
    for old in Lieutenant.query.filter_by(
            owner_id=player.id, name='太史慈').all():
        db.session.delete(old)
    db.session.flush()

    lt_info = LIEUTENANT_DATA_named[NAMED_TIER][NAMED_PINYIN]
    lt = Lieutenant(
        owner_id=player.id,
        name=lt_info['name'],
        gender=lt_info['gender'],
        class_type=lt_info['class_type'],
        quality=9,            # 满品质
        enlightenment=10,     # 满悟性
        reinforce=20,         # 满强化
        loyalty=100,
        lifespan=100,
        level=60,             # 满级
        experience=0,
        position='front',
        is_deployed=True,     # 出战
        skills_raw='[]',
        skill_slots=3,
        tier=NAMED_TIER,
        is_alive=True,
        base_max_health=lt_info.get('base_max_health'),
        base_max_mana=lt_info.get('base_max_mana'),
        base_attack=lt_info.get('base_attack'),
        base_defense=lt_info.get('base_defense'),
        base_crit_rate=lt_info.get('base_crit_rate'),
        base_dodge_rate=lt_info.get('base_dodge_rate'),
    )
    # 满技能：选 3 个可用技能各满级(3级)，手动填充(绕过技能书消耗)
    skills = []
    for sid, sdef in LIEUTENANT_SKILLS.items():
        if len(skills) >= lt.skill_slots:
            break
        class_req = sdef.get('class_required')
        if class_req and lt.class_type != class_req:
            continue
        entry = {'id': sid, 'name': sdef['name']}
        LieutenantService._fill_skill_fields(sdef, entry, sdef['max_level'])
        skills.append(entry)
    lt.skills = skills
    lt.current_health = lt.get_max_health()
    lt.current_mana = lt.get_max_mana()
    db.session.add(lt)
    db.session.flush()
    return lt


def main():
    global LIEUTENANT_DATA_named
    from services.lieutenant_service import LIEUTENANT_DATA
    LIEUTENANT_DATA_named = LIEUTENANT_DATA

    app = create_app()
    with app.app_context():
        player = PlayerModel.query.filter_by(player_uid=TARGET_UID).first()
        if not player:
            print(f"找不到 UID={TARGET_UID} 的玩家")
            sys.exit(1)
        print(f"配置前: {player.nickname} {player.player_class} lv{player.level} {player.country} designer={player.is_designer}")

        # 清空旧装备槽
        for s in EquipmentSlot.query.filter_by(player_id=player.id).all():
            s.equipment_instance_id = None

        reset_player_stats(player, TARGET_LEVEL)
        player.nickname = '777'
        player.player_class = '术士'
        player.country = '吴'

        # 荣誉 + 军衔
        player.honor = TARGET_HONOR
        PlayerService.update_military_rank(player)

        # VIP5 + 长期有效
        player.vip_level = 5
        player.vip_exp = 500
        player.vip_expire_time = datetime.utcnow() + timedelta(days=3650)

        # 设计号
        player.is_designer = True

        # 银两拉满
        player.gold = 999999999
        db.session.flush()

        # 装备：武器/饰品神器，5防具史诗
        weapon = make_equipment(player, WEAPON_TPL, 'weapon', '神器')
        equip_to_slot(player, 'weapon', weapon)
        acc = make_equipment(player, ACCESSORY_TPL, 'accessory', '神器')
        equip_to_slot(player, 'accessory', acc)
        for slot_name, tid in SET_TEMPLATES.items():
            e = make_equipment(player, tid, slot_name, '史诗')
            equip_to_slot(player, slot_name, e)

        # 满级满技能一级名将
        lt = build_maxed_named_lieutenant(player)

        db.session.commit()

        print(f"配置后: {player.nickname} {player.player_class} lv{player.level} {player.country} designer={player.is_designer} honor={player.honor} 军衔={player.military_rank}")
        print(f"  武器: {weapon.name} [{weapon.rarity} +{weapon.enhance_level}]")
        print(f"  饰品: {acc.name} [{acc.rarity} +{acc.enhance_level}]")
        for sn in ['helmet','armor','pants','gloves','shoes']:
            sl = EquipmentSlot.query.filter_by(player_id=player.id, slot_name=sn).first()
            eq = EquipmentInstance.query.get(sl.equipment_instance_id) if sl and sl.equipment_instance_id else None
            print(f"  {sn}: {eq.name if eq else '无'} [{eq.rarity if eq else '-'} +{eq.enhance_level if eq else 0}]")
        print(f"  副将: {lt.name} lv{lt.level} tier{lt.tier} 品质{lt.quality}/悟性{lt.enlightenment}/强化{lt.reinforce} 技能{[s['name']+'Lv'+str(s.get('level')) for s in lt.skills]} 出战={lt.is_deployed}")
        print(f"  银两: {player.gold}")


if __name__ == "__main__":
    main()
