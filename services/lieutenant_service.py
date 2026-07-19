"""Lieutenant (副将) companion service."""
import random
import json
import os
from services import db
from services.data_service import DataService
from models.lieutenant import Lieutenant, QUALITY_NAMES, CLASS_NAMES, GENDER_NAMES, TIER_NAMES, TIER_FRAGMENTS


# 副将技能定义持久化文件：工作台修改技能倍率/魔法消耗时写入此文件，启动时加载覆盖默认值
LIEUTENANT_SKILLS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), 'data', 'lieutenant_skills.json')


# Normal lieutenant name pools (not part of the 1-3 tier system, no soul/achievement)
NORMAL_LIEUTENANT_NAMES = {
    'male_warrior': ['李通', '郝萌', '曹性', '成廉', '魏越', '侯成', '宋宪', '魏续', '韩浩', '史涣'],
    'male_mage': ['王楷', '许汜', '张超', '陈琳', '阮瑀', '刘馥', '王粲', '徐干', '杨修', '应玚'],
    'male_assassin': ['胡车儿', '秦朗', '吴硕', '耿纪', '韦晃', '金祎', '吉邈', '吉穆', '秦庆童', '苗泽'],
    'female_warrior': ['赵娥', '李姬', '孙氏', '徐氏', '杜氏'],
    'female_mage': ['樊氏', '邹氏', '尹氏', '何氏', '唐姬'],
    'female_assassin': ['郭氏', '曹节', '伏寿', '董贵妃', '刘氏'],
}

