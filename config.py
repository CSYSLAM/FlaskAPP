import os
import sys
from pathlib import Path


def get_base_path():
    """获取基础路径，支持PyInstaller打包"""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    else:
        return Path(__file__).parent


def get_instance_path():
    """获取instance路径"""
    base = get_base_path()
    instance_path = base / "instance"
    # 确保instance目录存在
    if not instance_path.exists():
        instance_path.mkdir(parents=True, exist_ok=True)
    return instance_path


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', os.urandom(32).hex())
    DATA_DIR = get_base_path() / "data"
    # 数据库放在instance目录下
    # check_same_thread=False: threaded=True 下允许跨线程访问(配合连接池每线程独立连接)
    SQLALCHEMY_DATABASE_URI = f'sqlite:///{get_instance_path() / "game_data.db"}?check_same_thread=False'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 10,
        'max_overflow': 20,
        'pool_pre_ping': True,
        'pool_recycle': 1800,
    }
    TEMPLATES_AUTO_RELOAD = True