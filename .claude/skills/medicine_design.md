# 医药铺（大夫 NPC）系统设计规则

治疗型 NPC 商店：购买回血/回蓝药品与百草园种子。蓝图注册前缀 `/medicine`。

## 一、概述

医药铺是由「大夫」类 NPC 触发的商店（NPC 实体在 `data/monsters.json` 中定义，店名取 NPC 的 `name`）。售卖两类物品：
- **药品（medicines）**：19 种回血/回蓝药水（potion_heal_* / potion_mana_*）。
- **种子（seeds）**：14 种百草园种子（与 villa 花园种植对应）。

商品目录硬编码于 `data/medicine_shop.json`，购买扣银两、加物品入背包（非绑定），并推进「购买类」任务进度（如主·购买金疮药）。

## 二、关键文件

| 文件 | 内容 |
|------|------|
| `blueprints/medicine_shop.py` | 路由：shop（/<npc_id>）、buy（/buy/<npc_id>/<item_id>） |
| `data/medicine_shop.json` | 商品目录：medicines[]、seeds[] |
| `services/data_service.py` | `get_monster`(取大夫名)、`get_item`(校验物品定义)、`add_item_to_inventory` |
| `services/quest_service.py` | `update_buy_item_progress`（购买任务推进） |

## 三、路由（前缀 /medicine）

> 蓝图 `medicine_bp` 本身无 `url_prefix`（medicine_shop.py:8），由 `app.py:253` 注册为 `/medicine`。故有效前缀为 `/medicine`。

| 路由 | 方法 | 说明 |
|------|------|------|
| `/medicine/<npc_id>` | GET | 商店页（tab=medicine 或 seed，分页每页 12） |
| `/medicine/buy/<npc_id>/<item_id>` | POST | 购买（quantity，默认 1） |

## 四、核心逻辑 / 设计规则

### 4.1 商店页 `shop`（medicine_shop.py:23）

- 取 `DataService.get_monster(npc_id).get('name', '大夫')` 作店名（若 NPC 非怪物表项，名字回退「大夫」）。
- `tab` 参数切换药品/种子；`page` 分页，每页 `per_page = 12`（medicine_shop.py:37）。
- 仅展示，无状态修改。

### 4.2 购买 `buy`（medicine_shop.py:65）

顺序：
1. 在 `catalog['medicines']` 与 `catalog['seeds']` 中按 `item_id` 查商品（medicine_shop.py:77-85）；查不到 → 闪「物品不存在」。
2. `DataService.get_item(item_id)` 校验物品定义存在（medicine_shop.py:94）。
3. `total_price = price * quantity`；银两不足报错。
4. `player.gold -= total_price`；`DataService.add_item_to_inventory(player.id, item_id, quantity, is_bound=False)`（medicine_shop.py:113-114，**购入物品非绑定**）。
5. `QuestService.update_buy_item_progress(player, item_id)` 推进购买类任务（medicine_shop.py:118，如「主·购买金疮药」）。
6. 提交、闪成功提示、重定向回原 tab/page。

## 五、数据文件 / 配置

`data/medicine_shop.json` 结构：
```json
{
  "medicines": [ {"item_id": "...", "name": "...", "price": N, "description": "..."} ],
  "seeds":     [ {"item_id": "...", "name": "...", "price": N} ]
}
```

**药品（19 种，价格 25–2250）**：`potion_heal`(25)、`potion_mana`(25)、`potion_heal_100`(100)、`potion_mana_100`(100)、`potion_heal_200`(200)、`potion_mana_200`(200)、`potion_heal_300`(300)、`potion_heal_400`(400)、`potion_heal_500`(500)、`potion_heal_625`(625)、`potion_heal_800`(800)、`potion_mana_800`(800)、`potion_heal_950`(950)、`potion_heal_1150`(1150)、`potion_mana_1150`(1150)、`potion_heal_2000`(2000)、`potion_mana_2000`(2000)、`potion_heal_2250`(2250)、`potion_mana_2250`(2250)。

**种子（14 种，价格 240–5960）**：`seed_jinchuangyao`(240)、`seed_jumosan`(240)、`seed_yangshengwan`(480)、`seed_xingshenshui`(480)、`seed_dabuwan`(960)、`seed_yeshanshen`(1920)、`seed_xuelianlu`(1920)、`seed_zhenzhubei`(2440)、`seed_huanyangdan`(2980)、`seed_guanyinshui`(2980)、`seed_tiancandan`(4960)、`seed_huashenshui`(4960)、`seed_shenxuedan`(5960)、`seed_qinglinglu`(5960)。

> 上述 `seed_*` 即 `villa_service.py` 的 `SEEDS` 中所列百草园种子；在此购买后回山庄种植（见 villa_design.md）。

## 六、注意事项 / 坑

- 商品 `price` 来自 json；物品实际效果（恢复量）由 `data/items.json` 中对应 `potion_*` 定义决定，两处须保持一致。
- 购入物品一律 `is_bound=False`，可被交易/丢弃。
- 店名依赖 `get_monster(npc_id)`；NPC 必须存在于怪物表，否则显示为「大夫」且无商品（目录仍按 item_id 加载）。
- 无「卖出/回收」逻辑，纯购买型商店。

## 七、相关文档

- `.claude/skills/villa_design.md` → 在此购买的 `seed_*` 用于百草园种植
- `CLAUDE.md` →「Blueprint URL Prefixes（medicine）」
