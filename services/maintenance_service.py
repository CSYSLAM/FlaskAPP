import threading
import time


class MaintenanceService:
    """全局后台维护任务：推进不应依赖玩家访问页面的状态机。"""

    _started = False

    @classmethod
    def start(cls, app):
        if cls._started:
            return
        cls._started = True

        def _loop():
            while True:
                try:
                    with app.app_context():
                        cls.run_once()
                except Exception:
                    pass
                time.sleep(60)

        t = threading.Thread(target=_loop, name='game-maintenance', daemon=True)
        t.start()

    @classmethod
    def run_once(cls):
        """执行一次维护循环；也可用于测试/手动触发。"""
        from services.market_service import MarketService
        from services.legion_service import LegionService
        from services.copy_dungeon_service import CopyDungeonService

        MarketService.expire_listings()
        LegionService.reset_all_daily_counters()
        CopyDungeonService.reset_all_daily_free_entries()
