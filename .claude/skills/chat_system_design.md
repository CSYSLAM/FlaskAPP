# 聊天系统设计 Skill

## 频道体系

### 公共频道
- 发言消耗：小喇叭（horn_small）x1
- 所有在线玩家可见
- 发言后在场景顶部显示：`【公共】玩家名：内容`
- 消息存入 `chat_messages` 表，类型 `public`

### 国家频道
- 发言免费
- 只有同国家玩家可见（按 `player.country` 过滤）
- 场景顶部显示：`【魏】玩家名：内容`
- 消息类型 `country`

### 私聊频道
- 从玩家页面进入：`/social/private/<username>`
- 黑名单检查：被拉黑则无法发送
- 消息类型 `private`
- 私聊列表页显示所有收发私聊

### 系统频道
- 只读，无输入框
- 展示系统广播：神兽击杀、神器获得、新婚戒指包、砸蛋/翻牌奖励等
- 消息类型 `system`
- 通过 `DataService.broadcast_system(content)` 写入
- **显示格式**：`【系统】内容(HH:MM)`（本地时间UTC+8）
- **排序规则**：最新消息在最上方（`order_by(created_at.desc())`）

## 界面风格

参考天命三国（tmsg2.n6game.cn）聊天界面：
- 顶部：频道名称 + 刷新链接
- 标签行：公共 | 国家 | 私聊 | 系统（当前标签加粗）
- 公共/国家频道：输入框(30字限制) + 发言按钮
- 公共频道输入框下方标注 `(消耗小喇叭x1)`
- 消息格式：`玩家名链接: 内容(时:分)`（本地时间）
- 私聊格式：`你对 玩家名: 内容(时:分)` 或 `玩家名 对你说: 内容(时:分)`
- 系统格式：`【系统】内容(时:分)`（本地时间）
- 底部：返回游戏 + 当前时间

## 系统消息触发场景

| 场景 | 消息格式 | 代码位置 |
|------|---------|----------|
| 神兽击杀 | `恭喜玩家率先击杀了XX，各位承让承让！` | battle_service.py |
| 神器获得 | `恭喜玩家获得神器装备名` | item_service.py |
| 新婚戒指包使用 | `玩家打开新婚X戒包，获得了装备名，恭喜恭喜！` | item_service.py |
| 砸蛋活动 | `玩家参与砸蛋活动：拿下了奖励名，太有实力啦！` | activity_service.py |
| 翻牌活动 | `玩家参与翻牌活动：拿下了奖励名，太有实力啦！` | activity_service.py |

## 时间显示处理

数据库存储UTC时间（`created_at = db.Column(db.DateTime, default=datetime.utcnow)`），显示时转换为本地时间：
- 模板中使用 `timedelta`：`{% set msg_time = msg.created_at + timedelta(hours=8) %}`
- 路由传入 `timedelta` 对象：`render_template(..., timedelta=timedelta)`

## 场景顶部消息显示

`scene.html` 在 flash 消息区上方显示最近3条：
- 公共消息：`【公共】玩家名：内容`
- 国家消息：`【魏】玩家名：内容`
- 按时间倒序后再反转显示（最早在上）

## 数据存储

### ChatMessage 模型
```python
class ChatMessage:
    sender_id      # 发送者（系统消息为 None）
    receiver_id    # 接收者（私聊用）
    content        # 消息内容
    message_type   # 'public' | 'country' | 'private' | 'system'
    created_at     # 发送时间（UTC）
```

### 关键查询
- 公共消息：`message_type='public', receiver_id=None`
- 国家消息：`message_type='country', sender_id IN (同国玩家ID列表)`
- 私聊消息：`message_type='private', (sender_id=A AND receiver_id=B) OR (sender_id=B AND receiver_id=A)`
- 系统消息：`message_type='system', order_by(created_at.desc())`

## 与旧系统的区别

| 特性 | 旧系统 | 新系统 |
|------|--------|--------|
| 公共发言 | 免费 | 消耗小喇叭 x1 |
| 大喇叭 | 消耗 megaphone | 已移除 |
| 消息类型 | 'player' | 'public' / 'country' |
| 频道标签 | 无 | 公共/国家/私聊/系统 |
| 国家频道 | 无 | 新增 |
| 场景消息 | 混合显示 | 公共+国家分层显示 |
| 时间显示 | UTC时间 | 本地时间(UTC+8) |
| 排序规则 | 正序+reverse | 倒序直接显示 |

## 关键代码位置

- 路由：`blueprints/social.py` — chat/send_message/private_chat/send_private_message
- 服务：`services/social_service.py` — send_public_message/send_country_message/send_private_message/get_*_messages
- 模板：`templates/chat.html` / `templates/private_chat.html`
- 场景：`templates/scene.html` 顶部消息区
- 数据：`services/data_service.py` — broadcast_system/list_latest_messages

## 规则变更记录

| 日期 | 变更内容 |
|------|---------|
| 2026-06-27 | 系统消息显示本地时间(UTC+8)，使用timedelta处理 |
| 2026-06-27 | 消息排序改为最新在上，移除模板reverse过滤器 |
| 2026-06-27 | 砸蛋/翻牌添加系统公告：玩家参与XX活动：拿下了奖励 |
| 2026-06-27 | 新婚戒指包使用添加系统公告 |