# Tier-based lieutenant data: {tier: {pinyin_id: {'name': '中文名', 'gender': 'male'/'female', 'class_type': 'warrior'/'mage'/'assassin'}}}
LIEUTENANT_DATA = {
    1: {
        'taishici': {'name': '太史慈', 'gender': 'male', 'class_type': 'mage',
                     'base_max_health': 105, 'base_max_mana': 112, 'base_attack': 22, 'base_defense': 57,
                     'base_crit_rate': 0.00120, 'base_dodge_rate': 0.00090},
        'xuchu': {'name': '许褚', 'gender': 'male', 'class_type': 'warrior',
                  'base_max_health': 126, 'base_max_mana': 37, 'base_attack': 19, 'base_defense': 71,
                  'base_crit_rate': 0.00116, 'base_dodge_rate': 0.00086},
        'zhouyu': {'name': '周瑜', 'gender': 'male', 'class_type': 'assassin',
                   'base_max_health': 117, 'base_max_mana': 60, 'base_attack': 21, 'base_defense': 62,
                   'base_crit_rate': 0.00150, 'base_dodge_rate': 0.00112},
    },
    2: {
        'guanping': {'name': '关平', 'gender': 'male', 'class_type': 'mage',
                     'base_max_health': 78, 'base_max_mana': 150, 'base_attack': 17, 'base_defense': 42,
                     'base_crit_rate': 0.00110, 'base_dodge_rate': 0.00085},
        'caozhen': {'name': '曹真', 'gender': 'male', 'class_type': 'warrior',
                    'base_max_health': 94, 'base_max_mana': 50, 'base_attack': 14, 'base_defense': 53,
                    'base_crit_rate': 0.00110, 'base_dodge_rate': 0.00085},
        'xiaoqiao': {'name': '小乔', 'gender': 'female', 'class_type': 'assassin',
                     'base_max_health': 87, 'base_max_mana': 80, 'base_attack': 16, 'base_defense': 46,
                     'base_crit_rate': 0.00135, 'base_dodge_rate': 0.00105},
        'daqiao': {'name': '大乔', 'gender': 'female', 'class_type': 'mage',
                   'base_max_health': 78, 'base_max_mana': 150, 'base_attack': 17, 'base_defense': 42,
                   'base_crit_rate': 0.00110, 'base_dodge_rate': 0.00085},
        'pangde': {'name': '庞德', 'gender': 'male', 'class_type': 'warrior',
                   'base_max_health': 94, 'base_max_mana': 50, 'base_attack': 14, 'base_defense': 53,
                   'base_crit_rate': 0.00110, 'base_dodge_rate': 0.00085},
        'liufeng': {'name': '刘封', 'gender': 'male', 'class_type': 'assassin',
                    'base_max_health': 87, 'base_max_mana': 80, 'base_attack': 16, 'base_defense': 48,
                    'base_crit_rate': 0.00135, 'base_dodge_rate': 0.00105},
    },
    3: {
        'adou': {'name': '阿斗', 'gender': 'male', 'class_type': 'mage',
                 'base_max_health': 39, 'base_max_mana': 150, 'base_attack': 9, 'base_defense': 21,
                 'base_crit_rate': 0.00070, 'base_dodge_rate': 0.00055},
        'liaohua': {'name': '廖化', 'gender': 'male', 'class_type': 'warrior',
                    'base_max_health': 47, 'base_max_mana': 50, 'base_attack': 7, 'base_defense': 26,
                    'base_crit_rate': 0.00075, 'base_dodge_rate': 0.00060},
        'xiahouba': {'name': '夏侯霸', 'gender': 'male', 'class_type': 'assassin',
                     'base_max_health': 43, 'base_max_mana': 80, 'base_attack': 8, 'base_defense': 23,
                     'base_crit_rate': 0.00090, 'base_dodge_rate': 0.00072},
        'zhaoguang': {'name': '赵广', 'gender': 'male', 'class_type': 'warrior',
                      'base_max_health': 39, 'base_max_mana': 50, 'base_attack': 9, 'base_defense': 21,
                      'base_crit_rate': 0.00070, 'base_dodge_rate': 0.00055},
        'wuguotai': {'name': '吴国太', 'gender': 'female', 'class_type': 'warrior',
                     'base_max_health': 47, 'base_max_mana': 50, 'base_attack': 7, 'base_defense': 26,
                     'base_crit_rate': 0.00075, 'base_dodge_rate': 0.00060},
        'zhenji': {'name': '甄姬', 'gender': 'female', 'class_type': 'assassin',
                   'base_max_health': 43, 'base_max_mana': 80, 'base_attack': 8, 'base_defense': 23,
                   'base_crit_rate': 0.00090, 'base_dodge_rate': 0.00072},
        'wangmeiren': {'name': '王美人', 'gender': 'female', 'class_type': 'mage',
                       'base_max_health': 39, 'base_max_mana': 150, 'base_attack': 9, 'base_defense': 21,
                       'base_crit_rate': 0.00070, 'base_dodge_rate': 0.00055},
        'xuyou': {'name': '许攸', 'gender': 'male', 'class_type': 'warrior',
                  'base_max_health': 47, 'base_max_mana': 50, 'base_attack': 7, 'base_defense': 26,
                  'base_crit_rate': 0.00075, 'base_dodge_rate': 0.00060},
        'yuejin': {'name': '乐进', 'gender': 'male', 'class_type': 'assassin',
                   'base_max_health': 43, 'base_max_mana': 80, 'base_attack': 8, 'base_defense': 23,
                   'base_crit_rate': 0.00090, 'base_dodge_rate': 0.00072},
    },
}

# Soul item_id -> (tier, pinyin_id) mapping
SOUL_TO_LT = {}
for tier, data in LIEUTENANT_DATA.items():
    for pinyin_id in data:
        SOUL_TO_LT[f'soul_{pinyin_id}'] = (tier, pinyin_id)


