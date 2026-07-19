# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Flask-based text RPG / idle-adventure game. Server-rendered HTML with Jinja2 templates, no frontend framework. SQLite database, no migrations.

## Running the App

```bash
python app.py
```
Runs with `debug=True` on the default Flask dev server. No `requirements.txt` exists — dependencies (flask, flask-sqlalchemy, flask-login, werkzeug) must be installed manually.

No test suite is configured.

## Architecture

Three-layer pattern: **Blueprints → Services → Models**

- **Blueprints** (`blueprints/`): Route handlers. Six domains: `auth`, `game`, `player`, `battle`, `shop`, `social`. All routes render HTML templates via form POST — no JSON API endpoints.
- **Services** (`services/`): Business logic. Blueprints call service functions rather than implementing logic directly.
- **Models** (`models/`): SQLAlchemy ORM models mapping to SQLite. Schema created via `db.create_all()` in the app factory — no Alembic/Flask-Migrate.

**App Factory**: `create_app()` in `app.py` loads config, initializes `db` and `login_manager`, registers all blueprints with URL prefixes, and creates tables.

**Config**: `config.py` defines Dev/Prod/Test classes. Instance-level secrets in `instance/config.py` override base config (not in VCS).

**Static Game Data**: `data/*.json` files define monsters, items, skills, locations, shops, equipment templates, and level-exp tables. `data/equipment_sets/*.json` files define equipment set templates (armor sets, weapons, accessories) loaded and merged into the template cache. All data loaded by `services/data_service.py`.

## Key Design Decisions

- **Denormalized storage**: Player `inventory` and `equipment` are JSON blobs on the Player model, not relational foreign keys. Same for monster drops and location monster lists.
- **No database migrations**: Schema changes require either manual SQL or recreating the DB. `db.create_all()` only creates tables that don't exist — it won't alter existing tables.
- **In-memory chat**: `services/public_chat.py` stores messages in a Python list capped at 100 entries. Messages are lost on server restart.
- **Equipment generation**: Procedural system in `services/equipment_generator.py` with 5 rarity tiers (common 40%, uncommon 30%, rare 20%, epic 8%, legendary 2%). See `docs/equipment_generation.md` for full design spec.
- **Blacksmith crafting**: NPC-triggered (铁匠 in monster_id) renders `blacksmith.html`. Epic forging uses `services/crafting_service.py` with per-slot material cost tables: weapons use wood+ore only (2 mats), accessories use wood+ore with varying silver, armor sets use leather+fabric+wood+ore (4 mats). Forged items roll 精良/卓越/史诗 only (no 神器). Separate sell-equipment (by rarity/level-range) and sell-item (by category) pages. Templates in `data/equipment_sets/craft_weapons.json` and `craft_accessories.json`.

## Interface Style

All game-facing UI in `templates/` must follow the mobile WAP text-page style guide in `docs/wap_text_ui_skill.md`.

Key rules:
- Mobile-first, text-first, single-column layouts
- Visual hierarchy should come from text, spacing, and restrained semantic color
- Prefer lightweight links, inline CSS/JS, and low-resource interactions
- Use animated gradient text only as sparse emphasis for rare or celebratory content
- Avoid modern heavy card dashboards, oversized buttons, and framework-like UI chrome

## Blueprint URL Prefixes

| Blueprint | Prefix | Purpose |
|-----------|--------|---------|
| auth | `/auth` | Login, register, logout |
| game | `/game` | Main view, movement, exploration, rest, NPC interaction |
| player | `/player` | Character, inventory, equipment |
| battle | `/battle` | Combat start, attack, skills, flee, result |
| shop | `/shop` | Buy/sell items and equipment |
| social | `/social` | Public chat |
| crafting | `/crafting` | Blacksmith: epic forging (weapons/accessories/armor sets), sell equipment, sell items |
| activity | `/` | Activities, events |
| lieutenant | `/lieutenant` | Lieutenant companion system |
| villa | `/villa` | Player villa/homestead |
| vip | `/vip` | VIP privileges |
| rank | `/rank` | Player rankings |
| guide | `/guide` | Game guides |
| map | `/map` | Map navigation, teleport |
| workbench | `/workbench` | Designer workbench: 玩家属性/公告/装备·怪物·物品·副将设计系统(增删改查) + 伤害/战斗/副将测试 |
| medicine | `/medicine` | Medicine shop (healer NPC) |
| warehouse | `/warehouse` | Item storage warehouse |
| dungeon | `/dungeon` | Copy dungeons |
| lost_found | `/lost_found` | Lost & found items |
| lieutenant_commander | `/commander` | Lieutenant commander NPC |

