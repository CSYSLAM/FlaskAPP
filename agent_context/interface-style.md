# 界面风格规范

本项目所有游戏端页面统一遵循“手机 WAP 文字页”设计 skill。

完整说明见 [docs/wap_text_ui_skill.md](/C:/csy_work/fysg/1008/FlaskAPP/docs/wap_text_ui_skill.md)。

## 核心定位
- 移动端优先
- 文字主导
- 彩色文本分层
- 轻交互、低资源
- 一屏一条主任务线

## 必守规则

### 页面骨架
- `viewport` 固定为 `width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no`
- 默认单栏流式排版，不做复杂卡片瀑布流
- `body` 统一保留左右 10px 边距
- 默认字体大小以 `16px` 为基线
- 所有页面优先使用服务端渲染和内联少量 CSS/JS

### 文本层级
- 普通叙述用默认黑字
- 可点击操作统一蓝链 `#136ec2`
- 奖励、品质、身份、稀有内容通过颜色而不是重组件区分
- 渐变炫彩文字只能点缀标题、掉落、称号、稀有提示，单屏尽量不超过 1 到 2 处
- 不依赖大面积背景、重阴影、复杂圆角来建立层级

### 交互密度
- 每个区块只保留当前最相关动作
- 导航优先使用文字链接和 `.` 分隔
- 链接点击后显示轻量 loading，避免重复触发
- 表单提交、道具查看、地图开关都保持文字化、低阻力
- 除非信息量确实需要，否则不要引入弹窗、抽屉、标签页套标签页

### 资源预算
- 不引入前端框架
- 不依赖大图、视频、复杂 SVG、长动画
- 样式复用优先，避免每页发散成不同视觉语言
- JS 只做点击反馈、局部显隐、轻量信息浮层

## 项目内固定视觉约定

### 链接与导航
- 链接颜色：`#136ec2`
- 链接默认无下划线
- 导航形式：`角色 .背包 .聊天 .活动`

### 装备品质色
- `.rarity-common`: `#ccc`
- `.rarity-uncommon`: `#2eff2e`
- `.rarity-rare`: `#0070dd`
- `.rarity-epic`: `#a335ee`
- `.rarity-legendary`: `#ff6600`

### 地图语义
- `.block`：小方块地图单元
- `.now_map_block`：当前位置
- `.map_block`：可见普通场景
- 场景名前加 `*`：安全区

### 通用 loading
```html
<div id="loading"><span></span></div>
<script>
var aLinks=document.getElementsByTagName("a");
for(var i=0;i<aLinks.length;i++){aLinks[i].onclick=function(){document.getElementById('loading').style.display='block';};}
setTimeout(function(){document.getElementById('loading').style.display='none';},350);
</script>
```

## 页面设计判断标准
- 这个页面是不是主要靠文字就能完成目标？
- 颜色是不是在表达信息优先级，而不是单纯装饰？
- 用户是不是一眼就能看到“现在该点什么”？
- 去掉大多数样式后，页面是否仍然清楚可玩？
- 这页的 CSS/JS 是否足够轻，低端手机也能顺畅打开？

## 模块页面清单
认证: `login.html`, `register.html`, `select_server.html`, `create_role.html`, `story.html`
游戏: `scene.html`
玩家: `character.html`, `inventory.html`, `skill_list.html`, `equipment_list.html`, `titles.html`
战斗: `battle.html`, `battle_result.html`, `revive.html`, `revive_result.html`
商店: `shop.html`
社交: `chat.html`, `social_index.html`, `social_friends.html`, `social_hongyan.html`, `social_zhiji.html`, `social_enemies.html`, `social_blacklist.html`
地图: `map_index.html`, `map_teleport.html`, `map_town.html`, `map_shenxing.html`, `map_world.html`, `map_area.html`
其他: `guide_index.html`, `guide_detail.html`, `activities.html`, `military_ranks.html`, `vip.html`, `rank_index.html`, `rank_show.html`
工作台: `workbench/index.html`, `workbench/edit_player.html`, `workbench/view_player.html`, `workbench/announce.html`, `workbench/set_designer.html`
