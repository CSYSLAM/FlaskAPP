from flask import Blueprint, render_template, redirect, url_for, request, session, flash
from flask_login import login_required, current_user
from datetime import datetime
import time
from models.player import PlayerModel, EquipmentInstance, PlayerSkill, EquipmentSlot
from services import db
from services.data_service import DataService
from services.player_service import PlayerService
from services.battle_service import BattleService
from services.equipment_service import EquipmentService

player_bp = Blueprint('player', __name__)


@player_bp.route("/character")
@login_required
def character():
    player = current_user
    PlayerService.update_military_rank(player)
    db.session.commit()
    can_level_up = player.experience >= player.exp_to_next_level
    from services.vip_service import VipService
    from services.achievement_service import AchievementService
    vip_level = VipService.get_active_vip_level(player)
    achievement_points = AchievementService.get_points(player)
    star_count = min(achievement_points // 2000, 5)

    # Villa
    villa_name = '我的山庄'
    try:
        from models.villa import Villa
        villa = Villa.query.filter_by(owner_id=player.id).first()
        if villa:
            villa_name = villa.name
    except Exception:
        pass

    # Spouse
    spouse_name = None
    try:
        from models.relationship import Relationship
        spouse_rel = Relationship.query.filter(
            ((Relationship.player1_id == player.id) | (Relationship.player2_id == player.id)),
            Relationship.rel_type == 'spouse'
        ).first()
        if spouse_rel:
            other_id = spouse_rel.get_other_player_id(player.id)
            spouse_p = PlayerModel.query.get(other_id)
            if spouse_p:
                spouse_name = spouse_p.name
    except Exception:
        pass

    # Hongyan / Zhiji counts and total fate
    hongyan_count = 0
    zhiji_count = 0
    total_fate = 0
    try:
        from models.relationship import Relationship
        hongyan_count = Relationship.count_relationships(player.id, 'hongyan')
        zhiji_count = Relationship.count_relationships(player.id, 'zhiji')
        rels = Relationship.get_relationships(player.id)
        total_fate = sum(r.fate_value for r in rels)
    except Exception:
        pass

    # Legion
    legion_info = None
    try:
        from models.legion import LegionMember, Legion
        lm = LegionMember.query.filter_by(player_id=player.id).first()
        if lm:
            legion = Legion.query.get(lm.legion_id)
            if legion:
                legion_info = {'name': legion.name, 'country': legion.country}
    except Exception:
        pass

    # Party
    party_info = None
    try:
        if player.party_id:
            from models.party import Party
            party = Party.query.get(player.party_id)
            if party:
                pcount = PlayerModel.query.filter_by(party_id=party.id).count()
                party_info = {'name': party.name, 'count': pcount}
    except Exception:
        pass

    return render_template("character.html",
                         player=player,
                         can_level_up=can_level_up,
                         vip_level=vip_level,
                         achievement_points=achievement_points,
                         star_count=star_count,
                         villa_name=villa_name,
                         spouse_name=spouse_name,
                         hongyan_count=hongyan_count,
                         zhiji_count=zhiji_count,
                         total_fate=total_fate,
                         legion_info=legion_info,
                         party_info=party_info,
                         EquipmentInstance=EquipmentInstance,
                         PlayerModel=PlayerModel,
                         DataService=DataService,
                         now=datetime.now())


@player_bp.route("/edit_signature", methods=["GET", "POST"])
@login_required
def edit_signature():
    player = current_user
    if request.method == "POST":
        sig = request.form.get("signature", "").strip()[:100]
        player.signature = sig
        db.session.commit()
        flash("签名已更新")
        return redirect(url_for("player.character"))
    return render_template("edit_signature.html", player=player)


@player_bp.route("/marriage")
@login_required
def marriage():
    player = current_user
    spouse_name = None
    try:
        from models.relationship import Relationship
        spouse_rel = Relationship.query.filter(
            ((Relationship.player1_id == player.id) | (Relationship.player2_id == player.id)),
            Relationship.rel_type == 'spouse'
        ).first()
        if spouse_rel:
            other_id = spouse_rel.get_other_player_id(player.id)
            spouse_p = PlayerModel.query.get(other_id)
            if spouse_p:
                spouse_name = spouse_p.name
    except Exception:
        pass
    return render_template("marriage.html", player=player, spouse_name=spouse_name)


@player_bp.route("/status")
@login_required
def character_status():
    player = current_user
    jingguai_activity = "低" if player.elite_kill_count < 10 else (
        "中" if player.elite_kill_count < 50 else "高")
    from services.social_service import SocialService
    social_attack_bonus, social_defense_bonus = SocialService.get_social_bonus(player)

    # Lieutenant passives with detailed stat bonuses
    # 出战副将的被动技能给主人的属性加成(技能定义在 LIEUTENANT_SKILLS，存在副将 skills_raw 里)
    lt_passives = []
    lt_bonuses = {'max_health': 0, 'max_mana': 0, 'attack': 0, 'defense': 0, 'crit_rate': 0, 'dodge_rate': 0}
    try:
        from models.lieutenant import Lieutenant
        from services.lieutenant_service import LIEUTENANT_SKILLS
        deployed = Lieutenant.query.filter_by(owner_id=player.id, is_deployed=True).first()
        if deployed:
            # 键名映射: get_passive_bonus 返回 health/mana/crit/dodge，模板用 max_health/max_mana/crit_rate/dodge_rate
            raw = deployed.get_passive_bonus()
            key_map = {'health': 'max_health', 'mana': 'max_mana',
                       'crit': 'crit_rate', 'dodge': 'dodge_rate',
                       'attack': 'attack', 'defense': 'defense'}
            for k, v in raw.items():
                if k in key_map and v:
                    lt_bonuses[key_map[k]] += v
            # 列出每个已学被动技能(取 LIEUTENANT_SKILLS 里的描述)
            for sk in deployed.skills:
                if sk.get('type') != 'passive':
                    continue
                sdef = LIEUTENANT_SKILLS.get(sk.get('id'), {})
                lt_passives.append({
                    'name': sk.get('name', ''),
                    'desc': sdef.get('description', ''),
                })
    except Exception:
        pass

    # Legion bonuses
    legion_bonuses = {}
    try:
        from services.legion_service import LegionService
        legion_bonuses = LegionService.get_legion_skill_bonuses(player)
    except Exception:
        pass

    # Team bonus
    team_exp_bonus = 0
    try:
        if player.party_id:
            from models.party import Party
            party = Party.query.get(player.party_id)
            if party and party.member_count > 1:
                team_exp_bonus = 5
    except Exception:
        pass

    return render_template("character_status.html",
                         player=player,
                         jingguai_activity=jingguai_activity,
                         social_attack_bonus=social_attack_bonus,
                         social_defense_bonus=social_defense_bonus,
                         lt_passives=lt_passives,
                         lt_bonuses=lt_bonuses,
                         legion_bonuses=legion_bonuses,
                         team_exp_bonus=team_exp_bonus)


@player_bp.route("/toggle_reserve/<reserve_type>")
@login_required
def toggle_reserve(reserve_type):
    player = current_user
    if reserve_type == 'blood':
        player.blood_reserve_enabled = not player.blood_reserve_enabled
    elif reserve_type == 'mana':
        player.mana_reserve_enabled = not player.mana_reserve_enabled
    db.session.commit()
    # Redirect back to the referring page
    ref = request.referrer
    if ref and 'toggle_reserve' not in ref:
        return redirect(ref)
    return redirect(url_for("player.character_status"))


@player_bp.route("/level_up")
@login_required
def level_up():
    player = current_user
    # 升级前快照基础属性，用于展示本次升级获得的加成
    old = {
        'attack': player.attack, 'defense': player.defense,
        'max_health': player.max_health, 'max_mana': player.max_mana,
        'crit_rate': player.crit_rate, 'dodge_rate': player.dodge_rate,
    }
    # 手动升级：经验达标才可升，升级后 HP/MP 恢复满
    if not PlayerService.can_level_up(player):
        flash("经验不足，无法升级")
        return redirect(url_for("player.character"))
    leveled = PlayerService.level_up_now(player)
    db.session.commit()
    if leveled:
        # 计算本次升级获得的属性增量
        STAT_NAMES = {
            'attack': '攻击力', 'defense': '防御力',
            'max_health': '生命值', 'max_mana': '魔法值',
            'crit_rate': '暴击率', 'dodge_rate': '闪避率',
        }
        parts = []
        for k, name in STAT_NAMES.items():
            delta = getattr(player, k) - old[k]
            if delta == 0:
                continue
            if k in ('crit_rate', 'dodge_rate'):
                # 暴击/闪避存为小数，展示为百分比
                parts.append(f"{name}+{delta*100:.1f}%")
            else:
                parts.append(f"{name}+{int(delta)}")
        if parts:
            flash(f"恭喜升到{player.level}级！本次加成：<span style='color:#136ec2'>{'，'.join(parts)}</span>", 'levelup')
        else:
            flash(f"恭喜升到{player.level}级！", 'levelup')
    return redirect(url_for("player.character"))


@player_bp.route("/view/<username>")
@login_required
def view_player(username):
    player = current_user
    target = DataService.get_player_by_username(username)
    if not target:
        return redirect(url_for("game.scene"))
    from services.social_service import SocialService
    from services.vip_service import VipService
    from services.party_service import PartyService
    tab = request.args.get('tab', 'info')
    target_vip_level = VipService.get_active_vip_level(target)
    target_party = PartyService.get_player_party(target)
    target_party_name = ""
    target_party_count = 0
    if target_party:
        from models.player import PlayerModel
        leader = PlayerModel.query.get(target_party.leader_id)
        target_party_name = f"{leader.nickname}的队伍" if leader else "队伍"
        target_party_count = len(target_party.members)
    my_party = PartyService.get_player_party(player)
    target_equipped = DataService.get_equipped(target.id)
    from services.achievement_service import AchievementService
    target_achievements, achievement_categories = AchievementService.get_all(target)
    from services.social_service import SocialService
    from models.relationship import Relationship
    target_spouse = None
    spouse_rel = Relationship.query.filter(
        ((Relationship.player1_id == target.id) | (Relationship.player2_id == target.id))
    ).first()
    if spouse_rel:
        spouse_id = spouse_rel.get_other_player_id(target.id)
        target_spouse = PlayerModel.query.get(spouse_id)
    hongyan_count = Relationship.count_relationships(target.id, 'hongyan')
    zhiji_count = Relationship.count_relationships(target.id, 'zhiji')
    from models.legion import Legion
    from services.legion_service import LegionService
    target_legion = LegionService.get_player_legion(target)
    from models.lieutenant import Lieutenant
    target_lieutenant = Lieutenant.query.filter_by(owner_id=target.id, is_deployed=True).first()
    return render_template("view_player.html",
                         player=player,
                         target_player=target,
                         target_vip_level=target_vip_level,
                         EquipmentInstance=EquipmentInstance,
                         DataService=DataService,
                         SocialService=SocialService,
                         target_party=target_party,
                         target_party_name=target_party_name,
                         target_party_count=target_party_count,
                         my_party=my_party,
                         tab=tab,
                         target_equipped=target_equipped,
                         target_achievements=target_achievements,
                         achievement_categories=achievement_categories,
                         target_spouse=target_spouse,
                         target_legion=target_legion,
                         hongyan_count=hongyan_count,
                         zhiji_count=zhiji_count,
                         target_lieutenant=target_lieutenant)


@player_bp.route("/military_ranks")
@login_required
def military_ranks():
    rank_order = [
        "士兵", "十夫长", "百夫长", "校尉", "都尉",
        "裨将", "偏将", "中郎将", "车骑将军", "骠骑将军",
        "大司马", "大都督",
    ]
    ranks = [(name, PlayerModel.MILITARY_RANKS[name]) for name in rank_order]
    return render_template("military_ranks.html",
                         player=current_user,
                         ranks=ranks)


@player_bp.route("/achievements")
@player_bp.route("/achievements/<category>")
@login_required
def achievements(category=None):
    from services.achievement_service import AchievementService
    player = current_user
    page = max(1, int(request.args.get('page', 1)))
    per_page = max(1, int(request.args.get('per_page', 12)))
    achievement_points = 0
    achievement_bonuses = {}
    try:
        AchievementService.check_all(player)
        db.session.commit()
        result, categories = AchievementService.get_all(player)
        achievement_points = AchievementService.get_points(player)
        achievement_bonuses = AchievementService.get_bonuses(player)
    except Exception:
        db.session.rollback()
        categories = DataService.get_achievement_categories()
        result = {cat: [] for cat in categories}
        achievement_points = 0
        achievement_bonuses = {}
    if not category:
        category = categories[0] if categories else None
    all_achievements = result.get(category, []) if category else []
    total = len(all_achievements)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages)
    start = (page - 1) * per_page
    achievement_list = all_achievements[start:start + per_page]
    return render_template("achievements.html",
                         player=player,
                         achievement_list=achievement_list,
                         categories=categories,
                         current_category=category,
                         page=page,
                         per_page=per_page,
                         total_pages=total_pages,
                         total=total,
                         achievement_points=achievement_points,
                         achievement_bonuses=achievement_bonuses)


