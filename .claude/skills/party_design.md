# 队伍（Party）系统设计规则

队伍（小队）系统的完整规则：创建/退出/邀请/申请/通过/踢人、队伍加成、在线追踪。

## 一、概述

队伍是临时组队系统，前缀 `/party`（blueprint `party`，注册名 `'party'`）。
核心能力：
- 最多 **5 人**，由队长管理（邀请/踢人/审批申请）。
- 每有 **1 名在线成员**，全队成员攻击/防御/生命/魔法获得 **+1%**（比率，乘区）。
- ⚠️ 队伍状态**全部存于内存**（`PartyService._parties` / `_player_party` 字典），**服务器重启即清空**；`player.party_id` 仅作与内存态的索引。

## 二、关键文件

| 文件 | 内容 |
|------|------|
| `blueprints/party.py` | 全部队伍路由；`index` 计算在线人数与加成展示 |
| `services/party_service.py` | `PartyService` + `PartyState`（内存态）、`mark_online`/`mark_offline`/`is_player_online`、`MAX_PARTY_SIZE=5`、`BONUS_PER_MEMBER=0.01` |
| `models/player.py` | `PlayerModel.party_id`（Integer 列，line 65，仅存内存态 party_id） |
| `services/player_service.py` | `PartyService.get_party_bonus_rate` 在 `get_attack`/`get_defense`/`get_max_health`/`get_max_mana` 乘区叠加（line 145、175 等） |
| `app.py` | 登录时 `mark_online(current_user.id)`（app.py:167-170），把玩家加入在线集合 |

## 三、路由（前缀 `/party`）

| 路由 | 方法 | 说明 |
|------|------|------|
| `/party/` | GET | 队伍主页：成员、在线数、加成、待处理邀请 |
| `/party/create` | GET | 创建队伍（创建者自动为队长） |
| `/party/leave` | GET | 退出队伍（队长退出则解散） |
| `/party/invite/<int:target_id>` | GET | 队长邀请某玩家（60 秒有效） |
| `/party/apply/<int:party_id>` | GET | 向某队伍提交申请 |
| `/party/accept_invite/<int:party_id>` | GET | 接受队伍邀请 |
| `/party/accept_application/<int:applicant_id>` | GET | 队长通过申请 |
| `/party/reject_application/<int:applicant_id>` | GET | 队长拒绝申请 |
| `/party/kick/<int:target_id>` | GET | 队长踢出成员 |

> 注：无独立“队伍对话”或“队伍任务”路由；队伍仅用于加成与成员管理。

## 四、核心逻辑/设计规则

### 1. 数据模型（内存态，非 ORM）
- `PartyState`（party_service.py:29）：`members`（set of player_id）、`leader_id`、`invites`（{player_id: expire_time}）、`applications`（{player_id: apply_time}）、`created_at`。
- `PartyService._parties`（`party_id → PartyState`）、`_player_party`（`player_id → party_id`）、`_next_id` 自增。
- `player.party_id`（DB 列）只是把玩家映射到内存 `party_id`；队伍本身**不写入数据库**。

### 2. 创建/退出
- `create_party`（party_service.py:47）：已在该玩家映射中则报“已在队伍中”；否则分配新 id，写入内存态与 `player.party_id`。
- `leave_party`（party_service.py:85）：从内存态移除；若离开者是队长 `_dissolve_party` 解散整队（清理所有成员 `party_id`），否则仅剩单人时也解散。

### 3. 邀请（队长专属）
- `invite_player`（party_service.py:129）：仅队长；目标不能已在其它队伍/本队；满 5 人拒绝；邀请 `invites[target_id] = now + 60`（60 秒过期）。
- `accept_invite`（party_service.py:145）：过期/队伍满则失败；成功后加入 `members` 并同步 `player.party_id`。

### 4. 申请（任何人可发起，队长审批）
- `apply_to_party`（party_service.py:167）：写入 `applications`（不过期）。
- `accept_application`（party_service.py:177）/ `reject_application`（party_service.py:202）：仅队长；满员或目标已入队则失败。

### 5. 踢人
- `kick_member`（party_service.py:109）：仅队长；不能踢自己；从 `members` 移除并清理 `player.party_id`。

### 6. 队伍加成（`get_party_bonus_rate`，party_service.py:230）
- 在线成员数 × `BONUS_PER_MEMBER`（0.01，即每在线成员 +1%）。
- 在线判定 `is_player_online`（party_service.py:20）= 玩家 id 在内存 `_online_players` 集合（由 `mark_online` 登录时加入）。
- 该加成以**比率**形式进入属性公式乘区：`(flat...) * (1 + ... + party_rate)`（`player_service.py:146、176` 等），作用于攻击/防御/生命/魔法。

### 7. 在线追踪
- 登录：`app.py:167` 调用 `mark_online(current_user.id)`。
- `PartyService` 提供 `mark_offline`、`on_player_disconnect`、`remove_offline_members` 等，但当前代码中**未挂接自动离线/掉线清理**（logout/断开不会主动调用 `mark_offline`，依赖 `_online_players` 只增不清，离线成员可能持续计入在线加成——属已知隐患，详见坑）。

## 五、数据文件/配置

- 无 data/ 配置文件。核心参数 `MAX_PARTY_SIZE = 5`、`BONUS_PER_MEMBER = 0.01` 硬编码于 `services/party_service.py:5-6`。
- 涉及物品：无（队伍不含物品消耗）。

## 六、注意事项/坑

- **队伍是纯内存态**：服务器重启后所有队伍消失，`player.party_id` 仍残留旧值，但 `get_player_party`（party_service.py:64）会检测到内存态缺失并清掉 `player.party_id = None`。
- **`models/party.py` 不存在**：`blueprints/player.py:90、191` 尝试 `from models.party import Party` 并 `Party.query.get(player.party_id)`，但该模型从未定义——代码被 `try/except Exception: pass` 包住，静默失败。故 `character.html` 里的“队伍信息 / 组队经验加成（team_exp_bonus）”**当前是死代码，恒为 0**。实际生效的队伍加成仅来自 `PartyService.get_party_bonus_rate` 的属性乘区加成，没有经验加成。
- **在线判定可能失真**：`mark_online` 在登录时加入集合，但缺少对应的 `mark_offline` 调用点，离线玩家 id 可能长期留在 `_online_players`，使队伍加成虚高。如需严谨在线判定，应接入 logout/disconnect 钩子。
- 邀请 60 秒过期，申请不过期。

## 七、相关文档

- [legion_design.md](legion_design.md) — 军团（另一套公会/团体系统，独立于队伍；军团加成是固定值，队伍加成是比率）
- [social_relation_design.md](social_relation_design.md) — 好友/红颜知己/结婚（社交比率加成）
- [CLAUDE.md](../../CLAUDE.md) — “Blueprint URL Prefixes” 中 `party` 前缀
