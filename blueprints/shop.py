from flask import Blueprint, render_template, request, session, redirect, url_for, flash
from models.item import Item
from services.data_service import DataService
from utils.decorators import login_required, check_health_status, check_pk_status

shop_bp = Blueprint('shop', __name__)

# 商城配置 - 可以轻松修改这里来改变显示的商品
SHOP_CONFIGS = {
    'default': {
        'name': '通用商城',
        'item_ids': None,  # None表示显示所有有价格的物品
        'category': 'all'
    },
    'potions': {
        'name': '药水商店',
        'item_ids': [
            'potion_heal', 'potion_mana', 'potion_health', 'potion_mana_temp',
            'potion_attack', 'potion_defense', 'potion_crit', 'potion_dodge',
            'potion_attack_absolute', 'potion_defense_absolute', 'potion_attack_mixed',
            'potion_crit_absolute', 'potion_dodge_absolute', 'potion_health_absolute',
            'potion_mana_absolute', 'potion_combo_attack', 'potion_elite'
        ],
        'category': None
    },
    'pills': {
        'name': '金丹商店',
        'item_ids': [
            'pill_attack', 'pill_defense', 'pill_health', 'pill_mana'
        ],
        'category': None
    },
    'materials': {
        'name': '材料商店',
        'item_ids': [
            'honor_scroll', 'enhance_gem', 'chest_key', 'money_small'
        ],
        'category': None
    },
    'chests': {
        'name': '宝箱礼盒',
        'item_ids': [
            'chest_lv1_weapon', 'chest_lv1_gear', 'gift_lv1_artifact'
        ],
        'category': None
    },
    'experience': {
        'name': '经验商店',
        'item_ids': [
            'exp_small', 'exp_large'
        ],
        'category': None
    }
}

@shop_bp.route("/")
@shop_bp.route("/<shop_type>")
@login_required
@check_health_status
@check_pk_status
def shop(shop_type='default'):
    player = DataService.get_current_player(session)
    
    # 获取分页参数
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    
    # 限制每页显示数量
    per_page = min(max(per_page, 5), 50)
    
    # 获取商店配置
    config = SHOP_CONFIGS.get(shop_type, SHOP_CONFIGS['default'])
    
    # 初始化默认的shop_data结构
    shop_items = {}
    total_items = 0
    total_pages = 1
    has_prev = False
    has_next = False
    
    # 获取物品数据
    try:
        all_items = Item.load_items()
        
        if config['item_ids']:
            # 使用ID列表获取物品
            for item_id in config['item_ids']:
                if item_id in all_items and all_items[item_id].price > 0:
                    shop_items[item_id] = all_items[item_id]
        else:
            # 使用分类获取物品
            for item_id, item in all_items.items():
                if item.price > 0:
                    if config['category'] == 'all' or item.item_type.value == config['category']:
                        shop_items[item_id] = item
        
        # 分页处理
        total_items = len(shop_items)
        if total_items > 0:
            total_pages = (total_items + per_page - 1) // per_page
            start_index = (page - 1) * per_page
            end_index = start_index + per_page
            
            # 获取当前页的物品
            items_list = list(shop_items.items())
            paginated_items = dict(items_list[start_index:end_index])
            shop_items = paginated_items
            
            has_prev = page > 1
            has_next = page < total_pages
        else:
            shop_items = {}
            
    except Exception as e:
        print(f"获取物品数据出错: {e}")
        shop_items = {}
        total_items = 0
        total_pages = 1
        has_prev = False
        has_next = False
    
    # 构建最终的shop_data
    shop_data = {
        'shop_items': shop_items,
        'total': total_items,
        'page': page,
        'per_page': per_page,
        'total_pages': total_pages,
        'has_prev': has_prev,
        'has_next': has_next
    }
    
    return render_template("shop.html", 
                         player=player, 
                         shop_data=shop_data,
                         shop_name=config['name'],
                         shop_type=shop_type)

@shop_bp.route("/buy_item", methods=["POST"])
@login_required
@check_health_status
@check_pk_status
def buy_item():
    player = DataService.get_current_player(session)
    item_id = request.form.get("item_id")
    quantity = request.form.get("quantity", type=int)
    shop_type = request.form.get("shop_type", "default")
    page = request.form.get("page", 1, type=int)
    per_page = request.form.get("per_page", 10, type=int)
    
    # 获取所有物品数据
    all_items = Item.load_items()
    if item_id not in all_items:
        flash("物品不存在", "error")
        return redirect(url_for('shop.shop', shop_type=shop_type, page=page, per_page=per_page))
    
    item = all_items[item_id]
    
    if item.price <= 0:
        flash("该物品不可购买", "error")
        return redirect(url_for('shop.shop', shop_type=shop_type, page=page, per_page=per_page))
    
    total_cost = item.price * quantity
    
    if quantity <= 0:
        flash("购买数量必须大于0", "error")
        return redirect(url_for('shop.shop', shop_type=shop_type, page=page, per_page=per_page))
    
    if player.money < total_cost:
        flash("余额不足", "error")
        return redirect(url_for('shop.shop', shop_type=shop_type, page=page, per_page=per_page))
    
    player.money -= total_cost
    for _ in range(quantity):
        player.add_item(item_id)
    
    DataService.save_player_data(session["username"], player)
    flash(f"成功购买{quantity}个{item.name}，花费{total_cost}银两", "success")
    
    return redirect(url_for('shop.shop', shop_type=shop_type, page=page, per_page=per_page))