@player_bp.route("/achievement/<achievement_id>")
@login_required
def achievement_detail(achievement_id):
    from services.achievement_service import AchievementService
    from services.data_service import DataService
    from models.player import Achievement
    player = current_user
    page = max(1, int(request.args.get('page', 1)))
    per_page = max(1, int(request.args.get('per_page', 12)))
    adef = DataService.get_achievements().get(achievement_id)
    if not adef:
        flash("成就不存在")
        return redirect(url_for('player.achievements'))
    progress = AchievementService._get_progress(player, achievement_id, adef)
    is_completed = AchievementService.is_completed(player.id, achievement_id)
    is_claimed = AchievementService.is_claimed(player.id, achievement_id)
    completed_record = Achievement.query.filter_by(
        player_id=player.id, achievement_id=achievement_id).first()
    # Determine difficulty based on condition_value
    val = adef['condition_value']
    if val <= 20:
        difficulty = '简单'
    elif val <= 100:
        difficulty = '普通'
    else:
        difficulty = '困难'
    achievement = {
        'id': achievement_id,
        'name': adef['name'],
        'description': adef['description'],
        'reward': adef.get('reward', {}),
        'points': adef.get('points', 0),
        'category': AchievementService._normalize_category(adef),
        'difficulty': difficulty,
        'completed': is_completed,
        'claimed': is_claimed,
        'completed_at': completed_record.completed_at if completed_record else None,
        'progress': progress,
        'condition_value': val,
        'page': page,
        'per_page': per_page,
    }
    return render_template("achievement_detail.html",
                         player=player,
                         achievement=achievement)


