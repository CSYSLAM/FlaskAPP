# 数据库Schema变更

项目使用SQLite + `db.create_all()`，只创建新表不会修改已有表。新增列需要手动ALTER TABLE。

在 `app.py` 的 `with app.app_context():` 块中添加 `try/except` 的 `ALTER TABLE` 语句：

```python
try:
    db.session.execute(db.text("ALTER TABLE players ADD COLUMN xxx"))
    db.session.commit()
except Exception:
    db.session.rollback()
```

已有列变更：
- `players.player_uid` (VARCHAR(10)) — 10位随机字母数字ID，注册时生成
- `players.is_designer` (BOOLEAN DEFAULT 0) — 设计师权限标记