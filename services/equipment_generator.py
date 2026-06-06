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

        allow_artifact_template = source != EquipmentSource.MONSTER
        template_id = cls._select_template(
            template_pool, template_weights, template_loader, allow_artifact_template)
        if not template_id:
            return None

        template = template_loader(template_id)
        if not template:
            return None

        is_monster_source = source == EquipmentSource.MONSTER
        is_artifact = template.get("is_artifact", False)
        if is_artifact and allow_artifact_template:
            rarity = "神器"
        else:
            rarity = cls._roll_rarity_from_weights(
                rarity_weights,
                is_elite=is_monster_source,
                allow_legendary=False,
            )

        stars = cls.roll_stars(star_range, star_weights)

        return {
            "template_id": template_id,
            "rarity": rarity,
            "stars": stars,
        }

    @classmethod
    def _select_template(cls, pool, weights, loader, allow_artifact_template=True):
        valid = []
        for tid in pool:
            template = loader(tid)
            if not template:
                continue
            if not allow_artifact_template and template.get("is_artifact", False):
                continue
            valid.append(tid)
        if not valid:
            return None

        if weights and len(weights) == len(pool):
            filtered = []
            filtered_weights = []
            for tid, weight in zip(pool, weights):
                if tid in valid:
                    filtered.append(tid)
                    filtered_weights.append(float(weight))
            if filtered:
                return random.choices(filtered, weights=filtered_weights, k=1)[0]
        return random.choice(valid)

    RARITY_KEY_MAP = {
        "common": "普通",
        "uncommon": "精良",
        "rare": "卓越",
        "epic": "史诗",
        "legendary": "神器",
    }

    @classmethod
    def _roll_rarity_from_weights(cls, weights, is_elite=False, allow_legendary=True):
        if weights:
            if isinstance(weights, dict):
                mapped = {}
                for k, v in weights.items():
                    cn = cls.RARITY_KEY_MAP.get(k, k)
                    mapped[cn] = float(v)
                if not allow_legendary:
                    mapped.pop("神器", None)
                mapped = {name: weight for name, weight in mapped.items() if weight > 0}
                if mapped:
                    names = list(mapped.keys())
                    values = list(mapped.values())
                    return random.choices(names, weights=values, k=1)[0]
            else:
                wlist = [float(w) for w in weights]
                if len(wlist) == len(cls.RARITY_NAMES):
                    if not allow_legendary:
                        wlist = wlist[:-1]
                        names = cls.RARITY_NAMES[:-1]
                        return random.choices(names, weights=wlist, k=1)[0]
                    return random.choices(cls.RARITY_NAMES, weights=wlist, k=1)[0]
        if is_elite:
            return random.choice(["精良", "卓越", "史诗"])
        return random.choice(["普通", "精良"])