@player_bp.route("/claim_achievement/<achievement_id>")
@login_required
def claim_achievement(achievement_id):
    from services.achievement_service import AchievementService
    from services.data_service import DataService
    player = current_user
    page = max(1, int(request.args.get('page', 1)))
    per_page = max(1, int(request.args.get('per_page', 12)))
    success, msg = AchievementService.claim(player, achievement_id)
    flash(msg)
    db.session.commit()
    adef = DataService.get_achievements().get(achievement_id)
    category = AchievementService._normalize_category(adef) if adef else '成长'
    return redirect(url_for('player.achievements', category=category, page=page, per_page=per_page))


# --- Equipment ---

@player_bp.route("/equipment_list")
@login_required
def equipment_list():
    return render_template("equipment_list.html",
                         player=current_user,
                         EquipmentInstance=EquipmentInstance,
                         DataService=DataService)


@player_bp.route("/view_equipped/<slot>")
@login_required
def view_equipped(slot):
    player = current_user
    equip = DataService.get_equipped(player.id).get(slot)
    if equip:
        return render_template('equipment_view.html',
                             player=player,
                             equipment=equip,
                             item_id=f'equipped_{slot}',
                             is_equipped={'val': True},
                             old_equip=None,
                             EquipmentInstance=EquipmentInstance,
                             DataService=DataService)
    return redirect(url_for('player.equipment_list'))


