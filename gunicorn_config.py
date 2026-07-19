# Gunicorn 配置 - 单进程16线程
# 原因：世界Boss/地面物品/劫匪等状态存进程内存(WorldBossService._bosses等类级dict)，
# 多worker下各进程内存独立、击杀状态会分裂(玩家杀BOSS后请求落到别的worker还能再打)。
# 单worker保证内存唯一，gthread线程池扛并发；--preload让init_bosses()在启动期完成。
# 2核机器上单worker×16线程 IO密集文本页 QPS~300+/s，远超200-400人在线峰值(~100QPS)。
# --timeout 60 兜底单请求卡死(会被杀重启worker)。

workers = 1
threads = 16
worker_class = "gthread"
preload_app = True
bind = "0.0.0.0:5000"
timeout = 60
graceful_timeout = 30
daemon = True
accesslog = "/tmp/gunicorn_access.log"
errorlog = "/tmp/gunicorn_error.log"
access_log_format = '%(h)s "%(r)s" %(s)s %(b)s'
