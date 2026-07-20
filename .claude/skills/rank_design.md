# 排行榜系统设计规则

基于 `blueprints/rank.py`（唯一相关蓝图），以及各榜单的数据来源（`PlayerModel` 字段、`Achievement`、`ActivityService`）。

## 一、概述

提供多种玩家排行榜（财富、荣誉、等级、成就、魅力、勤奋），展示前30名与"我的排名"。所有计算在请求时实时进行，无缓存、无独立 service 层——逻辑全部内联在 `blueprints/rank.py`。

- **蓝图前缀**：`/rank`（`blueprints/rank.py:8`，`url_prefix='/rank'`）。
- **榜单类型**：由 `RANK_TYPES`（`blueprints/rank.py:10`）硬编码定义，共6种。

## 二、关键文件

| 文件 | 内容 |
|------|------|
| `blueprints/rank.py` | `RANK_TYPES:10`、`index:20`、`show:30`（全部排序/取数/排名逻辑内联） |
| `models/player.py` | `PlayerModel`（`gold`/`honor`/`level`/`experience`/`charm`/`kill_count` 等领域字段） |
| `models/player.py` | `class Achievement:1006`（成就榜按 `claimed=True` 计数） |
| `services/social_service.py` | `SocialService._is_online`（传给模板判断在线的可调用对象，`rank.py:112`） |
| `services/activity_service.py` | `ActivityService.get_today_value`（勤奋榜按当日 `kill_count` 取值，`rank.py:69,77`） |

## 三、路由（均在 `/rank` 蓝图下，需登录）

| 路由 | 函数 | 说明 |
|------|------|------|
| `/rank/` | `index` | 榜单总览，列出 `RANK_TYPES` 全部类型 |
| `/rank/<rank_type>` | `show` | 指定榜单详情；`rank_type` 不在 `RANK_TYPES` 时回退到 `index` |

## 四、核心逻辑 / 设计规则

### 4.1 榜单类型（`RANK_TYPES:10`）

| rank_type | 名称 | 排序依据 | 单位 | 数据源 |
|-----------|------|----------|------|--------|
| `wealth` | 财富榜 | `PlayerModel.gold.desc()` | 银 | `player.gold` |
| `honor` | 荣誉榜 | `PlayerModel.honor.desc()` | 荣 | `player.honor` |
| `level` | 等级榜 | `level.desc(), experience.desc()` | 级 | `player.level`/`experience` |
| `achievement` | 成就榜 | 已领成就数降序 | 个 | `Achievement`（`claimed=True` 计数） |
| `charm` | 魅力榜 | `PlayerModel.charm.desc()` | 魅 | `player.charm` |
| `diligence` | 勤奋榜 | 当日击杀数降序 | 次 | `ActivityService.get_today_value(p,'kill_count')` |

### 4.2 取数与排名（`show:30`）

- **财富/荣誉/魅力**：直接 `PlayerModel.query.order_by(...).limit(30)` 取前30，`my_val` 取当前玩家对应字段。
- **等级**：按 `(level desc, experience desc)` 取前30；`my_val = player.level`（`rank.py:50-54`）。
- **成就**：先 `PlayerModel.query.all()` 全量，再对每个玩家 `Achievement.query.filter_by(player_id=p.id, claimed=True).count()`，按数量降序取前30；`my_val` 为当前玩家已领成就数（`rank.py:55-63`）。
- **勤奋**：全量玩家，逐个取 `ActivityService.get_today_value(p, 'kill_count')`（当日击杀），降序取前30；`my_val` 同理（`rank.py:68-78`）。

排名定位（`my_rank`）：先遍历前30的 `entries` 找 `p.id == player.id`；未进入前30且 `my_val>0` 时，财富/荣誉/成就/魅力用"大于我的人数+1"补偿计算（等级用 `level` 或 `(level,experience)` 比较，`rank.py:84-103`）。`diligence` 未进前30时不补算 `my_rank`（保持 `None`）。

### 4.3 渲染数据

`render_template('rank_show.html', player, rank_type, rdef, entries, my_val, my_rank, is_online=SocialService._is_online)`（`rank.py:105`）。`entries` 为 `[(PlayerModel, value), ...]` 列表；`rdef` 含 `name/desc/unit`。

## 五、数据文件 / 配置

- 无独立数据文件；榜单维度与文案完全由 `blueprints/rank.py:10` 的 `RANK_TYPES` 字典定义，新增榜单需改此字典与 `show` 分支。
- 玩家数值来自 `PlayerModel` 列；勤奋榜来自 `activity_service` 的当日统计（非持久列）。

## 六、注意事项 / 坑

1. **无缓存、全量查询**：成就榜与勤奋榜用 `PlayerModel.query.all()` 再在 Python 端逐人计数/排序，玩家量大时性能随人数线性增长（O(N) 查询+内存排序）。等级/财富/荣誉/魅力则用数据库 `order_by().limit(30)`，仅取前30。
2. **勤奋榜 `my_rank` 可能为空**：只有进入前30或 `my_val>0` 时才计算排名，但勤奋榜的兜底分支缺失（对比成就/财富等有 `elif rank_type==...` 补偿），未进前30的勤奋榜玩家 `my_rank=None`。
3. **成就榜按"已领取"计数**：`claimed=True`，仅完成未领取的不计入排名（`rank.py:59,63`）。
4. **等级榜次级排序用 `experience`**：同等级按经验降序，排名补偿逻辑也据此比较（`rank.py:94-98`）。
5. **榜单类型硬编码**：`show` 中 `rank_type` 不在 `RANK_TYPES` 时静默回退到 `index`，不会404。
6. **在线状态**：模板通过 `is_online(player)` 判断在线，传的是 `SocialService._is_online` 方法本身（非调用结果）。

## 七、相关文档

- `CLAUDE.md` —— "Blueprint URL Prefixes"（排行 `/rank`）
- `.claude/skills/achievement_design.md` —— 成就榜的 `claimed` 计数来源
- `.claude/skills/title_design.md` —— 魅力/战力等相关玩家字段（魅力榜 `charm` 独立于称号加成）
