import json, os, sys
sys.stdout.reconfigure(encoding='utf-8')

# === 1. Add quest items ===
with open('data/items.json', 'r', encoding='utf-8') as f:
    items = json.load(f)

items["quest_jiashu"] = {"name": "家书", "type": "quest", "description": "曹樱写给曹彰的家信", "price": 0, "sell_price": 0, "is_usable": False, "capacity": 0}
items["quest_fancai"] = {"name": "饭菜", "type": "quest", "description": "曹樱为父亲准备的饭菜", "price": 0, "sell_price": 0, "is_usable": False, "capacity": 0}

with open('data/items.json', 'w', encoding='utf-8') as f:
    json.dump(items, f, ensure_ascii=False, indent=2)
print("Added quest items: 家书, 饭菜")

# === 2. Add 曹彰 NPC ===
with open('data/monsters.json', 'r', encoding='utf-8') as f:
    monsters = json.load(f)

monsters["npc_beiping_east_曹彰"] = {
    "name": "曹彰", "level": 50, "killable": False, "immortal": False,
    "is_elite": False, "is_divine_beast": False, "is_copy": False, "copy_only": False,
    "description": "曹操之子，曹樱的父亲，驻守军营的将领",
    "base_stats": {"current_health": 99999, "health": 99999, "max_health": 99999, "mana": 0, "max_mana": 0, "attack": 0, "defense": 0, "crit_rate": 0, "dodge_rate": 0},
    "skills": [], "drops": {},
}

with open('data/monsters.json', 'w', encoding='utf-8') as f:
    json.dump(monsters, f, ensure_ascii=False, indent=2)
print("Added 曹彰 NPC")

# Place 曹彰 at 军营
fn = 'data/locations/beiping_east.json'
if os.path.exists(fn):
    with open(fn, 'r', encoding='utf-8') as f:
        locs = json.load(f)
    for scene_id, scene in locs.get('scenes', {}).items():
        if '军营' in scene.get('name', ''):
            scene.setdefault('npcs', [])
            if 'npc_beiping_east_曹彰' not in scene['npcs']:
                scene['npcs'].append('npc_beiping_east_曹彰')
                print(f"Placed 曹彰 at {scene_id} ({scene.get('name')})")
    with open(fn, 'w', encoding='utf-8') as f:
        json.dump(locs, f, ensure_ascii=False, indent=2)

# === 3. Write quests.json ===
quests = {}
q = lambda **kw: kw

quests["main_01"] = {
    "id": "main_01", "name": "主·初入三国", "type": "main",
    "npc_id": "npc_beiping_east_香凝", "npc_name": "香凝",
    "npc_location": "beiping_east.大院", "npc_location_name": "大院(北平东区)",
    "level_required": 1,
    "description": "前往「大院」与『香凝』对话",
    "objective": {"type": "talk_npc", "npc_id": "npc_beiping_east_香凝", "count": 1},
    "rewards": {"experience": 100, "gold": 100},
    "dialogs": {
        "accept": [
            {"speaker": "香凝", "text": "将军！将军！"},
            {"speaker": "你", "text": "姑娘慌慌张张何事(你脑袋晕乎乎心想不是在做梦？)！"}
        ],
        "complete": [
            {"speaker": "香凝", "text": "刚刚我看到一个黑影鬼鬼祟祟从小姐房中出来，将军快进屋救小姐！"},
            {"speaker": "你", "text": "啊？啊？啊？"}
        ]
    },
    "next_hint": "前往「厢房」与『曹樱』对话",
    "next_quest": "main_02"
}

quests["main_02"] = {
    "id": "main_02", "name": "主·少女初逢", "type": "main",
    "npc_id": "npc_beiping_east_曹樱", "npc_name": "曹樱",
    "npc_location": "beiping_east.厢房", "npc_location_name": "厢房(北平东区)",
    "level_required": 1, "prerequisite": "main_01",
    "description": "前往「厢房」与『曹樱』对话",
    "objective": {"type": "talk_npc", "npc_id": "npc_beiping_east_曹樱", "count": 1},
    "rewards": {"experience": 100, "gold": 100},
    "dialogs": {
        "complete": [
            {"speaker": "曹樱", "text": "将军从天上来，难道会是凡人吗？"},
            {"speaker": "你", "text": "应该不是吧(这是梦还是不是梦呢？)！"},
            {"speaker": "", "text": "(曹樱微微一笑，你顿时看呆了)"},
            {"speaker": "曹樱", "text": "(小小声)将军和梦中长的一样呢..."}
        ]
    },
    "next_quest": "main_03"
}

