from typing import Callable, List


# 占位符常量，集中定义，便于复用与检索
EQUIP_FROM_POOL_WEAPON_LV1 = "__EQUIP_FROM_POOL_WEAPON_LV1__"
EQUIP_FROM_POOL_GEAR_LV1 = "__EQUIP_FROM_POOL_GEAR_LV1__"
EQUIP_ARTIFACT_LV1 = "__EQUIP_ARTIFACT_LV1__"


def _handle_weapon_lv1(player, count: int) -> List[str]:
    for _ in range(count):
        player._grant_random_equipment_lv1(weapon_only=True)
    return ["1级随机武器x1"] * count


def _handle_gear_lv1(player, count: int) -> List[str]:
    for _ in range(count):
        player._grant_random_equipment_lv1(weapon_only=False)
    return ["1级随机装备x1"] * count


def _handle_artifact_lv1(player, count: int) -> List[str]:
    for _ in range(count):
        player._grant_artifact_lv1()
    return ["1级神器(概率)x1"] * count


# 注册表：占位符 -> 处理函数(player, count) -> List[str]（用于展示）
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


