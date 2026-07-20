# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

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

- **Blueprints** (`blueprints/`): Route handlers. ~24 domains registered in `app.py` `create_app()` — including `auth`, `game`, `player`, `battle`, `shop`, `social`, `activity`, `lieutenant`, `villa`, `vip`, `rank`, `guide`, `map`, `workbench`, `medicine`, `warehouse`, `dungeon`, `lost_found`, `legion`, `battlefield`, `party`, `quest`, `crafting`, `lieutenant_commander`. All routes render HTML templates via form POST — no JSON API endpoints. See the full prefix table in `CLAUDE.md`.
- **Services** (`services/`): Business logic. Blueprints call service functions rather than implementing logic directly.
- **Models** (`models/`): SQLAlchemy ORM models mapping to SQLite. Schema created via `db.create_all()` in the app factory — no Alembic/Flask-Migrate. Some "models" (e.g. `Location`, `Skill`, `Equipment`, `Item`, `Monster`) are plain in-memory classes loaded from `data/*.json`, not ORM tables.

**App Factory**: `create_app()` in `app.py` loads config, initializes `db` and `login_manager`, registers all blueprints with URL prefixes, and creates tables.

**Config**: `config.py` defines Dev/Prod/Test classes. Instance-level secrets in `instance/config.py` override base config (not in VCS).

**Static Game Data**: `data/*.json` files define monsters, items, skills, locations, shops, equipment templates, and level-exp tables. Loaded and cached by `services/data_service.py`.

**Mobile Console (separate service)**: `mobile_console/run.py` is a standalone Flask app on port 8765, fully decoupled from the game code. It manages Claude Code/CodeBuddy sessions and can start/stop/restart the game app and stream logs. It is NOT part of the game's blueprint/service/model layers.

## Key Design Decisions

- **Denormalized storage**: Player `inventory` and `equipment` are JSON blobs on the Player model, not relational foreign keys. Same for monster drops and location monster lists.
- **No database migrations**: Schema changes require either manual SQL or recreating the DB. `db.create_all()` only creates tables that don't exist — it won't alter existing tables. New columns are backfilled with manual `ALTER TABLE` statements in `app.py`.
- **Persistent chat**: Public/country/private/system chat is stored in the `chat_messages` table via the `ChatMessage` model (`models/player.py`), read through `services/data_service.py` (`broadcast_system`, `list_latest_messages`). `services/public_chat.py` is only a thin in-memory recent-message cache, not the source of truth.
- **Equipment generation**: Procedural system in `services/equipment_generator.py` with 5 rarity tiers (common 40%, uncommon 30%, rare 20%, epic 8%, legendary 2%). See `.claude/skills/equipment_generation.md` for full design spec.

## Interface Style

All game-facing UI in `templates/` must follow the mobile WAP text-page style guide in `docs/wap_text_ui_skill.md`.

Key rules:
- Mobile-first, text-first, single-column layouts
- Visual hierarchy should come from text, spacing, and restrained semantic color
- Prefer lightweight links, inline CSS/JS, and low-resource interactions
- Use animated gradient text only as sparse emphasis for rare or celebratory content
- Avoid modern heavy card dashboards, oversized buttons, and framework-like UI chrome

## Blueprint URL Prefixes

The full, current blueprint→prefix table (all ~24 domains) lives in `CLAUDE.md` under "Blueprint URL Prefixes". The six original core domains are: `auth` (`/auth`), `game` (`/game`), `player` (`/player`), `battle` (`/battle`), `shop` (`/shop`), `social` (`/social`).

## Authentication

Flask-Login with `Player` model implementing `UserMixin`. Passwords hashed via werkzeug. `login_manager.login_view = 'auth.login'`. `@login_required` from Flask-Login protects routes. No role-based access control.