@player_bp.route("/equip/<equipment_instance_id>")
@login_required
def equip_item(equipment_instance_id):
    player = current_user
    cat = request.args.get('category', '全部')
    page = request.args.get('page', '1')
    per_page = request.args.get('per_page', '10')
    real_id = equipment_instance_id
    if real_id.startswith('equipment_'):
        real_id = real_id[len('equipment_'):]
    success, msg = EquipmentService.equip(player, real_id)
    flash(msg)
    return redirect(url_for('player.inventory', category=cat, page=page, per_page=per_page))


@player_bp.route("/unequip/<slot>")
@login_required
def unequip(slot):
    player = current_user
    EquipmentService.unequip(player, slot)
    return redirect(url_for('player.character'))


@player_bp.route("/enhance/<equipment_instance_id>")
@login_required
def enhance_page(equipment_instance_id):
    player = current_user
    real_id = equipment_instance_id
    if real_id.startswith('equipment_'):
        real_id = real_id[len('equipment_'):]
    equip = EquipmentInstance.query.filter_by(
        instance_id=real_id,
        player_id=player.id
    ).first()
    if not equip:
        return redirect(url_for('player.inventory'))

    game_config = DataService.get_game_config()
    enhance_cost = game_config.get("enhance_cost", 5000)
    can_enhance = (
        player.gold >= enhance_cost and
        equip.enhance_level < 50 and
        DataService.get_inventory_item(player.id, "enhance_gem") is not None
    )
    return render_template('enhance.html',
                         player=player,
                         equipment=equip,
                         item_id=equipment_instance_id,
                         enhance_cost=enhance_cost,
                         can_enhance=can_enhance,
                         DataService=DataService, EquipmentInstance=EquipmentInstance)


@player_bp.route("/enhance/<equipment_instance_id>", methods=["POST"])
@login_required
def enhance_equipment(equipment_instance_id):
    player = current_user
    real_id = equipment_instance_id
    if real_id.startswith('equipment_'):
        real_id = real_id[len('equipment_'):]
    success, msg = EquipmentService.enhance(player, real_id)
    equip = EquipmentInstance.query.filter_by(
        instance_id=real_id,
        player_id=player.id
    ).first()
    if not success:
        flash(msg)

    game_config = DataService.get_game_config()
    enhance_cost = game_config.get("enhance_cost", 5000)
    can_enhance = (
        player.gold >= enhance_cost and
        equip and equip.enhance_level < 50 and
        DataService.get_inventory_item(player.id, "enhance_gem") is not None
    )
    return render_template('enhance.html',
                         player=player,
                         equipment=equip,
                         item_id=equipment_instance_id,
                         enhance_cost=enhance_cost,
                         can_enhance=can_enhance,
                         EquipmentInstance=EquipmentInstance,
                         message=msg,
                         success=success)


# --- Inventory ---

@player_bp.route("/inventory")
@player_bp.route("/inventory/<category>")
@login_required
def inventory(category='全部'):
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 10))
    player = current_user

    filtered = []
    search_word = request.args.get('search_word', '').strip()
    # Inventory items (non-equipment)
    for inv in DataService.get_inventory(player.id):
        if inv.quantity <= 0:
            continue
        item_data = DataService.get_item(inv.item_id)
        if not item_data:
            continue
        it_type = item_data.get('type', 'other')
        # 分类逻辑：材料包(consumable但名字含"包")归到"其他"
        item_name = item_data.get('name', '')
        if it_type in ('consumable', 'potion'):
            if '包' in item_name:
                cat = '其他'
            else:
                cat = '药品'
        elif it_type == 'material':
            cat = '材料'
        elif it_type == 'chest':
            cat = '宝箱'
        elif it_type == 'quest':
            cat = '任务'
        else:
            cat = '其他'
        # Search filter
        if search_word and search_word.lower() not in item_data.get('name', '').lower():
            continue
        if category == '全部' or category == cat:
            filtered.append({
                'type': 'item',
                'item_id': inv.item_id,
                'is_bound': inv.is_bound,
                'quantity': inv.quantity,
                'item_data': item_data,
                'category': cat,
                'effect_hint': DataService.get_item_effect_hint(inv.item_id),
            })

    # Equipment instances (unequipped)
    for equip in DataService.get_unequipped_equipment(player.id):
        if search_word and search_word.lower() not in equip.name.lower():
            continue
        if category == '全部' or category == '装备':
            filtered.append({
                'type': 'equipment',
                'item_id': f'equipment_{equip.instance_id}',
                'is_bound': equip.is_bound,
                'equipment': equip,
                'category': '装备',
            })

    total = len(filtered)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    page_items = filtered[start:start + per_page]

    used_capacity = DataService.get_backpack_used_capacity(player.id)

    return render_template("inventory.html",
                         player=player,
                         category=category,
                         page=page,
                         per_page=per_page,
                         total=total,
                         total_pages=total_pages,
                         page_items=page_items,
                         used_capacity=used_capacity,
                         search_word=search_word,
                         DataService=DataService,
                         EquipmentInstance=EquipmentInstance)


@player_bp.route("/use_item/<item_id>")
@login_required
def use_item(item_id):
    from services.item_service import ItemService
    player = current_user
    cat = request.args.get('category', '全部')
    page = request.args.get('page', '1')
    per_page = request.args.get('per_page', '10')
    is_bound = request.args.get('is_bound')
    bound_val = None
    if is_bound == '1':
        bound_val = True
    elif is_bound == '0':
        bound_val = False
    success, msg = ItemService.use_item(player, item_id, is_bound=bound_val)
    if msg == "RENAME_CARD_USED":
        return redirect(url_for("player.rename_character"))
    flash(msg)
    return redirect(url_for("player.inventory", category=cat, page=page, per_page=per_page))