## Authentication

Flask-Login with `Player` model implementing `UserMixin`. Passwords hashed via werkzeug. `login_manager.login_view = 'auth.login'`. `@login_required` from Flask-Login protects routes. No role-based access control.

## Item Usage Rules

Certain items have restricted usage contexts — they **cannot be used from the backpack** and must be consumed in specific game interfaces:

| Item | Item ID | Usage Context | Rule |
|------|---------|---------------|------|
| 回城符 | `return_scroll` | 地图→回城→【点击回城】 | Only consumed when clicking 回城 in map interface; `is_usable: false` in backpack |
| 神行符 | `speed_scroll` | 地图→神行→选择传送点 | Only consumed when executing 神行 teleport; `is_usable: false` in backpack |
| 活力卡 | `vitality_card` | 山庄→行动力旁【补充】按钮 | Only consumed via "补充(+10)" link when AP not full; `is_usable: false` in backpack. Each card restores 10 AP, max 120 |
| 催熟剂 | `ripening_agent` | 百草园→生长中作物旁【催熟】链接 | Only consumed via "催熟" link on growing plots; `is_usable: false` in backpack |
| 死亡替身符 | `death_substitute` | PK死亡时自动消耗 | Auto-consumed on PK death, not manually usable; `is_usable: false` |
| 断肠草 | `duanchang_cao` | 离婚专用道具 | Used in marriage/divorce flow, not from backpack; `is_usable: false` |
| 结交酒 | `friend_wine` / `bond_wine` | 红颜/知己结交流程 | Used in social interaction flow; `is_usable: false` |
| 断交酒 | `break_wine` | 红颜/知己断交流程 | Used in social interaction flow; `is_usable: false` |
| 副将技能书 | `lt_skill_<id>_<1-3>` | 副将→技能→学习/升级 | 36 本(12技能×3级:入门/进阶/精通)，在副将技能界面消耗，不从背包使用; `is_usable: false`。学1级需50本入门、升2级需20本进阶、升3级需10本精通 |
| 遗忘之章残页 | `lt_forget_page` | 背包→点开残页详情→【合成遗忘之章】 | 50 个残页合成 1 个遗忘之章; `is_usable: false`。合成入口仅在残页详情页显示，合成后残页仍够则留详情页，不够回背包 |
| 遗忘之章 | `lt_forget_tome` | 副将→技能详情→【遗忘】 | 副将遗忘技能时消耗 1 个; `is_usable: false` |
| 经验丹种子 | `exp_seed` / `seed_jingyandan` | 百草园种植 | Used in garden planting, not consumable; type is `seed` or `material` |
| 大经验丹种子 | `seed_big_exp` | 百草园种植(需4级) | Used in garden planting; requires garden level 4 |

**Key principle**: Items with `is_usable: false` must NOT be used from the backpack (player inventory). They are consumed by specific game mechanics or UI interactions. When adding new items, set `is_usable: false` if the item should only work in a specific context.

## Lieutenant (副将) System

详见 `.claude/skills/lieutenant_design.md`，包含属性公式、倍率表、名将base值、技能系统、被动加成、系统播报、工作台设计等完整规则。

关键要点速查：
- **属性公式**：六项统一 `base × level × 悟性(1+e×0.02) × 品质(1+q×0.005) × 强化(1+r×0.015)`，暴击/闪避同公式
- **被动加成bug**：`bonus_value` 在 learn/upgrade 时已按等级取好（如3级存11），`get_passive_bonus()` 直接使用不再乘level
- **18名将**：一级3个(base×0.75,暴击×0.8)、二级6个、三级9个，梯度 一级>二级>三级>普通
- **聚魂幡**：80%三级/19%二级/1%一级，创建时品质0-9随机
- **系统播报**：洗资质/悟性成功/强化成功时播报，失败不播

## Garden (百草园) System

- Seeds defined in `services/villa_service.py` SEEDS dict (21 seed types)
- Base seeds: seed_herb, seed_flower, seed_ginseng, seed_dragon (old system with HARVEST_ITEMS mapping)
- New seeds: seed_jinchuangyao through seed_big_exp (direct item_id in harvest field)
- Garden level requirement: `min_level` field in SEEDS (default 1)
- Action point cost: `ap_cost` field in SEEDS (default 2, higher-tier seeds cost more)
- Ripening agent: Instantly matures a growing crop (consumes 1 ripening_agent item)
- Garden slots: `3 + (villa.level - 1) // 5`
