"""
Migration script: Convert old PlayerModel.player_data JSON column
to the new normalized table structure.

Usage:
    python scripts/migrate_db.py

This script:
1. Reads all rows from the `players` table that have a `player_data` column
2. Parses the JSON blob
3. Writes data into the new normalized tables (inventory_items, equipment_instances, etc.)
4. Sets player columns from the JSON data
5. Removes the player_data column after migration
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from services import db
from models.player import (
    PlayerModel, EquipmentInstance, InventoryItem,
    EquipmentSlot, PlayerSkill, TempEffect, ChatMessage
)
from services.data_service import DataService


def migrate_player(player_row, old_data):
    """Migrate a single player's JSON data to normalized tables."""
    if not old_data:
        return

    data = old_data if isinstance(old_data, dict) else json.loads(old_data)

    # Update player columns from JSON
    for field in ['level', 'experience', 'exp_to_next_level', 'gold',
                  'health', 'max_health', 'mana', 'max_mana',
                  'attack', 'defense', 'crit_rate', 'dodge_rate',
                  'pill_attack', 'pill_defense', 'pill_max_health', 'pill_max_mana',
                  'current_location', 'honor', 'military_rank', 'rank_attack',
                  'in_battle', 'in_pk', 'last_attack_time', 'enhance_bonus_rate',
                  'current_view']:
        if field in data:
            setattr(player_row, field, data[field])

    if 'pk_opponent' in data:
        player_row.pk_opponent = data['pk_opponent']

    # Migrate inventory
    inventory = data.get('inventory', {})
    for item_id, item_data in inventory.items():
        if isinstance(item_data, dict):
            qty = item_data.get('quantity', 1)
        else:
            qty = int(item_data) if item_data else 1

        if item_id.startswith('equipment_'):
            # This is an equipment instance reference
            equip_data = item_data.get('equipment', {})
            if equip_data:
                equip = EquipmentInstance(
                    player_id=player_row.id,
                    instance_id=item_id,
                    template_id=equip_data.get('template_id', ''),
                    name=equip_data.get('name', item_id),
                    slot=equip_data.get('slot', 'weapon'),
                    rarity=equip_data.get('rarity', '普通'),
                    stars=equip_data.get('stars', 1),
                    level_required=equip_data.get('level_required', 1),
                    class_required=equip_data.get('class_required'),
                    is_bound=equip_data.get('is_bound', True),
                    enhance_level=equip_data.get('enhance_level', 0),
                )
                if equip_data.get('base_stats'):
                    equip.set_base_stats(equip_data['base_stats'])
                if equip_data.get('extra_stats'):
                    equip.set_extra_stats(equip_data['extra_stats'])
                if equip_data.get('initial_stats'):
                    equip.set_initial_stats(equip_data['initial_stats'])
                db.session.add(equip)

        inv = InventoryItem(
            player_id=player_row.id,
            item_id=item_id,
            quantity=qty
        )
        db.session.add(inv)

    # Migrate equipment slots
    equipment = data.get('equipment', {})
    for slot_name, equip_data in equipment.items():
        if equip_data:
            instance_id = equip_data.get('instance_id', '')
            equip_instance = EquipmentInstance.query.filter_by(
                instance_id=instance_id, player_id=player_row.id).first()
            slot = EquipmentSlot(
                player_id=player_row.id,
                slot_name=slot_name,
                equipment_instance_id=equip_instance.id if equip_instance else None
            )
            db.session.add(slot)
        else:
            slot = EquipmentSlot(
                player_id=player_row.id,
                slot_name=slot_name,
                equipment_instance_id=None
            )
            db.session.add(slot)

    # Ensure all slots exist
    for slot_name in EquipmentInstance.SLOTS:
        existing = EquipmentSlot.query.filter_by(
            player_id=player_row.id, slot_name=slot_name).first()
        if not existing:
            db.session.add(EquipmentSlot(
                player_id=player_row.id, slot_name=slot_name))

    # Migrate skills
    skills = data.get('skills', {})
    for skill_id, skill_data in skills.items():
        if isinstance(skill_data, dict):
            level = skill_data.get('level', 1)
            exp = skill_data.get('exp', 0)
        else:
            level = int(skill_data) if skill_data else 1
            exp = 0
        db.session.add(PlayerSkill(
            player_id=player_row.id,
            skill_id=skill_id,
            skill_level=level,
            skill_exp=exp
        ))

    # Migrate shortcuts
    shortcuts = data.get('shortcuts', {})
    if shortcuts:
        player_row.shortcuts_raw = json.dumps(shortcuts, ensure_ascii=False)

    # Migrate chat history
    chat_history = data.get('chat_history', {})
    if chat_history:
        player_row.chat_history_raw = json.dumps(chat_history, ensure_ascii=False)

    # Migrate notifications
    notifications = data.get('notifications', [])
    if notifications:
        player_row.notifications_raw = json.dumps(notifications, ensure_ascii=False)

    # Migrate temp effects
    temp_effects = data.get('temp_effects', [])
    for te in temp_effects:
        db.session.add(TempEffect(
            player_id=player_row.id,
            stat=te.get('stat', ''),
            value=te.get('value', 0),
            rate=te.get('rate', 0),
            expire_time=te.get('expire_time', 0),
            item_id=te.get('item_id'),
            effect_name=te.get('effect_name'),
        ))


def main():
    app = create_app()

    with app.app_context():
        # Check if player_data column exists
        try:
            result = db.session.execute(
                db.text("SELECT id, player_data FROM players LIMIT 1")
            )
            has_player_data = True
        except Exception:
            has_player_data = False
            print("No player_data column found - migration not needed or already done.")

        if not has_player_data:
            print("Migration complete (nothing to do).")
            return

        # Read all players with their JSON data
        players = db.session.execute(
            db.text("SELECT id, player_data FROM players")
        ).fetchall()

        print(f"Found {len(players)} players to migrate.")

        for row in players:
            player = PlayerModel.query.get(row[0])
            if not player:
                continue

            old_data = row[1]
            if old_data:
                try:
                    data = json.loads(old_data) if isinstance(old_data, str) else old_data
                    migrate_player(player, data)
                    print(f"  Migrated player: {player.username}")
                except Exception as e:
                    print(f"  ERROR migrating player {player.username}: {e}")
                    db.session.rollback()
                    continue

        # Create new tables
        db.create_all()
        db.session.commit()

        # Optionally drop player_data column
        try:
            db.session.execute(
                db.text("ALTER TABLE players DROP COLUMN player_data")
            )
            db.session.commit()
            print("Dropped player_data column.")
        except Exception as e:
            print(f"Could not drop player_data column: {e}")

        print("Migration complete!")


if __name__ == '__main__':
    main()