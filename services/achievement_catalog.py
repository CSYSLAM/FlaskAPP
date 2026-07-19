ALIGNED_CATEGORIES = [
    "道具",
    "成长",
    "副本",
    "杀怪",
    "社交",
    "P K",
    "赛事",
    "装备",
    "财富",
    "副将",
    "活动",
    "任务",
    "其他",
]

ITEM_USAGE_PREFIX = "name:"

ITEM_TIER_DEFINITIONS = (
    {"label": "开始磕", "value": 10, "points": 10},
    {"label": "药就是饭", "value": 100, "points": 30},
    {"label": "吃一辈子", "value": 1000, "points": 50},
)

CHEST_TIER_DEFINITIONS = (
    {"label": "开始开", "value": 20, "points": 20},
    {"label": "开箱高手", "value": 100, "points": 40},
)

ITEM_REWARD_FAMILIES = {
    "health": (
        {"max_health": 5},
        {"max_health": 10, "attack": 2},
        {"max_health": 20, "max_mana": 5, "attack": 3},
    ),
    "mana": (
        {"max_mana": 5},
        {"max_mana": 10, "defense": 2},
        {"max_mana": 20, "max_health": 5, "defense": 3},
    ),
    "attack": (
        {"attack": 3},
        {"attack": 6, "crit_rate": 0.01},
        {"attack": 10, "crit_rate": 0.02, "max_health": 10},
    ),
    "defense": (
        {"defense": 3},
        {"defense": 6, "max_health": 10},
        {"defense": 10, "max_health": 20, "dodge_rate": 0.01},
    ),
    "crit": (
        {"crit_rate": 0.01},
        {"crit_rate": 0.02, "attack": 3},
        {"crit_rate": 0.03, "attack": 6, "max_health": 10},
    ),
    "dodge": (
        {"dodge_rate": 0.01},
        {"dodge_rate": 0.02, "defense": 3},
        {"dodge_rate": 0.03, "defense": 6, "max_mana": 10},
    ),
    "exp": (
        {"max_health": 5, "max_mana": 5},
        {"max_health": 10, "max_mana": 10, "attack": 2},
        {"max_health": 20, "max_mana": 20, "attack": 4},
    ),
    "bundle": (
        {"max_health": 8, "max_mana": 8},
        {"max_health": 15, "max_mana": 15, "attack": 3},
        {"max_health": 30, "max_mana": 30, "attack": 5},
    ),
    "health_plus": (
        {"max_health": 6, "attack": 1},
        {"max_health": 12, "attack": 3},
        {"max_health": 24, "max_mana": 6, "attack": 4},
    ),
    "mana_plus": (
        {"max_mana": 6, "defense": 1},
        {"max_mana": 12, "defense": 3},
        {"max_mana": 24, "max_health": 6, "defense": 4},
    ),
    "health_crit": (
        {"max_health": 6, "crit_rate": 0.01},
        {"max_health": 12, "attack": 2, "crit_rate": 0.02},
        {"max_health": 22, "attack": 4, "crit_rate": 0.03},
    ),
    "mana_dodge": (
        {"max_mana": 6, "dodge_rate": 0.01},
        {"max_mana": 12, "defense": 2, "dodge_rate": 0.02},
        {"max_mana": 22, "defense": 4, "dodge_rate": 0.03},
    ),
    "attack_crit": (
        {"attack": 4, "crit_rate": 0.01},
        {"attack": 8, "crit_rate": 0.02},
        {"attack": 12, "crit_rate": 0.03, "max_health": 10},
    ),
}

CHEST_REWARD_FAMILIES = {
    "low": (
        {"max_health": 8, "defense": 1},
        {"max_health": 16, "defense": 3, "attack": 1},
    ),
    "mid": (
        {"max_health": 10, "max_mana": 10, "attack": 1},
        {"max_health": 20, "max_mana": 20, "attack": 3, "defense": 2},
    ),
    "high": (
        {"attack": 3, "defense": 3, "max_health": 12},
        {"attack": 6, "defense": 6, "max_health": 24, "max_mana": 12},
    ),
}

