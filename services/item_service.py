import random
from services import db
from services.data_service import DataService
from models.player import PlayerModel


class ItemService:

    @classmethod
    def use_item(cls, player, item_id, is_bound=None):
        inv = DataService.get_inventory_item(player.id, item_id, is_bound=is_bound)
        if not inv or inv.quantity <= 0:
            return False, "物品不存在或数量不足"

        bound = inv.is_bound
        item_data = DataService.get_item(item_id)
        if not item_data:
            return False, "物品数据异常"

        if not item_data.get("is_usable", True):
            return False, "该物品不可使用"

        usage_effect = item_data.get("usage_effect", {})

        # Block lieutenant-specific items from inventory use (must use from lieutenant interface)
        if item_id.startswith('lt_') and item_id not in ('lt_potion_heal', 'lt_potion_mana', 'lt_double_exp'):
            return False, "该物品需在副将界面使用"

        # Special: enhance_lucky — set enhance bonus, prevent stacking
        if usage_effect.get("special") == "enhance_lucky":
            if player.enhance_bonus_rate and player.enhance_bonus_rate > 0:
                return False, "强化幸运符效果已存在，不可叠加使用"
            player.enhance_bonus_rate = 0.05
            DataService.remove_item_from_inventory(player.id, item_id, 1, is_bound=bound)
            db.session.commit()
            return True, "下一次强化成功率+5%"

        # Special: rename_card — redirect to rename flow
        if usage_effect.get("special") == "rename":
            DataService.remove_item_from_inventory(player.id, item_id, 1, is_bound=bound)
            db.session.commit()
            return True, "RENAME_CARD_USED"

        # VIP items use their own service
        if item_data.get("type") == "vip":
            from services.vip_service import VipService
            success, msg = VipService.use_zhuhouling(player, item_id, is_bound=bound)
            return success, msg

        usage_condition = item_data.get("usage_condition")
        if usage_condition:
            level_req = usage_condition.get("level_required", 0)
            if player.level < level_req:
                return False, f"需要等级{level_req}"

            required_items = usage_condition.get("required_items", {})
            for req_id, req_count in required_items.items():
                # Aggregate across bound/unbound stacks
                total = 0
                for is_b in (False, True):
                    inv = DataService.get_inventory_item(player.id, req_id, is_bound=is_b)
                    if inv:
                        total += inv.quantity
                if total < req_count:
                    req_data = DataService.get_item(req_id)
                    req_name = req_data.get("name", req_id) if req_data else req_id
                    return False, f"需要{req_count}个{req_name}"

        effect_text_parts = []

        # Process stat changes
        stat_changes = usage_effect.get("stat_changes", {})
        for stat, value in stat_changes.items():
            if hasattr(player, stat):
                setattr(player, stat, getattr(player, stat) + value)
                desc = usage_effect.get("effect_descriptions", {}).get(stat)
                if desc:
                    effect_text_parts.append(desc.format(value=value))

        # Process random_one_of effect (随机获得列表中的一种物品x1)
        random_one_of = usage_effect.get("random_one_of")
        if random_one_of and isinstance(random_one_of, list):
            chosen_id = random.choice(random_one_of)
            DataService.add_item_to_inventory(player.id, chosen_id, 1)
            chosen_data = DataService.get_item(chosen_id)
            chosen_name = chosen_data.get("name", chosen_id) if chosen_data else chosen_id
            effect_text_parts.append(f"获得{chosen_name}x1")

        # Process grant_gold effect (银两包)
        grant_gold = usage_effect.get("grant_gold")
        if grant_gold:
            player.gold += grant_gold
            effect_text_parts.append(f"获得{grant_gold}银两")

        # Process restore_vitality effect (活力卡)
        restore_vitality = usage_effect.get("restore_vitality")
        if restore_vitality:
            from models.villa import Villa
            villa = Villa.query.filter_by(owner_id=player.id).first()
            if villa:
                villa.action_points = min(villa.max_action_points, villa.action_points + restore_vitality)
                effect_text_parts.append(f"恢复{restore_vitality}点行动力")
            else:
                effect_text_parts.append("没有山庄，无法使用")

        # Process random stat changes
        stat_changes_rng = usage_effect.get("stat_changes_rng", {})
        for stat, rng_range in stat_changes_rng.items():
            if hasattr(player, stat):
                try:
                    low, high = int(rng_range[0]), int(rng_range[1])
                    delta = random.randint(low, high)
                    setattr(player, stat, getattr(player, stat) + delta)
                    desc = usage_effect.get("effect_descriptions", {}).get(stat)
                    if desc:
                        effect_text_parts.append(desc.format(value=delta))
                except (ValueError, TypeError):
                    pass

        # Process temp effects
        from models.player import TempEffect
        import time
        temp_effects = usage_effect.get("temp_effects", [])
        for te in temp_effects:
            stat = te.get("stat")
            if not stat:
                continue
            value = te.get("value", 0)
            rate = te.get("rate", 0)
            duration = te.get("duration", 0)
            expire_time = time.time() + duration
            effect_name = te.get("effect_name", item_data.get("name", ""))

            existing = TempEffect.query.filter_by(
                player_id=player.id, stat=stat, item_id=item_id
            ).first()
            if existing:
                remaining = max(0, existing.expire_time - time.time())
                existing.expire_time = time.time() + remaining + duration
                existing.value = max(existing.value, value)
                existing.rate = max(existing.rate, rate)
            else:
                db.session.add(TempEffect(
                    player_id=player.id,
                    stat=stat,
                    value=value,
                    rate=rate,
                    expire_time=expire_time,
                    item_id=item_id,
                    effect_name=effect_name,
                ))

            minutes = int(duration // 60)
            seconds = int(duration % 60)
            time_str = f"{minutes}分{seconds}秒" if minutes > 0 else f"{seconds}秒"
            stat_name = PlayerModel.STAT_NAMES.get(stat, stat)
            parts = []
            if value > 0:
                parts.append(f"+{value}")
            if rate > 0:
                parts.append(f"+{rate*100:.1f}%")
            effect_text_parts.append(
                f"{effect_name or stat_name}提升{'+'.join(parts)}，持续{time_str}")

        # Process grant_title effect
        grant_title_id = usage_effect.get("grant_title")
        if grant_title_id:
            from services.title_service import TitleService
            if grant_title_id in player.owned_titles:
                title_type = 'prefix' if grant_title_id.startswith('prefix') else 'suffix'
                title_def = DataService.get_title(grant_title_id, title_type)
                title_name = title_def.get('name', grant_title_id) if title_def else grant_title_id
                return False, f"已拥有称号【{title_name}】，无法重复使用"
            granted = TitleService.grant_title(player, grant_title_id, 'prefix' if grant_title_id.startswith('prefix') else 'suffix')
            if granted:
                title_type = 'prefix' if grant_title_id.startswith('prefix') else 'suffix'
                title_def = DataService.get_title(grant_title_id, title_type)
                title_name = title_def.get('name', grant_title_id) if title_def else grant_title_id
                stars = title_def.get('stars', 1) if title_def else 1
                effect_text_parts.append(f"获得称号【{title_name}】({stars}星)")
            else:
                return False, "称号授予失败"

        # Process item changes (supports aggregated removal across bound/unbound stacks)
        item_changes = usage_effect.get("item_changes", {})
        for change_id, change_count in item_changes.items():
            if change_count < 0:
                remaining = abs(change_count)
                for is_b in (False, True):
                    if remaining <= 0:
                        break
                    inv = DataService.get_inventory_item(player.id, change_id, is_bound=is_b)
                    if inv and inv.quantity > 0:
                        take = min(inv.quantity, remaining)
                        DataService.remove_item_from_inventory(
                            player.id, change_id, take, is_bound=is_b)
                        remaining -= take

        # Process grant_item effect (grant items directly)
        grant_item = usage_effect.get("grant_item")
        if grant_item:
            if isinstance(grant_item, list) and len(grant_item) >= 2:
                granted_id = grant_item[0]
                granted_count = grant_item[1]
                DataService.add_item_to_inventory(player.id, granted_id, granted_count, is_bound=False)
                granted_data = DataService.get_item(granted_id)
                granted_name = granted_data.get("name", granted_id) if granted_data else granted_id
                effect_text_parts.append(f"获得{granted_name}*{granted_count}")

        # Process random items
        random_items = usage_effect.get("random_items", [])
        from services.item_reward_registry import handle_reward
        for ri in random_items:
            reward_id = ri.get("item_id")
            max_count = ri.get("max_count", 1)
            chance = ri.get("chance", 1.0)
            guaranteed = ri.get("guaranteed_count", 0)

            total = guaranteed
            remaining = max_count - guaranteed
            for _ in range(remaining):
                if random.random() < chance:
                    total += 1

            if total > 0:
                handled = handle_reward(player, reward_id, total)
                if handled:
                    effect_text_parts.extend(handled)
                else:
                    DataService.add_item_to_inventory(player.id, reward_id, total)
                    reward_data = DataService.get_item(reward_id)
                    reward_name = reward_data.get("name", reward_id) if reward_data else reward_id
                    effect_text_parts.append(f"获得{reward_name}x{total}")

        # Process equipment generators
        from services.equipment_service import EquipmentService
        from services.equipment_generator import EquipmentSource
        equipment_generators = usage_effect.get("equipment_generators", [])
        awarded_count = 0
        for rule in equipment_generators:
            count = int(rule.get("count", 1))
            chance = float(rule.get("chance", 1.0))
            for _ in range(count):
                if random.random() <= chance:
                    pool = cls._build_template_pool(rule)
                    if pool:
                        equip = EquipmentService.generate_from_pool(
                            player.id, pool,
                            rarity_weights=rule.get("rarity_weights"),
                            star_range=(int(rule.get("star_range", [1, 5])[0]),
                                        int(rule.get("star_range", [1, 5])[1])) if "star_range" in rule else None,
                            star_weights=rule.get("star_weights"),
                            template_weights=rule.get("template_weights"),
                        )
                        if equip:
                            DataService.add_item_to_inventory(
                                player.id, equip.instance_id)
                            awarded_count += 1
                            effect_text_parts.append(f"获得装备{equip.name}")
                            if equip.rarity == "神器":
                                DataService.broadcast_system(
                                    f"恭喜{player.nickname}获得神器{equip.name}")

        # Process generate_equipment effect (single equipment from template)
        generate_equipment = usage_effect.get("generate_equipment")
        if generate_equipment:
            template_id = generate_equipment.get("template_id")
            template = DataService.get_equipment_template(template_id)
            if template:
                # Determine rarity
                rarity = generate_equipment.get("rarity")
                rarity_range = generate_equipment.get("rarity_range")
                if rarity_range:
                    rarity = random.choice(rarity_range)

                # Determine stars
                stars_range = generate_equipment.get("stars_range", [1, 5])
                stars = random.randint(int(stars_range[0]), int(stars_range[1]))

                # Generate equipment
                from services.equipment_service import EquipmentService
                equip = EquipmentService.generate_random_equipment(
                    player.id, template_id, rarity, stars)
                if equip:
                    DataService.add_item_to_inventory(player.id, equip.instance_id)
                    effect_text_parts.append(f"获得装备{equip.name}")

                    # 新婚戒指包特殊公告
                    if item_id in ('wedding_diamond_pack', 'wedding_ring_pack'):
                        DataService.broadcast_system(
                            f"{player.nickname}打开{item_data.get('name')}，获得了{equip.name}，恭喜恭喜！")
                    elif equip.rarity == "神器":
                        DataService.broadcast_system(
                            f"恭喜{player.nickname}获得神器{equip.name}")

        # Process lieutenant potion effects
        if item_id == 'lt_potion_heal':
            from models.lieutenant import Lieutenant
            from services.lieutenant_service import LieutenantService
            lt = Lieutenant.query.filter_by(owner_id=player.id, is_deployed=True).first()
            if lt:
                LieutenantService.heal(lt, 100)
                effect_text_parts.append(f"副将{lt.name}生命恢复100")
            else:
                effect_text_parts.append("没有出战副将")
        elif item_id == 'lt_potion_mana':
            from models.lieutenant import Lieutenant
            from services.lieutenant_service import LieutenantService
            lt = Lieutenant.query.filter_by(owner_id=player.id, is_deployed=True).first()
            if lt:
                LieutenantService.restore_mana(lt, 50)
                effect_text_parts.append(f"副将{lt.name}魔法恢复50")
            else:
                effect_text_parts.append("没有出战副将")

        # Pre-validate grant_lieutenant effect before consuming item
        grant_lieutenant = usage_effect.get("grant_lieutenant")
        if grant_lieutenant:
            from services.lieutenant_service import LieutenantService, SOUL_TO_LT, LIEUTENANT_DATA as LT_DATA
            soul_item_id_check = f'soul_{grant_lieutenant}'
            if soul_item_id_check not in SOUL_TO_LT:
                return False, "无效的魂魄"
            tier_check, pid_check = SOUL_TO_LT[soul_item_id_check]
            lt_info_check = LT_DATA[tier_check][pid_check]
            if LieutenantService._count_owned(player) >= LieutenantService.get_max_slots(player):
                return False, "副将位已满"
            if LieutenantService.has_lieutenant_by_name(player, lt_info_check['name']):
                return False, f"已拥有副将【{lt_info_check['name']}】"

        # Consume the item
        DataService.remove_item_from_inventory(player.id, item_id, 1, is_bound=bound)

        # Track item usage for achievements
        usage = player.item_usage
        usage[item_id] = usage.get(item_id, 0) + 1
        track_name = item_data.get("name")
        if track_name:
            usage[f"name:{track_name}"] = usage.get(f"name:{track_name}", 0) + 1
        player.item_usage = usage
        from services.achievement_service import AchievementService
        AchievementService.check(player, 'item_use')

        # Process grant_lieutenant effect (soul items) — actually grant the lieutenant
        if grant_lieutenant:
            from services.lieutenant_service import LieutenantService, SOUL_TO_LT as SLT, LIEUTENANT_DATA as LTD
            soul_item_id_real = f'soul_{grant_lieutenant}'
            tier_real, pid_real = SLT[soul_item_id_real]
            lt_info_real = LTD[tier_real][pid_real]
            success, msg = LieutenantService.grant_lieutenant_from_soul(player, tier_real, pid_real)
            if not success:
                # Refund the item since grant failed
                DataService.add_item_to_inventory(player.id, item_id, 1)
                return False, msg
            tier_name = {1: '一级', 2: '二级', 3: '三级'}.get(tier_real, '')
            effect_text_parts.append(f"获得{tier_name}副将【{lt_info_real['name']}】")

        # Process random_soul effect (soul banner)
        random_soul = usage_effect.get("random_soul")
        if random_soul:
            from services.lieutenant_service import LIEUTENANT_DATA as LTD2
            import random as _random
            roll = _random.randint(1, 100)
            if roll <= 80:
                tier_r = 3
            elif roll <= 99:
                tier_r = 2
            else:
                tier_r = 1
            candidates = LTD2[tier_r]
            pinyin_id_r = _random.choice(list(candidates.keys()))
            lt_info_r = candidates[pinyin_id_r]
            DataService.add_item_to_inventory(player.id, f'soul_{pinyin_id_r}', 1)
            tier_name_r = {1: '一级', 2: '二级', 3: '三级'}.get(tier_r, '')
            DataService.broadcast_system(f"{player.nickname}通过副将聚魂获得了{tier_name_r}魂魄【{lt_info_r['name']}】")
            effect_text_parts.append(f"获得{tier_name_r}魂魄【{lt_info_r['name']}】")

        # Process capacity expansion effects
        expand_backpack = usage_effect.get("expand_backpack")
        if expand_backpack:
            player.backpack_capacity += expand_backpack
            effect_text_parts.append(f"背包容量增加{expand_backpack}，当前容量{player.backpack_capacity}")

        expand_warehouse = usage_effect.get("expand_warehouse")
        if expand_warehouse:
            player.warehouse_capacity += expand_warehouse
            effect_text_parts.append(f"仓库容量增加{expand_warehouse}，当前容量{player.warehouse_capacity}")

        # (item already consumed above)

        db.session.commit()

        effect_text = "、".join(effect_text_parts) if effect_text_parts else "使用了物品"
        player.item_effect = effect_text
        return True, effect_text

    @classmethod
    def bulk_use(cls, player, item_id, quantity, is_bound=None):
        inv = DataService.get_inventory_item(player.id, item_id, is_bound=is_bound)
        if not inv or inv.quantity < quantity:
            return 0

        success_count = 0
        for _ in range(quantity):
            success, _ = cls.use_item(player, item_id, is_bound=is_bound)
            if success:
                success_count += 1
        return success_count

    @classmethod
    def _build_template_pool(cls, rule):
        templates = DataService.get_equipment_templates()
        explicit_ids = rule.get("template_ids")
        if explicit_ids:
            return [tid for tid in explicit_ids if tid in templates]

        pool = []
        level_min = int(rule.get("level_min", 1))
        level_max = int(rule.get("level_max", 999))
        slots = set(rule.get("slots", [])) if rule.get("slots") else None
        class_required = rule.get("class_required")
        class_set = set(class_required) if isinstance(class_required, list) else (
            {class_required} if class_required else None)
        include_artifact = rule.get("include_artifact", True)
        exclude_artifact = rule.get("exclude_artifact", False)

        for tid, t in templates.items():
            lv = t.get("level_required", 1)
            if lv < level_min or lv > level_max:
                continue
            slot_val = t.get("slot")
            if slots and slot_val not in slots:
                continue
            if class_set is not None:
                tpl_cls = t.get("class_required")
                if isinstance(tpl_cls, list):
                    if not (set(tpl_cls) & class_set):
                        continue
                elif tpl_cls not in class_set:
                    continue
            is_art = t.get("is_artifact", False)
            if exclude_artifact and is_art:
                continue
            if not include_artifact and is_art:
                continue
            pool.append(tid)
        return pool
