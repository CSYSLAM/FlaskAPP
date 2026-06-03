"""Lieutenant (副将) companion service."""
import random
import json
from services import db
from services.data_service import DataService
from models.lieutenant import Lieutenant, QUALITY_NAMES, QUALITY_MULTIPLIER, CLASS_NAMES, GENDER_NAMES


LIEUTENANT_NAMES = {
    'male_warrior': ['徐晃', '马超', '关羽', '张飞', '赵云', '吕布', '典韦', '许褚', '夏侯惇', '魏延'],
    'male_mage': ['李儒', '庞统', '诸葛亮', '司马懿', '郭嘉', '贾诩', '荀彧', '周瑜', '陆逊', '法正'],
    'male_assassin': ['甘宁', '太史慈', '凌统', '丁奉', '徐盛', '吕蒙', '黄盖', '韩当', '程普', '蒋钦'],
    'female_warrior': ['孙尚香', '祝融', '关银屏', '张星彩', '鲍三娘', '马云騄'],
    'female_mage': ['黄月英', '步练师', '王元姬', '蔡文姬', '甄姬'],
    'female_assassin': ['貂蝉', '吕玲绮', '花鬘', '孙鲁育', '小乔'],
}

# Lieutenant skill definitions
LIEUTENANT_SKILLS = {
    # Active skills
    'combo': {'name': '连击', 'type': 'active', 'class_required': 'assassin',
              'max_level': 3, 'trigger_rate': [12, 18, 24],
              'damage_rate': [120, 150, 180],
              'description': '连续击杀，对敌造成大量伤害'},
    'smash': {'name': '猛击', 'type': 'active', 'class_required': 'warrior',
              'max_level': 3, 'trigger_rate': [12, 18, 24],
              'damage_rate': [120, 150, 180],
              'description': '猛烈一击，对敌造成大量伤害'},
    'thunder': {'name': '天雷', 'type': 'active', 'class_required': 'mage',
              'max_level': 3, 'trigger_rate': [12, 18, 24],
              'damage_rate': [120, 150, 180],
              'description': '召唤天雷，对敌造成大量伤害'},
    # Triggered skills
    'absorb': {'name': '吸收', 'type': 'triggered', 'class_required': None,
               'max_level': 3, 'trigger_rate': [12, 18, 24],
               'absorb_rate': [10, 15, 20],
               'description': '副将与主人遭到攻击有几率吸收伤害'},
    'heal_trigger': {'name': '回春', 'type': 'triggered', 'class_required': None,
                     'max_level': 3, 'trigger_rate': [10, 15, 20],
                     'heal_rate': [5, 8, 12],
                     'description': '战斗中有几率回复主人生命'},
    # Passive skills
    'sharp': {'name': '锐利', 'type': 'passive', 'class_required': None,
              'max_level': 3, 'bonus_type': 'attack',
              'bonus_value': [5, 8, 11],
              'description': '副将出战给与主人攻击加成'},
    'tough': {'name': '坚韧', 'type': 'passive', 'class_required': None,
              'max_level': 3, 'bonus_type': 'defense',
              'bonus_value': [5, 8, 13],
              'description': '副将出战给与主人防御加成'},
    'protect': {'name': '护佑', 'type': 'passive', 'class_required': None,
               'max_level': 3, 'bonus_type': 'health',
               'bonus_value': [5, 8, 13],
               'description': '副将出战给与主人生命加成'},
    'magic': {'name': '法能', 'type': 'passive', 'class_required': None,
              'max_level': 3, 'bonus_type': 'mana',
              'bonus_value': [5, 8, 13],
              'description': '副将出战给与主人魔法加成'},
    'brave': {'name': '勇猛', 'type': 'passive', 'class_required': None,
              'max_level': 3, 'bonus_type': 'crit',
              'bonus_value': [5, 8, 11],
              'description': '副将出战给与主人暴击加成'},
    'calm': {'name': '冷静', 'type': 'passive', 'class_required': None,
             'max_level': 3, 'bonus_type': 'dodge',
             'bonus_value': [5, 8, 11],
              'description': '副将出战给与主人闪避加成'},
}

