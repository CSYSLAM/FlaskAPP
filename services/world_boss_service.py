import time
from services.data_service import DataService


class WorldBossState:
    __slots__ = ('monster_id', 'current_health', 'max_health', 'is_alive',
                 'defeated_at', 'respawn_time', 'participants', 'last_attack_time')

    def __init__(self, monster_id, max_health, respawn_time):
        self.monster_id = monster_id
        self.current_health = max_health
        self.max_health = max_health
        self.is_alive = True
        self.defeated_at = 0
        self.respawn_time = respawn_time
        self.participants = {}  # {player_id: total_damage}
        self.last_attack_time = 0


class WorldBossService:
    """Shared world-boss state, all in-memory (class-level), matching _ground_items pattern."""

    _bosses = {}   # {monster_id: WorldBossState}
    _initialized = False

    # ---- respawn time helpers ----

    @classmethod
    def _get_respawn_time(cls, monster_id, monster_data):
        """Determine respawn time from monster config or location scene name."""
        if 'respawn_time' in monster_data:
            return monster_data['respawn_time']

        if monster_data.get('is_divine_beast'):
            return 600

        # Find which locations contain this monster
        locations = DataService.get_locations()
        scene_name = ''
        area = ''
        for loc_id, loc_data in locations.items():
            monsters_list = loc_data.get('monsters', [])
            if monster_id in monsters_list:
                scene_name = loc_data.get('name', '')
                area = loc_id.split('_')[0] if '_' in loc_id else ''
                break

        if '粮草营' in scene_name:
            return 180
        if '寒门' in scene_name:
            return 240
        if '虎牢关' in scene_name:
            return 360
        if area in ('xiapi', 'hanzhong', 'jiangling', 'luoyang'):
            return 120
        return 60

    # ---- init ----

    @classmethod
    def init_bosses(cls):
        """Called once after DataService loads. Creates state for every is_elite monster (excluding copy dungeon elites)."""
        if cls._initialized:
            return
        monsters = DataService.get_monsters()
        for mid, mdata in monsters.items():
            if not mdata.get('is_elite') or not mdata.get('killable', True):
                continue
            # Exclude copy dungeon elites (personal elites, not world bosses)
            if mdata.get('is_copy') or mdata.get('copy_only') or mdata.get('copy_dungeon_id'):
                continue
            stats = mdata.get('base_stats', {})
            max_hp = stats.get('max_health', stats.get('health', 100))
            respawn = cls._get_respawn_time(mid, mdata)
            cls._bosses[mid] = WorldBossState(mid, max_hp, respawn)
        cls._initialized = True

    # ---- public api ----

    @classmethod
    def get_boss(cls, monster_id):
        """Return WorldBossState, or None if not a world boss."""
        if not cls._initialized:
            cls.init_bosses()
        boss = cls._bosses.get(monster_id)
        if boss is None:
            return None
        cls._check_respawn(boss)
        return boss

    @classmethod
    def is_boss_alive(cls, monster_id):
        boss = cls.get_boss(monster_id)
        return boss is not None and boss.is_alive

    @classmethod
    def get_respawn_remaining(cls, monster_id):
        boss = cls._bosses.get(monster_id)
        if boss is None or boss.is_alive:
            return 0
        elapsed = time.time() - boss.defeated_at
        return max(0, int(boss.respawn_time - elapsed))

    @classmethod
    def damage_boss(cls, monster_id, player_id, damage):
        """Apply damage, return (killed: bool, killer_id: int or None)."""
        boss = cls._bosses.get(monster_id)
        if boss is None or not boss.is_alive:
            return False, None

        boss.current_health -= damage
        boss.last_attack_time = time.time()
        boss.participants[player_id] = boss.participants.get(player_id, 0) + damage

        if boss.current_health <= 0:
            boss.current_health = 0
            boss.is_alive = False
            boss.defeated_at = time.time()
            return True, player_id
        return False, None

    @classmethod
    def get_participant_count(cls, monster_id, player_id=None):
        boss = cls._bosses.get(monster_id)
        if boss is None:
            return 0
        if player_id is not None:
            return len([p for p in boss.participants if p != player_id])
        return len(boss.participants)

    # ---- internal ----

    @classmethod
    def _check_respawn(cls, boss):
        if boss.is_alive:
            return
        if time.time() - boss.defeated_at >= boss.respawn_time:
            boss.current_health = boss.max_health
            boss.is_alive = True
            boss.participants = {}
            boss.last_attack_time = 0
            # Divine beast respawn: broadcast system message
            cls._announce_respawn(boss.monster_id)

    @classmethod
    def _announce_respawn(cls, monster_id):
        """Announce divine beast / elite boss respawn via system message."""
        monsters = DataService.get_monsters()
        mdata = monsters.get(monster_id)
        if not mdata:
            return
        # Find location info
        locations = DataService.get_locations()
        loc_name = ''
        area_name = ''
        for loc_id, loc_data in locations.items():
            if monster_id in loc_data.get('monsters', []):
                loc_name = loc_data.get('name', '')
                area_name = loc_data.get('area_name', '')
                break

        if mdata.get('is_divine_beast'):
            desc = mdata.get('description', mdata.get('name', monster_id))
            msg = f"{desc}在{area_name}{loc_name}复活了，请速速前往击杀！"
        elif mdata.get('is_elite'):
            name = mdata.get('name', monster_id)
            if loc_name:
                msg = f"【精】{name}在{area_name}{loc_name}复活了，请速速前往击杀！"
            else:
                msg = f"【精】{name}已复活，请速速前往击杀！"
        else:
            return
        DataService.broadcast_system(msg)