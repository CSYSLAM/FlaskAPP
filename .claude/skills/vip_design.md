# VIP 系统设计规则

`/vip/*` 下的 VIP 等级、权益、诸侯令、升级/转换/领取/传送的完整规则。

## 一、概述

- **URL 前缀**：`/vip`（`blueprints/vip.py:7`）。
- **服务类**：`VipService`（`services/vip_service.py:8`），配置加载自 `data/vip_config.json`（`_load_config` `:11`）。
- **状态存储**：`player.vip_level`（等级）、`player.vip_exp`（经验）、`player.vip_expire_time`（到期 UTC 时间）、`player.vip_daily_claimed`（每日领取标记 JSON `{exp, gift}` 按日期）。
- **权益来源**：一切权益由 `vip_config.json` 的 `vip_levels[1..5]` 字段驱动；跨 `has_*`/`get_*_rate` 方法读取对应等级配置。

## 二、关键文件

| 文件 | 内容 |
|------|------|
| `blueprints/vip.py` | VIP 路由：主页/介绍/用诸侯令/升级/转换/领经验/领礼包/传送 |
| `services/vip_service.py` | `VipService`：等级/权益/诸侯令/升级/每日领取/传送判定 |
| `data/vip_config.json` | `vip_levels`（1–5 级权益表）+ `zhuhouling_items`（诸侯令 1/7/30 天，绑/非绑） |
| `models/player.py` | `vip_level`/`vip_exp`/`vip_expire_time`/`vip_daily_claimed` 字段 |
| `services/title_service.py` | 升级时发放专属称号（`VipService.upgrade_vip` `:114`） |
| `services/achievement_service.py` | `vip1`~`vip5` 成就（`upgrade_vip` `:121`） |
| `templates/vip.html` 等 | `vip_intro.html` / `vip_use.html` / `vip_teleport.html` |

> 跨文档联动：**`pk_drop_reduction`** 与 **`non_pk_loss_exempt`** 由本系统提供，被 `pk_combat_design.md` 的 PK 战败/被怪死亡结算调用（见第七、注意事项）。

## 三、路由（`/vip` 前缀）

| 路由 | 方法 | 说明 |
|------|------|------|
| `/vip/` | GET | VIP 主页：等级/剩余时长/可升级/每日可领/权益列表/免费传送 |
| `/vip/intro` | GET | 全等级权益与每日礼包介绍 |
| `/vip/use/<item_id>` | GET | 诸侯令使用确认页（校验 `type=='vip'`） |
| `/vip/use/<item_id>` | POST | 实际消耗诸侯令加时长 |
| `/vip/upgrade` | GET | 消耗经验手动升级（满 5 级不可） |
| `/vip/convert_exp/<int:count>` | GET | 诸侯时长换经验（1 天 = 10 exp） |
| `/vip/claim_exp` | GET | 领取每日 5 VIP 经验（满则换银两） |
| `/vip/claim_daily` | GET | 领取每日礼包（vip_level>0） |
| `/vip/teleport` | GET | 免费传送选点页（按 area 分组，排除副本） |
| `/vip/teleport/<path:location_id>` | GET | 执行免费传送 |

## 四、核心逻辑/设计规则

### 1. 等级与有效期（`get_active_vip_level` `:25`）

- 若 `vip_expire_time` 为空或 `utcnow() >= 到期` → 返回 **0**（VIP 失效，权益清零）。
- 否则返回 `max(player.vip_level, 1)`——**只要有未过期时长，至少算 1 级**。
- `get_vip_remaining_time`（`:36`）= 到期 − 当前 UTC，负数归零。

### 2. 诸侯令（`use_zhuhouling` `:43`）

- 校验物品 `type=='vip'` 且背包有量；读 `usage_effect.vip_days`。
- 延长到期：未过期则 `+= timedelta(days=vip_days)`，否则从 `now` 起算。
- **只加时长，不加速度/经验**（经验来自 `claim_daily_exp` 或 `convert_days_to_exp`）。
- 绑定判定：`use_zhuhouling`（POST `vip.py:97`）优先用绑定库存（`is_bound=True`），否则非绑；`vip_config.json` 的 `zhuhouling_items` 区分 `bound` 与 `vip_days`/`vip_exp`（注：配置含 `vip_exp` 字段，但 `use_zhuhouling` 当前只消费时长，未自动加经验）。

### 3. 升级（`upgrade_vip` `:98` / `can_upgrade_vip` `:85`）

- `can_upgrade_vip`：当前 `vip_level >= 5` → 满级；否则需 `vip_exp >= 下一档 required_exp`。
- `upgrade_vip`：扣 `required_exp`（`player.vip_exp -= cost_exp`，溢出保留），`vip_level += 1`。
- 若新等级有 `title` → 发称号（`TitleService.grant_title`，前缀/后缀判定）；触发 `vip_level` 成就。
- `required_exp` 阶梯：L2=100、L3=200、L4=300、L5=500（`vip_config.json`）。

### 4. 时长换经验（`convert_days_to_exp` `:72`）

- 校验剩余天数 ≥ `count`；扣时长 `vip_expire_time -= count 天`，加 `vip_exp += count*10`。
- 用于把冗余诸侯时长转为可升级经验。

### 5. 每日领取

- **每日经验** `claim_daily_exp`（`:128`）：VIP 生效才可；当日 `claimed['exp']` 已记则拒绝。若经验已满（≥ 下一档 `required_exp` 或已达 5 级）→ 改发 **500 银两**；否则 `vip_exp += 5`。
- **每日礼包** `claim_daily_gift`（`:162`）：按当前活跃等级 `daily_gift` 数组发放物品（如 L1：`续命灯x1`+`小喇叭x1`；L5 另加 `宝匣钥匙x1`+`强化宝玉x1`）。当日 `claimed['gift']` 已记则拒绝。

