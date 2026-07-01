# 工作台系统

## 设计师权限
- `PlayerModel.is_designer` (Boolean) — 控制工作台访问权限
- 通过 `_require_designer()` 检查，非设计师重定向到场景页
- 场景页底部仅设计师可见"工作台"链接

### 设置设计师的三种方式

**方式1：通过工作台页面（推荐）**
设计师登录后 → 工作台 → 设置设计师 → 输入目标玩家UID → 点击切换

**方式2：通过Python脚本（命令行）**
```bash
cd "C:/csy_work/fysg/1008/FlaskAPP" && python -c "
from app import create_app
app = create_app()
with app.app_context():
    from models.player import PlayerModel
    from services import db
    p = PlayerModel.query.filter_by(player_uid='目标UID').first()
    if p:
        p.is_designer = True
        db.session.commit()
        print('已设置')
"
```

**方式3：手动SQLite**
```sql
UPDATE players SET is_designer = 1 WHERE player_uid = '目标UID';
```

**注意：** 首次部署时没有任何账号是设计师，需要先用方式2或方式3设置第一个设计师账号，之后其他账号可以通过工作台设置。

## 工作台功能
1. **修改玩家属性** — 查询玩家（支持UID/用户名/数据库ID），修改各项属性
2. **查看玩家详情** — 属性公式拆解明细（flat/rate各来源分解）
3. **发送系统公告** — 全服广播
4. **设置设计师** — 一键切换 is_designer

## 关键：等级变更自动重算属性
当设计师修改玩家等级时，基础属性（attack/defense/max_health/max_mana/crit_rate/dodge_rate）必须按职业公式重新计算，否则属性与等级不匹配。

`blueprints/workbench.py:145-161`，在 save 块中检测 level 字段变更，使用 `CLASSES[player_class]` 的 `base_stats + level_up_stats * (level - 1)` 公式覆盖6项基础属性。

公式优先级：如果同时修改等级和基础属性，公式覆盖手动输入的基础属性值。

## _find_player() 查询逻辑
- 10位字母数字组合 → 按 player_uid 查找
- 纯数字 → 按数据库 id 查找

## 装备属性规则（2026-07-01 重做）
装备/武器模板的 `max_extra_stats` 必须包含全部 6 个属性（attack/defense/max_health/max_mana/crit_rate/dodge_rate，缺失补 `0.0`，不改已有非零值）。值为 `0` 的属性在生成附加属性时被跳过：不参与随机星级生成、不占用品质条数名额、不计入总星级、不在装备详情显示。

**基础属性与品质、星级的关系**：模板 `base_stats` 定义的是该装备最高品质（史诗）属性值。基础属性**只按品质系数衰减**，与星级无关（不管几星基础属性一致）：
- 普通 80% / 精良 90% / 卓越 95% / 史诗 100% / 神器 100%（见 `DataService.RARITY_BASE_RATIO`）

**附加属性星级系数**：每条附加属性独立随机 1-5 星（在目标星级 ±1 波动），按该星级查系数区间随机；`max_extra_stats` 即 5 星上限：
- 5星 100-110% / 4星 100-106% / 3星 100-102% / 2星 98-102% / 1星 96-100%（见 `DataService.EXTRA_STAT_STAR_RANGES`）
- 装备总星级 = floor(各附加属性星级之和 / 条数)，由附加属性反推；调用方传入的 `stars` 仅作为各条附加属性星级波动的中心。

实现位于 `services/data_service.py:create_equipment_instance()` / `_generate_extra_stats()`，工作台预览 `blueprints/workbench.py:_simulate_generate()` 与之保持一致，旧 `models/equipment.py:Equipment` 同步。详见 `.claude/skills/equipment_design.md`「基础属性与品质」「附加属性数值计算」。
- 其他 → 按 username 查找