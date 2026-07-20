# 游戏指南系统设计规则

基于 `blueprints/guide.py`、`data/guides.json`，并说明 `data/guides_content.json` 的实际加载情况。

## 一、概述

游戏内攻略/帮助中心：一个索引页列出全部指南，点进任一指南查看正文。正文以字符串数组形式存储，逐行渲染。

- **蓝图前缀**：`/guide`（`blueprints/guide.py:4`，`url_prefix='/guide'`）。
- **数据来源**：`DataService.get_guides()`（`services/data_service.py:701`）返回缓存 `guides`，该缓存由 `data/guides.json` 装载（`data_service.py:53` 的 `files` 映射 `'guides': 'guides.json'`）。
- **无需登录**：`index`/`detail` 路由未加 `@login_required`（匿名可读）。

## 二、关键文件

| 文件 | 内容 |
|------|------|
| `blueprints/guide.py` | `index:7`、`detail:14`（仅两个路由，逻辑极简） |
| `services/data_service.py` | `get_guides:701`（返回 `_cache['guides']`）；加载映射 `files['guides']='guides.json':53` |
| `data/guides.json` | 指南主数据：键为 `guide_id`，值含 `title`/`category`/`content[]` |
| `data/guides_content.json` | 另一份指南正文数据（**当前未被任何代码加载**，见第六节） |
| `templates/guide_index.html` | 指南索引页 |
| `templates/guide_detail.html` | 指南详情页（接收 `guide`、`guide_id`） |

## 三、路由（均在 `/guide` 蓝图下）

| 路由 | 函数 | 说明 |
|------|------|------|
| `/guide/` | `index` | 取 `DataService.get_guides()` 全部，渲染 `guide_index.html` |
| `/guide/<guide_id>` | `detail` | 取 `guides.get(guide_id)`；不存在返回 `("攻略不存在", 404)`，否则渲染 `guide_detail.html` |

## 四、核心逻辑 / 设计规则

### 4.1 数据形状（`data/guides.json`）

顶层为字典，键即 `guide_id`（如 `新手指导`、`装备系统`、`PK玩法`）；每项为：

```json
{
  "新手指导": {
    "title": "新手指导",
    "category": "新手入门",
    "content": ["一、...", "", "二、...", "..."]
  }
}
```

- `title`：显示标题（通常与 `guide_id` 相同）。
- `category`：分组标签（如 `新手入门`），用于索引页分类。
- `content`：字符串数组，每个元素一行；空字符串 `""` 渲染为换行/分隔（`detail` 模板逐行输出）。

### 4.2 渲染流程

- `index`：`guides = DataService.get_guides()` 直接把整张表传给模板，由模板决定如何分组/列出。
- `detail`：`guide = guides.get(guide_id)`，传 `guide` 与 `guide_id` 给模板；模板按 `guide['content']` 逐行渲染（`guide_detail.html`）。

### 4.3 `data/guides_content.json` 的差异

该文件结构不同：顶层为 `guide_id → 单段长字符串`（用 `\n\n`/`\n` 分隔段落），**没有 `title`/`category`/`content[]` 结构**，例如 `"装备系统": "一、『品质』...二、『职业』..."`。与 `guides.json` 互为平行版本。

## 五、数据文件 / 配置

- `data/guides.json`：当前生效的指南数据（含 `新手指导`/`日常进阶`/`银两获取`/`金珠获取`/`装备系统`/`技能系统`/`称号系统`/`成就系统`/`社交系统`/`山庄系统`/`军衔系统`/`副将系统`/`军团系统`/`神兽玩法`/`精怪玩法`/`PK玩法` 等）。
- `data/guides_content.json`：含相同主题（如 `新手指导`/`装备系统`/`PK玩法`/`称号系统`/`成就系统` 等）的纯文本版，内容更详尽（例如 `PK玩法` 含完整奖惩分档说明），但**代码未加载**。

## 六、注意事项 / 坑

1. **`guides_content.json` 未被加载**：`DataService._load_all_data` 的 `files` 映射仅含 `'guides': 'guides.json'`（`data_service.py:53`），`guide` 蓝图只用 `get_guides()`，因此 `guides_content.json` 目前是**死数据**——它那版更详尽的 `PK玩法`/`称号系统` 等正文不会出现在游戏内。如需启用，要在 `data_service.py` 增加加载项并让 `detail` 模板兼容"单字符串"格式。
2. **两份数据主题重叠但格式不同**：`guides.json` 用 `content[]` 数组，`guides_content.json` 用单字符串，二者不能直接互换。
3. **`detail` 不存在返回 404 纯文本**：`return "攻略不存在", 404`（`guide.py:20`），非渲染模板，风格与其它页不一致。
4. **无分类筛选路由**：`index` 一次性给全表，分类仅作展示标签，无 `/guide?category=` 之类过滤。
5. **匿名可访问**：指南路由无 `@login_required`，与大部分需登录的蓝图不同。

## 七、相关文档

- `CLAUDE.md` —— "Blueprint URL Prefixes"（指南 `/guide`）
- `.claude/skills/pk_combat_design.md` —— 游戏内 `PK玩法` 指南（`guides_content.json` 有更全版本但当前未加载）
- `.claude/skills/title_design.md` / `.claude/skills/achievement_design.md` —— 对应 `称号系统`/`成就系统` 指南主题
