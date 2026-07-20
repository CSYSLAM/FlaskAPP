# 登录注册与新手引导（认证）系统设计规则

账号注册、登录、选服/选角/建角、新手剧情，以及多窗口单点登录（SSO）与会话/限流机制。URL 前缀 `/auth`。

## 一、概述

`auth` 模块是玩家入口与 onboarding：
1. **注册** `/register`：建账号（werkzeug 哈希密码），此时无角色。
2. **登录** `/`：校验密码 → `login_user` + 绑定窗口 SSO。
3. **选服** `/select_server` → **选角/建角** `/select_role`、`/create_role`：填昵称/职业/性别/国家，初始化角色属性与新手装备。
4. **新手剧情** `/story/<id>`、`/story_complete`：5 段国别剧情，完成后落出生场景。

此外 `app.py` 的 `before_request` 钩子实现**多窗口会话（sid）**、**单点登录踢人（setup_window_auth）**、**在线标记（track_online）**、**请求限流（rate_limit，ck/tic/aid 凭证体系）**。

## 二、关键文件

| 文件 | 内容 |
|------|------|
| `blueprints/auth.py` | 路由与流程；COUNTRY_START / COUNTRY_STORY 映射 |
| `services/player_service.py` | `authenticate`（密码校验）、`create_character`（建角初始化） |
| `models/player.py` | `PlayerModel`（UserMixin） |
| `app.py` | `ensure_sid`、`setup_window_auth`、`track_online`、`rate_limit` 钩子；蓝图注册（/auth，line 237） |
| `services/window_session_service.py` | 多窗口会话（sid ↔ {user_id, sso_token}） |
| `services/auth_session_service.py` | 单点登录（ActiveSession 表：active_sid + tokens） |
| `services/rate_limit_service.py` | tic 票据与限流（ck/tic/aid 体系） |
| `models/active_session.py` | `ActiveSession` 表 |

## 三、路由（前缀 /auth）

> 蓝图 `auth_bp` 本身无 `url_prefix`（auth.py:7），由 `app.py:237` 注册为 `/auth`。

| 路由 | 方法 | 说明 |
|------|------|------|
| `/auth/` | GET/POST | 登录页（POST 校验密码并登录） |
| `/auth/register` | GET/POST | 注册（建账号，无角色） |
| `/auth/select_server` | GET | 选区页 |
| `/auth/select_role` | GET | 选角/建角分流（已有角色→剧情或进游戏；否则建角页） |
| `/auth/create_role` | GET/POST | 创建角色（昵称/职业/性别/国家） |
| `/auth/story/<int:story_id>` | GET | 新手剧情（共 5 段，按国家） |
| `/auth/story_complete` | GET | 完成剧情，进入游戏（落出生场景） |
| `/auth/logout` | GET | 登出（仅清当前窗口） |

## 四、核心逻辑 / 设计规则

### 4.1 国家映射（auth.py:10-21）

- `COUNTRY_START`：魏→`beiping_east.大院`、蜀→`jianing_west.大院`、吴→`wujun_east.大院`。
- `COUNTRY_STORY`：魏/蜀/吴 → `story_wei/shu/wu`（剧情内容区分）。

### 4.2 注册 `register`（auth.py:59）

- 校验两次密码一致、用户名唯一（`PlayerModel.query.filter_by(username)`）。
- 生成 **10 位唯一 `player_uid`**（数字+小写字母，循环去重，auth.py:82）。
- `password_hash = generate_password_hash(password)`（werkzeug）。
- 建 `PlayerModel`：昵称/职业/性别/国家空（`''`/默认男/魏），`level=1`、`gold=1500`、基础战斗值（health100/mana50/atk10/def5/crit0.05/dodge0.03）、`current_location='beiping_center.广场'`。**注意：仅建账号，无角色信息（nickname/class 为空）**。
- 成功后跳登录页，闪账号密码提示（建议截图保管）。

### 4.3 登录 `login_page`（auth.py:24）

- `PlayerService.authenticate(username, password)`（player_service.py:98）：查账号 + `check_password_hash`，更新 `last_login`，返回 player 或错误。
- `login_user(player)`；写 `session['username']`/`session['player_id']`。
- **绑定窗口 SSO**：`window_session_service.bind_window(sid, player.id)`（auth.py:46-47）→ 生成 sso token 并把该账号活动 sid 切到本窗口（旧窗口失效）。
- 登录播报：VIP5 系统广播上线；`SocialService.notify_relations_login` 通知配偶/关系。

### 4.4 选角 / 建角 / 剧情

