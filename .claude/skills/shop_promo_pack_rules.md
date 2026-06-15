# 商城促销特惠包规则

## 概述

金珠商城和元宝商城的"促销"标签页出售特惠包，使用后可获得批量物品。特惠包本身是consumable类型，通过`usage_effect.random_items`配置使用后获得的物品和数量。

## 促销商品列表

| 特惠包 | 价格(金珠/元宝) | 使用后获得 |
|--------|----------------|-----------|
| 军团战特惠包 | 2700 | 15个战场令旗(低级) + 10个战场令旗(中级) + 5个战场令旗(高级) + 10个战场续命灯 |
| 大血石特惠包 | 1200 | 15个大血石 |
| 大魔石特惠包 | 1200 | 15个大魔石 |
| 小喇叭特惠包 | 1200 | 15个小喇叭 |

## 已下架商品

| 特惠包 | 原价格 | 状态 |
|--------|--------|------|
| 风雷珠特惠包 | 500 | 已下架，is_usable=false |

## 物品详细说明

### 战场令旗
战场令旗分为三个等级，均为**other**类型（背包分类：其他）：

| 物品ID | 名称 | 商城价格 | 用途 |
|--------|------|---------|------|
| battle_flag_1 | 战场令旗(低级) | 100金珠/元宝 | 进入低级战场的门票 |
| battle_flag_2 | 战场令旗(中级) | 200金珠/元宝 | 进入中级战场的门票 |
| battle_flag_3 | 战场令旗(高级) | 500金珠/元宝 | 进入高级战场的门票 |

- **获取**: 军团战特惠包(15低级+10中级+5高级)、商城其他标签页
- **不可使用**: is_usable=false

### 战场续命灯 (battle_revive_lamp)
- **类型**: other（背包分类：其他）
- **用途**: 在战场被击败后15秒内使用可原地复活，否则传送出战场
- **重要**: 普通续命灯(potion_revive)在战场无效，只有战场续命灯才能在战场复活
- **获取**: 军团战特惠包(10个)、商城其他标签页(200金珠/元宝)

### 大血石 (big_hp_stone)
- **类型**: consumable
- **用途**: 使用后增加20000点生命储备
- **获取**: 大血石特惠包(15个)、商城辅助标签页(100金珠/元宝)

### 大魔石 (big_mp_stone)
- **类型**: consumable
- **用途**: 使用后增加20000点魔法储备
- **获取**: 大魔石特惠包(15个)、商城辅助标签页(100金珠/元宝)

### 小喇叭 (small_horn)
- **类型**: consumable
- **用途**: 使用后发送全服公告（公共聊天）
- **获取**: 小喇叭特惠包(15个)、商城其他标签页(100金珠/元宝)

## 商城分类规则

- **促销(promo)**: 特惠包，批量优惠
- **其他(other)**: 功能性物品（小喇叭、战场令旗、战场续命灯、续命灯、改名卡等）
- **辅助(assist)**: 增益类物品（血石、魔石、诸侯令、银两包等）
- **装备(equip)**: 材料包、婚戒包
- **副将(lieutenant)**: 副将相关物品

## 背包分类规则

战场令旗、战场续命灯属于**其他**类(type=other)，在背包中显示在"其他"分类下。

## 特惠包usage_effect配置格式

```json
{
  "usage_effect": {
    "random_items": [
      {"item_id": "目标物品id", "guaranteed_count": 固定数量, "max_count": 固定数量, "chance": 1.0}
    ]
  }
}
```

使用`guaranteed_count`和`max_count`相同且`chance=1.0`表示固定数量发放，无随机性。

## 规则变更记录

| 日期 | 变更内容 | 变更人 |
|------|---------|-------|
| 2026-06-14 | 初始规则：删除风雷珠特惠包，军团战特惠包→15低级+10中级+5高级令旗+10战场续命灯，大血/魔石特惠包→15大血/魔石，小喇叭特惠包→15小喇叭 | csy |
| 2026-06-14 | 战场令旗(低/中/高级)、战场续命灯type改为other，在商城其他标签页上架 | csy |
| 2026-06-14 | 大血石/大魔石usage_effect改为stat_changes.blood_reserve/mana_reserve+20000 | csy |
| 2026-06-14 | 商城物品名称添加title悬停提示，显示物品描述和内含物品 | csy |
| 2026-06-14 | 删除物品：风云令、长安令、白玉令、角色转国令、都统令、角色变性卡 | csy |
| 2026-06-14 | 双倍经验卡：type=other，usage_effect.temp_effects(exp_rate rate=1.0 1h)，battle_service检查TempEffect | csy |
| 2026-06-14 | 神游果：type=other, is_usable=false（副本门票消耗品） | csy |
| 2026-06-14 | 秘药礼包：random_items四个属性秘药(pill_attack/defense/max_health/max_mana各25%) | csy |
| 2026-06-14 | 孔明灯：type=other, is_usable=false（传送系统消耗），map_service用kongming_lantern | csy |
| 2026-06-14 | 追杀令：type=other, is_usable=false（社交仇人追杀消耗），social_service用hunt_order | csy |
| 2026-06-14 | 副将双倍经验卡：type=other，usage_effect.temp_effects(lt_exp_rate rate=1.0 1h)，battle_service副将获50%经验×加成 | csy |
| 2026-06-14 | 角色改名卡：type=other，usage_effect.special=rename，使用后跳转改名页面 | csy |
| 2026-06-14 | 强化小幸运符：type=other，usage_effect.special=enhance_lucky，设置player.enhance_bonus_rate=0.05不可叠加 | csy |