ITEM_SERIES = [
    {"slug": "zhixuecao", "name": "止血草", "reward_family": "health", "legacy_start_id": "item_zhixuecao", "tracking_keys": ["potion_heal"]},
    {"slug": "ningmocao", "name": "凝魔草", "reward_family": "mana", "legacy_start_id": "item_ningmocao", "tracking_keys": ["potion_mana"]},
    {"slug": "jinchuangyao", "name": "金疮药", "reward_family": "health", "legacy_start_id": "item_jinchuangyao", "tracking_keys": ["potion_heal_100"]},
    {"slug": "jumosan", "name": "聚魔散", "reward_family": "mana", "legacy_start_id": "item_jumosan", "tracking_keys": ["potion_mana_100"]},
    {"slug": "yangshengwan", "name": "养生丸", "reward_family": "health", "legacy_start_id": "item_yangshengwan", "tracking_keys": ["potion_heal_200"]},
    {"slug": "xingshenshui", "name": "醒神水", "reward_family": "mana", "legacy_start_id": "item_xingshenshui", "tracking_keys": ["potion_mana_200"]},
    {"slug": "huishengwan", "name": "回生丸", "reward_family": "health", "legacy_start_id": "item_huishengwan", "tracking_keys": ["potion_heal_300"]},
    {"slug": "dabuwan", "name": "大补丸", "reward_family": "mana", "legacy_start_id": "item_dabuwan", "tracking_keys": ["potion_heal_400"]},
    {"slug": "xiaohuandan", "name": "小还丹", "reward_family": "attack", "legacy_start_id": "item_xiaohuandan", "tracking_keys": ["potion_heal_500"]},
    {"slug": "dahuandan", "name": "大还丹", "reward_family": "defense", "legacy_start_id": "item_dahuandan", "tracking_keys": ["potion_heal_625"]},
    {"slug": "yeshanshen", "name": "野山参", "reward_family": "crit", "legacy_start_id": "item_yeshanshen", "tracking_keys": ["potion_heal_800"]},
    {"slug": "xuelianlu", "name": "雪莲露", "reward_family": "dodge", "legacy_start_id": "item_xuelianlu", "tracking_keys": ["potion_mana_800"]},
    {"slug": "zhenzhubei", "name": "珍珠贝", "reward_family": "health", "tracking_keys": ["potion_heal_950"]},
    {"slug": "huanyangdan", "name": "还阳丹", "reward_family": "health_plus", "tracking_keys": ["potion_heal_1150"]},
    {"slug": "guanyinshui", "name": "观音水", "reward_family": "mana_plus", "tracking_keys": ["potion_mana_1150"]},
    {"slug": "tiancandan", "name": "天蚕丹", "reward_family": "attack", "tracking_keys": ["potion_heal_2000"]},
    {"slug": "huashenshui", "name": "化神水", "reward_family": "mana_plus", "tracking_keys": ["potion_mana_2000"]},
    {"slug": "xiaojingyandan", "name": "小经验丹", "reward_family": "exp", "tracking_keys": ["exp_small"]},
    {"slug": "dajingyandan", "name": "大经验丹", "reward_family": "exp", "tracking_keys": ["exp_large"]},
    {"slug": "xiaoxueshi", "name": "小血石", "reward_family": "health", "tracking_keys": ["blood_stone_small"]},
    {"slug": "zhongxueshi", "name": "中血石", "reward_family": "health_plus", "tracking_keys": ["blood_stone_medium"]},
    {"slug": "daxueshi", "name": "大血石", "reward_family": "health_plus", "tracking_keys": ["blood_stone_large"]},
    {"slug": "xiaomoshi", "name": "小魔石", "reward_family": "mana", "tracking_keys": ["mana_stone_small"]},
    {"slug": "zhongmoshi", "name": "中魔石", "reward_family": "mana_plus", "tracking_keys": ["mana_stone_medium"]},
    {"slug": "damoshi", "name": "大魔石", "reward_family": "mana_plus", "tracking_keys": ["mana_stone_large"]},
    {"slug": "double_exp_card", "name": "双倍经验卡", "reward_family": "exp", "tracking_keys": ["double_exp_card"]},
    {"slug": "miyaolibao", "name": "秘药礼包", "reward_family": "bundle", "tracking_keys": ["potion_package"]},
    {"slug": "shenxuedan", "name": "神血丹", "reward_family": "health_plus", "tracking_keys": ["potion_heal_2250"]},
    {"slug": "qinglinglu", "name": "清灵露", "reward_family": "mana_dodge", "tracking_keys": ["potion_mana_2250"]},
    {"slug": "lt_double_exp_card", "name": "副将双倍经验卡", "reward_family": "exp"},
    {"slug": "lt_exp_low", "name": "副将低级经验丹", "reward_family": "exp", "tracking_keys": ["lt_exp_low"]},
    {"slug": "lt_exp_mid", "name": "副将中级经验丹", "reward_family": "exp", "tracking_keys": ["lt_exp_mid"]},
    {"slug": "lt_exp_high", "name": "副将高级经验丹", "reward_family": "exp", "tracking_keys": ["lt_exp_high"]},
]

CHEST_SERIES = [
    {"slug": "iron", "name": "铁质宝匣", "reward_family": "low", "tracking_keys": ["chest_iron", "chest_iron_bound"]},
    {"slug": "silver", "name": "银质宝匣", "reward_family": "mid", "tracking_keys": ["chest_silver", "chest_silver_bound"]},
    {"slug": "gold", "name": "金质宝匣", "reward_family": "high", "tracking_keys": ["chest_gold", "chest_gold_bound"]},
]


def _build_reward_tuple(series):
    if "tier_rewards" in series:
        return series["tier_rewards"]
    return ITEM_REWARD_FAMILIES[series["reward_family"]]


def build_aligned_item_achievements():
    achievements = {}

    for series in ITEM_SERIES:
        rewards = _build_reward_tuple(series)
        for idx, tier in enumerate(ITEM_TIER_DEFINITIONS):
            achievement_id = series.get("legacy_start_id") if idx == 0 and series.get("legacy_start_id") else (
                f"item_use_{series['slug']}_{tier['value']}"
            )
            achievements[achievement_id] = {
                "name": f"{tier['label']}【{series['name']}】",
                "category": "道具",
                "description": f"使用{tier['value']}个{series['name']}",
                "condition_type": "item_use",
                "condition_value": tier["value"],
                "tracking_key": f"{ITEM_USAGE_PREFIX}{series['name']}",
                "tracking_keys": list(series.get("tracking_keys", [])),
                "points": tier["points"],
                "reward": rewards[idx],
            }

    for series in CHEST_SERIES:
        rewards = CHEST_REWARD_FAMILIES[series["reward_family"]]
        for idx, tier in enumerate(CHEST_TIER_DEFINITIONS):
            achievement_id = f"item_open_{series['slug']}_{tier['value']}"
            achievements[achievement_id] = {
                "name": f"{tier['label']}【{series['name']}】",
                "category": "道具",
                "description": f"开启{tier['value']}个{series['name']}",
                "condition_type": "item_use",
                "condition_value": tier["value"],
                "tracking_key": f"{ITEM_USAGE_PREFIX}{series['name']}",
                "tracking_keys": list(series.get("tracking_keys", [])),
                "points": tier["points"],
                "reward": rewards[idx],
            }

    return achievements
