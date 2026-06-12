import random
from typing import Callable, List


EQUIP_FROM_POOL_WEAPON_LV1 = "__EQUIP_FROM_POOL_WEAPON_LV1__"
EQUIP_FROM_POOL_GEAR_LV1 = "__EQUIP_FROM_POOL_GEAR_LV1__"
EQUIP_ARTIFACT_LV1 = "__EQUIP_ARTIFACT_LV1__"


def _handle_weapon_lv1(player, count: int) -> List[str]:
    from services.equipment_service import EquipmentService
    from services.data_service import DataService
    results = []
    templates = ["chulong_sword_1"]
    for _ in range(count):
        valid = [tid for tid in templates if DataService.get_equipment_template(tid)]
        if valid:
            equip = EquipmentService.generate_from_pool(
                player.id, valid,
                rarity_weights={"普通": 0.7, "精良": 0.2, "卓越": 0.09, "史诗": 0.01},
                star_weights={1: 0.35, 2: 0.35, 3: 0.2, 4: 0.08, 5: 0.02}
            )
            if equip:
                DataService.add_item_to_inventory(player.id, equip.instance_id)
                results.append(f"雏龙长剑x1")
    return results


def _handle_gear_lv1(player, count: int) -> List[str]:
    from services.equipment_service import EquipmentService
    from services.data_service import DataService
    results = []
    templates = ["chulong_helmet_1", "chulong_armor_1", "chulong_gloves_1",
                 "chulong_pants_1", "chulong_shoes_1"]
    for _ in range(count):
        valid = [tid for tid in templates if DataService.get_equipment_template(tid)]
        if valid:
            equip = EquipmentService.generate_from_pool(
                player.id, valid,
                rarity_weights={"普通": 0.7, "精良": 0.2, "卓越": 0.09, "史诗": 0.01},
                star_weights={1: 0.35, 2: 0.35, 3: 0.2, 4: 0.08, 5: 0.02}
            )
            if equip:
                DataService.add_item_to_inventory(player.id, equip.instance_id)
                results.append(f"雏龙装备x1")
    return results


def _handle_artifact_lv1(player, count: int) -> List[str]:
    from services.equipment_service import EquipmentService
    from services.data_service import DataService
    results = []
    templates = ["test_artifact_weapon_lv1", "test_artifact_accessory_lv1"]
    for _ in range(count):
        valid = [tid for tid in templates if DataService.get_equipment_template(tid)]
        tid = random.choice(valid) if valid else None
        if tid:
            stars = random.randint(1, 5)
            equip = EquipmentService.generate_random_equipment(
                player.id, tid, rarity="神器", stars=stars)
            if equip:
                DataService.add_item_to_inventory(player.id, equip.instance_id)
                results.append(f"{equip.name}x1")
    return results


REWARD_HANDLERS: dict[str, Callable] = {
    EQUIP_FROM_POOL_WEAPON_LV1: _handle_weapon_lv1,
    EQUIP_FROM_POOL_GEAR_LV1: _handle_gear_lv1,
    EQUIP_ARTIFACT_LV1: _handle_artifact_lv1,
}


def handle_reward(player, placeholder_id: str, count: int) -> list[str]:
    handler = REWARD_HANDLERS.get(placeholder_id)
    if not handler:
        return []
    return handler(player, count)