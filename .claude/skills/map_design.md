# 地图系统设计规则

地图导航：主图/世界/区域、传送（城市广场）、回城（驿站）、神行（区域传送点）。URL 前缀 `/map`。

## 一、概述

地图模块负责玩家在场景间的移动，提供四类功能：
- **传送（teleport）**：去各城市广场，VIP 免费、非 VIP 消耗孔明灯。
- **回城（town）**：回所在区域驿站，消耗回城符。
- **神行（shenxing）**：去当前区域的怪物/功能传送点，消耗神行符。
- **世界/区域地图浏览**：只读展示。

业务逻辑在 `services/map_service.py`，目的地映射（`CITY_SQUARES`/`AREA_STATIONS`）硬编码。副本内禁止任何传送（须先离开副本）。

## 二、关键文件

| 文件 | 内容 |
|------|------|
| `blueprints/map_route.py` | 路由：/、teleport、goto_scene、teleport_go、town、shenxing、shenxing_go、world、area |
| `services/map_service.py` | `MapService`：CITY_SQUARES、AREA_STATIONS、teleport、teleport_to_scene、town、shenxing、get_area_* |
| `services/copy_dungeon_service.py` | 副本判定 `get_country_dungeon_entries`、副本入口 |
| `data/locations.json`（经 data_service） | 场景定义（area_id、monsters、npcs、exits、is_copy_map） |

## 三、路由（前缀 /map）

| 路由 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 地图主页：传送/回城/神行/快捷入口 |
| `/teleport` | GET/POST | 传送城市广场（POST target / GET 渲染页） |
| `/teleport_go/<target>` | GET | 链接直传城市广场 |
| `/goto_scene/<path:scene_id>` | GET | 传送到指定场景（副本入口用） |
| `/town` | GET | 回城（去区域驿站） |
| `/shenxing` | GET | 神行页：当前区域传送点列表 |
| `/shenxing_go/<scene_id>` | GET | 执行神行 |
| `/world` | GET | 世界地图 |
| `/area` | GET | 区域地图（含各场景出口） |

## 四、核心逻辑 / 设计规则

### 4.1 目的地映射（`map_service.py`）

- `CITY_SQUARES`（map_service.py:8）：13 城市 → `{城市}.广场`（北平、晋阳、许昌、下邳、汉中、江陵、洛阳、建邺、柴桑、吴郡、成都、昆仑、神农架）。
- `AREA_STATIONS`（map_service.py:26）：11 区域 → 驿站/村（如 `beiping_center.驿站`、`kunlun.太平村`）。

### 4.2 传送 `teleport`（map_service.py:41）

- `target` 须命中 `CITY_SQUARES`，且 `DataService.get_locations()` 中存在（未开放城市拦截）。
- **VIP 免费**（`player.is_vip`）；非 VIP 须背包有 `kongming_lantern`（孔明灯）1 个，扣 1。
- 成功 → `player.current_location = 目标广场`。

### 4.3 回城 `town`（map_service.py:85）

- 取当前场景 `area_id`，查 `AREA_STATIONS`；无驿站则失败。
- **消耗回城符 `return_scroll` 1 个**（背包不足报错），置 `current_location = 驿站`。
- 对应 CLAUDE.md「Item Usage Rules」：`return_scroll` 仅「地图→回城→点击回城」消耗，`is_usable:false`。

### 4.4 神行 `shenxing`（map_service.py:114）

- `scene_id` 须为已注册场景。**消耗神行符 `speed_scroll` 1 个**，置 `current_location = scene_id`。
- 神行页由 `get_area_teleport_points_by_area`（map_service.py:158）给出当前区域所有含怪物/NPC 的场景。
- 对应 CLAUDE.md：`speed_scroll` 仅「地图→神行→执行」消耗，`is_usable:false`。

### 4.5 副本限制

所有传送/回城/神行入口均先判定当前场景 `is_copy_map`（map_route.py:33-36, 62, 78, 97, 133），副本内调用提示「请先放弃副本再离开」，不执行传送。

### 4.6 区域/世界浏览

- `get_area_scenes(area_id)`（map_service.py:181）：返回同区域全部场景及四向出口（north/south/east/west_exit）。
- `world`/`area` 仅渲染模板，无状态修改。

## 五、数据文件 / 配置

- 目的地为代码常量（`map_service.py` 顶部字典），非 data 文件。
- 场景数据来自 `data/locations.json`（经 `DataService.get_locations`），需含 `area_id`、`monsters`、`npcs`、`is_copy_map`、四向出口字段。

## 六、注意事项 / 坑

- 传送消耗的是**孔明灯 `kongming_lantern`**，该物品不在 CLAUDE.md 受限列表内但代码强制非 VIP 消耗；VIP 完全免单。
- `teleport` 只到城市**广场**；去具体功能点（铁匠/药店）靠 `shenxing` 或 `goto_scene`（副本入口）。
- `AREA_STATIONS` 仅 11 个区域，部分场景（如昆仑/神农架/倭寇岛）无对应驿站 → 这些区域 `town` 会失败。
- 副本内所有移动接口被锁，必须先放弃副本。

## 七、相关文档

- `CLAUDE.md` →「Blueprint URL Prefixes（map）」「Item Usage Rules（return_scroll / speed_scroll）」
- `.claude/skills/villa_design.md` → 活力卡补行动力（与地图无直接耦合，但同为 `is_usable:false` 类物品）
