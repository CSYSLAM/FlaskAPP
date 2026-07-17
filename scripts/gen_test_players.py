# -*- coding: utf-8 -*-
"""生成测试玩家：30/40/50/60 级 × 三职业（战士/术士/刺客）。

每个玩家：
- 等级拉到目标，按职业公式重算 6 项基础属性
- 荣誉拉到该等级对应最高军衔档，自动更新军衔与 rank_attack
- VIP5 + 长期有效 + vip_exp 500
- 5 星称号（prefix 龙 + suffix 传人/霸王/忠义之魂，按职业分配）
- 装备对应等级史诗武器 + 5 件史诗防具 + 1 件史诗饰品，全部 5 星、强化 +50（直接设等级并按公式重算 base_stats）
- 银两拉满（便于后续测试）

可重复运行：同名玩家已存在则覆盖式重置属性与装备。
"""
import sys
import io
from datetime import datetime, timedelta

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from app import create_app
from services import db
from services.data_service import DataService
from services.player_service import PlayerService
from models.player import PlayerModel, EquipmentInstance, EquipmentSlot

# 等级 → 军衔最高荣誉档（取该等级可达最高军衔的荣誉下限）
HONOR_BY_LEVEL = {
    30: 20000,   # 偏将
    40: 70000,   # 车骑将军
    50: 150000,  # 大司马
    60: 200000,  # 大都督
}

# 三职业的武器 / 防具套装 / 饰品模板（按等级）
LOADOUT = {
    "战士": {
        30: {"weapon": "kaishan_fu_30_zhanshi", "set": "leiting",  "accessory": "hongxue_jiezhi_34"},
        40: {"weapon": "pojun_fu_40_zhanshi",   "set": "jinggang", "accessory": "lingxi_xianglian_40"},
        50: {"weapon": "shanhe_fu_50_zhanshi",  "set": "bailian",  "accessory": "ziyu_xianglian_46"},
        60: {"weapon": "zhanyue_60_zhanshi",    "set": "qinglong", "accessory": "feicui_zhihuan_54"},
        "title_prefix": "prefix龙",
        "title_suffix": "suffix霸王",
    },
    "术士": {
        30: {"weapon": "duanshui_jian_30_shushi", "set": "riguang", "accessory": "hongxue_jiezhi_34"},
        40: {"weapon": "qingyun_jian_40_shushi",  "set": "yuanlv",  "accessory": "lingxi_xianglian_40"},
        50: {"weapon": "feifeng_jian_50_shushi",  "set": "jinxiu",  "accessory": "ziyu_xianglian_46"},
        60: {"weapon": "qixing_longyuan_60_shushi","set": "zhuque", "accessory": "feicui_zhihuan_54"},
        "title_prefix": "prefix龙",
        "title_suffix": "suffix传人",
    },
    "刺客": {
        30: {"weapon": "qingyun_jian_30_cike", "set": "yese",   "accessory": "hongxue_jiezhi_34"},
        40: {"weapon": "jifengci_40_cike",     "set": "jifeng", "accessory": "lingxi_xianglian_40"},
        50: {"weapon": "hanbing_jian_50_cike", "set": "queling","accessory": "ziyu_xianglian_46"},
        60: {"weapon": "suipo_60_cike",        "set": "baihu",  "accessory": "feicui_zhihuan_54"},
        "title_prefix": "prefix龙",
        "title_suffix": "suffix忠义之魂",
    },
}

# 防具套装 → 5 件模板（helmet/armor/pants/gloves/shoes），来自 CraftingService.SET_DEFINITIONS
SET_TEMPLATES = {
    "leiting":  ["leiting_helmet_29",  "leiting_armor_28",  "leiting_pants_27",  "leiting_gloves_26",  "leiting_shoes_25"],
    "riguang":  ["riguang_helmet_29",  "riguang_armor_28",  "riguang_pants_27",  "riguang_gloves_26",  "riguang_shoes_25"],
    "yese":     ["yese_helmet_29",     "yese_armor_28",     "yese_pants_27",     "yese_gloves_26",     "yese_shoes_25"],
    "jinggang": ["jinggang_helmet_39", "jinggang_armor_38", "jinggang_pants_37", "jinggang_gloves_36", "jinggang_shoes_35"],
    "yuanlv":   ["yuanlv_helmet_39",   "yuanlv_armor_38",   "yuanlv_pants_37",   "yuanlv_gloves_36",   "yuanlv_shoes_35"],
    "jifeng":   ["jifeng_helmet_39",   "jifeng_armor_38",   "jifeng_pants_37",   "jifeng_gloves_36",   "jifeng_shoes_35"],
    "bailian":  ["bailian_helmet_49",  "bailian_armor_48",  "bailian_pants_47",  "bailian_gloves_46",  "bailian_shoes_45"],
    "jinxiu":   ["jinxiu_helmet_49",   "jinxiu_armor_48",   "jinxiu_pants_47",   "jinxiu_gloves_46",   "jinxiu_shoes_45"],
    "queling":  ["queling_helmet_49",  "queling_armor_48",  "queling_pants_47",  "queling_gloves_46",  "queling_shoes_45"],
    "qinglong": ["qinglong_helmet_59", "qinglong_armor_58", "qinglong_pants_57", "qinglong_gloves_56", "qinglong_shoes_55"],
    "zhuque":   ["zhuque_helmet_59",   "zhuque_armor_58",   "zhuque_pants_57",   "zhuque_gloves_56",   "zhuque_shoes_55"],
    "baihu":    ["baihu_helmet_59",    "baihu_armor_58",    "baihu_pants_57",    "baihu_gloves_56",    "baihu_shoes_55"],
}

