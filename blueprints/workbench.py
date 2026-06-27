from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from services import db
from services.data_service import DataService
from services.player_service import PlayerService
from models.player import PlayerModel
import json
import os
import random as _random

workbench_bp = Blueprint('workbench', __name__)

# ─── Equipment Sets Directory ───
EQUIPMENT_SETS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'equipment_sets')

SLOT_CHOICES = ['weapon', 'helmet', 'armor', 'gloves', 'pants', 'shoes', 'accessory']
SLOT_NAMES = {'weapon': '武器', 'helmet': '头盔', 'armor': '铠甲', 'gloves': '手套', 'pants': '裤子', 'shoes': '鞋子', 'accessory': '饰品'}
CLASS_CHOICES_EQ = [None, '战士', '术士', '刺客']
STAT_KEYS = ['attack', 'defense', 'max_health', 'max_mana', 'crit_rate', 'dodge_rate']
STAT_NAMES = {'attack': '攻击', 'defense': '防御', 'max_health': '生命上限', 'max_mana': '魔法上限', 'crit_rate': '暴击率', 'dodge_rate': '闪避率'}
RARITY_NAMES = ["普通", "精良", "卓越", "史诗", "神器"]

# ─── Monster Design Constants ───
MONSTER_DATA_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'monsters.json')
COPY_MONSTER_DATA_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'copy_monsters.json')
MONSTER_STAT_KEYS = ['health', 'mana', 'attack', 'defense', 'crit_rate', 'dodge_rate']
MONSTER_STAT_NAMES = {
    'health': '生命值', 'mana': '魔法值', 'attack': '攻击力',
    'defense': '防御力', 'crit_rate': '暴击率', 'dodge_rate': '闪避率'
}
MONSTER_TYPE_CHOICES = ['world', 'copy']  # 世界怪物 / 副本怪物
MONSTER_TYPE_NAMES = {'world': '世界怪物', 'copy': '副本怪物'}
RARITY_WEIGHT_KEYS = ['common', 'uncommon', 'rare', 'epic', 'legendary']
RARITY_WEIGHT_NAMES = {
    'common': '普通', 'uncommon': '精良', 'rare': '卓越',
    'epic': '史诗', 'legendary': '神器'
}

# ─── Item Design Constants ───
ITEM_DATA_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'items.json')
ITEM_TYPE_CHOICES = ['material', 'potion', 'consumable', 'chest', 'other', 'vip', 'quest', 'equipment', 'item']
ITEM_TYPE_NAMES = {
    'material': '材料', 'potion': '药水', 'consumable': '消耗品', 'chest': '宝箱',
    'other': '其他', 'vip': 'VIP', 'quest': '任务', 'equipment': '装备', 'item': '物品'
}
ITEM_CURRENCY_CHOICES = [None, 'yuanbao', 'jinzu']
ITEM_CURRENCY_NAMES = {None: '银两', 'yuanbao': '元宝', 'jinzu': '金珠'}
# usage_effect 所有可能的键
USAGE_EFFECT_KEYS = [
    'stat_changes', 'stat_changes_rng', 'effect_descriptions', 'temp_effects',
    'grant_title', 'grant_gold', 'grant_item', 'random_one_of', 'random_items',
    'item_changes', 'equipment_generators', 'generate_equipment', 'special',
    'vip_days', 'restore_vitality', 'expand_backpack', 'expand_warehouse',
    'grant_lieutenant', 'random_soul', 'peace_status',
]
USAGE_EFFECT_NAMES = {
    'stat_changes': '属性变化', 'stat_changes_rng': '随机属性变化', 'effect_descriptions': '效果描述',
    'temp_effects': '临时效果', 'grant_title': '授予称号', 'grant_gold': '给予银两',
    'grant_item': '给予物品', 'random_one_of': '随机选一', 'random_items': '随机物品',
    'item_changes': '物品变动', 'equipment_generators': '装备生成器', 'generate_equipment': '生成装备',
    'special': '特殊效果', 'vip_days': 'VIP天数', 'restore_vitality': '恢复活力',
    'expand_backpack': '扩展背包', 'expand_warehouse': '扩展仓库',
    'grant_lieutenant': '授予副将', 'random_soul': '随机魂魄', 'peace_status': '免战状态',
}
# stat_changes / stat_changes_rng 可修改的属性
STAT_CHANGE_KEYS = [
    'health', 'mana', 'experience', 'gold', 'honor', 'yuanbao', 'jinzu',
    'pill_attack', 'pill_defense', 'pill_max_health', 'pill_max_mana',
    'blood_reserve', 'mana_reserve',
]
STAT_CHANGE_NAMES = {
    'health': '生命', 'mana': '魔法', 'experience': '经验', 'gold': '银两',
    'honor': '荣誉', 'yuanbao': '元宝', 'jinzu': '金珠',
    'pill_attack': '攻击丹', 'pill_defense': '防御丹', 'pill_max_health': '生命丹',
    'pill_max_mana': '魔法丹', 'blood_reserve': '血瓶储备', 'mana_reserve': '蓝瓶储备',
}


def _find_player(target_id):
    """查找玩家：支持 player_uid > username > 数字 id"""
    if not target_id:
        return None
    # 10位字母数字组合 = player_uid
    if len(target_id) == 10 and any(c.isalpha() for c in target_id):
        return DataService.get_player_by_uid(target_id)
    # 纯数字 = 数据库 id
    if target_id.isdigit():
        return DataService.get_player_by_id(int(target_id))
    # 其他 = username
    return DataService.get_player_by_username(target_id)


def _require_designer():
    if not current_user.is_designer:
        flash("无权访问工作台")
        return False
    return True


# --- Index ---

@workbench_bp.route("/")
@login_required
def index():
    if not _require_designer():
        return redirect(url_for('game.scene'))
    return render_template("workbench/index.html")


# --- Edit Player ---

STAT_INT_FIELDS = [
    ('attack', '基础攻击'),
    ('defense', '基础防御'),
    ('max_health', '基础生命上限'),
    ('max_mana', '基础魔法上限'),
]

STAT_FLOAT_FIELDS = [
    ('crit_rate', '基础暴击率'),
    ('dodge_rate', '基础闪避率'),
]

PILL_FIELDS = [
    ('pill_attack', '丹药攻击'),
    ('pill_defense', '丹药防御'),
    ('pill_max_health', '丹药生命'),
    ('pill_max_mana', '丹药魔法'),
]

ACCOUNT_INT_FIELDS = [
    ('level', '等级'),
    ('experience', '经验值'),
    ('gold', '银两'),
    ('yuanbao', '元宝'),
    ('jinzu', '金珠'),
    ('vip_level', 'VIP等级'),
    ('vip_exp', 'VIP经验'),
    ('honor', '荣誉'),
    ('rank_attack', '军衔攻击加成'),
    ('charm', '魅力值'),
]

ACCOUNT_STR_FIELDS = [
    ('military_rank', '军衔'),
    ('player_class', '职业'),
    ('country', '国家'),
]

CLASS_CHOICES = ['战士', '术士', '刺客']
COUNTRY_CHOICES = ['魏', '蜀', '吴', '群雄']
RANK_CHOICES = [
    '士兵', '列兵', '下士', '中士', '上士', '军士', '尉官', '校官', '裨将', '偏将', '副将', '上将'
]


@workbench_bp.route("/edit_player", methods=["GET", "POST"])
@login_required
def edit_player():
    if not _require_designer():
        return redirect(url_for('game.scene'))

    target = None
    fields = {}

    # Determine target player
    if request.method == "POST":
        target_id = request.form.get("target_id", "").strip()
        if target_id:
            target = _find_player(target_id)
            if not target:
                flash("找不到该玩家")

    if target:
        # Collect current values for display
        for field_id, label in (STAT_INT_FIELDS + STAT_FLOAT_FIELDS +
                                 PILL_FIELDS + ACCOUNT_INT_FIELDS):
            fields[field_id] = {'label': label, 'value': getattr(target, field_id), 'type': 'number'}
        for field_id, label in ACCOUNT_STR_FIELDS:
            fields[field_id] = {'label': label, 'value': getattr(target, field_id), 'type': 'text'}
        fields['is_designer'] = {'label': '是否设计师', 'value': target.is_designer, 'type': 'bool'}

        # Apply changes
        if request.form.get("save"):
            changed = False
            for field_id, _ in (STAT_INT_FIELDS + PILL_FIELDS + ACCOUNT_INT_FIELDS):
                val = request.form.get(field_id, "").strip()
                if val != "":
                    try:
                        setattr(target, field_id, int(val))
                        changed = True
                    except ValueError:
                        flash(f"{field_id} 必须是整数")
            for field_id, _ in STAT_FLOAT_FIELDS:
                val = request.form.get(field_id, "").strip()
                if val != "":
                    try:
                        setattr(target, field_id, float(val))
                        changed = True
                    except ValueError:
                        flash(f"{field_id} 必须是数字")
            for field_id, _ in ACCOUNT_STR_FIELDS:
                val = request.form.get(field_id, "").strip()
                if val != "":
                    setattr(target, field_id, val)
                    changed = True
            is_designer_val = request.form.get("is_designer")
            if is_designer_val is not None and bool(is_designer_val) != target.is_designer:
                target.is_designer = bool(is_designer_val)
                changed = True

            if changed:
                # If level changed, recalculate base stats from class formula
                new_level = request.form.get("level", "").strip()
                if new_level:
                    try:
                        new_level = int(new_level)
                        class_data = PlayerModel.CLASSES.get(target.player_class)
                        if class_data:
                            base = class_data["base_stats"]
                            lvl_up = class_data["level_up_stats"]
                            target.attack = base["attack"] + lvl_up["attack"] * (new_level - 1)
                            target.defense = base["defense"] + lvl_up["defense"] * (new_level - 1)
                            target.max_health = base["max_health"] + lvl_up["max_health"] * (new_level - 1)
                            target.max_mana = base["max_mana"] + lvl_up["max_mana"] * (new_level - 1)
                            target.crit_rate = base["crit_rate"] + lvl_up["crit_rate"] * (new_level - 1)
                            target.dodge_rate = base["dodge_rate"] + lvl_up["dodge_rate"] * (new_level - 1)
                    except ValueError:
                        pass

                db.session.commit()
                flash(f"玩家 {target.nickname}(ID:{target.id}) 属性已更新")
                # Re-read values
                target = DataService.get_player_by_id(target.id)
                fields = {}
                for field_id, label in (STAT_INT_FIELDS + STAT_FLOAT_FIELDS +
                                         PILL_FIELDS + ACCOUNT_INT_FIELDS):
                    fields[field_id] = {'label': label, 'value': getattr(target, field_id), 'type': 'number'}
                for field_id, label in ACCOUNT_STR_FIELDS:
                    fields[field_id] = {'label': label, 'value': getattr(target, field_id), 'type': 'text'}
                fields['is_designer'] = {'label': '是否设计师', 'value': target.is_designer, 'type': 'bool'}

    return render_template("workbench/edit_player.html",
                           target=target,
                           fields=fields,
                           class_choices=CLASS_CHOICES,
                           country_choices=COUNTRY_CHOICES,
                           rank_choices=RANK_CHOICES)


