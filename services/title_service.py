"""Title service for calculating title bonuses."""
from services.data_service import DataService


class TitleService:
    @classmethod
    def get_title_bonuses(cls, player):
        """Calculate all title bonuses for a player.

        Prefix bonus: base_value * (1 + prefix_count%)
        Suffix bonus: base_value * (1 + suffix_count%)
        Hidden attributes: activated when prefix and suffix are a valid pair
        """
        bonuses = {
            'max_health': 0,
            'max_mana': 0,
            'attack': 0,
            'defense': 0,
            'crit_rate': 0,
            'dodge_rate': 0,
            'prefix_count': 0,
            'suffix_count': 0,
            'hidden_activated': False,
        }

        owned = player.owned_titles
        prefixes = DataService.get_title_prefixes()
        suffixes = DataService.get_title_suffixes()

        # Count owned prefixes and suffixes
        for title_id in owned:
            if title_id in prefixes:
                bonuses['prefix_count'] += 1
            elif title_id in suffixes:
                bonuses['suffix_count'] += 1

        prefix_count = bonuses['prefix_count']
        suffix_count = bonuses['suffix_count']

        # Calculate prefix bonus with count-based multiplier
        # prefix属性+prefix_count% means: prefix_base * (1 + prefix_count%)
        if player.title_prefix_id:
            prefix = DataService.get_title(player.title_prefix_id, 'prefix')
            if prefix:
                stars = prefix.get('stars', 1)
                star_bonus = DataService.get_star_bonus(stars)
                base_hp = star_bonus.get('base_hp', 0)
                base_mp = star_bonus.get('base_mp', 0)
                base_atk = star_bonus.get('base_attack', 0)
                base_def = star_bonus.get('base_defense', 0)
                # Apply percentage bonus: base * (1 + count%)
                mult = 1 + prefix_count / 100.0
                bonuses['max_health'] += int(base_hp * mult)
                bonuses['max_mana'] += int(base_mp * mult)
                bonuses['attack'] += int(base_atk * mult)
                bonuses['defense'] += int(base_def * mult)

        # Calculate suffix bonus with count-based multiplier
        # suffix属性+suffix_count% means: suffix_base * (1 + suffix_count%)
        if player.title_suffix_id:
            suffix = DataService.get_title(player.title_suffix_id, 'suffix')
            if suffix:
                stars = suffix.get('stars', 1)
                star_bonus = DataService.get_star_bonus(stars)
                base_hp = star_bonus.get('base_hp', 0)
                base_mp = star_bonus.get('base_mp', 0)
                base_atk = star_bonus.get('base_attack', 0)
                base_def = star_bonus.get('base_defense', 0)
                # Apply percentage bonus: base * (1 + count%)
                mult = 1 + suffix_count / 100.0
                bonuses['max_health'] += int(base_hp * mult)
                bonuses['max_mana'] += int(base_mp * mult)
                bonuses['attack'] += int(base_atk * mult)
                bonuses['defense'] += int(base_def * mult)

        # Check for hidden attribute activation (matching pair)
        # Hidden attributes activate only when prefix.pair_id == suffix_id AND suffix.pair_id == prefix_id
        if player.title_prefix_id and player.title_suffix_id:
            prefix = DataService.get_title(player.title_prefix_id, 'prefix')
            suffix = DataService.get_title(player.title_suffix_id, 'suffix')
            if prefix and suffix:
                prefix_pair_id = prefix.get('pair_id')
                suffix_pair_id = suffix.get('pair_id')
                # Both must match each other
                if prefix_pair_id == player.title_suffix_id and suffix_pair_id == player.title_prefix_id:
                    # Matching pair - activate hidden attributes
                    prefix_stars = prefix.get('stars', 1)
                    suffix_stars = suffix.get('stars', 1)
                    avg_stars = (prefix_stars + suffix_stars) / 2
                    star_bonus = DataService.get_star_bonus(int(avg_stars))
                    bonuses['crit_rate'] = star_bonus.get('hidden_crit', 0)
                    bonuses['dodge_rate'] = star_bonus.get('hidden_dodge', 0)
                    bonuses['hidden_activated'] = True

        return bonuses

    @classmethod
    def is_matching_pair(cls, prefix_id, suffix_id):
        """Check if prefix and suffix form a matching pair."""
        if not prefix_id or not suffix_id:
            return False
        prefix = DataService.get_title(prefix_id, 'prefix')
        if not prefix:
            return False
        return prefix.get('pair_id') == suffix_id

    @classmethod
    def grant_title(cls, player, title_id, title_type):
        """Grant a title to a player."""
        owned = player.owned_titles
        if title_id not in owned:
            owned.append(title_id)
            player.owned_titles = owned
            return True
        return False

    @classmethod
    def set_title(cls, player, title_id, title_type):
        """Set the player's active title prefix or suffix."""
        if title_type == 'prefix':
            if title_id in player.owned_titles:
                player.title_prefix_id = title_id
                return True
        elif title_type == 'suffix':
            if title_id in player.owned_titles:
                player.title_suffix_id = title_id
                return True
        return False

    @classmethod
    def unset_title(cls, player, title_type):
        """Remove the player's active title prefix or suffix."""
        if title_type == 'prefix':
            player.title_prefix_id = None
        elif title_type == 'suffix':
            player.title_suffix_id = None