ENHANCE_MAX = 50
PASSWORD = "test123456"


def reset_player_stats(player, level):
    """按职业公式重算 6 项基础属性，设等级与经验。"""
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


def make_enhanced_equipment(player, template_id, slot):
    """生成史诗 5 星装备并直接强化到 +50（按 enhance 公式重算 base_stats）。"""
    equip = DataService.create_equipment_instance(
        player.id, template_id, "史诗", 5)
    if not equip:
        return None
    # 直接设强化等级并按 equipment_service.enhance 的公式重算 base_stats
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
    # 旧装备直接丢弃（测试玩家不保留旧装备）
    slot.equipment_instance_id = equip.id


def build_player(username, nickname, player_class, level, country="魏"):
    cfg = LOADOUT[player_class][level]
    title_cfg = LOADOUT[player_class]  # title_prefix/suffix 在职业层
    # 已存在则复用，否则注册
    player = PlayerModel.query.filter_by(username=username).first()
    if player:
        # 清空旧装备槽
        for s in EquipmentSlot.query.filter_by(player_id=player.id).all():
            s.equipment_instance_id = None
        # 若旧玩家缺 player_uid（旧版 register 未生成），补上
        if not player.player_uid:
            import random
            import string
            while True:
                uid = ''.join(random.choices(string.digits + string.ascii_lowercase, k=10))
                if not PlayerModel.query.filter_by(player_uid=uid).first():
                    player.player_uid = uid
                    break
    else:
        player, err = PlayerService.register(
            username, PASSWORD, nickname, player_class, country=country)
        if not player:
            raise RuntimeError(f"注册失败 {username}: {err}")
        # PlayerService.register 不生成 player_uid，这里补上（10位小写字母数字）
        import random
        import string
        while True:
            uid = ''.join(random.choices(string.digits + string.ascii_lowercase, k=10))
            if not PlayerModel.query.filter_by(player_uid=uid).first():
                break
        player.player_uid = uid

    reset_player_stats(player, level)
    player.nickname = nickname
    player.player_class = player_class
    player.country = country

    # 荣誉 + 军衔
    player.honor = HONOR_BY_LEVEL[level]
    PlayerService.update_military_rank(player)

    # VIP5 + 长期有效
    player.vip_level = 5
    player.vip_exp = 500
    player.vip_expire_time = datetime.utcnow() + timedelta(days=3650)

    # 5 星称号
    player.title_prefix_id = title_cfg["title_prefix"]
    player.title_suffix_id = title_cfg["title_suffix"]
    # 确保拥有该称号
    owned = player.owned_titles
    for tid in (title_cfg["title_prefix"], title_cfg["title_suffix"]):
        if tid not in owned:
            owned.append(tid)
    player.owned_titles = owned

    # 银两拉满
    player.gold = 999999999

    db.session.flush()

    # 装备：武器 + 5 防具 + 饰品
    weapon = make_enhanced_equipment(player, cfg["weapon"], "weapon")
    equip_to_slot(player, "weapon", weapon)
    set_tpls = SET_TEMPLATES[cfg["set"]]
    for slot_name, tid in zip(
            ["helmet", "armor", "pants", "gloves", "shoes"], set_tpls):
        e = make_enhanced_equipment(player, tid, slot_name)
        equip_to_slot(player, slot_name, e)
    acc = make_enhanced_equipment(player, cfg["accessory"], "accessory")
    equip_to_slot(player, "accessory", acc)

    db.session.commit()
    return player


def main():
    app = create_app()
    with app.app_context():
        players = []
        plan = [
            ("test_zhan30", "测试战士30", "战士", 30),
            ("test_zhan40", "测试战士40", "战士", 40),
            ("test_zhan50", "测试战士50", "战士", 50),
            ("test_zhan60", "测试战士60", "战士", 60),
            ("test_shu30", "测试术士30", "术士", 30),
            ("test_shu40", "测试术士40", "术士", 40),
            ("test_shu50", "测试术士50", "术士", 50),
            ("test_shu60", "测试术士60", "术士", 60),
            ("test_ci30",  "测试刺客30", "刺客", 30),
            ("test_ci40",  "测试刺客40", "刺客", 40),
            ("test_ci50",  "测试刺客50", "刺客", 50),
            ("test_ci60",  "测试刺客60", "刺客", 60),
        ]
        for username, nickname, cls, lv in plan:
            p = build_player(username, nickname, cls, lv)
            players.append(p)
            print(f"[OK] {username} ({cls} lv{lv}) UID={p.player_uid} 军衔={p.military_rank}")

        print(f"\n共生成 {len(players)} 个测试玩家")
        # 输出汇总供生成 md 用
        print("\n===SUMMARY===")
        for p in players:
            print(f"{p.username}|{p.nickname}|{p.player_class}|{p.level}|{p.player_uid}|{p.military_rank}|{p.honor}|VIP{p.vip_level}|{p.title_prefix_id}|{p.title_suffix_id}")


if __name__ == "__main__":
    main()