@player_bp.route("/bulk_use/<item_id>", methods=["POST"])
@login_required
def bulk_use_item(item_id):
    from services.item_service import ItemService
    player = current_user
    cat = request.form.get('category', '全部')
    page = request.form.get('page', '1')
    per_page = request.form.get('per_page', '10')
    quantity = int(request.form.get('quantity', 1))
    is_bound = request.form.get('is_bound')
    bound_val = None
    if is_bound == '1':
        bound_val = True
    elif is_bound == '0':
        bound_val = False
    inv = DataService.get_inventory_item(player.id, item_id, is_bound=bound_val)
    if not inv:
        return redirect(url_for('player.inventory', category=cat, page=page, per_page=per_page))

    quantity = min(quantity, inv.quantity)
    success_count = ItemService.bulk_use(player, item_id, quantity, is_bound=bound_val)
    flash(f"成功使用{success_count}个")
    return redirect(url_for('player.inventory', category=cat, page=page, per_page=per_page))


@player_bp.route("/view_item/<item_id>")
@login_required
def view_item(item_id):
    player = current_user
    is_bound = request.args.get('is_bound')
    from_page = request.args.get('from', 'inventory')  # 来源页面：inventory 或 equipment
    bound_val = None
    if is_bound == '1':
        bound_val = True
    elif is_bound == '0':
        bound_val = False
    if item_id.startswith('equipment_'):
        real_id = item_id[len('equipment_'):]
        equip = EquipmentInstance.query.filter_by(
            instance_id=real_id, player_id=player.id).first()
        if equip:
            old_equip = DataService.get_equipped(player.id).get(equip.slot)
            return render_template('equipment_view.html',
                                 player=player,
                                 equipment=equip,
                                 item_id=item_id,
                                 is_equipped={'val': False},
                                 old_equip=old_equip,
                                 EquipmentInstance=EquipmentInstance,
                                 DataService=DataService,
                                 from_page=from_page)
    else:
        item_data = DataService.get_item(item_id)
        inv = DataService.get_inventory_item(player.id, item_id, is_bound=bound_val)
        if item_data:
            # 遗忘之章残页详情页：附带残页数量供合成入口显示
            context = dict(
                item=item_data,
                item_id=item_id,
                is_bound=inv.is_bound if inv else False,
                quantity=inv.quantity if inv else 0,
                from_page=from_page,
            )
            if item_id == 'lt_forget_page':
                context['forget_page_count'] = inv.quantity if inv else 0
                context['forget_tome_cost'] = 50
            return render_template('item_view.html', **context)
    return redirect(url_for('player.inventory'))


@player_bp.route("/synthesize_forget_tome")
@login_required
def synthesize_forget_tome():
    """遗忘之章合成：50 个遗忘之章残页(lt_forget_page) 合成 1 个遗忘之章(lt_forget_tome)。
    合成后若残页仍 ≥50 则留详情页(可继续合)，否则回背包。"""
    player = current_user
    cost = 50
    page_inv = DataService.get_inventory_item(player.id, 'lt_forget_page')
    have = page_inv.quantity if page_inv else 0
    if have < cost:
        flash(f"遗忘之章残页不足，需要{cost}个(当前{have}个)")
        return redirect(url_for('player.view_item', item_id='lt_forget_page'))

    DataService.remove_item_from_inventory(player.id, 'lt_forget_page', cost)
    DataService.add_item_to_inventory(player.id, 'lt_forget_tome', 1)
    db.session.commit()

    have -= cost
    flash(f"合成成功，获得1个遗忘之章" + (f"，剩余{have}个残页" if have > 0 else "，残页已用完"))
    # 残页仍够再合一次则留在残页详情页继续合，否则回背包
    if have >= cost:
        return redirect(url_for('player.view_item', item_id='lt_forget_page'))
    return redirect(url_for('player.inventory'))


@player_bp.route("/sell/<item_id>")
@login_required
def sell_item(item_id):
    player = current_user
    cat = request.args.get('category', '全部')
    page = request.args.get('page', '1')
    per_page = request.args.get('per_page', '10')
    is_bound = request.args.get('is_bound')
    bound_val = None
    if is_bound == '1':
        bound_val = True
    elif is_bound == '0':
        bound_val = False
    if item_id.startswith('equipment_'):
        real_id = item_id[len('equipment_'):]
        success, msg, price = EquipmentService.sell_equipment(player, real_id)
    else:
        from services.shop_service import ShopService
        inv = DataService.get_inventory_item(player.id, item_id, is_bound=bound_val)
        qty = inv.quantity if inv else 1
        success, msg, price = ShopService.sell_item(player, item_id, qty, is_bound=bound_val)
    if success:
        flash(msg)
    return redirect(url_for('player.inventory', category=cat, page=page, per_page=per_page))


@player_bp.route("/destroy_item/<item_id>")
@login_required
def destroy_item(item_id):
    player = current_user
    cat = request.args.get('category', '全部')
    page = request.args.get('page', '1')
    per_page = request.args.get('per_page', '10')
    is_bound = request.args.get('is_bound')
    bound_val = None
    if is_bound == '1':
        bound_val = True
    elif is_bound == '0':
        bound_val = False
    if item_id.startswith('equipment_'):
        real_id = item_id[len('equipment_'):]
        equip = EquipmentInstance.query.filter_by(
            instance_id=real_id, player_id=player.id).first()
        if equip:
            slot = EquipmentSlot.query.filter_by(
                equipment_instance_id=equip.id).first()
            if slot:
                slot.equipment_instance_id = None
            db.session.delete(equip)
            db.session.commit()
    else:
        inv = DataService.get_inventory_item(player.id, item_id, is_bound=bound_val)
        if inv:
            db.session.delete(inv)
            db.session.commit()
    return redirect(url_for('player.inventory', category=cat, page=page, per_page=per_page))


