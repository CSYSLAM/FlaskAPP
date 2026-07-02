"""
Migration: Add battle status-effect columns to the `players` table.

Adds:
  - status_confuse_rounds  (Integer, default 0)  混乱剩余回合
  - status_silence_rounds  (Integer, default 0)  封魔剩余回合

Reason: `db.create_all()` only creates tables that don't exist — it will NOT
alter an existing `players` table. Run this once after pulling the new
status-effect code so existing DBs get the columns.

IMPORTANT: This script connects to SQLite directly (bypassing SQLAlchemy) on
purpose. The PlayerModel already declares these columns, so any ORM query
run before the physical ALTER TABLE would crash. Use the raw DB path.

Usage:
    python scripts/migrate_add_status_columns.py            # default instance db
    python scripts/migrate_add_status_columns.py other.db    # alternate db
"""
import os
import sqlite3
import sys

COLUMNS = [
    ("status_confuse_rounds", "INTEGER DEFAULT 0"),
    ("status_silence_rounds", "INTEGER DEFAULT 0"),
    ("status_bleed_rounds", "INTEGER DEFAULT 0"),
    ("status_bleed_value", "INTEGER DEFAULT 0"),
]


def column_exists(con, table, column):
    cur = con.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def main():
    db_name = sys.argv[1] if len(sys.argv) > 1 else "game1.db"
    db_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "instance", db_name,
    )
    if not os.path.exists(db_path):
        print(f"DB not found: {db_path}")
        sys.exit(1)

    print(f"Migrating: {db_path}")
    con = sqlite3.connect(db_path)
    try:
        existing = {row[1] for row in con.execute("PRAGMA table_info(players)")}
        print(f"Existing columns on players: {sorted(existing)}")
        for name, decl in COLUMNS:
            if column_exists(con, "players", name):
                print(f"  SKIP: players.{name} already exists")
                continue
            con.execute(f"ALTER TABLE players ADD COLUMN {name} {decl}")
            con.commit()
            print(f"  ADDED: players.{name} {decl}")
    finally:
        con.close()
    print("Status-column migration complete!")


if __name__ == '__main__':
    main()