# --- View Player Details ---

@workbench_bp.route("/view_player", methods=["GET", "POST"])
@login_required
def view_player():
    if not _require_designer():
        return redirect(url_for('game.scene'))

    target = None
    details = {}

    if request.method == "POST":
        target_id = request.form.get("target_id", "").strip()
        if target_id:
            target = _find_player(target_id)
            if not target:
                flash("找不到该玩家")

    if target:
        # Compute detailed stat breakdown using PlayerService formulas
        from services.title_service import TitleService
        from services.social_service import SocialService
        from services.vip_service import VipService
        from models.lieutenant import Lieutenant

        passive = target.get_passive_bonuses()
        title_bonuses = TitleService.get_title_bonuses(target)

        # --- Attack breakdown ---
        base_atk = target.attack
        equip_atk = PlayerService._get_equipment_stat_sum(target, "attack")
        pill_atk = target.pill_attack
        flat_atk, rate_atk = DataService.get_temp_stat_bonus(target.id, "attack")
        rank_atk = target.rank_attack
        passive_atk_rate = passive.get('attack', 0)
        title_atk = title_bonuses.get('attack', 0)
        lt_atk_rate = PlayerService._get_lt_passive_bonus(target, 'attack')
        relation_atk = SocialService.get_online_relation_attack_bonus(target)
        vip_rate = VipService.get_stat_bonus_rate(target)
        atk_flat = base_atk + equip_atk + pill_atk + flat_atk + rank_atk + title_atk + relation_atk
        atk_rate = 1 + rate_atk + passive_atk_rate + lt_atk_rate + vip_rate
        atk_result = int(atk_flat * atk_rate)

        details['attack'] = {
            'name': '有效攻击力',
            'flat_parts': [
                ('基础攻击', base_atk),
                ('装备加成', equip_atk),
                ('丹药加成', pill_atk),
                ('临时BUFF(flat)', flat_atk),
                ('军衔加成', rank_atk),
                ('称号加成', title_atk),
                ('红颜/知己/结婚', relation_atk),
            ],
            'rate_parts': [
                ('临时BUFF(rate)', rate_atk),
                ('被动技能', passive_atk_rate),
                ('副将加成', lt_atk_rate),
                ('VIP加成', vip_rate),
            ],
            'flat_sum': atk_flat,
            'rate_sum': atk_rate,
            'result': atk_result,
        }

        # --- Defense breakdown ---
        base_def = target.defense
        equip_def = PlayerService._get_equipment_stat_sum(target, "defense")
        pill_def = target.pill_defense
        flat_def, rate_def = DataService.get_temp_stat_bonus(target.id, "defense")
        passive_def_rate = passive.get('defense', 0)
        title_def = title_bonuses.get('defense', 0)
        lt_def_rate = PlayerService._get_lt_passive_bonus(target, 'defense')
        def_flat = base_def + equip_def + pill_def + flat_def + title_def
        def_rate = 1 + rate_def + passive_def_rate + lt_def_rate + vip_rate
        def_result = int(def_flat * def_rate)

        details['defense'] = {
            'name': '有效防御力',
            'flat_parts': [
                ('基础防御', base_def),
                ('装备加成', equip_def),
                ('丹药加成', pill_def),
                ('临时BUFF(flat)', flat_def),
                ('称号加成', title_def),
            ],
            'rate_parts': [
                ('临时BUFF(rate)', rate_def),
                ('被动技能', passive_def_rate),
                ('副将加成', lt_def_rate),
                ('VIP加成', vip_rate),
            ],
            'flat_sum': def_flat,
            'rate_sum': def_rate,
            'result': def_result,
        }

        # --- Max Health breakdown ---
        base_hp = target.max_health
        equip_hp = PlayerService._get_equipment_stat_sum(target, "max_health")
        pill_hp = target.pill_max_health
        flat_hp, rate_hp = DataService.get_temp_stat_bonus(target.id, "max_health")
        passive_hp_rate = passive.get('max_health', 0)
        title_hp = title_bonuses.get('max_health', 0)
        lt_hp_rate = PlayerService._get_lt_passive_bonus(target, 'health')
        hp_flat = base_hp + equip_hp + pill_hp + flat_hp + title_hp
        hp_rate = 1 + rate_hp + passive_hp_rate + lt_hp_rate + vip_rate
        hp_result = int(hp_flat * hp_rate)

        details['max_health'] = {
            'name': '有效生命上限',
            'flat_parts': [
                ('基础生命', base_hp),
                ('装备加成', equip_hp),
                ('丹药加成', pill_hp),
                ('临时BUFF(flat)', flat_hp),
                ('称号加成', title_hp),
            ],
            'rate_parts': [
                ('临时BUFF(rate)', rate_hp),
                ('被动技能', passive_hp_rate),
                ('副将加成', lt_hp_rate),
                ('VIP加成', vip_rate),
            ],
            'flat_sum': hp_flat,
            'rate_sum': hp_rate,
            'result': hp_result,
        }

        # --- Max Mana breakdown ---
        base_mp = target.max_mana
        equip_mp = PlayerService._get_equipment_stat_sum(target, "max_mana")
        pill_mp = target.pill_max_mana
        flat_mp, rate_mp = DataService.get_temp_stat_bonus(target.id, "max_mana")
        passive_mp_rate = passive.get('max_mana', 0)
        title_mp = title_bonuses.get('max_mana', 0)
        lt_mp_rate = PlayerService._get_lt_passive_bonus(target, 'mana')
        mp_flat = base_mp + equip_mp + pill_mp + flat_mp + title_mp
        mp_rate = 1 + rate_mp + passive_mp_rate + lt_mp_rate + vip_rate
        mp_result = int(mp_flat * mp_rate)

        details['max_mana'] = {
            'name': '有效魔法上限',
            'flat_parts': [
                ('基础魔法', base_mp),
                ('装备加成', equip_mp),
                ('丹药加成', pill_mp),
                ('临时BUFF(flat)', flat_mp),
                ('称号加成', title_mp),
            ],
            'rate_parts': [
                ('临时BUFF(rate)', rate_mp),
                ('被动技能', passive_mp_rate),
                ('副将加成', lt_mp_rate),
                ('VIP加成', vip_rate),
            ],
            'flat_sum': mp_flat,
            'rate_sum': mp_rate,
            'result': mp_result,
        }

        # --- Crit Rate ---
        equip_crit = PlayerService._get_equipment_stat_sum(target, "crit_rate")
        title_crit = title_bonuses.get('crit_rate', 0)
        lt_crit = PlayerService._get_lt_passive_bonus(target, 'crit')
        details['crit_rate'] = {
            'name': '有效暴击率',
            'flat_parts': [
                ('基础暴击率', target.crit_rate),
                ('装备加成', equip_crit),
                ('被动技能', passive.get('crit_rate', 0)),
                ('称号加成', title_crit),
                ('副将加成', lt_crit),
            ],
            'rate_parts': [],
            'flat_sum': target.crit_rate + equip_crit + passive.get('crit_rate', 0) + title_crit + lt_crit,
            'rate_sum': 1,
            'result': round(target.crit_rate + equip_crit + passive.get('crit_rate', 0) + title_crit + lt_crit, 4),
        }

        # --- Dodge Rate ---
        equip_dodge = PlayerService._get_equipment_stat_sum(target, "dodge_rate")
        title_dodge = title_bonuses.get('dodge_rate', 0)
        lt_dodge = PlayerService._get_lt_passive_bonus(target, 'dodge')
        details['dodge_rate'] = {
            'name': '有效闪避率',
            'flat_parts': [
                ('基础闪避率', target.dodge_rate),
                ('装备加成', equip_dodge),
                ('被动技能', passive.get('dodge_rate', 0)),
                ('称号加成', title_dodge),
                ('副将加成', lt_dodge),
            ],
            'rate_parts': [],
            'flat_sum': target.dodge_rate + equip_dodge + passive.get('dodge_rate', 0) + title_dodge + lt_dodge,
            'rate_sum': 1,
            'result': round(target.dodge_rate + equip_dodge + passive.get('dodge_rate', 0) + title_dodge + lt_dodge, 4),
        }

    return render_template("workbench/view_player.html", target=target, details=details)


# --- Set Designer ---

@workbench_bp.route("/set_designer", methods=["GET", "POST"])
@login_required
def set_designer():
    if not _require_designer():
        return redirect(url_for('game.scene'))

    target = None

    if request.method == "POST":
        target_id = request.form.get("target_id", "").strip()
        if target_id:
            target = _find_player(target_id)
            if not target:
                flash("找不到该玩家")

    if target and request.form.get("toggle"):
        target.is_designer = not target.is_designer
        db.session.commit()
        status = "已成为设计师" if target.is_designer else "已取消设计师"
        flash(f"玩家 {target.nickname}(ID:{target.player_uid}) {status}")

    return render_template("workbench/set_designer.html", target=target)


# --- System Announcement ---

@workbench_bp.route("/announce", methods=["GET", "POST"])
@login_required
def announce():
    if not _require_designer():
        return redirect(url_for('game.scene'))

    if request.method == "POST":
        content = request.form.get("content", "").strip()
        if content:
            DataService.broadcast_system(content)
            flash("公告已发送")
        else:
            flash("公告内容不能为空")

    return render_template("workbench/announce.html")