# --- Skills ---

@player_bp.route("/skill_list/<npc_id>")
@login_required
def skill_list(npc_id):
    from models.player import PlayerSkill
    player = current_user
    skill_type = request.args.get('skill_type', 'active')
    if skill_type == 'active':
        skill_list_data = DataService.get_active_skills()
    else:
        skill_list_data = DataService.get_passive_skills()
    player_skills = {
        ps.skill_id: ps
        for ps in PlayerSkill.query.filter_by(player_id=player.id).all()
    }
    return render_template("skill_list.html",
                         player=player,
                         skill_list=skill_list_data,
                         player_skills=player_skills,
                         skill_type=skill_type,
                         npc_id=npc_id)


@player_bp.route("/skill_detail/<npc_id>/<skill_id>")
@login_required
def skill_detail(npc_id, skill_id):
    from models.player import PlayerSkill
    player = current_user
    sdef = DataService.get_skill(skill_id)
    if not sdef:
        flash("技能不存在")
        return redirect(url_for('player.skill_list', npc_id=npc_id))
    ps = PlayerSkill.query.filter_by(
        player_id=player.id, skill_id=skill_id).first()
    return render_template("skill_detail.html",
                         player=player,
                         skill_def=sdef,
                         player_skill=ps,
                         npc_id=npc_id)


@player_bp.route("/learn_skill/<npc_id>/<skill_id>")
@login_required
def learn_skill(npc_id, skill_id):
    from models.player import PlayerSkill
    player = current_user
    skill_data = DataService.get_skill(skill_id)
    if not skill_data:
        flash("技能不存在")
        return redirect(url_for('player.skill_list', npc_id=npc_id, skill_type='active'))

    skill_type = skill_data.get('skill_type', 'active')

    class_req = skill_data.get("class_required")
    if class_req and player.player_class != class_req:
        flash(f"需要{class_req}职业")
        return redirect(url_for('player.skill_list', npc_id=npc_id, skill_type=skill_type))

    existing = PlayerSkill.query.filter_by(
        player_id=player.id, skill_id=skill_id).first()
    if existing:
        flash("已经学习过该技能")
        return redirect(url_for('player.skill_list', npc_id=npc_id, skill_type=skill_type))

    # Learning cost: 1级消耗 = base（与升级公式 cost = base * mult^(level-1) 在 level=1 时一致）
    exp_base = skill_data.get('upgrade_exp_base', 100)
    gold_base = skill_data.get('upgrade_gold_base', 1000)
    exp_cost = exp_base
    gold_cost = gold_base

    if player.experience < exp_cost:
        flash(f"经验不足，学习需要{exp_cost}点经验")
        return redirect(url_for('player.skill_list', npc_id=npc_id, skill_type=skill_type))

    if player.gold < gold_cost:
        flash(f"银两不足，学习需要{gold_cost}银两")
        return redirect(url_for('player.skill_list', npc_id=npc_id, skill_type=skill_type))

    player.experience -= exp_cost
    player.gold -= gold_cost
    db.session.add(PlayerSkill(player_id=player.id, skill_id=skill_id))
    db.session.commit()
    from services.quest_service import QuestService
    QuestService.update_learn_skill_progress(player)
    flash(f"成功学习技能【{skill_data['name']}】")
    return redirect(url_for('player.skill_list', npc_id=npc_id, skill_type=skill_type))


@player_bp.route("/upgrade_skill/<npc_id>/<skill_id>")
@login_required
def upgrade_skill(npc_id, skill_id):
    from models.player import PlayerSkill
    player = current_user
    ps = PlayerSkill.query.filter_by(
        player_id=player.id, skill_id=skill_id).first()
    if not ps:
        flash("未学习该技能")
        return redirect(url_for('player.skill_list', npc_id=npc_id, skill_type='active'))

    skill_data = DataService.get_skill(skill_id)
    if not skill_data:
        flash("技能不存在")
        return redirect(url_for('player.skill_list', npc_id=npc_id, skill_type='active'))

    skill_type = skill_data.get('skill_type', 'active')

    if ps.skill_level >= skill_data.get("max_level", 10):
        flash("技能已达最高等级")
        return redirect(url_for('player.skill_list', npc_id=npc_id, skill_type=skill_type))

    next_level = ps.skill_level + 1
    exp_base = skill_data.get('upgrade_exp_base', 100)
    gold_base = skill_data.get('upgrade_gold_base', 1000)
    mult = skill_data.get('upgrade_cost_multiplier', 2.2)
    # 几何递增: 1级=base, 2级=base*mult, 3级=base*mult^2 ... next_level 级 = base*mult^(next_level-1)
    exp_cost = int(exp_base * (mult ** (next_level - 1)))
    gold_cost = int(gold_base * (mult ** (next_level - 1)))

    if player.experience < exp_cost:
        flash(f"经验不足，需要{exp_cost}点经验")
        return redirect(url_for('player.skill_list', npc_id=npc_id, skill_type=skill_type))

    if player.gold < gold_cost:
        flash(f"银两不足，需要{gold_cost}银两")
        return redirect(url_for('player.skill_list', npc_id=npc_id, skill_type=skill_type))

    player.experience -= exp_cost
    player.gold -= gold_cost
    ps.skill_level += 1
    db.session.commit()
    flash(f"成功将【{skill_data['name']}】升级到{ps.skill_level}级")
    return redirect(url_for('player.skill_list', npc_id=npc_id, skill_type=skill_type))


