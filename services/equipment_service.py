import uuid
import random
from services import db
from services.data_service import DataService
from models.player import EquipmentInstance, EquipmentSlot, InventoryItem


class EquipmentService:

    @classmethod
    def equip(cls, player, equipment_instance_id):
        equip = EquipmentInstance.query.filter_by(
            instance_id=equipment_instance_id).first()
        if not equip or equip.player_id != player.id:
            return False, "装备不存在"

        if equip.level_required > player.level:
            return False, f"需要等级{equip.level_required}"

        if equip.class_required and equip.class_required != player.player_class:
            return False, f"需要{equip.class_required}职业"

        if not equip.is_bound:
            equip.is_bound = True

        slot = EquipmentSlot.query.filter_by(
            player_id=player.id, slot_name=equip.slot).first()
        if not slot:
            return False, "装备槽不存在"

        old_equip_id = slot.equipment_instance_id
        old_equip = EquipmentInstance.query.get(old_equip_id) if old_equip_id else None

        # Compute stat diff
        new_stats = equip.get_total_stats()
        old_stats = old_equip.get_total_stats() if old_equip else {}
        diff_parts = []
        STAT_NAMES = EquipmentInstance.STAT_NAMES
        for stat in set(list(new_stats.keys()) + list(old_stats.keys())):
            new_val = new_stats.get(stat, 0)
            old_val = old_stats.get(stat, 0)
            delta = new_val - old_val
            if delta == 0:
                continue
            display = STAT_NAMES.get(stat, stat)
            if stat in ['crit_rate', 'dodge_rate']:
                sign = "+" if delta > 0 else ""
                diff_parts.append(f"{display}{sign}{delta*100:.1f}%")
            else:
                sign = "+" if delta > 0 else ""
                diff_parts.append(f"{display}{sign}{int(delta)}")

        slot.equipment_instance_id = equip.id

        inv = InventoryItem.query.filter_by(
            player_id=player.id, item_id=equip.instance_id).first()
        if inv:
            db.session.delete(inv)

        if old_equip_id:
            if old_equip:
                DataService.add_item_to_inventory(player.id, old_equip.instance_id)

        db.session.commit()

        from services.achievement_service import AchievementService
        equipped = DataService.get_equipped(player.id)
        count = sum(1 for v in equipped.values() if v is not None)
        AchievementService.check(player, 'equip_full', count)
        db.session.commit()

        msg = f"装备了 {equip.name}"
        if diff_parts:
            msg += " " + " ".join(diff_parts)
        return True, msg

    @classmethod
    def unequip(cls, player, slot_name):
        slot = EquipmentSlot.query.filter_by(
            player_id=player.id, slot_name=slot_name).first()
        if not slot or not slot.equipment_instance_id:
            return False, "该槽位没有装备"

        equip = EquipmentInstance.query.get(slot.equipment_instance_id)
        slot.equipment_instance_id = None

        if equip:
            DataService.add_item_to_inventory(player.id, equip.instance_id)

        db.session.commit()
        return True, f"卸下了 {equip.name if equip else slot_name}"

    @classmethod
    def enhance(cls, player, equipment_instance_id):
        equip = EquipmentInstance.query.filter_by(
            instance_id=equipment_instance_id).first()
        if not equip or equip.player_id != player.id:
            return False, "装备不存在"

        game_config = DataService.get_game_config()
        enhance_cost = game_config.get("enhance_cost", 5000)

        if equip.enhance_level >= 50:
            return False, "装备已达最大强化等级"

        if player.gold < enhance_cost:
            return False, "银两不足"

        gem_inv = DataService.get_inventory_item(player.id, "enhance_gem")
        if not gem_inv or gem_inv.quantity < 1:
            return False, "需要强化宝玉"

        player.gold -= enhance_cost
        DataService.remove_item_from_inventory(player.id, "enhance_gem", 1)

        success_rate = equip.get_enhance_success_rate(player.enhance_bonus_rate)
        if random.random() < success_rate:
            equip.enhance_level += 1
            player.enhance_bonus_rate = 0

            initial = equip.get_initial_stats()
            new_base = {}
            for stat, initial_value in initial.items():
                total_bonus = int(initial_value * 0.01 * equip.enhance_level)
                new_base[stat] = initial_value + total_bonus
            equip.set_base_stats(new_base)
            equip.update_name()

            DataService.broadcast_system(
                f"{player.nickname}成功将{equip.name}强化至+{equip.enhance_level}")

            from services.achievement_service import AchievementService
            AchievementService.check(player, 'enhance', equip.enhance_level)

            db.session.commit()
            return True, f"强化成功！装备等级提升至+{equip.enhance_level}"
        else:
            equip.enhance_level = max(0, equip.enhance_level - 1)
            player.enhance_bonus_rate += 0.05

            initial = equip.get_initial_stats()
            new_base = {}
            for stat, initial_value in initial.items():
                total_bonus = int(initial_value * 0.01 * equip.enhance_level)
                new_base[stat] = initial_value + total_bonus
            equip.set_base_stats(new_base)
            equip.update_name()

            db.session.commit()
            return False, f"强化失败！装备等级降至+{equip.enhance_level}，下次成功率+5%"

    @classmethod
    def sell_equipment(cls, player, equipment_instance_id):
        equip = EquipmentInstance.query.filter_by(
            instance_id=equipment_instance_id).first()
        if not equip or equip.player_id != player.id:
            return False, "装备不存在", 0

        price = equip.get_sell_price()
        player.gold += price
        player.gold_earned = (player.gold_earned or 0) + price

        slot = EquipmentSlot.query.filter_by(
            equipment_instance_id=equip.id).first()
        if slot:
            slot.equipment_instance_id = None

        db.session.delete(equip)
        db.session.commit()

        from services.achievement_service import AchievementService
        AchievementService.check(player, 'gold_earned', player.gold_earned)
        db.session.commit()

        return True, f"出售了 {equip.name}，获得 {price} 银两", price

    @classmethod
    def generate_random_equipment(cls, player_id, template_id, rarity=None, stars=None):
        template = DataService.get_equipment_template(template_id)
        if not template:
            return None

        if template.get("is_artifact"):
            rarity = "神器"
        elif not rarity:
            from services.equipment_generator import EquipmentGenerator
            rarity = EquipmentGenerator.roll_rarity(False)

        if not stars:
            stars = random.randint(1, 5)

        equip = DataService.create_equipment_instance(
            player_id, template_id, rarity, stars)
        return equip

    @classmethod
    def generate_from_pool(cls, player_id, pool, rarity_weights=None,
                           star_range=None, star_weights=None,
                           template_weights=None):
        from services.equipment_generator import EquipmentGenerator, EquipmentSource
        roll = EquipmentGenerator.generate_from_pool(
            source=EquipmentSource.CHEST,
            template_pool=pool,
            template_weights=template_weights,
            template_loader=DataService.get_equipment_template,
            rarity_weights=rarity_weights,
            star_range=star_range,
            star_weights=star_weights,
        )
        if not roll:
            return None

        equip = DataService.create_equipment_instance(
            player_id, roll["template_id"], roll["rarity"], roll["stars"])
        return equip