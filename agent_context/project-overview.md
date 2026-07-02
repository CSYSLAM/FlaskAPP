# 梦回三国2 项目概览

## 项目定位
Flask文字RPG/挂机冒险游戏，服务端渲染HTML，无前端框架，SQLite数据库。

## 架构
三层模式：Blueprints → Services → Models
- Blueprints: 路由处理，渲染HTML模板
- Services: 业务逻辑
- Models: SQLAlchemy ORM，映射到SQLite

## 运行方式
`python app.py`，debug=True，Flask开发服务器

## 关键设计
- 玩家背包/装备用JSON blob存储（非外键关联）
- 无数据库迁移（ALTER TABLE手动添加列）。加列用专用迁移脚本，如 `scripts/migrate_add_status_columns.py`（加战斗状态列）。**注意：迁移脚本必须用原生 sqlite3 连接，不能 create_app()——因 model 已声明新列，ORM 在加列前查询会崩**
- 聊天系统为内存存储（100条上限，重启丢失）
- 装备生成系统：5个稀有度（普通40%/精良30%/卓越20%/史诗8%/神器2%）
- 世界BOSS/神兽使用类级别内存共享状态（WorldBossService._bosses）
- **伤害公式为统一乘法模型**（2026-07-02）：`伤害 = atk × (1 + atk/max(1,def)) × coefficient`，由 `BattleService._compute_damage` 实现，覆盖玩家打怪/怪物打玩家/PK/副将 4 条路径。详见 `.claude/skills/combat_formulas.md`
- **战斗状态效果**（2026-07-02）：混乱/封魔/流血/吸血/破甲 5 种。玩家状态存 PlayerModel 列（`status_confuse_rounds` 等），怪物状态存 `current_encounter` JSON 的 `monster_status`。详见 `.claude/skills/skill_design.md`

## Blueprint路由前缀
auth=/auth, game=/game, player=/player, battle=/battle, shop=/shop, social=/social, activity=/, lieutenant=/, villa=/, vip=/, rank=/, guide=/, map=/, workbench=/workbench, crafting=/crafting

## 静态数据
data/*.json：怪物、物品、技能、商店、装备模板、等级经验表、称号、攻略
data/locations/*.json：按区域分文件存储场景数据
data/equipment_sets/*.json：装备套装模板（含神器）