@player_bp.route("/temp_effects")
@login_required
def temp_effects():
    return render_template("temp_effects.html",
                         player=current_user,
                         DataService=DataService,
                         now=time.time())


# --- Skill View ---

@player_bp.route("/skill_view")
@player_bp.route("/skill_view/<skill_type>")
@login_required
def skill_view(skill_type='active'):
    from models.player import PlayerSkill
    player = current_user
    if skill_type == 'active':
        skill_list = DataService.get_active_skills()
    else:
        skill_list = DataService.get_passive_skills()
    player_skills = {
        ps.skill_id: ps
        for ps in PlayerSkill.query.filter_by(player_id=player.id).all()
    }
    shortcuts = player.get_shortcuts() if hasattr(player, 'get_shortcuts') else {}
    return render_template("skill_view.html",
                         player=player,
                         skill_list=skill_list,
                         player_skills=player_skills,
                         skill_type=skill_type,
                         shortcuts=shortcuts,
                         DataService=DataService)


@player_bp.route("/skill_view_detail/<skill_id>")
@login_required
def skill_view_detail(skill_id):
    from models.player import PlayerSkill
    player = current_user
    sdef = DataService.get_skill(skill_id)
    if not sdef:
        flash("技能不存在")
        return redirect(url_for('player.skill_view'))
    ps = PlayerSkill.query.filter_by(
        player_id=player.id, skill_id=skill_id).first()
    shortcuts = player.get_shortcuts() if hasattr(player, 'get_shortcuts') else {}
    shortcut_slot = None
    for slot, sid in shortcuts.items():
        if sid == skill_id:
            shortcut_slot = slot.replace('skill', '')
            break
    return render_template("skill_view_detail.html",
                         player=player,
                         skill_def=sdef,
                         skill_id=skill_id,
                         player_skill=ps,
                         shortcut_slot=shortcut_slot,
                         DataService=DataService)


@player_bp.route("/set_skill_shortcut/<skill_id>/<int:slot>")
@login_required
def set_skill_shortcut(skill_id, slot):
    player = current_user
    sdef = DataService.get_skill(skill_id)
    if not sdef or sdef.get('skill_type') != 'active':
        flash("只能设置主动技能为快捷键")
        return redirect(url_for('player.skill_view_detail', skill_id=skill_id))
    from models.player import PlayerSkill
    ps = PlayerSkill.query.filter_by(
        player_id=player.id, skill_id=skill_id).first()
    if not ps:
        flash("未学习该技能")
        return redirect(url_for('player.skill_view_detail', skill_id=skill_id))
    shortcuts = player.get_shortcuts()
    if slot == 0:
        # Remove from shortcuts
        for s, sid in list(shortcuts.items()):
            if sid == skill_id:
                del shortcuts[s]
    else:
        shortcuts[f'skill{slot}'] = skill_id
    player.set_shortcuts(shortcuts)
    db.session.commit()
    if slot == 0:
        flash(f"已取消【{sdef['name']}】的快捷键")
    else:
        flash(f"已将【{sdef['name']}】设为快捷键{slot}")
    return redirect(url_for('player.skill_view_detail', skill_id=skill_id))


# --- Title routes ---

@player_bp.route("/titles")
@player_bp.route("/titles/<title_type>")
@login_required
def titles(title_type='prefix'):
    from services.title_service import TitleService
    player = current_user
    title_bonuses = TitleService.get_title_bonuses(player)

    if title_type == 'prefix':
        all_titles = DataService.get_title_prefixes()
        owned_set = [t for t in player.owned_titles if t in all_titles]
        count_label = '前缀数量'
        bonus_label = '前缀属性'
    else:
        all_titles = DataService.get_title_suffixes()
        owned_set = [t for t in player.owned_titles if t in all_titles]
        count_label = '后缀数量'
        bonus_label = '后缀属性'

    return render_template("titles.html",
                         player=player,
                         title_type=title_type,
                         all_titles=all_titles,
                         owned_set=owned_set,
                         title_bonuses=title_bonuses,
                         count_label=count_label,
                         bonus_label=bonus_label,
                         DataService=DataService)


@player_bp.route("/title_detail/<title_type>/<title_id>")
@login_required
def title_detail(title_type, title_id):
    from services.title_service import TitleService
    player = current_user

    if title_type == 'prefix':
        title_def = DataService.get_title(title_id, 'prefix')
        other_type = 'suffix'
    else:
        title_def = DataService.get_title(title_id, 'suffix')
        other_type = 'prefix'

    if not title_def:
        flash("称号不存在")
        return redirect(url_for('player.titles'))

    stars = title_def.get('stars', 1)
    star_bonus = DataService.get_star_bonus(stars)

    # Check if owned
    is_owned = title_id in player.owned_titles
    is_equipped = (title_type == 'prefix' and player.title_prefix_id == title_id) or \
                  (title_type == 'suffix' and player.title_suffix_id == title_id)

    # Check if matching pair is equipped
    pair_id = title_def.get('pair_id')
    pair_title = None
    if pair_id:
        pair_title = DataService.get_title(pair_id, other_type)

    return render_template("title_detail.html",
                         player=player,
                         title_type=title_type,
                         title_id=title_id,
                         title_def=title_def,
                         star_bonus=star_bonus,
                         is_owned=is_owned,
                         is_equipped=is_equipped,
                         pair_id=pair_id,
                         pair_title=pair_title,
                         DataService=DataService)


