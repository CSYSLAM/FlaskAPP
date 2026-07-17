"""
扩展所有副本步数到 15-20 步。在每个副本的现有步骤序列中插入新步骤，
保持剧情连贯。运行后需重新运行 gen_copy_dungeons.py。
"""
import json, os
os.chdir('/mnt/FlaskAPP')

fn = 'tools/dungeon_defs.json'
d = json.load(open(fn, 'r', encoding='utf-8'))

def dlv(l): return 420 * l

def mk_step(name, scene, target_name, target_count, obj, progress, story, complete,
            is_elite=False, qgiv_name=None, qgiv_scene=None,
            hint_complete=None, reward_gold=None):
    s = {
        'name': name, 'scene': scene, 'target_name': target_name,
        'target_count': target_count,
        'objective': obj, 'progress_label': progress,
        'story': story, 'complete_story': complete,
        'is_elite': is_elite,
        'reward_exp': 420 * 48,  # default, will be overridden
    }
    if qgiv_name:
        s['quest_giver_name'] = qgiv_name
        s['quest_giver_scene'] = qgiv_scene
    if hint_complete: s['complete_hint'] = hint_complete
    if reward_gold: s['reward_gold'] = reward_gold
    return s

# Returns a function that sets correct reward_exp for a given level
def with_lvl(lvl):
    def _s(**kw):
        s = mk_step(**kw)
        s['reward_exp'] = dlv(lvl)
        return s
    return _s

# ================================================================
# EXTRA STEPS for each dungeon (to be inserted into existing chain)
# Format: {dungeon_id: [(insert_after_idx, [list of new steps]), ...]}
# insert_after_idx is 0-based index of existing step after which to insert
# ================================================================

EXTRA = {}
