# Bug修复经验

## Bug: UnboundLocalError 在击败神兽时
原因: `_handle_monster_defeat()` 中的 `if monster.is_divine_beast:` 块内写了 `from services.data_service import DataService`（局部导入），而文件顶部已有。Python将 `DataService` 视为局部变量但尚未赋值。

教训: 不要在函数内部重复导入已在文件顶部导入的模块。局部导入会造成变量遮蔽。

## Bug: 神兽击杀公告不显示
原因: `_save_encounter()` 没有保存 `is_divine_beast` 属性到encounter JSON。`get_current_monster()` 从encounter数据重建Monster对象时，`is_divine_beast` 丢失为 `False`。

教训: Monster对象的新属性必须同时添加到 `_save_encounter()` 中，否则encounter序列化/反序列化链路会丢失。

## Bug: 军衔页面 KeyError: '列兵'
原因: `blueprints/player.py` 的 `rank_order` 列表第一项是 `"列兵"`，但 `PlayerModel.MILITARY_RANKS` 的key是 `"士兵"`。

## Bug: 场景怪物链接范围不完整
原因: 神兽和精英怪的链接标签只包裹了部分文字（如只包裹了等级），而不是整个怪物名称。
修复: 将 `<a>` 标签包裹整个 `【兽王】应龙(40级)` 或 `【精】法正(20级精)` 字符串。

## 当前临时状态
- 神器掉落率已改为100%（测试用），测试完需改回5%
- 地上物品已清空（小银两包、止血草、凝魔草均已删除）