@player_bp.route("/equip_title/<title_type>/<title_id>")
@login_required
def equip_title(title_type, title_id):
    from services.title_service import TitleService
    from services.player_service import PlayerService
    player = current_user

    if title_id not in player.owned_titles:
        flash("未拥有该称号")
        return redirect(url_for('player.titles', title_type=title_type))

    # Calculate old stats before equipping
    old_hp = PlayerService.get_max_health(player)
    old_mp = PlayerService.get_max_mana(player)
    old_atk = PlayerService.get_attack(player)
    old_def = PlayerService.get_defense(player)
    old_crit = player.effective_crit_rate
    old_dodge = player.effective_dodge_rate

    if title_type == 'prefix':
        player.title_prefix_id = title_id
    else:
        player.title_suffix_id = title_id

    db.session.commit()

    # Calculate new stats after equipping
    new_hp = PlayerService.get_max_health(player)
    new_mp = PlayerService.get_max_mana(player)
    new_atk = PlayerService.get_attack(player)
    new_def = PlayerService.get_defense(player)
    new_crit = player.effective_crit_rate
    new_dodge = player.effective_dodge_rate

    title_def = DataService.get_title(title_id, title_type)
    title_name = title_def.get('name', title_id)

    # Build attribute change message
    changes = []
    if new_hp != old_hp:
        changes.append(f"生命值+{new_hp - old_hp}")
    if new_mp != old_mp:
        changes.append(f"魔法值+{new_mp - old_mp}")
    if new_atk != old_atk:
        changes.append(f"攻击力+{new_atk - old_atk}")
    if new_def != old_def:
        changes.append(f"防御力+{new_def - old_def}")
    if new_crit != old_crit:
        changes.append(f"暴击率+{round((new_crit - old_crit) * 100, 1)}%")
    if new_dodge != old_dodge:
        changes.append(f"闪避率+{round((new_dodge - old_dodge) * 100, 1)}%")

    if changes:
        flash(f"已装备称号【{title_name}】，{', '.join(changes)}")
    else:
        flash(f"已装备称号【{title_name}】")
    return redirect(url_for('player.titles', title_type=title_type))


@player_bp.route("/unequip_title/<title_type>")
@login_required
def unequip_title(title_type):
    from services.title_service import TitleService
    from services.player_service import PlayerService
    player = current_user

    # Get old title name
    old_id = None
    if title_type == 'prefix':
        old_id = player.title_prefix_id
    else:
        old_id = player.title_suffix_id

    old_title_def = DataService.get_title(old_id, title_type) if old_id else None
    old_title_name = old_title_def.get('name', old_id) if old_title_def else "称号"

    # Calculate old stats before unequipping
    old_hp = PlayerService.get_max_health(player)
    old_mp = PlayerService.get_max_mana(player)
    old_atk = PlayerService.get_attack(player)
    old_def = PlayerService.get_defense(player)
    old_crit = player.effective_crit_rate
    old_dodge = player.effective_dodge_rate

    if title_type == 'prefix':
        player.title_prefix_id = None
    else:
        player.title_suffix_id = None

    db.session.commit()

    # Calculate new stats after unequipping
    new_hp = PlayerService.get_max_health(player)
    new_mp = PlayerService.get_max_mana(player)
    new_atk = PlayerService.get_attack(player)
    new_def = PlayerService.get_defense(player)
    new_crit = player.effective_crit_rate
    new_dodge = player.effective_dodge_rate

    # Build attribute change message
    changes = []
    if new_hp != old_hp:
        changes.append(f"生命值-{old_hp - new_hp}")
    if new_mp != old_mp:
        changes.append(f"魔法值-{old_mp - new_mp}")
    if new_atk != old_atk:
        changes.append(f"攻击力-{old_atk - new_atk}")
    if new_def != old_def:
        changes.append(f"防御力-{old_def - new_def}")
    if new_crit != old_crit:
        changes.append(f"暴击率-{round((old_crit - new_crit) * 100, 1)}%")
    if new_dodge != old_dodge:
        changes.append(f"闪避率-{round((old_dodge - new_dodge) * 100, 1)}%")

    if changes:
        flash(f"已卸下称号【{old_title_name}】，{', '.join(changes)}")
    else:
        flash("已卸下称号")
    return redirect(url_for('player.titles', title_type=title_type))


@player_bp.route("/rename", methods=["GET", "POST"])
@login_required
def rename_character():
    player = current_user
    if request.method == "GET":
        return render_template("rename_character.html", player=player)
    new_name = request.form.get("new_name", "").strip()
    if not new_name:
        flash("请输入新名字")
        return redirect(url_for("player.rename_character"))
    if len(new_name) > 12:
        flash("名字长度不能超过12个字符")
        return redirect(url_for("player.rename_character"))
    existing = DataService.get_player_by_username(new_name)
    if existing and existing.id != player.id:
        flash("该名字已被使用")
        return redirect(url_for("player.rename_character"))
    player.nickname = new_name
    player.username = new_name
    db.session.commit()
    flash(f"改名成功，新名字：{new_name}")
    return redirect(url_for("player.character"))


from services import db
