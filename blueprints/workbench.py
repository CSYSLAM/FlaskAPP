from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from services import db
from services.data_service import DataService
from services.player_service import PlayerService
from models.player import PlayerModel

workbench_bp = Blueprint('workbench', __name__)


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