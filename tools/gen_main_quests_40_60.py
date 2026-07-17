# -*- coding: utf-8 -*-
"""
生成 40-60 级「共享主线」任务（三国角色通用，不分国家）。

故事：《汉室余晖·烽火四城》
  一股隐秘势力「烬焰盟」（首领代号烛龙）借中立四城为跳板，图谋重启烽火。
  玩家作为本国使者，循 下邳(40-46) → 江陵(47-51) → 汉中(52-54) → 洛阳(55-60)
  追查真相，串联水镜先生、蔡文姬等角色，最终在洛阳了断。

- 任务 id 前缀 main_all_，对所有国家开放（quest_service 已做对应放开）。
- 生成器以「合并」方式写入，不会覆盖已有任务/NPC。
运行： venv/bin/python tools/gen_main_quests_40_60.py
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(p):
    with open(os.path.join(ROOT, p), 'r', encoding='utf-8') as f:
        return json.load(f)


def dump(p, obj):
    with open(os.path.join(ROOT, p), 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def rewards_for(level):
    return {
        "experience": 18000 + (level - 39) * 2200,
        "gold": 1200 + (level - 39) * 150,
        "honor": 4 + (level - 39) // 2,
    }


# ---------------------------------------------------------------------------
# 1) 任务物品（用于 deliver 链）
# ---------------------------------------------------------------------------
QUEST_ITEMS = {
    "quest_jinmi_xin": {"name": "烬焰密信", "type": "quest",
                         "description": "截获的烬焰盟密信，墨迹未干，暗藏接头暗号。",
                         "price": 0, "sell_price": 0, "is_usable": False, "capacity": 0},
    "quest_yuxi_tapan": {"name": "玉玺拓片", "type": "quest",
                         "description": "江陵水寨密室中所得的传国玉玺拓片，纹路诡谲。",
                         "price": 0, "sell_price": 0, "is_usable": False, "capacity": 0},
    "quest_luoyang_bu": {"name": "洛阳布防图", "type": "quest",
                          "description": "汉中军帐中夺得的洛阳布防图，标注烛龙总坛虚实。",
                          "price": 0, "sell_price": 0, "is_usable": False, "capacity": 0},
    "quest_chuanguo_yuxi": {"name": "传国玉玺", "type": "quest",
                             "description": "失传已久的传国玉玺，和氏之璧琢成，乃天下气运所系。",
                             "price": 0, "sell_price": 0, "is_usable": False, "capacity": 0},
}

# ---------------------------------------------------------------------------
# 2) NPC 阵容（重复出场以保证剧情连贯）
#    key -> (name, location_file_stem, scene_key, description)
# ---------------------------------------------------------------------------
NPCS = {
    "npc_xiapi_center_水镜先生": ("水镜先生", "xiapi_center", "广场",
        "隐居下邳的世外高人，洞悉天下大势，看似慵懒却句句机锋，点破「烬焰盟」之名。"),
    "npc_xiapi_center_蔡文姬": ("蔡文姬", "xiapi_center", "客栈",
        "流落下邳的才女，琴棋书画皆绝，手中似藏着传国玉玺的惊天线索。"),
    "npc_xiapi_center_糜竺": ("糜竺", "xiapi_center", "钱庄",
        "下邳糜氏商号之主，富甲一方，近来商队屡生异状，面上堆笑心底难测。"),
    "npc_xiapi_center_陈宫": ("陈宫", "xiapi_center", "太守府",
        "下邳旧臣，智谋深沉，心系城中百姓，对权争早生倦意。"),
    "npc_xiapi_center_影": ("影", "xiapi_center", "酒馆",
        "游走街巷的神秘客，言语飘忽，似在打探什么，又与烬焰盟脱不了干系。"),
    "npc_jiangling_center_黄承彦": ("黄承彦", "jiangling_center", "广场",
        "荆襄名士，黄月英之父，淡泊名利却明察秋毫，一语点破玉玺之祸。"),
    "npc_jiangling_center_苏飞": ("苏飞", "jiangling_center", "钱庄",
        "江陵船王，水面上的门道无所不知，豪爽中藏着几分狡黠。"),
    "npc_jiangling_center_黄祖": ("黄祖", "jiangling_center", "太守府",
        "江陵守将，老成持重，初时忌惮义军，终为大局所动。"),
    "npc_jiangling_center_蔡文姬": ("蔡文姬", "jiangling_center", "客栈",
        "随你辗转至江陵，却被烬焰盟探子盯上，危在旦夕。"),
    "npc_jiangling_center_影": ("影", "jiangling_center", "酒馆",
        "在江陵重现的神秘客，此番似在替烬焰盟清剿知情者。"),
    "npc_hanzhong_center_田豫": ("田豫", "hanzhong_center", "广场",
        "镇北将军，坐镇汉中，治军严明，是阻断烬焰盟粮道的中流砥柱。"),
    "npc_hanzhong_center_胡昭": ("胡昭", "hanzhong_center", "酒馆",
        "汉中隐士，书法兵法双绝，司马懿之师，藏有克制烬焰盟的机要。"),
    "npc_luoyang_center_荀爽": ("荀爽", "luoyang_center", "广场",
        "残汉太傅，须发皆白而风骨犹存，愿开洛阳城门纳天下义师。"),
    "npc_luoyang_center_烛龙": ("烛龙", "luoyang_center", "皇宫",
        "蛰伏宗亲，表面温润，实则野心滔天，欲借传国玉玺再起烽火。"),
    "npc_luoyang_center_蔡文姬": ("蔡文姬", "luoyang_center", "客栈",
        "脱险后随你入洛阳，以琴声与才学助你安定人心。"),
    "npc_luoyang_center_影": ("影", "luoyang_center", "酒馆",
        "烛龙麾下得力臂助，至此图穷匕见，拦在义军之前。"),
    "npc_luoyang_center_残汉老臣": ("残汉老臣", "luoyang_center", "军营",
        "洛阳宫中老臣，亲历倾覆，誓要护住最后一点汉室尊严。"),
}

# 水镜先生在汉中亦出场（复用同一 NPC key，跨城放置）
NPC_EXTRA_PLACEMENTS = {
    "npc_xiapi_center_水镜先生": [("hanzhong_center", "广场")],
}

NPC_TMPL = {
    "level": 50, "is_elite": False, "killable": False, "immortal": True,
    "base_stats": {"health": 99999, "mana": 9999, "attack": 999, "defense": 999,
                   "crit_rate": 0, "dodge_rate": 0},
    "skills": [],
    "drops": {"equipment_drop": {"drop_rate": 0, "templates": [], "rarity_weights": {}},
              "items": {}, "money": {"min": 0, "max": 0}, "experience": 0},
    "is_divine_beast": False, "is_copy": False, "copy_only": False, "max_health": 100,
}

# ---------------------------------------------------------------------------
# 2b) 击杀目标怪物（用于 kill_monster 链）
#     (name, level, location_stem, scene_key)
#     怪物按 name 匹配击杀进度，因此 name 必须与任务 objective.monster_name 完全一致。
#     统一以 monster_q_<name> 为 key，避免与世界中已有的同名杂兵（如吴军守卫）撞 key。
# ---------------------------------------------------------------------------
MOB_TARGETS = [
    ("应龙", 40, "xiapi_south", "南门"),
    ("吴军守卫", 42, "xiapi_south", "南门"),
    ("魏军守卫", 43, "xiapi_east", "东门"),
    ("孙桓", 45, "xiapi_east", "东门"),
    ("蜀军守卫", 44, "xiapi_west", "西门"),
    ("庞德", 46, "xiapi_north", "北门"),
    ("吴军前锋", 48, "jiangling_west", "西门"),
    ("孙静", 48, "jiangling_east", "东门"),
    ("刘封", 49, "jiangling_west", "西门"),
    ("步骘", 50, "jiangling_west", "西门"),
    ("潘章", 51, "jiangling_north", "北门"),
    ("灵火道人", 53, "hanzhong_west", "西门"),
    ("廖化", 53, "hanzhong_south", "南门"),
    ("张济", 55, "luoyang_north", "北门"),
    ("徐荣", 56, "luoyang_west", "西门"),
    ("虎豹队长", 57, "luoyang_south", "南门"),
    ("连弩队长", 58, "luoyang_center", "广场"),
    ("神秘将军", 59, "luoyang_north", "北门"),
    ("青龙", 59, "luoyang_north", "北门"),
    ("玄武", 60, "luoyang_north", "北门"),
]


def mob_stats(level):
    """按普通杂兵标准缩放（参考 43 级基准: hp10900/atk180/def7000/exp610）。"""
    d = level - 43
    hp = 10900 + d * 300
    atk = 180 + d * 4
    defense = 7000 + d * 160
    exp = 610 + d * 33
    return ({"health": hp, "mana": max(500, hp // 8), "attack": atk,
             "defense": defense, "crit_rate": 0.05, "dodge_rate": 0.05}, exp)


def mob_key(name):
    return f"monster_q_{name}"


def build_monsters():
    monsters = load("data/monsters.json")
    added = []
    for name, level, stem, scene in MOB_TARGETS:
        key = mob_key(name)
        if key not in monsters:
            bs, exp = mob_stats(level)
            monsters[key] = {
                "name": name, "level": level, "is_elite": False,
                "killable": True, "immortal": False,
                "description": f"烬焰盟爪牙【{name}】，阻于{stem}.{scene}。",
                "base_stats": bs,
                "skills": ["normal_attack"],
                "drops": {"equipment_drop": {"drop_rate": 0, "templates": [],
                                             "rarity_weights": {}},
                          "items": {}, "money": {"min": 30 + level * 2,
                                                 "max": 80 + level * 4},
                          "experience": exp},
                "is_divine_beast": False, "is_copy": False, "copy_only": False,
                "max_health": 100,
            }
            added.append(key)
    if added:
        dump("data/monsters.json", monsters)
    # 把怪物放到目标 scene 的 monsters 数组（追加，不覆盖已有）
    placed = []
    for name, level, stem, scene in MOB_TARGETS:
        fn = f"data/locations/{stem}.json"
        if not os.path.exists(fn):
            continue
        loc = load(fn)
        sc = loc.get("scenes", {}).get(scene)
        if not sc:
            continue
        sc.setdefault("monsters", [])
        key = mob_key(name)
        if key not in sc["monsters"]:
            sc["monsters"].append(key)
            dump(fn, loc)
            placed.append(f"{stem}.{scene}:{name}")
    return added, placed


def build_npcs():
    monsters = load("data/monsters.json")
    added = []
    for key, (name, stem, scene, desc) in NPCS.items():
        if key not in monsters:
            npc = dict(NPC_TMPL)
            npc["name"] = name
            npc["description"] = desc
            monsters[key] = npc
            added.append(key)
    # 跨城复用放置
    for key, places in NPC_EXTRA_PLACEMENTS.items():
        for stem, scene in places:
            _add_npc_to_scene(stem, scene, key)
    # 本城放置
    for key, (name, stem, scene, desc) in NPCS.items():
        _add_npc_to_scene(stem, scene, key)
    if added:
        dump("data/monsters.json", monsters)
    return added


def _add_npc_to_scene(stem, scene, key):
    fn = f"data/locations/{stem}.json"
    if not os.path.exists(fn):
        return
    loc = load(fn)
    sc = loc.get("scenes", {}).get(scene)
    if not sc:
        return
    sc.setdefault("npcs", [])
    if key not in sc["npcs"]:
        sc["npcs"].append(key)
        dump(fn, loc)


# ---------------------------------------------------------------------------
# 3) 任务数据
# ---------------------------------------------------------------------------
def dlg(accept, complete):
    out = {}
    if accept:
        out["accept"] = accept
    if complete:
        out["complete"] = complete
    return out


QUESTS = []

# ===== 下邳 40-46 (14 个) =====
QUESTS += [
dict(id="main_all_40a", name="主·烽烟初探", type="main",
     npc_id="npc_xiapi_center_水镜先生", npc_name="水镜先生",
     npc_location="xiapi_center.广场", npc_location_name="广场(下邳中区)",
     level_required=40, description="前往「广场」与水镜先生对话，领受追查使节失踪之命。",
     objective={"type": "talk_npc", "npc_id": "npc_xiapi_center_水镜先生", "count": 1},
     rewards=rewards_for(40),
     dialogs=dlg(
        [{"speaker":"水镜先生","text":"小友自远方来，眉间却锁着烽火色。天下似静，实则暗流已起。"},
         {"speaker":"你","text":"先生慧眼。我奉主公之命借道下邳，怎料本国数批使节尽数失踪，音讯全无。"},
         {"speaker":"水镜先生","text":"失踪的何止使节。近来下邳商队屡遭劫，军械私运成风——你可知『烬焰盟』？"},
         {"speaker":"你","text":"烬焰盟？听来不似寻常贼匪。"},
         {"speaker":"水镜先生","text":"此盟借中立四城为跳板，图谋重启烽火。你既撞上，便由你查清吧。"}],
        [{"speaker":"水镜先生","text":"去寻那流落城中的蔡文姬，她手中或有你想要的线索。切莫声张。"},
         {"speaker":"你","text":"弟子遵命。这局棋，我便替天下先落一子。"}]),
     next_hint="前往「客栈」与蔡文姬对话", next_quest="main_all_40b"),

dict(id="main_all_40b", name="主·夜巷妖影", type="main",
     npc_id="npc_xiapi_center_水镜先生", npc_name="水镜先生",
     npc_location="xiapi_center.广场", npc_location_name="广场(下邳中区)",
     level_required=40, prerequisite="main_all_40a",
     description="下邳南郊妖兽作乱，疑为烬焰盟纵妖。前往「下邳南」击杀1头【应龙】。",
     objective={"type": "kill_monster", "monster_name": "应龙", "count": 1},
     rewards=rewards_for(40),
     dialogs=dlg(
        [{"speaker":"水镜先生","text":"南郊传来喊杀，应是烬焰盟纵出的妖兽『应龙』在噬人。"},
         {"speaker":"你","text":"纵妖害人，好狠的手段。我这就去除了它。"}],
        [{"speaker":"你","text":"妖兽已诛，只是它颈间挂一枚烬焰盟的青铜令。"},
         {"speaker":"水镜先生","text":"果然是他们。此令所刻『烛龙』二字，便是那盟主代号。记下了。"}]),
     target_location="xiapi_south.南门", next_hint="前往「客栈」与蔡文姬对话", next_quest="main_all_41a"),

dict(id="main_all_41a", name="主·文姬之秘", type="main",
     npc_id="npc_xiapi_center_蔡文姬", npc_name="蔡文姬",
     npc_location="xiapi_center.客栈", npc_location_name="客栈(下邳中区)",
     level_required=41, prerequisite="main_all_40b",
     description="前往「客栈」与蔡文姬对话，探听传国玉玺的线索。",
     objective={"type": "talk_npc", "npc_id": "npc_xiapi_center_蔡文姬", "count": 1},
     rewards=rewards_for(41),
     dialogs=dlg(
        [{"speaker":"蔡文姬","text":"将军来临，文姬失礼了。我自洛阳逃出，只因先父留下一纸残图……"},
         {"speaker":"你","text":"残图所绘何物？"},
         {"speaker":"蔡文姬","text":"是传国玉玺的拓影。烬焰盟正满天下搜寻此图，似要用玉玺重立新廷。"}],
        [{"speaker":"你","text":"玉玺若落贼手，天下必再大乱。此图可否交我保管？"},
         {"speaker":"蔡文姬","text":"文姬性命犹是将军所护，何况一纸残图。只是图在江陵旧友处留有一份拓片。"}]),
     next_hint="前往「钱庄」与糜竺对话，查军械私运", next_quest="main_all_41b"),

dict(id="main_all_41b", name="主·钱庄暗账", type="main",
     npc_id="npc_xiapi_center_糜竺", npc_name="糜竺",
     npc_location="xiapi_center.钱庄", npc_location_name="钱庄(下邳中区)",
     level_required=41, prerequisite="main_all_41a",
     description="前往「钱庄」与糜竺对话，旁敲军械私运的账册。",
     objective={"type": "talk_npc", "npc_id": "npc_xiapi_center_糜竺", "count": 1},
     rewards=rewards_for(41),
     dialogs=dlg(
        [{"speaker":"糜竺","text":"将军驾临，蓬荜生辉。小号做的是正经买卖，将军莫要见外。"},
         {"speaker":"你","text":"糜公富甲一方，近来北上商队却屡屡出事，可是有人借贵号渠道转运军械？"},
         {"speaker":"糜竺","text":"……（面色微变）将军说笑了，军械岂是商号敢碰的。"}],
        [{"speaker":"你","text":"你袖中那页暗账，边角烙着烬焰盟的火印，以为我未见？"},
         {"speaker":"糜竺","text":"（长叹）将军明鉴。实是被人挟持，不得已而为之。南郊码头今夜便有一船私货。"}]),
     next_hint="前往「南门」截击私运船", next_quest="main_all_42a"),

dict(id="main_all_42a", name="主·截江夺货", type="main",
     npc_id="npc_xiapi_center_糜竺", npc_name="糜竺",
     npc_location="xiapi_center.钱庄", npc_location_name="钱庄(下邳中区)",
     level_required=42, prerequisite="main_all_41b",
     description="南郊码头守卫阻截私运，前往「下邳南」击杀1名【吴军守卫】。",
     objective={"type": "kill_monster", "monster_name": "吴军守卫", "count": 1},
     rewards=rewards_for(42),
     dialogs=dlg(
        [{"speaker":"糜竺","text":"今夜子时，私船靠南郊码头。将军若能截下，糜某感恩戴德。"},
         {"speaker":"你","text":"看是哪路人马敢在下邳撒野。"}],
        [{"speaker":"你","text":"守卫已除，船舱里尽是烬焰盟的甲胄弓弩。"},
         {"speaker":"糜竺","text":"多谢将军。这其中牵扯的，怕不只是一个下邳。"}]),
     target_location="xiapi_south.南门", next_hint="前往「酒馆」会神秘客影", next_quest="main_all_42b"),

dict(id="main_all_42b", name="主·影中之人", type="main",
     npc_id="npc_xiapi_center_影", npc_name="影",
     npc_location="xiapi_center.酒馆", npc_location_name="酒馆(下邳中区)",
     level_required=42, prerequisite="main_all_42a",
     description="前往「酒馆」与神秘客影对话，试探烬焰盟底细。",
     objective={"type": "talk_npc", "npc_id": "npc_xiapi_center_影", "count": 1},
     rewards=rewards_for(42),
     dialogs=dlg(
        [{"speaker":"影","text":"将军好手段，连南郊的船都翻了。可惜，螳螂捕蝉。"},
         {"speaker":"你","text":"你是烬焰盟的人？烛龙又是谁？"},
         {"speaker":"影","text":"将军不必知道太多。玉玺的线索，盟里迟早会亲手取回。"}],
        [{"speaker":"你","text":"取回？怕是取不回了。你主子藏在洛阳，我迟早寻去。"},
         {"speaker":"影","text":"（冷笑）那便洛阳见。只是将军护着的那位才女，未必能熬到那时。"}]),
     next_hint="前往「客栈」护住蔡文姬", next_quest="main_all_43a"),

dict(id="main_all_43a", name="主·客栈惊变", type="main",
     npc_id="npc_xiapi_center_蔡文姬", npc_name="蔡文姬",
     npc_location="xiapi_center.客栈", npc_location_name="客栈(下邳中区)",
     level_required=43, prerequisite="main_all_42b",
     description="烬焰盟探子围了客栈，前往「下邳东」击杀1名【魏军守卫】解围。",
     objective={"type": "kill_monster", "monster_name": "魏军守卫", "count": 1},
     rewards=rewards_for(43),
     dialogs=dlg(
        [{"speaker":"蔡文姬","text":"将军！门外来了许多生脸人，腰间皆是乌金短刃，分明是烬焰盟的死士。"},
         {"speaker":"你","text":"你且退后。这些人，我来解决。"}],
        [{"speaker":"你","text":"围客栈的死士已清。文姬，你须臾不离我左右。"},
         {"speaker":"蔡文姬","text":"（盈泪）文姬这条命，早系在将军身上了。"}]),
     target_location="xiapi_east.东门", next_hint="前往「太守府」见陈宫", next_quest="main_all_43b"),

dict(id="main_all_43b", name="主·旧臣筹谋", type="main",
     npc_id="npc_xiapi_center_陈宫", npc_name="陈宫",
     npc_location="xiapi_center.太守府", npc_location_name="太守府(下邳中区)",
     level_required=43, prerequisite="main_all_43a",
     description="前往「太守府」与陈宫对话，商定肃清下邳暗桩之策。",
     objective={"type": "talk_npc", "npc_id": "npc_xiapi_center_陈宫", "count": 1},
     rewards=rewards_for(43),
     dialogs=dlg(
        [{"speaker":"陈宫","text":"将军为下邳除害，陈某感佩。只是暗桩盘根错节，非一日可清。"},
         {"speaker":"你","text":"暗桩之首可在城中？"},
         {"speaker":"陈宫","text":"有一封密信将送往洛阳，执信者便是关键。将军若能截下，便可顺藤摸瓜。"}],
        [{"speaker":"你","text":"密信我志在必得。陈公且稳坐下邳，清扫余孽之事便交我。"},
         {"speaker":"陈宫","text":"有将军此言，下邳百姓可安心了。"}]),
     next_hint="前往「西后街」截获密信信使", next_quest="main_all_44a"),

dict(id="main_all_44a", name="主·截获密信", type="main",
     npc_id="npc_xiapi_center_陈宫", npc_name="陈宫",
     npc_location="xiapi_center.太守府", npc_location_name="太守府(下邳中区)",
     level_required=44, prerequisite="main_all_43b",
     description="西后街杀出烬焰盟信使，前往「下邳西」击杀1名【蜀军守卫】夺信。",
     objective={"type": "kill_monster", "monster_name": "蜀军守卫", "count": 1},
     rewards=rewards_for(44),
     dialogs=dlg(
        [{"speaker":"陈宫","text":"信使已从西城溜出，将军快追！信在则线索在。"},
         {"speaker":"你","text":"他跑不出下邳。"}],
        [{"speaker":"你","text":"信使已诛，密信到手。封皮烙着火印，内书『洛阳总坛，节度汉中』。"},
         {"speaker":"陈宫","text":"好！顺着此信，将军的下一站便是江陵——玉玺拓片在彼处。"}]),
     target_location="xiapi_west.西门", next_hint="将密信交回陈宫", next_quest="main_all_44b",
     grant_item={"item_id": "quest_jinmi_xin", "item_name": "烬焰密信", "count": 1}),

dict(id="main_all_44b", name="主·密信呈交", type="main",
     npc_id="npc_xiapi_center_陈宫", npc_name="陈宫",
     npc_location="xiapi_center.太守府", npc_location_name="太守府(下邳中区)",
     level_required=44, prerequisite="main_all_44a",
     description="将截获的【烬焰密信】呈交陈宫，了结下邳之局。",
     objective={"type": "deliver_item", "item_id": "quest_jinmi_xin", "item_name": "烬焰密信",
                "count": 1, "target_npc": "npc_xiapi_center_陈宫"},
     rewards=rewards_for(44),
     dialogs=dlg(
        [{"speaker":"陈宫","text":"将军竟真把信追了回来。不知信中写了什么？"},
         {"speaker":"你","text":"信已在此，陈公过目。"}],
        [{"speaker":"陈宫","text":"（展信色变）好狠的算计——他们要在汉中囤粮聚兵，断褒斜道！"},
         {"speaker":"你","text":"下邳既清，我明日便下江陵。文姬，随我同去。"}]),
     next_hint="前往「客栈」与蔡文姬作别下邳", next_quest="main_all_45a"),

dict(id="main_all_45a", name="主·文姬随行", type="main",
     npc_id="npc_xiapi_center_蔡文姬", npc_name="蔡文姬",
     npc_location="xiapi_center.客栈", npc_location_name="客栈(下邳中区)",
     level_required=45, prerequisite="main_all_44b",
     description="前往「客栈」与蔡文姬道别下邳，邀其同赴江陵。",
     objective={"type": "talk_npc", "npc_id": "npc_xiapi_center_蔡文姬", "count": 1},
     rewards=rewards_for(45),
     dialogs=dlg(
        [{"speaker":"蔡文姬","text":"将军要去江陵寻那拓片？文姬愿随行，多一人多一分力气。"},
         {"speaker":"你","text":"正缺你这样的明白人。只是路途凶险。"},
         {"speaker":"蔡文姬","text":"凶险又如何？玉玺之秘，文姬本就脱不得干系。"}],
        [{"speaker":"你","text":"好，收拾行装，我们走水路下江陵。"},
         {"speaker":"蔡文姬","text":"（浅笑）这一路，有将军在，文姬心安。"}]),
     next_hint="前往「东门」扫除拦路贼", next_quest="main_all_45b"),

dict(id="main_all_45b", name="主·东郊突围", type="main",
     npc_id="npc_xiapi_center_蔡文姬", npc_name="蔡文姬",
     npc_location="xiapi_center.客栈", npc_location_name="客栈(下邳中区)",
     level_required=45, prerequisite="main_all_45a",
     description="出城遭烬焰盟伏击，前往「下邳东」击杀1名【孙桓】开路。",
     objective={"type": "kill_monster", "monster_name": "孙桓", "count": 1},
     rewards=rewards_for(45),
     dialogs=dlg(
        [{"speaker":"蔡文姬","text":"将军！东门外伏兵四起，是冲我们来的！"},
         {"speaker":"你","text":"区区伏兵，挡不住我。文姬退后。"}],
        [{"speaker":"你","text":"孙桓已倒，去路已通。上船！"},
         {"speaker":"蔡文姬","text":"（回望下邳）这座城，算是与将军结了缘。"}]),
     target_location="xiapi_east.东门", next_hint="前往「军营」辞别水镜先生", next_quest="main_all_46a"),

dict(id="main_all_46a", name="主·水镜赠言", type="main",
     npc_id="npc_xiapi_center_水镜先生", npc_name="水镜先生",
     npc_location="xiapi_center.广场", npc_location_name="广场(下邳中区)",
     level_required=46, prerequisite="main_all_45b",
     description="前往「广场」向水镜先生辞行，听其一语点破全局。",
     objective={"type": "talk_npc", "npc_id": "npc_xiapi_center_水镜先生", "count": 1},
     rewards=rewards_for(46),
     dialogs=dlg(
        [{"speaker":"水镜先生","text":"将军要去江陵了？江陵水寨深，玉玺拓片怕没那么好取。"},
         {"speaker":"你","text":"再深的水，也要蹚一蹚。"},
         {"speaker":"水镜先生","text":"记住：烬焰盟图的是『名』——传国玉玺在手，便可挟名以令诸侯。破其名，则局自解。"}],
        [{"speaker":"你","text":"先生一语，胜读十年兵书。他日洛阳事了，再来向先生讨酒。"},
         {"speaker":"水镜先生","text":"（抚须而笑）老夫备着呢。去吧。"}]),
     next_hint="前往「北城楼」击退追兵，了结下邳篇", next_quest="main_all_46b"),

dict(id="main_all_46b", name="主·下邳落幕", type="main",
     npc_id="npc_xiapi_center_水镜先生", npc_name="水镜先生",
     npc_location="xiapi_center.广场", npc_location_name="广场(下邳中区)",
     level_required=46, prerequisite="main_all_46a",
     description="烬焰盟最后一批追兵扑向北城楼，前往「下邳北」击杀1名【庞德】。",
     objective={"type": "kill_monster", "monster_name": "庞德", "count": 1},
     rewards=rewards_for(46),
     dialogs=dlg(
        [{"speaker":"水镜先生","text":"追兵上来了，将军且去北城楼料理，老夫在此煮茶相候。"},
         {"speaker":"你","text":"一盏茶的工夫，便回来。"}],
        [{"speaker":"你","text":"庞德授首，下邳再无烬焰盟的旗号。"},
         {"speaker":"水镜先生","text":"下邳篇至此收束。将军，江陵的风浪，才刚起。"}]),
     target_location="xiapi_north.北门", next_hint="乘船前往江陵", next_quest="main_all_47a"),
]

# ===== 江陵 47-51 (10 个) =====
QUESTS += [
dict(id="main_all_47a", name="主·江陵初临", type="main",
     npc_id="npc_jiangling_center_黄承彦", npc_name="黄承彦",
     npc_location="jiangling_center.广场", npc_location_name="广场(江陵中区)",
     level_required=47, prerequisite="main_all_46b",
     description="舟抵江陵，前往「广场」与黄承彦对话，问玉玺拓片下落。",
     objective={"type": "talk_npc", "npc_id": "npc_jiangling_center_黄承彦", "count": 1},
     rewards=rewards_for(47),
     dialogs=dlg(
        [{"speaker":"黄承彦","text":"自北边来的贵人？江陵水土养人，却也养出了不少暗鬼。"},
         {"speaker":"你","text":"先生可知一纸玉玺拓片，流落江陵水寨？"},
         {"speaker":"黄承彦","text":"玉玺……（摇头）此物不是福，是祸。水寨之主得了拓片，夜夜不安，前日竟有人潜入欲夺。"}],
        [{"speaker":"你","text":"拓片既在江陵，我便去水寨走一遭。"},
         {"speaker":"黄承彦","text":"将军且慎。水寨之主苏飞，面上豪爽，心底却深。"}]),
     next_hint="前往「钱庄」寻船王苏飞", next_quest="main_all_47b"),

dict(id="main_all_47b", name="主·船王之诺", type="main",
     npc_id="npc_jiangling_center_苏飞", npc_name="苏飞",
     npc_location="jiangling_center.钱庄", npc_location_name="钱庄(江陵中区)",
     level_required=47, prerequisite="main_all_47a",
     description="前往「钱庄」与船王苏飞对话，谋潜入水寨之法。",
     objective={"type": "talk_npc", "npc_id": "npc_jiangling_center_苏飞", "count": 1},
     rewards=rewards_for(47),
     dialogs=dlg(
        [{"speaker":"苏飞","text":"哟，贵客。江陵的水，某家最熟。将军想要进寨子？那得看值不值。"},
         {"speaker":"你","text":"苏当家若肯助我潜入水寨，这份情，某记下了。"},
         {"speaker":"苏飞","text":"（大笑）爽快！明夜子时，某亲驾小舟，送将军入寨。"}],
        [{"speaker":"你","text":"既如此，便依苏当家。玉玺拓片，我志在必得。"},
         {"speaker":"苏飞","text":"将军好胆。只是寨中守卫彪悍，将军当心。"}]),
     next_hint="入夜前往水寨，击退巡哨", next_quest="main_all_48a"),

dict(id="main_all_48a", name="主·夜潜水寨", type="main",
     npc_id="npc_jiangling_center_苏飞", npc_name="苏飞",
     npc_location="jiangling_center.钱庄", npc_location_name="钱庄(江陵中区)",
     level_required=48, prerequisite="main_all_47b",
     description="随苏飞潜入水寨，巡哨阻路，前往「江陵西」击杀1名【吴军前锋】。",
     objective={"type": "kill_monster", "monster_name": "吴军前锋", "count": 1},
     rewards=rewards_for(48),
     dialogs=dlg(
        [{"speaker":"苏飞","text":"到了，前头便是巡哨。将军手脚轻些。"},
         {"speaker":"你","text":"哨卫交给我，苏当家且在外接应。"}],
        [{"speaker":"你","text":"巡哨已清。密室就在前头，拓片必在其中。"},
         {"speaker":"苏飞","text":"将军好身手。某在外头望风，快去快回。"}]),
     target_location="jiangling_west.西门", next_hint="前往「客栈」安抚蔡文姬", next_quest="main_all_48b"),

dict(id="main_all_48b", name="主·文姬遇险", type="main",
     npc_id="npc_jiangling_center_蔡文姬", npc_name="蔡文姬",
     npc_location="jiangling_center.客栈", npc_location_name="客栈(江陵中区)",
     level_required=48, prerequisite="main_all_48a",
     description="回客栈惊觉文姬被掳，前往「江陵东」击杀1名【孙静】逼问下落。",
     objective={"type": "kill_monster", "monster_name": "孙静", "count": 1},
     rewards=rewards_for(48),
     dialogs=dlg(
        [{"speaker":"店家","text":"将军！方才几个黑衣人闯进房，把那位姑娘掳走了！"},
         {"speaker":"你","text":"（按剑）追！东面有动静，定是那伙贼人。"},
         {"speaker":"你","text":"孙静，文姬在哪？说！"}],
        [{"speaker":"你","text":"孙静已亡，线索指向水寨密室——他们要把文姬带去洛阳！"},
         {"speaker":"蔡文姬","text":"（远处呼救）将军——救我——"},
         {"speaker":"你","text":"文姬莫怕，我这就来。"}]),
     target_location="jiangling_east.东门", next_hint="杀回水寨密室救人", next_quest="main_all_49a"),

dict(id="main_all_49a", name="主·密室夺图", type="main",
     npc_id="npc_jiangling_center_苏飞", npc_name="苏飞",
     npc_location="jiangling_center.钱庄", npc_location_name="钱庄(江陵中区)",
     level_required=49, prerequisite="main_all_48b",
     description="随苏飞再入水寨密室，守卫顽抗，前往「江陵西」击杀1名【刘封】夺回拓片与文姬。",
     objective={"type": "kill_monster", "monster_name": "刘封", "count": 1},
     rewards=rewards_for(49),
     dialogs=dlg(
        [{"speaker":"苏飞","text":"密室在后头水牢，某带你抄近路。"},
         {"speaker":"你","text":"文姬若在，拼死也要带她出来。"}],
        [{"speaker":"你","text":"刘封伏诛，拓片到手，文姬也救下了！"},
         {"speaker":"蔡文姬","text":"（扑来）将军……文姬还以为见不到你了。"},
         {"speaker":"你","text":"说过护你，便不会食言。"}]),
     target_location="jiangling_west.西门", next_hint="将拓片交黄承彦辨真伪", next_quest="main_all_49b",
     grant_item={"item_id": "quest_yuxi_tapan", "item_name": "玉玺拓片", "count": 1}),

dict(id="main_all_49b", name="主·拓片辨真", type="main",
     npc_id="npc_jiangling_center_黄承彦", npc_name="黄承彦",
     npc_location="jiangling_center.广场", npc_location_name="广场(江陵中区)",
     level_required=49, prerequisite="main_all_49a",
     description="将玉玺拓片交黄承彦辨真伪，了结江陵之局。",
     objective={"type": "deliver_item", "item_id": "quest_yuxi_tapan", "item_name": "玉玺拓片",
                "count": 1, "target_npc": "npc_jiangling_center_黄承彦"},
     rewards=rewards_for(49),
     dialogs=dlg(
        [{"speaker":"黄承彦","text":"将军竟真从水寨夺了回来。让老朽细看这拓片……"},
         {"speaker":"你","text":"先生可辨得真假？"}],
        [{"speaker":"黄承彦","text":"（指尖轻颤）是真的。玉玺纹路与此暗合，烬焰盟图谋不虚。"},
         {"speaker":"你","text":"拓片既真，下一站便是汉中——陈宫那封密信说，他们要在汉中囤兵。"}]),
     next_hint="前往「太守府」说动守将黄祖联手", next_quest="main_all_50a"),

dict(id="main_all_50a", name="主·守将迟疑", type="main",
     npc_id="npc_jiangling_center_黄祖", npc_name="黄祖",
     npc_location="jiangling_center.太守府", npc_location_name="太守府(江陵中区)",
     level_required=50, prerequisite="main_all_49b",
     description="前往「太守府」说动守将黄祖，联手截断烬焰盟水路。",
     objective={"type": "talk_npc", "npc_id": "npc_jiangling_center_黄祖", "count": 1},
     rewards=rewards_for(50),
     dialogs=dlg(
        [{"speaker":"黄祖","text":"将军要老夫出兵？江陵乃要害，某不敢擅动。"},
         {"speaker":"你","text":"黄将军守土有责，岂能坐视贼盟借水路转运？"},
         {"speaker":"黄祖","text":"……（沉吟）也罢。水路要冲，某派人封了。将军前路，老夫送一程。"}],
        [{"speaker":"你","text":"得黄将军一诺，江陵便稳了半边天。"},
         {"speaker":"黄祖","text":"去吧。汉中那头，田豫将军不是好相与的，将军自重。"}]),
     next_hint="前往「西城楼」肃清残敌", next_quest="main_all_50b"),

dict(id="main_all_50b", name="主·江陵余烬", type="main",
     npc_id="npc_jiangling_center_黄祖", npc_name="黄祖",
     npc_location="jiangling_center.太守府", npc_location_name="太守府(江陵中区)",
     level_required=50, prerequisite="main_all_50a",
     description="烬焰盟残部据西城楼死守，前往「江陵西」击杀1名【步骘】。",
     objective={"type": "kill_monster", "monster_name": "步骘", "count": 1},
     rewards=rewards_for(50),
     dialogs=dlg(
        [{"speaker":"黄祖","text":"西城楼还剩一伙顽敌，将军顺手清了，江陵便干净了。"},
         {"speaker":"你","text":"残兵败将，何足道哉。"}],
        [{"speaker":"你","text":"步骘已死，江陵再无烬焰盟的旗号。"},
         {"speaker":"黄祖","text":"将军此去汉中，一路保重。老夫在江陵，等将军洛阳的捷报。"}]),
     target_location="jiangling_west.西门", next_hint="陆路向汉中进发", next_quest="main_all_51a"),

dict(id="main_all_51a", name="主·入汉道中", type="main",
     npc_id="npc_jiangling_center_蔡文姬", npc_name="蔡文姬",
     npc_location="jiangling_center.客栈", npc_location_name="客栈(江陵中区)",
     level_required=51, prerequisite="main_all_50b",
     description="临行前与蔡文姬在客栈话别，她以琴声壮行。",
     objective={"type": "talk_npc", "npc_id": "npc_jiangling_center_蔡文姬", "count": 1},
     rewards=rewards_for(51),
     dialogs=dlg(
        [{"speaker":"蔡文姬","text":"将军又要走了。此去汉中山高路险，文姬以一曲《出塞》壮行。"},
         {"speaker":"你","text":"（听琴）好曲。待洛阳事了，某陪你再听一曲。"},
         {"speaker":"蔡文姬","text":"那时，天下该太平了吧？"}],
        [{"speaker":"你","text":"会的。我向你保证。"},
         {"speaker":"蔡文姬","text":"（含笑）那文姬，便在江陵等将军凯旋。"}]),
     next_hint="前往「北城楼」破截杀入汉中", next_quest="main_all_51b"),

dict(id="main_all_51b", name="主·褒斜截杀", type="main",
     npc_id="npc_jiangling_center_蔡文姬", npc_name="蔡文姬",
     npc_location="jiangling_center.客栈", npc_location_name="客栈(江陵中区)",
     level_required=51, prerequisite="main_all_51a",
     description="入汉中道中遭伏，前往「江陵北」击杀1名【潘章】开路。",
     objective={"type": "kill_monster", "monster_name": "潘章", "count": 1},
     rewards=rewards_for(51),
     dialogs=dlg(
        [{"speaker":"蔡文姬","text":"将军！北面山道杀声又起！"},
         {"speaker":"你","text":"贼盟是不肯放我入汉中。破了他！"}],
        [{"speaker":"你","text":"潘章授首，褒斜道通了。文姬，江陵珍重。"},
         {"speaker":"蔡文姬","text":"（挥手）将军——洛阳见！"}]),
     target_location="jiangling_north.北门", next_hint="入汉中，见田豫", next_quest="main_all_52a"),
]

# ===== 汉中 52-54 (6 个) =====
QUESTS += [
dict(id="main_all_52a", name="主·镇北迎宾", type="main",
     npc_id="npc_hanzhong_center_田豫", npc_name="田豫",
     npc_location="hanzhong_center.广场", npc_location_name="广场(汉中中区)",
     level_required=52, prerequisite="main_all_51b",
     description="抵汉中，前往「广场」与镇北将军田豫会合，明言来意。",
     objective={"type": "talk_npc", "npc_id": "npc_hanzhong_center_田豫", "count": 1},
     rewards=rewards_for(52),
     dialogs=dlg(
        [{"speaker":"田豫","text":"远来辛苦。下邳、江陵的事，田某已听说了。将军是为粮道而来？"},
         {"speaker":"你","text":"正是。陈宫那封密信说，烬焰盟要在汉中囤粮聚兵，断褒斜道。"},
         {"speaker":"田豫","text":"不差。某已盯了他们半载。将军既来，便一同端了这窝点。"}],
        [{"speaker":"你","text":"得田将军鼎力，大事成矣。"},
         {"speaker":"田豫","text":"先探营。军师胡昭藏有布防机要，将军不妨一访。"}]),
     next_hint="前往「酒馆」访隐士胡昭", next_quest="main_all_52b"),

dict(id="main_all_52b", name="主·隐士机要", type="main",
     npc_id="npc_hanzhong_center_胡昭", npc_name="胡昭",
     npc_location="hanzhong_center.酒馆", npc_location_name="酒馆(汉中中区)",
     level_required=52, prerequisite="main_all_52a",
     description="前往「酒馆」访隐士胡昭，得其汉中布防之教。",
     objective={"type": "talk_npc", "npc_id": "npc_hanzhong_center_胡昭", "count": 1},
     rewards=rewards_for(52),
     dialogs=dlg(
        [{"speaker":"胡昭","text":"将军来寻老朽？褒斜道的兵法，老朽倒略知一二。"},
         {"speaker":"你","text":"先生可知烬焰盟粮屯何处？"},
         {"speaker":"胡昭","text":"粮屯在北麓大营，守备森严。然其枢纽，在『灵火道人』执掌的火库。"}],
        [{"speaker":"你","text":"火库为枢，便先夺火库。"},
         {"speaker":"胡昭","text":"将军好眼力。断火库，则粮道自乱。老朽便助将军这第一步。"}]),
     next_hint="前往北麓大营，破火库", next_quest="main_all_53a"),

dict(id="main_all_53a", name="主·夜夺火库", type="main",
     npc_id="npc_hanzhong_center_田豫", npc_name="田豫",
     npc_location="hanzhong_center.广场", npc_location_name="广场(汉中中区)",
     level_required=53, prerequisite="main_all_52b",
     description="随田豫夜袭北麓大营火库，守库道人顽抗，前往「汉中西」击杀1名【灵火道人】。",
     objective={"type": "kill_monster", "monster_name": "灵火道人", "count": 1},
     rewards=rewards_for(53),
     dialogs=dlg(
        [{"speaker":"田豫","text":"时机到了。火库守将灵火道人，便交给将军。"},
         {"speaker":"你","text":"田将军断后，火库我拿下。"}],
        [{"speaker":"你","text":"灵火道人已诛，火库既破，粮道自乱。"},
         {"speaker":"田豫","text":"好！趁乱夺其布防图，洛阳便在将军掌中。"}]),
     target_location="hanzhong_west.西门", next_hint="肃清粮屯，夺布防图", next_quest="main_all_53b"),

dict(id="main_all_53b", name="主·断粮夺图", type="main",
     npc_id="npc_hanzhong_center_田豫", npc_name="田豫",
     npc_location="hanzhong_center.广场", npc_location_name="广场(汉中中区)",
     level_required=53, prerequisite="main_all_53a",
     description="乘势扫平粮屯，前往「汉中南」击杀1名【廖化】夺回洛阳布防图。",
     objective={"type": "kill_monster", "monster_name": "廖化", "count": 1},
     rewards=rewards_for(53),
     dialogs=dlg(
        [{"speaker":"田豫","text":"粮屯已乱，将军速去夺图！"},
         {"speaker":"你","text":"廖化守图，破之即得。"}],
        [{"speaker":"你","text":"廖化伏诛，洛阳布防图到手。烛龙的真名，图上竟有标注！"},
         {"speaker":"田豫","text":"哦？何种人物，竟敢以宗亲之身，行此逆谋？"}]),
     target_location="hanzhong_south.南门", next_hint="将布防图交胡昭参详", next_quest="main_all_54a",
     grant_item={"item_id": "quest_luoyang_bu", "item_name": "洛阳布防图", "count": 1}),

dict(id="main_all_54a", name="主·图穷名现", type="main",
     npc_id="npc_hanzhong_center_胡昭", npc_name="胡昭",
     npc_location="hanzhong_center.酒馆", npc_location_name="酒馆(汉中中区)",
     level_required=54, prerequisite="main_all_53b",
     description="将洛阳布防图交胡昭参详，识破烛龙真身。",
     objective={"type": "deliver_item", "item_id": "quest_luoyang_bu", "item_name": "洛阳布防图",
                "count": 1, "target_npc": "npc_hanzhong_center_胡昭"},
     rewards=rewards_for(54),
     dialogs=dlg(
        [{"speaker":"胡昭","text":"将军夺得的图，老朽替你参详。"},
         {"speaker":"你","text":"图上烛龙真名，先生可曾看出？"}],
        [{"speaker":"胡昭","text":"（失声）竟是蛰伏的宗亲刘琰！此人素装恭顺，暗里养士聚兵，狼子野心。"},
         {"speaker":"你","text":"刘琰……原来是他。洛阳一战，某必会会会这位『烛龙』。"}]),
     next_hint="与田豫定下入洛之策", next_quest="main_all_54b"),

dict(id="main_all_54b", name="主·汉中山岳", type="main",
     npc_id="npc_hanzhong_center_田豫", npc_name="田豫",
     npc_location="hanzhong_center.广场", npc_location_name="广场(汉中中区)",
     level_required=54, prerequisite="main_all_54a",
     description="与田豫定下入洛之策，辞别汉中。",
     objective={"type": "talk_npc", "npc_id": "npc_hanzhong_center_田豫", "count": 1},
     rewards=rewards_for(54),
     dialogs=dlg(
        [{"speaker":"田豫","text":"粮道已断，汉中无虞。将军入洛，某率本部为声援。"},
         {"speaker":"你","text":"有田将军这一句，某便放心了。"}],
        [{"speaker":"你","text":"汉中篇毕。下一站，洛阳。"},
         {"speaker":"田豫","text":"将军去吧。那『烛龙』刘琰，便交给将军了。"}]),
     next_hint="兵发洛阳", next_quest="main_all_55a"),
]

# ===== 洛阳 55-60 (12 个) =====
QUESTS += [
dict(id="main_all_55a", name="主·残汉开门", type="main",
     npc_id="npc_luoyang_center_荀爽", npc_name="荀爽",
     npc_location="luoyang_center.广场", npc_location_name="广场(洛阳中区)",
     level_required=55, prerequisite="main_all_54b",
     description="兵临洛阳，前往「广场」说动残汉太傅荀爽开城纳义师。",
     objective={"type": "talk_npc", "npc_id": "npc_luoyang_center_荀爽", "count": 1},
     rewards=rewards_for(55),
     dialogs=dlg(
        [{"speaker":"荀爽","text":"来者何人？洛阳乃天子旧都，岂容乱兵擅入。"},
         {"speaker":"你","text":"老太傅，某非乱兵，是来除烬焰盟、护这旧都的。"},
         {"speaker":"荀爽","text":"烬焰盟……老夫守这宫墙半生，等的便是这句话。开城门！"}],
        [{"speaker":"你","text":"得太傅相助，洛阳便有了根基。"},
         {"speaker":"荀爽","text":"将军且入皇宫查探。那刘琰，便在宫深处。"}]),
     next_hint="潜入皇宫，先破前卫", next_quest="main_all_55b"),

dict(id="main_all_55b", name="主·宫门初战", type="main",
     npc_id="npc_luoyang_center_荀爽", npc_name="荀爽",
     npc_location="luoyang_center.广场", npc_location_name="广场(洛阳中区)",
     level_required=55, prerequisite="main_all_55a",
     description="皇宫前卫拦路，前往「洛阳北」击杀1名【张济】。",
     objective={"type": "kill_monster", "monster_name": "张济", "count": 1},
     rewards=rewards_for(55),
     dialogs=dlg(
        [{"speaker":"荀爽","text":"宫门有刘琰的亲卫，将军且破之。"},
         {"speaker":"你","text":"张济守门，某去会会。"}],
        [{"speaker":"你","text":"张济已倒，宫门洞开。刘琰，你躲不掉了。"},
         {"speaker":"荀爽","text":"将军勇烈，老夫在城头为将军壮威。"}]),
     target_location="luoyang_north.北门", next_hint="深入皇宫，破徐荣", next_quest="main_all_56a"),

dict(id="main_all_56a", name="主·深宫对峙", type="main",
     npc_id="npc_luoyang_center_烛龙", npc_name="烛龙",
     npc_location="luoyang_center.皇宫", npc_location_name="皇宫(洛阳中区)",
     level_required=56, prerequisite="main_all_55b",
     description="深入皇宫，与烛龙（刘琰）首次对峙，其臂助影现身。",
     objective={"type": "talk_npc", "npc_id": "npc_luoyang_center_烛龙", "count": 1},
     rewards=rewards_for(56),
     dialogs=dlg(
        [{"speaker":"烛龙","text":"呵，远来的贵客。你一路破我三城，倒是让本王刮目。"},
         {"speaker":"你","text":"刘琰，你以宗亲之身行此逆谋，可知天下不容？"},
         {"speaker":"烛龙","text":"宗亲？正是宗亲，才配执玉玺、再立新廷。将军何不投我，共享富贵？"},
         {"speaker":"你","text":"玉玺是护民的，不是你称孤道寡的凭据。"}],
        [{"speaker":"烛龙","text":"冥顽。影，替本王送客。"},
         {"speaker":"影","text":"（拔刃）将军，这一路辛苦，便到此为止吧。"}]),
     next_hint="宫中再战，破影与徐荣", next_quest="main_all_56b"),

dict(id="main_all_56b", name="主·影刃当前", type="main",
     npc_id="npc_luoyang_center_影", npc_name="影",
     npc_location="luoyang_center.酒馆", npc_location_name="酒馆(洛阳中区)",
     level_required=56, prerequisite="main_all_56a",
     description="影领死士阻于宫道，前往「洛阳西」击杀1名【徐荣】。",
     objective={"type": "kill_monster", "monster_name": "徐荣", "count": 1},
     rewards=rewards_for(56),
     dialogs=dlg(
        [{"speaker":"影","text":"将军既不肯投，便留在这宫道里。"},
         {"speaker":"你","text":"你的主子都不敢亲自出手，你倒卖力。"}],
        [{"speaker":"你","text":"徐荣已亡。影，你主子的棋，快下完了。"},
         {"speaker":"影","text":"（咬牙）将军莫狂，总坛尚有一战。"}]),
     target_location="luoyang_west.西门", next_hint="重入皇宫，破虎豹精锐", next_quest="main_all_57a"),

dict(id="main_all_57a", name="主·虎豹精锐", type="main",
     npc_id="npc_luoyang_center_残汉老臣", npc_name="残汉老臣",
     npc_location="luoyang_center.军营", npc_location_name="军营(洛阳中区)",
     level_required=57, prerequisite="main_all_56b",
     description="义军整队，残汉老臣助你破刘琰虎豹精锐，前往「洛阳南」击杀1名【虎豹队长】。",
     objective={"type": "kill_monster", "monster_name": "虎豹队长", "count": 1},
     rewards=rewards_for(57),
     dialogs=dlg(
        [{"speaker":"残汉老臣","text":"将军，老臣虽老，尚能提剑。虎豹营便交老臣与将军。"},
         {"speaker":"你","text":"有老丈同行，某底气更足。"}],
        [{"speaker":"你","text":"虎豹队长授首，刘琰的牙爪去了一截。"},
         {"speaker":"残汉老臣","text":"将军，皇宫深处便是那贼巢，老臣为你压阵。"}]),
     target_location="luoyang_south.南门", next_hint="会合蔡文姬，定总攻", next_quest="main_all_57b"),

dict(id="main_all_57b", name="主·文姬入洛", type="main",
     npc_id="npc_luoyang_center_蔡文姬", npc_name="蔡文姬",
     npc_location="luoyang_center.客栈", npc_location_name="客栈(洛阳中区)",
     level_required=57, prerequisite="main_all_57a",
     description="蔡文姬自江陵赶至洛阳相助，于客栈为你抚琴定策。",
     objective={"type": "talk_npc", "npc_id": "npc_luoyang_center_蔡文姬", "count": 1},
     rewards=rewards_for(57),
     dialogs=dlg(
        [{"speaker":"蔡文姬","text":"将军果真打到了洛阳。文姬不放心，便也来了。"},
         {"speaker":"你","text":"你来得好。最后一战，有你在侧，某心定。"},
         {"speaker":"蔡文姬","text":"玉玺拓片与残图皆已印证，刘琰的总坛便在皇宫正殿之后。"}],
        [{"speaker":"你","text":"既知巢穴，便一鼓作气。文姬且候捷音。"},
         {"speaker":"蔡文姬","text":"（浅笑）将军凯旋时，文姬再为你抚一曲《大风》。"}]),
     next_hint="总攻皇宫，破连弩精兵", next_quest="main_all_58a"),

dict(id="main_all_58a", name="主·总坛外垣", type="main",
     npc_id="npc_luoyang_center_荀爽", npc_name="荀爽",
     npc_location="luoyang_center.广场", npc_location_name="广场(洛阳中区)",
     level_required=58, prerequisite="main_all_57b",
     description="总攻开始，外垣连弩精兵顽抗，前往「洛阳中」击杀1名【连弩队长】。",
     objective={"type": "kill_monster", "monster_name": "连弩队长", "count": 1},
     rewards=rewards_for(58),
     dialogs=dlg(
        [{"speaker":"荀爽","text":"将军，总坛外垣的连弩营，是入殿的最后屏障。"},
         {"speaker":"你","text":"某去拆了这屏障。"}],
        [{"speaker":"你","text":"连弩队长已亡，殿后便无遮挡。刘琰，出来罢。"}]),
     target_location="luoyang_center.广场", next_hint="焚盟书，断其根基", next_quest="main_all_58b"),

dict(id="main_all_58b", name="主·焚书断根", type="main",
     npc_id="npc_luoyang_center_荀爽", npc_name="荀爽",
     npc_location="luoyang_center.广场", npc_location_name="广场(洛阳中区)",
     level_required=58, prerequisite="main_all_58a",
     description="冲入总坛密室，焚毁烬焰盟书，断其根基。",
     objective={"type": "talk_npc", "npc_id": "npc_luoyang_center_荀爽", "count": 1},
     rewards=rewards_for(58),
     dialogs=dlg(
        [{"speaker":"荀爽","text":"密室之中，便是那卷盟书。将军，烧了它！"},
         {"speaker":"你","text":"（举火）烬焰盟的算计，随这把火，散罢。"}],
        [{"speaker":"荀爽","text":"（火光映面）好！根既断，枝叶自枯。将军大功。"},
         {"speaker":"你","text":"根断了，人还未除。刘琰，某亲自去会。"}]),
     next_hint="正殿决战，破神秘将军", next_quest="main_all_59a"),

dict(id="main_all_59a", name="主·殿前死战", type="main",
     npc_id="npc_luoyang_center_影", npc_name="影",
     npc_location="luoyang_center.酒馆", npc_location_name="酒馆(洛阳中区)",
     level_required=59, prerequisite="main_all_58b",
     description="影率最后死士据殿前死战，前往「洛阳北」击杀1名【神秘将军】。",
     objective={"type": "kill_monster", "monster_name": "神秘将军", "count": 1},
     rewards=rewards_for(59),
     dialogs=dlg(
        [{"speaker":"影","text":"将军逼到殿前，影便陪你赌上最后一战。"},
         {"speaker":"你","text":"你主子躲在殿里，你却在前头挡刀。值么？"},
         {"speaker":"影","text":"（惨笑）值不值，影自有分晓。"}],
        [{"speaker":"你","text":"神秘将军已倒。影，你这一局，也输了。"},
         {"speaker":"影","text":"（喘息）将军……洛阳，便托付你了。"}]),
     target_location="luoyang_north.北门", next_hint="四象守阵，破青龙白虎", next_quest="main_all_59b"),

dict(id="main_all_59b", name="主·四象守阵", type="main",
     npc_id="npc_luoyang_center_残汉老臣", npc_name="残汉老臣",
     npc_location="luoyang_center.军营", npc_location_name="军营(洛阳中区)",
     level_required=59, prerequisite="main_all_59a",
     description="刘琰以四象守阵护殿，前往「洛阳北」击杀1名【青龙】（或白虎）。",
     objective={"type": "kill_monster", "monster_name": "青龙", "count": 1},
     rewards=rewards_for(59),
     dialogs=dlg(
        [{"speaker":"残汉老臣","text":"殿前四象阵——青龙、白虎、朱雀、玄武，乃刘琰最后依仗。"},
         {"speaker":"你","text":"四象又如何？某先破青龙。"}],
        [{"speaker":"你","text":"青龙已碎，阵眼已破其半。刘琰，你的阵撑不住了。"},
         {"speaker":"残汉老臣","text":"将军神勇！老臣替将军压住白虎那一象。"}]),
     target_location="luoyang_north.北门", next_hint="终战烛龙刘琰", next_quest="main_all_60a"),

dict(id="main_all_60a", name="主·玉玺归处", type="main",
     npc_id="npc_luoyang_center_荀爽", npc_name="荀爽",
     npc_location="luoyang_center.广场", npc_location_name="广场(洛阳中区)",
     level_required=60, prerequisite="main_all_59b",
     description="终战之前，荀爽将寻得的传国玉玺交你定夺归属。",
     objective={"type": "talk_npc", "npc_id": "npc_luoyang_center_荀爽", "count": 1},
     rewards=rewards_for(60),
     dialogs=dlg(
        [{"speaker":"荀爽","text":"将军，老臣于密室夹墙寻得此物——传国玉玺。天下气运所系，将军定夺。"},
         {"speaker":"你","text":"（双手捧玺）玉玺重千钧。荀公，某以为，玺当归万民，不归一家。"}],
        [{"speaker":"荀爽","text":"（垂泪）将军此言，胜过千军。玉玺何在，便在天下人心。"},
         {"speaker":"你","text":"既如此，某便用它，了结这最后一战。"}]),
     next_hint="入正殿，决战烛龙刘琰", next_quest="main_all_60b",
     grant_item={"item_id": "quest_chuanguo_yuxi", "item_name": "传国玉玺", "count": 1}),

dict(id="main_all_60b", name="主·烽火终章", type="main",
     npc_id="npc_luoyang_center_烛龙", npc_name="烛龙",
     npc_location="luoyang_center.皇宫", npc_location_name="皇宫(洛阳中区)",
     level_required=60, prerequisite="main_all_60a",
     description="正殿决战烛龙刘琰，前往「洛阳北」击杀1名【玄武】，了断烽火。",
     objective={"type": "kill_monster", "monster_name": "玄武", "count": 1},
     rewards=rewards_for(60),
     dialogs=dlg(
        [{"speaker":"烛龙","text":"将军执玺而来，是要与本王争这天下？"},
         {"speaker":"你","text":"某不为天下，为这四海不再烽火。刘琰，你的梦，醒了。"},
         {"speaker":"烛龙","text":"（狂笑）既有玉玺，何不索性……（阵动）玄武，护我！"}],
        [{"speaker":"你","text":"玄武已灭，四象尽碎。刘琰，你输了。"},
         {"speaker":"烛龙","text":"（颓然）玉玺……竟落在一个不想要天下的人手里……"},
         {"speaker":"你","text":"烽火暂熄，天下稍安。至于玉玺归处——（望向荀爽与文姬）且留给后来人吧。"}]),
     target_location="luoyang_north.北门",
     next_hint="（主线终章·汉室余晖）"),
]


def build_quests():
    quests = load("data/quests.json")
    added = []
    for q in QUESTS:
        if q["id"] not in quests:
            quests[q["id"]] = q
            added.append(q["id"])
    if added:
        dump("data/quests.json", quests)
    return added


def build_items():
    items = load("data/items.json")
    added = []
    for iid, idef in QUEST_ITEMS.items():
        if iid not in items:
            items[iid] = idef
            added.append(iid)
    if added:
        dump("data/items.json", items)
    return added


def main():
    a_items = build_items()
    a_npcs = build_npcs()
    a_mobs, a_placed = build_monsters()
    a_quests = build_quests()
    print(f"quest items added : {a_items}")
    print(f"npcs added        : {a_npcs}")
    print(f"mob templates     : {a_mobs}")
    print(f"mob placements    : {a_placed}")
    print(f"quests added      : {len(a_quests)} (total now in quests.json: "
          f"{len(load('data/quests.json'))})")
    # 链完整性自检
    q = load("data/quests.json")
    bad = [qq['id'] for qq in QUESTS if qq.get('prerequisite') and qq['prerequisite'] not in q]
    nxt = [qq['id'] for qq in QUESTS if qq.get('next_quest') and qq['next_quest'] not in q]
    print(f"missing prerequisite targets: {bad}")
    print(f"missing next_quest targets  : {nxt}")


if __name__ == "__main__":
    main()
