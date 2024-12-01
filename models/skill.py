class Skill:
    def __init__(self, skill_id, name, class_required, description, base_damage_rate, 
                 base_mana_cost, damage_rate_per_level, mana_cost_per_level, 
                 effect_description=None, hits=1):
        self.skill_id = skill_id
        self.name = name
        self.class_required = class_required  # 职业要求,None表示通用技能
        self.description = description
        self.base_damage_rate = base_damage_rate  # 基础伤害倍率
        self.base_mana_cost = base_mana_cost  # 基础魔法消耗
        self.damage_rate_per_level = damage_rate_per_level  # 每级增加伤害倍率
        self.mana_cost_per_level = mana_cost_per_level  # 每级增加魔法消耗
        self.effect_description = effect_description  # 额外效果描述
        self.hits = hits  # 攻击次数
        self.level = 1
        self.max_level = 10

    def level_up_cost(self):
        """返回升级所需经验和银两"""
        exp_cost = 100 * self.level * (1 + self.level * 0.1)
        money_cost = 1000 * self.level * (1 + self.level * 0.1)
        return int(exp_cost), int(money_cost)

    def get_current_damage_rate(self):
        """获取当前等级的伤害倍率"""
        return self.base_damage_rate + (self.level - 1) * self.damage_rate_per_level

    def get_current_mana_cost(self):
        """获取当前等级的魔法消耗"""
        return self.base_mana_cost + (self.level - 1) * self.mana_cost_per_level

    @staticmethod
    def load_skills():
        """加载所有技能数据"""
        return {
            # 术士技能
            "thunder": Skill("thunder", "天雷术", "术士", 
                           "召唤天雷攻击敌人", 2.0, 30, 0.2, 3,
                           "有几率使目标麻痹一回合"),
            
            "earth_fire": Skill("earth_fire", "地火术", "术士",
                              "召唤地火灼烧敌人", 1.8, 25, 0.15, 2,
                              "造成持续灼烧伤害"),
                              
            "seal_magic": Skill("seal_magic", "封魔术", "术士",
                              "封印目标的魔法", 1.5, 35, 0.1, 4,
                              "降低目标魔法恢复速度"),
                              
            # 刺客技能
            "pierce": Skill("pierce", "破甲刺", "刺客",
                          "无视部分护甲的刺击", 2.2, 35, 0.25, 3,
                          "无视30%护甲"),
                          
            "double_hit": Skill("double_hit", "二连击", "刺客",
                              "快速的两次攻击", 1.6, 15, 0.1, 2,
                              "进行两次攻击判定", hits=2),
                              
            "poison_strike": Skill("poison_strike", "毒刃击", "刺客",
                                 "带有剧毒的攻击", 1.7, 30, 0.15, 3,
                                 "造成持续中毒伤害"),
                                 
            # 战士技能
            "storm_kill": Skill("storm_kill", "暴风杀", "战士",
                              "狂风般的连续攻击", 1.7, 20, 0.15, 2,
                              "有几率造成眩晕"),
                              
            "ten_slash": Skill("ten_slash", "十刃斩", "战士",
                             "十面埋伏般的斩击", 1.9, 25, 0.2, 2,
                             "范围伤害效果"),
                             
            "blood_drink": Skill("blood_drink", "血饮斩", "战士",
                               "吸取敌人生命的斩击", 1.8, 30, 0.15, 3,
                               "吸取造成伤害的20%转化为生命值"),
                               
            # 通用技能
            "chaos": Skill("chaos", "混乱术", None,
                         "使目标陷入混乱", 1.5, 40, 0.1, 4,
                         "使目标混乱,一定几率攻击自己")
        }