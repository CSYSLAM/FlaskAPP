import json
import os
from datetime import datetime, timedelta
from services import db
from services.data_service import DataService


class VipService:
    _config = None

    @classmethod
    def _load_config(cls):
        if cls._config is None:
            config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'vip_config.json')
            with open(config_path, 'r', encoding='utf-8') as f:
                cls._config = json.load(f)
        return cls._config

    @classmethod
    def get_vip_level_config(cls, level):
        config = cls._load_config()
        return config['vip_levels'].get(str(level))

    @classmethod
    def get_active_vip_level(cls, player):
        """Get player's active VIP level. Level is always at least 1, but 0 if expired."""
        if not player.vip_expire_time or datetime.utcnow() >= player.vip_expire_time:
            return 0
        return max(player.vip_level, 1)

    @classmethod
    def is_vip_active(cls, player):
        return cls.get_active_vip_level(player) > 0

    @classmethod
    def get_vip_remaining_time(cls, player):
        if not player.vip_expire_time:
            return timedelta(0)
        remaining = player.vip_expire_time - datetime.utcnow()
        return remaining if remaining > timedelta(0) else timedelta(0)

    @classmethod
    def use_zhuhouling(cls, player, item_id, is_bound=None):
        """Use a zhuhouling — only adds VIP duration, no exp."""
        item_data = DataService.get_item(item_id)
        if not item_data or item_data.get('type') != 'vip':
            return False, "不是诸侯令"

        inv = DataService.get_inventory_item(player.id, item_id, is_bound=is_bound)
        if not inv or inv.quantity <= 0:
            return False, "物品数量不足"

        effect = item_data.get('usage_effect', {})
        vip_days = effect.get('vip_days', 0)
        if vip_days <= 0:
            return False, "无效的诸侯令"

        bound = inv.is_bound
        DataService.remove_item_from_inventory(player.id, item_id, 1, is_bound=bound)

        # Extend VIP time
        now = datetime.utcnow()
        if player.vip_expire_time and player.vip_expire_time > now:
            player.vip_expire_time += timedelta(days=vip_days)
        else:
            player.vip_expire_time = now + timedelta(days=vip_days)

        db.session.commit()
        return True, f"获得{vip_days}天VIP特权"

    @classmethod
    def convert_days_to_exp(cls, player, count):
        """Convert VIP days to exp (1 day = 10 exp)."""
        remaining = cls.get_vip_remaining_time(player)
        total_days = remaining.total_seconds() / 86400.0
        if total_days < count:
            return False, f"诸侯时长不足{count}天(当前{int(total_days)}天)"

        player.vip_expire_time -= timedelta(days=count)
        player.vip_exp += count * 10
        db.session.commit()
        return True, f"消耗{count}天诸侯时长，获得{count * 10}VIP经验"

    @classmethod
    def can_upgrade_vip(cls, player):
        """Check if player can upgrade their VIP level."""
        current = player.vip_level
        if current >= 5:
            return False, "已满级"
        next_config = cls.get_vip_level_config(current + 1)
        if not next_config:
            return False, "已达上限"
        if player.vip_exp < next_config['required_exp']:
            return False, f"经验不足，需要{next_config['required_exp']}VIP经验"
        return True, None

    @classmethod
    def upgrade_vip(cls, player):
        """Manually upgrade VIP level by consuming required exp."""
        can, err = cls.can_upgrade_vip(player)
        if not can:
            return False, err

        old_level = player.vip_level
        new_level = old_level + 1
        next_config = cls.get_vip_level_config(new_level)
        cost_exp = next_config['required_exp']

        player.vip_level = new_level
        # Consume the required exp for this level; overflow stays
        player.vip_exp -= cost_exp

        # Grant title if applicable
        if next_config.get('title'):
            from services.title_service import TitleService
            title_id = next_config['title']
            title_type = 'prefix' if title_id.startswith('prefix') else 'suffix'
            TitleService.grant_title(player, title_id, title_type)

        # Check achievements
        from services.achievement_service import AchievementService
        AchievementService.check(player, 'vip_level', new_level)

        db.session.commit()
        return True, f"VIP等级提升至{new_level}级，消耗{cost_exp}VIP经验"

    @classmethod
    def claim_daily_exp(cls, player):
        """Claim 5 VIP daily exp. If exp is full (>= next level required), give silver instead."""
        if not cls.is_vip_active(player):
            return False, "VIP未生效"

        today = datetime.utcnow().strftime('%Y-%m-%d')
        claimed = player.vip_daily_claimed
        if claimed.get('exp') == today:
            return False, "今日已领取VIP经验"

        # Check if exp is full
        next_level = player.vip_level + 1
        next_config = cls.get_vip_level_config(next_level) if next_level <= 5 else None
        exp_full = False
        if next_config and player.vip_exp >= next_config['required_exp']:
            exp_full = True
        elif player.vip_level >= 5:
            exp_full = True

        if exp_full:
            # Give silver instead
            player.gold += 500
            claimed['exp'] = today
            player.vip_daily_claimed = claimed
            db.session.commit()
            return True, "经验已满，领取500银两"

        player.vip_exp += 5
        claimed['exp'] = today
        player.vip_daily_claimed = claimed
        db.session.commit()
        return True, "领取5VIP经验"

    @classmethod
    def claim_daily_gift(cls, player):
        """Claim daily VIP gift."""
        level = cls.get_active_vip_level(player)
        if level <= 0:
            return False, "VIP未生效"

        today = datetime.utcnow().strftime('%Y-%m-%d')
        claimed = player.vip_daily_claimed
        if claimed.get('gift') == today:
            return False, "今日已领取礼包"

        config = cls.get_vip_level_config(level)
        if not config or not config.get('daily_gift'):
            return False, "该等级没有每日礼包"

        items_msg = []
        for gift in config['daily_gift']:
            item_id = gift['item_id']
            qty = gift['quantity']
            DataService.add_item_to_inventory(player.id, item_id, qty)
            item_data = DataService.get_item(item_id)
            item_name = item_data.get('name', item_id) if item_data else item_id
            items_msg.append(f"{item_name}x{qty}")

        claimed['gift'] = today
        player.vip_daily_claimed = claimed
        db.session.commit()
        return True, f"领取成功：{' '.join(items_msg)}"

    @classmethod
    def get_stat_bonus_rate(cls, player):
        level = cls.get_active_vip_level(player)
        if level <= 0:
            return 0
        config = cls.get_vip_level_config(level)
        return config.get('stat_bonus_rate', 0) if config else 0

    @classmethod
    def get_exp_bonus_rate(cls, player):
        level = cls.get_active_vip_level(player)
        if level <= 0:
            return 0
        config = cls.get_vip_level_config(level)
        return config.get('exp_bonus_rate', 0) if config else 0

    @classmethod
    def has_free_teleport(cls, player):
        level = cls.get_active_vip_level(player)
        if level <= 0:
            return False
        config = cls.get_vip_level_config(level)
        return config.get('free_teleport', False) if config else False

    @classmethod
    def has_free_rest(cls, player):
        level = cls.get_active_vip_level(player)
        if level <= 0:
            return False
        config = cls.get_vip_level_config(level)
        return config.get('free_rest', False) if config else False

    @classmethod
    def has_free_stage_teleport(cls, player):
        level = cls.get_active_vip_level(player)
        if level <= 0:
            return False
        config = cls.get_vip_level_config(level)
        return config.get('free_stage_teleport', False) if config else False

    @classmethod
    def get_pk_drop_reduction(cls, player):
        level = cls.get_active_vip_level(player)
        if level <= 0:
            return 0
        config = cls.get_vip_level_config(level)
        return config.get('pk_drop_reduction', 0) if config else 0

    @classmethod
    def is_non_pk_loss_exempt(cls, player):
        level = cls.get_active_vip_level(player)
        if level <= 0:
            return False
        config = cls.get_vip_level_config(level)
        return config.get('non_pk_loss_exempt', False) if config else False

    @classmethod
    def get_storage_bonus(cls, player):
        level = cls.get_active_vip_level(player)
        if level <= 0:
            return 0
        config = cls.get_vip_level_config(level)
        return config.get('storage_bonus', 0) if config else 0

    @classmethod
    def has_color_nick(cls, player):
        level = cls.get_active_vip_level(player)
        if level <= 0:
            return False
        config = cls.get_vip_level_config(level)
        return config.get('color_nick', False) if config else False

    @classmethod
    def has_broadcast(cls, player):
        level = cls.get_active_vip_level(player)
        if level <= 0:
            return False
        config = cls.get_vip_level_config(level)
        return config.get('broadcast', False) if config else False

    @classmethod
    def get_vip_privilege_list(cls, level):
        config = cls.get_vip_level_config(level)
        if not config:
            return []

        privileges = []
        privileges.append(f"人物属性提升:{int(config.get('stat_bonus_rate', 0) * 100)}%")
        privileges.append(f"打怪经验增加:{int(config.get('exp_bonus_rate', 0) * 100)}%")
        privileges.append(f"仓库容量提升:{config.get('storage_bonus', 0)}")
        if config.get('free_teleport'):
            privileges.append("特权免费传送")
        if config.get('free_rest'):
            privileges.append("客栈免费休息")
        if config.get('free_stage_teleport'):
            privileges.append("驿站免费传送")
        if config.get('pk_drop_reduction', 0) > 0:
            privileges.append(f"PK战败荣誉少扣{int(config.get('pk_drop_reduction', 0) * 100)}%")
        if config.get('non_pk_loss_exempt'):
            privileges.append("非PK战败损失免除")
        if config.get('title'):
            privileges.append(f"专属特权称号")
        if config.get('color_nick'):
            privileges.append("山庄彩昵特权")
        if config.get('broadcast'):
            privileges.append("上线全服播报")
        if config.get('achievement'):
            privileges.append(f"三国特权【VIP{level}】成就")

        gift_items = []
        for gift in config.get('daily_gift', []):
            item_data = DataService.get_item(gift['item_id'])
            name = item_data.get('name', gift['item_id']) if item_data else gift['item_id']
            gift_items.append(f"{name}x{gift['quantity']}")
        if gift_items:
            privileges.append(f"每日礼包:{' '.join(gift_items)}")

        return privileges