- `select_role`（auth.py:126）：已有 `nickname`&`player_class` 且 `story_completed` → 进游戏；未完剧情 → 重走 `story`；否则建角页。
- `create_role`（auth.py:142）→ `PlayerService.create_character`（player_service.py:61）：
  - 校验 `CLASSES` 有效、昵称唯一。
  - 按职业 `base_stats` 初始化全部战斗属性，`level=1`、`exp_to_next_level=50`、`gold=1500`。
  - `DataService.init_equipment_slots`；赠 `potion_heal`、`potion_mana` 各 50（绑定）。
  - 提交后转向剧情 `story/1`。
- `story`（auth.py:167）：`total_stories=5`，按 `player.country` 取 `story_wei/shu/wu` 内容渲染。
- `story_complete`（auth.py:191）：`story_completed=True`，`current_location = COUNTRY_START[country]` → 进游戏。

### 4.5 登出 `logout`（auth.py:209）

- 仅清**当前窗口**：`window_session_service.clear_window(sid)` + `auth_session_service.clear(pid, sid=sid)`（不影响同浏览器其他窗口）。
- `logout_user()`，清 `session['username']`/`['player_id']`。

### 4.6 Flask-Login 集成

- `PlayerModel` 实现 `UserMixin`；`login_manager.login_view='auth.login'`。
- 本应用因多窗口，实际 `current_user` 由 `setup_window_auth` 注入 `g._login_user`（见下），`@login_required` 仍生效。

### 4.7 多窗口 SSO 与会话机制（`app.py`）

- **`ensure_sid`（app.py:91，before_request）**：无 sid 的 GET 先从 `Referer` 恢复 sid（GET 表单丢 sid 场景），仍无则分配新 sid 并重定向带 `?sid`。`sid` 经 `url_defaults` 注入所有站内链接。
- **`setup_window_auth`（app.py:127，before_request）**：按当前 `sid` 从窗口会话取 `user_id` 注入 `g._login_user`；并 `is_window_active()` 检测 SSO——若本窗口 token 失效（同账号在别处登录）→ 清窗口 + 重定向登录页 `kicked=1`（「该账号在别处登录，您已下线」）。未登录窗口显式置匿名用户，避免共享 cookie 串号。
- **`track_online`（app.py:164）**：已认证则 `party_service.mark_online(id)` 标记在线。
- **`rate_limit`（app.py:173）**：基于 `rate_limit_service` 的 **tic 旧票据检测**——请求 `tic < 上次接受的 tic`（复制旧 URL / 后退旧页）→ 渲染 `rate_limit.html` 返回 429；同页多按钮共享同 tic 放行。凭证体系：`ck=sid`、`tic=请求票据`、`aid=动作标识`（见 rate_limit_service 文档头）。

### 4.8 SSO 实现细节

- `auth_session_service.bind(player_id, sid)`（auth_session_service.py:37）：生成 token，写入 `ActiveSession`（active_sid=sid，tokens[sid]=token），旧 sid token 仍在但 active_sid 已切 → 旧窗口 `is_active` 失效被踢。
- `is_active`（auth_session_service.py:65）：`sid==active_sid 且 tokens[sid]==token` 才有效；token 为 None（旧会话/重启残留）视为合法（不踢，等下次登录再绑）。
- 多 worker 共享同一 `ActiveSession` 表，状态一致；并发登录由 DB 写锁串行化。

## 五、数据文件 / 配置

- 密码：`werkzeug.security.generate_password_hash` / `check_password_hash`（默认 pbkdf2/sha256）。
- `ActiveSession` 表：`player_id / token / active_sid / tokens(JSON)`；`app.py` 启动时对旧表 `ALTER TABLE` 补 `active_sid`/`tokens` 列（app.py:282-290）。
- 国家/出生/剧情映射硬编码于 `auth.py` 顶部与 `data/story_*.json`（剧情内容，由 story 页 `story_{id}` 取）。

## 六、注意事项 / 坑

- 注册只建**账号**不建角色；角色靠 `create_role` 后 `create_character` 初始化。直接操作 DB 插入的账号若无角色会停留在建角页。
- `player_uid` 为 10 位，注册时循环随机生成去重；`app.py` 启动会对旧库 `ALTER` 补该列。
- 多窗口 SSO 依赖 URL `?sid` 全程携带；手输 URL / 书签（无 sid）会被 `ensure_sid` 当作新窗口分配新 sid（新登录态），可能造成「同浏览器两个账号」。
- 旧会话（功能上线前已登录、无 token）首次不踢，等下次主动登录才绑定——属有意的平滑过渡。
- `logout` 只清当前 sid 窗口，不会 `session.clear()`（避免误踢同浏览器其他窗口）。

## 七、相关文档

- `CLAUDE.md` →「Authentication」「Blueprint URL Prefixes（auth）」
- `.claude/skills/equipment_design.md` → 建角赠送的 `potion_heal`/`potion_mana`、装备槽初始化
- `.claude/skills/villa_design.md` → 账号登录后 VIP 广播（login 流程）
