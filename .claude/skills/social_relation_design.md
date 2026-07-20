# 社交关系（Social Relation）系统设计规则

社交关系的完整规则：好友/黑名单、红颜/知己（结交/断交酒）、仇敌/追杀、私聊/送礼、结婚（求婚/同意/离婚/配偶传送）。

## 一、概述

社交系统前缀 `/social`（blueprint `social`，注册名 `'social'`）。包含：公开/国家/私聊/系统聊天、好友、黑名单、仇敌、红颜/知己、结婚。
好友/黑名单/仇敌列表存于 `PlayerModel` 的 JSON 字段（`friends`/`blacklist`/`enemies`）；红颜/知己/夫妻是 `Relationship` ORM 表；聊天存 `ChatMessage` 表。

## 二、关键文件

| 文件 | 内容 |
|------|------|
| `blueprints/social.py` | 全部社交路由 |
| `services/social_service.py` | `SocialService`：好友/黑名单/仇敌、送花/缘分、红颜知己、结婚/离婚/传送、聊天、送礼；常量 `MAX_FRIENDS=30`、`MAX_BLACKLIST=30`、`MAX_ENEMIES=30`、`MAX_RELATIONS=5`、`FATE_REQUIRED=100`、`MARRIAGE_FATE_REQUIRED=1000` |
| `models/relationship.py` | `Relationship` 模型（`rel_type`：`hongyan`/`zhiji`/`spouse`/`pending`，`fate_value`，`initiator_id`） |
| `models/player.py` | `friends`/`blacklist`/`enemies`（JSON 列）、`relation_requests`（JSON 列）、`notifications`、`charm`、`gender`、`current_location`、`party_id` 等 |
| `services/player_service.py` | `get_social_bonus_rate`/`get_spouse_bonus_rate` 在属性乘区叠加（line 134-135 等） |
| `data/items.json` | `bond_wine`（结交酒）、`break_wine`（断交酒）、`duanchang_cao`（断肠草）、`flower_rose`（玫瑰）、`hunt_order`（追杀令）、`horn_small`（小喇叭） |

## 三、路由（前缀 `/social`）

| 路由 | 方法 | 说明 |
|------|------|------|
| `/social/` , `/social/social` | GET | 社交主页 |
| `/social/search_player` | GET | 按 UID 搜玩家 |
| `/social/friends` | GET | 好友列表 |
| `/social/add_friend/<username>` | GET | 加好友 |
| `/social/remove_friend/<username>` | GET | 删好友 |
| `/social/blacklist` | GET | 黑名单 |
| `/social/add_blacklist/<username>` | GET | 加黑名单 |
| `/social/remove_blacklist/<username>` | GET | 移出黑名单 |
| `/social/enemies` | GET | 仇人列表 |
| `/social/remove_enemy/<username>` | GET | 删仇人 |
| `/social/hunt_enemy/<username>` | GET | 用追杀令传送至仇人处 |
| `/social/hongyan` | GET | 红颜列表 + 待处理请求 |
| `/social/zhiji` | GET | 知己列表 + 待处理请求 |
| `/social/send_flower/<username>` | GET, POST | 送玫瑰（增魅力+缘分） |
| `/social/request_relation/<username>/<rel_type>` | GET | 发起红颜/知己结交（消耗结交酒） |
| `/social/accept_relation/<username>` | GET | 接受结交（再消耗结交酒） |
| `/social/reject_relation/<username>` | GET | 拒绝结交 |
| `/social/break_relation/<username>` | GET | 断交（消耗断交酒） |
| `/social/propose_marriage/<username>` | GET | 求婚（消耗 2 结交酒） |
| `/social/accept_marriage/<username>` | GET | 接受求婚 |
| `/social/reject_marriage/<username>` | GET | 拒绝求婚 |
| `/social/divorce` | GET | 离婚（消耗断肠草） |
| `/social/spouse_teleport` | GET | 传送至配偶（副本内禁止） |
| `/social/chat?tab=` | GET | 聊天（tab=public/country/system/private） |
| `/social/send_message` | POST | 发公开/国家消息 |
| `/social/private/<username>` | GET | 与某人私聊 |
| `/social/send_private/<username>` | POST | 发私聊 |
| `/social/gift` | POST | 送礼（item/equipment/gold） |
| `/social/toggle_view/<view_type>` | GET | 切换聊天视图 |
| `/social/gift_page/<username>` | GET | 送礼页（可赠物品/装备列表） |

## 四、核心逻辑/设计规则

### 1. 好友 / 黑名单（`SocialService`，social_service.py:210 起）
- 好友上限 `MAX_FRIENDS=30`；加好友写 `player.friends`（JSON 列表，存 username），并给目标发通知。
- 黑名单上限 `MAX_BLACKLIST=30`；加入 `player.blacklist`。
- 私聊/送礼前校验 `is_blocked`：若目标把发送者拉黑，则无法发消息（social.py:325、346）。

### 2. 仇敌 / 追杀（social_service.py:305 起）
- 仇敌列表来自 `player.enemies`（JSON，username 列表），上限 `MAX_ENEMIES=30`。
- `hunt_enemy`（social_service.py:318）：消耗 1 个 `hunt_order`（追杀令），把 `player.current_location` 设为仇人所在位置；仇人须已在 `enemies` 列表。

### 3. 缘分与送花（`send_flower`，social_service.py:355）
- 消耗 `flower_rose`，数量=增魅力+增缘分（`target.charm += q`、`_increase_fate`）。
- `fate_value` 存于 `Relationship`（无关系则建 `pending` 记录）。
- 999/99 朵触发系统播报。