quests["main_03"] = {
    "id": "main_03", "name": "主·小菜一碟", "type": "main",
    "npc_id": "npc_beiping_east_曹樱", "npc_name": "曹樱",
    "npc_location": "beiping_east.厢房", "npc_location_name": "厢房(北平东区)",
    "level_required": 1, "prerequisite": "main_02",
    "description": "前往「大院」击杀『窃贼』收集1本[青囊书]",
    "objective": {"type": "collect_item", "item_id": "quest_qingnangshu", "item_name": "青囊书", "count": 1, "monster_name": "窃贼"},
    "rewards": {"experience": 100, "gold": 100},
    "dialogs": {
        "accept": [
            {"speaker": "曹樱", "text": "将军刚刚有个『窃贼』把我的[青囊书]偷走了，将军可否帮我抢回来？"},
            {"speaker": "你", "text": "原来那黑影是窃贼，看我这就去取回来。"},
            {"speaker": "曹樱", "text": "窃贼还在大院，将军一定要小心。"}
        ],
        "complete": [
            {"speaker": "曹樱", "text": "感谢将军，将军果然勇猛过人"},
            {"speaker": "你", "text": "嘿嘿，我也这么认为"},
            {"speaker": "曹樱", "text": "将军这么勇猛，不如帮我带封信吧？"},
            {"speaker": "你", "text": "额，行吧..."},
            {"speaker": "曹樱", "text": "略略略，谢谢将军。"}
        ]
    },
    "next_hint": "前往「军营」与『曹彰』对话",
    "next_quest": "main_04"
}

quests["main_04"] = {
    "id": "main_04", "name": "主·初遇曹彰", "type": "main",
    "npc_id": "npc_beiping_east_曹彰", "npc_name": "曹彰",
    "npc_location": "beiping_east.军营", "npc_location_name": "军营(北平东区)",
    "level_required": 1, "prerequisite": "main_03",
    "description": "前往「军营」与『曹彰』对话",
    "objective": {"type": "deliver_item", "item_id": "quest_jiashu", "item_name": "家书", "count": 1, "target_npc": "npc_beiping_east_曹彰"},
    "rewards": {"experience": 100, "gold": 100},
    "dialogs": {
        "accept": [
            {"speaker": "曹彰", "text": "是曹樱叫你来的吗？"},
            {"speaker": "你", "text": "是的，这里有封你的家信。"},
            {"speaker": "曹彰", "text": "那就谢过将军了。"}
        ],
        "complete": [
            {"speaker": "曹彰", "text": "我这就回一封，还请将军带回去一趟。"},
            {"speaker": "你", "text": "好，小事一桩！"}
        ]
    },
    "next_hint": "前往「厢房」与『曹樱』对话",
    "next_quest": "main_05",
    "grant_item": {"item_id": "quest_jiashu", "item_name": "家书", "count": 1}
}

quests["main_05"] = {
    "id": "main_05", "name": "主·飞书传人", "type": "main",
    "npc_id": "npc_beiping_east_曹樱", "npc_name": "曹樱",
    "npc_location": "beiping_east.厢房", "npc_location_name": "厢房(北平东区)",
    "level_required": 1, "prerequisite": "main_04",
    "description": "前往「厢房」与『曹樱』对话",
    "objective": {"type": "deliver_item", "item_id": "quest_jiashu", "item_name": "家书", "count": 1, "target_npc": "npc_beiping_east_曹樱"},
    "rewards": {"experience": 100, "gold": 100},
    "dialogs": {
        "accept": [
            {"speaker": "曹樱", "text": "将军这么这么快就回来了？"},
            {"speaker": "你", "text": "这是曹将军给你回的一封信。"}
        ],
        "complete": [
            {"speaker": "曹樱", "text": "嘻嘻，谢谢将军！"},
            {"speaker": "你", "text": "这次没有啥事了吧？"},
            {"speaker": "曹樱", "text": "麻烦将军把这饭菜带给父亲一下。"},
            {"speaker": "你", "text": "我真多嘴，行吧！"}
        ]
    },
    "next_hint": "前往「军营」与『曹彰』对话",
    "next_quest": "main_06",
    "grant_item": {"item_id": "quest_fancai", "item_name": "饭菜", "count": 1}
}

quests["main_06"] = {
    "id": "main_06", "name": "主·又见曹彰", "type": "main",
    "npc_id": "npc_beiping_east_曹彰", "npc_name": "曹彰",
    "npc_location": "beiping_east.军营", "npc_location_name": "军营(北平东区)",
    "level_required": 1, "prerequisite": "main_05",
    "description": "前往「军营」与『曹彰』对话",
    "objective": {"type": "deliver_item", "item_id": "quest_fancai", "item_name": "饭菜", "count": 1, "target_npc": "npc_beiping_east_曹彰"},
    "rewards": {"experience": 100, "gold": 100},
    "dialogs": {
        "accept": [
            {"speaker": "曹彰", "text": "将军怎么又回来了？"},
            {"speaker": "你", "text": "...你以为我想啊，这是曹樱给你的饭菜。"}
        ]
    }
}

with open('data/quests.json', 'w', encoding='utf-8') as f:
    json.dump(quests, f, ensure_ascii=False, indent=2)
print(f"Updated quests.json with {len(quests)} quests")
PYEOF