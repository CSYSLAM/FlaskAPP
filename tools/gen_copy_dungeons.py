# -*- coding: utf-8 -*-
"""
三国副本任务数据生成器（数据驱动版）。
读取 tools/dungeon_defs.json 中的副本定义，生成：
  - data/copy_dungeons.json 条目
  - data/copy_monsters.json 条目
  - data/monsters.json 入口NPC
  - data/locations/*_copy_live.json 副本场景文件
  - data/locations/<city>.json 城市入口NPC放置
幂等合并写入（已有条目不覆盖）。
运行：venv/bin/python tools/gen_copy_dungeons.py
"""
import json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load(p):
    with open(os.path.join(ROOT, p), 'r', encoding='utf-8') as f:
        return json.load(f)

def dump(p, obj):
    with open(os.path.join(ROOT, p), 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

# ========== 怪物数值 ==========
def mob_stats(level, is_elite):
    m = 2.8 if is_elite else 1.0
    return {"health": int(level * 230 * m), "mana": int(level * 180 * m),
            "attack": int(level * 14 * m), "defense": int(level * 200 * m),
            "crit_rate": 0.08 if is_elite else 0.05, "dodge_rate": 0.08 if is_elite else 0.05}

def mob_drops(level):
    t = max(1, (level // 10) * 5)  # tier: 5, 10, 15 ...
    p = ['helmet', 'armor', 'gloves', 'pants', 'shoes']
    return {"equipment_drop": {"drop_rate": 0.1, "templates": [f"mabu_{x}_{t}" for x in p],
            "rarity_weights": {"common": 60, "uncommon": 40}},
            "items": {"potion_heal": 0.1}, "money": {"min": level, "max": level * 3}, "experience": level * 25}

def safe_key(s):
    d = {'【': '', '】': '', '·': '', '/': '', '(': '', ')': '', '：': '', ' ': '_'}
    return ''.join(d.get(c, c) for c in s).strip('_')

# ========== 城市模板 ==========
CITY_SCENES = ["广场", "客栈", "酒馆", "铁匠铺", "药铺", "驿站", "钱庄", "军营", "太守府"]
CITY_GATES = ["北门", "南门", "东门", "西门"]

def make_city(stem):
    """生成标准城市位置文件"""
    scenes = {}
    for sk in CITY_SCENES:
        scenes[sk] = {"name": sk, "exits": {}}
        for d in CITY_GATES:
            scenes[sk]["exits"][d[-1]] = f"{stem}.{d}"
    for g in CITY_GATES:
        scenes[g] = {"name": g, "exits": {"south" if g == "北门" else "north": f"{stem}.广场"}}
        if g == "北门": scenes[g]["exits"] = {"south": f"{stem}.广场"}
        elif g == "南门": scenes[g]["exits"] = {"north": f"{stem}.广场"}
        elif g == "东门": scenes[g]["exits"] = {"west": f"{stem}.广场"}
        elif g == "西门": scenes[g]["exits"] = {"east": f"{stem}.广场"}
    return {"name": stem, "scenes": scenes}

# ========== 构建函数 ==========
def chest(lv):
    if lv <= 25: return "chest_copy_low"
    if lv <= 45: return "chest_copy_mid"
    return "chest_copy_high_bound"

def build_dungeon(d, defs):
    """从紧凑 JSON 定义生成 copy_dungeons.json 格式"""
    sid = d['id']; lv = d['level']; stem = f"{sid}_copy_live"
    steps_out = []
    givers = d.get('givers', [])
    for i, s in enumerate(d['steps']):
        sn = s['name']; sc = s['scene']
        full_scene = f"{stem}.{sc}"
        # 怪物 key
        mn = s['target_name']; el = s.get('is_elite', False)
        mk = f"mon_{safe_key(sid)}_{safe_key(mn)}" if not el else f"mon_{safe_key(sid)}_elite_{safe_key(mn[3:])}"
        step = {
            "id": f"step_{i+1}", "name": sn,
            "scene_id": full_scene,
            "target_name": s['target_name'],
            "is_elite": s.get('is_elite', False),
            "objective": s['objective'],
            "progress_label": s['progress_label'],
            "story": s['story'],
            "complete_story": s.get('complete_story', ''),
            "target_monsters": [mk],
            "required_count": s['target_count'],
            "reward": {"experience": s.get('reward_exp', int(lv * 420)),
                       "gold": s.get('reward_gold', int(lv * 42)),
                       "items": s.get('reward_items', [])}
        }
        if s.get('quest_giver_name'):
            gk = f"npc_{safe_key(sid)}_{safe_key(s['quest_giver_name'])}"
            step['quest_giver_npc_id'] = gk
            step['quest_giver_location'] = full_scene
        if s.get('required_items'):
            step['required_items'] = s['required_items']
        if s.get('hint'): step['hint'] = s['hint']
        if s.get('complete_hint'): step['complete_hint'] = s['complete_hint']
        steps_out.append(step)
    # givers dict
    gi = []
    for g in givers:
        gk = f"npc_{safe_key(sid)}_{safe_key(g['name'])}"
        gs = f"{stem}.{g['scene']}"
        gi.append({"npc_key": gk, "name": g['name'], "scene": gs})
    entry_scene = d['steps'][0]['scene']
    return {
        "id": sid, "name": d['name'], "level": lv,
        "entry_location": f"{stem}.{entry_scene}",
        "entry_npc_id": f"npc_{d['entry_city_stem']}_{safe_key(d['entry_npc_name'])}副本",
        "entry_npc_name": d['entry_npc_name'],
        "entry_city_stem": d['entry_city_stem'],
        "entry_city_scene": d.get('entry_city_scene', '广场'),
        "return_location": d['return_location'],
        "story_intro": d.get('story_intro', []),
        "story_outro": d.get('story_outro', []),
        "total_reward": {"experience": d.get('total_exp', lv * 600),
                         "gold": d.get('total_gold', lv * 80),
                         "items": [{"item_id": chest(lv), "count": 1}]},
        "steps": steps_out,
        "givers": gi,
    }

def build_copy_dungeons_entry(dungeon):
    """从 build_dungeon 输出生成 final copy_dungeons.json 条目"""
    return {
        "name": dungeon['name'],
        "is_copy_dungeon": True,
        "entry_location": dungeon['entry_location'],
        "entry_npc_id": dungeon['entry_npc_id'],
        "entry_item_id": "shenyou_guo",
        "entry_item_count": 1,
        "return_location": dungeon['return_location'],
        "story_intro": dungeon['story_intro'],
        "story_outro": dungeon['story_outro'],
        "reward": dungeon['total_reward'],
        "steps": [{
            "id": s['id'], "name": s['name'], "scene_id": s['scene_id'],
            "objective": s['objective'], "progress_label": s['progress_label'],
            "target_monsters": s['target_monsters'], "required_count": s['required_count'],
            "story": s['story'], "complete_story": s['complete_story'],
            "reward": s['reward'],
            **({"quest_giver_location": s['quest_giver_location'], "quest_giver_npc_id": s['quest_giver_npc_id']} if s.get('quest_giver_npc_id') else {}),
            **({"required_items": s['required_items']} if s.get('required_items') else {}),
            **({"hint": s['hint']} if s.get('hint') else {}),
            **({"complete_hint": s['complete_hint']} if s.get('complete_hint') else {}),
        } for s in dungeon['steps']]
    }

def build_scene_file(dungeon):
    """生成副本场景文件"""
    sid = dungeon['id']; stem = f"{sid}_copy_live"
    scenes = {}
    for i, s in enumerate(dungeon['steps']):
        sc = s['scene_id']
        parts = sc.rsplit('.', 1)
        sn = parts[1] if len(parts) > 1 else sc
        out = {"name": sn, "exits": {}, "monsters": s['target_monsters'][:1]}
        if i > 0:
            out["exits"]["south"] = dungeon['steps'][i-1]['scene_id']
        if i < len(dungeon['steps']) - 1:
            out["exits"]["north"] = dungeon['steps'][i+1]['scene_id']
        # quest_giver
        if s.get('quest_giver_npc_id'):
            out.setdefault("npcs", []).append(s['quest_giver_npc_id'])
        scenes[sc] = out
    return {"name": sid, "is_copy_map": True, "copy_dungeon_id": sid, "scenes": scenes}

def build_monsters(d):
    sid = d['id']; out = {}
    for s in d['steps']:
        mk = s['target_monsters'][0]
        if mk in out: continue
        lv = d['level']; el = s.get('is_elite', False)
        out[mk] = {
            "name": s['target_name'], "level": lv,
            "is_elite": el, "killable": True, "immortal": False,
            "description": f"【副本怪物】{s['target_name']}",
            "is_copy": True, "copy_only": True,
            "copy_dungeon_id": sid, "copy_stage": s['id'],
            "base_stats": mob_stats(lv, el),
            "skills": ["normal_attack"], "drops": mob_drops(lv),
        }
    for g in d['givers']:
        gk = g['npc_key']
        if gk in out: continue
        out[gk] = {
            "name": g['name'], "level": 50, "is_elite": False,
            "killable": False, "immortal": True,
            "description": f"【副本任务NPC】{g['name']}",
            "is_copy": True, "copy_only": True,
            "copy_dungeon_id": sid, "copy_role": "quest_giver",
            "base_stats": {"health": 99999, "mana": 9999, "attack": 999, "defense": 999,
                           "crit_rate": 0, "dodge_rate": 0},
            "skills": [], "drops": {"equipment_drop": {"drop_rate": 0, "templates": [],
                "rarity_weights": {}}, "items": {}, "money": {"min": 0, "max": 0}, "experience": 0},
        }
    return out

def build_entry_npc(d):
    key = d['entry_npc_id']; name = d['entry_npc_name']
    return {key: {
        "name": f"{name}【副本】", "level": 50, "is_elite": False,
        "killable": False, "immortal": True,
        "description": f"负责副本「{d['name']}」传送",
        "copy_dungeon_id": d['id'], "copy_role": "entry_npc",
        "base_stats": {"health": 99999, "mana": 9999, "attack": 999, "defense": 999,
                       "crit_rate": 0, "dodge_rate": 0},
        "skills": [], "drops": {"equipment_drop": {"drop_rate": 0, "templates": [],
            "rarity_weights": {}}, "items": {}, "money": {"min": 0, "max": 0}, "experience": 0},
        "is_divine_beast": False, "is_copy": False, "copy_only": False, "max_health": 100,
    }}

# ========== 主流程 ==========
def main():
    defs = load("tools/dungeon_defs.json")
    dungeons = [build_dungeon(d, defs) for d in defs['dungeons']]
    city_stems = defs.get('new_cities', [])

    # 1. 创建缺失的城市文件
    for cs in city_stems:
        fn = f"data/locations/{cs}.json"
        if not os.path.exists(os.path.join(ROOT, fn)):
            dump(fn, make_city(cs))
            print(f"city created: {cs}")

    # 2. 写入/合并 copy_dungeons.json
    cd = load("data/copy_dungeons.json")
    added_cd = []
    for d in dungeons:
        if d['id'] not in cd:
            cd[d['id']] = build_copy_dungeons_entry(d)
            added_cd.append(d['id'])
    if added_cd:
        dump("data/copy_dungeons.json", cd)

    # 3. 写入/合并 copy_monsters.json
    cm = load("data/copy_monsters.json")
    added_cm = []
    for d in dungeons:
        for mk, mv in build_monsters(d).items():
            if mk not in cm:
                cm[mk] = mv
                added_cm.append(mk)
    if added_cm:
        dump("data/copy_monsters.json", cm)

    # 4. 写入/合并 monsters.json（入口NPC）
    mf = load("data/monsters.json")
    added_mf = []
    for d in dungeons:
        for nk, nv in build_entry_npc(d).items():
            if nk not in mf:
                mf[nk] = nv
                added_mf.append(nk)
    if added_mf:
        dump("data/monsters.json", mf)

    # 5. 写入副本场景文件
    added_sc = []
    for d in dungeons:
        fn = f"data/locations/{d['id']}_copy_live.json"
        if not os.path.exists(os.path.join(ROOT, fn)):
            dump(fn, build_scene_file(d))
            added_sc.append(d['id'])

    # 6. 在城市场景中放置入口NPC
    placed_npc = []
    for d in dungeons:
        cs = d['entry_city_stem']; sck = d['entry_city_scene']
        fn = f"data/locations/{cs}.json"
        if not os.path.exists(os.path.join(ROOT, fn)):
            print(f"WARN: city scene missing {fn}, skip NPC placement for {d['id']}")
            continue
        loc = load(fn)
        sc = loc.get("scenes", {}).get(sck)
        if not sc:
            print(f"WARN: scene {sck} missing in {cs}, skip NPC for {d['id']}")
            continue
        sc.setdefault("npcs", [])
        nk = d['entry_npc_id']
        if nk not in sc["npcs"]:
            sc["npcs"].append(nk)
            dump(fn, loc)
            placed_npc.append(f"{cs}.{sck}:{nk}")

    print(f"copy_dungeons  added: {added_cd}")
    print(f"copy_monsters  added: {len(added_cm)}")
    print(f"entry NPCs     added: {added_mf}")
    print(f"scenes         added: {added_sc}")
    print(f"NPC placements : {placed_npc}")

    # 验证
    print("--- validation ---")
    verr = 0
    for d in dungeons:
        nk = d['entry_npc_id']
        nl = d['entry_location']
        if nk not in mf:
            print(f"MISS entry NPC: {nk} for {d['id']}")
            verr += 1
        if nl not in scenes_created(d['id']):
            print(f"MISS entry scene: {nl} for {d['id']}")
            verr += 1
    print(f"validation errors: {verr}")

def scenes_created(did):
    # 辅助：返回已创建的副本场景列表
    fn = f"data/locations/{did}_copy_live.json"
    p = os.path.join(ROOT, fn)
    if not os.path.exists(p): return []
    return list(load(fn).get("scenes", {}).keys())

if __name__ == "__main__":
    main()
