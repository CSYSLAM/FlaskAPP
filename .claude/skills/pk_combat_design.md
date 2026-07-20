# PK与战斗损失系统设计规则

野外PK奖惩 + 被怪死亡惩罚 + 复活 + 免战 + 仇敌的完整规则。伤害公式见 `combat_formulas.md`。

## 一、野外PK发起条件（`BattleService.start_pk`）

全部满足才可发起（入口 `blueprints/battle.py` 的 `/start_pk/<username>`）：

| 条件 | 不满足提示 |
|------|-----------|
| 双方均未在战斗/PK中 | 你已在战斗中 / 对方已在战斗中 |
| 发起方 ≥25 级 | 25级后开启PK |
| 双方同一场景 | 需要同一场景才能PK |
| 当前场景 `can_pk=true`（非安全区） | 安全区禁止PK |
| 对方未死亡（非 need_revive 且 health>0） | 对方已死亡，无法PK |
| 对方非免战状态 | 对方处于免战状态 |
| 60秒内对同一目标发起 <3 次（`PK_ATTEMPT_LIMIT=3`） | PK发起过于频繁 |

- **安全区**：地图名前带 `*` 表示安全区；场景级 `can_pk` 标志（`DataService.get_locations().get(current_location).get('can_pk')`）。
- **频率限制**：存于发起方 `activity_data['pk_attempts'] = {目标username: [时间戳]}`，滚动60秒窗口。

## 二、PK战败结算（`_handle_pk_defeat`）

### 同国
- **无任何损失**（仅生命值变化）：不转荣誉/银两、不掉装备、不记仇敌、不记成就。

### 异国（荣誉/银两零和转移）

**荣誉档位**（等级差 = 胜方级 − 败方级）：

| 等级差 | 荣誉 |
|--------|------|
| 败方更高（diff<0） | 15 |
| 低10级以内（0≤diff≤10） | 10 |
| 低11-20级（10<diff<20） | 5 |
| 低20级以上（diff≥20） | 0 |

**荣誉减免**（取高不叠加，向下取整）：
- VIP1~5 少扣 10%/20%/30%/40%/50%（`vip_config.json` 的 `pk_drop_reduction`）。
- 死亡替身符少扣 30%——**仅当替身符减免高于VIP时才消耗1张**（`0.30 > vip减免`）。
- 实际转移 = `floor(档位 × (1−减免))`，受败方荣誉余额上限。
- **零和**：胜方所得 = 败方所扣。

**银两档位**（×败方等级，受败方银两余额上限，零和）：

| 等级差 | 系数 |
|--------|------|
| 败方更高 | ×10 |
| 低10级以内 | ×6 |
| 低11-20级 | ×3 |
| 低20级以上 | ×0 |

**其它规则**：
- 不掉装备（胜方不得装备，败方不失装备）。
- 败方记胜方为仇敌（`add_enemy`，仅异国）。
- 败方出战副将掉忠诚（`LieutenantService.handle_death(owner_died=True)`）。
- **PK战败不扣经验**。
- 成就 `pk_win`/`pk_loss` 仅异国记录（同国不记）。
- 败方进入复活态（`need_revive=True`、`killed_by`）。

> **战场**（`battlefield_service`）是独立系统：按段位 `TIER_HONOR` 零和转荣誉 + 战斗积分，不适用本规则。

## 三、被怪击杀惩罚（`_apply_pve_death_penalty`）

在6个PvE死亡点（含逃跑失败）触发：
- 经验 **−10%**（`int(经验×0.1)`，保底0，不掉级）。
- 银两 **−(怪物等级×1)**（保底0）。
- 荣誉不变。
- **VIP（`non_pk_loss_exempt`）全免**。
- 死亡消息追加"（损失X经验、Y银两）"。

## 四、复活（`revive_action`，`blueprints/battle.py`）

| 方式 | 效果 |
|------|------|
| 满血复活（续命灯 `potion_revive`） | 满血满蓝，无损失 |
| 虚弱复活 | 10%血/蓝，**不扣经验**（经验已在死亡时扣） |
| 回城疗伤（300银两） | 虚弱复活 + 传送本城客栈（先 `{city}_center.客栈`，回退 `{city}_center.广场`；银两不足提示） |

- 经验只在**死亡时**扣（PvE），复活不再扣。
- 已删除"濒死(H≤1)获胜扣10%经验"的旧惨胜惩罚（`battle_result`）。

## 五、免战符（`peace_token`）

- 商城「金珠-辅助」购买（110金珠）。
- 背包使用（`usage_effect.special = "pk_truce"`，`item_service.use_item` 分支）。
- 设置 `activity_data['pk_immunity_until'] = now + 1800`（**30分钟**，重复使用延长）。
- 免战期内其他玩家无法对其发起PK（`start_pk` 校验）。
- 注：旧版300分钟/`peace_status` 规格已废弃（原未生效）。

## 六、仇敌与追杀

- 异国被击杀 → `defender.add_enemy(胜方)`。
- 「社交-仇人」列表：`SocialService.get_enemy_list`。
- **追杀令**（`hunt_order`）：消耗1个，传送至仇人所在位置（`SocialService.hunt_enemy`）。
- 删除仇人：`SocialService.remove_enemy`。

## 七、关键文件

| 文件 | 内容 |
|------|------|
| `services/battle_service.py` | `start_pk`、`_handle_pk_defeat`、`_pk_honor_tier`/`_pk_silver_tier`/`_pk_honor_reduction`、`_apply_pve_death_penalty`、6个PvE死亡点 |
| `blueprints/battle.py` | `revive_action`（满血/虚弱/回城疗伤）、`start_pk` 路由 |
| `services/item_service.py` | 免战符 `pk_truce` 分支 |
| `services/vip_service.py` | `get_pk_drop_reduction`、`is_non_pk_loss_exempt`、权益文案 |
| `services/social_service.py` | `get_enemy_list`、`hunt_enemy`、`remove_enemy` |
| `data/vip_config.json` | `pk_drop_reduction`（0.1~0.5） |
| `data/items.json` | `peace_token`、`hunt_order`、`death_substitute` |
| `data/guides_content.json` | 游戏内指南「PK玩法」 |
| `templates/revive.html` | 复活选项（含回城疗伤） |

## 八、变更记录

| 日期 | 变更 |
|------|------|
| 2026-07-20 | PK系统重做：荣誉/银两按等级差分档（零和、向下取整）；荣誉减免VIP10-50%+替身符30%取高不叠加；PK不掉装备、不扣经验、副将掉忠诚、同国无损失；免战符30分钟；PK频率60秒3次；被怪击杀扣经验10%+银两(怪级×1)（死亡时扣、VIP免）；虚弱复活不再扣经验；新增回城疗伤(300银两)；删除濒死获胜经验扣除 |