# ═══════════════════════════════════════════════════════════
# Equipment Design System (装备设计系统)
# ═══════════════════════════════════════════════════════════

def _load_set_file(filename):
    """读取 equipment_sets 目录下的 JSON 文件"""
    filepath = os.path.join(EQUIPMENT_SETS_DIR, filename)
    if not os.path.exists(filepath):
        return None
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def _save_set_file(filename, data):
    """写入 equipment_sets 目录下的 JSON 文件"""
    filepath = os.path.join(EQUIPMENT_SETS_DIR, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _get_all_set_files():
    """列出所有 equipment_sets JSON 文件"""
    if not os.path.exists(EQUIPMENT_SETS_DIR):
        return []
    return sorted([f for f in os.listdir(EQUIPMENT_SETS_DIR) if f.endswith('.json')])

def _build_set_index():
    """构建套装索引：按 set_name 分组，返回 {set_name: [{template_id, name, slot, ...}, ...]}"""
    templates = DataService.get_equipment_templates()
    index = {}
    ungrouped = []
    for tid, tpl in templates.items():
        sname = tpl.get('set_name', '')
        item = {
            'template_id': tid,
            'name': tpl.get('name', tid),
            'slot': tpl.get('slot', ''),
            'level_required': tpl.get('level_required', 0),
            'class_required': tpl.get('class_required'),
            'is_artifact': tpl.get('is_artifact', False),
        }
        if not sname:
            ungrouped.append(item)
        else:
            if sname not in index:
                index[sname] = []
            index[sname].append(item)
    # 每组内按 slot 排序
    slot_order = {s: i for i, s in enumerate(SLOT_CHOICES)}
    for sname in index:
        index[sname].sort(key=lambda x: (slot_order.get(x['slot'], 99), x['level_required']))
    ungrouped.sort(key=lambda x: (slot_order.get(x['slot'], 99), x['level_required']))
    return index, ungrouped

def _find_template_file(template_id):
    """查找某个 template_id 所在的文件名"""
    for fname in _get_all_set_files():
        data = _load_set_file(fname)
        if data and template_id in data:
            return fname
    return None

def _simulate_generate(template_id, rarity=None, stars=None):
    """模拟生成一件装备，返回属性预览（不写入数据库）
    神器装备只能生成神器品质；非神器装备不能生成神器品质"""
    template = DataService.get_equipment_template(template_id)
    if not template:
        return None
    is_artifact = template.get('is_artifact', False)
    if is_artifact:
        rarity = "神器"
    else:
        if rarity is None:
            # 非神器随机时排除神器
            rarity = _random.choice(RARITY_NAMES[:-1])
        elif rarity == "神器":
            # 非神器装备不能生成神器品质
            rarity = "史诗"
    if stars is None:
        stars = _random.randint(1, 5)
    ratio = stars / 5
    base_stats = {stat: int(value * ratio) for stat, value in template.get("base_stats", {}).items()}
    extra_stats = DataService._generate_extra_stats(template, rarity, stars)
    name = f"【{rarity}】{template.get('name', template_id)}({stars}星)({template.get('level_required', 1)}级)"
    return {
        'template_id': template_id,
        'name': name,
        'rarity': rarity,
        'stars': stars,
        'slot': template.get('slot', ''),
        'level_required': template.get('level_required', 1),
        'class_required': template.get('class_required'),
        'is_artifact': is_artifact,
        'base_stats': base_stats,
        'extra_stats': extra_stats,
    }

def _simulate_generate_set(set_name, rarity=None, stars=None):
    """模拟生成一整套装备"""
    templates = DataService.get_equipment_templates()
    items = []
    for tid, tpl in templates.items():
        if tpl.get('set_name', '') == set_name:
            result = _simulate_generate(tid, rarity, stars)
            if result:
                items.append(result)
    items.sort(key=lambda x: (SLOT_CHOICES.index(x['slot']) if x['slot'] in SLOT_CHOICES else 99, x['level_required']))
    return items


# --- Equipment Design: Main Page ---

@workbench_bp.route("/equip_design")
@login_required
def equip_design():
    if not _require_designer():
        return redirect(url_for('game.scene'))
    set_index, ungrouped = _build_set_index()
    set_files = _get_all_set_files()
    return render_template("workbench/equip_design.html",
                           set_index=set_index,
                           ungrouped=ungrouped,
                           set_files=set_files,
                           slot_names=SLOT_NAMES,
                           stat_names=STAT_NAMES)


# --- Equipment Design: View Single Equipment ---

@workbench_bp.route("/equip_view/<template_id>")
@login_required
def equip_view(template_id):
    if not _require_designer():
        return redirect(url_for('game.scene'))
    template = DataService.get_equipment_template(template_id)
    if not template:
        flash("找不到该装备模板")
        return redirect(url_for('workbench.equip_design'))
    source_file = _find_template_file(template_id)
    return render_template("workbench/equip_view.html",
                           template_id=template_id,
                           template=template,
                           source_file=source_file,
                           slot_names=SLOT_NAMES,
                           stat_names=STAT_NAMES,
                           slot_choices=SLOT_CHOICES,
                           class_choices=CLASS_CHOICES_EQ,
                           stat_keys=STAT_KEYS)


# --- Equipment Design: Add Single Equipment ---

@workbench_bp.route("/equip_add", methods=["GET", "POST"])
@login_required
def equip_add():
    if not _require_designer():
        return redirect(url_for('game.scene'))

    if request.method == "POST":
        template_id = request.form.get("template_id", "").strip()
        target_file = request.form.get("target_file", "").strip()
        new_filename = request.form.get("new_filename", "").strip()
        file_mode = request.form.get("file_mode", "existing")

        if not template_id:
            flash("模板ID不能为空")
            return redirect(url_for('workbench.equip_add'))

        # 检查ID是否已存在
        if DataService.get_equipment_template(template_id):
            flash(f"模板ID '{template_id}' 已存在，请使用编辑功能或换一个ID")
            return redirect(url_for('workbench.equip_add'))

        if file_mode == "new":
            # 新建文件模式
            if not new_filename:
                flash("新文件名不能为空")
                return redirect(url_for('workbench.equip_add'))
            if not new_filename.endswith('.json'):
                new_filename += '.json'
            # 检查文件名格式：只允许小写字母、数字、下划线
            import re
            base_name = new_filename.replace('.json', '')
            if not re.match(r'^[a-z][a-z0-9_]*$', base_name):
                flash(f"文件名 '{base_name}' 格式不正确，只能使用小写英文、数字和下划线，且以字母开头。如: baopi_set")
                return redirect(url_for('workbench.equip_add'))
            # 检查文件名是否已存在
            if new_filename in _get_all_set_files():
                flash(f"文件 '{new_filename}' 已存在，请换个名字或选择已有文件")
                return redirect(url_for('workbench.equip_add'))
            # 检查文件名不能和 equipment_templates.json 冲突
            if new_filename == 'equipment_templates.json':
                flash("不能使用 'equipment_templates.json' 作为文件名，该文件为系统基础文件")
                return redirect(url_for('workbench.equip_add'))
            target_file = new_filename
        else:
            # 已有文件模式
            if not target_file:
                flash("必须选择目标文件")
                return redirect(url_for('workbench.equip_add'))
            if target_file not in _get_all_set_files():
                flash(f"文件 '{target_file}' 不存在于 equipment_sets 目录")
                return redirect(url_for('workbench.equip_add'))

        # 构建模板数据
        tpl = _build_template_from_form(request.form)
        if tpl is None:
            return redirect(url_for('workbench.equip_add'))

        # 写入文件
        if file_mode == "new":
            data = {template_id: tpl}
        else:
            data = _load_set_file(target_file)
            if data is None:
                data = {}
            data[template_id] = tpl
        _save_set_file(target_file, data)

        # 刷新缓存
        DataService._cache['equipment_templates'][template_id] = tpl

        flash(f"装备 '{tpl.get('name', template_id)}' 已添加到 {target_file}")
        return redirect(url_for('workbench.equip_view', template_id=template_id))

    # GET: 显示添加表单
    set_files = _get_all_set_files()
    return render_template("workbench/equip_add.html",
                           set_files=set_files,
                           slot_choices=SLOT_CHOICES,
                           slot_names=SLOT_NAMES,
                           class_choices=CLASS_CHOICES_EQ,
                           stat_keys=STAT_KEYS,
                           stat_names=STAT_NAMES)


# --- Equipment Design: Add Full Set ---

@workbench_bp.route("/equip_add_set", methods=["GET", "POST"])
@login_required
def equip_add_set():
    if not _require_designer():
        return redirect(url_for('game.scene'))

    if request.method == "POST":
        set_name = request.form.get("set_name", "").strip()
        target_file = request.form.get("target_file", "").strip()
        new_filename = request.form.get("new_filename", "").strip()
        file_mode = request.form.get("file_mode", "existing")
        class_required = request.form.get("set_class_required", "") or None
        is_artifact = request.form.get("set_is_artifact") == "1"
        is_bound = request.form.get("set_is_bound") == "1"
        base_level = int(request.form.get("set_base_level", 1))
        base_price = int(request.form.get("set_base_price", 0))
        description = request.form.get("set_description", "").strip()

        if not set_name:
            flash("套装名称不能为空")
            return redirect(url_for('workbench.equip_add_set'))

        # 处理目标文件
        if file_mode == "new":
            if not new_filename:
                # 从套装名自动生成，但需要转拼音或用英文
                flash("新建文件时请输入文件名，只能使用小写英文、数字和下划线，如: baopi_set")
                return redirect(url_for('workbench.equip_add_set'))
            if not new_filename.endswith('.json'):
                new_filename += '.json'
            # 检查文件名格式
            import re
            base_name = new_filename.replace('.json', '')
            if not re.match(r'^[a-z][a-z0-9_]*$', base_name):
                flash(f"文件名 '{base_name}' 格式不正确，只能使用小写英文、数字和下划线，且以字母开头。如: baopi_set")
                return redirect(url_for('workbench.equip_add_set'))
            if new_filename in _get_all_set_files():
                flash(f"文件 '{new_filename}' 已存在，请换个名字或选择已有文件")
                return redirect(url_for('workbench.equip_add_set'))
            if new_filename == 'equipment_templates.json':
                flash("不能使用 'equipment_templates.json' 作为文件名，该文件为系统基础文件")
                return redirect(url_for('workbench.equip_add_set'))
            target_file = new_filename
        else:
            if not target_file:
                target_file = set_name.lower().replace(' ', '_') + "_set.json"

        # 收集各部位数据
        items = {}
        for slot in SLOT_CHOICES:
            enabled = request.form.get(f"slot_{slot}_enabled")
            if not enabled:
                continue

            item_name = request.form.get(f"slot_{slot}_name", "").strip()
            if not item_name:
                flash(f"{SLOT_NAMES.get(slot, slot)}名称不能为空")
                return redirect(url_for('workbench.equip_add_set'))

            # 生成 template_id
            level_offset = int(request.form.get(f"slot_{slot}_level_offset", 0))
            item_level = base_level + level_offset
            tid_prefix = set_name.lower().replace(' ', '_')
            template_id = f"{tid_prefix}_{slot}_{item_level}"

            # 检查ID冲突
            if DataService.get_equipment_template(template_id):
                flash(f"模板ID '{template_id}' 已存在，请修改套装名或等级")
                return redirect(url_for('workbench.equip_add_set'))

            # 收集 base_stats 和 max_extra_stats
            base_stats = {}
            max_extra_stats = {}
            for sk in STAT_KEYS:
                bval = request.form.get(f"slot_{slot}_base_{sk}", "").strip()
                mval = request.form.get(f"slot_{slot}_max_{sk}", "").strip()
                if bval:
                    try:
                        base_stats[sk] = float(bval) if sk in ('crit_rate', 'dodge_rate') else int(bval)
                    except ValueError:
                        flash(f"{SLOT_NAMES.get(slot, slot)} 基础{STAT_NAMES.get(sk, sk)}格式错误")
                        return redirect(url_for('workbench.equip_add_set'))
                if mval:
                    try:
                        max_extra_stats[sk] = float(mval) if sk in ('crit_rate', 'dodge_rate') else int(mval)
                    except ValueError:
                        flash(f"{SLOT_NAMES.get(slot, slot)} 最大额外{STAT_NAMES.get(sk, sk)}格式错误")
                        return redirect(url_for('workbench.equip_add_set'))

            if not base_stats:
                flash(f"{SLOT_NAMES.get(slot, slot)}至少需要一个基础属性")
                return redirect(url_for('workbench.equip_add_set'))

            item_price = int(request.form.get(f"slot_{slot}_price", 0) or base_price)

            items[template_id] = {
                "name": item_name,
                "slot": slot,
                "set_name": set_name,
                "level_required": item_level,
                "class_required": class_required,
                "is_artifact": is_artifact,
                "is_bound": is_bound,
                "base_price": item_price,
                "base_stats": base_stats,
                "max_extra_stats": max_extra_stats,
            }
            if description:
                items[template_id]["description"] = description

        if not items:
            flash("至少需要启用一个部位")
            return redirect(url_for('workbench.equip_add_set'))

        # 写入文件
        data = _load_set_file(target_file) if target_file in _get_all_set_files() else {}
        if data is None:
            data = {}
        data.update(items)
        _save_set_file(target_file, data)

        # 刷新缓存
        for tid, tpl in items.items():
            DataService._cache['equipment_templates'][tid] = tpl

        flash(f"套装 '{set_name}' ({len(items)}件) 已添加到 {target_file}")
        return redirect(url_for('workbench.equip_design'))

    # GET: 显示添加套装表单
    set_files = _get_all_set_files()
    return render_template("workbench/equip_add_set.html",
                           set_files=set_files,
                           slot_choices=SLOT_CHOICES,
                           slot_names=SLOT_NAMES,
                           class_choices=CLASS_CHOICES_EQ,
                           stat_keys=STAT_KEYS,
                           stat_names=STAT_NAMES)


# --- Equipment Design: Edit Equipment ---

@workbench_bp.route("/equip_edit/<template_id>", methods=["GET", "POST"])
@login_required
def equip_edit(template_id):
    if not _require_designer():
        return redirect(url_for('game.scene'))

    template = DataService.get_equipment_template(template_id)
    if not template:
        flash("找不到该装备模板")
        return redirect(url_for('workbench.equip_design'))

    source_file = _find_template_file(template_id)
    if not source_file:
        flash("该装备不在 equipment_sets 目录中，无法编辑")
        return redirect(url_for('workbench.equip_view', template_id=template_id))

    if request.method == "POST":
        tpl = _build_template_from_form(request.form, existing=template)
        if tpl is None:
            return redirect(url_for('workbench.equip_edit', template_id=template_id))

        # 写入文件
        data = _load_set_file(source_file)
        if data is None:
            flash("读取文件失败")
            return redirect(url_for('workbench.equip_edit', template_id=template_id))
        data[template_id] = tpl
        _save_set_file(source_file, data)

        # 刷新缓存
        DataService._cache['equipment_templates'][template_id] = tpl

        flash(f"装备 '{tpl.get('name', template_id)}' 已更新")
        return redirect(url_for('workbench.equip_view', template_id=template_id))

    # GET: 显示编辑表单
    return render_template("workbench/equip_edit.html",
                           template_id=template_id,
                           template=template,
                           source_file=source_file,
                           slot_choices=SLOT_CHOICES,
                           slot_names=SLOT_NAMES,
                           class_choices=CLASS_CHOICES_EQ,
                           stat_keys=STAT_KEYS,
                           stat_names=STAT_NAMES)


# --- Equipment Design: Delete Equipment ---

@workbench_bp.route("/equip_delete/<template_id>", methods=["GET", "POST"])
@login_required
def equip_delete(template_id):
    if not _require_designer():
        return redirect(url_for('game.scene'))

    template = DataService.get_equipment_template(template_id)
    if not template:
        flash("找不到该装备模板")
        return redirect(url_for('workbench.equip_design'))

    source_file = _find_template_file(template_id)
    if not source_file:
        flash("该装备不在 equipment_sets 目录中，无法删除")
        return redirect(url_for('workbench.equip_view', template_id=template_id))

    if request.method == "POST":
        confirm = request.form.get("confirm")
        if confirm == "yes":
            data = _load_set_file(source_file)
            if data and template_id in data:
                del data[template_id]
                _save_set_file(source_file, data)
                # 刷新缓存
                DataService._cache['equipment_templates'].pop(template_id, None)
                flash(f"装备 '{template.get('name', template_id)}' 已从 {source_file} 删除")
            else:
                flash("文件中未找到该装备")
            return redirect(url_for('workbench.equip_design'))
        else:
            return redirect(url_for('workbench.equip_view', template_id=template_id))

    return render_template("workbench/equip_delete.html",
                           template_id=template_id,
                           template=template,
                           source_file=source_file)


# --- Equipment Design: Test Generate Single ---

@workbench_bp.route("/equip_test/<template_id>", methods=["GET", "POST"])
@login_required
def equip_test(template_id):
    if not _require_designer():
        return redirect(url_for('game.scene'))

    template = DataService.get_equipment_template(template_id)
    if not template:
        flash("找不到该装备模板")
        return redirect(url_for('workbench.equip_design'))

    results = []
    is_artifact = template.get('is_artifact', False)
    # 神器装备只能选神器品质；非神器装备不能选神器品质
    available_rarities = ["神器"] if is_artifact else [r for r in RARITY_NAMES if r != "神器"]

    if request.method == "POST":
        count = int(request.form.get("count", 1))
        rarity = request.form.get("rarity", "") or None
        stars = request.form.get("stars", "") or None
        if stars:
            stars = int(stars)
        count = min(count, 20)  # 最多20次
        for _ in range(count):
            result = _simulate_generate(template_id, rarity=rarity, stars=stars)
            if result:
                results.append(result)

    return render_template("workbench/equip_test.html",
                           template_id=template_id,
                           template=template,
                           results=results,
                           is_artifact=is_artifact,
                           available_rarities=available_rarities,
                           stat_names=STAT_NAMES,
                           slot_names=SLOT_NAMES)


# --- Equipment Design: Test Generate Full Set ---

@workbench_bp.route("/equip_test_set/<set_name>", methods=["GET", "POST"])
@login_required
def equip_test_set(set_name):
    if not _require_designer():
        return redirect(url_for('game.scene'))

    # 检查套装是否存在以及是否包含神器
    templates = DataService.get_equipment_templates()
    set_items_meta = []
    has_artifact = False
    has_non_artifact = False
    for tid, tpl in templates.items():
        if tpl.get('set_name', '') == set_name:
            set_items_meta.append({'template_id': tid, 'is_artifact': tpl.get('is_artifact', False)})
            if tpl.get('is_artifact', False):
                has_artifact = True
            else:
                has_non_artifact = True

    if not set_items_meta:
        flash(f"套装 '{set_name}' 不存在或无套装归属，无法测试套装生成。可使用单件装备的测试生成。")
        return redirect(url_for('workbench.equip_design'))

    # 神器套装只能选神器品质；非神器套装不能选神器品质
    is_all_artifact = has_artifact and not has_non_artifact
    available_rarities = ["神器"] if is_all_artifact else [r for r in RARITY_NAMES if r != "神器"]

    if request.method == "POST":
        rarity = request.form.get("rarity", "") or None
        stars = request.form.get("stars", "") or None
        if stars:
            stars = int(stars)
        items = _simulate_generate_set(set_name, rarity=rarity, stars=stars)
        if not items:
            flash(f"未找到套装 '{set_name}' 的装备")
            return redirect(url_for('workbench.equip_design'))
        return render_template("workbench/equip_test_set.html",
                               set_name=set_name,
                               items=items,
                               rarity=rarity,
                               stars=stars,
                               is_all_artifact=is_all_artifact,
                               available_rarities=available_rarities,
                               stat_names=STAT_NAMES,
                               slot_names=SLOT_NAMES)

    # GET: 显示选择表单
    return render_template("workbench/equip_test_set.html",
                           set_name=set_name,
                           items=None,
                           is_all_artifact=is_all_artifact,
                           available_rarities=available_rarities,
                           stat_names=STAT_NAMES,
                           slot_names=SLOT_NAMES)


# --- Equipment Design: View Set ---

@workbench_bp.route("/equip_set/<set_name>")
@login_required
def equip_set(set_name):
    if not _require_designer():
        return redirect(url_for('game.scene'))

    templates = DataService.get_equipment_templates()
    set_items = []
    for tid, tpl in templates.items():
        if tpl.get('set_name', '') == set_name:
            set_items.append({
                'template_id': tid,
                'name': tpl.get('name', tid),
                'slot': tpl.get('slot', ''),
                'level_required': tpl.get('level_required', 0),
                'class_required': tpl.get('class_required'),
                'is_artifact': tpl.get('is_artifact', False),
                'base_stats': tpl.get('base_stats', {}),
                'max_extra_stats': tpl.get('max_extra_stats', {}),
            })
    slot_order = {s: i for i, s in enumerate(SLOT_CHOICES)}
    set_items.sort(key=lambda x: (slot_order.get(x['slot'], 99), x['level_required']))

    return render_template("workbench/equip_set.html",
                           set_name=set_name,
                           set_items=set_items,
                           slot_names=SLOT_NAMES,
                           stat_names=STAT_NAMES)


# --- Equipment Design: View File ---

@workbench_bp.route("/equip_file/<filename>")
@login_required
def equip_file(filename):
    if not _require_designer():
        return redirect(url_for('game.scene'))

    data = _load_set_file(filename)
    if data is None:
        flash(f"文件 '{filename}' 不存在")
        return redirect(url_for('workbench.equip_design'))

    items = []
    for tid, tpl in data.items():
        items.append({
            'template_id': tid,
            'name': tpl.get('name', tid),
            'slot': tpl.get('slot', ''),
            'set_name': tpl.get('set_name', ''),
            'level_required': tpl.get('level_required', 0),
            'class_required': tpl.get('class_required'),
            'is_artifact': tpl.get('is_artifact', False),
        })
    slot_order = {s: i for i, s in enumerate(SLOT_CHOICES)}
    items.sort(key=lambda x: (slot_order.get(x['slot'], 99), x['level_required']))

    return render_template("workbench/equip_file.html",
                           filename=filename,
                           items=items,
                           slot_names=SLOT_NAMES)


# ─── Helper: Build Template from Form ───

def _build_template_from_form(form, existing=None):
    """从表单数据构建装备模板字典"""
    name = form.get("name", "").strip()
    if not name:
        flash("装备名称不能为空")
        return None

    slot = form.get("slot", "")
    if slot not in SLOT_CHOICES:
        flash("无效的装备部位")
        return None

    set_name = form.get("set_name", "").strip()
    level_required = int(form.get("level_required", 1))
    class_required = form.get("class_required", "") or None
    is_artifact = form.get("is_artifact") == "1"
    is_bound = form.get("is_bound") == "1"
    base_price = int(form.get("base_price", 0))
    description = form.get("description", "").strip()

    # 收集 base_stats
    base_stats = {}
    for sk in STAT_KEYS:
        val = form.get(f"base_{sk}", "").strip()
        if val:
            try:
                base_stats[sk] = float(val) if sk in ('crit_rate', 'dodge_rate') else int(val)
            except ValueError:
                flash(f"基础{STAT_NAMES.get(sk, sk)}格式错误")
                return None

    # 收集 max_extra_stats
    max_extra_stats = {}
    for sk in STAT_KEYS:
        val = form.get(f"max_{sk}", "").strip()
        if val:
            try:
                max_extra_stats[sk] = float(val) if sk in ('crit_rate', 'dodge_rate') else int(val)
            except ValueError:
                flash(f"最大额外{STAT_NAMES.get(sk, sk)}格式错误")
                return None

    if not base_stats:
        flash("至少需要一个基础属性")
        return None

    tpl = {
        "name": name,
        "slot": slot,
        "set_name": set_name,
        "level_required": level_required,
        "class_required": class_required,
        "is_artifact": is_artifact,
        "is_bound": is_bound,
        "base_stats": base_stats,
        "max_extra_stats": max_extra_stats,
    }
    if base_price:
        tpl["base_price"] = base_price
    if description:
        tpl["description"] = description

    return tpl


# ═══════════════════════════════════════════════════════════
# Monster Design System (怪物设计系统)
# ═══════════════════════════════════════════════════════════

def _load_monster_data():
    """读取 monsters.json"""
    if not os.path.exists(MONSTER_DATA_FILE):
        return {}
    with open(MONSTER_DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def _save_monster_data(data):
    """写入 monsters.json"""
    with open(MONSTER_DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _load_copy_monster_data():
    """读取 copy_monsters.json"""
    if not os.path.exists(COPY_MONSTER_DATA_FILE):
        return {}
    with open(COPY_MONSTER_DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def _save_copy_monster_data(data):
    """写入 copy_monsters.json"""
    with open(COPY_MONSTER_DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _build_monster_index():
    """构建怪物索引：按类型分组（世界怪物 / 副本怪物 / NPC），返回分组字典"""
    monsters = DataService.get_monsters()
    world_monsters = []
    copy_monsters = []
    npc_list = []
    for mid, m in monsters.items():
        item = {
            'monster_id': mid,
            'name': m.get('name', mid),
            'level': m.get('level', 0),
            'is_elite': m.get('is_elite', False),
            'is_divine_beast': m.get('is_divine_beast', False),
            'killable': m.get('killable', True),
            'is_copy': m.get('is_copy', False),
            'copy_only': m.get('copy_only', False),
        }
        if not m.get('killable', True):
            npc_list.append(item)
        elif m.get('is_copy', False) or m.get('copy_only', False):
            copy_monsters.append(item)
        else:
            world_monsters.append(item)
    # 排序
    world_monsters.sort(key=lambda x: (x['level'], x['monster_id']))
    copy_monsters.sort(key=lambda x: (x['level'], x['monster_id']))
    npc_list.sort(key=lambda x: (x['level'], x['monster_id']))
    return {
        'world': world_monsters,
        'dungeon': copy_monsters,
        'npc': npc_list,
    }

def _find_monster_source(mid):
    """查找怪物数据在哪个文件：monsters.json 或 copy_monsters.json"""
    monsters = _load_monster_data()
    if mid in monsters:
        return 'monsters.json'
    copy_monsters = _load_copy_monster_data()
    if mid in copy_monsters:
        return 'copy_monsters.json'
    return None

def _simulate_monster_battle(mid, player_level=1):
    """模拟怪物战斗：计算伤害/掉落预览（不写入数据库）"""
    m = DataService.get_monster(mid)
    if not m:
        return None
    from models.monster import Monster
    monster = Monster.from_dict(mid, m)
    result = {
        'monster_id': mid,
        'name': m.get('name', mid),
        'level': m.get('level', 0),
        'is_elite': m.get('is_elite', False),
        'is_divine_beast': m.get('is_divine_beast', False),
        'base_stats': m.get('base_stats', {}),
        'killable': m.get('killable', True),
        'loot_preview': None,
    }
    if m.get('killable', True):
        # 模拟掉落
        loot = monster.get_loot()
        equipment_result = None
        item_results = []
        if loot is not None:
            if isinstance(loot, tuple) and loot[0] == "item":
                item_results.append(loot[1])
            elif isinstance(loot, dict):
                equipment_result = loot
        # 额外尝试一次物品掉落（独立于装备掉落）
        for item_id, chance in m.get('drops', {}).get('items', {}).items():
            if _random.random() < chance:
                item_results.append(item_id)
        result['loot_preview'] = {
            'equipment': equipment_result,
            'dropped_items': item_results,
            'money': monster.get_money_drop(),
            'experience': monster.get_experience_drop(),
        }
        # 模拟伤害信息
        result['damage_preview'] = {
            'attack_power': monster.attack,
            'crit_rate': f"{monster.crit_rate * 100:.1f}%",
        }
    return result


# --- Monster Design: Main Page ---

@workbench_bp.route("/monster_design")
@login_required
def monster_design():
    if not _require_designer():
        return redirect(url_for('game.scene'))
    monster_index = _build_monster_index()
    return render_template("workbench/monster_design.html",
                           monster_index=monster_index)


# --- Monster Design: View Single Monster ---

@workbench_bp.route("/monster_view/<monster_id>")
@login_required
def monster_view(monster_id):
    if not _require_designer():
        return redirect(url_for('game.scene'))
    monster = DataService.get_monster(monster_id)
    if not monster:
        flash("找不到该怪物")
        return redirect(url_for('workbench.monster_design'))
    source_file = _find_monster_source(monster_id)

    # 计算实际品质权重（经过 _sanitize 后）
    from models.monster import Monster
    raw_rw = monster.get('drops', {}).get('equipment_drop', {}).get('rarity_weights', {})
    is_elite = monster.get('is_elite', False)
    sanitized_rw = Monster._sanitize_monster_rarity_weights(raw_rw, is_elite) or {}
    # 检查是否有被过滤的品质
    filtered_rarities = []
    if raw_rw and sanitized_rw:
        for rk in raw_rw:
            if rk not in sanitized_rw and raw_rw[rk] > 0:
                filtered_rarities.append(rk)
    # 计算世界boss复活时间
    respawn_desc = ''
    if monster.get('killable') and is_elite and not monster.get('is_copy') and not monster.get('copy_only'):
        from services.world_boss_service import WorldBossService
        rt = WorldBossService._get_respawn_time(monster_id, monster)
        respawn_desc = f'{rt}秒({rt // 60}分钟)'
        if monster.get('respawn_time'):
            respawn_desc += ' [数据自定义]'

    return render_template("workbench/monster_view.html",
                           monster_id=monster_id,
                           monster=monster,
                           source_file=source_file,
                           stat_names=MONSTER_STAT_NAMES,
                           rarity_weight_names=RARITY_WEIGHT_NAMES,
                           sanitized_rw=sanitized_rw,
                           filtered_rarities=filtered_rarities,
                           respawn_desc=respawn_desc)


# --- Monster Design: Add Monster ---

@workbench_bp.route("/monster_add", methods=["GET", "POST"])
@login_required
def monster_add():
    if not _require_designer():
        return redirect(url_for('game.scene'))

    if request.method == "POST":
        monster_id = request.form.get("monster_id", "").strip()
        if not monster_id:
            flash("怪物ID不能为空")
            return redirect(url_for('workbench.monster_add'))

        # 检查ID是否已存在
        if DataService.get_monster(monster_id):
            flash(f"怪物ID '{monster_id}' 已存在")
            return redirect(url_for('workbench.monster_add'))

        monster_data = _build_monster_from_form(request.form)
        if monster_data is None:
            return redirect(url_for('workbench.monster_add'))

        # 写入文件
        target_file = request.form.get("target_file", "monsters.json")
        if target_file == "copy_monsters.json":
            data = _load_copy_monster_data()
            if data is None:
                data = {}
            data[monster_id] = monster_data
            _save_copy_monster_data(data)
        else:
            data = _load_monster_data()
            if data is None:
                data = {}
            data[monster_id] = monster_data
            _save_monster_data(data)

        # 刷新缓存
        DataService._cache['monsters'][monster_id] = monster_data

        flash(f"怪物 '{monster_data.get('name', monster_id)}' 已添加到 {target_file}")
        return redirect(url_for('workbench.monster_view', monster_id=monster_id))

    # GET: 显示添加表单
    # 构建物品选择器数据
    item_choices, eq_choices, set_index = _build_picker_data()
    return render_template("workbench/monster_add.html",
                           stat_keys=MONSTER_STAT_KEYS,
                           stat_names=MONSTER_STAT_NAMES,
                           rarity_weight_keys=RARITY_WEIGHT_KEYS,
                           rarity_weight_names=RARITY_WEIGHT_NAMES,
                           item_choices=item_choices,
                           eq_choices=eq_choices,
                           set_index=set_index)


# --- Monster Design: Edit Monster ---

@workbench_bp.route("/monster_edit/<monster_id>", methods=["GET", "POST"])
@login_required
def monster_edit(monster_id):
    if not _require_designer():
        return redirect(url_for('game.scene'))

    monster = DataService.get_monster(monster_id)
    if not monster:
        flash("找不到该怪物")
        return redirect(url_for('workbench.monster_design'))

    source_file = _find_monster_source(monster_id)
    if not source_file:
        flash("找不到该怪物的数据文件")
        return redirect(url_for('workbench.monster_view', monster_id=monster_id))

    if request.method == "POST":
        monster_data = _build_monster_from_form(request.form, existing=monster)
        if monster_data is None:
            return redirect(url_for('workbench.monster_edit', monster_id=monster_id))

        # 写入文件
        if source_file == "copy_monsters.json":
            data = _load_copy_monster_data()
        else:
            data = _load_monster_data()
        if data is None:
            data = {}
        data[monster_id] = monster_data
        if source_file == "copy_monsters.json":
            _save_copy_monster_data(data)
        else:
            _save_monster_data(data)

        # 刷新缓存
        DataService._cache['monsters'][monster_id] = monster_data

        flash(f"怪物 '{monster_data.get('name', monster_id)}' 已更新")
        return redirect(url_for('workbench.monster_view', monster_id=monster_id))

    # GET: 显示编辑表单
    item_choices, eq_choices, set_index = _build_picker_data()
    return render_template("workbench/monster_edit.html",
                           monster_id=monster_id,
                           monster=monster,
                           source_file=source_file,
                           stat_keys=MONSTER_STAT_KEYS,
                           stat_names=MONSTER_STAT_NAMES,
                           rarity_weight_keys=RARITY_WEIGHT_KEYS,
                           rarity_weight_names=RARITY_WEIGHT_NAMES,
                           item_choices=item_choices,
                           eq_choices=eq_choices,
                           set_index=set_index)


# --- Monster Design: Delete Monster ---

@workbench_bp.route("/monster_delete/<monster_id>", methods=["GET", "POST"])
@login_required
def monster_delete(monster_id):
    if not _require_designer():
        return redirect(url_for('game.scene'))

    monster = DataService.get_monster(monster_id)
    if not monster:
        flash("找不到该怪物")
        return redirect(url_for('workbench.monster_design'))

    source_file = _find_monster_source(monster_id)
    if not source_file:
        flash("找不到该怪物的数据文件")
        return redirect(url_for('workbench.monster_view', monster_id=monster_id))

    if request.method == "POST":
        confirm = request.form.get("confirm")
        if confirm == "yes":
            if source_file == "copy_monsters.json":
                data = _load_copy_monster_data()
            else:
                data = _load_monster_data()
            if data and monster_id in data:
                del data[monster_id]
                if source_file == "copy_monsters.json":
                    _save_copy_monster_data(data)
                else:
                    _save_monster_data(data)
                # 刷新缓存
                DataService._cache['monsters'].pop(monster_id, None)
                flash(f"怪物 '{monster.get('name', monster_id)}' 已从 {source_file} 删除")
            else:
                flash("文件中未找到该怪物")
            return redirect(url_for('workbench.monster_design'))
        else:
            return redirect(url_for('workbench.monster_view', monster_id=monster_id))

    return render_template("workbench/monster_delete.html",
                           monster_id=monster_id,
                           monster=monster,
                           source_file=source_file)


# --- Monster Design: Test Battle/Loot ---

@workbench_bp.route("/monster_test/<monster_id>", methods=["GET", "POST"])
@login_required
def monster_test(monster_id):
    if not _require_designer():
        return redirect(url_for('game.scene'))

    monster = DataService.get_monster(monster_id)
    if not monster:
        flash("找不到该怪物")
        return redirect(url_for('workbench.monster_design'))

    results = []
    if request.method == "POST":
        count = int(request.form.get("count", 1))
        player_level = int(request.form.get("player_level", 1))
        count = min(count, 20)
        for _ in range(count):
            result = _simulate_monster_battle(monster_id, player_level)
            if result:
                results.append(result)

    return render_template("workbench/monster_test.html",
                           monster_id=monster_id,
                           monster=monster,
                           results=results,
                           stat_names=MONSTER_STAT_NAMES,
                           rarity_weight_names=RARITY_WEIGHT_NAMES)


# ─── Helper: Build Picker Data ───

def _build_picker_data():
    """构建选择器数据：物品列表、装备模板列表、套装索引"""
    all_items = DataService.get_items()
    item_choices = [{'id': iid, 'name': item.get('name', iid)} for iid, item in all_items.items()]

    all_eq_templates = DataService.get_equipment_templates()
    eq_choices = [{'id': tid, 'name': tpl.get('name', tid), 'level': tpl.get('level_required', 0),
                   'slot': tpl.get('slot', ''), 'set_name': tpl.get('set_name', ''),
                   'is_artifact': tpl.get('is_artifact', False)}
                  for tid, tpl in all_eq_templates.items()]

    # 构建套装索引: {set_name: {name, is_artifact, min_level, max_level, items: [{id, name, level, slot}]}}
    set_index = {}
    for tid, tpl in all_eq_templates.items():
        sname = tpl.get('set_name', '')
        if not sname:
            continue
        if sname not in set_index:
            set_index[sname] = {
                'name': sname,
                'is_artifact': tpl.get('is_artifact', False),
                'min_level': tpl.get('level_required', 999),
                'max_level': tpl.get('level_required', 0),
                'items': [],
            }
        lv = tpl.get('level_required', 0)
        entry = set_index[sname]
        entry['min_level'] = min(entry['min_level'], lv)
        entry['max_level'] = max(entry['max_level'], lv)
        entry['is_artifact'] = entry['is_artifact'] or tpl.get('is_artifact', False)
        entry['items'].append({
            'id': tid,
            'name': tpl.get('name', tid),
            'level': lv,
            'slot': tpl.get('slot', ''),
        })

    return item_choices, eq_choices, set_index


# ─── Helper: Build Monster from Form ───

def _build_monster_from_form(form, existing=None):
    """从表单数据构建怪物字典"""
    name = form.get("name", "").strip()
    if not name:
        flash("怪物名称不能为空")
        return None

    level = int(form.get("level", 1))
    is_elite = form.get("is_elite") == "1"
    killable = form.get("killable") == "1"
    immortal = form.get("immortal") == "1"
    is_divine_beast = form.get("is_divine_beast") == "1"
    description = form.get("description", "").strip()

    # respawn_time (精英/神兽复活秒数)
    respawn_time = int(form.get("respawn_time", 0) or 0)

    # base_stats
    base_stats = {}
    for sk in MONSTER_STAT_KEYS:
        val = form.get(f"base_{sk}", "").strip()
        if val:
            try:
                base_stats[sk] = float(val) if sk in ('crit_rate', 'dodge_rate') else int(val)
            except ValueError:
                flash(f"基础{MONSTER_STAT_NAMES.get(sk, sk)}格式错误")
                return None
    if not base_stats:
        flash("至少需要一个基础属性")
        return None

    # skills
    skills_str = form.get("skills", "").strip()
    skills = [s.strip() for s in skills_str.split(",") if s.strip()] if skills_str else []

    # drops - equipment_drop
    eq_drop_rate = float(form.get("eq_drop_rate", 0))
    eq_templates_str = form.get("eq_templates", "").strip()
    eq_templates = [t.strip() for t in eq_templates_str.split(",") if t.strip()] if eq_templates_str else []
    rarity_weights = {}
    for rk in RARITY_WEIGHT_KEYS:
        val = form.get(f"rw_{rk}", "").strip()
        if val:
            try:
                rarity_weights[rk] = int(val)
            except ValueError:
                flash(f"{RARITY_WEIGHT_NAMES.get(rk, rk)}权重格式错误")
                return None

    # 精英怪品质限制：非神兽精英不能有神器权重
    if is_elite and not is_divine_beast and rarity_weights.get('legendary', 0) > 0:
        rarity_weights['legendary'] = 0
        flash("非神兽精英怪不能设置神器品质权重，已自动归零")

    # drops - items
    items_str = form.get("drop_items", "").strip()
    drop_items = {}
    if items_str:
        for pair in items_str.split(","):
            pair = pair.strip()
            if ":" in pair:
                item_id, chance = pair.split(":", 1)
                try:
                    drop_items[item_id.strip()] = float(chance.strip())
                except ValueError:
                    flash(f"掉落物品 '{pair}' 格式错误，应为 item_id:概率")
                    return None

    # drops - money
    money_min = int(form.get("money_min", 0))
    money_max = int(form.get("money_max", 0))

    # drops - experience
    experience = int(form.get("experience", 0))

    # artifact (divine beast)
    artifact_template = form.get("artifact_template", "").strip() or None
    artifact_drop_rate = float(form.get("artifact_drop_rate", 0)) if artifact_template else 0

    # copy fields
    is_copy = form.get("is_copy") == "1"
    copy_only = form.get("copy_only") == "1"
    copy_dungeon_id = form.get("copy_dungeon_id", "").strip() or None
    copy_stage = form.get("copy_stage", "").strip() or None
    copy_final_boss = form.get("copy_final_boss") == "1"
    copy_role = form.get("copy_role", "").strip() or None

    # guaranteed_items
    gi_str = form.get("guaranteed_items", "").strip()
    guaranteed_items = [i.strip() for i in gi_str.split(",") if i.strip()] if gi_str else []

    monster_data = {
        "name": name,
        "level": level,
        "is_elite": is_elite,
        "killable": killable,
        "immortal": immortal,
        "description": description or name,
        "base_stats": base_stats,
        "skills": skills,
        "drops": {
            "equipment_drop": {
                "drop_rate": eq_drop_rate,
                "templates": eq_templates,
                "rarity_weights": rarity_weights,
            },
            "items": drop_items,
            "money": {
                "min": money_min,
                "max": money_max,
            },
            "experience": experience,
        },
        "is_divine_beast": is_divine_beast,
        "is_copy": is_copy,
        "copy_only": copy_only,
    }

    # Optional fields
    if artifact_template:
        monster_data["drops"]["equipment_drop"]["artifact_template"] = artifact_template
        monster_data["drops"]["equipment_drop"]["artifact_drop_rate"] = artifact_drop_rate
    if copy_dungeon_id:
        monster_data["copy_dungeon_id"] = copy_dungeon_id
    if copy_stage:
        monster_data["copy_stage"] = copy_stage
    if copy_final_boss:
        monster_data["copy_final_boss"] = True
    if copy_role:
        monster_data["copy_role"] = copy_role
    if guaranteed_items:
        monster_data["guaranteed_items"] = guaranteed_items
    if respawn_time > 0:
        monster_data["respawn_time"] = respawn_time
    monster_data["max_health"] = 100

    return monster_data


# ═══════════════════════════════════════════════════════════
# Item Design System (物品设计系统)
# ═══════════════════════════════════════════════════════════

def _load_item_data():
    """读取 items.json"""
    if not os.path.exists(ITEM_DATA_FILE):
        return {}
    with open(ITEM_DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def _save_item_data(data):
    """写入 items.json"""
    with open(ITEM_DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _build_item_index():
    """构建物品索引：按类型分组，返回分组字典"""
    all_items = DataService.get_items()
    groups = {}
    for iid, item in all_items.items():
        t = item.get('type', 'other')
        if t not in groups:
            groups[t] = []
        groups[t].append({
            'item_id': iid,
            'name': item.get('name', iid),
            'type': t,
            'price': item.get('price', 0),
            'is_usable': item.get('is_usable', False),
            'capacity': item.get('capacity', 0),
        })
    # 每组按名称排序
    for t in groups:
        groups[t].sort(key=lambda x: x['item_id'])
    return groups

def _build_item_from_form(form, existing=None):
    """从表单数据构建物品字典"""
    name = form.get("name", "").strip()
    if not name:
        flash("物品名称不能为空")
        return None

    item_type = form.get("type", "material")
    if item_type not in ITEM_TYPE_CHOICES:
        flash("无效的物品类型")
        return None

    description = form.get("description", "").strip()
    if not description:
        description = name

    price = int(form.get("price", 0) or 0)
    sell_price_str = form.get("sell_price", "").strip()
    sell_price = int(sell_price_str) if sell_price_str else None
    currency = form.get("currency", "") or None
    if currency and currency not in ('yuanbao', 'jinzu'):
        currency = None
    is_usable = form.get("is_usable") == "1"
    is_permanent_buff = form.get("is_permanent_buff") == "1"
    can_bulk_use = form.get("can_bulk_use") == "1"
    capacity = float(form.get("capacity", 0) or 0)

    item_data = {
        "name": name,
        "type": item_type,
        "description": description,
        "price": price,
        "is_usable": is_usable,
        "capacity": capacity,
    }

    if sell_price is not None:
        item_data["sell_price"] = sell_price
    if currency:
        item_data["currency"] = currency
    if is_permanent_buff:
        item_data["is_permanent_buff"] = True
    if can_bulk_use:
        item_data["can_bulk_use"] = True

    # usage_condition (JSON)
    uc_str = form.get("usage_condition_json", "").strip()
    if uc_str:
        try:
            usage_condition = json.loads(uc_str)
            if isinstance(usage_condition, dict) and usage_condition:
                item_data["usage_condition"] = usage_condition
        except json.JSONDecodeError:
            flash("使用条件 JSON 格式错误")
            return None

    # usage_effect (JSON)
    ue_str = form.get("usage_effect_json", "").strip()
    if ue_str:
        try:
            usage_effect = json.loads(ue_str)
            if isinstance(usage_effect, dict) and usage_effect:
                item_data["usage_effect"] = usage_effect
        except json.JSONDecodeError:
            flash("使用效果 JSON 格式错误")
            return None

    return item_data

def _simulate_item_use(item_id):
    """模拟物品使用：展示效果预览（不写入数据库）"""
    item = DataService.get_item(item_id)
    if not item:
        return None
    result = {
        'item_id': item_id,
        'name': item.get('name', item_id),
        'type': item.get('type', ''),
        'is_usable': item.get('is_usable', False),
    }
    ue = item.get('usage_effect', {})
    if not ue:
        result['effect_summary'] = '无使用效果'
        return result

    summary_lines = []

    # stat_changes
    sc = ue.get('stat_changes', {})
    if sc:
        for stat, val in sc.items():
            stat_label = STAT_CHANGE_NAMES.get(stat, stat)
            summary_lines.append(f"属性变化: {stat_label} {'+'if val>0 else ''}{val}")

    # stat_changes_rng
    scr = ue.get('stat_changes_rng', {})
    if scr:
        for stat, rng in scr.items():
            stat_label = STAT_CHANGE_NAMES.get(stat, stat)
            if isinstance(rng, list) and len(rng) == 2:
                summary_lines.append(f"随机属性: {stat_label} {rng[0]}~{rng[1]}")

    # temp_effects
    te = ue.get('temp_effects', [])
    if te:
        for eff in te:
            stat = eff.get('stat', '')
            val = eff.get('value', 0)
            rate = eff.get('rate', 0)
            dur = eff.get('duration', 0)
            ename = eff.get('effect_name', stat)
            detail = f"临时效果: {ename}"
            if val:
                detail += f" +{val}"
            if rate:
                detail += f" +{rate*100:.0f}%"
            detail += f" 持续{dur}秒"
            summary_lines.append(detail)

    # grant_title
    gt = ue.get('grant_title', '')
    if gt:
        summary_lines.append(f"授予称号: {gt}")

    # grant_gold
    gg = ue.get('grant_gold', 0)
    if gg:
        summary_lines.append(f"给予银两: +{gg}")

    # grant_item
    gi = ue.get('grant_item', None)
    if gi:
        if isinstance(gi, list) and len(gi) >= 2:
            gi_item = DataService.get_item(gi[0])
            gi_name = gi_item.get('name', gi[0]) if gi_item else gi[0]
            summary_lines.append(f"给予物品: {gi_name}×{gi[1]}")
        else:
            summary_lines.append(f"给予物品: {gi}")

    # random_one_of
    roo = ue.get('random_one_of', [])
    if roo:
        names = []
        for rid in roo[:5]:
            ri = DataService.get_item(rid)
            names.append(ri.get('name', rid) if ri else rid)
        extra = f" 等{len(roo)}个" if len(roo) > 5 else ""
        summary_lines.append(f"随机选一: {', '.join(names)}{extra}")

    # random_items
    ri_list = ue.get('random_items', [])
    if ri_list:
        for ri_entry in ri_list:
            riid = ri_entry.get('item_id', '')
            ri_item = DataService.get_item(riid)
            ri_name = ri_item.get('name', riid) if ri_item else riid
            chance = ri_entry.get('chance', 0)
            gc = ri_entry.get('guaranteed_count', 0)
            mc = ri_entry.get('max_count', 1)
            summary_lines.append(f"随机物品: {ri_name} (概率{chance*100:.0f}%, 保底{gc}, 最多{mc})")

    # item_changes
    ic = ue.get('item_changes', {})
    if ic:
        for iid2, cnt in ic.items():
            ic_item = DataService.get_item(iid2)
            ic_name = ic_item.get('name', iid2) if ic_item else iid2
            summary_lines.append(f"物品变动: {ic_name} {'+'if cnt>0 else ''}{cnt}")

    # equipment_generators
    eg_list = ue.get('equipment_generators', [])
    if eg_list:
        for idx, eg in enumerate(eg_list):
            cnt = eg.get('count', 1)
            chance = eg.get('chance', 1)
            tids = eg.get('template_ids', [])
            summary_lines.append(f"装备生成器#{idx+1}: {cnt}件, 概率{chance*100:.0f}%, 池{len(tids)}个模板")

    # generate_equipment
    ge = ue.get('generate_equipment', None)
    if ge:
        tid = ge.get('template_id', '')
        tpl = DataService.get_equipment_template(tid)
        tname = tpl.get('name', tid) if tpl else tid
        rr = ge.get('rarity_range', [])
        summary_lines.append(f"生成装备: {tname} (品质{rr})")

    # special
    sp = ue.get('special', '')
    if sp:
        summary_lines.append(f"特殊效果: {sp}")

    # vip_days
    vd = ue.get('vip_days', 0)
    if vd:
        summary_lines.append(f"VIP天数: +{vd}天")

    # restore_vitality
    rv = ue.get('restore_vitality', 0)
    if rv:
        summary_lines.append(f"恢复活力: +{rv}")

    # expand_backpack
    eb = ue.get('expand_backpack', 0)
    if eb:
        summary_lines.append(f"扩展背包: +{eb}")

    # expand_warehouse
    ew = ue.get('expand_warehouse', 0)
    if ew:
        summary_lines.append(f"扩展仓库: +{ew}")

    # grant_lieutenant
    gl = ue.get('grant_lieutenant', '')
    if gl:
        summary_lines.append(f"授予副将: {gl}")

    # random_soul
    rs = ue.get('random_soul', False)
    if rs:
        summary_lines.append(f"随机魂魄: 80%三级/19%二级/1%一级")

    # peace_status
    ps = ue.get('peace_status', 0)
    if ps:
        summary_lines.append(f"免战状态: {ps}分钟")

    # effect_descriptions
    ed = ue.get('effect_descriptions', {})
    if ed:
        for k, v in ed.items():
            summary_lines.append(f"效果描述: {k} → {v}")

    result['effect_summary'] = '\n'.join(summary_lines) if summary_lines else '有效果配置但无法解析'
    result['effect_lines'] = summary_lines
    return result


# --- Item Design: Main Page ---

@workbench_bp.route("/item_design")
@login_required
def item_design():
    if not _require_designer():
        return redirect(url_for('game.scene'))
    item_index = _build_item_index()
    return render_template("workbench/item_design.html",
                           item_index=item_index,
                           type_names=ITEM_TYPE_NAMES)


# --- Item Design: View Single Item ---

@workbench_bp.route("/item_view/<item_id>")
@login_required
def item_view(item_id):
    if not _require_designer():
        return redirect(url_for('game.scene'))
    item = DataService.get_item(item_id)
    if not item:
        flash("找不到该物品")
        return redirect(url_for('workbench.item_design'))

    # 生成效果预览
    preview = _simulate_item_use(item_id)

    return render_template("workbench/item_view.html",
                           item_id=item_id,
                           item=item,
                           preview=preview,
                           type_names=ITEM_TYPE_NAMES,
                           currency_names=ITEM_CURRENCY_NAMES,
                           stat_change_names=STAT_CHANGE_NAMES,
                           effect_names=USAGE_EFFECT_NAMES)


# --- Item Design: Add Item ---

@workbench_bp.route("/item_add", methods=["GET", "POST"])
@login_required
def item_add():
    if not _require_designer():
        return redirect(url_for('game.scene'))

    if request.method == "POST":
        item_id = request.form.get("item_id", "").strip()
        if not item_id:
            flash("物品ID不能为空")
            return redirect(url_for('workbench.item_add'))

        # 检查ID是否已存在
        if DataService.get_item(item_id):
            flash(f"物品ID '{item_id}' 已存在")
            return redirect(url_for('workbench.item_add'))

        item_data = _build_item_from_form(request.form)
        if item_data is None:
            return redirect(url_for('workbench.item_add'))

        # 写入文件
        data = _load_item_data()
        if data is None:
            data = {}
        data[item_id] = item_data
        _save_item_data(data)

        # 刷新缓存
        DataService._cache['items'][item_id] = item_data

        flash(f"物品 '{item_data.get('name', item_id)}' 已添加")
        return redirect(url_for('workbench.item_view', item_id=item_id))

    # GET: 显示添加表单
    # 构建套装索引（用于装备模板选择器）
    _, _, set_index = _build_picker_data()
    return render_template("workbench/item_add.html",
                           type_choices=ITEM_TYPE_CHOICES,
                           type_names=ITEM_TYPE_NAMES,
                           currency_choices=ITEM_CURRENCY_CHOICES,
                           currency_names=ITEM_CURRENCY_NAMES,
                           set_index=set_index)


# --- Item Design: Edit Item ---

@workbench_bp.route("/item_edit/<item_id>", methods=["GET", "POST"])
@login_required
def item_edit(item_id):
    if not _require_designer():
        return redirect(url_for('game.scene'))

    item = DataService.get_item(item_id)
    if not item:
        flash("找不到该物品")
        return redirect(url_for('workbench.item_design'))

    if request.method == "POST":
        item_data = _build_item_from_form(request.form, existing=item)
        if item_data is None:
            return redirect(url_for('workbench.item_edit', item_id=item_id))

        # 写入文件
        data = _load_item_data()
        if data is None:
            data = {}
        data[item_id] = item_data
        _save_item_data(data)

        # 刷新缓存
        DataService._cache['items'][item_id] = item_data

        flash(f"物品 '{item_data.get('name', item_id)}' 已更新")
        return redirect(url_for('workbench.item_view', item_id=item_id))

    # GET: 显示编辑表单
    item_ue_json = json.dumps(item.get('usage_effect', {}), ensure_ascii=False, indent=2)
    item_uc_json = json.dumps(item.get('usage_condition', {}), ensure_ascii=False, indent=2)
    _, _, set_index = _build_picker_data()
    return render_template("workbench/item_edit.html",
                           item_id=item_id,
                           item=item,
                           item_ue_json=item_ue_json,
                           item_uc_json=item_uc_json,
                           type_choices=ITEM_TYPE_CHOICES,
                           type_names=ITEM_TYPE_NAMES,
                           currency_choices=ITEM_CURRENCY_CHOICES,
                           currency_names=ITEM_CURRENCY_NAMES,
                           set_index=set_index)


# --- Item Design: Delete Item ---

@workbench_bp.route("/item_delete/<item_id>", methods=["GET", "POST"])
@login_required
def item_delete(item_id):
    if not _require_designer():
        return redirect(url_for('game.scene'))

    item = DataService.get_item(item_id)
    if not item:
        flash("找不到该物品")
        return redirect(url_for('workbench.item_design'))

    if request.method == "POST":
        confirm = request.form.get("confirm")
        if confirm == "yes":
            data = _load_item_data()
            if data and item_id in data:
                del data[item_id]
                _save_item_data(data)
                # 刷新缓存
                DataService._cache['items'].pop(item_id, None)
                flash(f"物品 '{item.get('name', item_id)}' 已删除")
            else:
                flash("文件中未找到该物品")
            return redirect(url_for('workbench.item_design'))
        else:
            return redirect(url_for('workbench.item_view', item_id=item_id))

    return render_template("workbench/item_delete.html",
                           item_id=item_id,
                           item=item,
                           type_names=ITEM_TYPE_NAMES)


# --- Item Design: Test Use ---

@workbench_bp.route("/item_test/<item_id>", methods=["GET", "POST"])
@login_required
def item_test(item_id):
    if not _require_designer():
        return redirect(url_for('game.scene'))

    item = DataService.get_item(item_id)
    if not item:
        flash("找不到该物品")
        return redirect(url_for('workbench.item_design'))

    results = []
    if request.method == "POST":
        count = int(request.form.get("count", 1))
        count = min(count, 20)
        for _ in range(count):
            result = _simulate_item_use(item_id)
            if result:
                # 对含随机的效果做实际随机模拟
                ue = item.get('usage_effect', {})
                sim_lines = []

                # stat_changes_rng 模拟
                scr = ue.get('stat_changes_rng', {})
                if scr:
                    for stat, rng in scr.items():
                        if isinstance(rng, list) and len(rng) == 2:
                            val = _random.randint(rng[0], rng[1])
                            stat_label = STAT_CHANGE_NAMES.get(stat, stat)
                            sim_lines.append(f"随机属性: {stat_label} = {val}")

                # random_one_of 模拟
                roo = ue.get('random_one_of', [])
                if roo:
                    chosen = _random.choice(roo)
                    ci = DataService.get_item(chosen)
                    cn = ci.get('name', chosen) if ci else chosen
                    sim_lines.append(f"随机选一: {cn}")

                # random_items 模拟
                ri_list = ue.get('random_items', [])
                if ri_list:
                    for ri_entry in ri_list:
                        riid = ri_entry.get('item_id', '')
                        chance = ri_entry.get('chance', 0)
                        gc = ri_entry.get('guaranteed_count', 0)
                        mc = ri_entry.get('max_count', 1)
                        qty = gc  # 保底
                        for _ in range(mc - gc):
                            if _random.random() < chance:
                                qty += 1
                        if qty > 0:
                            ri_item = DataService.get_item(riid)
                            ri_name = ri_item.get('name', riid) if ri_item else riid
                            sim_lines.append(f"随机物品: {ri_name}×{qty}")

                # equipment_generators 模拟
                eg_list = ue.get('equipment_generators', [])
                if eg_list:
                    from services.equipment_generator import EquipmentGenerator
                    for idx, eg in enumerate(eg_list):
                        cnt = eg.get('count', 1)
                        chance_val = eg.get('chance', 1)
                        for _ in range(cnt):
                            if _random.random() < chance_val:
                                pool = eg.get('template_ids', [])
                                if pool:
                                    tid = _random.choice(pool)
                                    rw = eg.get('rarity_weights', {})
                                    sw = eg.get('star_weights', {})
                                    try:
                                        eq = EquipmentGenerator.generate_from_template(tid, rarity_weights=rw, star_weights=sw)
                                        if eq:
                                            sim_lines.append(f"装备生成#{idx+1}: {eq.get('name', tid)} ({eq.get('rarity', '?')}{eq.get('stars', '')}★)")
                                        else:
                                            sim_lines.append(f"装备生成#{idx+1}: 模板{tid}生成失败")
                                    except Exception as e:
                                        sim_lines.append(f"装备生成#{idx+1}: 生成异常({str(e)[:50]})")

                # generate_equipment 模拟
                ge = ue.get('generate_equipment', None)
                if ge:
                    from services.equipment_generator import EquipmentGenerator
                    tid = ge.get('template_id', '')
                    rr = ge.get('rarity_range', [])
                    try:
                        eq = EquipmentGenerator.generate_from_template(tid, rarity_range=rr)
                        if eq:
                            sim_lines.append(f"生成装备: {eq.get('name', tid)} ({eq.get('rarity', '?')}{eq.get('stars', '')}★)")
                        else:
                            sim_lines.append(f"生成装备: 模板{tid}生成失败")
                    except Exception as e:
                        sim_lines.append(f"生成装备: 生成异常({str(e)[:50]})")

                # random_soul 模拟
                rs = ue.get('random_soul', False)
                if rs:
                    roll = _random.random()
                    if roll < 0.01:
                        tier = "一级"
                    elif roll < 0.20:
                        tier = "二级"
                    else:
                        tier = "三级"
                    sim_lines.append(f"随机魂魄: {tier}副将")

                result['sim_lines'] = sim_lines
                results.append(result)

    return render_template("workbench/item_test.html",
                           item_id=item_id,
                           item=item,
                           results=results,
                           type_names=ITEM_TYPE_NAMES,
                           effect_names=USAGE_EFFECT_NAMES)