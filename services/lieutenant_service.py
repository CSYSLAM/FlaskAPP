"""Lieutenant (副将) companion service."""
import random
import json
from services import db
from services.data_service import DataService
from models.lieutenant import Lieutenant, QUALITY_NAMES, QUALITY_MULTIPLIER, CLASS_NAMES, GENDER_NAMES, TIER_NAMES, TIER_FRAGMENTS


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
        'dianwei': {'name': '典韦', 'gender': 'male', 'class_type': 'warrior'},
        'huangzhong': {'name': '黄忠', 'gender': 'male', 'class_type': 'assassin'},
        'pangtong': {'name': '庞统', 'gender': 'male', 'class_type': 'mage'},
        'xunyu': {'name': '荀彧', 'gender': 'male', 'class_type': 'mage'},
        'zhouyu': {'name': '周瑜', 'gender': 'male', 'class_type': 'mage'},
        'diaochan': {'name': '貂蝉', 'gender': 'female', 'class_type': 'assassin'},
        'guojia': {'name': '郭嘉', 'gender': 'male', 'class_type': 'mage'},
        'machao': {'name': '马超', 'gender': 'male', 'class_type': 'assassin'},
        'liru': {'name': '李儒', 'gender': 'male', 'class_type': 'mage'},
        'xuchu': {'name': '许褚', 'gender': 'male', 'class_type': 'warrior'},
        'dengai': {'name': '邓艾', 'gender': 'male', 'class_type': 'assassin'},
        'taishici': {'name': '太史慈', 'gender': 'male', 'class_type': 'assassin'},
    },
    2: {
        'xiaoqiao': {'name': '小乔', 'gender': 'female', 'class_type': 'mage'},
        'zhugejin': {'name': '诸葛瑾', 'gender': 'male', 'class_type': 'mage'},
        'sunliang': {'name': '孙亮', 'gender': 'male', 'class_type': 'warrior'},
        'liufeng': {'name': '刘封', 'gender': 'male', 'class_type': 'warrior'},
        'jiangwan': {'name': '蒋琬', 'gender': 'male', 'class_type': 'mage'},
        'manchong': {'name': '满宠', 'gender': 'male', 'class_type': 'mage'},
        'daqiao': {'name': '大乔', 'gender': 'female', 'class_type': 'mage'},
        'guanping': {'name': '关平', 'gender': 'male', 'class_type': 'warrior'},
        'caozhen': {'name': '曹真', 'gender': 'male', 'class_type': 'warrior'},
        'pangde': {'name': '庞德', 'gender': 'male', 'class_type': 'warrior'},
        'caiwenji': {'name': '蔡文姬', 'gender': 'female', 'class_type': 'mage'},
        'mayunlu': {'name': '马云禄', 'gender': 'female', 'class_type': 'warrior'},
        'dengzhong': {'name': '邓忠', 'gender': 'male', 'class_type': 'warrior'},
    },
    3: {
        'adou': {'name': '阿斗', 'gender': 'male', 'class_type': 'warrior'},
        'liaohua': {'name': '廖化', 'gender': 'male', 'class_type': 'warrior'},
        'lvkuang': {'name': '吕旷', 'gender': 'male', 'class_type': 'warrior'},
        'zhaoguang': {'name': '赵广', 'gender': 'male', 'class_type': 'assassin'},
        'xuyou': {'name': '许攸', 'gender': 'male', 'class_type': 'mage'},
        'wuguotai': {'name': '吴国太', 'gender': 'female', 'class_type': 'mage'},
        'zhenji': {'name': '甄姬', 'gender': 'female', 'class_type': 'mage'},
        'zhangxiu': {'name': '张绣', 'gender': 'male', 'class_type': 'warrior'},
        'wangmeiren': {'name': '王美人', 'gender': 'female', 'class_type': 'mage'},
        'yuejin': {'name': '乐进', 'gender': 'male', 'class_type': 'warrior'},
        'matie': {'name': '马铁', 'gender': 'male', 'class_type': 'warrior'},
        'xiahouba': {'name': '夏侯霸', 'gender': 'male', 'class_type': 'warrior'},
        'dongbai': {'name': '董白', 'gender': 'female', 'class_type': 'assassin'},
    },
}

# Soul item_id -> (tier, pinyin_id) mapping
SOUL_TO_LT = {}
for tier, data in LIEUTENANT_DATA.items():
    for pinyin_id in data:
        SOUL_TO_LT[f'soul_{pinyin_id}'] = (tier, pinyin_id)


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

    @classmethod
    def get_lieutenants(cls, player):
        return Lieutenant.query.filter_by(owner_id=player.id).all()

    @classmethod
    def get_deployed(cls, player):
        return Lieutenant.query.filter_by(owner_id=player.id, is_deployed=True).first()

    @classmethod
    def recruit(cls, player, method='token'):
        """Recruit a random NORMAL lieutenant (not a named 1-3 tier lieutenant).
        Normal lieutenants have no soul, no achievement, no tier.
        method: 'token' (use 1 recruitment_token) or 'gold' (pay 5000 gold)
        """
        max_slots = cls.get_max_slots(player)
        count = Lieutenant.query.filter_by(owner_id=player.id).count()
        if count >= max_slots:
            return None, "副将位已满"

        if method == 'token':
            inv = DataService.get_inventory_item(player.id, 'recruitment_token')
            if not inv or inv.quantity < 1:
                return None, "没有招募令"
            DataService.remove_item_from_inventory(player.id, 'recruitment_token', 1)
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
        DataService.add_item_to_inventory(player.id, 'soul_banner_fragment', fragments)
        db.session.commit()

        tier_name = TIER_NAMES.get(tier, '')
        return True, f"分解{tier_name}魂魄【{lt_info['name']}】获得{fragments}个聚魂幡碎片"

    @classmethod
    def synthesize_banner(cls, player):
        """Synthesize 10 fragments into 1 soul banner."""
        inv = DataService.get_inventory_item(player.id, 'soul_banner_fragment')
        if not inv or inv.quantity < SYNTHESIZE_FRAGMENTS:
            return False, f"聚魂幡碎片不足（需要{SYNTHESIZE_FRAGMENTS}个）"

        DataService.remove_item_from_inventory(player.id, 'soul_banner_fragment', SYNTHESIZE_FRAGMENTS)
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
            tier=tier,
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
        inv = DataService.get_inventory_item(lieutenant.owner_id, 'lt_quality_pill')
        if not inv or inv.quantity <= 0:
            return False, "没有副将资质丹"
        DataService.remove_item_from_inventory(lieutenant.owner_id, 'lt_quality_pill', 1)

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
        skills = lieutenant.skills
        new_skills = [sk for sk in skills if sk.get('id') != skill_id]
        if len(new_skills) == len(skills):
            return False, "未学习该技能"
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
