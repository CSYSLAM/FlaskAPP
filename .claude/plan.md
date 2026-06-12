# Refactoring Plan - Flask RPG App Full Overhaul

## Phase 1: Engineering Infrastructure & Security

### 1.1 requirements.txt
- Pin flask, flask-sqlalchemy, flask-login, werkzeug, etc.

### 1.2 Password hashing (CRITICAL)
- Replace plaintext comparison in `auth.py` with `werkzeug.security.generate_password_hash` / `check_password_hash`
- Add migration to hash existing plaintext passwords on first load

### 1.3 Config cleanup
- Remove hardcoded `secret_key = 'your-secret-key-here'` from app.py
- Use instance/config.py properly, with fallback generation
- Move game constants (enhance cost, sell prices, class stats) to data/*.json

### 1.4 Flask-Login proper integration
- Make PlayerModel implement UserMixin
- Configure login_manager.login_view = 'auth.login'
- Replace custom session-based login_required with @login_required
- Implement user_loader properly

## Phase 2: Database Normalization

### 2.1 New schema (replacing the single player_data JSON blob)

**players table** - core player attributes:
- id (Integer, PK, autoincrement)
- username (String, unique, not null)
- password_hash (String, not null)
- nickname (String)
- level, exp, hp, max_hp, mp, max_mp, attack, defense, magic_attack, magic_defense, speed
- gold
- location (String, default 'village')
- character_class (String)
- rank (String)
- created_at, last_login

**inventory_items table**:
- id (Integer, PK)
- player_id (FK -> players.id)
- item_id (String) - references data/items.json
- quantity (Integer, default 1)

**equipment_instances table**:
- id (Integer, PK)
- player_id (FK -> players.id, nullable for shop)
- template_id (String) - references equipment templates
- instance_id (String, unique) - generated unique ID
- name (String)
- rarity (String)
- slot (String)
- base_attack, base_defense, base_magic_attack, base_magic_defense, base_hp, base_mp (Integer)
- enhance_level (Integer, default 0)
- additional_stats (JSON for special bonuses)
- equipped (Boolean, default False)

**player_skills table**:
- id (Integer, PK)
- player_id (FK -> players.id)
- skill_id (String)

**player_equipment_slots table**:
- id (Integer, PK)
- player_id (FK -> players.id)
- slot_name (String)
- equipment_instance_id (FK -> equipment_instances.id, nullable)

### 2.2 Migration approach
- Write a one-time migration script that reads old player_data JSON from PlayerModel and splits into new tables
- Keep old PlayerModel temporarily for migration
- After migration, drop the old player_data column

### 2.3 Remove Player pure-Python class
- All logic moves to services or stays as SQLAlchemy model methods
- PlayerModel becomes the single source of truth

## Phase 3: Service Layer Extraction

### 3.1 Create proper service modules
- `services/player_service.py` - registration, leveling, stats, inventory CRUD, equipment equip/unequip/enhance
- `services/battle_service.py` - combat logic (PvE and PvP), damage calculation
- `services/shop_service.py` - buy/sell items and equipment
- `services/social_service.py` - chat, gifting

### 3.2 Slim down blueprints
- Each blueprint only handles HTTP concerns: parse form data, call service, render template
- No business logic in blueprints

### 3.3 Make services stateless
- GameService.current_monster becomes per-player state stored in DB (current_enemy JSON field on players, or separate encounter table)
- No global mutable class variables

## Phase 4: Caching & Performance

### 4.1 Data caching in DataService
- Cache JSON file loads at init_app time
- Provide cached getters for items, skills, monsters, locations, equipment templates, shop configs
- Clear cache on demand (dev mode)

### 4.2 Equipment ID generation
- Use uuid4 instead of timestamp+random

## Phase 5: Concurrency & Robustness

### 5.1 Optimistic locking
- Add `version` column to players table
- On save, check version hasn't changed; if it has, retry
- Or simpler: use SELECT FOR UPDATE within a transaction context

### 5.2 Transaction wrapping
- PK: both players' changes in one transaction
- Gifting: sender loses item + receiver gains item in one transaction
- Enhancing: deduct gold + update equipment in one transaction

### 5.3 Error handling
- Add proper try/except in service layer
- Flash meaningful error messages
- Ensure 404/500 handlers exist

## Phase 6: Blueprint URL consistency

### 6.1 Fix game_bp prefix
- Add url_prefix='/game' to game_bp registration
- Update all templates' url_for references

## Execution Order
1. Phase 1 (security + infra) - can be done independently
2. Phase 2 (DB normalization) - depends on Phase 1 for password_hash field
3. Phase 3 (service layer) - depends on Phase 2 for new model structure
4. Phase 4 (caching) - can overlap with Phase 3
5. Phase 5 (concurrency) - depends on Phase 2/3
6. Phase 6 (URL fix) - can be done anytime after Phase 3
