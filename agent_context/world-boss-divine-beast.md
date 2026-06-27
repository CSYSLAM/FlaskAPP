# 世界BOSS与神兽系统

## 神兽（Divine Beast）

12只神兽都有 `is_elite: true` + `is_divine_beast: true`，通过 `WorldBossService._bosses`（类级别内存dict）管理共享HP和复活状态。

### 关键文件
- `services/world_boss_service.py` — 世界BOSS状态管理（类级别 `_bosses` dict）
- `services/battle_service.py` — 战斗逻辑（`_handle_monster_defeat`、`_save_encounter`）
- `models/monster.py` — Monster类（`get_loot()` 中有神器掉落逻辑）
- `data/monsters.json` — 神兽数据配置

### 重要：encounter数据保存
`_save_encounter()` 将怪物状态序列化为JSON存入 `player.current_encounter`。每次攻击时会通过 `get_current_monster()` 反序列化重建Monster对象。如果某个属性没有保存到encounter中，反序列化后会丢失。

在Monster类上新增属性时，必须同步更新 `_save_encounter()`。

当前 `_save_encounter()` 保存的属性：monster_id, name, level, is_elite, is_divine_beast, killable, immortal, description, base_stats(6项), skills, drops, last_damage_taken, last_damage_dealt, last_action, last_skill, is_world_boss

### 神兽公告
- 击败神兽时通过 `DataService.broadcast_system()` 发送全服公告
- 公告内容格式：`{昵称}率先击杀了{description}，各位承让承让！`
- 公告写入 `chat_messages` 表，场景页展示最近3条

### 神兽复活
- 复活时间：600秒（10分钟）
- 状态存储在内存中（WorldBossService），服务重启后所有BOSS复活

### 神器掉落
当前测试状态：artifact_drop_rate 已改为 1.0（100%），测试完毕后改回 0.05（5%）
- 12只神兽各有独立的 artifact_template 配置
- 神器星级：随机3-5星