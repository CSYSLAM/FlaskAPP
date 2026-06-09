import random
from services.data_service import DataService


class Monster:
    MONSTER_ALLOWED_RARITIES = {
        False: {"common", "uncommon", "普通", "精良"},
        True: {"uncommon", "rare", "epic", "精良", "卓越", "史诗"},
    }

    def __init__(self, monster_id, data):
        self.monster_id = monster_id
        self.is_elite = data.get("is_elite", False)
        self.is_divine_beast = data.get("is_divine_beast", False)
        self.is_copy = data.get("is_copy", False) or data.get("copy_only", False)
        self.copy_only = data.get("copy_only", False)
        self.copy_dungeon_id = data.get("copy_dungeon_id")
        self.copy_stage = data.get("copy_stage")
        self.copy_role = data.get("copy_role")
        self.name = data["name"]
        self.level = data["level"]
        self.killable = data["killable"]
        self.immortal = data["immortal"]
        self.description = data["description"]

        stats = data["base_stats"]
        self.health = stats.get("current_health", stats["health"])
        self.max_health = stats["max_health"] if "max_health" in stats else stats["health"]
        self.mana = stats["mana"]
        self.max_mana = stats["mana"]
        self.attack = stats["attack"]
        self.defense = stats["defense"]
        self.crit_rate = stats["crit_rate"]
        self.dodge_rate = stats["dodge_rate"]

        self.skills = data["skills"]
        self.drops = data["drops"]
        equip_cfg = data.get("drops", {}).get("equipment_drop", {})
        self.artifact_drop = equip_cfg.get("artifact_template")
        self.artifact_drop_rate = equip_cfg.get("artifact_drop_rate", 0.05)
        self.last_damage_taken = data.get("last_damage_taken", 0)
        self.last_damage_dealt = data.get("last_damage_dealt", "")
        self.last_action = data.get("last_action", "")
        self.last_skill = data.get("last_skill", "")
        self.respawning = False
        self.respawn_remaining = 0

    @classmethod
    def _sanitize_monster_rarity_weights(cls, weights, is_elite):
        if not isinstance(weights, dict):
            return weights

        allowed = cls.MONSTER_ALLOWED_RARITIES[bool(is_elite)]
        sanitized = {}
        for key, value in weights.items():
            if key in allowed:
                sanitized[key] = value

        return sanitized or None

    @classmethod
    def create_monster(cls, monster_id):
        monsters = DataService.get_monsters()
        if monster_id in monsters:
            return cls(monster_id, monsters[monster_id])
        return None

    @classmethod
    def from_dict(cls, monster_id, data):
        """Create a Monster from a dict (either cached data or encounter data)."""
        return cls(monster_id, data)

    def attack_player(self, player):
        from services.player_service import PlayerService
        self.last_action = "使用了普通攻击"
        self.last_skill = "普通攻击"

        if random.random() >= player.dodge_rate:
            min_damage = self.level * 2 if self.is_elite else self.level
            damage = max(min_damage, self.attack - player.defense)
            if random.random() <= self.crit_rate:
                damage *= 2
                self.last_damage_dealt = f"{damage}(暴击!)"
            else:
                self.last_damage_dealt = str(int(damage))
            player.health -= int(damage)
            player.last_damage_taken = int(damage)
            return damage
        else:
            self.last_damage_dealt = "闪避"
            player.last_damage_taken = 0
            return 0

    def get_loot(self):
        from services.equipment_service import EquipmentService
        equip_cfg = self.drops.get("equipment_drop", {})
        drop_rate = equip_cfg.get("drop_rate", 0.0)
        if random.random() < drop_rate:
            pool = equip_cfg.get("templates", self.drops.get("equipment_templates", []))
            template_weights = equip_cfg.get("template_weights")
            rarity_weights = equip_cfg.get(
                "rarity_weights_elite" if self.is_elite else "rarity_weights")
            rarity_weights = self._sanitize_monster_rarity_weights(rarity_weights, self.is_elite)
            star_range = None
            if "star_min" in equip_cfg or "star_max" in equip_cfg:
                star_range = (equip_cfg.get("star_min", 1), equip_cfg.get("star_max", 5))
            star_weights = equip_cfg.get("star_weights")

            from services.equipment_generator import EquipmentGenerator, EquipmentSource
            roll = EquipmentGenerator.generate_from_pool(
                source=EquipmentSource.MONSTER,
                template_pool=pool,
                template_weights=template_weights,
                template_loader=DataService.get_equipment_template,
                rarity_weights=rarity_weights,
                star_range=star_range,
                star_weights=star_weights,
            )
            if roll:
                return roll

        # Divine beast artifact drop (independent chance)
        if self.is_divine_beast and self.artifact_drop:
            if random.random() < self.artifact_drop_rate:
                stars = random.randint(3, 5)
                return {
                    "template_id": self.artifact_drop,
                    "rarity": "神器",
                    "stars": stars,
                }

        for item_id, chance in self.drops["items"].items():
            if random.random() < chance:
                return ("item", item_id)
        return None

    def get_money_drop(self):
        return random.randint(self.drops["money"]["min"], self.drops["money"]["max"])

    def get_experience_drop(self):
        return self.drops["experience"]

    def reset_health(self):
        if self.immortal:
            self.health = self.max_health
