import random
import json
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any


class EquipmentSource(Enum):
    MONSTER = "monster"
    CHEST = "chest"
    FORGE = "forge"
    EVENT = "event"


def _weighted_choice(weight_map: Dict[str, float]) -> Optional[str]:
    total = sum(weight_map.values())
    if total <= 0:
        return None
    r = random.random() * total
    upto = 0.0
    for key, w in weight_map.items():
        upto += w
        if upto >= r:
            return key
    return None


class EquipmentGenerator:
    """统一的装备生成器：根据来源与规则生成装备品质与星级。

    设计要点：
    - 神器与普通品质独立：若模板 is_artifact 为 True，则直接为"神器"；否则从普通品质池(普通/精良/卓越/史诗)中抽取。
    - 概率配置可由调用方传入（怪物、宝箱、锻造、活动都可以自定义）。
    - 支持星级规则：可配置固定范围或加权分布。
    - 模板选择：支持在调用方层面传入候选模板与其权重。
    """

    DEFAULT_RARITY_WEIGHTS_NON_ELITE: Dict[str, float] = {
        "普通": 1.0
    }

    DEFAULT_RARITY_WEIGHTS_ELITE: Dict[str, float] = {
        "普通": 0.4,
        "精良": 0.3,
        "卓越": 0.2,
        "史诗": 0.1,
    }

    DEFAULT_STAR_RANGE: Tuple[int, int] = (1, 5)

    @classmethod
    def roll_rarity(
        cls,
        is_artifact_template: bool,
        rarity_weights: Optional[Dict[str, float]] = None,
    ) -> str:
        if is_artifact_template:
            return "神器"
        weights = rarity_weights or cls.DEFAULT_RARITY_WEIGHTS_NON_ELITE
        picked = _weighted_choice(weights)
        return picked or "普通"

    @staticmethod
    def roll_stars(
        star_range: Optional[Tuple[int, int]] = None,
        star_weights: Optional[Dict[int, float]] = None,
    ) -> int:
        if star_weights:
            picked = _weighted_choice({str(k): v for k, v in star_weights.items()})
            return int(picked) if picked is not None else 1
        low, high = star_range or EquipmentGenerator.DEFAULT_STAR_RANGE
        return random.randint(low, high)

    @staticmethod
    def pick_template(candidates: List[str], weights: Optional[Dict[str, float]] = None) -> Optional[str]:
        if not candidates:
            return None
        if not weights:
            return random.choice(candidates)
        # 仅保留在候选中的权重
        filtered = {tid: weights.get(tid, 0.0) for tid in candidates}
        return _weighted_choice(filtered)

    @classmethod
    def generate(
        cls,
        *,
        source: EquipmentSource,
        template_id: str,
        template_loader,
        rarity_weights: Optional[Dict[str, float]] = None,
        star_range: Optional[Tuple[int, int]] = None,
        star_weights: Optional[Dict[int, float]] = None,
    ) -> Dict[str, Any]:
        """返回一个 dict，包含：template_id, rarity, stars。
        由上层再实例化 Equipment(template_id, rarity, stars)。
        """
        template: Dict[str, Any] = template_loader(template_id)
        rarity = cls.roll_rarity(template.get("is_artifact", False), rarity_weights)
        stars = cls.roll_stars(star_range, star_weights)
        return {
            "template_id": template_id,
            "rarity": rarity,
            "stars": stars,
            "source": source.value,
        }

    @classmethod
    def generate_from_pool(
        cls,
        *,
        source: EquipmentSource,
        template_pool: List[str],
        template_weights: Optional[Dict[str, float]],
        template_loader,
        rarity_weights: Optional[Dict[str, float]] = None,
        star_range: Optional[Tuple[int, int]] = None,
        star_weights: Optional[Dict[int, float]] = None,
    ) -> Optional[Dict[str, Any]]:
        template_id = cls.pick_template(template_pool, template_weights)
        if not template_id:
            return None
        return cls.generate(
            source=source,
            template_id=template_id,
            template_loader=template_loader,
            rarity_weights=rarity_weights,
            star_range=star_range,
            star_weights=star_weights,
        )


