# 技能/Skill 文档索引（模块总览）

本目录是按**领域模块**组织的游戏系统设计文档（skill），供 AI 协助开发时参考。
所有文档均基于最新代码（`app.py` 实际注册的 24 个蓝图）编写，函数均附 `file:line` 引用。

> 配套的中心文档：
> - `CLAUDE.md`（项目总览 + 蓝图前缀表 + 物品使用规则 + 副将/PK/百草园速查）
> - `AGENTS.md`（架构与运行说明）
> - `agent_context/`（设计记录 / 运维笔记，见文末）

## 一、战斗与数值（Combat & Numbers）
| 文档 | 内容 |
|------|------|
| [combat_formulas.md](combat_formulas.md) | 统一乘法伤害公式、PvE/PK/副将三路径、5 种战斗状态效果、世界BOSS规则 |
| [skill_design.md](skill_design.md) | 主动/被动技能数据（`skills.json`）、伤害公式接入、蓝耗取整、状态字段 |
| [pk_combat_design.md](pk_combat_design.md) | 发起条件、荣誉/银两零和分档、减免、被怪死亡惩罚、复活、免战符、仇敌追杀 |
| [lieutenant_design.md](lieutenant_design.md) | 副将属性公式、18名将×3档、技能/被动、战斗集成、工作台设计 |
| [battlefield_design.md](battlefield_design.md) | 战场/领土战 PvP（段位城市、令旗、占领），与 PK 系统独立 |

## 二、装备与物品（Equipment & Items）
| 文档 | 内容 |
|------|------|
| [equipment_design.md](equipment_design.md) | 装备主文档：基础/附加属性、稀有度、神器独立、强化、套装、工作台设计 |
| [equipment_generation.md](equipment_generation.md) | `EquipmentGenerator` 公开 API、掉落配置、星级机制、命名规则 |
| [monster_equipment_drop_rules.md](monster_equipment_drop_rules.md) | 怪物掉落分级、品质池、掉率、神器隔离、绑定、精英材料 |
| [crafting_design.md](crafting_design.md) | 铁匠铺：史诗打造（材料表）、强化、批量卖装备/卖道具 |
| [jinzu_shop_item_rules.md](jinzu_shop_item_rules.md) | 金珠商城道具分类与使用上下文规则（背包可用 vs 场景专用） |
| [shop_promo_pack_rules.md](shop_promo_pack_rules.md) | 促销礼包（军团战/血蓝石/号角/材料/婚戒）与 `usage_effect` 配置 |
| [warehouse_and_drop_rules.md](warehouse_and_drop_rules.md) | 仓库（银两/物品存取、容量）＋遗失物品（赎回＋拍卖生命周期） |

## 三、社交与组织（Social & Org）
| 文档 | 内容 |
|------|------|
| [chat_system_design.md](chat_system_design.md) | 持久化聊天（公频/国频/私聊/系统）、播报、`chat_messages` 表 |
| [social_relation_design.md](social_relation_design.md) | 好友/黑名单/仇敌、红颜/知己、结交/断交酒、婚恋、配偶传送、送礼 |
| [legion_design.md](legion_design.md) | 军团：创建/加入、技能、捐献、任务、兑换、领土战占领 |
| [party_design.md](party_design.md) | 组队：5人上限、在线加成（内存态） |

## 四、成长与经济（Progression & Economy）
| 文档 | 内容 |
|------|------|
| [activity_design.md](activity_design.md) | 日常活动：签到/砸蛋/猜拳/答题/陪读/翻牌/幸运币/活跃度/每日任务 |
| [finance_design.md](finance_design.md) | 金珠理财·股市：交易时段、涨跌、限价委托、劫匪、榜单（内存态） |
| [quest_design.md](quest_design.md) | 主/支线任务：JSON Schema、6类 objective、进度追踪、国别隔离 |
| [vip_design.md](vip_design.md) | VIP 等级权益（属性/经验/仓库/PK减免/免损/传送/称号）、诸侯令 |
| [achievement_design.md](achievement_design.md) | 成就：校验/领取/进度/加成、16分类、道具/宝匣系列档位 |
| [title_design.md](title_design.md) | 称号：前缀/后缀、数量×星级加成、套装对激活隐藏属性 |
| [rank_design.md](rank_design.md) | 排行榜：财富/荣誉/等级/成就/魅力/勤奋 取数与排名 |
| [guide_design.md](guide_design.md) | 游戏内指南：`guides.json` 结构、`/guide` 路由 |

## 五、世界与交互（World & Interaction）
| 文档 | 内容 |
|------|------|
| [villa_design.md](villa_design.md) | 山庄：镇守副将、演武场、百草园（SEEDS/催熟）、好友偷取/祈福、活力卡 |
| [map_design.md](map_design.md) | 地图：传送、回城（回城符）、神行（神行符）、副本内禁传送 |
| [medicine_design.md](medicine_design.md) | 医药铺（治疗 NPC）：浏览/购买药品与种子 |
| [lost_found_design.md](lost_found_design.md) | 失物招领＋拍卖行：赎回/竞拍逻辑 |
| [copy_dungeon_design.md](copy_dungeon_design.md) | 数据驱动副本：JSON 结构、阶段/目标、禁传送、黄巾/计定辽东/官渡走查 |
| [ice_tower_design.md](ice_tower_design.md) | 寒冰塔：6层26房、楼层精英为共享世界BOSS、寒冰塔通行令 |
| [auth_design.md](auth_design.md) | 注册/登录/选服选角建角/新手剧情 + 多窗口 SSO/限流（`app.py` 钩子） |

## 六、界面规范（UI）
| 文档 | 内容 |
|------|------|
| [wap_text_ui_skill.md](wap_text_ui_skill.md) | 手机 WAP 文字页风格总规范：文字优先、语义色、轻交互、资源预算 |
| `../agent_context/interface-style.md` | 界面风格落地细则：页面骨架、固定视觉约定（链接色/品质色/地图语义）、模块页面清单 |

## 七、设计工具（Designer Workbench）
| 文档 | 内容 |
|------|------|
| `../agent_context/workbench-designer.md` | 设计师权限、设置方式、等级变更重算、装备属性规则、`_find_player` 逻辑 |

## 八、运维 / 设计记录（`agent_context/`，非 skill）
| 文档 | 内容 |
|------|------|
| `../agent_context/world-boss-divine-beast.md` | 12 神兽/世界BOSS：共享血量、击杀播报、600s 复活、神器掉落 |
| `../agent_context/huangjin-trial-live-notes.md` | 黄巾起义副本实测记录、5阶段流程、待对齐项 |
| `../agent_context/tmsg-achievement-alignment.md` | 成就 16 分类重新对齐记录（道具系列已落地） |
| `../agent_context/db-schema-migration.md` | SQLite 无迁移：`ALTER TABLE` 手动加列、`db.create_all()` 局限 |
| `../agent_context/bugfix-lessons.md` | 修复经验：神兽 UnboundLocalError、击杀公告、军衔 KeyError（已修复）、临时状态 |

---

### 命名约定
- `*_design.md`：某系统的完整设计规则（多数模块）。
- `*_rules.md`：物品/分类/掉落等规则型文档。
- `*_generation.md` / `*_formulas.md` / `*_skill.md`：生成器 API / 数值公式 / UI 规范等专项。
- 交叉引用一律用相对路径链接；中心总览见 `CLAUDE.md` 与 `AGENTS.md`。