### 4. 红颜 / 知己（结交酒流程）
- 类型规则：`hongyan`（红颜）需**异性**（`player.gender != target.gender` 才允许）；`zhiji`（知己）需**同性**（social_service.py:422-427）。
- 缘分门槛 `FATE_REQUIRED=100`（`get_fate_value` 不足则拒绝）。
- 数量上限 `MAX_RELATIONS=5`（双方各自计算）。
- **结交酒 `bond_wine` 消耗两次**：发起 `request_relationship`（social_service.py:447）消耗 1 个；对方 `accept_relationship`（social_service.py:492）再消耗 1 个。即一段关系共 2 个结交酒。
- 发起写入目标 `relation_requests`（JSON）；接受时建/更新 `Relationship(rel_type=红颜或知己)`。

### 5. 断交（`break_relationship`，social_service.py:545）
- 消耗 1 个 `break_wine`（断交酒）。
- 将关系 `rel_type` 置回 `pending`，`fate_value` 扣 100（`max(0, fate-100)`）。

### 6. 结婚（结交酒 2 个 + 婚戒）
- `propose_marriage`（social_service.py:640）：双方**异性**；双方未婚；缘分 ≥ `MARRIAGE_FATE_REQUIRED=1000`；**双方须佩戴婚戒** `wedding_grass_ring`/`wedding_diamond_ring`（在 accessory 槽，`_check_wedding_ring`）；消耗 **2 个 `bond_wine`**；写入目标 `relation_requests`（type=`marriage`）。
- `accept_marriage`（social_service.py:701）：复核条件后新建 `Relationship(rel_type='spouse')`，原有红颜/知己记录保留；触发系统播报。
- `reject_marriage`（social_service.py:760）：移除请求。
- `divorce`（social_service.py:783）：消耗 1 个 `duanchang_cao`（断肠草）；删除 `spouse` 关系记录；并将双方之间 hongyan/zhiji 关系的 `fate_value` 扣 900；给原配偶发通知。
- `spouse_teleport`（social_service.py:816）：免费传送至配偶位置；双方在副本（`is_copy_map`）时禁止。

### 7. 社交属性加成（乘区比率）
- `get_social_bonus_rate`（social_service.py:20）：`(hongyan数 + zhiji数) × 0.01`，作用于攻击/防御/生命/魔法乘区（player_service.py:134、164、194、222）。
- `get_spouse_bonus_rate`（social_service.py:838）：已婚 +5%（0.05），乘区（player_service.py:135、165、195、223）。
- `get_online_relation_attack_bonus`（social_service.py:590）已废弃，恒返回 0。
- 登录时 `notify_relations_login` 给配偶/红颜/知己发上线通知。

### 8. 私聊 / 送礼 / 聊天
- 聊天存 `ChatMessage`，公开频道消耗 `horn_small`（小喇叭，social_service.py:35），国家频道免费。
- 私聊存 `message_type='private'`，双向查询。
- `send_gift`（social_service.py:86）：支持 item / equipment / gold；绑定物品（`is_bound`）不可赠送。

## 五、数据文件/配置

- 关系与列表均存 DB（`relationship` 表、`players` 的 JSON 列），**无独立 data/ 配置文件**。
- 物品消耗：`bond_wine`（结交酒）、`break_wine`（断交酒）、`duanchang_cao`（断肠草）、`flower_rose`（玫瑰）、`hunt_order`（追杀令）、`horn_small`（小喇叭）、`wedding_grass_ring`/`wedding_diamond_ring`（婚戒，于 equipment 数据）。
- 关键常量在 `social_service.py:9-14`，阈值 `FATE_REQUIRED=100`、`MARRIAGE_FATE_REQUIRED=1000`。

## 六、注意事项/坑

- **物品 ID 与 CLAUDE.md 不一致**：CLAUDE.md 的 “Item Usage Rules” 把结交酒写作 `friend_wine / bond_wine`，但**实际代码只用 `bond_wine`**（`request_relationship` 与 `accept_relationship`、`propose_marriage` 均查/扣 `bond_wine`）。`friend_wine` 在逻辑中无任何引用（仅某玩家背包数据里出现过），是死物品 ID。结交一段关系需要 2 个 `bond_wine`（发起+接受各 1），求婚需 2 个 `bond_wine`（仅发起方消耗）。
- `bond_wine`、`break_wine`、`duanchang_cao` 均为 `is_usable: false`，**不能从背包使用**，只能在社交流程中消耗（与 CLAUDE.md “Item Usage Rules” 一致）。
- 红颜=异性、知己=同性、结婚=异性，性别判定是硬约束。
- 结婚不合并红颜/知己记录：spouse 是独立 `Relationship` 行，离婚后仅删 `spouse` 行，红颜/知己关系保留但 `fate_value` 扣 900。

## 七、相关文档

- [pk_combat_design.md](pk_combat_design.md) — 仇敌来源（异国 PK 战败自动记仇敌）、`hunt_order` 追杀用法
- [legion_design.md](legion_design.md) / [party_design.md](party_design.md) — 其它团体加成（均为属性叠加，来源不同）
- [CLAUDE.md](../../CLAUDE.md) — “Item Usage Rules” 中 `friend_wine`/`break_wine`/`duanchang_cao` 等（注意其与代码实际的出入，见本节坑）
