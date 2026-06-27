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

## 装备分类商品（材料包）

| 商品 | 价格(金珠/元宝) | 使用后获得 | 物品ID |
|------|----------------|-----------|--------|
| 碎皮包 | 400 | 碎皮x20 | sui_pi_pack |
| 黄杨木包 | 400 | 黄杨木x20 | huangyang_mu_pack |
| 麻布包 | 400 | 麻布x20 | ma_bu_pack |
| 黄铜矿包 | 400 | 黄铜矿x20 | huangtong_kuang_pack |
| 硬皮包 | 600 | 硬皮x20 | ying_pi_pack |
| 沉香木包 | 600 | 沉香木x20 | chenxiang_mu_pack |
| 棉布包 | 600 | 棉布x20 | mian_bu_pack |
| 黑铁矿包 | 600 | 黑铁矿x20 | heitie_kuang_pack |
| 厚皮包 | 800 | 厚皮x20 | hou_pi_pack |
| 紫檀木包 | 800 | 紫檀木x20 | zitan_mu_pack |
| 呢绒包 | 800 | 呢绒x20 | nirong_pack |
| 精金矿包 | 800 | 精金矿x20 | jingjin_kuang_pack |

### 材料包使用效果配置

```json
{
  "usage_effect": {
    "grant_item": ["craft_材料id", 20]
  }
}
```

材料包type为consumable，背包分类时名字含"包"的显示在"其他"分类。

## 装备分类商品（新婚戒指包）

| 商品 | 价格(金珠/元宝) | 使用后获得 | 系统公告 |
|------|----------------|-----------|----------|
| 新婚钻戒包 | 2000 | 20级神器饰品【新婚钻戒】(1-5星随机) | XXX打开新婚钻戒包，获得了XX，恭喜恭喜！ |
| 新婚草戒包 | 100 | 20级饰品【新婚草戒】(普通-史诗随机) | XXX打开新婚草戒包，获得了XX，恭喜恭喜！ |

### 新婚戒指包使用效果配置

```json
{
  "usage_effect": {
    "generate_equipment": {
      "template_id": "wedding_diamond_ring",  // 或 wedding_grass_ring
      "rarity": "神器",  // 钻戒包固定神器
      "rarity_range": ["普通", "精良", "卓越", "史诗"],  // 草戒包品质范围
      "stars_range": [1, 5]  // 星级随机范围
    }
  }
}
```

### 相关装备模板

| 模板ID | 名称 | 等级 | 类型 | 品质 |
|--------|------|------|------|------|
| wedding_diamond_ring | 新婚钻戒 | 20 | accessory | 神器 |
| wedding_grass_ring | 新婚草戒 | 20 | accessory | 普通-史诗 |

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

材料包（名字含"包"的consumable）显示在"其他"分类，材料（type=material）显示在"材料"分类。

代码位置：`blueprints/player.py` inventory函数：
```python
if it_type in ('consumable', 'potion'):
    if '包' in item_name:
        cat = '其他'
    else:
        cat = '药品'
```

## 特惠包usage_effect配置格式

### 固定数量发放（random_items）
```json
{
  "usage_effect": {
    "random_items": [
      {"item_id": "目标物品id", "guaranteed_count": 固定数量, "max_count": 固定数量, "chance": 1.0}
    ]
  }
}
```

### 直接授予物品（grant_item）
```json
{
  "usage_effect": {
    "grant_item": ["物品id", 数量]
  }
}
```

### 生成装备（generate_equipment）
```json
{
  "usage_effect": {
    "generate_equipment": {
      "template_id": "装备模板id",
      "rarity": "神器",  // 固定品质
      "rarity_range": ["普通", "精良", "卓越", "史诗"],  // 品质范围
      "stars_range": [1, 5]  // 星级范围
    }
  }
}
```

代码位置：`services/item_service.py` use_item方法处理这些效果。

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
| 2026-06-27 | 材料包：grant_item获得对应材料x20，背包分类显示在"其他" | csy |
| 2026-06-27 | 新婚钻戒包：generate_equipment生成20级神器饰品(1-5星)，使用时系统公告 | csy |
| 2026-06-27 | 新婚草戒包：generate_equipment生成20级饰品(普通-史诗)，使用时系统公告 | csy |
| 2026-06-27 | item_service添加grant_item和generate_equipment效果处理 | csy |