# Skill book item IDs for each skill and level
SKILL_BOOK_IDS = {}
for sid, sdef in LIEUTENANT_SKILLS.items():
    level_names = ['入门', '进阶', '精通']
    required_counts = [50, 20, 10]
    for lv in range(1, sdef['max_level'] + 1):
        key = f'lt_skill_{sid}_{lv}'
        SKILL_BOOK_IDS[key] = {
            'skill_id': sid,
            'level': lv,
            'name': f'{sdef["name"]}{level_names[lv-1]}',
            'required_count': required_counts[lv-1],
        }

MAX_LIEUTENANT_SLOTS = 4
LOYALTY_DEATH_LOSS = 10
LIFESPAN_DEATH_LOSS = 5


class LieutenantService:

    @classmethod
    def get_lieutenants(cls, player):
        return Lieutenant.query.filter_by(owner_id=player.id).all()

    @classmethod
    def get_deployed(cls, player):
        return Lieutenant.query.filter_by(owner_id=player.id, is_deployed=True).first()

    @classmethod
    def recruit(cls, player, gender, class_type):
        count = Lieutenant.query.filter_by(owner_id=player.id).count()
        if count >= MAX_LIEUTENANT_SLOTS:
            return None, "副将位已满"

        name_pool = LIEUTENANT_NAMES.get(f'{gender}_{class_type}', ['副将'])
        name = random.choice(name_pool)

        lt = Lieutenant(
            owner_id=player.id,
            name=name,
            gender=gender,
            class_type=class_type,
            quality=0,
            enlightenment=0,
            reinforce=0,
            loyalty=80,
            lifespan=100,
            level=1,
            position='front',
            is_deployed=False,
            skills_raw='[]',
            skill_slots=3,
        )
        lt.current_health = lt.get_max_health()
        lt.current_mana = lt.get_max_mana()
        lt.is_alive = True

        db.session.add(lt)
        db.session.commit()
        return lt, f"招募了副将【{name}】({lt.quality_name}{lt.class_name})"

    @classmethod
    def expand_slots(cls, player):
        """Expand lieutenant slots using skill expansion item."""
        inv = DataService.get_inventory_item(player.id, 'lt_slot_expand')
        if not inv or inv.quantity <= 0:
            return False, "没有副将扩充符"
        count = Lieutenant.query.filter_by(owner_id=player.id).count()
        if count >= MAX_LIEUTENANT_SLOTS:
            return False, "副将位已满"
        DataService.remove_item_from_inventory(player.id, 'lt_slot_expand', 1)
        # Effectively this allows a new slot; MAX is 4, user buys expand to add
        # For simplicity, we increase the effective max stored on player
        data = player.activity_data
        lt_max = data.get('lieutenant_max', MAX_LIEUTENANT_SLOTS)
        data['lieutenant_max'] = lt_max + 1
        player.activity_data = data
        db.session.commit()
        return True, f"副将位扩充至{data['lieutenant_max']}个"

    @classmethod
    def get_max_slots(cls, player):
        data = player.activity_data
        return data.get('lieutenant_max', MAX_LIEUTENANT_SLOTS)

    @classmethod
    def wash_quality(cls, lieutenant):
        """Wash quality (洗资质) - randomize quality using 资质丹."""
        inv = DataService.get_inventory_item(lieutenant.owner_id, 'lt_quality_pill')
        if not inv or inv.quantity <= 0:
            return False, "没有副将资质丹"
        DataService.remove_item_from_inventory(lieutenant.owner_id, 'lt_quality_pill', 1)

        old_quality = lieutenant.quality
        new_quality = random.randint(0, 20)
        lieutenant.quality = new_quality

        # Recalculate health/mana based on new quality
        max_hp = lieutenant.get_max_health()
        max_mp = lieutenant.get_max_mana()
        lieutenant.current_health = min(lieutenant.current_health, max_hp)
        lieutenant.current_mana = min(lieutenant.current_mana, max_mp)

        db.session.commit()
        return True, f"资质从{QUALITY_NAMES.get(old_quality, '普通')}变为{lieutenant.quality_name}"

    @classmethod
    def enlighten(cls, lieutenant):
        """Increase enlightenment (悟性) using 悟性丹. Success rate decreases per level."""
        inv = DataService.get_inventory_item(lieutenant.owner_id, 'lt_enlighten_pill')
        if not inv or inv.quantity <= 0:
            return False, "没有副将悟性丹"

        if lieutenant.enlightenment >= 10:
            return False, "悟性已达上限"

        DataService.remove_item_from_inventory(lieutenant.owner_id, 'lt_enlighten_pill', 1)

        success_rate = max(0.3, 1.0 - lieutenant.enlightenment * 0.07)
        if random.random() < success_rate:
            lieutenant.enlightenment += 1
            max_hp = lieutenant.get_max_health()
            max_mp = lieutenant.get_max_mana()
            lieutenant.current_health = min(lieutenant.current_health, max_hp)
            lieutenant.current_mana = min(lieutenant.current_mana, max_mp)
            db.session.commit()
            return True, f"悟性提升至{lieutenant.enlightenment}"
        else:
            db.session.commit()
            return True, f"悟性提升失败，保持{lieutenant.enlightenment}"

    @classmethod
    def reinforce(cls, lieutenant):
        """Reinforce (强化) using 强化丹. Success rate decreases per level."""
        inv = DataService.get_inventory_item(lieutenant.owner_id, 'lt_reinforce_pill')
        if not inv or inv.quantity <= 0:
            return False, "没有副将强化丹"

        if lieutenant.reinforce >= 20:
            return False, "强化已达上限"

        DataService.remove_item_from_inventory(lieutenant.owner_id, 'lt_reinforce_pill', 1)

        success_rate = max(0.3, 0.95 - lieutenant.reinforce * 0.03)
        if random.random() < success_rate:
            lieutenant.reinforce += 1
            max_hp = lieutenant.get_max_health()
            max_mp = lieutenant.get_max_mana()
            lieutenant.current_health = min(lieutenant.current_health, max_hp)
            lieutenant.current_mana = min(lieutenant.current_mana, max_mp)
            db.session.commit()
            return True, f"强化成功，+{lieutenant.reinforce}"
        else:
            db.session.commit()
            return True, f"强化失败，保持+{lieutenant.reinforce}"

    @classmethod
    def restore_loyalty(cls, lieutenant):
        """Restore loyalty using 忠诚丹."""
        inv = DataService.get_inventory_item(lieutenant.owner_id, 'lt_loyalty_pill')
        if not inv or inv.quantity <= 0:
            return False, "没有副将忠诚丹"

        if lieutenant.loyalty >= 100:
            return False, "忠诚度已满"

        DataService.remove_item_from_inventory(lieutenant.owner_id, 'lt_loyalty_pill', 1)
        lieutenant.loyalty = min(100, lieutenant.loyalty + 20)
        db.session.commit()
        return True, f"忠诚度恢复至{lieutenant.loyalty}"

    @classmethod
    def restore_lifespan(cls, lieutenant):
        """Restore lifespan using 寿命丹."""
        inv = DataService.get_inventory_item(lieutenant.owner_id, 'lt_lifespan_pill')
        if not inv or inv.quantity <= 0:
            return False, "没有副将寿命丹"

        if lieutenant.lifespan >= 100:
            return False, "寿命已满"

        DataService.remove_item_from_inventory(lieutenant.owner_id, 'lt_lifespan_pill', 1)
        lieutenant.lifespan = min(100, lieutenant.lifespan + 20)
        db.session.commit()
        return True, f"寿命恢复至{lieutenant.lifespan}"

    @classmethod
    def deploy(cls, lieutenant):
        """Deploy lieutenant for battle."""
        can, msg = lieutenant.can_deploy()
        if not can:
            return False, msg

        # Undeploy any currently deployed lieutenant
        current = Lieutenant.query.filter_by(
            owner_id=lieutenant.owner_id, is_deployed=True).first()
        if current:
            current.is_deployed = False

        lieutenant.is_deployed = True
        lieutenant.is_alive = True
        if lieutenant.current_health <= 0:
            lieutenant.current_health = 1
        db.session.commit()
        return True, f"副将【{lieutenant.name}】出战"

    @classmethod
    def recall(cls, lieutenant):
        """Recall lieutenant from battle."""
        lieutenant.is_deployed = False
        db.session.commit()
        return True, f"副将【{lieutenant.name}】休息"

    @classmethod
    def set_position(cls, lieutenant, position):
        """Set lieutenant position (front/back)."""
        if position not in ('front', 'back'):
            return False, "无效位置"
        lieutenant.position = position
        db.session.commit()
        position_name = '前置' if position == 'front' else '后置'
        return True, f"副将【{lieutenant.name}】设为{position_name}"

    @classmethod
    def expand_skill_slots(cls, lieutenant):
        """Expand skill slots using 技能扩展符."""
        inv = DataService.get_inventory_item(lieutenant.owner_id, 'lt_skill_expand')
        if not inv or inv.quantity <= 0:
            return False, "没有副将技能扩展符"

        if lieutenant.skill_slots >= 8:
            return False, "技能位已满"

        DataService.remove_item_from_inventory(lieutenant.owner_id, 'lt_skill_expand', 1)
        lieutenant.skill_slots += 1
        db.session.commit()
        return True, f"技能位扩充至{lieutenant.skill_slots}个"

    @classmethod
    def learn_skill(cls, lieutenant, skill_id, level=1):
        """Learn a lieutenant skill at specified level using skill books."""
        sdef = LIEUTENANT_SKILLS.get(skill_id)
        if not sdef:
            return False, "技能不存在"

        # Check class requirement
        class_req = sdef.get('class_required')
        if class_req and lieutenant.class_type != class_req:
            return False, f"需要{CLASS_NAMES.get(class_req, class_req)}职业"

        skills = lieutenant.skills
        current_slots = len(skills)
        if current_slots >= lieutenant.skill_slots:
            return False, "技能位已满"

        # Check if skill already exists
        for sk in skills:
            if sk.get('id') == skill_id:
                return False, "已学习该技能"

        # Find the skill book for this level
        book_key = f'lt_skill_{skill_id}_{level}'
        book_info = SKILL_BOOK_IDS.get(book_key)
        if not book_info:
            return False, "技能书不存在"

        required_count = book_info['required_count']
        inv = DataService.get_inventory_item(lieutenant.owner_id, book_key)
        if not inv or inv.quantity < required_count:
            return False, f"需要{required_count}个{book_info['name']}"

        DataService.remove_item_from_inventory(lieutenant.owner_id, book_key, required_count)

        # Add skill
        skill_entry = {
            'id': skill_id,
            'name': sdef['name'],
            'type': sdef['type'],
            'level': level,
        }
        if sdef['type'] == 'passive':
            skill_entry['bonus_type'] = sdef['bonus_type']
            skill_entry['bonus_value'] = sdef['bonus_value'][level - 1]
        elif sdef['type'] == 'active':
            skill_entry['trigger_rate'] = sdef['trigger_rate'][level - 1]
            skill_entry['damage_rate'] = sdef['damage_rate'][level - 1]
        elif sdef['type'] == 'triggered':
            if 'absorb_rate' in sdef:
                skill_entry['absorb_rate'] = sdef['absorb_rate'][level - 1]
            elif 'heal_rate' in sdef:
                skill_entry['heal_rate'] = sdef['heal_rate'][level - 1]
            skill_entry['trigger_rate'] = sdef['trigger_rate'][level - 1]

        skills.append(skill_entry)
        lieutenant.skills = skills
        db.session.commit()
        return True, f"学习了技能【{sdef['name']}{level}级】"

    @classmethod
    def upgrade_skill(cls, lieutenant, skill_id):
        """Upgrade a lieutenant skill to next level."""
        sdef = LIEUTENANT_SKILLS.get(skill_id)
        if not sdef:
            return False, "技能不存在"

        skills = lieutenant.skills
        skill_idx = None
        for i, sk in enumerate(skills):
            if sk.get('id') == skill_id:
                skill_idx = i
                break

        if skill_idx is None:
            return False, "未学习该技能"

        current_level = skills[skill_idx].get('level', 1)
        next_level = current_level + 1
        if next_level > sdef['max_level']:
            return False, "技能已满级"

        # Find the skill book for the next level
        book_key = f'lt_skill_{skill_id}_{next_level}'
        book_info = SKILL_BOOK_IDS.get(book_key)
        if not book_info:
            return False, "技能书不存在"

        required_count = book_info['required_count']
        inv = DataService.get_inventory_item(lieutenant.owner_id, book_key)
        if not inv or inv.quantity < required_count:
            return False, f"需要{required_count}个{book_info['name']}"

        DataService.remove_item_from_inventory(lieutenant.owner_id, book_key, required_count)

        # Update skill
        skills[skill_idx]['level'] = next_level
        if sdef['type'] == 'passive':
            skills[skill_idx]['bonus_value'] = sdef['bonus_value'][next_level - 1]
        elif sdef['type'] == 'active':
            skills[skill_idx]['trigger_rate'] = sdef['trigger_rate'][next_level - 1]
            skills[skill_idx]['damage_rate'] = sdef['damage_rate'][next_level - 1]
        elif sdef['type'] == 'triggered':
            if 'absorb_rate' in sdef:
                skills[skill_idx]['absorb_rate'] = sdef['absorb_rate'][next_level - 1]
            elif 'heal_rate' in sdef:
                skills[skill_idx]['heal_rate'] = sdef['heal_rate'][next_level - 1]
            skills[skill_idx]['trigger_rate'] = sdef['trigger_rate'][next_level - 1]

        lieutenant.skills = skills
        db.session.commit()
        level_names = ['入门', '进阶', '精通']
        return True, f"技能【{sdef['name']}】升级至{level_names[next_level-1]}({next_level}级)"

    @classmethod
    def forget_skill(cls, lieutenant, skill_id):
        """Forget a lieutenant skill."""
        skills = lieutenant.skills
        new_skills = [sk for sk in skills if sk.get('id') != skill_id]
        if len(new_skills) == len(skills):
            return False, "未学习该技能"
        lieutenant.skills = new_skills
        db.session.commit()
        return True, "已遗忘该技能"

    @classmethod
    def handle_death(cls, lieutenant, owner_died=False):
        """Handle lieutenant death in battle.

        Args:
            lieutenant: The lieutenant that died
            owner_died: If True, owner died (back position loses loyalty)
                       If False, lieutenant died in front (loses lifespan)
        """
        lieutenant.is_alive = False
        lieutenant.current_health = 0
        lieutenant.is_deployed = False  # Auto rest

        if owner_died:
            # Back position - owner died, lose loyalty
            lieutenant.loyalty = max(0, lieutenant.loyalty - LOYALTY_DEATH_LOSS)
        else:
            # Front position - lieutenant killed, lose lifespan
            lieutenant.lifespan = max(0, lieutenant.lifespan - LIFESPAN_DEATH_LOSS)
        db.session.commit()

    @classmethod
    def revive(cls, lieutenant):
        """Revive lieutenant with health=1."""
        lieutenant.is_alive = True
        lieutenant.current_health = 1
        lieutenant.current_mana = min(lieutenant.current_mana, lieutenant.get_max_mana())
        db.session.commit()

    @classmethod
    def heal(cls, lieutenant, amount):
        """Heal lieutenant."""
        if not lieutenant.is_alive:
            lieutenant.is_alive = True
            lieutenant.current_health = 1
        lieutenant.current_health = min(lieutenant.get_max_health(), lieutenant.current_health + amount)
        db.session.commit()

    @classmethod
    def restore_mana(cls, lieutenant, amount):
        """Restore lieutenant mana."""
        lieutenant.current_mana = min(lieutenant.get_max_mana(), lieutenant.current_mana + amount)
        db.session.commit()

    @classmethod
    def gain_experience(cls, lieutenant, exp):
        """Give experience to lieutenant, auto level up."""
        lieutenant.experience += exp
        while lieutenant.experience >= cls._exp_to_next(lieutenant.level):
            lieutenant.experience -= cls._exp_to_next(lieutenant.level)
            lieutenant.level += 1
            lieutenant.current_health = lieutenant.get_max_health()
            lieutenant.current_mana = lieutenant.get_max_mana()
        db.session.commit()

    @classmethod
    def _exp_to_next(cls, level):
        return 50 + level * 30

    @classmethod
    def get_available_skills(cls, lieutenant):
        """Get skills available for this lieutenant to learn."""
        available = {}
        for sid, sdef in LIEUTENANT_SKILLS.items():
            class_req = sdef.get('class_required')
            if class_req and lieutenant.class_type != class_req:
                continue
            # Check if already learned
            learned = any(sk.get('id') == sid for sk in lieutenant.skills)
            if learned:
                continue
            available[sid] = sdef
        return available

    @classmethod
    def get_lt_skill_def(cls, skill_id):
        return LIEUTENANT_SKILLS.get(skill_id)

    @classmethod
    def get_all_skill_defs(cls):
        return LIEUTENANT_SKILLS

    @classmethod
    def get_skill_book_info(cls, book_key):
        return SKILL_BOOK_IDS.get(book_key)