### 6. 免费传送（`has_free_teleport` `:208` / `do_teleport` `vip.py:178`）

- 仅活跃 VIP 且 `free_teleport==true`（L1–L5 全部 true）。
- 副本内禁用（`is_copy_map` 时拒绝并提示先离开副本）。
- 目标须存在于 `DataService.get_locations()`，直接设 `player.current_location` → 跳 `game.scene`。

### 7. 权益字段表（`vip_config.json` 每级）

| 字段 | 含义 | 取用方法 | L1 | L2 | L3 | L4 | L5 |
|------|------|---------|----|----|----|----|----|
| `stat_bonus_rate` | 人物属性提升 | `get_stat_bonus_rate` `:192` | 1% | 2% | 3% | 4% | 5% |
| `exp_bonus_rate` | 打怪经验增加 | `get_exp_bonus_rate` `:200` | 5% | 10% | 15% | 20% | 25% |
| `storage_bonus` | 仓库容量 | `get_storage_bonus` `:248` | 100 | 200 | 300 | 400 | 500 |
| `pk_drop_reduction` | PK战败荣誉少扣 | `get_pk_drop_reduction` `:232` | 10% | 20% | 30% | 40% | 50% |
| `non_pk_loss_exempt` | 非PK战败损失免除 | `is_non_pk_loss_exempt` `:240` | true | true | true | true | true |
| `free_teleport` | 特权免费传送 | `has_free_teleport` `:208` | true | true | true | true | true |
| `free_rest` | 客栈免费休息 | `has_free_rest` `:216` | true | true | true | true | true |
| `free_stage_teleport` | 驿站免费传送 | `has_free_stage_teleport` `:224` | true | true | true | true | true |
| `title` | 专属称号 | `upgrade_vip` | null | 后缀VIP用户 | null | null | null |
| `color_nick` | 山庄彩昵 | `has_color_nick` `:256` | false | false | false | true | true |
| `broadcast` | 上线全服播报 | `has_broadcast` `:264` | false | false | false | false | true |
| `achievement` | 三国特权成就 | `upgrade_vip` | vip1 | vip2 | vip3 | vip4 | vip5 |
| `daily_gift` | 每日礼包 | `claim_daily_gift` | 见上 | 见上 | +宝匣钥匙 | 同L3 | +强化宝玉 |

- `get_vip_privilege_list`（`:272`）把上述字段拼成中文权益文案（供主页/介绍页展示）。

## 五、数据文件/配置

- **`data/vip_config.json`**：
  - `vip_levels`：键 `"1"`~`"5"`，每级含上表全部字段 + `name`/`required_exp`。
  - `zhuhouling_items`：`zhuhouling_1d`/`_7d`/`_30d` 及对应 `_bound` 版，字段 `name`/`vip_days`/`vip_exp`/`bound`/`description`。
- **玩家字段**（`models/player.py`）：`vip_level`、`vip_exp`、`vip_expire_time`(UTC datetime)、`vip_daily_claimed`(JSON)。
- 配置由 `VipService._load_config`（`:11`）缓存类级，改文件需重启。

## 六、注意事项/坑

- **时长即等级前提**：`get_active_vip_level` 只看到期时间，不看 `vip_level`。即便 `vip_level=5`，过期也返回 0（权益全失）。诸侯令只延长时间、不刷新等级。
- **经验与等级分离**：`vip_exp` 不会自动升级，须玩家手动 `/vip/upgrade` 消耗经验升档。经验满时每日经验领取自动转 500 银两。
- **诸侯令不加速度/经验**：`use_zhuhouling` 仅加 `vip_expire_time`；虽 `zhuhouling_items` 含 `vip_exp` 字段，但当前代码未消费它（升级经验靠每日领取/时长转换）。
- **PK 减免与免损**（重点联动）：`pk_drop_reduction` 与 `non_pk_loss_exempt` 仅对**活跃** VIP（未过期）生效。详见 `pk_combat_design.md`：PK 战败按等级差分档后，VIP 减免荣誉（取高不叠加，替身符 30% 仅在高于 VIP 时才消耗）；被怪死亡时 `non_pk_loss_exempt==true` 全免经验/银两损失。
- **副本内禁用传送**：`/vip/teleport` 与 `do_teleport` 在 `is_copy_map` 场景均拒绝，须先离开副本。
- **每日领取按 UTC 日期**：`vip_daily_claimed` 用 `datetime.utcnow().strftime('%Y-%m-%d')` 标记，与服务器本地时区可能存在跨日偏差。
- **免费传送对所有非副本地点开放**：不消耗任何货币，但每个 `location_id` 须真实存在。

## 七、相关文档

- `pk_combat_design.md` — **核心联动**：`pk_drop_reduction`（荣誉少扣）、`non_pk_loss_exempt`（被怪死亡免损）由 `VipService.get_pk_drop_reduction`/`is_non_pk_loss_exempt` 提供，PK 结算时读取
- `activity_design.md` — 活动奖池含诸侯令（`duke_token_1d/7d/30d`），是 VIP 时长的主要来源
- `lieutenant_design.md` — 无直接关系
- `CLAUDE.md` — Blueprint URL Prefixes（`vip` 前缀）、Item Usage Rules（诸侯令等 `is_usable:false` 物品的使用限制）
