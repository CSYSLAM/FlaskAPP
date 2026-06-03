import random
import uuid
from enum import Enum


class EquipmentSource(Enum):
    MONSTER = "monster"
    CHEST = "chest"
    SHOP = "shop"
    CRAFT = "craft"


class EquipmentGenerator:
    DEFAULT_RARITY_WEIGHTS = [0.40, 0.30, 0.20, 0.08, 0.02]
    ELITE_RARITY_WEIGHTS = [0.15, 0.30, 0.30, 0.20, 0.05]
    RARITY_NAMES = ["普通", "精良", "卓越", "史诗", "神器"]

    DEFAULT_STAR_WEIGHTS = [0.30, 0.25, 0.20, 0.15, 0.10]
    HIGH_STAR_WEIGHTS = [0.05, 0.10, 0.20, 0.30, 0.35]

    @classmethod
    def roll_rarity(cls, is_elite=False):
        weights = cls.ELITE_RARITY_WEIGHTS if is_elite else cls.DEFAULT_RARITY_WEIGHTS
        return random.choices(cls.RARITY_NAMES, weights=weights, k=1)[0]

    @classmethod
    def roll_stars(cls, star_range=None, star_weights=None):
        if star_range:
            return random.randint(int(star_range[0]), int(star_range[1]))
        if star_weights:
            weights = [float(w) for w in star_weights]
            stars = list(range(1, len(weights) + 1))
            return random.choices(stars, weights=weights, k=1)[0]
        return random.choices([1, 2, 3, 4, 5], weights=cls.DEFAULT_STAR_WEIGHTS, k=1)[0]

    @classmethod
    def generate_from_pool(cls, source, template_pool, template_loader,
                           rarity_weights=None, star_range=None,
                           star_weights=None, template_weights=None):
        if not template_pool:
            return None

        template_id = cls._select_template(
            template_pool, template_weights, template_loader)
        if not template_id:
            return None

        template = template_loader(template_id)
        if not template:
            return None

        is_elite = source == EquipmentSource.MONSTER
        if template.get("is_artifact"):
            rarity = "神器"
        else:
            rarity = cls._roll_rarity_from_weights(rarity_weights, is_elite)

        stars = cls.roll_stars(star_range, star_weights)

        return {
            "template_id": template_id,
            "rarity": rarity,
            "stars": stars,
        }

    @classmethod
    def _select_template(cls, pool, weights, loader):
        valid = [tid for tid in pool if loader(tid)]
        if not valid:
            return None

        if weights and len(weights) == len(pool):
            weights = [float(w) for w in weights]
            return random.choices(pool, weights=weights, k=1)[0]
        return random.choice(valid)

    RARITY_KEY_MAP = {
        "common": "普通",
        "uncommon": "精良",
        "rare": "卓越",
        "epic": "史诗",
        "legendary": "神器",
    }

    @classmethod
    def _roll_rarity_from_weights(cls, weights, is_elite=False):
        if weights:
            if isinstance(weights, dict):
                mapped = {}
                for k, v in weights.items():
                    cn = cls.RARITY_KEY_MAP.get(k, k)
                    mapped[cn] = float(v)
                if len(mapped) == len(cls.RARITY_NAMES):
                    return random.choices(cls.RARITY_NAMES, weights=list(mapped.values()), k=1)[0]
            else:
                wlist = [float(w) for w in weights]
                if len(wlist) == len(cls.RARITY_NAMES):
                    return random.choices(cls.RARITY_NAMES, weights=wlist, k=1)[0]
        return cls.roll_rarity(is_elite)