# 副将技能默认定义(代码内兜底)；工作台可覆盖并持久化到 lieutenant_skills.json
_DEFAULT_LIEUTENANT_SKILLS = {
    # ---- 主动技能 active：战斗中按 trigger_rate 概率释放，消耗 mana_cost 蓝量；
    #   蓝量不足则降级为普通攻击。伤害一律走 BattleService._compute_damage 统一公式。----
    'combo': {'name': '连击', 'type': 'active', 'class_required': 'assassin',
              'max_level': 3, 'trigger_rate': [12, 18, 24],
              'mana_cost': [40, 70, 100],
              'hits': 2,                  # 打两次，每次独立计算伤害(系数1.0)
              'description': '连续两次攻击，每次独立结算伤害(参考刺客二连击)'},
    'smash': {'name': '猛击', 'type': 'active', 'class_required': 'warrior',
              'max_level': 3, 'trigger_rate': [12, 18, 24],
              'mana_cost': [30, 50, 80],
              'atk_buff_rate': 0.5,       # 本回合攻击 +50%
              'def_debuff_rounds': 2,     # 副将自身下2回合防御减半
              'damage_rate': [1.2, 1.5, 1.8],
              'description': '本回合攻击+50%造成大量伤害，自身下2回合防御减半'},
    'thunder': {'name': '天雷', 'type': 'active', 'class_required': 'mage',
                'max_level': 3, 'trigger_rate': [12, 18, 24],
                'mana_cost': [120, 200, 300],   # 大量魔法
                'damage_rate': [2.0, 2.8, 3.6], # 巨额伤害(高系数)
                'description': '消耗大量魔法造成巨额伤害'},
    # ---- 触发技能 triggered：主人受击时按 trigger_rate 触发，前后置都可触发；按职业限定。----
    'absorb': {'name': '吸收', 'type': 'triggered', 'class_required': 'assassin',
               'max_level': 3, 'trigger_rate': [12, 18, 24],
               'absorb_rate': [10, 15, 20],     # 主人受击时吸收伤害的百分比
               'description': '刺客专属：主人受击时有几率吸收10/15/20%伤害'},
    'heal_trigger': {'name': '回春', 'type': 'triggered', 'class_required': 'warrior',
                     'max_level': 3, 'trigger_rate': [10, 15, 20],
                     'heal_rate': [5, 8, 12],   # 回复主人生命上限的百分比
                     'description': '战士专属：战斗中有几率回复主人生命'},
    'magic_shield': {'name': '法相', 'type': 'triggered', 'class_required': 'mage',
                     'max_level': 3, 'trigger_rate': [10, 15, 20],
                     'shield_rate': [0.4, 0.6, 0.8],  # 护盾 = 主人当前魔法 × shield_rate
                     'description': '术士专属：本回合主人获得护盾(主人当前魔法×40/60/80%)抵消伤害，溢出消失'},
    # ---- 被动技能 passive：出战即给主人加成(不变) ----
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


def _load_lieutenant_skills():
    """加载副将技能定义：优先读 data/lieutenant_skills.json(工作台持久化)，
    读取失败或字段缺失时用 _DEFAULT_LIEUTENANT_SKILLS 兜底，保证新增字段总有值。"""
    skills = {sid: dict(sdef) for sid, sdef in _DEFAULT_LIEUTENANT_SKILLS.items()}
    try:
        if os.path.exists(LIEUTENANT_SKILLS_FILE):
            with open(LIEUTENANT_SKILLS_FILE, encoding='utf-8') as f:
                saved = json.load(f)
            for sid, sdef in saved.items():
                if sid in skills:
                    merged = dict(skills[sid])
                    merged.update(sdef)
                    skills[sid] = merged
    except (json.JSONDecodeError, OSError):
        pass
    return skills


def save_lieutenant_skills(skills_data):
    """工作台调用：把完整技能定义写入 JSON 文件持久化。"""
    with open(LIEUTENANT_SKILLS_FILE, 'w', encoding='utf-8') as f:
        json.dump(skills_data, f, ensure_ascii=False, indent=2)
        f.write('\n')


def reset_lieutenant_skills():
    """工作台调用：删除持久化文件，恢复代码默认值。返回默认定义。"""
    try:
        if os.path.exists(LIEUTENANT_SKILLS_FILE):
            os.remove(LIEUTENANT_SKILLS_FILE)
    except OSError:
        pass
    return {sid: dict(sdef) for sid, sdef in _DEFAULT_LIEUTENANT_SKILLS.items()}


LIEUTENANT_SKILLS = _load_lieutenant_skills()

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
RECRUIT_GOLD_COST = 5000
DECOMPOSE_GOLD_COST = 5000
SYNTHESIZE_FRAGMENTS = 10


class LieutenantService:

    @staticmethod
    def _fill_skill_fields(sdef, entry, level):
        """按技能类型把 sdef 里对应等级的数值字段写进 entry(技能实例)。
        learn/upgrade 共用，保证战斗读取的字段一致。"""
        entry['type'] = sdef['type']
        entry['level'] = level
        if sdef['type'] == 'passive':
            entry['bonus_type'] = sdef['bonus_type']
            entry['bonus_value'] = sdef['bonus_value'][level - 1]
        elif sdef['type'] == 'active':
            entry['trigger_rate'] = sdef['trigger_rate'][level - 1]
            entry['mana_cost'] = sdef['mana_cost'][level - 1]
            if 'damage_rate' in sdef:
                entry['damage_rate'] = sdef['damage_rate'][level - 1]
            if 'hits' in sdef:
                entry['hits'] = sdef['hits']
            if 'atk_buff_rate' in sdef:
                entry['atk_buff_rate'] = sdef['atk_buff_rate']
            if 'def_debuff_rounds' in sdef:
                entry['def_debuff_rounds'] = sdef['def_debuff_rounds']
        elif sdef['type'] == 'triggered':
            if 'absorb_rate' in sdef:
                entry['absorb_rate'] = sdef['absorb_rate'][level - 1]
            elif 'heal_rate' in sdef:
                entry['heal_rate'] = sdef['heal_rate'][level - 1]
            elif 'shield_rate' in sdef:
                entry['shield_rate'] = sdef['shield_rate'][level - 1]
        return entry

    @classmethod
    def get_lieutenants(cls, player):
        return Lieutenant.query.filter_by(owner_id=player.id, is_design_only=False).all()

    @classmethod
    def get_deployed(cls, player):
        return Lieutenant.query.filter_by(owner_id=player.id, is_deployed=True, is_design_only=False).first()

    @classmethod
    def recruit(cls, player, method='token'):
        """Recruit a random NORMAL lieutenant (not a named 1-3 tier lieutenant).
        Normal lieutenants have no soul, no achievement, no tier.
        method: 'token' (use 1 lt_recruit) or 'gold' (pay 5000 gold)
        """
        max_slots = cls.get_max_slots(player)
        count = Lieutenant.query.filter_by(owner_id=player.id).count()
        if count >= max_slots:
            return None, "副将位已满"

        if method == 'token':
            inv = DataService.get_inventory_item(player.id, 'lt_recruit')
            if not inv or inv.quantity < 1:
                return None, "没有招募令"
            DataService.remove_item_from_inventory(player.id, 'lt_recruit', 1)
        else:
            if player.gold < RECRUIT_GOLD_COST:
                return None, f"银两不足（需要{RECRUIT_GOLD_COST}银两）"
            player.gold -= RECRUIT_GOLD_COST

        # Random gender and class
        gender = random.choice(['male', 'female'])
        class_type = random.choice(['warrior', 'mage', 'assassin'])
        name_pool = NORMAL_LIEUTENANT_NAMES.get(f'{gender}_{class_type}', ['副将'])
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
            tier=0,
        )
        lt.current_health = lt.get_max_health()
        lt.current_mana = lt.get_max_mana()
        lt.is_alive = True

        db.session.add(lt)
        db.session.commit()
        return lt, f"招募了副将【{name}】({lt.quality_name}{lt.class_name})"

    @classmethod
    def expand_slots(cls, player):
        inv = DataService.get_inventory_item(player.id, 'lt_slot_expand')
        if not inv or inv.quantity <= 0:
            return False, "没有副将扩充符"
        data = player.activity_data
        current_max = data.get('lieutenant_max', MAX_LIEUTENANT_SLOTS)
        DataService.remove_item_from_inventory(player.id, 'lt_slot_expand', 1)
        data['lieutenant_max'] = current_max + 1
        player.activity_data = data
        db.session.commit()
        return True, f"副将位扩充至{data['lieutenant_max']}个"

    @classmethod
    def get_max_slots(cls, player):
        data = player.activity_data
        return data.get('lieutenant_max', MAX_LIEUTENANT_SLOTS)

    @classmethod
    def banish(cls, lieutenant):
        """Banish/expel a lieutenant."""
        if lieutenant.is_deployed:
            return False, "请先让副将休息"
        name = lieutenant.name
        db.session.delete(lieutenant)
        db.session.commit()
        return True, f"已放逐副将【{name}】"

    @classmethod
    def get_player_souls(cls, player):
        """Get all soul items in player's inventory, grouped by tier."""
        inventory = DataService.get_inventory(player.id)
        souls = {1: [], 2: [], 3: []}
        for inv in inventory:
            if inv.item_id.startswith('soul_') and inv.item_id in SOUL_TO_LT:
                tier, pinyin_id = SOUL_TO_LT[inv.item_id]
                lt_info = LIEUTENANT_DATA[tier][pinyin_id]
                souls[tier].append({
                    'item_id': inv.item_id,
                    'name': lt_info['name'],
                    'quantity': inv.quantity,
                    'fragments': TIER_FRAGMENTS[tier],
                })
        for tier in souls:
            souls[tier].sort(key=lambda x: x['name'])
        return souls

    @classmethod
    def decompose_soul(cls, player, soul_item_id):
        """Decompose a soul into soul banner fragments."""
        if soul_item_id not in SOUL_TO_LT:
            return False, "无效的魂魄"
        if player.gold < DECOMPOSE_GOLD_COST:
            return False, f"银两不足（需要{DECOMPOSE_GOLD_COST}银两）"

        inv = DataService.get_inventory_item(player.id, soul_item_id)
        if not inv or inv.quantity < 1:
            return False, "魂魄数量不足"

        tier, pinyin_id = SOUL_TO_LT[soul_item_id]
        fragments = TIER_FRAGMENTS[tier]
        lt_info = LIEUTENANT_DATA[tier][pinyin_id]

        DataService.remove_item_from_inventory(player.id, soul_item_id, 1)
        player.gold -= DECOMPOSE_GOLD_COST
        DataService.add_item_to_inventory(player.id, 'soul_flag_shard', fragments)
        db.session.commit()

        tier_name = TIER_NAMES.get(tier, '')
        return True, f"分解{tier_name}魂魄【{lt_info['name']}】获得{fragments}个聚魂幡碎片"

    @classmethod
    def synthesize_banner(cls, player):
        """Synthesize 10 fragments into 1 soul banner."""
        inv = DataService.get_inventory_item(player.id, 'soul_flag_shard')
        if not inv or inv.quantity < SYNTHESIZE_FRAGMENTS:
            return False, f"聚魂幡碎片不足（需要{SYNTHESIZE_FRAGMENTS}个）"

        DataService.remove_item_from_inventory(player.id, 'soul_flag_shard', SYNTHESIZE_FRAGMENTS)
        DataService.add_item_to_inventory(player.id, 'soul_banner', 1)
        db.session.commit()
        return True, f"使用{SYNTHESIZE_FRAGMENTS}个聚魂幡碎片合成了1个聚魂幡"

    @classmethod
    def use_soul_banner(cls, player):
        """Use soul banner to get a random soul."""
        inv = DataService.get_inventory_item(player.id, 'soul_banner')
        if not inv or inv.quantity < 1:
            return False, "没有聚魂幡"

        DataService.remove_item_from_inventory(player.id, 'soul_banner', 1)

        roll = random.randint(1, 100)
        if roll <= 80:
            tier = 3
        elif roll <= 99:
            tier = 2
        else:
            tier = 1

        candidates = LIEUTENANT_DATA[tier]
        pinyin_id = random.choice(list(candidates.keys()))
        lt_info = candidates[pinyin_id]
        soul_item_id = f'soul_{pinyin_id}'

        DataService.add_item_to_inventory(player.id, soul_item_id, 1)
        db.session.commit()

        tier_name = TIER_NAMES.get(tier, '')
        DataService.broadcast_system(f"{player.nickname}通过副将聚魂获得了{tier_name}魂魄【{lt_info['name']}】")
        return True, f"获得{tier_name}魂魄【{lt_info['name']}】"

    @classmethod
    def use_soul(cls, player, soul_item_id):
        """Use a soul to obtain the corresponding lieutenant."""
        if soul_item_id not in SOUL_TO_LT:
            return False, "无效的魂魄"

        tier, pinyin_id = SOUL_TO_LT[soul_item_id]
        success, msg = cls.grant_lieutenant_from_soul(player, tier, pinyin_id)
        if not success:
            return False, msg

        # Consume the soul item
        inv = DataService.get_inventory_item(player.id, soul_item_id)
        if not inv or inv.quantity < 1:
            return False, "魂魄数量不足"

        DataService.remove_item_from_inventory(player.id, soul_item_id, 1)

        db.session.commit()

        lt_info = LIEUTENANT_DATA[tier][pinyin_id]
        tier_name = TIER_NAMES.get(tier, '')
        return True, f"获得{tier_name}副将【{lt_info['name']}】"

    @classmethod
    def grant_lieutenant_from_soul(cls, player, tier, pinyin_id):
        """Grant a tiered lieutenant from a soul. Does NOT consume the soul item."""
        if tier not in LIEUTENANT_DATA or pinyin_id not in LIEUTENANT_DATA[tier]:
            return False, "副将数据不存在"

        lt_info = LIEUTENANT_DATA[tier][pinyin_id]

        max_slots = cls.get_max_slots(player)
        count = Lieutenant.query.filter_by(owner_id=player.id).count()
        if count >= max_slots:
            return False, "副将位已满"

        existing = Lieutenant.query.filter_by(owner_id=player.id, name=lt_info['name']).first()
        if existing:
            return False, f"已拥有副将【{lt_info['name']}】"

        lt = Lieutenant(
            owner_id=player.id,
            name=lt_info['name'],
            gender=lt_info['gender'],
            class_type=lt_info['class_type'],
            quality=random.randint(0, 9),  # 普通档0-9随机
            enlightenment=0,
            reinforce=0,
            loyalty=80,
            lifespan=100,
            level=1,
            position='front',
            is_deployed=False,
            skills_raw='[]',
            skill_slots=3,
            tier=tier,
            # 从LIEUTENANT_DATA取基础属性(自定义值优先于CLASS_BASE_STATS)
            base_max_health=lt_info.get('base_max_health'),
            base_max_mana=lt_info.get('base_max_mana'),
            base_attack=lt_info.get('base_attack'),
            base_defense=lt_info.get('base_defense'),
            base_crit_rate=lt_info.get('base_crit_rate'),
            base_dodge_rate=lt_info.get('base_dodge_rate'),
        )
        lt.current_health = lt.get_max_health()
        lt.current_mana = lt.get_max_mana()
        lt.is_alive = True

        db.session.add(lt)
        db.session.flush()

        from services.achievement_service import AchievementService
        AchievementService.check(player, 'lieutenant_owned')

        return True, "ok"

    @classmethod
    def _get_lt_info(cls, tier, pinyin_id):
        """Get lieutenant info dict for a given tier and pinyin_id."""
        return LIEUTENANT_DATA.get(tier, {}).get(pinyin_id, {})

    @classmethod
    def _count_owned(cls, player):
        return Lieutenant.query.filter_by(owner_id=player.id).count()

    @classmethod
    def has_lieutenant_by_name(cls, player, name):
        return Lieutenant.query.filter_by(owner_id=player.id, name=name).first() is not None

    @classmethod
    def wash_quality(cls, lieutenant):
        inv = DataService.get_inventory_item(lieutenant.owner_id, 'lt_aptitude')
        if not inv or inv.quantity <= 0:
            return False, "没有副将资质丹"
        DataService.remove_item_from_inventory(lieutenant.owner_id, 'lt_aptitude', 1)

        old_quality = lieutenant.quality
        new_quality = random.randint(0, 20)
        lieutenant.quality = new_quality

        max_hp = lieutenant.get_max_health()
        max_mp = lieutenant.get_max_mana()
        lieutenant.current_health = min(lieutenant.current_health, max_hp)
        lieutenant.current_mana = min(lieutenant.current_mana, max_mp)

        db.session.commit()
        return True, f"资质从{QUALITY_NAMES.get(old_quality, '普通')}变为{lieutenant.quality_name}"

    @classmethod
    def enlighten(cls, lieutenant):
        inv = DataService.get_inventory_item(lieutenant.owner_id, 'lt_wuxing')
        if not inv or inv.quantity <= 0:
            return False, "没有副将悟性丹"

        if lieutenant.enlightenment >= 10:
            return False, "悟性已达上限"

        DataService.remove_item_from_inventory(lieutenant.owner_id, 'lt_wuxing', 1)

        success_rate = max(0.06, (1.0 - lieutenant.enlightenment * 0.07) / 5)
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
        inv = DataService.get_inventory_item(lieutenant.owner_id, 'lt_enhance')
        if not inv or inv.quantity <= 0:
            return False, "没有副将强化丹"

        if lieutenant.reinforce >= 20:
            return False, "强化已达上限"

        DataService.remove_item_from_inventory(lieutenant.owner_id, 'lt_enhance', 1)

        success_rate = max(0.06, (0.95 - lieutenant.reinforce * 0.03) / 5)
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
        inv = DataService.get_inventory_item(lieutenant.owner_id, 'lt_loyalty')
        if not inv or inv.quantity <= 0:
            return False, "没有副将忠诚丹"

        if lieutenant.loyalty >= 100:            return False, "忠诚度已满"

        DataService.remove_item_from_inventory(lieutenant.owner_id, 'lt_loyalty', 1)
        lieutenant.loyalty = min(100, lieutenant.loyalty + 20)
        db.session.commit()
        return True, f"忠诚度恢复至{lieutenant.loyalty}"

    @classmethod
    def restore_lifespan(cls, lieutenant):
        inv = DataService.get_inventory_item(lieutenant.owner_id, 'lt_life')
        if not inv or inv.quantity <= 0:
            return False, "没有副将寿命丹"

        if lieutenant.lifespan >= 100:
            return False, "寿命已满"

        DataService.remove_item_from_inventory(lieutenant.owner_id, 'lt_life', 1)
        lieutenant.lifespan = min(100, lieutenant.lifespan + 20)
        db.session.commit()
        return True, f"寿命恢复至{lieutenant.lifespan}"

    @classmethod
    def deploy(cls, lieutenant):
        can, msg = lieutenant.can_deploy()
        if not can:
            return False, msg

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
        lieutenant.is_deployed = False
        db.session.commit()
        return True, f"副将【{lieutenant.name}】休息"

    @classmethod
    def set_position(cls, lieutenant, position):
        if position not in ('front', 'back'):
            return False, "无效位置"
        lieutenant.position = position
        db.session.commit()
        position_name = '前置' if position == 'front' else '后置'
        return True, f"副将【{lieutenant.name}】设为{position_name}"

    @classmethod
    def expand_skill_slots(cls, lieutenant):
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
        sdef = LIEUTENANT_SKILLS.get(skill_id)
        if not sdef:
            return False, "技能不存在"

        class_req = sdef.get('class_required')
        if class_req and lieutenant.class_type != class_req:
            return False, f"需要{CLASS_NAMES.get(class_req, class_req)}职业"

        skills = lieutenant.skills
        current_slots = len(skills)
        if current_slots >= lieutenant.skill_slots:
            return False, "技能位已满"

        for sk in skills:
            if sk.get('id') == skill_id:
                return False, "已学习该技能"

        book_key = f'lt_skill_{skill_id}_{level}'
        book_info = SKILL_BOOK_IDS.get(book_key)
        if not book_info:
            return False, "技能书不存在"

        required_count = book_info['required_count']
        inv = DataService.get_inventory_item(lieutenant.owner_id, book_key)
        if not inv or inv.quantity < required_count:
            return False, f"需要{required_count}个{book_info['name']}"

        DataService.remove_item_from_inventory(lieutenant.owner_id, book_key, required_count)

        skill_entry = {
            'id': skill_id,
            'name': sdef['name'],
        }
        cls._fill_skill_fields(sdef, skill_entry, level)

        skills.append(skill_entry)
        lieutenant.skills = skills
        db.session.commit()
        return True, f"学习了技能【{sdef['name']}{level}级】"

    @classmethod
    def upgrade_skill(cls, lieutenant, skill_id):
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

        book_key = f'lt_skill_{skill_id}_{next_level}'
        book_info = SKILL_BOOK_IDS.get(book_key)
        if not book_info:
            return False, "技能书不存在"

        required_count = book_info['required_count']
        inv = DataService.get_inventory_item(lieutenant.owner_id, book_key)
        if not inv or inv.quantity < required_count:
            return False, f"需要{required_count}个{book_info['name']}"

        DataService.remove_item_from_inventory(lieutenant.owner_id, book_key, required_count)

        skills[skill_idx]['level'] = next_level
        cls._fill_skill_fields(sdef, skills[skill_idx], next_level)

        lieutenant.skills = skills
        db.session.commit()
        level_names = ['入门', '进阶', '精通']
        return True, f"技能【{sdef['name']}】升级至{level_names[next_level-1]}({next_level}级)"

    @classmethod
    def forget_skill(cls, lieutenant, skill_id):
        skills = lieutenant.skills
        new_skills = [sk for sk in skills if sk.get('id') != skill_id]
        if len(new_skills) == len(skills):
            return False, "未学习该技能"

        # 遗忘需要消耗 1 个遗忘之章(lt_forget_tome，由 50 个遗忘之章残页合成)
        inv = DataService.get_inventory_item(lieutenant.owner_id, 'lt_forget_tome')
        if not inv or inv.quantity < 1:
            return False, "没有遗忘之章(需50个遗忘之章残页合成)"
        DataService.remove_item_from_inventory(lieutenant.owner_id, 'lt_forget_tome', 1)

        lieutenant.skills = new_skills
        db.session.commit()
        return True, "已遗忘该技能"

    @classmethod
    def handle_death(cls, lieutenant, owner_died=False):
        lieutenant.is_alive = False
        lieutenant.current_health = 0
        lieutenant.is_deployed = False

        if owner_died:
            lieutenant.loyalty = max(0, lieutenant.loyalty - LOYALTY_DEATH_LOSS)
        else:
            lieutenant.lifespan = max(0, lieutenant.lifespan - LIFESPAN_DEATH_LOSS)
        db.session.commit()

    @classmethod
    def revive(cls, lieutenant):
        lieutenant.is_alive = True
        lieutenant.current_health = 1
        lieutenant.current_mana = min(lieutenant.current_mana, lieutenant.get_max_mana())
        db.session.commit()

    @classmethod
    def heal(cls, lieutenant, amount):
        if not lieutenant.is_alive:
            lieutenant.is_alive = True
            lieutenant.current_health = 1
        lieutenant.current_health = min(lieutenant.get_max_health(), lieutenant.current_health + amount)
        db.session.commit()

    @classmethod
    def restore_mana(cls, lieutenant, amount):
        lieutenant.current_mana = min(lieutenant.get_max_mana(), lieutenant.current_mana + amount)
        db.session.commit()

    @classmethod
    def gain_experience(cls, lieutenant, exp):
        """增加经验，不自动升级。经验满后需手动升级。"""
        if lieutenant.level >= 60:
            return  # 满级不再累计经验
        lieutenant.experience += exp
        db.session.commit()

    @classmethod
    def level_up(cls, lieutenant):
        """手动升级：经验满则升1级，多余经验保留。"""
        if lieutenant.level >= 60:
            return False, "副将已达最高等级"
        need = cls._exp_to_next(lieutenant.level)
        if lieutenant.experience < need:
            return False, f"经验不足，需要{need}，当前{lieutenant.experience}"
        lieutenant.experience -= need
        lieutenant.level += 1
        lieutenant.current_health = lieutenant.get_max_health()
        lieutenant.current_mana = lieutenant.get_max_mana()
        db.session.commit()
        return True, f"升级到{lieutenant.level}级，剩余经验{lieutenant.experience}"

    @classmethod
    def _exp_to_next(cls, level):
        return 50 + level * 30

    @classmethod
    def use_exp_pill(cls, lieutenant, item_id):
        """在副将界面使用经验丹，给指定副将加经验。"""
        PILL_EXP = {
            'lt_exp_low': 100,
            'lt_exp_mid': 250,
            'lt_exp_high': 500,
        }
        PILL_NAMES = {
            'lt_exp_low': '副将低级经验丹',
            'lt_exp_mid': '副将中级经验丹',
            'lt_exp_high': '副将高级经验丹',
        }
        exp_amount = PILL_EXP.get(item_id, 0)
        if exp_amount == 0:
            return False, "无效的经验丹"
        inv = DataService.get_inventory_item(lieutenant.owner_id, item_id)
        if not inv or inv.quantity <= 0:
            return False, f"没有{PILL_NAMES.get(item_id, '经验丹')}"
        if lieutenant.level >= 60:
            return False, "副将已达最高等级"
        DataService.remove_item_from_inventory(lieutenant.owner_id, item_id, 1)
        cls.gain_experience(lieutenant, exp_amount)
        # Track item usage for achievements
        from models.player import PlayerModel
        owner = PlayerModel.query.get(lieutenant.owner_id)
        if owner:
            usage = owner.item_usage
            usage[item_id] = usage.get(item_id, 0) + 1
            name_key = f"name:{PILL_NAMES[item_id]}"
            usage[name_key] = usage.get(name_key, 0) + 1
            owner.item_usage = usage
            from services.achievement_service import AchievementService
            AchievementService.check(owner, 'item_use')
        return True, f"消耗1颗{PILL_NAMES[item_id]}，经验+{exp_amount}"

    @classmethod
    def get_available_skills(cls, lieutenant):
        available = {}
        for sid, sdef in LIEUTENANT_SKILLS.items():
            class_req = sdef.get('class_required')
            if class_req and lieutenant.class_type != class_req:
                continue
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
