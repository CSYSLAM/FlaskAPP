#!/usr/bin/env python3
"""
Flask 游戏项目重构迁移脚本
"""

import os
import shutil
from pathlib import Path

def create_directory_structure():
    """创建新的目录结构"""
    directories = [
        'blueprints',
        'services', 
        'utils',
        'models',  # 已存在，但确保存在
        'templates',  # 已存在
        'data',  # 已存在
        'player_data'  # 已存在
    ]
    
    for directory in directories:
        Path(directory).mkdir(exist_ok=True)
        # 创建 __init__.py 文件
        if directory in ['blueprints', 'services', 'utils']:
            init_file = Path(directory) / '__init__.py'
            if not init_file.exists():
                init_file.write_text('"""\\n{} 模块初始化文件\\n"""'.format(directory))

def backup_original_files():
    """备份原始文件"""
    backup_dir = Path('backup_original')
    backup_dir.mkdir(exist_ok=True)
    
    files_to_backup = ['app.py']
    for file in files_to_backup:
        if Path(file).exists():
            shutil.copy2(file, backup_dir / file)
            print(f"已备份 {file} 到 {backup_dir}/{file}")

def update_template_routes():
    """更新模板中的路由引用"""
    route_mappings = {
        # 认证相关
        "url_for('login_page')": "url_for('auth.login_page')",
        "url_for('register')": "url_for('auth.register')", 
        "url_for('logout')": "url_for('auth.logout')",
        
        # 游戏相关
        "url_for('scene')": "url_for('game.scene')",
        "url_for('move',": "url_for('game.move',",
        "url_for('pickup_item',": "url_for('game.pickup_item',",
        "url_for('view_npc',": "url_for('game.view_npc',",
        
        # 玩家相关
        "url_for('character')": "url_for('player.character')",
        "url_for('level_up')": "url_for('player.level_up')",
        "url_for('inventory')": "url_for('player.inventory')",
        "url_for('equipment_list')": "url_for('player.equipment_list')",
        "url_for('view_player',": "url_for('player.view_player',",
        "url_for('equip_item',": "url_for('player.equip_item',",
        "url_for('unequip',": "url_for('player.unequip',",
        "url_for('view_item',": "url_for('player.view_item',",
        "url_for('sell_item',": "url_for('player.sell_item',",
        "url_for('destroy_item',": "url_for('player.destroy_item',",
        "url_for('use_item',": "url_for('player.use_item',",
        "url_for('bulk_use_item',": "url_for('player.bulk_use_item',",
        "url_for('view_equipment',": "url_for('player.view_equipment',",
        "url_for('enhance_page',": "url_for('player.enhance_page',",
        "url_for('enhance_equipment',": "url_for('player.enhance_equipment',",
        "url_for('learn_skill',": "url_for('player.learn_skill',",
        "url_for('upgrade_skill',": "url_for('player.upgrade_skill',",
        "url_for('skill_hall')": "url_for('player.skill_hall')",
        "url_for('military_ranks')": "url_for('player.military_ranks')",
        "url_for('view_equipped',": "url_for('player.view_equipped',",
        
        # 战斗相关
        "url_for('battle')": "url_for('battle.battle')",
        "url_for('fight')": "url_for('battle.fight')",
        "url_for('pk_battle',": "url_for('battle.pk_battle',",
        "url_for('pk_fight')": "url_for('battle.pk_fight')",
        "url_for('start_pk',": "url_for('battle.start_pk',",
        "url_for('battle_result')": "url_for('battle.battle_result')",
        "url_for('continue_battle')": "url_for('battle.continue_battle')",
        "url_for('revive')": "url_for('battle.revive')",
        "url_for('revive_action',": "url_for('battle.revive_action',",
        "url_for('shortcuts')": "url_for('battle.shortcuts')",
        "url_for('set_shortcut')": "url_for('battle.set_shortcut')",
        
        # 商店相关
        "url_for('shop')": "url_for('shop.shop')",
        "url_for('buy_item')": "url_for('shop.buy_item')",
        
        # 社交相关
        "url_for('chat')": "url_for('social.chat')",
        "url_for('send_message',": "url_for('social.send_message',",
        "url_for('gift_page',": "url_for('social.gift_page',", 
        "url_for('send_gift',": "url_for('social.send_gift',",
        "url_for('toggle_view',": "url_for('social.toggle_view',",
    }
    
    templates_dir = Path('templates')
    if not templates_dir.exists():
        print("templates 目录不存在")
        return
        
    html_files = list(templates_dir.glob('*.html'))
    
    for html_file in html_files:
        print(f"更新模板文件: {html_file}")
        content = html_file.read_text(encoding='utf-8')
        
        # 应用所有路由映射
        for old_route, new_route in route_mappings.items():
            content = content.replace(old_route, new_route)
            
        html_file.write_text(content, encoding='utf-8')

def main():
    print("开始 Flask 游戏项目重构迁移...")
    
    # # 1. 备份原始文件
    # print("1. 备份原始文件...")
    # backup_original_files()
    
    # # 2. 创建目录结构
    # print("2. 创建新的目录结构...")
    # create_directory_structure()
    
    # 3. 更新模板路由
    print("3. 更新模板中的路由引用...")
    update_template_routes()
    
    print("\\n迁移完成!")
    print("\\n接下来需要手动完成的步骤:")
    print("1. 复制新的代码文件到对应目录")
    print("2. 安装依赖: pip install flask")
    print("3. 测试应用: python app.py")
    print("4. 检查模板是否正确渲染")
    print("\\n注意: 原始 app.py 已备份到 backup_original/ 目录")

if __name__ == "__main__":
    main()