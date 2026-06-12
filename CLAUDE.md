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
| workbench | `/workbench` | Designer workbench for GM operations |
| medicine | `/medicine` | Medicine shop (healer NPC) |
| warehouse | `/warehouse` | Item storage warehouse |
| dungeon | `/dungeon` | Copy dungeons |
| lost_found | `/lost_found` | Lost & found items |
| lieutenant_commander | `/commander` | Lieutenant commander NPC |

## Authentication

Flask-Login with `Player` model implementing `UserMixin`. Passwords hashed via werkzeug. `login_manager.login_view = 'auth.login'`. `@login_required` from Flask-Login protects routes. No role-based access control.
